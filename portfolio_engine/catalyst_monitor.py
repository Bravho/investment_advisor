"""
Catalyst slippage monitor.

Reads the dated catalyst calendar stored in ``data/watchlist.json`` (the
``catalysts`` object: ISO-date -> description) and classifies each entry
relative to today:

    upcoming   — date is in the future
    today      — date is today
    overdue    — date has passed (and the entry is not marked confirmed)

Motivation (added by nightly agent 2026-06-15): the US-Iran peace deal was
"scheduled to be signed Sunday 2026-06-14" but slipped without a formal
signing — Tehran disputed the timeline. A scheduled, market-moving catalyst
that passes its date *without confirmation* is itself a risk signal: any
trade thesis priced off the assumed outcome (e.g. PTTEP/oil premium unwind)
must be re-checked rather than assumed realised.

This module is intentionally dependency-light (stdlib only) and never
mutates the watchlist — it only reports. Designed to be called by the
nightly pipeline and surfaced in the morning brief.

A catalyst is treated as CONFIRMED (and therefore not flagged overdue) when
its description contains a confirmation marker — any of: "CONFIRMED",
"COMPLETED", "SIGNED", "RELEASED", "DONE" (case-insensitive) — UNLESS it also
contains scheduling language ("SCHEDULED", "TO BE SIGNED", "EXPECTED", "EST.",
"LIKELY", "PENDING") which always wins. This matters because a calendar entry
like "deal SCHEDULED TO BE SIGNED Sunday" contains the word "SIGNED" but is a
*plan*, not an outcome — it must stay flagged until the calendar is updated
with the real result.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

try:
    from utils.common import PROJECT_DIR, configure_logging  # type: ignore
    logger = configure_logging("portfolio_engine.catalyst_monitor")
except Exception:  # pragma: no cover - allow standalone use outside the app
    import logging
    PROJECT_DIR = Path(__file__).resolve().parent.parent
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("portfolio_engine.catalyst_monitor")


_CONFIRM_MARKERS = ("CONFIRMED", "COMPLETED", "SIGNED", "RELEASED", "DONE")
# Scheduling language always overrides a confirmation marker: a *planned*
# event is not a *confirmed* one even if it contains the word "signed".
_SCHEDULE_MARKERS = (
    "SCHEDULED", "TO BE SIGNED", "TO GET SIGNED", "EXPECTED", "EST.",
    "ESTIMATED", "LIKELY", "PENDING", "PREVIEW", "NOT SIGNED", "UNSIGNED",
    "SLIPPED",
)
_DATE_KEY_LEN = 10  # "YYYY-MM-DD"


def _watchlist_path() -> Path:
    return PROJECT_DIR / "data" / "watchlist.json"


def _parse_date_key(key: str) -> date | None:
    """Catalyst keys are ISO dates; some use a YYYY-MM-DD_HH suffix. Take the
    leading YYYY-MM-DD and parse it. Returns None if unparseable."""
    head = key[:_DATE_KEY_LEN]
    try:
        return datetime.strptime(head, "%Y-%m-%d").date()
    except ValueError:
        return None


def _is_confirmed(description: str) -> bool:
    upper = description.upper()
    # Scheduling language wins: a planned event is never "confirmed".
    if any(marker in upper for marker in _SCHEDULE_MARKERS):
        return False
    return any(marker in upper for marker in _CONFIRM_MARKERS)


def load_catalysts(watchlist_path: Path | None = None) -> dict[str, str]:
    """Load the raw {date_key: description} catalyst map from watchlist.json."""
    path = watchlist_path or _watchlist_path()
    if not path.exists():
        logger.warning("watchlist.json not found at %s", path)
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        logger.warning("Could not parse watchlist.json at %s", path)
        return {}
    catalysts = data.get("catalysts", {})
    return {str(k): str(v) for k, v in catalysts.items()}


def classify_catalysts(
    today: date | None = None,
    watchlist_path: Path | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """
    Classify every catalyst into upcoming / today / overdue buckets.

    Returns a dict with keys ``upcoming``, ``today``, ``overdue`` — each a
    list of ``{date, days_delta, confirmed, description}`` records sorted by
    date. ``days_delta`` is positive for future dates, negative for past.
    """
    today = today or date.today()
    buckets: dict[str, list[dict[str, Any]]] = {"upcoming": [], "today": [], "overdue": []}

    for key, desc in load_catalysts(watchlist_path).items():
        d = _parse_date_key(key)
        if d is None:
            continue
        delta = (d - today).days
        confirmed = _is_confirmed(desc)
        record = {
            "date": d.isoformat(),
            "days_delta": delta,
            "confirmed": confirmed,
            "description": desc,
        }
        if delta > 0:
            buckets["upcoming"].append(record)
        elif delta == 0:
            buckets["today"].append(record)
        else:
            buckets["overdue"].append(record)

    for name in buckets:
        buckets[name].sort(key=lambda r: r["date"])
    return buckets


def slipped_catalysts(
    today: date | None = None,
    watchlist_path: Path | None = None,
) -> list[dict[str, Any]]:
    """
    Return catalysts whose date has passed but which are NOT marked confirmed
    — i.e. scheduled events that may have slipped. These are the entries that
    warrant a manual re-check (and a watchlist update) before any dependent
    thesis is treated as resolved.
    """
    overdue = classify_catalysts(today, watchlist_path)["overdue"]
    return [r for r in overdue if not r["confirmed"]]


def catalyst_alert_summary(
    today: date | None = None,
    horizon_days: int = 5,
    watchlist_path: Path | None = None,
) -> dict[str, Any]:
    """
    Compact summary for the morning brief.

    - ``imminent``: confirmed-or-not catalysts within the next ``horizon_days``
      (including today) — what to watch this week.
    - ``slipped``: overdue + unconfirmed catalysts — what may have failed to
      occur as scheduled and needs verification.
    """
    buckets = classify_catalysts(today, watchlist_path)
    imminent = [
        r for r in (buckets["today"] + buckets["upcoming"])
        if 0 <= r["days_delta"] <= horizon_days
    ]
    slipped = [r for r in buckets["overdue"] if not r["confirmed"]]
    summary = {
        "as_of": (today or date.today()).isoformat(),
        "horizon_days": horizon_days,
        "imminent_count": len(imminent),
        "slipped_count": len(slipped),
        "imminent": imminent,
        "slipped": slipped,
    }
    if slipped:
        logger.warning(
            "%d scheduled catalyst(s) appear to have slipped without confirmation: %s",
            len(slipped),
            ", ".join(f"{r['date']} ({-r['days_delta']}d ago)" for r in slipped),
        )
    return summary


if __name__ == "__main__":  # pragma: no cover - manual smoke test
    import pprint

    pprint.pprint(catalyst_alert_summary())
