"""Scheduled refresh of the Thai watch list. Runs inside the portfolio engine (APScheduler, Mon-Fri).

Free and local only: yfinance pulls, pandas scoring, and a JSON write. No paid API, no agent session.

Safety:
- Pulls and scoring run in a fresh temp folder. The live data/thai_watchlist.json is replaced only
  when every step succeeds, and the replacement is atomic (write temp file, then os.replace).
- If any step fails or times out, the previous good file stays and the failure is logged.
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIVE_JSON = HERE.parents[1] / "data" / "thai_watchlist.json"
STEP_TIMEOUT_S = 900
STEPS = [
    ("pull_stocks", "pull_stocks.py"),
    ("pull_funds", "pull_funds.py"),
    ("analyze_stocks", "analyze_stocks.py"),
    ("analyze_funds", "analyze_funds.py"),
]
log = logging.getLogger("portfolio_engine.thai_watchlist")


def _run(step: str, script: Path, cwd: Path, extra: list[str] | None = None) -> None:
    cmd = [sys.executable, str(script), *(extra or [])]
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=STEP_TIMEOUT_S)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-3:]
        raise RuntimeError(f"{step} failed (exit {proc.returncode}): {' | '.join(tail)}")


def run_refresh() -> dict:
    """Blocking. Returns a short summary dict. Raises on failure (live file untouched)."""
    with tempfile.TemporaryDirectory(prefix="thai_wl_") as tmp:
        work = Path(tmp)
        for step, script in STEPS:
            _run(step, HERE / script, work)
        _run("build", HERE / "build_watchlist.py", HERE,
             ["--src", str(work), "--out", str(LIVE_JSON)])
    import json
    data = json.loads(LIVE_JSON.read_text(encoding="utf-8"))
    alerts = [x["ticker"] for x in data["stocks"] + data["funds"] if x.get("xd", {}).get("next_xd", {}).get("alert_within_60d")]
    return {"as_of_prices": data["as_of_prices"], "stocks": len(data["stocks"]), "funds": len(data["funds"]), "xd_alerts": alerts}


async def refresh() -> dict:
    """Async wrapper for the scheduler. Keeps the event loop free while yfinance runs."""
    try:
        summary = await asyncio.to_thread(run_refresh)
        log.info("Thai watch list refreshed: %s", summary)
        return summary
    except Exception:
        log.exception("Thai watch list refresh failed; previous file kept")
        raise
