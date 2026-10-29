"""
price_history.py — the session-keyed price history store.

WHY THIS MODULE EXISTS (added by nightly agent 2026-08-14)
---------------------------------------------------------
Every night this agent has retrieved prices, written them into a dated snapshot,
and thrown away the ability to compare them. `data/snapshots/YYYY-MM-DD.json` is
a record of what was believed on a date; it is not a time series, because the
mark inside it may be days older than the filename and the schema has drifted.

The consequence has been concrete and repeated: the PTTEP/BAFS "accidental hedge"
thesis — that PTTEP gains when crude rallies while BAFS (a jet-fuel logistics
operator) loses — has sat at one contrary observation and zero confirming ones for
four consecutive runs, because measuring it needs a *sample* and no sample exists.
The DEVLOG has named this the blocking dependency three nights running.

WHAT THIS STORE PROMISES
------------------------
1.  One row per (ticker, session_date). Sessions, not calendar days — a Thai long
    weekend must not silently become four observations of the same close.
2.  Append-only with explicit supersede. Re-observing a session either agrees
    (confidence rises) or conflicts (both are kept, the conflict is recorded, and
    nothing is silently overwritten).
3.  Provenance travels with the price: source, retrieval time, and whether the
    print was a genuine close (see data_collector.set_quote_parser).
4.  Statistics refuse to run on samples too small to mean anything. `beta()` with
    n=3 returns a refusal, not a number. A beta computed from four points is not
    a weak estimate — it is noise wearing a decimal point, and the entire reason
    the hedge thesis is unresolved is that nobody has been willing to say so.

Deliberately NOT here: any network call. This module stores and computes only, so
that it can be unit-tested and so a collector outage degrades coverage rather than
corrupting history.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, asdict, field
from datetime import datetime, date, timezone
from pathlib import Path
from typing import Any, Optional, Iterable

PROJECT_DIR = Path(__file__).resolve().parent.parent
STORE_PATH = PROJECT_DIR / "data" / "price_history" / "prices.json"

SCHEMA_VERSION = 2

# Minimum paired observations before a regression statistic is reported at all.
MIN_SAMPLE_FOR_BETA = 20
# Below this, correlation is reported but flagged as indicative only.
MIN_SAMPLE_FOR_CORRELATION = 10


class InsufficientSample(Exception):
    """Raised when a statistic is requested on a sample too small to support it."""


@dataclass
class PriceBar:
    """One session's price record for one ticker."""

    ticker: str
    session_date: str                    # YYYY-MM-DD, the SESSION, not the retrieval day
    close: float
    currency: str = "THB"
    open_: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    volume_shares: Optional[int] = None
    value_thousand: Optional[float] = None
    average_price: Optional[float] = None
    is_confirmed_close: bool = False     # from set_quote_parser: Status was 'Closed'
    source_name: Optional[str] = None
    source_url: Optional[str] = None
    retrieved_at: Optional[str] = None
    superseded: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _empty_store() -> dict[str, Any]:
    return {
        "_meta": {
            "schema_version": SCHEMA_VERSION,
            "created": datetime.now(timezone.utc).isoformat(),
            "last_written": None,
            "written_by": None,
        },
        "series": {},      # ticker -> {session_date -> bar dict}
        "conflicts": [],   # append-only log of disagreements
    }


def load_store(path: Path | str = STORE_PATH) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return _empty_store()
    try:
        with open(p, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError):
        # A corrupt store must be visible, not silently replaced.
        raise
    data.setdefault("series", {})
    data.setdefault("conflicts", [])
    data.setdefault("_meta", {})
    return data


def save_store(store: dict[str, Any], path: Path | str = STORE_PATH,
               written_by: str = "price_history") -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    store.setdefault("_meta", {})
    store["_meta"]["schema_version"] = SCHEMA_VERSION
    store["_meta"]["last_written"] = datetime.now(timezone.utc).isoformat()
    store["_meta"]["written_by"] = written_by
    tmp = p.with_suffix(p.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(store, fh, indent=1, ensure_ascii=False)
    os.replace(tmp, p)   # atomic; a killed run cannot leave a half-written history
    return p


def record_bar(bar: PriceBar, store: Optional[dict[str, Any]] = None,
               path: Path | str = STORE_PATH, save: bool = True) -> dict[str, Any]:
    """Insert or reconcile one session bar. Never silently overwrites.

    Returns {'action': 'inserted'|'confirmed'|'conflict'|'superseded', ...}.
    """
    store = store if store is not None else load_store(path)
    series = store["series"].setdefault(bar.ticker, {})
    existing = series.get(bar.session_date)

    result: dict[str, Any]
    if existing is None:
        series[bar.session_date] = bar.to_dict()
        result = {"action": "inserted", "ticker": bar.ticker,
                  "session_date": bar.session_date, "close": bar.close}
    elif abs(float(existing["close"]) - float(bar.close)) < 1e-9:
        # Same number from a second look. Corroboration only counts if the
        # SOURCE differs; a repeat fetch of one publisher is not independent.
        independent = (existing.get("source_name") != bar.source_name)
        existing.setdefault("notes", []).append(
            f"re-observed {bar.retrieved_at} via {bar.source_name}: agrees"
            + ("" if independent else " (same source — not independent corroboration)")
        )
        if bar.is_confirmed_close and not existing.get("is_confirmed_close"):
            existing["is_confirmed_close"] = True
            existing["notes"].append("upgraded to confirmed close")
        result = {"action": "confirmed", "ticker": bar.ticker,
                  "session_date": bar.session_date, "close": bar.close,
                  "independent": independent}
    else:
        # Genuine disagreement. Prefer a confirmed close over an unconfirmed one;
        # otherwise keep what we had and log loudly. Never average them.
        conflict = {
            "ticker": bar.ticker,
            "session_date": bar.session_date,
            "held": {"close": existing["close"], "source": existing.get("source_name"),
                     "confirmed": existing.get("is_confirmed_close")},
            "incoming": {"close": bar.close, "source": bar.source_name,
                         "confirmed": bar.is_confirmed_close},
            "logged_at": datetime.now(timezone.utc).isoformat(),
        }
        if bar.is_confirmed_close and not existing.get("is_confirmed_close"):
            new = bar.to_dict()
            new["superseded"] = list(existing.get("superseded", [])) + [existing]
            new["notes"] = list(new.get("notes", [])) + [
                "superseded an unconfirmed mark; both retained"
            ]
            series[bar.session_date] = new
            conflict["resolution"] = "incoming adopted (confirmed close beats unconfirmed)"
            result = {"action": "superseded", **conflict}
        else:
            existing.setdefault("superseded", []).append(bar.to_dict())
            conflict["resolution"] = "held mark retained; incoming stored as alternate"
            result = {"action": "conflict", **conflict}
        store["conflicts"].append(conflict)

    if save:
        save_store(store, path, written_by="price_history.record_bar")
    return result


def get_series(ticker: str, store: Optional[dict[str, Any]] = None,
               path: Path | str = STORE_PATH) -> list[dict[str, Any]]:
    """All bars for a ticker, oldest first."""
    store = store if store is not None else load_store(path)
    bars = store["series"].get(ticker, {})
    return [bars[k] for k in sorted(bars)]


def closes(ticker: str, store: Optional[dict[str, Any]] = None,
           path: Path | str = STORE_PATH,
           confirmed_only: bool = False) -> dict[str, float]:
    """{session_date: close} for a ticker."""
    out: dict[str, float] = {}
    for bar in get_series(ticker, store, path):
        if confirmed_only and not bar.get("is_confirmed_close"):
            continue
        out[bar["session_date"]] = float(bar["close"])
    return out


def returns(ticker: str, store: Optional[dict[str, Any]] = None,
            path: Path | str = STORE_PATH,
            confirmed_only: bool = False,
            log_returns: bool = False,
            max_gap_sessions: int = 1) -> dict[str, float]:
    """Session-over-session returns keyed by the LATER session date.

    `max_gap_sessions` is enforced against the stored series, not the calendar:
    if there is a hole in the history, the return spanning that hole is dropped
    rather than reported as a one-session move. A gap-spanning return is the
    single easiest way to manufacture a fake outlier in a beta.
    """
    c = closes(ticker, store, path, confirmed_only=confirmed_only)
    dates = sorted(c)
    out: dict[str, float] = {}
    for i in range(1, len(dates)):
        prev_d, cur_d = dates[i - 1], dates[i]
        # Distance measured in stored sessions is always 1 here; the real test is
        # whether the calendar gap is plausibly that many sessions.
        gap_days = (date.fromisoformat(cur_d) - date.fromisoformat(prev_d)).days
        if gap_days > max_gap_sessions * 5:   # generous: covers holidays/long weekends
            continue
        p0, p1 = c[prev_d], c[cur_d]
        if p0 <= 0 or p1 <= 0:
            continue
        out[cur_d] = math.log(p1 / p0) if log_returns else (p1 / p0 - 1.0)
    return out


def align(series_a: dict[str, float], series_b: dict[str, float]) -> tuple[list[str], list[float], list[float]]:
    """Inner-join two date->value maps on common dates."""
    common = sorted(set(series_a) & set(series_b))
    return common, [series_a[d] for d in common], [series_b[d] for d in common]


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs)


def correlation(xs: list[float], ys: list[float]) -> Optional[float]:
    n = len(xs)
    if n < 2:
        return None
    mx, my = _mean(xs), _mean(ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / math.sqrt(sxx * syy)


def beta(ticker: str, benchmark: str,
         store: Optional[dict[str, Any]] = None,
         path: Path | str = STORE_PATH,
         min_sample: int = MIN_SAMPLE_FOR_BETA) -> dict[str, Any]:
    """OLS beta of `ticker` returns on `benchmark` returns.

    Returns a dict that ALWAYS carries `n` and `sufficient`. When the sample is
    below `min_sample`, `beta` is None and `refusal_reason` explains why — the
    caller gets an honest "not yet", never a number it might quote.
    """
    store = store if store is not None else load_store(path)
    ra = returns(ticker, store, path)
    rb = returns(benchmark, store, path)
    dates, xs_t, xs_b = align(ra, rb)
    n = len(dates)

    base: dict[str, Any] = {
        "ticker": ticker,
        "benchmark": benchmark,
        "n": n,
        "first_session": dates[0] if dates else None,
        "last_session": dates[-1] if dates else None,
        "min_sample_required": min_sample,
        "sufficient": n >= min_sample,
        "beta": None,
        "correlation": None,
        "refusal_reason": None,
    }

    if n < MIN_SAMPLE_FOR_CORRELATION:
        base["refusal_reason"] = (
            f"only {n} paired sessions; need >= {MIN_SAMPLE_FOR_CORRELATION} for even an "
            f"indicative correlation and >= {min_sample} for a beta. "
            f"No statistic is reported. This is the sample problem, not a modelling problem."
        )
        return base

    r = correlation(xs_b, xs_t)
    base["correlation"] = r
    base["correlation_is_indicative_only"] = n < min_sample

    if n < min_sample:
        base["refusal_reason"] = (
            f"{n} paired sessions is below the {min_sample} required for a beta. "
            f"Correlation is shown as a directional hint only and must not be "
            f"quoted as a hedge ratio."
        )
        return base

    mb = _mean(xs_b)
    sbb = sum((b - mb) ** 2 for b in xs_b)
    if sbb <= 0:
        base["refusal_reason"] = "benchmark returns have zero variance over the window"
        return base
    mt = _mean(xs_t)
    base["beta"] = sum((b - mb) * (t - mt) for b, t in zip(xs_b, xs_t)) / sbb
    return base


def coverage(store: Optional[dict[str, Any]] = None,
             path: Path | str = STORE_PATH) -> dict[str, Any]:
    """How much history exists, and how far each ticker is from usable statistics."""
    store = store if store is not None else load_store(path)
    out: dict[str, Any] = {"tickers": {}, "conflicts": len(store.get("conflicts", []))}
    for ticker, bars in store["series"].items():
        dates = sorted(bars)
        confirmed = sum(1 for d in dates if bars[d].get("is_confirmed_close"))
        out["tickers"][ticker] = {
            "sessions": len(dates),
            "confirmed_closes": confirmed,
            "first": dates[0] if dates else None,
            "last": dates[-1] if dates else None,
            "sessions_until_beta": max(0, MIN_SAMPLE_FOR_BETA + 1 - len(dates)),
        }
    return out


def record_many(bars: Iterable[PriceBar], path: Path | str = STORE_PATH) -> list[dict[str, Any]]:
    """Batch insert — one load, one save, so a batch is atomic."""
    store = load_store(path)
    results = [record_bar(b, store=store, path=path, save=False) for b in bars]
    save_store(store, path, written_by="price_history.record_many")
    return results
