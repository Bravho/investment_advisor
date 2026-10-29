#!/usr/bin/env python3
"""Double-fork launcher for investment_advisor services (macOS-safe).

Used by start_all.sh and by ai_secretary_brain/scripts/start_advisors.sh so the
stack survives parent-shell teardown. Does NOT place trades or change money settings.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOG = ROOT / "logs"
PORTS = {
    "orchestrator": 8090,
    "ai_engine": 8997,  # usually started by orchestrator worker; optional direct
    "portfolio_engine": 8996,
    "advisor": 8991,
    "guru_council": 8993,
    "dashboard": 3999,
}


def port_open(port: int) -> bool:
    try:
        out = subprocess.check_output(["lsof", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"], stderr=subprocess.DEVNULL)
        return bool(out.strip())
    except subprocess.CalledProcessError:
        return False


def spawn(name: str, argv: list[str], cwd: Path) -> None:
    LOG.mkdir(exist_ok=True)
    log_path = LOG / f"{name}.log"
    pid_path = LOG / f"{name}.pid"
    if os.fork() != 0:
        time.sleep(0.15)
        return
    os.setsid()
    if os.fork() != 0:
        os._exit(0)
    os.chdir(str(cwd))
    with open(log_path, "a", encoding="utf-8") as lf:
        lf.write(f"\n===== spawn {name} {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n")
        lf.flush()
        os.dup2(lf.fileno(), 1)
        os.dup2(lf.fileno(), 2)
    with open("/dev/null", "r", encoding="utf-8") as dn:
        os.dup2(dn.fileno(), 0)
    p = subprocess.Popen(argv, cwd=str(cwd), start_new_session=True)
    pid_path.write_text(str(p.pid))
    os._exit(0)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-dashboard", action="store_true")
    parser.add_argument("--skip-if-up", action="store_true", help="Do not restart services whose ports already listen")
    args = parser.parse_args()

    services = [
        (
            "orchestrator",
            [str(ROOT / "data_collector" / "venv" / "bin" / "python"), "orchestrator.py", "start"],
            ROOT / "data_collector",
            8090,
        ),
        (
            "portfolio_engine",
            [str(ROOT / "venv" / "bin" / "python"), "api.py"],
            ROOT / "portfolio_engine",
            8996,
        ),
        (
            "advisor",
            [str(ROOT / "venv" / "bin" / "python"), "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8991"],
            ROOT,
            8991,
        ),
        (
            "guru_council",
            [str(ROOT / "venv" / "bin" / "python"), "-m", "guru_council.cli", "serve", "--port", "8993"],
            ROOT,
            8993,
        ),
    ]
    if not args.skip_dashboard:
        services.append(("dashboard", ["npm", "run", "dev"], ROOT / "dashboard", 3999))

    # Ensure Postgres hint only (do not start brew services here unless missing)
    try:
        subprocess.run(["pg_isready", "-q"], check=False)
    except FileNotFoundError:
        pass

    for name, argv, cwd, port in services:
        if args.skip_if_up and port_open(port):
            print(f"skip {name}: port {port} already listening")
            continue
        print(f"launch {name}...")
        spawn(name, argv, cwd)
        time.sleep(0.4)

    time.sleep(3)
    for name, port in [("orchestrator", 8090), ("ai_engine_via_orch", 8997), ("portfolio_engine", 8996), ("advisor", 8991), ("guru_council", 8993), ("dashboard", 3999)]:
        print(f"port {port} ({name}): {'UP' if port_open(port) else 'DOWN'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
