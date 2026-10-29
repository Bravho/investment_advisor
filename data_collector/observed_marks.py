"""
Agent-observed mark store — provenance-carrying prices the nightly agent
retrieved itself, for use when no automated feed can reach the market.

WHY THIS MODULE EXISTS
----------------------
On 2026-08-10 this project shipped ``th_price_fallback.py``, a stdlib-only
end-of-day SET price reader, explicitly so that the nightly agent could obtain
marks without the dead collector daemon. The Aug-10 run verified the parser
against captured HTML and queued "run it live from the project machine" as the
next priority.

On 2026-08-11 it was run live from the nightly agent's own execution sandbox
and **failed on every ticker with** ``urlopen error Tunnel connection failed:
403 Forbidden``. Direct outbound HTTP from that sandbox — ``urllib``, ``curl``,
``requests``, any of it — is blocked at an egress proxy. The parser was never
the problem; the *caller* has no network.

That is a structural fact worth stating plainly, because it invalidates a
design assumption the last three runs were built on:

    The nightly agent CAN read the web, but only through its own retrieval
    tooling. It CANNOT do so from inside Python. Therefore no Python module in
    this project can be the nightly agent's price path.

``th_price_fallback.py`` is still correct and still useful — but only when run
on Tho's own machine, where egress is unrestricted. It is a host-side tool, not
an agent-side one, and it was queued as the latter.

This module is the agent-side half. The nightly agent retrieves a price with
its own tooling, then calls ``record_mark()`` to deposit it here with full
provenance. Everything downstream reads from this store and can always tell
where a number came from, when the market printed it, and how many independent
sources agreed.

WHY PROVENANCE IS MANDATORY, NOT OPTIONAL
-----------------------------------------
On 2026-08-10 the project discovered that its carried BAFS mark of 9.80 was
wrong by +18.4% — the real close was 11.60. The 9.80 was a February/June price
that had been stamped with an August date. It survived five nightly runs
because nothing recorded *where it came from* or *what session it described*,
so there was no way to falsify it. It rendered exactly like a good number.

Hence the rules below. They are deliberately strict; a mark that cannot satisfy
them is rejected outright rather than stored with a warning, because a warning
in a JSON file is not read by anybody at 2:30 a.m.

DESIGN RULES
------------
1. **No provenance, no mark.** ``source_name``, ``source_url`` and
   ``observed_as_of`` (the SESSION DATE, from the source itself) are required.
   A mark missing any of them raises ``MarkRejected``.
2. **Observation date and retrieval date are separate fields and are never
   conflated.** ``observed_as_of`` is the trading session the price describes.
   ``retrieved_at`` is when the agent looked. The Aug-10 defect was precisely
   these two being collapsed into one.
3. **Absence propagates as absent.** Accessors return ``None``, never ``0`` and
   never a silently carried previous value.
4. **Corroboration is counted, not assumed.** A second source agreeing within
   tolerance raises ``corroboration`` and is recorded in ``sources``. A second
   source *dis*agreeing is recorded as a conflict and does NOT overwrite.
5. **Age is refused, not warned about.** ``get_mark()`` returns None past
   ``max_age_days``.
6. **A portfolio total made of mixed-date legs says so.** ``portfolio_marks()``
   reports ``mark_dates`` and ``mark_date_mixed`` so a total assembled from a
   Monday leg and a Friday leg is never presented as a Monday total.

Added by nightly agent 2026-08-11
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_STORE_PATH = _PROJECT_ROOT / "data" / "observed_marks.json"

# Two independent quotes of the same session are treated as corroborating if
# they differ by less than this. SET ticks are 0.10/0.50 depending on price
# band, so anything under a quarter of a percent is a rounding or vendor-lag
# artefact rather than a disagreement about what happened.
_CORROBORATION_TOLERANCE_PCT = 0.25

_DEFAULT_MAX_AGE_DAYS = 7


class MarkRejected(ValueError):
    """Raised when a candidate mark fails the provenance rules."""


@dataclass
class ObservedMark:
    """
    One price for one instrument, for one trading session, with its paper trail.

    ``observed_as_of`` is the session the price describes, taken from the
    source. ``retrieved_at`` is when the agent fetched it. These are different
    questions and this project has already been burned once by answering the
    first with the second.
    """

    ticker: str
    close: float
    currency: str
    observed_as_of: str          # ISO date of the TRADING SESSION
    retrieved_at: str            # ISO timestamp of the RETRIEVAL
    source_name: str
    source_url: str
    corroboration: int = 1       # number of independent sources agreeing
    sources: list[dict[str, Any]] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    note: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def age_days(self, reference: Optional[date] = None) -> Optional[int]:
        try:
            observed = date.fromisoformat(self.observed_as_of)
        except (TypeError, ValueError):
            return None
        return ((reference or date.today()) - observed).days

    @property
    def is_corroborated(self) -> bool:
        """True once at least two independent sources agree on this session."""
        return self.corroboration >= 2


# --------------------------------------------------------------------------
# Store I/O — never raises, never returns a fabricated value
# --------------------------------------------------------------------------

def _load_store() -> dict[str, Any]:
    if not _STORE_PATH.exists():
        return {"_meta": {}, "marks": {}}
    try:
        with _STORE_PATH.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("observed_marks store unreadable (%s) — treating as EMPTY, "
                     "not as 'no marks exist'.", exc)
        return {"_meta": {"read_error": str(exc)}, "marks": {}}
    data.setdefault("marks", {})
    data.setdefault("_meta", {})
    return data


def _save_store(store: dict[str, Any]) -> Optional[Path]:
    store["_meta"]["last_written"] = datetime.now(timezone.utc).isoformat()
    store["_meta"]["written_by"] = "data_collector/observed_marks.py"
    try:
        _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _STORE_PATH.open("w", encoding="utf-8") as handle:
            json.dump(store, handle, indent=2, ensure_ascii=False, sort_keys=False)
        return _STORE_PATH
    except OSError as exc:
        logger.error("Could not write observed_marks store: %s", exc)
        return None


def store_status() -> dict[str, Any]:
    """
    Report on the store itself, so callers can tell "no marks recorded" from
    "the store was never created" — the distinction the dividend-tracker bug
    turned on.
    """
    store = _load_store()
    marks = store.get("marks", {})
    return {
        "store_exists": _STORE_PATH.exists(),
        "path": str(_STORE_PATH),
        "ticker_count": len(marks),
        "tickers": sorted(marks),
        "last_written": store.get("_meta", {}).get("last_written"),
        "read_error": store.get("_meta", {}).get("read_error"),
    }


# --------------------------------------------------------------------------
# Write path
# --------------------------------------------------------------------------

def _validate(
    ticker: str,
    close: Any,
    observed_as_of: Any,
    source_name: Any,
    source_url: Any,
) -> None:
    """Rule 1. Reject, do not warn."""
    if not ticker or not isinstance(ticker, str):
        raise MarkRejected("ticker is required")
    if close is None:
        raise MarkRejected(f"{ticker}: close is None — record nothing rather than zero")
    try:
        value = float(close)
    except (TypeError, ValueError) as exc:
        raise MarkRejected(f"{ticker}: close {close!r} is not numeric") from exc
    if value <= 0:
        raise MarkRejected(f"{ticker}: close {value} is not a positive price")
    if not observed_as_of:
        raise MarkRejected(
            f"{ticker}: observed_as_of is required. A price without the session "
            "it describes is what produced the 2026-08-10 marks error."
        )
    try:
        date.fromisoformat(str(observed_as_of))
    except ValueError as exc:
        raise MarkRejected(
            f"{ticker}: observed_as_of {observed_as_of!r} is not an ISO date"
        ) from exc
    if not source_name:
        raise MarkRejected(f"{ticker}: source_name is required")
    if not source_url or not str(source_url).startswith("http"):
        raise MarkRejected(
            f"{ticker}: source_url must be a retrievable URL so the mark can be "
            "re-checked by a later run"
        )


def record_mark(
    ticker: str,
    close: float,
    observed_as_of: str,
    source_name: str,
    source_url: str,
    currency: str = "THB",
    note: Optional[str] = None,
    retrieved_at: Optional[str] = None,
) -> ObservedMark:
    """
    Record one agent-observed price.

    Behaviour when a mark for this ticker already exists:

    * **Newer session** — replaces it. The prior mark is kept in ``sources`` so
      the succession is auditable.
    * **Same session, price agrees within tolerance** — corroboration count
      rises; this is the only way ``is_corroborated`` becomes True.
    * **Same session, price disagrees** — recorded in ``conflicts`` and the
      stored close is left ALONE. Two sources disagreeing about one session is
      information, and silently taking the newer one destroys it. Resolution is
      a judgement call for the run, not for this function.
    * **Older session** — recorded in ``sources`` for history but does not
      replace a newer mark.

    Raises ``MarkRejected`` if provenance is incomplete.
    """
    _validate(ticker, close, observed_as_of, source_name, source_url)
    ticker = ticker.upper()
    close = float(close)
    now = retrieved_at or datetime.now(timezone.utc).isoformat()
    attribution = {
        "source_name": source_name,
        "source_url": source_url,
        "close": close,
        "observed_as_of": observed_as_of,
        "retrieved_at": now,
    }

    store = _load_store()
    existing_raw = store["marks"].get(ticker)

    if existing_raw is None:
        mark = ObservedMark(
            ticker=ticker,
            close=close,
            currency=currency,
            observed_as_of=observed_as_of,
            retrieved_at=now,
            source_name=source_name,
            source_url=source_url,
            corroboration=1,
            sources=[attribution],
            note=note,
        )
        store["marks"][ticker] = mark.to_dict()
        _save_store(store)
        return mark

    existing = ObservedMark(**existing_raw)

    if observed_as_of > existing.observed_as_of:
        superseded = {**attribution, "supersedes": existing.observed_as_of}
        mark = ObservedMark(
            ticker=ticker,
            close=close,
            currency=currency,
            observed_as_of=observed_as_of,
            retrieved_at=now,
            source_name=source_name,
            source_url=source_url,
            corroboration=1,
            sources=(existing.sources + [superseded])[-12:],
            conflicts=[],           # conflicts are per-session; a new session clears them
            note=note or existing.note,
        )
    elif observed_as_of == existing.observed_as_of:
        divergence_pct = abs(close - existing.close) / existing.close * 100.0
        mark = existing
        mark.sources = (existing.sources + [attribution])[-12:]
        if divergence_pct <= _CORROBORATION_TOLERANCE_PCT:
            if source_name not in {s.get("source_name") for s in existing.sources}:
                mark.corroboration = existing.corroboration + 1
        else:
            mark.conflicts.append({**attribution, "divergence_pct": round(divergence_pct, 3)})
            logger.warning(
                "%s: %s quotes %.4f for %s but stored mark is %.4f (%.2f%% apart). "
                "Conflict RECORDED; stored close unchanged.",
                ticker, source_name, close, observed_as_of, existing.close, divergence_pct,
            )
        if note:
            mark.note = note
    else:
        mark = existing
        mark.sources = (existing.sources + [{**attribution, "stale_relative_to":
                                             existing.observed_as_of}])[-12:]
        logger.info(
            "%s: %s quote for %s is older than stored mark for %s — kept as history only.",
            ticker, source_name, observed_as_of, existing.observed_as_of,
        )

    store["marks"][ticker] = mark.to_dict()
    _save_store(store)
    return mark


# --------------------------------------------------------------------------
# Read path
# --------------------------------------------------------------------------

def get_mark(
    ticker: str,
    max_age_days: int = _DEFAULT_MAX_AGE_DAYS,
    reference: Optional[date] = None,
) -> Optional[ObservedMark]:
    """
    Most recent observed mark for ``ticker``, or None.

    Rule 5: a mark older than ``max_age_days`` is REFUSED rather than returned
    with a caveat, because the whole point of this store is that a stale mark
    and a fresh one must not be interchangeable at the call site.
    """
    raw = _load_store()["marks"].get(ticker.upper())
    if raw is None:
        return None
    try:
        mark = ObservedMark(**raw)
    except TypeError as exc:
        logger.error("Malformed mark for %s (%s) — treated as ABSENT.", ticker, exc)
        return None
    age = mark.age_days(reference)
    if age is None:
        logger.error("%s: mark has no parseable session date — treated as ABSENT.", ticker)
        return None
    if age > max_age_days:
        logger.warning(
            "%s: observed mark is %d days old (session %s, limit %d) — REFUSED.",
            ticker, age, mark.observed_as_of, max_age_days,
        )
        return None
    return mark


def portfolio_marks(
    shares: dict[str, int],
    max_age_days: int = _DEFAULT_MAX_AGE_DAYS,
    reference: Optional[date] = None,
) -> dict[str, Any]:
    """
    Value a book from observed marks, refusing to produce a misleading total.

    ``total_value`` is ``None`` if ANY leg is unpriced. A partial sum reads like
    a real total while describing a smaller portfolio than the owner holds, and
    every weight derived from it is then overstated — the exact failure logged
    in ``market_data.py`` on 2026-08-08.

    ``mark_date_mixed`` is the field to look at before quoting a total: legs
    marked on different sessions do not add up to a portfolio value on any one
    date, and the difference is not always immaterial.
    """
    positions: dict[str, Any] = {}
    unpriced: list[str] = []
    mark_dates: set[str] = set()
    total = 0.0

    for ticker, quantity in shares.items():
        mark = get_mark(ticker, max_age_days=max_age_days, reference=reference)
        if mark is None:
            unpriced.append(ticker)
            positions[ticker] = {
                "quantity": quantity,
                "close": None,
                "value": None,
                "observed_as_of": None,
                "reason": "no observed mark within age limit",
            }
            continue
        value = mark.close * quantity
        total += value
        mark_dates.add(mark.observed_as_of)
        positions[ticker] = {
            "quantity": quantity,
            "close": mark.close,
            "value": round(value, 2),
            "observed_as_of": mark.observed_as_of,
            "source_name": mark.source_name,
            "source_url": mark.source_url,
            "corroboration": mark.corroboration,
            "is_corroborated": mark.is_corroborated,
        }

    complete = not unpriced
    dates = sorted(mark_dates)
    result: dict[str, Any] = {
        "positions": positions,
        "unpriced": unpriced,
        "valuation_complete": complete,
        "total_value": round(total, 2) if complete else None,
        "mark_dates": dates,
        "mark_date_mixed": len(dates) > 1,
        "as_of_range": [dates[0], dates[-1]] if dates else None,
        "weights_pct": None,
        "caveat": None,
    }

    if complete and total > 0:
        result["weights_pct"] = {
            ticker: round(entry["value"] / total * 100.0, 4)
            for ticker, entry in positions.items()
        }
    if not complete:
        result["caveat"] = (
            f"total_value is None because {len(unpriced)} leg(s) are unpriced "
            f"({', '.join(unpriced)}). A partial sum would understate the book."
        )
    elif result["mark_date_mixed"]:
        result["caveat"] = (
            f"Legs are marked on different sessions ({dates[0]} .. {dates[-1]}). "
            "This total is not a portfolio value on any single date; the "
            "older legs have not been observed since their session."
        )
    return result


def uncorroborated(max_age_days: int = _DEFAULT_MAX_AGE_DAYS) -> list[str]:
    """Tickers whose current mark rests on a single source. Worth a second look."""
    out = []
    for ticker in _load_store()["marks"]:
        mark = get_mark(ticker, max_age_days=max_age_days)
        if mark is not None and not mark.is_corroborated:
            out.append(ticker)
    return sorted(out)


def open_conflicts() -> list[dict[str, Any]]:
    """Every recorded source disagreement, so none can go quietly unresolved."""
    out = []
    for ticker, raw in _load_store()["marks"].items():
        for conflict in raw.get("conflicts", []):
            out.append({"ticker": ticker, "stored_close": raw.get("close"), **conflict})
    return out


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    report = {
        "store": store_status(),
        "uncorroborated": uncorroborated(),
        "open_conflicts": open_conflicts(),
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["store"]["store_exists"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
