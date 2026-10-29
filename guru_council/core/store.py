"""Local JSON persistence — analyzed reports and saved source sets.

Keeping analyzed data locally (per the project goal) enables comparison and
trend tracking over time without requiring a database. Swap in Postgres later
by reimplementing these functions.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from ..config import DATA_DIR, REPORTS_DIR, SOURCESETS_DIR

_WATCHLIST = DATA_DIR / "watchlist.json"
_HOLDINGS = DATA_DIR / "holdings.json"
# the user's current holdings — excluded from new-idea discovery
DEFAULT_HOLDINGS = ["SCB.BK", "PTTEP.BK", "SCBGOLDE"]


def _safe(ticker: str) -> str:
    return ticker.upper().replace("/", "_").replace("\\", "_")


# -- source sets ------------------------------------------------------------
def save_source_set(ticker: str, sources: list[dict[str, Any]]) -> None:
    path = SOURCESETS_DIR / f"{_safe(ticker)}.json"
    path.write_text(json.dumps(sources, indent=2, ensure_ascii=False), encoding="utf-8")


def load_source_set(ticker: str) -> list[dict[str, Any]] | None:
    path = SOURCESETS_DIR / f"{_safe(ticker)}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


# -- reports ----------------------------------------------------------------
def save_report(report: dict[str, Any]) -> None:
    report.setdefault("created_at", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    ticker = report["investment"]["ticker"]
    path = REPORTS_DIR / f"{_safe(ticker)}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


def load_report(ticker: str) -> dict[str, Any] | None:
    path = REPORTS_DIR / f"{_safe(ticker)}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def all_reports() -> list[dict[str, Any]]:
    out = []
    for path in sorted(REPORTS_DIR.glob("*.json")):
        try:
            out.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            continue
    return out


# -- watchlist --------------------------------------------------------------
def get_watchlist() -> list[str]:
    if _WATCHLIST.exists():
        try:
            return json.loads(_WATCHLIST.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def add_watchlist(ticker: str) -> list[str]:
    wl = get_watchlist()
    t = ticker.upper()
    if t not in wl:
        wl.append(t)
        _WATCHLIST.write_text(json.dumps(wl, indent=2, ensure_ascii=False), encoding="utf-8")
    return wl


# -- holdings (excluded from discovery) ------------------------------------
def get_holdings() -> list[str]:
    if not _HOLDINGS.exists():
        _HOLDINGS.write_text(json.dumps(DEFAULT_HOLDINGS, indent=2, ensure_ascii=False), encoding="utf-8")
        return list(DEFAULT_HOLDINGS)
    try:
        return [t.upper() for t in json.loads(_HOLDINGS.read_text(encoding="utf-8"))]
    except Exception:
        return list(DEFAULT_HOLDINGS)
