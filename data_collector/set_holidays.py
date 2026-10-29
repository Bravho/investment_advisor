"""
SET (Stock Exchange of Thailand) non-trading-day calendar.

Added by nightly agent 2026-08-13.

WHY THIS EXISTS
---------------
``set_official.previous_trading_day()`` shipped on 2026-08-12 with a limitation
its own docstring stated out loud: it skipped weekends and nothing else. The
docstring even named the day that would break it --- **2026-08-12, HM Queen
Sirikit the Queen Mother's Birthday** --- and said "there is very likely no
2026-08-12 session at all."

Tonight that was confirmed from two independent sources (see ``PROVENANCE``).
There was no 12 August 2026 session. The exchange's own EOD publish stamp on
all three of Tho's holdings still reads ``12 Aug 2026 03:20:09`` at 02:30 ICT
on 13 August --- it never advanced, because there was no session to publish.

The failure this prevents is quiet and one-directional. Ask the old function
for the session before Thursday 13 August and it answers Wednesday 12 August:
a day the exchange was shut. Any mark, any dividend cum/ex boundary, any
"previous close" derived from that answer is **off by one session**, and
nothing in the data looks wrong afterwards. That is the same class of defect
as the February-price and Buddhist-era traps already logged in DEVLOG.md: a
number that is wrong while looking entirely ordinary.

A holiday calendar is a hardcoded table and hardcoded tables rot. The design
decisions below all follow from taking that seriously.

DESIGN
------
* **The table is dated and sourced, not anonymous.** Every year carries the URL
  it came from and the date it was read. ``coverage()`` reports the span, and
  every lookup outside that span **raises** rather than guessing. A holiday
  calendar that silently degrades to weekends-only outside its range is worse
  than no calendar, because callers stop checking.

* **Thai holidays cannot be extrapolated.** Makha Bucha, Visakha Bucha and
  Asarnha Bucha are lunar and move ~11 days a year. Substitution days appear
  when a fixed holiday lands on a weekend. The Cabinet adds special holidays
  with a few months' notice (2026 has two: 2 January and 16 October). No rule
  generates this list; it must be read off the exchange each year. Hence
  ``YearNotCoveredError``.

* **Bank holiday != exchange holiday.** SET occasionally trades on days the
  banks are shut; SCBAM's calendar annotates those "(exch Open)". None of the
  2026 Thai entries carry that annotation, so all 18 are treated as closures,
  but the distinction is recorded in ``NOTES`` so a future reader knows the
  question was asked rather than overlooked.

* **Nothing here fetches.** Same split as ``set_official``: the agent supplies
  the bytes, the module supplies the interpretation, so the interpretation is
  testable inside the agent sandbox even though the fetch is not.

USAGE
-----
    >>> from datetime import date
    >>> is_trading_day(date(2026, 8, 12))
    False
    >>> previous_trading_day(date(2026, 8, 13)).isoformat()
    '2026-08-11'
    >>> sessions_between(date(2026, 8, 11), date(2026, 8, 14))
    2
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, Iterable, List, Optional, Tuple

__all__ = [
    "YearNotCoveredError",
    "HOLIDAYS",
    "PROVENANCE",
    "NOTES",
    "coverage",
    "is_holiday",
    "is_trading_day",
    "holiday_name",
    "previous_trading_day",
    "next_trading_day",
    "sessions_between",
    "trading_days_in_range",
    "assert_covered",
]


class YearNotCoveredError(LookupError):
    """
    Raised when a date falls outside the years this table was read for.

    Deliberately an error and not a warning. The whole point of the module is
    that a wrong session date is invisible downstream; degrading quietly to
    weekends-only would reintroduce exactly the bug it was written to remove.
    """


# --------------------------------------------------------------------------- #
# The table
# --------------------------------------------------------------------------- #
# Thailand-only entries. Singapore and United States rows on the source page
# are deliberately NOT included --- this calendar answers "was the SET open",
# and nothing else. Cross-market holidays belong in a separate table keyed by
# venue, which is queued work.

HOLIDAYS: Dict[int, Dict[str, str]] = {
    2025: {
        "2025-01-01": "New Year's Day",
        "2025-02-12": "Makha Bucha Day",
        "2025-04-07": "Substitution for Chakri Memorial Day",
        "2025-04-14": "Songkran Festival",
        "2025-04-15": "Substitution for Songkran Festival",
        "2025-05-01": "National Labour Day",
        "2025-05-05": "Substitution for Coronation Day",
        "2025-05-12": "Substitution for Visakha Bucha Day",
        "2025-06-02": "Special holiday",
        "2025-06-03": "HM Queen Suthida's Birthday",
        "2025-07-10": "Asarnha Bucha Day",
        "2025-07-28": "HM King Maha Vajiralongkorn's Birthday",
        "2025-08-11": "Special holiday",
        "2025-08-12": "HM Queen Sirikit the Queen Mother's Birthday / Mother's Day",
        "2025-10-23": "Chulalongkorn Day",
        "2025-12-05": "HM King Bhumibol Adulyadej the Great's Birthday / Father's Day",
        "2025-12-10": "Constitution Day",
        "2025-12-31": "New Year's Eve",
        # 2025-10-13 is annotated "(exch Open)" on the source and is therefore
        # NOT a closure. Recorded here as a comment so the omission reads as a
        # decision rather than an oversight.
    },
    2026: {
        "2026-01-01": "New Year's Day",
        "2026-01-02": "Additional special holiday",
        "2026-03-03": "Makha Bucha Day",
        "2026-04-06": "Chakri Memorial Day",
        "2026-04-13": "Songkran Festival",
        "2026-04-14": "Songkran Festival",
        "2026-04-15": "Songkran Festival",
        "2026-05-01": "National Labour Day",
        "2026-05-04": "Coronation Day",
        "2026-06-01": "Substitution for Visakha Bucha Day",
        "2026-06-03": "HM Queen Suthida's Birthday",
        "2026-07-28": "HM King Maha Vajiralongkorn's Birthday",
        "2026-07-29": "Asarnha Bucha Day",
        "2026-08-12": "HM Queen Sirikit the Queen Mother's Birthday / Mother's Day",
        "2026-10-13": "HM King Bhumibol Adulyadej the Great Memorial Day",
        "2026-10-16": "Additional special holiday",
        "2026-10-23": "HM King Chulalongkorn the Great Memorial Day",
        "2026-12-07": "Substitution for HM King Bhumibol's Birthday / Father's Day",
        "2026-12-10": "Constitution Day",
        "2026-12-31": "New Year's Eve",
    },
}

PROVENANCE: Dict[int, Dict[str, str]] = {
    2025: {
        "source_name": "SCB Asset Management fund trading holiday calendar",
        "source_url": "https://www.scbam.com/en/fund/default/fund-information/scbgold",
        "retrieved": "2026-08-13",
        "confidence": "secondary",
    },
    2026: {
        "source_name": "SCB Asset Management fund trading holiday calendar",
        "source_url": "https://www.scbam.com/en/fund/default/fund-information/scbgold",
        "retrieved": "2026-08-13",
        "confidence": "secondary",
        "corroboration": (
            "2026-08-12 independently confirmed closed by (a) SET quote pages for "
            "BAFS, PTTEP and SCB, whose EOD publish stamp still read "
            "'12 Aug 2026 03:20:09' at 02:30 ICT on 13 Aug and therefore covered "
            "the 11 Aug session, and (b) contemporaneous press reporting that the "
            "Thai bourse was shut for Mother's Day."
        ),
    },
}

NOTES: Tuple[str, ...] = (
    "SECONDARY SOURCE. The table was transcribed from SCBAM's published fund "
    "trading holiday calendar, not from set.or.th/en/about/event-calendar/holiday, "
    "whose holiday table is rendered client-side and returned empty to the "
    "agent's retrieval tooling. SCBAM is a large regulated Thai asset manager "
    "and its Thailand column has always tracked the exchange, but it is one "
    "step removed from the issuer. Re-derive from SET directly when a renderer "
    "is available.",

    "BANK vs EXCHANGE. SET sometimes trades on days when Thai banks are closed; "
    "the source annotates such days '(exch Open)' and they are excluded from "
    "this table. No 2026 Thailand entry carries that annotation. 2025-10-13 does "
    "and is excluded accordingly.",

    "HALF DAYS ARE NOT MODELLED. This answers open/closed only. A shortened "
    "session is a trading day here.",

    "NO EXTRAPOLATION. Buddhist observances are lunar, substitution days depend "
    "on weekday placement, and Cabinet special holidays are announced ad hoc. "
    "Lookups outside the covered years raise YearNotCoveredError by design.",
)


# --------------------------------------------------------------------------- #
# Core predicates
# --------------------------------------------------------------------------- #

def coverage() -> Tuple[int, int]:
    """Return ``(first_year, last_year)`` covered by the table."""
    years = sorted(HOLIDAYS)
    return years[0], years[-1]


def assert_covered(day: date) -> None:
    """Raise :class:`YearNotCoveredError` unless ``day``'s year is in the table."""
    if day.year not in HOLIDAYS:
        first, last = coverage()
        raise YearNotCoveredError(
            f"SET holiday table covers {first}-{last}; {day.isoformat()} is outside "
            f"it. Thai holidays cannot be extrapolated (lunar dates, substitution "
            f"days, ad-hoc Cabinet holidays) -- add the year from the exchange "
            f"calendar rather than guessing."
        )


def is_holiday(day: date) -> bool:
    """True if ``day`` is a listed SET closure. Weekends are NOT holidays here."""
    assert_covered(day)
    return day.isoformat() in HOLIDAYS[day.year]


def holiday_name(day: date) -> Optional[str]:
    """Name of the closure on ``day``, or ``None`` if it is not a listed holiday."""
    assert_covered(day)
    return HOLIDAYS[day.year].get(day.isoformat())


def is_weekend(day: date) -> bool:
    """True on Saturday or Sunday. Does not consult the table, so never raises."""
    return day.weekday() >= 5


def is_trading_day(day: date) -> bool:
    """True if the SET held a session on ``day`` (not a weekend, not a holiday)."""
    if is_weekend(day):
        return False
    return not is_holiday(day)


# --------------------------------------------------------------------------- #
# Navigation
# --------------------------------------------------------------------------- #

_MAX_GAP_DAYS = 14  # Songkran plus weekends is the longest real run; 14 is slack.


def previous_trading_day(day: date) -> date:
    """
    The last SET session strictly before ``day``.

    Holiday- and weekend-aware. This is the drop-in replacement for
    ``set_official.previous_trading_day``, which handled weekends only.

        >>> previous_trading_day(date(2026, 8, 13)).isoformat()   # Thu after the holiday
        '2026-08-11'
        >>> previous_trading_day(date(2026, 8, 12)).isoformat()   # from the holiday itself
        '2026-08-11'
    """
    d = day - timedelta(days=1)
    for _ in range(_MAX_GAP_DAYS):
        if is_trading_day(d):
            return d
        d -= timedelta(days=1)
    raise RuntimeError(
        f"No SET trading day found in the {_MAX_GAP_DAYS} days before "
        f"{day.isoformat()} -- the holiday table is probably malformed."
    )


def next_trading_day(day: date) -> date:
    """The first SET session strictly after ``day``."""
    d = day + timedelta(days=1)
    for _ in range(_MAX_GAP_DAYS):
        if is_trading_day(d):
            return d
        d += timedelta(days=1)
    raise RuntimeError(
        f"No SET trading day found in the {_MAX_GAP_DAYS} days after "
        f"{day.isoformat()} -- the holiday table is probably malformed."
    )


def trading_days_in_range(start: date, end: date) -> List[date]:
    """
    Every SET session in the half-open interval ``[start, end)``.

    Half-open on purpose: the natural question is "how many sessions have passed
    since my mark", and the mark's own session should not be counted twice.
    """
    if end < start:
        raise ValueError("end must not precede start")
    out: List[date] = []
    d = start
    while d < end:
        if is_trading_day(d):
            out.append(d)
        d += timedelta(days=1)
    return out


def sessions_between(start: date, end: date) -> int:
    """
    Number of SET sessions in ``[start, end)`` --- i.e. the staleness, in
    sessions, of a mark dated ``start`` when read on ``end``.

    Counting in sessions rather than calendar days is the point. A mark taken
    on Tuesday 11 August and read on Thursday 13 August is two calendar days
    old but only **one session** old, because Wednesday was Mother's Day. Age
    limits expressed in calendar days retire good marks over long weekends and
    keep bad ones over short ones.
    """
    return len(trading_days_in_range(start, end))


def describe(day: date) -> str:
    """One-line human-readable status for ``day``. Useful in logs and briefs."""
    if is_weekend(day):
        return f"{day.isoformat()} ({day.strftime('%a')}): CLOSED - weekend"
    name = holiday_name(day)
    if name:
        return f"{day.isoformat()} ({day.strftime('%a')}): CLOSED - {name}"
    return f"{day.isoformat()} ({day.strftime('%a')}): trading session"
