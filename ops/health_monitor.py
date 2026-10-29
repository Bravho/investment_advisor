#!/usr/bin/env python3
"""Investment-advisor stack health monitor.

Checks every service port, the data-collector heartbeat age and the public
dashboard tunnel. On a state change (OK -> FAIL, or FAIL -> OK) it pushes a
LINE alert to Tho via ai_secretary_brain's existing
``services.line_client.send_to_owner`` (respects Do-Not-Disturb periods).

* Alerts are de-duplicated: one message per state change, plus a reminder
  every REMIND_HOURS while something stays down (saves LINE push quota).
* ``--dry-run`` (or HEALTH_MONITOR_DRY_RUN=1) never sends; it only logs the
  message that would be sent.
* ``--test-alert`` sends one clearly-labelled test message (manual use only).

Run with ai_secretary_brain's venv python (has the LINE SDK). Scheduled by
~/Library/LaunchAgents/com.tho.investment.healthmonitor.plist every 5 min.
"""
from __future__ import annotations

import json
import os
import socket
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
PROJECT = HOME / "Projects/investment_advisor"
SECRETARY = HOME / "Projects/ai_secretary_brain"
STATE_FILE = PROJECT / "logs/health_state.json"
LOG_FILE = PROJECT / "logs/health_monitor.log"
HEARTBEAT = PROJECT / "data_collector/heartbeat.json"
PUBLIC_URL_FILE = HOME / ".config/investment_advisor/public_url.txt"
HEARTBEAT_MAX_AGE_MIN = 15
REMIND_HOURS = 6

PORTS = {
    "Main advisor API (8991)": 8991,
    "Orchestrator / data collector (8090)": 8090,
    "AI engine (8997)": 8997,
    "Portfolio engine (8996)": 8996,
    "Guru council (8993)": 8993,
    "Dashboard (3999)": 3999,
    "Dashboard auth proxy (19091)": 19091,
    "AI secretary / LINE webhook (8999)": 8999,
    "PostgreSQL (5432)": 5432,
    "Ollama (11434)": 11434,
}


def log(msg: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')} {msg}"
    print(line)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=3):
            return True
    except OSError:
        return False


def heartbeat_problem() -> str | None:
    try:
        data = json.loads(HEARTBEAT.read_text())
        ts = datetime.fromisoformat(data["timestamp"])
        age = (datetime.now(timezone.utc) - ts).total_seconds() / 60
        if age > HEARTBEAT_MAX_AGE_MIN:
            return f"heartbeat stale ({age:.0f} min old)"
        bad = [n for n, w in (data.get("workers") or {}).items() if w.get("status") != "running"]
        if bad:
            return "workers not running: " + ", ".join(bad)
    except Exception as exc:  # noqa: BLE001
        return f"heartbeat unreadable ({exc.__class__.__name__})"
    return None


def tunnel_problem() -> str | None:
    """Public URL should answer 401 (auth required) or 200. Read-only HEAD."""
    try:
        url = PUBLIC_URL_FILE.read_text().strip().split()[0]
    except Exception:
        return None  # no tunnel configured -> nothing to check
    req = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            code = resp.status
    except urllib.error.HTTPError as exc:
        code = exc.code
    except Exception as exc:  # noqa: BLE001
        return f"public dashboard unreachable ({exc.__class__.__name__})"
    return None if code in (200, 401) else f"public dashboard HTTP {code}"


def collect() -> dict[str, str | None]:
    results: dict[str, str | None] = {}
    for name, port in PORTS.items():
        results[name] = None if port_open(port) else "port not listening"
    results["Collector heartbeat"] = heartbeat_problem()
    results["Public dashboard tunnel"] = tunnel_problem()
    return results


def send_line(text: str, dry: bool) -> bool:
    if dry:
        log("DRY-RUN would send LINE: " + text.replace("\n", " | "))
        return True
    sys.path.insert(0, str(SECRETARY))
    os.chdir(SECRETARY)  # so line_client's load_dotenv() finds the secretary .env
    from services.line_client import send_to_owner  # type: ignore

    ok = send_to_owner(text)
    log(f"LINE alert sent={ok}")
    return ok


def main() -> int:
    dry = "--dry-run" in sys.argv or os.getenv("HEALTH_MONITOR_DRY_RUN") == "1"
    if "--test-alert" in sys.argv:
        return 0 if send_line("🧪 TEST: investment advisor health monitor can reach you on LINE.", dry) else 1

    results = collect()
    failing = {k: v for k, v in results.items() if v}
    try:
        state = json.loads(STATE_FILE.read_text())
    except Exception:
        state = {"failing": {}, "last_alert": None}

    prev = set(state.get("failing", {}))
    now_fail = set(failing)
    new_fail = now_fail - prev
    recovered = prev - now_fail
    remind = False
    if now_fail and state.get("last_alert"):
        last = datetime.fromisoformat(state["last_alert"])
        remind = (datetime.now() - last).total_seconds() > REMIND_HOURS * 3600

    log(f"check: {len(results) - len(failing)}/{len(results)} OK" + (f"; failing: {failing}" if failing else ""))

    if new_fail or recovered or remind:
        lines = ["⚠️ Investment Advisor health alert" if now_fail else "✅ Investment Advisor recovered"]
        for k in sorted(now_fail):
            lines.append(f"❌ {k}: {failing[k]}{' (new)' if k in new_fail else ''}")
        for k in sorted(recovered):
            lines.append(f"✅ {k}: back up")
        lines.append(datetime.now().strftime("%Y-%m-%d %H:%M ICT"))
        if send_line("\n".join(lines), dry):
            state["last_alert"] = datetime.now().isoformat()

    state["failing"] = failing
    state["checked_at"] = datetime.now().isoformat()
    if not dry:
        STATE_FILE.write_text(json.dumps(state, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
