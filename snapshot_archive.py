"""Shared, dependency-free daily snapshot archiver.

Added 2026-10-29 (Phase 2). Both ai_engine and portfolio_engine have a
top-level package called ``utils``, so ai_engine could not import
``portfolio_engine.performance_analytics`` (ModuleNotFoundError / wrong
``utils``). This stdlib-only module is loaded by file path from either side and
writes data/snapshots/YYYY-MM-DD.json exactly like
performance_analytics.save_daily_snapshot().
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Any, Optional

PROJECT_DIR = Path(__file__).resolve().parent
logger = logging.getLogger("snapshot_archive")


def save_daily_snapshot(snapshot_data: dict[str, Any], output_dir: Optional[Path] = None) -> Path:
    base = output_dir or (PROJECT_DIR / "data" / "snapshots")
    base.mkdir(parents=True, exist_ok=True)
    today_str = date.today().isoformat()
    out_path = base / f"{today_str}.json"
    payload: dict[str, Any] = {"snapshot_date": today_str, **snapshot_data}
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    logger.info("Daily portfolio snapshot saved to %s", out_path)
    return out_path


def load_shared_save_daily_snapshot():
    """Return save_daily_snapshot loaded by file path (safe from utils clashes)."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("ia_snapshot_archive", Path(__file__).resolve())
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module.save_daily_snapshot
