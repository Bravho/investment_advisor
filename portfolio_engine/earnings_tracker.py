"""
earnings_tracker.py — Pre-earnings alert and calendar module for SET holdings.

Stores upcoming earnings/results release dates for Tho's holdings.
Scans for events within a configurable alert window (default: 3 days) and
returns a pre-earnings brief context dict that can be injected into the
daily brief prompt or emailed separately.

Data is persisted to data/earnings/earnings_calendar.json so entries
survive across restarts and can be enriched manually.

Holdings tracked: SCB.BK (SCB X, next: 2026-07-17), PTTEP.BK, BAFS.BK.

Added by nightly agent 2026-06-13
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from utils.common import PROJECT_DIR, configure_logging

logger = configure_logging("portfolio_engine.earnings_tracker")

# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

_EARNINGS_DIR = PROJECT_DIR / "data" / "earnings"
_EARNINGS_FILE = _EARNINGS_DIR / "earnings_calendar.json"


@dataclass
class EarningsEvent:
    """A single earnings / results announcement for a SET holding."""

    ticker: str
    company_name: str
    event_type: str                # "quarterly_results" | "annual_results" | "interim_dividend_announcement"
    expected_date: str             # ISO YYYY-MM-DD  (confirmed or estimated)
    confirmed: bool = False        # True once SET/company officially confirms
    time_of_day: str = "after_close"  # "before_open" | "after_close" | "unknown"
    notes: str = ""
    added_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def _load_calendar() -> list[EarningsEvent]:
    """Load persisted earnings calendar from JSON file."""
    if not _EARNINGS_FILE.exists():
        return []
    try:
        raw = json.loads(_EARNINGS_FILE.read_text(encoding="utf-8"))
        return [EarningsEvent(**item) for item in raw]
    except (json.JSONDecodeError, TypeError, KeyError):
        logger.warning("Could not parse %s — returning empty calendar", _EARNINGS_FILE)
        return []


def _save_calendar(events: list[EarningsEvent]) -> None:
    """Persist earnings calendar to JSON."""
    _EARNINGS_DIR.mkdir(parents=True, exist_ok=True)
    _EARNINGS_FILE.write_text(
        json.dumps([asdict(e) for e in events], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def add_earnings_event(
    ticker: str,
    company_name: str,
    event_type: str,
    expected_date: str,
    confirmed: bool = False,
    time_of_day: str = "after_close",
    notes: str = "",
) -> EarningsEvent:
    """
    Add or update an earnings event. If an event with the same ticker +
    expected_date already exists it is overwritten (upsert behaviour).
    """
    events = _load_calendar()
    new_event = EarningsEvent(
        ticker=ticker,
        company_name=company_name,
        event_type=event_type,
        expected_date=expected_date,
        confirmed=confirmed,
        time_of_day=time_of_day,
        notes=notes,
    )
    # Upsert: replace existing entry with same ticker + date
    events = [
        e for e in events
        if not (e.ticker == ticker and e.expected_date == expected_date)
    ]
    events.append(new_event)
    _save_calendar(events)
    logger.info("Earnings event upserted: %s on %s", ticker, expected_date)
    return new_event


def get_earnings_events(ticker: str | None = None) -> list[EarningsEvent]:
    """Return all events, optionally filtered by ticker."""
    events = _load_calendar()
    if ticker:
        events = [e for e in events if e.ticker.upper() == ticker.upper()]
    return sorted(events, key=lambda e: e.expected_date)


# ---------------------------------------------------------------------------
# Alert scanner
# ---------------------------------------------------------------------------

def upcoming_earnings_alerts(
    alert_days: int = 3,
    reference_date: date | None = None,
) -> list[dict[str, Any]]:
    """
    Return earnings events where expected_date falls within [today, today + alert_days].

    Each result dict contains the event fields plus:
      - days_until: int  (0 = today, 1 = tomorrow, etc.)
      - alert_level: "imminent" (0-1 days) | "upcoming" (2-3 days) | "watch" (>3)
    """
    ref = reference_date or date.today()
    horizon = ref + timedelta(days=alert_days)
    alerts = []
    for event in _load_calendar():
        try:
            ev_date = date.fromisoformat(event.expected_date)
        except ValueError:
            continue
        if ref <= ev_date <= horizon:
            days_until = (ev_date - ref).days
            alert_level = "imminent" if days_until <= 1 else "upcoming"
            row = asdict(event)
            row["days_until"] = days_until
            row["alert_level"] = alert_level
            alerts.append(row)
    return sorted(alerts, key=lambda r: r["days_until"])


# ---------------------------------------------------------------------------
# Pre-earnings brief context builder
# ---------------------------------------------------------------------------

def pre_earnings_brief(
    alert_days: int = 3,
    reference_date: date | None = None,
) -> dict[str, Any]:
    """
    Build a structured context dict for upcoming earnings events.
    Designed to be injected directly into the daily brief prompt.

    Returns:
      {
        "has_upcoming_earnings": bool,
        "alerts": [...],          # from upcoming_earnings_alerts()
        "summary_text": str,      # human-readable for prompt injection
      }
    """
    alerts = upcoming_earnings_alerts(alert_days=alert_days, reference_date=reference_date)
    if not alerts:
        return {
            "has_upcoming_earnings": False,
            "alerts": [],
            "summary_text": "No earnings events within the next 3 days.",
        }

    lines = []
    for a in alerts:
        conf_marker = "✓ confirmed" if a["confirmed"] else "est."
        lines.append(
            f"• {a['ticker']} ({a['company_name']}) — {a['event_type']} on "
            f"{a['expected_date']} ({conf_marker}), {a['days_until']} day(s) away. "
            f"Time: {a['time_of_day']}. Notes: {a['notes']}"
        )

    return {
        "has_upcoming_earnings": True,
        "alerts": alerts,
        "summary_text": (
            f"⚠️ UPCOMING EARNINGS ALERT ({len(alerts)} event(s) within {alert_days} days):\n"
            + "\n".join(lines)
        ),
    }


# ---------------------------------------------------------------------------
# Earnings preview loader (consensus estimate enrichment)
# Added by nightly agent 2026-06-14
# ---------------------------------------------------------------------------

def load_earnings_preview(ticker: str) -> dict[str, Any] | None:
    """
    Load a consensus/estimate preview JSON for an upcoming earnings event.

    Preview files live in data/earnings/<slug>_preview.json and contain
    analyst-estimate metrics (NIM, NPL, dividend outlook, scenario reactions).
    Currently available: SCB.BK -> scb_h12026_preview.json;
    BAFS.BK -> bafs_h12026_preview.json (AUTHORED 2026-08-05 ahead of the est.
    2026-08-14 H1 print and the CONFIRMED 2026-08-28 investor meeting; frames the
    print on VOLUME/arrivals rather than fuel cost, because H1 covers Jan-Jun and
    therefore PRE-DATES the Aug-03/04 Brent collapse to $79.47).

    Returns the parsed dict, or None if no preview file exists for the ticker.

    Added by nightly agent 2026-06-14
    """
    # Map ticker -> preview filename (extend as new previews are authored)
    preview_map = {
        "SCB.BK": "scb_h12026_preview.json",
        # Added by nightly agent 2026-08-05 — BAFS is the one holding the Aug-04/05
        # oil regime change HELPS, and it is ~29% of Tho's ex-gold book, so the H1
        # print needed a preview. Key framing: H1 = Jan-Jun, when Brent was mostly
        # ELEVATED, so the oil relief lands in Q3/Q4 not here. Judge on throughput.
        "BAFS.BK": "bafs_h12026_preview.json",
    }
    filename = preview_map.get(ticker.upper())
    if not filename:
        return None
    preview_file = _EARNINGS_DIR / filename
    if not preview_file.exists():
        logger.info("No earnings preview file found for %s at %s", ticker, preview_file)
        return None
    try:
        return json.loads(preview_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("Could not parse earnings preview %s", preview_file)
        return None


# ---------------------------------------------------------------------------
# Post-earnings actuals loader (result reconciliation)
# Added by nightly agent 2026-07-24
# ---------------------------------------------------------------------------

def load_earnings_actual(ticker: str) -> dict[str, Any] | None:
    """
    Load a post-earnings ACTUALS JSON for a reported earnings event.

    Actual files live in data/earnings/<slug>_actual.json and hold the reported
    figures plus a reconciliation against the pre-earnings preview (beat/inline/
    miss vs consensus, dividend outcome, and an updated thesis read). This is the
    counterpart to load_earnings_preview(): once a company reports, the nightly
    agent writes the actuals file so the brief can switch from "preview" to
    "reported + reconciled" without touching the preview.
    Currently available: SCB.BK -> scb_q22026_actual.json;
    PTTEP.BK -> pttep_q22026_actual.json (CAPTURED 2026-08-02: Q2 net profit
    USD 833m / +104% YoY, record ~573kboe/d volume, THB 4.50 interim div pay
    Aug-28; reconciled in line-to-beat vs the CLSA/DBS preview).

    Returns the parsed dict, or None if no actuals file exists for the ticker.

    Added by nightly agent 2026-07-24
    """
    # Map ticker -> actuals filename (extend as new results are captured)
    actual_map = {
        "SCB.BK": "scb_q22026_actual.json",
        # Pre-registered 2026-07-26; actuals CAPTURED by nightly agent 2026-08-02
        # from the Q2-2026 print (released Aug-02, analyst meeting Aug-03). The
        # file now exists, so load_earnings_actual() returns the reported+reconciled
        # dict and the brief auto-switches PTTEP from preview to reported. Key: net
        # profit USD 833m (+104% YoY / +122% QoQ), record 572,882 boe/d, ASP
        # $52.89/boe, H1 net income THB 39.03bn, THB 4.50 interim div (pay Aug-28).
        "PTTEP.BK": "pttep_q22026_actual.json",
    }
    filename = actual_map.get(ticker.upper())
    if not filename:
        return None
    actual_file = _EARNINGS_DIR / filename
    if not actual_file.exists():
        logger.info("No earnings actuals file found for %s at %s", ticker, actual_file)
        return None
    try:
        return json.loads(actual_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("Could not parse earnings actuals %s", actual_file)
        return None


def pre_earnings_brief_enriched(
    alert_days: int = 3,
    reference_date: date | None = None,
) -> dict[str, Any]:
    """
    Like pre_earnings_brief(), but attaches any available consensus-estimate
    preview data (NIM/NPL/dividend outlook, scenario reactions) for each
    alerting ticker. Use this in brief_generator when you want the LLM to see
    the estimate context, not just the calendar entry.

    Returns the pre_earnings_brief() dict plus a "previews" list, each item:
      {"ticker": str, "preview": {...}}  and an expanded "summary_text".

    Added by nightly agent 2026-06-14
    """
    base = pre_earnings_brief(alert_days=alert_days, reference_date=reference_date)
    if not base.get("has_upcoming_earnings"):
        return base

    previews: list[dict[str, Any]] = []
    extra_lines: list[str] = []
    seen: set[str] = set()
    for alert in base["alerts"]:
        ticker = alert["ticker"]
        if ticker in seen:
            continue
        seen.add(ticker)
        preview = load_earnings_preview(ticker)
        if preview:
            previews.append({"ticker": ticker, "preview": preview})
            cons = preview.get("consensus_estimates", {})
            div = preview.get("dividend_outlook", {})
            np_base = cons.get("net_profit_h1_2026_bn_thb", {}).get("base")
            nim = cons.get("net_interest_margin_pct", {}).get("base")
            npl = cons.get("npl_ratio_pct", {}).get("base")
            div_base = div.get("h1_2026_interim_div_est_thb", {}).get("base")
            extra_lines.append(
                f"  ↳ {ticker} consensus: net profit ~THB {np_base}bn, "
                f"NIM ~{nim}%, NPL ~{npl}%, interim div est THB {div_base}. "
                f"Advisory: {preview.get('advisory_note_for_tho', '')[:200]}"
            )

    if previews:
        base["previews"] = previews
        base["summary_text"] = base["summary_text"] + "\n" + "\n".join(extra_lines)
    return base


# ---------------------------------------------------------------------------
# Earnings-date validation against the SET statutory filing window
# Added by nightly agent 2026-06-30
#
# Motivation: third-party data vendors (e.g. Yahoo Finance) publish
# ALGORITHMIC "next earnings date" estimates that are frequently wrong for
# SET names. On 2026-06-29 Yahoo listed PTTEP's next earnings as 2026-07-23,
# conflicting with our internal estimate of 2026-08-11. Rather than trust
# either blindly, we reconcile both against two ground-truth anchors:
#   1. The SET statutory rule — a listed company must file reviewed quarterly
#      financials within 45 days of the quarter-end (Q2 ends Jun-30 -> the
#      hard deadline is Aug-14).
#   2. The empirical large-cap reporting band — SET blue-chips historically
#      file ~30-45 days after quarter-end (PTTEP's Q1-2026 landed 2026-05-06,
#      i.e. 36 days after Mar-31).
# A candidate date that falls BEFORE the 30-day empirical floor (Jul-23 = only
# 23 days after Jun-30) is almost certainly a bad vendor auto-estimate; a date
# AFTER the 45-day statutory deadline is legally impossible. This keeps the
# calendar honest without needing a live SET-calendar scrape.
# ---------------------------------------------------------------------------

# Statutory SET filing window for reviewed quarterly financials.
SET_QUARTERLY_FILING_DEADLINE_DAYS = 45
# Empirical band in which SET large-caps actually report (days after quarter-end).
TYPICAL_SET_REPORT_MIN_DAYS = 30
TYPICAL_SET_REPORT_MAX_DAYS = 45

# Known third-party vendor estimates to reconcile against the internal calendar.
# Format: ticker -> {"source": str, "date": ISO-YYYY-MM-DD}. Extend as conflicts
# are spotted; entries are advisory only and never overwrite the calendar.
KNOWN_EXTERNAL_ESTIMATES: dict[str, dict[str, str]] = {
    # Yahoo Finance auto-estimate flagged 2026-06-29 (DEVLOG). 23 days after the
    # Jun-30 quarter-end -> below the 30-day empirical floor -> rejected.
    "PTTEP.BK": {"source": "Yahoo Finance (auto-estimate)", "date": "2026-07-23"},
}


def _infer_quarter_end(report_date: date) -> date:
    """
    Infer the fiscal quarter-end a quarterly report most plausibly covers,
    given the date the report is (or is expected to be) released.

    SET interim results are filed AFTER the quarter closes, so the relevant
    quarter-end is the most recent one strictly before the report month's
    quarter. Mapping by report month:
        Jan-Mar  -> prior-year Dec-31 (FY annual / Q4)
        Apr-Jun  -> Mar-31  (Q1)
        Jul-Sep  -> Jun-30  (Q2 / H1)
        Oct-Dec  -> Sep-30  (Q3)
    """
    y, m = report_date.year, report_date.month
    if m <= 3:
        return date(y - 1, 12, 31)
    if m <= 6:
        return date(y, 3, 31)
    if m <= 9:
        return date(y, 6, 30)
    return date(y, 9, 30)


def _set_filing_deadline(quarter_end: date) -> date:
    """Statutory SET deadline: quarter-end + 45 days."""
    return quarter_end + timedelta(days=SET_QUARTERLY_FILING_DEADLINE_DAYS)


def _classify_report_date(report_date: date) -> dict[str, Any]:
    """
    Classify a single candidate quarterly-report date against the statutory
    deadline and the empirical large-cap reporting band.

    Returns a dict with the inferred quarter-end, the statutory deadline,
    days_after_quarter_end, and a status:
        "implausibly_early"  — on/before the quarter-end (cannot report yet)
        "suspiciously_early" — before the 30-day empirical floor (likely a bad
                               vendor auto-estimate)
        "within_typical_band"— 30-45 days after quarter-end (most credible)
        "late_but_legal"     — 46+ days but on/before... (n/a, see below)
        "breaches_deadline"  — after the 45-day statutory deadline (impossible)
    """
    qe = _infer_quarter_end(report_date)
    deadline = _set_filing_deadline(qe)
    days_after = (report_date - qe).days
    if days_after <= 0:
        status = "implausibly_early"
    elif report_date > deadline:
        status = "breaches_deadline"
    elif days_after < TYPICAL_SET_REPORT_MIN_DAYS:
        status = "suspiciously_early"
    else:  # 30..45 days, on/before deadline
        status = "within_typical_band"
    return {
        "quarter_end": qe.isoformat(),
        "statutory_deadline": deadline.isoformat(),
        "days_after_quarter_end": days_after,
        "status": status,
    }


# ---------------------------------------------------------------------------
# Interim-dividend date validation — Added by nightly agent 2026-07-14
# ---------------------------------------------------------------------------
# An interim dividend cannot go ex-date before the company reports the H1/Q2
# results that declare it, and it normally goes ex within ~3 months of those
# results (SCB's FY2025 final was declared with FY results and went ex ~2-8
# weeks later). We validate a stored interim_dividend_announcement date against
# the quarterly-results event that most plausibly triggers it.
DIVIDEND_MIN_DAYS_AFTER_RESULTS = 0     # ex-date must be strictly after results
DIVIDEND_TYPICAL_MAX_DAYS = 90          # more than ~3 months out = unusually late


def _find_reference_results_date(ticker: str, dividend_date: date) -> date | None:
    """
    Find the quarterly-results event for `ticker` that most plausibly triggers
    an interim dividend with ex-date `dividend_date`: the latest quarterly
    results date on/before the dividend date. Returns None if none found.

    Added by nightly agent 2026-07-14
    """
    candidates: list[date] = []
    for ev in get_earnings_events(ticker):
        if ev.event_type != "quarterly_results":
            continue
        try:
            d = date.fromisoformat(ev.expected_date)
        except ValueError:
            continue
        if d <= dividend_date:
            candidates.append(d)
    return max(candidates) if candidates else None


def _classify_dividend_date(ticker: str, dividend_date: date) -> dict[str, Any]:
    """
    Classify an interim_dividend_announcement date relative to the results
    release that would declare it. A dividend cannot go ex before the company
    reports, and normally goes ex within ~3 months of the H1 results.

    Status:
        "implausibly_before_earnings" — on/before the triggering results date
        "within_typical_window"       — 1..90 days after the results date
        "unusually_late"              — >90 days after the results date
        "no_reference_earnings"       — no prior quarterly event to anchor to

    Added by nightly agent 2026-07-14
    """
    ref = _find_reference_results_date(ticker, dividend_date)
    if ref is None:
        return {
            "reference_results_date": None,
            "days_after_results": None,
            "status": "no_reference_earnings",
        }
    days_after = (dividend_date - ref).days
    if days_after <= DIVIDEND_MIN_DAYS_AFTER_RESULTS:
        status = "implausibly_before_earnings"
    elif days_after > DIVIDEND_TYPICAL_MAX_DAYS:
        status = "unusually_late"
    else:
        status = "within_typical_window"
    return {
        "reference_results_date": ref.isoformat(),
        "days_after_results": days_after,
        "status": status,
    }


def validate_earnings_dates(
    external_dates: dict[str, dict[str, str]] | None = None,
    reference_date: date | None = None,
) -> dict[str, Any]:
    """
    Validate every quarterly-results event in the calendar against the SET
    statutory filing window, and reconcile against any third-party vendor
    estimates (defaults to KNOWN_EXTERNAL_ESTIMATES).

    For each quarterly event this reports the inferred quarter-end, the 45-day
    statutory deadline, how many days after quarter-end the stored date falls,
    and a credibility status. When a conflicting external estimate exists, both
    candidates are scored and a recommendation is emitted (prefer the date that
    sits inside the 30-45 day empirical band; never auto-mutate the calendar).

    Returns:
      {
        "checked_at": iso,
        "results": [ {ticker, expected_date, confirmed, ...classification...,
                      external: {...}|None, reconciliation: str|None}, ... ],
        "issues": [ ...subset of results whose status is not within_typical_band
                    and is not confirmed... ],
        "summary_text": str,   # human-readable for prompt/DEVLOG injection
      }

    Added by nightly agent 2026-06-30
    """
    ext = KNOWN_EXTERNAL_ESTIMATES if external_dates is None else external_dates
    results: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []

    for event in get_earnings_events():
        # Interim-dividend events use their own (results-anchored) validation.
        # Added by nightly agent 2026-07-14
        if event.event_type == "interim_dividend_announcement":
            try:
                dv_date = date.fromisoformat(event.expected_date)
            except ValueError:
                continue
            dcls = _classify_dividend_date(event.ticker, dv_date)
            drow: dict[str, Any] = {
                "ticker": event.ticker,
                "company_name": event.company_name,
                "event_type": "interim_dividend_announcement",
                "expected_date": event.expected_date,
                "confirmed": event.confirmed,
                **dcls,
                "external": None,
                "reconciliation": None,
            }
            results.append(drow)
            # Only an ex-date on/before its triggering earnings is a true bug;
            # "unusually_late"/"no_reference" are informational, not errors.
            if dcls["status"] == "implausibly_before_earnings" and not event.confirmed:
                issues.append(drow)
            continue
        if event.event_type != "quarterly_results":
            continue
        try:
            ev_date = date.fromisoformat(event.expected_date)
        except ValueError:
            continue
        cls = _classify_report_date(ev_date)
        row: dict[str, Any] = {
            "ticker": event.ticker,
            "company_name": event.company_name,
            "event_type": "quarterly_results",
            "expected_date": event.expected_date,
            "confirmed": event.confirmed,
            **cls,
            "external": None,
            "reconciliation": None,
        }

        vendor = ext.get(event.ticker.upper())
        if vendor and vendor.get("date") and vendor["date"] != event.expected_date:
            try:
                vd = date.fromisoformat(vendor["date"])
                vcls = _classify_report_date(vd)
                row["external"] = {"source": vendor.get("source", "external"), **vcls,
                                   "date": vendor["date"]}
                internal_good = cls["status"] == "within_typical_band"
                vendor_good = vcls["status"] == "within_typical_band"
                if internal_good and not vendor_good:
                    row["reconciliation"] = (
                        f"KEEP internal {event.expected_date} "
                        f"({cls['days_after_quarter_end']}d after quarter-end, in the "
                        f"30-45d band); REJECT {vendor.get('source')} {vendor['date']} "
                        f"({vcls['days_after_quarter_end']}d, {vcls['status']})."
                    )
                elif vendor_good and not internal_good:
                    row["reconciliation"] = (
                        f"REVIEW: {vendor.get('source')} {vendor['date']} "
                        f"({vcls['days_after_quarter_end']}d, within band) looks more "
                        f"credible than internal {event.expected_date} "
                        f"({cls['days_after_quarter_end']}d, {cls['status']})."
                    )
                else:
                    row["reconciliation"] = (
                        f"AMBIGUOUS: internal {event.expected_date} ({cls['status']}) vs "
                        f"{vendor.get('source')} {vendor['date']} ({vcls['status']}); "
                        f"confirm on the SET calendar."
                    )
            except ValueError:
                pass

        results.append(row)
        if cls["status"] != "within_typical_band" and not event.confirmed:
            issues.append(row)

    lines = []
    for r in results:
        marker = "✓" if r["confirmed"] else "·"
        # Dividend rows carry different keys than quarterly rows.
        # Added by nightly agent 2026-07-14
        if r.get("event_type") == "interim_dividend_announcement":
            ref = r.get("reference_results_date")
            days = r.get("days_after_results")
            anchor = (
                f"{days}d after results {ref}" if ref is not None
                else "no anchoring results event"
            )
            line = (
                f"{marker} {r['ticker']} [interim dividend]: {r['expected_date']} — "
                f"{r['status']} ({anchor})"
            )
        else:
            line = (
                f"{marker} {r['ticker']}: {r['expected_date']} — {r['status']} "
                f"({r['days_after_quarter_end']}d after {r['quarter_end']}; "
                f"statutory deadline {r['statutory_deadline']})"
            )
        if r["reconciliation"]:
            line += f"\n    ↳ {r['reconciliation']}"
        lines.append(line)
    summary = "Earnings & dividend date validation (SET 45-day window):\n" + "\n".join(lines) \
        if lines else "No results/dividend events to validate."

    if issues:
        logger.warning(
            "Earnings-date validation flagged %d unconfirmed event(s) outside the "
            "typical SET reporting band: %s",
            len(issues),
            [f"{i['ticker']} {i['expected_date']} ({i['status']})" for i in issues],
        )

    return {
        "checked_at": datetime.utcnow().isoformat(),
        "results": results,
        "issues": issues,
        "summary_text": summary,
    }


# ---------------------------------------------------------------------------
# Portfolio-level earnings summary (all events, upcoming first)
# ---------------------------------------------------------------------------

def portfolio_earnings_summary() -> dict[str, Any]:
    """
    Return a full view of all tracked earnings events, grouped by ticker.
    Useful for rendering a calendar widget or populating the watchlist.
    """
    events = get_earnings_events()
    today = date.today()
    upcoming = [e for e in events if date.fromisoformat(e.expected_date) >= today]
    past = [e for e in events if date.fromisoformat(e.expected_date) < today]
    return {
        "total_events": len(events),
        "upcoming": [asdict(e) for e in upcoming],
        "past": [asdict(e) for e in past],
        "generated_at": datetime.utcnow().isoformat(),
    }


# ---------------------------------------------------------------------------
# Seed known earnings events
# ---------------------------------------------------------------------------

def seed_known_earnings() -> None:
    """
    Pre-populate the earnings calendar with known/confirmed events for
    Tho's SET holdings. Safe to call repeatedly (upsert semantics).

    Added by nightly agent 2026-06-13
    """
    # SCB X — Q2/H1-2026 Results (confirmed by SET disclosure)
    add_earnings_event(
        ticker="SCB.BK",
        company_name="SCB X PCL",
        event_type="quarterly_results",
        expected_date="2026-07-17",
        confirmed=True,
        time_of_day="after_close",
        notes=(
            "H1-2026 / Q2-2026 results. Key metrics: net interest margin, "
            "NPL ratio, H1 dividend announcement (est. THB 5.5-6.0/share). "
            "52w range 115-149.50 THB; current 137.50 THB. "
            "Alert window: brief should flag this from 2026-07-14. "
            "REPORTED & RECONCILED 2026-07-24: Q2-2026 net profit THB 11,117m "
            "(+9.0% QoQ, -13.1% YoY); NII THB 27,306m (-10.2% YoY, NIM pressure "
            "from 2025-26 rate cuts); fee/other income THB 11,365m (+14.8% YoY, "
            "wealth); trading income THB 2,552m (+349% QoQ, the QoQ swing); "
            "cost/income 41.3%; NPL 3.17% (improved from 3.23%, BETTER than the "
            "3.3% preview); coverage 158.6%; CAR 18.6%. H1-2026 ~THB 21.3bn is "
            "modestly BELOW the ~22-25bn preview range (NIM-driven), so the "
            "Smartkarma ~12.79bn Q2 preview (flagged as echoing the FY2025 print) "
            "was indeed too high. NO dividend declared with results — interim "
            "expected ~Sep (see interim_dividend_announcement event). Full "
            "reconciliation in data/earnings/scb_q22026_actual.json "
            "(load_earnings_actual('SCB.BK'))."
        ),
    )
    # PTTEP — Q2/H1-2026 results
    # CORRECTED by nightly agent 2026-07-28: the official PTTEP IR calendar
    # (pttep.com/en/investor-relations/calendar) lists the Q2-2026 ANALYST MEETING on
    # 2026-08-03 (10:30-12:00 GMT+7). SET results filings land on/just before the
    # analyst meeting, so the results release is ~Aug-2 (after-close) / Aug-3. This
    # supersedes the 2026-07-25 "Aug-04" seed (SET-sourced via kaohooninternational,
    # which was 1 day late vs the IR calendar). Anchoring to the confirmed Aug-03
    # analyst-meeting date resolves the open PTTEP-date reconciliation flag. Aug-03 is
    # 34 days after the Jun-30 quarter-end (inside the 30-45d SET large-cap band) and
    # still vindicates the 2026-06-30 rejection of Yahoo's 2026-07-23 auto-estimate
    # (23 days, below the empirical floor).
    # REFINED by nightly agent 2026-07-29: an independent source (public.com/MSN
    # earnings pages) corroborates the Q2-2026 RESULTS RELEASE on 2026-08-02, with the
    # analyst meeting following on Aug-03 (IR calendar). Since the actuals-capture and
    # the pre-earnings brief key off the RESULTS FILING (not the meeting), the seed is
    # moved 2026-08-03 -> 2026-08-02 (results release, after-close). Aug-03 analyst
    # meeting retained in the notes. Alert window now opens 2026-07-30.
    add_earnings_event(
        ticker="PTTEP.BK",
        company_name="PTT Exploration and Production PCL",
        event_type="quarterly_results",
        expected_date="2026-08-02",
        confirmed=True,
        time_of_day="after_close",
        notes=(
            "RESULTS RELEASED & CAPTURED 2026-08-02 (nightly agent): Q2 net profit "
            "USD 833m (+104% YoY / +122% QoQ), record 572,882 boe/d, ASP $52.89/boe, "
            "H1 net income THB 39.03bn (+14%), THB 4.50 interim dividend pay Aug-28 — "
            "actuals + reconciliation in data/earnings/pttep_q22026_actual.json. "
            "[Original schedule note retained:] "
            "Q2/H1-2026 results — RESULTS RELEASE 2026-08-02 (after-close), analyst "
            "meeting 2026-08-03 (10:30-12:00 GMT+7) per PTTEP's official IR calendar; "
            "the Aug-02 release is independently corroborated (public.com/MSN earnings, "
            "nightly agent 2026-07-29). Supersedes the earlier Aug-04 (SET-sourced, a "
            "day late) and the Aug-03 meeting-anchored seed. 33 days after the Jun-30 "
            "quarter-end, inside the 30-45d SET large-cap band. Pre-earnings alert "
            "window opens 2026-07-30. Watch: Q2 (Apr-Jun) AVG realised oil (the big "
            "Brent spike was mostly July/Q3, so the Q2 print may be more moderate than "
            "the late-July ~$100 peak; NB Brent has since crashed to ~$85 as the "
            "US-Iran pause drained the premium), record ~560kboe/d production volume, "
            "capex guidance, and any interim dividend. Capture actuals into "
            "data/earnings/pttep_q22026_actual.json (loader wiring already done — brief "
            "auto-surfaces it post-print)."
        ),
    )
    # BAFS — H1-2026 results (estimated; SET usually releases ~Aug)
    add_earnings_event(
        ticker="BAFS.BK",
        company_name="Bangkok Aviation Fuel Services PCL",
        event_type="quarterly_results",
        expected_date="2026-08-14",
        confirmed=False,
        time_of_day="after_close",
        notes=(
            "H1-2026 / Q2-2026 results (estimated). "
            "Key: aviation fuel throughput volume (linked to tourist arrivals), "
            "FY2026 interim dividend announcement expected ~Sep 2026. "
            # Added by nightly agent 2026-08-10 — FALSE-ALARM RETRACTION.
            # The 2026-08-09 run recorded that BAFS "reported ~2026-08-06 and was
            # MISSED" and promoted its retrieval to the highest-value outstanding
            # data task. That was WRONG. The 2026-08-10 run traced the claim to a
            # Thai-language article reporting net profit THB 56m (+29% YoY) with a
            # THB 0.11 interim dividend — figures which belong to Q2/2568 (2025),
            # XD 2025-08-28, not to 2026. Buddhist-era year labelling (2568 = 2025,
            # 2569 = 2026) is the trap, and it is a standing hazard for every Thai
            # source this project reads.
            # Verified 2026-08-10 against two independent points: (1) BAFS IR
            # "Financial Highlights" still headlines Q1/2026 (total revenue THB
            # 991.01m, assets 21,936.84m, liabilities 15,466.91m) as the latest
            # published period; (2) the aio.panphol quarterly grid shows the Q2
            # column for FY2569 empty. BAFS has NOT reported H1-2026 as of
            # 2026-08-10. The original ~Aug-14 estimate is consistent with the
            # 2025 pattern (board approved Q2/2568 in mid-August, XD Aug-28) and
            # is retained. Nothing was missed; do not re-open this chase. "
            "STILL TO CONFIRM: the exact date on the SET/BAFS IR calendar. "
            "Judge the print on THROUGHPUT, not headline margin, and check "
            "whether management attributes anything to the baht."
        ),
    )
    # SCB interim dividend ex-date (estimated, Sep/Oct 2026)
    add_earnings_event(
        ticker="SCB.BK",
        company_name="SCB X PCL",
        event_type="interim_dividend_announcement",
        expected_date="2026-09-15",
        confirmed=False,
        time_of_day="before_open",
        notes=(
            "H1-2026 interim dividend ex-date (estimated Sep 2026). "
            "FY2025 final was THB 5.64/share paid May 7. "
            "Monitor post-Jul-17 earnings announcement for confirmation. "
            "UPDATE 2026-07-24: the Jul-17 Q2 filing did NOT declare an interim "
            "dividend (SCBX historically declares it separately in Aug-Sep; the "
            "FY2025 interim was THB 2.00/share, XD 2025-09-02, paid 2025-09-19). "
            "With H1-2026 profit ~-13% YoY, the 2026 interim will likely be near "
            "THB 2.00 rather than the earlier THB 5.5-6.0 estimate — the ~THB 10-11 "
            "FULL-YEAR payout (vs 11.28 in FY2025) is the right frame for the yield "
            "thesis. Still confirmed=False pending the board declaration."
        ),
    )
    logger.info("Earnings calendar seeded with %d events", 4)


# ---------------------------------------------------------------------------
# Nightly check entry point
# ---------------------------------------------------------------------------

def run_nightly_earnings_check(alert_days: int = 7) -> dict[str, Any]:
    """
    Called by the nightly pipeline. Seeds the calendar if empty, then
    checks for upcoming events and returns a brief context dict.

    alert_days=7 gives 7-day forward look for the nightly report;
    brief_generator uses 3-day window for actionable alerts.
    """
    # Ensure calendar is populated
    if not _EARNINGS_FILE.exists() or len(_load_calendar()) == 0:
        seed_known_earnings()

    alerts_7d = upcoming_earnings_alerts(alert_days=alert_days)
    alerts_3d = upcoming_earnings_alerts(alert_days=3)
    result = {
        "alerts_next_7_days": alerts_7d,
        "alerts_next_3_days": alerts_3d,
        "pre_earnings_brief_context": pre_earnings_brief(alert_days=3),
        # Added by nightly agent 2026-06-14 — consensus-estimate enrichment
        "pre_earnings_brief_enriched": pre_earnings_brief_enriched(alert_days=3),
        "summary": portfolio_earnings_summary(),
        # Added by nightly agent 2026-06-30 — SET statutory-window date validation
        "date_validation": validate_earnings_dates(),
        "checked_at": datetime.utcnow().isoformat(),
    }
    if alerts_3d:
        logger.warning(
            "EARNINGS ALERT: %d event(s) within 3 days — %s",
            len(alerts_3d),
            [f"{a['ticker']} {a['expected_date']}" for a in alerts_3d],
        )
    else:
        logger.info("No earnings events within 3 days. Next 7-day events: %d", len(alerts_7d))
    return result
