#!/usr/bin/env python3
"""Size-based log rotation (copy -> gzip archive -> truncate live file).

User-level replacement for newsyslog (no sudo needed). Runs daily from
~/Library/LaunchAgents/com.tho.logrotate.plist.

* Never deletes anything: archives are kept forever under <logdir>/archive/.
* Live file is truncated in place so writers holding it open (O_APPEND)
  keep working without restart.
* Only files larger than THRESHOLD are rotated.
"""
import gzip
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

THRESHOLD = int(os.environ.get("ROTATE_THRESHOLD_MB", "10")) * 1024 * 1024
HOME = Path.home()
TARGETS = [
    HOME / "Projects/ai_secretary_brain/logs/app.log",
    HOME / "Projects/ai_secretary_brain/logs/scheduler.log",
    HOME / "Projects/ai_secretary_brain/logs/launchd.out.log",
    HOME / "Projects/ai_secretary_brain/logs/launchd.err.log",
    HOME / "Projects/ai_secretary_brain/logs/ngrok.log",
]
GLOBS = [
    (HOME / "Projects/investment_advisor/logs", "*.log"),
    (HOME / "Projects/investment_advisor/data_collector/logs", "*_process.log"),
    (HOME / "Projects/investment_advisor/data_collector/logs", "orchestrator.log"),
    (HOME / "Projects/investment_advisor/ai_engine/logs", "*.log"),
    (HOME / "Projects/investment_advisor/portfolio_engine/logs", "*.log"),
]


def rotate(path: Path, dry: bool) -> None:
    try:
        size = path.stat().st_size
    except FileNotFoundError:
        return
    if size < THRESHOLD:
        return
    arch_dir = path.parent / "archive"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = arch_dir / f"{path.name}.{stamp}.gz"
    print(f"rotate {path} ({size/1e6:.1f} MB) -> {dest}{' [dry-run]' if dry else ''}")
    if dry:
        return
    arch_dir.mkdir(exist_ok=True)
    with open(path, "rb") as src, gzip.open(dest, "wb", compresslevel=6) as out:
        shutil.copyfileobj(src, out, 1024 * 1024)
    # verify archive readable before truncating
    with gzip.open(dest, "rb") as chk:
        chk.read(1)
    os.truncate(path, 0)


def main() -> None:
    dry = "--dry-run" in sys.argv
    files = list(TARGETS)
    for d, pat in GLOBS:
        if d.exists():
            files.extend(sorted(d.glob(pat)))
    for f in files:
        try:
            rotate(f, dry)
        except Exception as exc:  # keep going
            print(f"ERROR rotating {f}: {exc}", file=sys.stderr)
    print(f"{datetime.now().isoformat()} rotate_logs done ({len(files)} candidates)")


if __name__ == "__main__":
    main()
