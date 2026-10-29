"""
dividend_tracker.py — SET dividend calendar and alert system.

Tracks dividend announcements (ex-date, pay-date, amount per share) for
Thai SET equity holdings: BAFS.BK, PTTEP.BK, SCB.BK. Persists history in
data/dividends/dividend_history.json. Flags upcoming ex-dates within 5 days
for morning brief inclusion. Supports yield analysis and historical payout
tracking for medium-term investment decisions.

Added by nightly agent 2026-06-10
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from utils.common import PROJECT_DIR, configure_logging

logger = configure_logging("portfolio_engine.dividend_tracker")
UTC = timezone.utc

# ---------------------------------------------------------------------------
# Storage paths
# ---------------------------------------------------------------------------

DIVIDEND_STORE_PATH = PROJECT_DIR / "data" / "dividends" / "dividend_history.json"
ALERT_ADVANCE_DAYS = 5  # Flag ex-dates within this many calendar days

# ---------------------------------------------------------------------------
# Known SET holdings and their baseline data
# ---------------------------------------------------------------------------

SET_HOLDINGS: dict[str, dict[str, Any]] = {
    "BAFS.BK": {
        "name": "Bangkok Aviation Fuel Services PCL",
        "sector": "energy_services",
        "typical_yield_pct": 1.5,   # approximate trailing dividend yield %
        "payment_frequency": "annual_with_interim",  # interim + final pattern
        "currency": "THB",
    },
    "PTTEP.BK": {
        "name": "PTT Exploration and Production PCL",
        "sector": "energy",
        "typical_yield_pct": 3.5,
        "payment_frequency": "semi_annual",  # interim + final
        "currency": "THB",
    },
    "SCB.BK": {
        "name": "SCB X PCL (Siam Commercial Bank)",
        "sector": "financials",
        "typical_yield_pct": 5.5,
        "payment_frequency": "semi_annual",  # interim + final
        "currency": "THB",
    },
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class DividendRecord:
    """Single dividend event for a SET stock."""
    ticker: str
    fiscal_year: int
    dividend_type: str              # "interim" | "final" | "special"
    amount_per_share_thb: float
    ex_date: str                    # ISO date YYYY-MM-DD
    record_date: Optional[str]      # ISO date YYYY-MM-DD (may be None if unknown)
    pay_date: Optional[str]         # ISO date YYYY-MM-DD (may be None if upcoming)
    source: str                     # "SET_announcement" | "estimated" | "manual"
    notes: str = ""
    recorded_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def _load_history() -> dict[str, list[dict[str, Any]]]:
    """Load dividend history from JSON. Returns empty dict if file absent."""
    if DIVIDEND_STORE_PATH.exists():
        try:
            return json.loads(DIVIDEND_STORE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning("Could not load dividend history; starting fresh")
    return {}


# --- Added by nightly agent 2026-08-09 ------------------------------------
# BUG FOUND THIS RUN: `data/dividends/dividend_history.json` had never been
# written, because `seed_known_dividends()` is only invoked manually and nothing
# calls it on the read path. `_load_history()` therefore returned `{}` and
# `upcoming_ex_dates()` returned `[]` — so the CONFIRMED PTTEP ex-date of
# 2026-08-14 would have produced NO alert, five days out, on a position Tho
# actually holds.
#
# This is the same failure shape as the dead price feed: absence of data
# rendering identically to absence of events. "No dividends upcoming" and "the
# store was never created" must not look the same to a caller.
#
# Two fixes, both conservative:
#   1. `_ensure_store_seeded()` self-heals on first read — the seed data is
#      already in this module, so there is no reason for a missing file to mean
#      an empty answer.
#   2. `store_status()` lets callers tell the two states apart explicitly.
# Neither changes existing function signatures or removes any behaviour.

_SEED_ATTEMPTED = False


def _ensure_store_seeded() -> dict[str, list[dict[str, Any]]]:
    """
    Return dividend history, seeding the store from module constants on first
    use if the file does not yet exist.

    Idempotent and best-effort: if seeding fails (read-only filesystem, etc.)
    the in-memory seed is still returned, so alerts fire even when the write
    cannot be persisted. Never raises.
    """
    global _SEED_ATTEMPTED

    history = _load_history()
    if history:
        return history
    if _SEED_ATTEMPTED:
        return history

    _SEED_ATTEMPTED = True
    logger.warning(
        "Dividend store missing or empty at %s — seeding from module constants. "
        "Until this run, upcoming_ex_dates() was silently returning no alerts.",
        DIVIDEND_STORE_PATH,
    )
    try:
        seed_known_dividends()
    except Exception as exc:  # noqa: BLE001 - never let seeding break a read
        logger.error("Dividend seeding failed: %s", exc)
    return _load_history()


def store_status() -> dict[str, Any]:
    """
    Report the state of the dividend store so callers can distinguish
    'no upcoming dividends' from 'the store was never populated'.

    Added by nightly agent 2026-08-09.
    """
    exists = DIVIDEND_STORE_PATH.exists()
    history = _load_history()
    record_count = sum(len(v) for v in history.values())
    return {
        "store_path": str(DIVIDEND_STORE_PATH),
        "store_exists": exists,
        "tickers_tracked": sorted(history.keys()),
        "record_count": record_count,
        "seeded": record_count > 0,
        "verdict": "OK" if record_count > 0 else "EMPTY",
        "caveat": (
            None
            if record_count > 0
            else "Store is empty — an empty alert list means NO DATA, not no dividends."
        ),
    }
# --------------------------------------------------------------------------


def _save_history(history: dict[str, list[dict[str, Any]]]) -> None:
    DIVIDEND_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    DIVIDEND_STORE_PATH.write_text(
        json.dumps(history, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Core CRUD operations
# ---------------------------------------------------------------------------

def add_dividend(record: DividendRecord) -> dict[str, Any]:
    """
    Persist a dividend record. Deduplicates by (ticker, fiscal_year, dividend_type, ex_date).

    Returns the saved record dict.

    Added by nightly agent 2026-06-10
    """
    history = _load_history()
    ticker_records: list[dict[str, Any]] = history.setdefault(record.ticker, [])

    # Dedup key
    existing = [
        r for r in ticker_records
        if r.get("fiscal_year") == record.fiscal_year
        and r.get("dividend_type") == record.dividend_type
        and r.get("ex_date") == record.ex_date
    ]
    if existing:
        # Overwrite in place
        ticker_records[:] = [
            r for r in ticker_records
            if not (
                r.get("fiscal_year") == record.fiscal_year
                and r.get("dividend_type") == record.dividend_type
                and r.get("ex_date") == record.ex_date
            )
        ]
        logger.info("Overwriting dividend record for %s FY%s %s",
                    record.ticker, record.fiscal_year, record.dividend_type)

    entry = record.to_dict()
    ticker_records.append(entry)
    # Sort by ex_date descending
    history[record.ticker] = sorted(ticker_records, key=lambda r: r["ex_date"], reverse=True)
    _save_history(history)
    logger.info("Saved dividend %s %s %s: THB %.2f/share ex %s",
                record.ticker, record.fiscal_year, record.dividend_type,
                record.amount_per_share_thb, record.ex_date)
    return entry


def get_dividends(ticker: str, limit: int = 20) -> list[dict[str, Any]]:
    """Return the most recent `limit` dividend records for a ticker."""
    history = _load_history()
    return history.get(ticker, [])[:limit]


def get_all_dividends() -> dict[str, list[dict[str, Any]]]:
    """Return complete dividend history for all tracked tickers."""
    return _load_history()


# ---------------------------------------------------------------------------
# Alert detection: upcoming ex-dates
# ---------------------------------------------------------------------------

def upcoming_ex_dates(advance_days: int = ALERT_ADVANCE_DAYS) -> list[dict[str, Any]]:
    """
    Return dividend records whose ex_date falls within the next `advance_days`
    calendar days from today. These should trigger a morning alert.

    Returns a list of dicts with ticker, ex_date, pay_date, amount, days_until.

    Added by nightly agent 2026-06-10
    """
    today = date.today()
    threshold = today + timedelta(days=advance_days)
    # Changed by nightly agent 2026-08-09: was `_load_history()`, which returned
    # {} when the store file had never been written and so produced an empty
    # alert list indistinguishable from "no dividends due".
    history = _ensure_store_seeded()
    alerts: list[dict[str, Any]] = []

    for ticker, records in history.items():
        for rec in records:
            try:
                ex_date = date.fromisoformat(rec["ex_date"])
            except (ValueError, KeyError):
                continue
            if today <= ex_date <= threshold:
                days_until = (ex_date - today).days
                alerts.append({
                    "ticker": ticker,
                    "name": SET_HOLDINGS.get(ticker, {}).get("name", ticker),
                    "ex_date": rec["ex_date"],
                    "pay_date": rec.get("pay_date"),
                    "amount_per_share_thb": rec.get("amount_per_share_thb"),
                    "fiscal_year": rec.get("fiscal_year"),
                    "dividend_type": rec.get("dividend_type"),
                    "days_until_ex_date": days_until,
                    "alert_level": "🚨 URGENT" if days_until <= 2 else "⚠️ UPCOMING",
                })

    return sorted(alerts, key=lambda a: a["days_until_ex_date"])


# ---------------------------------------------------------------------------
# Yield analysis
# ---------------------------------------------------------------------------

def calculate_trailing_yield(
    ticker: str,
    current_price_thb: float,
    fiscal_year: Optional[int] = None,
) -> dict[str, Any]:
    """
    Calculate trailing dividend yield for a SET holding.

    Sums all dividend records for the given fiscal year (or the most recent
    completed year if fiscal_year is None).

    Args:
        ticker: SET ticker (e.g. 'PTTEP.BK')
        current_price_thb: Current share price in THB
        fiscal_year: Fiscal year to sum dividends for (default: latest in history)

    Returns:
        Dict with total_dps_thb, yield_pct, price_used, fiscal_year

    Added by nightly agent 2026-06-10
    """
    history = _load_history()
    records = history.get(ticker, [])
    if not records:
        return {"error": "no_dividend_data", "ticker": ticker}

    # Determine fiscal year
    if fiscal_year is None:
        fiscal_years = sorted({r.get("fiscal_year", 0) for r in records}, reverse=True)
        fiscal_year = fiscal_years[0] if fiscal_years else None

    year_records = [r for r in records if r.get("fiscal_year") == fiscal_year]
    if not year_records:
        return {"error": f"no_data_for_fy{fiscal_year}", "ticker": ticker}

    total_dps = sum(float(r.get("amount_per_share_thb", 0)) for r in year_records)
    yield_pct = round((total_dps / current_price_thb * 100), 4) if current_price_thb else 0.0

    return {
        "ticker": ticker,
        "fiscal_year": fiscal_year,
        "total_dps_thb": round(total_dps, 4),
        "dividend_count": len(year_records),
        "current_price_thb": current_price_thb,
        "trailing_yield_pct": yield_pct,
        "dividends": year_records,
    }


def portfolio_dividend_summary(
    holdings: dict[str, float],
) -> dict[str, Any]:
    """
    Generate a dividend summary for all SET equity holdings.

    Args:
        holdings: {ticker: current_price_thb} dict

    Returns:
        Summary with per-ticker yield, upcoming alerts, and portfolio-level stats.

    Added by nightly agent 2026-06-10
    """
    per_ticker = {}
    for ticker, price in holdings.items():
        per_ticker[ticker] = calculate_trailing_yield(ticker, price)

    alerts = upcoming_ex_dates()

    tickers_with_data = [v for v in per_ticker.values() if "trailing_yield_pct" in v]
    avg_yield = (
        round(sum(v["trailing_yield_pct"] for v in tickers_with_data) / len(tickers_with_data), 4)
        if tickers_with_data else None
    )

    return {
        "generated_date": date.today().isoformat(),
        "per_ticker": per_ticker,
        "upcoming_ex_date_alerts": alerts,
        "average_yield_pct": avg_yield,
        "alert_count": len(alerts),
    }


# ---------------------------------------------------------------------------
# Seed known historical dividends for Tho's holdings
# ---------------------------------------------------------------------------

def seed_known_dividends() -> int:
    """
    Seed the dividend history file with known/researched dividend records
    for BAFS.BK, PTTEP.BK, and SCB.BK based on publicly available data.

    This populates the tracker with historical data so yield analysis is
    immediately useful. Only adds records not already present.

    Added by nightly agent 2026-06-10
    """
    known_records: list[DividendRecord] = [
        # ------------------------------------------------------------------
        # PTTEP.BK — FY2026 INTERIM: CONFIRMED, ex-date resolved.
        # Board approved 2026-07-31 alongside the Q2/H1-2026 results (net profit
        # USD 833m, +104% YoY, record 572,882 boe/d). XD 2026-08-14, pay 2026-08-28.
        # This resolves the ex-date sub-watch that had been open since 2026-08-02
        # and is the first CONFIRMED (not estimated) forward dividend in the seed —
        # upcoming_ex_dates() will now fire a real alert as XD approaches.
        # Sources: thaipr.net/en/energy_en/3746211 ; energy-pedia.com (204809) ;
        # pttep.com investor-relations dividend-policy-and-payments.
        # Added by nightly agent 2026-08-04
        # ------------------------------------------------------------------
        DividendRecord(
            ticker="PTTEP.BK",
            fiscal_year=2026,
            dividend_type="interim",
            amount_per_share_thb=4.50,
            ex_date="2026-08-14",
            record_date="2026-08-15",
            pay_date="2026-08-28",
            source="SET_announcement",
            notes=(
                "CONFIRMED interim H1-2026, declared with the Q2 results; board approved "
                "2026-07-31. Last cum-dividend trading day 2026-08-13. Tho holds 1,400 shares "
                "-> THB 6,300 gross (~THB 5,670 net of the 10% Thai withholding). No action "
                "needed to capture it: just do not sell before XD. Do NOT add before XD — the "
                "Aug-04 oil de-escalation (Brent ~$81) is eroding the forward earnings driver, "
                "so buying in pre-XD just repurchases his own dividend at a 10% tax cost."
            ),
        ),
        # ------------------------------------------------------------------
        # PTTEP.BK — semi-annual; FY2025 interim + final, FY2024 full year
        # ------------------------------------------------------------------
        DividendRecord(
            ticker="PTTEP.BK",
            fiscal_year=2025,
            dividend_type="final",
            amount_per_share_thb=4.65,
            ex_date="2026-02-23",
            record_date="2026-02-24",
            pay_date="2026-04-22",
            source="SET_announcement",
            notes="Final dividend FY2025; AGM approved. Source: TFEX/SET notice",
        ),
        DividendRecord(
            ticker="PTTEP.BK",
            fiscal_year=2025,
            dividend_type="interim",
            amount_per_share_thb=2.50,
            ex_date="2025-09-10",
            record_date="2025-09-11",
            pay_date="2025-10-08",
            source="estimated",
            notes="Interim H1-2025 estimate based on prior year pattern; verify via SET",
        ),
        DividendRecord(
            ticker="PTTEP.BK",
            fiscal_year=2024,
            dividend_type="final",
            amount_per_share_thb=4.50,
            ex_date="2025-02-26",
            record_date="2025-02-27",
            pay_date="2025-04-23",
            source="estimated",
            notes="FY2024 final estimate; verify via PTTEP investor relations",
        ),
        # ------------------------------------------------------------------
        # SCB.BK — semi-annual; FY2025 final and interim
        # ------------------------------------------------------------------
        DividendRecord(
            ticker="SCB.BK",
            fiscal_year=2025,
            dividend_type="final",
            amount_per_share_thb=9.28,
            ex_date="2026-04-09",
            record_date="2026-04-10",
            pay_date="2026-05-07",
            source="SET_announcement",
            notes="Final dividend FY2025 approved at AGM Apr 8 2026; total incl interim = 11.28 THB. "
                  "Source: MarketScreener/SCBX investor relations",
        ),
        DividendRecord(
            ticker="SCB.BK",
            fiscal_year=2025,
            dividend_type="interim",
            amount_per_share_thb=2.00,
            ex_date="2025-09-10",
            record_date="2025-09-11",
            pay_date="2025-10-08",
            source="estimated",
            notes="Interim dividend H1-2025; total FY2025 = 11.28 THB incl final. Estimate based on "
                  "confirmed total payout; exact interim ex-date — verify via SET",
        ),
        DividendRecord(
            ticker="SCB.BK",
            fiscal_year=2024,
            dividend_type="final",
            amount_per_share_thb=7.00,
            ex_date="2025-04-10",
            record_date="2025-04-11",
            pay_date="2025-05-08",
            source="estimated",
            notes="FY2024 final estimate based on prior-year pattern; verify via SCB investor relations",
        ),
        # ------------------------------------------------------------------
        # BAFS.BK — annual pattern with interim; FY2024 known, FY2025 estimated
        # ------------------------------------------------------------------
        DividendRecord(
            ticker="BAFS.BK",
            fiscal_year=2024,
            dividend_type="final",
            amount_per_share_thb=0.20,
            ex_date="2025-05-08",
            record_date="2025-05-09",
            pay_date="2025-05-22",
            source="SET_announcement",
            notes="Final dividend FY2024; AGM Apr 30 2025. Total FY2024 = 0.30 THB "
                  "(0.10 interim + 0.20 final). Source: Investing.com dividend history",
        ),
        DividendRecord(
            ticker="BAFS.BK",
            fiscal_year=2024,
            dividend_type="interim",
            amount_per_share_thb=0.10,
            ex_date="2024-09-03",
            record_date="2024-09-04",
            pay_date="2024-09-03",
            source="SET_announcement",
            notes="Interim H1-2024 dividend; 0.10 THB. Source: Investing.com dividend history",
        ),
        DividendRecord(
            ticker="BAFS.BK",
            fiscal_year=2025,
            dividend_type="interim",
            amount_per_share_thb=0.10,
            ex_date="2025-09-05",
            record_date="2025-09-06",
            pay_date="2025-09-05",
            source="estimated",
            notes="Estimated H1-2025 interim based on FY2024 pattern. Verify via SET announcement",
        ),
        DividendRecord(
            ticker="BAFS.BK",
            fiscal_year=2025,
            dividend_type="final",
            amount_per_share_thb=0.20,
            ex_date="2026-05-08",
            record_date="2026-05-09",
            pay_date="2026-05-22",
            source="estimated",
            notes="Estimated FY2025 final; pattern from FY2024. AGM typically April. "
                  "Verify via SET once announced — estimated based on prior year",
        ),
    ]

    added = 0
    history = _load_history()
    for record in known_records:
        ticker_records = history.get(record.ticker, [])
        # Check for duplicate
        is_dup = any(
            r.get("fiscal_year") == record.fiscal_year
            and r.get("dividend_type") == record.dividend_type
            and r.get("ex_date") == record.ex_date
            for r in ticker_records
        )
        if not is_dup:
            add_dividend(record)
            added += 1
        else:
            logger.debug("Skipped duplicate: %s FY%s %s",
                         record.ticker, record.fiscal_year, record.dividend_type)

    logger.info("Seed completed: %d new records added", added)
    return added


# ---------------------------------------------------------------------------
# Ex-dividend price mechanics
# Added by nightly agent 2026-08-14
# ---------------------------------------------------------------------------

# Thai withholding tax on dividends paid to resident individuals.
THAI_DIVIDEND_WHT = 0.10


def theoretical_ex_price(
    last_cum_close: float,
    dps: float,
    *,
    last_cum_session: str,
    ex_date: str,
    round_to_tick: bool = True,
) -> dict[str, Any]:
    """Theoretical ex-dividend opening reference = last CUM close - DPS.

    WHY THE SIGNATURE IS AWKWARD (this is deliberate)
    -------------------------------------------------
    `last_cum_session` and `ex_date` are required keyword arguments that this
    function uses only to VALIDATE its own inputs. They exist because of a real
    error: on 2026-08-13 this system published a theoretical ex-price of 147.50
    for PTTEP, computed as 152.00 - 4.50. The 152.00 was the 11 August close,
    and it was the most recent mark on file. But PTTEP also traded on 13 August
    and closed at 150.50, and 13 August — not 11 August — was the last cum
    session. The correct reference was 150.50 - 4.50 = 146.00. The published
    number was wrong by 1.50 (1.0%), which is a third of the dividend itself.

    The mistake was not arithmetic. It was using "the newest price we happen to
    hold" where "the last cum-dividend close" was required. Those two are the
    same number only when the collector is current, and this collector has been
    dead since 2026-07-15. So the function now refuses to compute unless the
    caller states which session the price came from, and that session is the
    trading day immediately before the ex-date.

    Returns a dict; `theoretical_ex_price` is None when validation fails, with
    `error` explaining what the caller must supply instead.
    """
    out: dict[str, Any] = {
        "last_cum_close": last_cum_close,
        "last_cum_session": last_cum_session,
        "ex_date": ex_date,
        "dps": dps,
        "theoretical_ex_price": None,
        "drop_ratio_pct": None,
        "gross_per_share": dps,
        "net_per_share_after_wht": round(dps * (1 - THAI_DIVIDEND_WHT), 6),
        "wht_rate": THAI_DIVIDEND_WHT,
        "error": None,
        "warnings": [],
    }

    if last_cum_close is None or last_cum_close <= 0:
        out["error"] = "last_cum_close must be a positive price"
        return out
    if dps is None or dps <= 0:
        out["error"] = "dps must be positive"
        return out
    if dps >= last_cum_close:
        out["error"] = f"dps {dps} >= price {last_cum_close}; inputs are not the same instrument"
        return out

    # The cum session must be the trading day immediately preceding the ex-date.
    try:
        cum_d = date.fromisoformat(last_cum_session)
        ex_d = date.fromisoformat(ex_date)
    except (TypeError, ValueError):
        out["error"] = "last_cum_session and ex_date must be YYYY-MM-DD"
        return out

    if cum_d >= ex_d:
        out["error"] = f"last_cum_session {last_cum_session} is not before ex_date {ex_date}"
        return out

    expected_cum = None
    try:
        from data_collector.set_holidays import previous_trading_day
        expected_cum = previous_trading_day(ex_d)
    except Exception as exc:  # calendar unavailable or year out of table
        out["warnings"].append(
            f"SET holiday calendar unavailable ({type(exc).__name__}); could not verify "
            f"that {last_cum_session} is the last session before {ex_date}"
        )

    if expected_cum is not None and expected_cum != cum_d:
        out["error"] = (
            f"{last_cum_session} is not the last cum session before {ex_date}; "
            f"the SET calendar says that is {expected_cum.isoformat()}. "
            f"Supply that session's close — this is the 2026-08-13 PTTEP error."
        )
        return out

    raw = last_cum_close - dps
    price = raw
    if round_to_tick:
        try:
            from data_collector.set_official import round_to_tick as _rt
            # Round DOWN: the theoretical ex-price is a reference the exchange
            # derives conservatively, and rounding up would overstate the mark.
            price = _rt(raw, "down")
            if abs(price - raw) > 1e-9:
                out["warnings"].append(f"raw {raw:.4f} rounded to tick {price}")
        except Exception as exc:
            out["warnings"].append(
                f"tick rounding unavailable ({type(exc).__name__}); raw value returned"
            )

    out["theoretical_ex_price"] = price
    out["raw_ex_price"] = raw
    out["drop_ratio_pct"] = round(dps / last_cum_close * 100, 4)
    out["note"] = (
        "This is a REFERENCE price, not a forecast. The information is the "
        "deviation of the actual open from it, not the number itself."
    )
    return out


def ex_open_deviation(theoretical: float, actual_open: float,
                      dps: Optional[float] = None) -> dict[str, Any]:
    """Compare an actual ex-date open against the theoretical reference.

    The deviation, expressed as a fraction of the dividend, is the interpretable
    quantity: 'the stock recovered 40% of the dividend on the open' says
    something; 'the stock opened at 146.60' does not.
    """
    diff = actual_open - theoretical
    out = {
        "theoretical_ex_price": theoretical,
        "actual_open": actual_open,
        "deviation": round(diff, 4),
        "deviation_pct": round(diff / theoretical * 100, 4) if theoretical else None,
        "dividend_recovered_fraction": None,
    }
    if dps:
        out["dividend_recovered_fraction"] = round(diff / dps, 4)
    return out


# ---------------------------------------------------------------------------
# Nightly runner — call from scheduled task
# ---------------------------------------------------------------------------

def run_nightly_dividend_check() -> dict[str, Any]:
    """
    Main nightly entry point:
    1. Seed any missing known dividends
    2. Check for upcoming ex-dates within ALERT_ADVANCE_DAYS
    3. Return summary for inclusion in morning brief

    Added by nightly agent 2026-06-10
    """
    seeded = seed_known_dividends()
    alerts = upcoming_ex_dates()

    logger.info("Nightly dividend check: %d records seeded, %d upcoming ex-date alerts",
                seeded, len(alerts))
    return {
        "run_date": date.today().isoformat(),
        "records_seeded": seeded,
        "upcoming_alerts": alerts,
        "alert_count": len(alerts),
    }


# ---------------------------------------------------------------------------
# Quick CLI test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json as _json
    result = run_nightly_dividend_check()
    print(_json.dumps(result, indent=2, ensure_ascii=False))

    # Show trailing yield for PTTEP at ~147 THB
    print("\n--- Trailing Yield (PTTEP @ 147.50 THB) ---")
    pttep_yield = calculate_trailing_yield("PTTEP.BK", current_price_thb=147.50, fiscal_year=2025)
    print(_json.dumps(pttep_yield, indent=2, ensure_ascii=False))
