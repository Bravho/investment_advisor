"""
set_quote_parser.py — status-gated interpretation of set.or.th stock quote pages.

WHY THIS MODULE EXISTS (added by nightly agent 2026-08-14)
---------------------------------------------------------
The SET quote page (https://www.set.or.th/en/market/product/stock/quote/<SYM>/price)
is server-rendered, which makes it the best available FIRST-PARTY price source for
Thai equities. But the page always renders the same shape whether the market is
open, closed, or the response came from a stale edge cache. The `Last` field is
therefore NOT a closing price. It is "the last print as of `Last Update`, in the
state described by `Status`".

On 2026-08-14 the nightly run retrieved all three holdings within ~40 seconds:

    BAFS   Status: Closed  Last Update: 14 Aug 2026 02:34:56   Last 11.40
    PTTEP  Status: Closed  Last Update: 14 Aug 2026 02:35:26   Last 150.50
    SCB    Status: Open1   Last Update: 13 Aug 2026 09:59:37   Last 152.00

The SCB response was a cached snapshot taken ~10 minutes into the 13 Aug morning
session. Its `Last` of 152.00 is an INTRADAY print, not the 13 Aug close. Read
naively it would have been booked as a close — and it would have looked entirely
plausible, because it happened to equal the genuine 11 Aug close of 152.00. A
wrong number that agrees with the previous right number is the hardest kind to
catch downstream, so it has to be caught here, at parse time.

DESIGN RULE
-----------
`classify()` never guesses. It returns a QuoteSnapshot whose `kind` is one of
CLOSE / INTRADAY / PREOPEN / UNKNOWN, and `close` is populated *only* for CLOSE.
Callers that want a closing price must ask for `.close` and handle None. There is
deliberately no `price` convenience property: every caller is forced to say which
semantics it wants. Degrading an intraday print to "close enough" is the bug this
module exists to prevent, so it is not offered as an option.

Status vocabulary observed on set.or.th:
    "Open1"   first trading session (10:00-12:30 ICT)
    "Open2"   second trading session (14:30-16:30 ICT)
    "Closed"  outside sessions, or a non-trading day
    "Pre-Open"/"Intermission"/"Off-hour" also occur; treated conservatively.

Note that "Closed" alone is NOT sufficient to identify WHICH session closed. That
requires the `Last Update` timestamp plus the SET trading calendar, which is why
`session_date_for()` delegates to data_collector.set_holidays.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, date, time, timedelta, timezone
from typing import Any, Optional

# Bangkok is UTC+7 year-round (no DST).
ICT = timezone(timedelta(hours=7))

# SET equity trading sessions, Indochina Time.
MORNING_OPEN = time(10, 0)
MORNING_CLOSE = time(12, 30)
AFTERNOON_OPEN = time(14, 30)
AFTERNOON_CLOSE = time(16, 30)

# Quote kinds.
KIND_CLOSE = "CLOSE"
KIND_INTRADAY = "INTRADAY"
KIND_PREOPEN = "PREOPEN"
KIND_UNKNOWN = "UNKNOWN"

_OPEN_STATUSES = {"open1", "open2", "open", "open 1", "open 2"}
_CLOSED_STATUSES = {"closed", "close"}
_PREOPEN_STATUSES = {"pre-open", "preopen", "pre open", "intermission", "off-hour", "offhour"}

# "14 Aug 2026 02:35:26"
_TS_RE = re.compile(
    r"(?P<day>\d{1,2})\s+(?P<mon>[A-Za-z]{3})\s+(?P<year>\d{4})\s+"
    r"(?P<hh>\d{2}):(?P<mm>\d{2}):(?P<ss>\d{2})"
)
_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


class QuoteIntegrityError(ValueError):
    """Raised when a snapshot's own fields contradict each other."""


@dataclass
class QuoteSnapshot:
    """One retrieval of a SET quote page, with its provenance and semantics."""

    ticker: str
    kind: str
    status_raw: str
    last: Optional[float] = None
    prior: Optional[float] = None
    open_: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    volume_shares: Optional[int] = None
    value_thousand_baht: Optional[float] = None
    average_price: Optional[float] = None
    floor: Optional[float] = None
    ceiling: Optional[float] = None
    last_update_ict: Optional[str] = None       # ISO-8601, +07:00
    retrieved_at_utc: Optional[str] = None      # ISO-8601, +00:00
    session_date: Optional[str] = None          # YYYY-MM-DD, the session `last` belongs to
    source_url: Optional[str] = None
    notes: list[str] = field(default_factory=list)

    @property
    def close(self) -> Optional[float]:
        """The closing price, or None if this snapshot is not a close.

        Intentionally strict. If you want "whatever the last print was",
        read `.last` and accept that you are reading an intraday number.
        """
        return self.last if self.kind == KIND_CLOSE else None

    @property
    def is_close(self) -> bool:
        return self.kind == KIND_CLOSE

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["close"] = self.close
        return d


def parse_last_update(text: str) -> Optional[datetime]:
    """Parse SET's 'Last Update' stamp. Returns an ICT-aware datetime."""
    if not text:
        return None
    m = _TS_RE.search(text)
    if not m:
        return None
    mon = _MONTHS.get(m.group("mon").lower())
    if mon is None:
        return None
    return datetime(
        int(m.group("year")), mon, int(m.group("day")),
        int(m.group("hh")), int(m.group("mm")), int(m.group("ss")),
        tzinfo=ICT,
    )


def _normalise_status(status_raw: str) -> str:
    s = (status_raw or "").strip().lower()
    if s in _OPEN_STATUSES:
        return "open"
    if s in _CLOSED_STATUSES:
        return "closed"
    if s in _PREOPEN_STATUSES:
        return "preopen"
    return "unknown"


def session_date_for(stamp: datetime) -> Optional[str]:
    """Which SET session does a 'Closed' stamp describe?

    A stamp after 16:30 ICT describes that day's session. A stamp before
    10:00 ICT (e.g. 02:35, when this agent runs) describes the PREVIOUS
    trading day. Getting this backwards is how an agent that runs at 02:30
    books yesterday's close under today's date.

    Delegates to the SET holiday calendar so long weekends resolve correctly.
    Returns None when the calendar cannot answer rather than guessing.
    """
    if stamp is None:
        return None
    try:
        from data_collector.set_holidays import previous_trading_day, is_trading_day
    except Exception:  # pragma: no cover - calendar optional, absence must be visible
        return None

    d = stamp.date()
    try:
        if stamp.time() >= AFTERNOON_CLOSE:
            # After today's close: this day, if it was a session at all.
            return d.isoformat() if is_trading_day(d) else previous_trading_day(d).isoformat()
        # Before the close (including the small hours): the prior session.
        return previous_trading_day(d).isoformat()
    except Exception:
        return None


def classify(
    ticker: str,
    status_raw: str,
    last_update_raw: str,
    *,
    last: Optional[float] = None,
    prior: Optional[float] = None,
    open_: Optional[float] = None,
    high: Optional[float] = None,
    low: Optional[float] = None,
    volume_shares: Optional[int] = None,
    value_thousand_baht: Optional[float] = None,
    average_price: Optional[float] = None,
    floor: Optional[float] = None,
    ceiling: Optional[float] = None,
    source_url: Optional[str] = None,
    now_utc: Optional[datetime] = None,
    max_staleness_hours: float = 24.0,
) -> QuoteSnapshot:
    """Turn raw SET quote fields into a QuoteSnapshot with explicit semantics.

    `max_staleness_hours` guards against edge-cached responses: a "Closed"
    status whose Last Update is older than this is downgraded to UNKNOWN,
    because we can no longer tell which session it describes with confidence.
    """
    now_utc = now_utc or datetime.now(timezone.utc)
    stamp = parse_last_update(last_update_raw)
    status = _normalise_status(status_raw)
    notes: list[str] = []

    if stamp is None:
        kind = KIND_UNKNOWN
        notes.append("Last Update stamp unparseable; cannot date this print.")
    elif status == "open":
        kind = KIND_INTRADAY
        notes.append(
            f"Status {status_raw!r} means the session was live at "
            f"{stamp.isoformat()}; `last` is an intraday print, NOT a close."
        )
    elif status == "preopen":
        kind = KIND_PREOPEN
        notes.append(f"Status {status_raw!r}: pre-open/intermission, no valid last print.")
    elif status == "closed":
        age_h = (now_utc - stamp.astimezone(timezone.utc)).total_seconds() / 3600.0
        if age_h > max_staleness_hours:
            kind = KIND_UNKNOWN
            notes.append(
                f"Status Closed but stamp is {age_h:.1f}h old "
                f"(limit {max_staleness_hours}h) — likely a cached response; "
                f"session cannot be attributed."
            )
        elif age_h < -0.25:
            kind = KIND_UNKNOWN
            notes.append(f"Stamp is {-age_h:.1f}h in the future; clock or timezone fault.")
        else:
            kind = KIND_CLOSE
    else:
        kind = KIND_UNKNOWN
        notes.append(f"Unrecognised status {status_raw!r}; refusing to interpret.")

    snap = QuoteSnapshot(
        ticker=ticker,
        kind=kind,
        status_raw=status_raw,
        last=last,
        prior=prior,
        open_=open_,
        high=high,
        low=low,
        volume_shares=volume_shares,
        value_thousand_baht=value_thousand_baht,
        average_price=average_price,
        floor=floor,
        ceiling=ceiling,
        last_update_ict=stamp.isoformat() if stamp else None,
        retrieved_at_utc=now_utc.isoformat(),
        session_date=session_date_for(stamp) if kind == KIND_CLOSE else None,
        source_url=source_url,
        notes=notes,
    )
    snap.notes.extend(check_internal_consistency(snap))
    return snap


def check_internal_consistency(snap: QuoteSnapshot, tol: float = 0.01) -> list[str]:
    """Cross-check a snapshot's fields against each other.

    These are the checks that catch a mis-scrape, as opposed to a stale one:
    a `last` outside the day range, or a published average that disagrees with
    value/volume. Returns a list of human-readable findings (empty == clean).
    Raises only on impossibilities, never on mere disagreement.
    """
    out: list[str] = []

    if snap.high is not None and snap.low is not None and snap.high < snap.low:
        raise QuoteIntegrityError(f"{snap.ticker}: high {snap.high} < low {snap.low}")

    for label, v in (("last", snap.last), ("open", snap.open_)):
        if v is None or snap.high is None or snap.low is None:
            continue
        if not (snap.low - tol <= v <= snap.high + tol):
            out.append(f"{label} {v} outside day range {snap.low}-{snap.high}")

    if snap.value_thousand_baht and snap.volume_shares:
        implied = (snap.value_thousand_baht * 1000.0) / snap.volume_shares
        if snap.average_price is not None:
            if abs(implied - snap.average_price) > max(0.01, snap.average_price * 0.001):
                out.append(
                    f"value/volume implies {implied:.4f} but published average is "
                    f"{snap.average_price} — turnover and average disagree"
                )
            else:
                out.append(f"value/volume {implied:.4f} reconciles with average {snap.average_price}")
        if snap.high is not None and snap.low is not None:
            if not (snap.low - tol <= implied <= snap.high + tol):
                out.append(
                    f"implied average {implied:.4f} outside day range "
                    f"{snap.low}-{snap.high} — fields are not from one session"
                )

    # SET price bands are +/-30% of the prior close, rounded to tick.
    if snap.prior and snap.ceiling and snap.floor:
        if not (snap.floor < snap.prior < snap.ceiling):
            out.append(
                f"prior {snap.prior} not inside band {snap.floor}-{snap.ceiling}"
            )
    return out


def summarise(snaps: list[QuoteSnapshot]) -> dict[str, Any]:
    """Fleet view over a batch of retrievals — what is safe to book tonight."""
    usable = [s for s in snaps if s.is_close]
    return {
        "retrieved": len(snaps),
        "usable_closes": len(usable),
        "rejected": [
            {"ticker": s.ticker, "kind": s.kind, "status": s.status_raw,
             "last_update_ict": s.last_update_ict, "notes": s.notes}
            for s in snaps if not s.is_close
        ],
        "session_dates": sorted({s.session_date for s in usable if s.session_date}),
        "same_session": len({s.session_date for s in usable if s.session_date}) <= 1,
    }
