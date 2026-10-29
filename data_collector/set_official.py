"""
First-party SET (Stock Exchange of Thailand) quote-page reader.

Added by nightly agent 2026-08-12.

WHY THIS EXISTS
---------------
Three problems converge here, and this module is the answer to all three.

1. **The nightly agent has no outbound network from Python.** Proven live on
   2026-08-11: every ``urlopen`` from inside the agent sandbox dies with
   ``Tunnel connection failed: 403 Forbidden``. The agent *can* retrieve pages
   with its own tooling; it simply cannot do so from a Python process. The
   consequence, learned expensively, is that **no Python module in this project
   can be the agent's fetcher.**

   So this module does not fetch. It **parses text the caller already has.**
   Retrieval and parsing are split on purpose: the agent supplies the bytes,
   this module supplies the interpretation, and the interpretation is therefore
   testable by the agent even though the fetch is not. On Tho's machine, where
   egress is open, ``fetch_and_parse()`` closes the loop.

2. **The project had no first-party price source.** Every mark until tonight
   came from a third-party vendor, and the vendors disagreed: BAFS has been
   quoted at 11.60, 9.95, 9.25, 8.45 and 8.40 by five different sites, several
   of them wearing dates that were not the dates the price was observed. On
   2026-08-12 ``www.set.or.th`` was found to be reachable by the agent's
   retrieval tooling. The exchange is the issuer of the number; it outranks
   every aggregator, and it settled BAFS.

3. **The same SET page serves at three different freshness levels, and the
   naive read is wrong at two of them.** This is the defect this module mostly
   exists to prevent, so it is worth stating precisely.

THE FRESHNESS TRAP
------------------
A SET quote page carries ``Last``, ``Prior``, a ``Status`` and a
``Last Update`` wall-clock stamp. Observed on a single night, 2026-08-12:

    BAFS  Last Update 12 Aug 2026 02:34:39  Status Closed  Last 11.30  Prior 11.20
    SCB   Last Update 11 Aug 2026 08:07:17  Status Closed  Last -      Prior 152.00
    SET   Last Update 11 Aug 2026 12:04:53  Status Open1   Last 1618.80

Read naively, all three "are" the current price. In fact:

* BAFS 11.30 is the **final close of the 2026-08-11 session** — the stamp is
  02:34 on the 12th because that is when the page was rendered, *not* when the
  session was. The session date is NOT the stamp date.
* SCB's ``Last`` is ``-`` because the page is a **pre-open snapshot**. Its only
  usable number is ``Prior``, and ``Prior`` is the close of **2026-08-10**, two
  sessions before the stamp's implied "today".
* The SET index 1,618.80 is an **intraday tick**, not a close. Recording it as a
  close would be the futures/spot error in a new costume.

The rule this module enforces: **the session a number belongs to is derived
from the Last Update clock time relative to SET trading hours, never from the
stamp's calendar date.** A number whose session cannot be established is
returned as ``None`` with a reason, never guessed. This is the same principle
as ``observed_marks`` — absence propagates as absent — applied one layer
earlier, at the parse.

Stdlib only. No network unless ``fetch_and_parse()`` is called explicitly.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any, Optional

logger = logging.getLogger("set_official")

# SET continuous trading, Asia/Bangkok. Pre-open auction runs from ~09:30;
# the morning session opens 10:00 and the afternoon session closes 16:30.
SET_OPEN = time(10, 0)
SET_CLOSE = time(16, 30)

# SET spread (tick) table, in THB. (lower_bound_inclusive, tick).
# Used to reproduce the exchange's own ceiling/floor rounding as an integrity
# check on a scraped ``Prior``.
SET_TICK_TABLE: tuple[tuple[float, float], ...] = (
    (0.0, 0.01),
    (2.0, 0.02),
    (5.0, 0.05),
    (10.0, 0.10),
    (25.0, 0.25),
    (100.0, 0.50),
    (200.0, 1.00),
    (400.0, 2.00),
)

DAILY_PRICE_BAND = 0.30  # ±30% ceiling/floor

# Page states. These are not cosmetic labels — each implies a *different*
# answer to "which session does Last belong to", and two of them imply that
# Last is not a close at all.
PREOPEN = "PREOPEN"        # Before 10:00. Last is blank or belongs to a prior session.
INTRADAY = "INTRADAY"      # 10:00-16:30 and trading. Last is a live tick, NOT a close.
FINAL = "FINAL"            # After the close (or overnight). Last is a settled close.
UNKNOWN = "UNKNOWN"        # Stamp unparseable. Nothing is trusted.

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

# "Last Update : 12 Aug 2026 02:34:39" / "Last Update 11 Aug 2026 12:04:53"
_STAMP_RE = re.compile(
    r"Last\s+Update\s*:?\s*(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{4})\s+"
    r"(\d{1,2}):(\d{2})(?::(\d{2}))?",
    re.IGNORECASE,
)
_STATUS_RE = re.compile(r"(?:Market\s+)?Status\s*:?\s*([A-Za-z0-9]+)", re.IGNORECASE)

_NUM = r"(-|[\d,]+\.?\d*)"


class SetParseError(ValueError):
    """Raised when a page cannot be interpreted safely."""


@dataclass
class SetQuote:
    """One parsed SET quote page, with the session question answered explicitly."""

    symbol: str
    page_state: str
    stamp: Optional[datetime]
    status_text: Optional[str]
    last: Optional[float] = None
    prior: Optional[float] = None
    open_: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    volume: Optional[int] = None
    value_thousand_baht: Optional[float] = None
    average_price: Optional[float] = None
    ceiling: Optional[float] = None
    floor: Optional[float] = None
    change: Optional[float] = None
    pct_change: Optional[float] = None
    week52_low: Optional[float] = None
    week52_high: Optional[float] = None
    source_url: Optional[str] = None
    warnings: list[str] = field(default_factory=list)

    # -- the two questions callers actually care about -------------------------

    def close_mark(self) -> dict[str, Any]:
        """
        The defensible (close, session_date) pair, or an explicit refusal.

        Returns ``{"close": float|None, "session": str|None, "basis": str,
        "reason": str|None}``. ``basis`` names WHICH field the close came from
        ("last" or "prior"), because a caller that cannot tell those apart will
        eventually record a pre-open ``Prior`` as today's close — which is
        exactly how this project put a February BAFS price under an August date
        for five runs.
        """
        if self.stamp is None:
            return {"close": None, "session": None, "basis": "none",
                    "reason": "Last Update stamp unparseable; session cannot be established."}

        stamp_day = self.stamp.date()
        prev = previous_trading_day(stamp_day)

        if self.page_state == FINAL:
            if self.last is None:
                # Settled page with no Last: fall back to Prior, one session earlier.
                if self.prior is None:
                    return {"close": None, "session": None, "basis": "none",
                            "reason": "FINAL page carries neither Last nor Prior."}
                return {"close": self.prior, "session": previous_trading_day(prev).isoformat(),
                        "basis": "prior",
                        "reason": "FINAL page had no Last; used Prior, dated one session back."}
            session = stamp_day if self.stamp.time() > SET_CLOSE else prev
            return {"close": self.last, "session": session.isoformat(),
                    "basis": "last", "reason": None}

        if self.page_state == PREOPEN:
            if self.prior is None:
                return {"close": None, "session": None, "basis": "none",
                        "reason": "Pre-open page and no Prior value; nothing usable."}
            # Pre-open on day D: Prior is the close of the previous trading day.
            return {"close": self.prior, "session": prev.isoformat(), "basis": "prior",
                    "reason": "Pre-open snapshot; Last not yet published. Prior used."}

        if self.page_state == INTRADAY:
            # Deliberately refuse. An intraday tick is not a close and must not
            # be stored as one, however tempting a fresh-looking number is.
            return {"close": None, "session": None, "basis": "none",
                    "reason": ("Page is INTRADAY: 'Last' is a live tick, not a close. "
                               "Refused. Use prior_close() if the previous session is wanted.")}

        return {"close": None, "session": None, "basis": "none",
                "reason": f"Page state {self.page_state}; nothing trusted."}

    def prior_close(self) -> dict[str, Any]:
        """
        The (prior, session) pair — the session *before* the one ``Last`` describes.

        ``Prior`` is always one session behind whatever session the page is
        currently reporting, so it is resolved by finding that session first and
        then stepping back. Doing it any other way gets the overnight FINAL case
        wrong: a page stamped 02:34 on the 12th is reporting the 11th, so its
        ``Prior`` is the 10th — not the 11th, which is what dating from the
        stamp alone would give. (Caught by test on 2026-08-12.)
        """
        if self.stamp is None or self.prior is None:
            return {"close": None, "session": None,
                    "reason": "No stamp or no Prior field."}
        reporting = self._reporting_session()
        if reporting is None:
            return {"close": None, "session": None,
                    "reason": f"Cannot establish reporting session for state {self.page_state}."}
        return {"close": self.prior,
                "session": previous_trading_day(reporting).isoformat(),
                "reason": None}

    def _reporting_session(self) -> Optional[date]:
        """
        The trading session whose numbers this page is showing.

        FINAL after the close  -> that same calendar day.
        FINAL overnight/early  -> the previous trading day (the page is showing
                                  last night's settled figures).
        INTRADAY               -> that same calendar day (in progress).
        PREOPEN                -> the previous trading day is the last completed
                                  session, so that is what ``Prior`` steps back from;
                                  the page itself is reporting nothing yet.
        """
        if self.stamp is None:
            return None
        day = self.stamp.date()
        if self.page_state == FINAL:
            return day if self.stamp.time() > SET_CLOSE else previous_trading_day(day)
        if self.page_state == INTRADAY:
            return day
        if self.page_state == PREOPEN:
            return day
        return None

    def band_check(self) -> dict[str, Any]:
        """
        Recompute the exchange's own ceiling/floor from ``Prior`` and compare.

        SET sets the daily band at ±30% of the prior close, then rounds the
        result to the tick applicable *at the band price* — ceiling down, floor
        up. Reproducing that is a cheap, strong integrity check: if a scrape
        mangled ``Prior``, the published ceiling and floor will not reconcile,
        and a mangled prior is otherwise invisible.

        Returns ``{"checked": bool, "ok": bool|None, ...}``.
        """
        if self.prior is None or self.ceiling is None or self.floor is None:
            return {"checked": False, "ok": None,
                    "reason": "Need prior, ceiling and floor to check."}
        exp_ceiling = round_to_tick(self.prior * (1 + DAILY_PRICE_BAND), "down")
        exp_floor = round_to_tick(self.prior * (1 - DAILY_PRICE_BAND), "up")
        ok = (abs(exp_ceiling - self.ceiling) < 1e-9
              and abs(exp_floor - self.floor) < 1e-9)
        return {"checked": True, "ok": ok, "prior": self.prior,
                "expected_ceiling": exp_ceiling, "published_ceiling": self.ceiling,
                "expected_floor": exp_floor, "published_floor": self.floor,
                "reason": None if ok else "Band does not reconcile with Prior — suspect scrape."}

    def internal_consistency(self) -> dict[str, Any]:
        """
        Cross-check value/volume against the published average price, and check
        that Last sits inside the day range.

        Both are free — the page already carries every term — and both catch a
        column-misalignment, which is the failure mode a regex parser actually
        has.
        """
        checks: dict[str, Any] = {"checked": [], "failed": []}
        if self.value_thousand_baht and self.volume and self.average_price:
            implied = (self.value_thousand_baht * 1_000.0) / self.volume
            checks["checked"].append("avg_price")
            checks["implied_average_price"] = round(implied, 4)
            # Value/volume include trade reports and odd lots; average price is
            # auto-matching only, so an exact tie is not required.
            if abs(implied - self.average_price) / self.average_price > 0.02:
                checks["failed"].append("avg_price")
        if self.last is not None and self.high is not None and self.low is not None:
            checks["checked"].append("range")
            if not (self.low - 1e-9 <= self.last <= self.high + 1e-9):
                checks["failed"].append("range")
        checks["ok"] = not checks["failed"]
        return checks


# --------------------------------------------------------------------------- #
# Calendar
# --------------------------------------------------------------------------- #

# Added by nightly agent 2026-08-13 — holiday calendar wiring.
#
# The limitation this replaces was documented in the docstring below on
# 2026-08-12 and confirmed real within 24 hours: there was NO 2026-08-12 SET
# session (HM Queen Sirikit the Queen Mother's Birthday). The weekend-only
# implementation would have answered "2026-08-12" when asked for the session
# before Thursday 13 August, dating every mark derived from it one session late.
#
# Import is optional and failure is non-fatal: if set_holidays is unavailable
# the module keeps its previous weekend-only behaviour rather than refusing to
# load. But the degradation is *reported*, not silent — see
# ``holiday_calendar_status()`` — because a calendar that quietly downgrades is
# the bug, not the fix.
try:
    from . import set_holidays as _set_holidays  # type: ignore[attr-defined]
except (ImportError, ValueError):  # pragma: no cover - relative import outside a package
    try:
        import set_holidays as _set_holidays  # type: ignore[no-redef]
    except ImportError:
        _set_holidays = None  # type: ignore[assignment]


def holiday_calendar_status() -> dict:
    """
    Report whether holiday-aware date arithmetic is actually available.

    Callers that care about correct session dates should check this rather than
    assume. Returns ``mode`` of ``"holiday_aware"`` or ``"weekend_only"``.
    """
    if _set_holidays is None:
        return {
            "mode": "weekend_only",
            "covered_years": None,
            "warning": (
                "set_holidays not importable — previous_trading_day() skips weekends "
                "only and WILL return non-sessions on Thai public holidays."
            ),
        }
    first, last = _set_holidays.coverage()
    return {
        "mode": "holiday_aware",
        "covered_years": [first, last],
        "warning": None,
    }


def previous_trading_day(day: date) -> date:
    """
    Previous SET trading day.

    Holiday-aware when ``set_holidays`` is importable and ``day`` falls inside
    the years that table covers; weekend-only otherwise. The fallback is the
    module's pre-2026-08-13 behaviour and is retained so that a missing calendar
    degrades rather than crashes — but it is a genuine degradation, and
    :func:`holiday_calendar_status` exists so callers can tell which mode they
    are in instead of guessing.

    Worked example, the one that motivated the change::

        previous_trading_day(date(2026, 8, 13)) -> 2026-08-11

    not 2026-08-12, which was HM the Queen Mother's Birthday and not a session.
    """
    if _set_holidays is not None:
        try:
            return _set_holidays.previous_trading_day(day)
        except _set_holidays.YearNotCoveredError:
            # Outside the table's range. Fall through to weekend-only rather
            # than fail — but the caller can detect this via the status helper.
            pass
    d = day - timedelta(days=1)
    while d.weekday() >= 5:  # 5 = Saturday, 6 = Sunday
        d -= timedelta(days=1)
    return d


def round_to_tick(price: float, direction: str) -> float:
    """Round ``price`` to the SET spread unit applicable at that price level."""
    tick = SET_TICK_TABLE[0][1]
    for lower, t in SET_TICK_TABLE:
        if price >= lower:
            tick = t
        else:
            break
    steps = price / tick
    # Guard float noise: a value that is a tick multiple to within 1e-9 is one.
    if abs(steps - round(steps)) < 1e-6:
        steps = round(steps)
    elif direction == "down":
        steps = int(steps)
    elif direction == "up":
        steps = int(steps) + 1
    else:
        raise ValueError("direction must be 'up' or 'down'")
    return round(steps * tick, 4)


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #

def _to_float(raw: Optional[str]) -> Optional[float]:
    """'11.30' -> 11.3 ; '-' -> None ; '' -> None. Never raises, never returns 0 for absent."""
    if raw is None:
        return None
    s = raw.strip().replace(",", "").replace("+", "")
    if s in {"", "-", "--", "N/A", "n/a"}:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _field(text: str, label: str) -> Optional[float]:
    """Pull the number that follows a field label in the flattened page text."""
    pattern = re.compile(
        rf"(?:^|\n)\s*{re.escape(label)}\s*(?:\*\*)?\s*\n+\s*{_NUM}",
        re.IGNORECASE,
    )
    m = pattern.search(text)
    if m:
        return _to_float(m.group(1))
    # Inline form: "High 152.00"
    m = re.search(rf"{re.escape(label)}\s+{_NUM}(?:\s|$)", text, re.IGNORECASE)
    return _to_float(m.group(1)) if m else None


def parse_stamp(text: str) -> Optional[datetime]:
    """Parse the 'Last Update' wall-clock stamp. Returns None if absent."""
    m = _STAMP_RE.search(text)
    if not m:
        return None
    day, mon_raw, year, hh, mm, ss = m.groups()
    mon = _MONTHS.get(mon_raw[:3].lower())
    if mon is None:
        return None
    yr = int(year)
    # Buddhist-era guard. 2569 BE = 2026 CE. The English SET pages publish CE,
    # but Thai-language pages and several Thai vendors publish BE, and this
    # project has already been burned once by reading a BE year as CE.
    if yr > 2400:
        logger.warning("Buddhist-era year %d detected; converting to %d.", yr, yr - 543)
        yr -= 543
    try:
        return datetime(yr, mon, int(day), int(hh), int(mm), int(ss or 0))
    except ValueError:
        return None


def classify_page_state(stamp: Optional[datetime], status_text: Optional[str],
                        last: Optional[float]) -> str:
    """
    Decide which of PREOPEN / INTRADAY / FINAL / UNKNOWN the page is.

    Status text alone is not enough: SET prints ``Closed`` both for a pre-open
    page (nothing traded yet today) and for a settled post-close page, and
    those two have *opposite* correct readings of ``Prior``.
    """
    if stamp is None:
        return UNKNOWN
    t = stamp.time()
    status = (status_text or "").strip().lower()

    if status.startswith("open"):
        return INTRADAY
    if SET_OPEN <= t <= SET_CLOSE and not status.startswith("close"):
        return INTRADAY
    if t < SET_OPEN:
        # Overnight/early morning. If Last carries a number it is last night's
        # settled close; if it is blank the page is a true pre-open shell.
        return FINAL if last is not None else PREOPEN
    return FINAL


def parse_quote_page(text: str, symbol: str, source_url: Optional[str] = None) -> SetQuote:
    """
    Parse the text of a set.or.th stock quote page.

    ``text`` is whatever the caller retrieved — rendered text or markdown. This
    function performs NO network access.
    """
    if not text or len(text) < 200:
        raise SetParseError("Page text is empty or implausibly short.")

    stamp = parse_stamp(text)
    status_m = _STATUS_RE.search(text)
    status_text = status_m.group(1) if status_m else None

    last = _field(text, "Last")
    prior = _field(text, "Prior")

    quote = SetQuote(
        symbol=symbol.upper(),
        page_state=classify_page_state(stamp, status_text, last),
        stamp=stamp,
        status_text=status_text,
        last=last,
        prior=prior,
        open_=_field(text, "Open"),
        high=_field(text, "High"),
        low=_field(text, "Low"),
        average_price=_field(text, "Average Price"),
        ceiling=_field(text, "Ceiling"),
        floor=_field(text, "Floor"),
        source_url=source_url,
    )

    vol = re.search(r"Volume\s*\(Shares\)\s*\n*\s*([\d,]+)", text, re.IGNORECASE)
    if vol:
        quote.volume = int(vol.group(1).replace(",", ""))
    val = re.search(r"Value\s*\('000 Baht\)\s*\n*\s*([\d,]+\.?\d*)", text, re.IGNORECASE)
    if val:
        quote.value_thousand_baht = _to_float(val.group(1))

    chg = re.search(r"([+-]?[\d,]+\.\d+)\s*\n?\s*\(([+-]?[\d.]+)%\)", text)
    if chg:
        quote.change = _to_float(chg.group(1))
        quote.pct_change = _to_float(chg.group(2))

    rng = re.search(r"52\s*Weeks?\s*Range\s*\n+\s*([\d,]+\.?\d*)\s*\n+\s*([\d,]+\.?\d*)",
                    text, re.IGNORECASE)
    if rng:
        quote.week52_low = _to_float(rng.group(1))
        quote.week52_high = _to_float(rng.group(2))

    if quote.page_state == UNKNOWN:
        quote.warnings.append("Last Update stamp not found — no session can be assigned.")
    if quote.last is None and quote.prior is None:
        quote.warnings.append("Neither Last nor Prior parsed — check page layout drift.")

    band = quote.band_check()
    if band["checked"] and not band["ok"]:
        quote.warnings.append(f"Price band does not reconcile with Prior: {band}")
    cons = quote.internal_consistency()
    if cons["failed"]:
        quote.warnings.append(f"Internal consistency failed: {cons['failed']}")

    return quote


def to_observed_mark_kwargs(quote: SetQuote) -> Optional[dict[str, Any]]:
    """
    Shape a parsed quote for ``observed_marks.record_mark(**kwargs)``.

    Returns None when the page yields no defensible close — the caller then
    records nothing, which is the correct outcome and better than a mark whose
    session is a guess.
    """
    mark = quote.close_mark()
    if mark["close"] is None or mark["session"] is None:
        logger.info("%s: no defensible close (%s).", quote.symbol, mark["reason"])
        return None
    note = f"SET first-party page, state={quote.page_state}, basis={mark['basis']}"
    if mark["reason"]:
        note += f" ({mark['reason']})"
    return {
        "ticker": f"{quote.symbol}.BK",
        "close": mark["close"],
        "observed_as_of": mark["session"],
        "source_name": "set.or.th (Stock Exchange of Thailand, first-party)",
        "source_url": quote.source_url or
                      f"https://www.set.or.th/en/market/product/stock/quote/{quote.symbol}/price",
        "currency": "THB",
        "note": note,
    }


def fetch_and_parse(symbol: str, timeout: int = 20) -> SetQuote:
    """
    Convenience path for **Tho's machine only**, where outbound HTTP works.

    Deliberately not used by the nightly agent: egress from the agent's Python
    is blocked at a proxy (verified 2026-08-11), and pretending otherwise is
    what produced an unrunnable module on 2026-08-10.
    """
    from urllib.request import Request, urlopen  # local import: keeps module import-safe

    url = f"https://www.set.or.th/en/market/product/stock/quote/{symbol.lower()}/price"
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (investment_advisor)"})
    with urlopen(req, timeout=timeout) as resp:  # noqa: S310 - fixed, first-party host
        html = resp.read().decode("utf-8", errors="replace")
    text = re.sub(r"<[^>]+>", "\n", html)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return parse_quote_page(text, symbol, source_url=url)


__all__ = [
    "SetQuote", "SetParseError", "parse_quote_page", "parse_stamp",
    "classify_page_state", "previous_trading_day", "round_to_tick",
    "holiday_calendar_status",
    "to_observed_mark_kwargs", "fetch_and_parse",
    "PREOPEN", "INTRADAY", "FINAL", "UNKNOWN",
]
