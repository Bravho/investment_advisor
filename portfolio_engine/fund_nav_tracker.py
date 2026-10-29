"""
fund_nav_tracker.py — Mutual fund NAV fetcher and tracker for Thai open-end funds.

Fetches NAV for SCBAM gold and equity funds from public sources and persists
them in the local data/snapshots directory for trend analysis and fee drag
calculations. Supports both hedged and unhedged gold fund variants.

Added by nightly agent 2026-06-08
"""

import json
import os
from datetime import date, datetime, timezone, timedelta

MAX_NAV_AGE_DAYS = 7  # Tho standing rule 2026-10-07
from pathlib import Path
from typing import Any, Optional

from utils.common import PROJECT_DIR, configure_logging

logger = configure_logging("portfolio_engine.fund_nav")
UTC = timezone.utc

# ---------------------------------------------------------------------------
# Fund registry — map short name → SCBAM fund code (for URL construction)
# ---------------------------------------------------------------------------
FUND_REGISTRY: dict[str, dict[str, str]] = {
    "SCBGOLDE": {
        "name": "SCB Gold Open End Fund (E-channel)",
        "url": "https://www.scbam.com/en/fund/default/fund-information/scbgolde",
        "currency": "THB",
        "underlying": "XAU/USD",
        "ter_pct": 0.50,   # approximate TER % per annum
    },
    "SCBGOLDHE": {
        "name": "SCB Gold THB Hedged Open End Fund (E-channel)",
        "url": "https://www.scbam.com/en/fund/default/fund-information/scbgoldhe",
        "currency": "THB",
        "underlying": "XAU/USD (THB hedged)",
        "ter_pct": 0.65,   # hedged funds typically carry slightly higher TER
    },
    "SCBGOLDH": {
        "name": "SCB Gold THB Hedged Open End Fund (Accumulation)",
        "url": "https://www.scbam.com/en/fund/default/fund-information/scbgoldh",
        "currency": "THB",
        "underlying": "XAU/USD (THB hedged)",
        "ter_pct": 0.65,
    },
}

NAV_STORE_PATH = PROJECT_DIR / "data" / "snapshots" / "fund_nav_history.json"


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def _load_nav_history() -> dict[str, list[dict[str, Any]]]:
    """Load the persisted NAV history JSON; return empty dict if not found."""
    if NAV_STORE_PATH.exists():
        try:
            return json.loads(NAV_STORE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning("Could not read NAV history; starting fresh")
    return {}


def _save_nav_history(history: dict[str, list[dict[str, Any]]]) -> None:
    NAV_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    NAV_STORE_PATH.write_text(
        json.dumps(history, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# NAV fetching — uses yfinance as a proxy via gold spot price when direct
# scraping is unavailable, and stores a manual-entry fallback path.
# ---------------------------------------------------------------------------

def estimate_nav_from_gold(
    gold_price_usd: float,
    usd_thb_rate: float,
    hedged: bool = False,
    units_per_gram: float = 0.00003215,  # 1 troy oz = 31.1035 g; NAV often quoted per unit ~1g
    hedge_ref_rate: Optional[float] = None,
) -> float:
    """
    Estimate fund NAV (THB per unit) from gold spot price.

    For UNHEDGED funds (e.g. SCBGOLDE):
        NAV ≈ gold_usd × usd_thb × units_per_gram
        — NAV moves with BOTH gold and the live USD/THB rate.

    For THB-HEDGED funds (e.g. SCBGOLDHE / SCBGOLDH):
        NAV ≈ gold_usd × hedge_ref_rate × units_per_gram
        — the FX exposure is hedged back to a fixed reference rate, so NAV
        tracks gold moves ONLY and is (approximately) insensitive to USD/THB.
        Using the live rate here would be wrong: it would double-count an FX
        move the fund has explicitly hedged away.

    Fixed 2026-06-22 by nightly agent: previously the ``hedged`` flag was
    accepted but ignored — hedged and unhedged NAVs were computed identically,
    so the SCBGOLDHE series spuriously moved with the baht. The hedge reference
    rate is now applied (param ``hedge_ref_rate`` → env ``GOLD_HEDGE_REF_RATE``
    → default 32.5, a neutral mid-band rate), isolating the gold component.

    Parameters
    ----------
    gold_price_usd : float
        Gold spot price in USD per troy ounce.
    usd_thb_rate : float
        Live USD/THB rate (used only for the unhedged convention).
    hedged : bool
        If True, applies the THB-hedged convention (fixed reference rate).
    units_per_gram : float
        Typical Thai gold fund: 1 unit ≈ tiny fraction of oz → ~0.00003215 (SCBGOLDE ~4 THB/unit)
    hedge_ref_rate : float, optional
        The rate the fund hedges its USD exposure to. Defaults to env
        ``GOLD_HEDGE_REF_RATE`` or 32.5. Ignored for unhedged funds.

    Returns
    -------
    float
        Estimated NAV in THB per unit.
    """
    if hedged:
        ref = hedge_ref_rate
        if ref is None:
            ref = float(os.getenv("GOLD_HEDGE_REF_RATE", "32.5"))
        return round(gold_price_usd * ref * units_per_gram, 4)
    return round(gold_price_usd * usd_thb_rate * units_per_gram, 4)


def record_nav_entry(
    fund_code: str,
    nav_thb: float,
    nav_date: Optional[date] = None,
    source: str = "estimated",
    gold_price_usd: Optional[float] = None,
    usd_thb_rate: Optional[float] = None,
) -> dict[str, Any]:
    """
    Record a NAV data point for a fund. Appends to the persistent history file.

    Parameters
    ----------
    fund_code : str
        One of the keys in FUND_REGISTRY (e.g. "SCBGOLDE").
    nav_thb : float
        NAV value in THB per unit.
    nav_date : date, optional
        Date of the NAV; defaults to today.
    source : str
        How the NAV was obtained: "official", "estimated", "manual".
    gold_price_usd : float, optional
        Gold price used for estimation (stored for audit trail).
    usd_thb_rate : float, optional
        FX rate used for estimation.

    Returns
    -------
    dict
        The NAV record that was saved.
    """
    if fund_code not in FUND_REGISTRY:
        raise ValueError(f"Unknown fund code '{fund_code}'. Known: {list(FUND_REGISTRY)}")

    entry: dict[str, Any] = {
        "date": str(nav_date or date.today()),
        "nav_thb": nav_thb,
        "source": source,
        "recorded_at": datetime.now(UTC).isoformat(),
    }
    if gold_price_usd is not None:
        entry["gold_price_usd"] = gold_price_usd
    if usd_thb_rate is not None:
        entry["usd_thb_rate"] = usd_thb_rate

    history = _load_nav_history()
    records = history.setdefault(fund_code, [])

    # Avoid duplicate entries for the same date
    existing_dates = {r["date"] for r in records}
    if entry["date"] in existing_dates:
        logger.info("NAV for %s on %s already recorded; overwriting", fund_code, entry["date"])
        records[:] = [r for r in records if r["date"] != entry["date"]]

    records.append(entry)
    # Keep only last 365 data points per fund
    history[fund_code] = sorted(records, key=lambda r: r["date"])[-365:]
    _save_nav_history(history)
    logger.info("Saved NAV for %s: THB %.4f (%s)", fund_code, nav_thb, source)
    return entry


# ---------------------------------------------------------------------------
# Analysis helpers
# ---------------------------------------------------------------------------

def get_nav_history(fund_code: str, days: int = 90) -> list[dict[str, Any]]:
    """Return the last `days` NAV records for a fund."""
    history = _load_nav_history()
    records = history.get(fund_code, [])
    return records[-days:]


def calculate_fund_return(fund_code: str, days: int = 90) -> dict[str, Any]:
    """
    Calculate the return of a fund over the last `days` using stored NAV history.

    Returns a dict with start_nav, end_nav, return_pct, period_days.
    """
    records = get_nav_history(fund_code, days)
    if len(records) < 2:
        return {"fund_code": fund_code, "error": "insufficient_data", "records_found": len(records)}
    start = float(records[0]["nav_thb"])
    end = float(records[-1]["nav_thb"])
    return_pct = round((end - start) / start * 100, 4) if start else 0.0
    return {
        "fund_code": fund_code,
        "fund_name": FUND_REGISTRY.get(fund_code, {}).get("name", fund_code),
        "start_date": records[0]["date"],
        "end_date": records[-1]["date"],
        "start_nav_thb": start,
        "end_nav_thb": end,
        "return_pct": return_pct,
        "records_used": len(records),
    }


def calculate_fee_drag(
    fund_code: str,
    position_value_thb: float,
    holding_years: float = 1.0,
) -> dict[str, Any]:
    """
    Estimate the annual management fee drag for a fund position.

    Parameters
    ----------
    fund_code : str
        Fund code from FUND_REGISTRY.
    position_value_thb : float
        Current market value of the position in THB.
    holding_years : float
        Expected holding period in years (default 1.0).

    Returns
    -------
    dict
        Fee drag analysis including annual cost and comparison to ETF alternatives.
    """
    info = FUND_REGISTRY.get(fund_code)
    if not info:
        return {"error": f"Unknown fund code '{fund_code}'"}

    ter_pct = info["ter_pct"]
    annual_fee_thb = round(position_value_thb * ter_pct / 100, 2)
    total_fee_thb = round(annual_fee_thb * holding_years, 2)

    # ETF alternatives for comparison (approximate TER)
    etf_alternatives = {
        "GLD (SPDR Gold ETF)": 0.40,
        "IAU (iShares Gold ETF)": 0.25,
        "SGOL (Aberdeen Gold ETF)": 0.17,
    }
    savings = {
        etf: round((ter_pct - etf_ter) / 100 * position_value_thb * holding_years, 2)
        for etf, etf_ter in etf_alternatives.items()
        if ter_pct > etf_ter
    }

    return {
        "fund_code": fund_code,
        "fund_name": info["name"],
        "ter_pct": ter_pct,
        "position_value_thb": position_value_thb,
        "annual_fee_thb": annual_fee_thb,
        "total_fee_thb_over_period": total_fee_thb,
        "holding_years": holding_years,
        "etf_fee_savings_if_switched": savings,
        "note": "TER is approximate; verify at scbam.com for exact current figure",
    }


# ---------------------------------------------------------------------------
# Snapshot runner — call this nightly to record today's estimated NAV
# ---------------------------------------------------------------------------




def fetch_official_nav(fund_code: str = "SCBGOLDE") -> Optional[dict[str, Any]]:
    """Fetch official NAV/unit from reliable public sources (not gold×FX estimate).

    Priority:
      1) SETTRADE mutual-fund overview (embeds navPerUnit history)
      2) SET.or.th fund quote page (best-effort regex)
      3) SCBAM fund page (best-effort; often JS-shell with no embedded NAV)

    Returns {date, nav_thb, source, source_url} or None.
    """
    import re
    import urllib.request

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
        "Accept-Language": "th-TH,th;q=0.9,en;q=0.8",
    }

    def _get(url: str) -> str:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.read().decode("utf-8", "replace")

    # 1) SETTRADE — known-good official-ish publish of daily NAV
    settrade_url = f"https://www.settrade.com/th/mutualfund/quote/{fund_code}/overview"
    try:
        html = _get(settrade_url)
        pts = re.findall(r'date:"([^"]+)",navPerUnit:([0-9]+\.[0-9]+)', html)
        if pts:
            d, nav = sorted(((x, float(y)) for x, y in pts), key=lambda t: t[0])[-1]
            nav_date = date.fromisoformat(d[:10])
            age_days = (date.today() - nav_date).days
            return {
                "date": d[:10],
                "nav_thb": float(nav),
                "source": "settrade_official",
                "source_url": settrade_url,
                "age_days": age_days,
                "stale": age_days > MAX_NAV_AGE_DAYS,
            }
    except Exception as exc:
        logger.warning("SETTRADE NAV fetch failed for %s: %s", fund_code, exc)

    # 2) SET.or.th fund quote
    set_url = f"https://www.set.or.th/en/market/product/fund/quote/{fund_code}/price"
    try:
        html = _get(set_url)
        pts = re.findall(r'navPerUnit["\']?\s*[:=]\s*([0-9]+\.[0-9]+)', html)
        if pts:
            return {
                "date": date.today().isoformat(),
                "nav_thb": float(pts[-1]),
                "source": "set_or_th",
                "source_url": set_url,
            }
    except Exception as exc:
        logger.warning("SET.or.th NAV fetch failed for %s: %s", fund_code, exc)

    # 3) SCBAM page — often empty shell; attempt embedded numbers near NAV
    for scbam_url in (
        f"https://www.scbam.com/en/fund/default/fund-information/{fund_code.lower()}",
        f"https://www.scbam.com/th/fund/default/fund-information/{fund_code.lower()}",
    ):
        try:
            html = _get(scbam_url)
            nums = re.findall(
                r'(?:NAV|navPerUnit|มูลค่าหน่วยลงทุน)[^0-9]{0,40}([0-9]{1,3}\.[0-9]{2,4})',
                html,
                flags=re.I,
            )
            if nums:
                return {
                    "date": date.today().isoformat(),
                    "nav_thb": float(nums[0]),
                    "source": "scbam_page",
                    "source_url": scbam_url,
                }
        except Exception as exc:
            logger.warning("SCBAM NAV fetch failed for %s: %s", fund_code, exc)

    return None


def fetch_settrade_nav(fund_code: str = "SCBGOLDE") -> Optional[dict[str, Any]]:
    """Backward-compatible alias — prefers multi-source official fetch."""
    return fetch_official_nav(fund_code)


def run_nightly_nav_snapshot(
    gold_price_usd: float = 4500.0,
    usd_thb_rate: float = 32.94,
) -> list[dict[str, Any]]:
    """
    Record estimated NAVs for all tracked gold funds using tonight's prices.

    Call with current gold price and USD/THB rate. Falls back to defaults
    based on June 2026 market data if arguments are omitted.

    Added by nightly agent 2026-06-08
    """
    results = []
    hedge_ref_rate = float(os.getenv("GOLD_HEDGE_REF_RATE", "32.5"))
    for fund_code, info in FUND_REGISTRY.items():
        hedged = "hedged" in info.get("name", "").lower()
        official = fetch_official_nav(fund_code) if fund_code == "SCBGOLDE" else None
        if official is not None:
            entry = record_nav_entry(
                fund_code=fund_code,
                nav_thb=float(official["nav_thb"]),
                nav_date=date.fromisoformat(official["date"]),
                source="settrade_official",
                gold_price_usd=gold_price_usd,
                usd_thb_rate=usd_thb_rate,
            )
            results.append({**entry, "fund_code": fund_code, "hedged": hedged, "source_url": official.get("source_url")})
            continue
        nav = estimate_nav_from_gold(
            gold_price_usd, usd_thb_rate, hedged=hedged, hedge_ref_rate=hedge_ref_rate
        )
        # For hedged funds the live USD/THB is hedged away, so the FX figure
        # recorded for the audit trail is the fixed hedge reference rate, not
        # the floating market rate (nightly agent 2026-06-22).
        entry = record_nav_entry(
            fund_code=fund_code,
            nav_thb=nav,
            source="estimated",
            gold_price_usd=gold_price_usd,
            usd_thb_rate=hedge_ref_rate if hedged else usd_thb_rate,
        )
        results.append({**entry, "fund_code": fund_code, "hedged": hedged})
    return results


if __name__ == "__main__":
    # Quick test run
    snapshots = run_nightly_nav_snapshot(gold_price_usd=4500.0, usd_thb_rate=32.94)
    for s in snapshots:
        print(f"{s['fund_code']}: NAV = {s['nav_thb']:.4f} THB/unit")
