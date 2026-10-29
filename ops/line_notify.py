"""Send stdin text to Tho via the secretary's LINE client (respects Do-Not-Disturb).

Run with the secretary venv:  ai_secretary_brain/venv/bin/python ops/line_notify.py < message.txt
Exit 0 = sent, 2 = skipped (quiet period / not configured), 1 = error. Never prints secrets.
"""
import os
import sys
from pathlib import Path

SECRETARY = Path(os.getenv("SECRETARY_DIR", "/Users/admin/Projects/ai_secretary_brain"))
text = sys.stdin.read().strip()
if not text:
    sys.exit(1)
if os.getenv("WATCH_ALERTS_DRY_RUN") == "1":
    print("dry-run, not sent")
    sys.exit(0)
sys.path.insert(0, str(SECRETARY))
os.chdir(SECRETARY)
from services.line_client import send_to_owner  # noqa: E402

ok = send_to_owner(text)  # non-urgent -> skipped during DND periods
print("sent" if ok else "not sent (quiet period or error)")
sys.exit(0 if ok else 2)
