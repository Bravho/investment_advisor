"""
Fallback SET price reader — breaks the dependency on the dead collector daemon.

WHY THIS MODULE EXISTS
----------------------
The live market-data collector (``data_collector/market_data.py``) has been down
since 2026-07-15 23:53 ICT. It stopped on a clean SIGTERM and was never
restarted. Six consecutive nightly runs have named "restart the collector" as
the top priority and six consecutive nightly runs have been unable to do it,
because the remedy is a supervisor/launchd job on Tho's machine and a nightly
agent does not restart processes.

That is a real constraint, but it produced a worse failure than the outage
itself: every nightly run kept re-deriving portfolio weights, concentration
flags and deltas from marks carried forward from 2026-08-04, and reported them
with a current date. On 2026-08-10 the carried BAFS mark (9.80) was checked
against the market for the first time in six runs and turned out to be wrong by
+18.4% — the actual 2026-08-07 close was 11.60. The book was understated by
about THB 41,000. The marks were not merely stale; they were silently wrong,
and nothing in the pipeline could tell the difference.

The lesson is that a single price path with no fallback is a single point of
failure for the entire advisory product. This module is the fallback. It reads
end-of-day OHLCV for SET-listed tickers from a public Thai retail-investor
site, independently of PostgreSQL, yfinance, the scheduler and the daemon. It
is NOT a replacement for the collector — it has no intraday capability, no
database write path and a third-party dependency — it is a way for the nightly
run to answer "what is this actually worth today?" without a live daemon.

DESIGN RULES (inherited from the cost_basis_guard / dividend-store defects)
--------------------------------------------------------------------------
1. **Absence propagates as absent.** Every accessor returns ``None`` on failure,
   never ``0`` and never a silently carried previous value. The three worst
   defects this project has had (avg_cost_price = 0, the unwritten dividend
   store, the carried price marks) were all absence rendering as a plausible
   number.
2. **Verify at the read path, not the write path.** ``self_test()`` exercises
   the real parse against live HTML rather than checking that a helper exists.
3. **Every quote carries its own as-of date, from the source row.** A quote
   without a date is discarded, because an undated quote is what allowed a
   February price to masquerade as an August one.
4. **The source is named in the return value.** Downstream code must be able to
   tell a fallback mark from a collector mark and label it for Tho.

Buddhist-era dates: the source publishes dates as Thai Buddhist calendar years
(2569 = 2026) with abbreviated Thai month names. ``_parse_thai_date`` converts
these to ISO. A row whose date cannot be parsed is dropped, not guessed.

Added by nightly agent 2026-08-10
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

_SOURCE_NAME = "aio.panphol.com"
_SOURCE_URL_TEMPLATE = "https://aio.panphol.com/stock/{symbol}/price"
_REQUEST_TIMEOUT_SECONDS = 20
_USER_AGENT = "investment-advisor-nightly/1.0 (personal portfolio tracker)"

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_CACHE_DIR = _PROJECT_ROOT / "data" / "price_cache"

# Portfolio tickers, in the project's canonical ".BK" form, mapped to the plain
# SET symbol the source uses. Extend as positions change.
TICKER_TO_SET_SYMBOL: dict[str, str] = {
    "BAFS.BK": "BAFS",
    "PTTEP.BK": "PTTEP",
    "SCB.BK": "SCB",
}

# Thai Buddhist-era month abbreviations as published by the source.
_THAI_MONTH_ABBR: dict[str, int] = {
    "ม.ค.": 1,
    "ก.พ.": 2,
    "มี.ค.": 3,
    "เม.ย.": 4,
    "พ.ค.": 5,
    "มิ.ย.": 6,
    "ก.ค.": 7,
    "ส.ค.": 8,
    "ก.ย.": 9,
    "ต.ค.": 10,
    "พ.ย.": 11,
    "ธ.ค.": 12,
}

_BUDDHIST_ERA_OFFSET = 543


# --------------------------------------------------------------------------
# Data model
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class DailyQuote:
    """
    One end-of-day bar for one SET ticker.

    ``as_of`` is the trading date the source published for the row, converted
    from the Thai Buddhist calendar. It is never inferred from "today" — a bar
    without a parseable date is discarded upstream, so an instance of this class
    always knows which session it describes.
    """

    ticker: str
    as_of: str          # ISO date, e.g. "2026-08-07"
    open: Optional[float]
    close: Optional[float]
    high: Optional[float]
    low: Optional[float]
    change: Optional[float]
    change_pct: Optional[float]
    volume: Optional[int]
    source: str = _SOURCE_NAME

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def age_days(self, reference: Optional[date] = None) -> Optional[int]:
        """Calendar days between this bar's session and ``reference`` (today)."""
        reference = reference or datetime.now(timezone.utc).date()
        try:
            return (reference - date.fromisoformat(self.as_of)).days
        except (ValueError, TypeError):
            return None


# --------------------------------------------------------------------------
# Parsing helpers
# --------------------------------------------------------------------------

def _parse_thai_date(raw: str) -> Optional[str]:
    """
    Convert a Thai Buddhist-era date such as "07 ส.ค. 69" to ISO "2026-08-07".

    The source abbreviates the year to two digits of the Buddhist era (69 =
    2569 BE = 2026 CE). Returns None if any component fails to parse — callers
    MUST drop the row rather than substitute a date.
    """
    if not raw:
        return None
    parts = raw.strip().split()
    if len(parts) != 3:
        return None
    day_text, month_text, year_text = parts
    month = _THAI_MONTH_ABBR.get(month_text)
    if month is None:
        return None
    try:
        day = int(day_text)
        year_be_short = int(year_text)
    except ValueError:
        return None
    # Two-digit Buddhist year -> full Buddhist year -> Gregorian.
    year_be_full = 2500 + year_be_short if year_be_short < 100 else year_be_short
    year_ce = year_be_full - _BUDDHIST_ERA_OFFSET
    try:
        return date(year_ce, month, day).isoformat()
    except ValueError:
        return None


def _to_float(raw: Any) -> Optional[float]:
    """Parse a possibly comma-formatted number. Returns None, never 0.0."""
    if raw is None:
        return None
    text = str(raw).strip().replace(",", "").replace("+", "").replace("%", "")
    if not text or text in {"-", "—", "–"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _to_int(raw: Any) -> Optional[int]:
    value = _to_float(raw)
    return int(value) if value is not None else None


# --------------------------------------------------------------------------
# Failure classification
#
# Added by nightly agent 2026-08-11.
#
# The 2026-08-10 version of self_test() reported ok=False identically whether
# the page could not be reached or the page was reached and could not be
# parsed. Those two failures have opposite remedies — one is an environment
# problem nobody can fix from here, the other is a code defect that must be
# fixed tonight — and collapsing them is the same mistake as a dead feed and a
# broken parser being indistinguishable downstream, which cost this project six
# runs. The classification below exists so the report names the right remedy.
#
# The specific case that motivated it: run live from the nightly agent's own
# sandbox on 2026-08-11, every ticker failed with
#     urlopen error Tunnel connection failed: 403 Forbidden
# i.e. an egress proxy refusing outbound HTTP. Nothing about the parser was
# wrong. See data_collector/observed_marks.py for the agent-side path that
# exists because of this.
# --------------------------------------------------------------------------

FAILURE_NETWORK_BLOCKED = "NETWORK_BLOCKED"
FAILURE_NETWORK_UNREACHABLE = "NETWORK_UNREACHABLE"
FAILURE_HTTP_ERROR = "HTTP_ERROR"
FAILURE_PARSE = "PARSE_FAILURE"
FAILURE_STALE = "SOURCE_STALE"
FAILURE_NONE = "OK"

# Substrings that identify an egress proxy or firewall refusing the request
# rather than the origin being down. A proxy 403 on CONNECT is categorically
# different from the site returning 403 to us.
_EGRESS_BLOCK_SIGNATURES = (
    "tunnel connection failed",
    "proxy",
    "forbidden by proxy",
    "connection refused by",
)

# Last failure seen by _fetch_html, per symbol. Read by self_test().
_LAST_FETCH_ERROR: dict[str, dict[str, str]] = {}


def _classify_fetch_error(exc: BaseException) -> str:
    """Map a fetch exception onto one of the FAILURE_* codes."""
    text = str(exc).lower()
    if any(signature in text for signature in _EGRESS_BLOCK_SIGNATURES):
        return FAILURE_NETWORK_BLOCKED
    if isinstance(exc, urllib.error.HTTPError):
        return FAILURE_HTTP_ERROR
    return FAILURE_NETWORK_UNREACHABLE


def last_fetch_error(symbol: str) -> Optional[dict[str, str]]:
    """Most recent fetch failure for ``symbol``, or None if the last fetch worked."""
    return _LAST_FETCH_ERROR.get(symbol.upper())


def _fetch_html(symbol: str) -> Optional[str]:
    """GET the source page. Returns None on any network or HTTP failure."""
    url = _SOURCE_URL_TEMPLATE.format(symbol=symbol)
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=_REQUEST_TIMEOUT_SECONDS) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            body = response.read().decode(charset, errors="replace")
        _LAST_FETCH_ERROR.pop(symbol.upper(), None)
        return body
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        kind = _classify_fetch_error(exc)
        _LAST_FETCH_ERROR[symbol.upper()] = {"failure": kind, "detail": str(exc), "url": url}
        logger.warning("Fallback price fetch failed for %s [%s]: %s", symbol, kind, exc)
        return None


def _strip_tags(cell: str) -> str:
    return re.sub(r"<[^>]+>", "", cell).replace("&nbsp;", " ").strip()


def _parse_price_rows(html: str, ticker: str) -> list[DailyQuote]:
    """
    Extract the daily OHLCV table from the page HTML.

    The table columns are, in order:
        date | open | close | change | change% | high | low | volume | P/E | yield | beta

    Rows that do not yield a parseable date are DROPPED. A row that parses but
    has an unparseable close is kept with ``close=None`` so the caller can see
    that the session exists but the price is unknown — which is different from
    the session not existing.
    """
    quotes: list[DailyQuote] = []
    for row_html in re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.DOTALL | re.IGNORECASE):
        cells = [
            _strip_tags(cell)
            for cell in re.findall(
                r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, flags=re.DOTALL | re.IGNORECASE
            )
        ]
        if len(cells) < 8:
            continue
        as_of = _parse_thai_date(cells[0])
        if as_of is None:
            continue  # header row, or a date we refuse to guess at
        quotes.append(
            DailyQuote(
                ticker=ticker,
                as_of=as_of,
                open=_to_float(cells[1]),
                close=_to_float(cells[2]),
                change=_to_float(cells[3]),
                change_pct=_to_float(cells[4]),
                high=_to_float(cells[5]),
                low=_to_float(cells[6]),
                volume=_to_int(cells[7]),
            )
        )
    quotes.sort(key=lambda quote: quote.as_of, reverse=True)
    return quotes


# --------------------------------------------------------------------------
# Public accessors
# --------------------------------------------------------------------------

def fetch_daily_history(ticker: str, limit: int = 60) -> list[DailyQuote]:
    """
    Fetch up to ``limit`` most recent end-of-day bars for a SET ticker.

    Accepts either the canonical "BAFS.BK" form or the plain "BAFS" symbol.
    Returns an empty list on failure — callers must treat empty as "unknown",
    never as "no movement".
    """
    symbol = TICKER_TO_SET_SYMBOL.get(ticker.upper(), ticker.upper().replace(".BK", ""))
    html = _fetch_html(symbol)
    if html is None:
        return []
    quotes = _parse_price_rows(html, ticker.upper())
    if not quotes:
        logger.warning(
            "Fallback source returned HTML for %s but no parseable price rows — "
            "the page layout may have changed. Run self_test().",
            ticker,
        )
    return quotes[:limit]


def latest_close(ticker: str, max_age_days: int = 7) -> Optional[DailyQuote]:
    """
    Most recent end-of-day bar for ``ticker``, or None.

    ``max_age_days`` guards against the fallback quietly becoming its own stale
    feed: a bar older than the threshold is REFUSED rather than returned with a
    warning, because the entire point of this module is that a stale mark and a
    fresh mark must not be interchangeable. Note that SET closes for weekends
    and Thai public holidays, so the default tolerates a long weekend.
    """
    history = fetch_daily_history(ticker, limit=5)
    for quote in history:
        if quote.close is None:
            continue
        age = quote.age_days()
        if age is None:
            continue
        if age > max_age_days:
            logger.warning(
                "Fallback quote for %s is %d days old (as_of %s, limit %d) — REFUSED.",
                ticker,
                age,
                quote.as_of,
                max_age_days,
            )
            return None
        return quote
    return None


def latest_closes(
    tickers: Optional[list[str]] = None,
    max_age_days: int = 7,
) -> dict[str, Optional[DailyQuote]]:
    """
    Latest close for each ticker. Values are None where the price is unknown.

    The returned dict always has a key for every requested ticker, so callers
    can distinguish "we asked and could not find out" from "we never asked".
    """
    tickers = tickers or list(TICKER_TO_SET_SYMBOL)
    return {ticker: latest_close(ticker, max_age_days=max_age_days) for ticker in tickers}


def portfolio_marks(
    shares: dict[str, int],
    max_age_days: int = 7,
) -> dict[str, Any]:
    """
    Value a SET equity book from fallback marks.

    Returns a dict with per-position values, the total, and — critically — an
    explicit ``unpriced`` list. If ANY position is unpriced the total is
    returned as None rather than as a partial sum, because a partial sum of a
    portfolio silently understates it and reads as a real number downstream.
    That is exactly the failure mode that let a THB 41,000 gap sit unnoticed
    for six runs.
    """
    quotes = latest_closes(list(shares), max_age_days=max_age_days)
    positions: dict[str, Any] = {}
    unpriced: list[str] = []
    running_total = 0.0

    for ticker, quantity in shares.items():
        quote = quotes.get(ticker)
        if quote is None or quote.close is None:
            unpriced.append(ticker)
            positions[ticker] = {
                "shares": quantity,
                "price": None,
                "value_thb": None,
                "as_of": None,
                "source": None,
            }
            continue
        value = round(quote.close * quantity, 2)
        running_total += value
        positions[ticker] = {
            "shares": quantity,
            "price": quote.close,
            "value_thb": value,
            "as_of": quote.as_of,
            "source": quote.source,
        }

    return {
        "positions": positions,
        "unpriced": unpriced,
        "total_thb": None if unpriced else round(running_total, 2),
        "total_is_partial": bool(unpriced),
        "total_note": (
            "SUPPRESSED — one or more positions could not be priced. A partial "
            "sum would understate the book and is not returned."
            if unpriced
            else "Complete: every requested position was priced."
        ),
        "source": _SOURCE_NAME,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }


# --------------------------------------------------------------------------
# Cache — lets a later run reuse tonight's marks without re-fetching
# --------------------------------------------------------------------------

def save_quotes(quotes: dict[str, Optional[DailyQuote]], as_of: Optional[str] = None) -> Optional[Path]:
    """Persist a set of quotes to data/price_cache/YYYY-MM-DD.json."""
    as_of = as_of or datetime.now(timezone.utc).date().isoformat()
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        target = _CACHE_DIR / f"{as_of}.json"
        payload = {
            "written_at": datetime.now(timezone.utc).isoformat(),
            "source": _SOURCE_NAME,
            "quotes": {
                ticker: (quote.to_dict() if quote is not None else None)
                for ticker, quote in quotes.items()
            },
        }
        target.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return target
    except OSError as exc:
        logger.warning("Could not write fallback price cache: %s", exc)
        return None


# --------------------------------------------------------------------------
# Self-test — exercises the REAL parse, per design rule 2
# --------------------------------------------------------------------------

def self_test() -> dict[str, Any]:
    """
    Verify the fallback end to end against live HTML.

    Checks that (a) the page fetches, (b) rows parse, (c) the newest bar is
    recent, and (d) the close is a plausible positive number. Returns a report
    dict; ``ok`` is True only if every ticker passes. Intended to be run by the
    nightly agent BEFORE relying on any mark this module produces.
    """
    results: dict[str, Any] = {}
    for ticker in TICKER_TO_SET_SYMBOL:
        symbol = TICKER_TO_SET_SYMBOL[ticker]
        history = fetch_daily_history(ticker, limit=5)
        newest = history[0] if history else None
        fetch_error = last_fetch_error(symbol)

        # Added by nightly agent 2026-08-11 — name WHICH failure, not just that
        # one happened. See the classification block above for why.
        if fetch_error is not None:
            failure = fetch_error["failure"]
        elif not history:
            failure = FAILURE_PARSE
        elif newest is None or newest.close is None or newest.close <= 0:
            failure = FAILURE_PARSE
        elif (newest.age_days() or 999) > 7:
            failure = FAILURE_STALE
        else:
            failure = FAILURE_NONE

        results[ticker] = {
            "rows_parsed": len(history),
            "newest_as_of": newest.as_of if newest else None,
            "newest_close": newest.close if newest else None,
            "age_days": newest.age_days() if newest else None,
            "failure": failure,
            "failure_detail": (fetch_error or {}).get("detail"),
            "ok": failure == FAILURE_NONE,
        }

    failures = {entry["failure"] for entry in results.values()} - {FAILURE_NONE}
    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "source": _SOURCE_NAME,
        "tickers": results,
        "failures": sorted(failures),
        "diagnosis": _diagnose(failures),
        "ok": all(entry["ok"] for entry in results.values()),
    }


def _diagnose(failures: set) -> str:
    """
    Turn a set of failure codes into the remedy, not a restatement of the fault.

    Deliberately opinionated: a report that says "something went wrong" makes
    the reader do the diagnosis, and at 2:30 a.m. nobody does.
    """
    if not failures:
        return (
            "OK — the source is reachable, the layout parses, and every quote is "
            "recent. Marks from this module can be trusted for this run."
        )
    if FAILURE_NETWORK_BLOCKED in failures:
        return (
            "NETWORK BLOCKED AT AN EGRESS PROXY — this is an ENVIRONMENT limit, "
            "not a code defect, and it cannot be fixed by editing this module. "
            "Outbound HTTP from Python is refused here. Run this module on Tho's "
            "own machine, where egress is unrestricted. For the nightly agent, "
            "use data_collector/observed_marks.py instead: the agent retrieves "
            "the price with its own tooling and records it with provenance. "
            "DO NOT 'fix' this by relaxing the parser."
        )
    if FAILURE_NETWORK_UNREACHABLE in failures:
        return (
            "SOURCE UNREACHABLE — DNS, TLS or connectivity failure. Retry later; "
            "if it persists across runs the source may have moved and a "
            "replacement is needed. The parser is untested either way."
        )
    if FAILURE_HTTP_ERROR in failures:
        return (
            "SOURCE RETURNED AN HTTP ERROR — the origin answered and refused. "
            "Likely rate limiting, a changed path, or bot blocking. Check the URL "
            "template before touching the parser."
        )
    if FAILURE_PARSE in failures:
        return (
            "PAGE FETCHED BUT DID NOT PARSE — this IS a code defect and is "
            "actionable tonight. The source layout has probably changed; "
            "re-derive the column order in _parse_price_rows against the live "
            "page. Do not ship marks from this module until it passes."
        )
    if FAILURE_STALE in failures:
        return (
            "SOURCE REACHABLE AND PARSING BUT ITS NEWEST BAR IS OLD — the source "
            "itself has stopped updating. Treat its quotes as unusable and find a "
            "second source rather than widening the age limit."
        )
    return f"UNCLASSIFIED failure set: {sorted(failures)}"


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    report = self_test()
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
