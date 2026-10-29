"""Portfolio intelligence engine."""

import sys
from pathlib import Path

# Keep modules runnable both as ``portfolio_engine.api`` and from this directory.
ENGINE_DIR = Path(__file__).resolve().parent
if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))
