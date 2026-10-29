"""
foreign_access_cost.py — All-in cost of reaching a FOREIGN market from a THB base.

Why this module exists
----------------------
`fee_analyzer.py` already handles the cost of things Tho ALREADY owns: Thai fund
TERs and SET brokerage/transaction tax. It has no view on the question that
actually gates every new international idea this project surfaces:

    "If I put THB X into <foreign market> for <N> months, what does it cost me
     just to be there — before the market does anything at all?"

That number is dominated by items a headline never mentions:

  1. the THB -> USD (-> local) FX spread, paid TWICE (in and out),
  2. broker commission with a MINIMUM TICKET, which is the silent killer at
     small position sizes — a USD 15 minimum on a USD 900 trade is 1.7%,
  3. the fund/ETF TER, compounding over the holding period,
  4. dividend withholding tax in the source country,
  5. structural currency DRIFT — not volatility, but the persistent managed
     depreciation some emerging currencies run against the USD, which is a
     near-certain negative carry on the asset measured in THB.

Item 5 is the one most retail analysis omits entirely, and for managed-float
currencies (VND being the textbook case) it can exceed the TER several times
over across a 2-year medium-term hold.

Design notes
------------
* Pure-python, no network, no DB, no third-party imports. It is deliberately
  runnable and testable in isolation — earlier nightly runs kept logging
  "could not exercise end-to-end in the sandbox", so this module is written to
  not have that problem.
* Costs are returned as PERCENT OF THE POSITION over the stated horizon, so a
  route can be compared directly against the expected return of the idea.
* Every default is tagged with a confidence level. Where a real fee schedule
  should be checked against a fund factsheet or broker tariff, the field says
  so rather than pretending to precision.
* This computes COST ONLY. It is not a return forecast and takes no view on
  whether the underlying market is attractive.

Added by nightly agent 2026-08-06
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

try:  # keep the module importable (and runnable) outside the package context
    from utils.common import configure_logging

    logger = configure_logging("portfolio_engine.foreign_access_cost")
except Exception:  # pragma: no cover - standalone/verification path
    import logging

    logger = logging.getLogger("portfolio_engine.foreign_access_cost")


# ---------------------------------------------------------------------------
# Currency drift registry
# ---------------------------------------------------------------------------
# Structural annual drift vs USD, expressed as PERCENT PER YEAR of value LOST by
# holding the local currency. Positive = the currency depreciates vs USD, i.e. a
# drag on a USD-measured return. This is the *trend* component only; it is NOT
# volatility and NOT a forecast of any given year.
#
# Confidence is explicit because these are regime-dependent: a managed crawl can
# be re-pegged or widened by the central bank at any time.
CURRENCY_DRIFT_VS_USD: dict[str, dict[str, Any]] = {
    "VND": {
        "annual_drift_pct": 3.0,
        "range_pct": (2.0, 4.0),
        "regime": "managed crawling band (State Bank of Vietnam)",
        "confidence": "medium",
        "note": (
            "The SBV runs a managed crawl that has depreciated the dong against the "
            "USD in most years. For a THB-based investor this stacks BEHIND the "
            "THB/USD leg: the asset is VND, priced through USD, settled from THB. "
            "Over a 2-year hold this is typically the single largest cost line, "
            "larger than the TER."
        ),
    },
    "THB": {
        "annual_drift_pct": 0.0,
        "range_pct": (-2.0, 2.0),
        "regime": "managed float — this is Tho's BASE currency",
        "confidence": "n/a",
        "note": "Base currency. No drift cost by definition; other legs are measured against it.",
    },
    "USD": {
        "annual_drift_pct": 0.0,
        "range_pct": (-4.0, 4.0),
        "regime": "free float",
        "confidence": "n/a",
        "note": (
            "No structural drift assumed. THB/USD is treated as two-sided RISK, not "
            "as a cost — see fx_risk_note on the result. A weaker baht helps a USD "
            "asset and vice versa."
        ),
    },
    "INR": {
        "annual_drift_pct": 2.5,
        "range_pct": (1.5, 4.0),
        "regime": "managed float (RBI)",
        "confidence": "low-medium",
        "note": "Historically a persistent depreciator vs USD. Verify before relying on it.",
    },
    "JPY": {
        "annual_drift_pct": 0.0,
        "range_pct": (-8.0, 8.0),
        "regime": "free float",
        "confidence": "n/a",
        "note": "No structural drift; very high two-sided volatility. Treat as risk, not cost.",
    },
}

# Withholding tax on dividends paid to a THAI resident, by source jurisdiction.
# Where a treaty rate exists it generally must be CLAIMED (e.g. a W-8BEN for US
# securities); the un-claimed statutory rate is given too, because the default
# outcome for a retail investor who files nothing is the statutory rate.
DIVIDEND_WITHHOLDING_PCT: dict[str, dict[str, Any]] = {
    "US": {
        "statutory_pct": 30.0,
        "treaty_pct_for_thai_resident": 15.0,
        "claim_mechanism": "W-8BEN filed with the broker",
        "confidence": "medium — confirm with the broker; treaty relief is not automatic",
    },
    "TH": {
        "statutory_pct": 10.0,
        "treaty_pct_for_thai_resident": 10.0,
        "claim_mechanism": "withheld at source; creditable on a Thai return",
        "confidence": "high",
    },
    "VN": {
        "statutory_pct": 0.0,
        "treaty_pct_for_thai_resident": 0.0,
        "claim_mechanism": "n/a for most foreign portfolio investors",
        "confidence": "low — verify; Vietnam's treatment of foreign portfolio flows changes",
    },
}


# ---------------------------------------------------------------------------
# Route definition
# ---------------------------------------------------------------------------

@dataclass
class AccessRoute:
    """One concrete way of getting THB money into a foreign market."""

    route_id: str
    label: str
    # Currency actually transacted in (what the FX spread is paid on). "THB"
    # means no offshore FX leg is paid by Tho directly.
    trade_currency: str = "USD"
    # Currency of the UNDERLYING assets — drives the structural drift charge.
    underlying_currency: str = "USD"
    # Jurisdiction the dividends are sourced from, for withholding.
    dividend_source: str = "US"

    # Round-trip friction
    fx_spread_pct_per_leg: float = 0.50      # THB<->USD retail spread, each way
    commission_pct: float = 0.25             # % of ticket
    commission_min_usd: float = 15.0         # the silent killer at small sizes
    front_load_pct: float = 0.0              # fund front-end fee
    back_load_pct: float = 0.0

    # Recurring
    ter_pct: float = 0.68                    # annual, all layers combined
    dividend_yield_pct: float = 1.0          # to size the withholding drag

    # Flags
    us_situs_asset: bool = True              # US estate-tax exposure > USD 60k
    notes: str = ""
    confidence: str = "medium"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _round(value: float, places: int = 2) -> float:
    return round(value + 0.0, places)


def access_cost(
    route: AccessRoute,
    position_thb: float,
    horizon_months: int = 24,
    usd_thb: float = 33.10,
) -> dict[str, Any]:
    """
    All-in cost of holding `position_thb` via `route` for `horizon_months`.

    Returns a breakdown in BOTH THB and percent-of-position, plus a
    `breakeven_gross_return_pct` — the gross market return the idea must
    deliver before Tho sees his first baht of profit.

    Added by nightly agent 2026-08-06
    """
    years = max(horizon_months, 1) / 12.0
    position_usd = position_thb / usd_thb if usd_thb else 0.0

    # --- one-off entry/exit ---
    fx_pct = 0.0
    if route.trade_currency != "THB":
        fx_pct = route.fx_spread_pct_per_leg * 2  # in and out

    # commission: greater of percentage and the minimum ticket, both legs
    comm_pct_leg = route.commission_pct
    if position_usd > 0:
        min_as_pct = (route.commission_min_usd / position_usd) * 100.0
        comm_pct_leg = max(comm_pct_leg, min_as_pct)
    else:
        min_as_pct = 0.0
    commission_pct_total = comm_pct_leg * 2
    min_binding = min_as_pct > route.commission_pct

    load_pct = route.front_load_pct + route.back_load_pct
    one_off_pct = fx_pct + commission_pct_total + load_pct

    # --- recurring ---
    ter_total_pct = route.ter_pct * years
    wht = DIVIDEND_WITHHOLDING_PCT.get(route.dividend_source, {})
    wht_rate = float(wht.get("treaty_pct_for_thai_resident", 0.0))
    wht_pct_total = route.dividend_yield_pct * (wht_rate / 100.0) * years

    drift = CURRENCY_DRIFT_VS_USD.get(route.underlying_currency, {})
    drift_annual = float(drift.get("annual_drift_pct", 0.0))
    drift_pct_total = drift_annual * years

    total_pct = one_off_pct + ter_total_pct + wht_pct_total + drift_pct_total

    lines = {
        "fx_spread_round_trip_pct": _round(fx_pct),
        "commission_round_trip_pct": _round(commission_pct_total),
        "fund_loads_pct": _round(load_pct),
        "ter_over_horizon_pct": _round(ter_total_pct),
        "dividend_withholding_pct": _round(wht_pct_total),
        "currency_drift_pct": _round(drift_pct_total),
    }
    biggest = max(lines, key=lambda k: lines[k]) if lines else None

    result: dict[str, Any] = {
        "route_id": route.route_id,
        "label": route.label,
        "position_thb": _round(position_thb),
        "position_usd": _round(position_usd),
        "horizon_months": horizon_months,
        "usd_thb_assumed": usd_thb,
        "cost_lines_pct": lines,
        "one_off_pct": _round(one_off_pct),
        "recurring_pct": _round(ter_total_pct + wht_pct_total + drift_pct_total),
        "total_cost_pct": _round(total_pct),
        "total_cost_thb": _round(position_thb * total_pct / 100.0),
        "annualised_cost_pct": _round(total_pct / years),
        "breakeven_gross_return_pct": _round(total_pct),
        "largest_single_cost": biggest,
        "commission_minimum_is_binding": min_binding,
        "confidence": route.confidence,
        "flags": [],
        "notes": route.notes,
    }

    if min_binding:
        result["flags"].append(
            f"COMMISSION MINIMUM BINDING — the USD {route.commission_min_usd:.0f} floor is "
            f"{min_as_pct:.2f}% of this ticket vs the {route.commission_pct:.2f}% headline rate. "
            "The position is too small to amortise fixed costs; either size up or drop the idea."
        )
    if drift_annual >= 2.0:
        result["flags"].append(
            f"STRUCTURAL CURRENCY DRIFT — {route.underlying_currency} runs a "
            f"{drift.get('regime', 'managed')} and has typically depreciated ~{drift_annual:.1f}%/yr "
            f"vs USD, costing ~{drift_pct_total:.1f}% over {horizon_months} months. This is a "
            "near-certain drag, not a two-sided risk."
        )
    if route.us_situs_asset:
        result["flags"].append(
            "US ESTATE-TAX SITUS — US-listed securities held by a non-resident alien are "
            "US-situs assets with only a USD 60,000 exemption (vs USD 13m+ for US persons). "
            "Not binding at current portfolio size, but it becomes a real planning issue as "
            "the offshore sleeve grows past that line."
        )
    if route.trade_currency != "THB":
        result["fx_risk_note"] = (
            "Beyond the spread above, this route leaves Tho with unhedged THB/USD exposure "
            "for the whole holding period. That is genuine two-sided RISK, not a cost: a "
            "stronger baht erodes the position in THB terms even if the asset is flat. "
            "THB/USD has moved several percent inside single quarters this year."
        )

    return result


def compare_routes(
    routes: list[AccessRoute],
    position_thb: float,
    horizon_months: int = 24,
    usd_thb: float = 33.10,
) -> dict[str, Any]:
    """
    Rank access routes by all-in cost and state the cheapest one plainly.

    Added by nightly agent 2026-08-06
    """
    results = [access_cost(r, position_thb, horizon_months, usd_thb) for r in routes]
    results.sort(key=lambda r: r["total_cost_pct"])
    cheapest = results[0] if results else None
    spread = (
        _round(results[-1]["total_cost_pct"] - results[0]["total_cost_pct"])
        if len(results) > 1
        else 0.0
    )
    return {
        "position_thb": _round(position_thb),
        "horizon_months": horizon_months,
        "routes_ranked": results,
        "cheapest_route_id": cheapest["route_id"] if cheapest else None,
        "cost_spread_between_best_and_worst_pct": spread,
        "verdict": (
            f"Cheapest route is '{cheapest['label']}' at {cheapest['total_cost_pct']:.2f}% "
            f"all-in over {horizon_months} months "
            f"({cheapest['annualised_cost_pct']:.2f}%/yr). The gap to the most expensive "
            f"route is {spread:.2f}% — route selection matters "
            + ("MORE than a year of typical dividend income." if spread > 3 else "but is second-order here.")
            if cheapest
            else "No routes supplied."
        ),
    }


# ---------------------------------------------------------------------------
# Pre-built routes — Vietnam (the live Aug-2026 question)
# ---------------------------------------------------------------------------

def vietnam_routes() -> list[AccessRoute]:
    """
    The realistic ways a Thai retail investor can own Vietnamese equity.

    Direct VN market access is omitted deliberately: it requires a local
    trading code and custodian and is not practical for Tho.

    Added by nightly agent 2026-08-06
    """
    return [
        AccessRoute(
            route_id="vnm_us_etf",
            label="VanEck Vietnam ETF (VNM, NYSE Arca) via a Thai offshore account",
            trade_currency="USD",
            underlying_currency="VND",
            dividend_source="US",
            fx_spread_pct_per_leg=0.50,
            commission_pct=0.25,
            commission_min_usd=15.0,
            ter_pct=0.68,
            dividend_yield_pct=1.0,
            us_situs_asset=True,
            confidence="medium",
            notes=(
                "TER ~0.66-0.68%, AUM ~USD 560-640m — small enough that spreads and "
                "premium/discount to NAV are a real secondary cost not modelled here. "
                "Thai broker offshore tariffs vary widely; the 0.25% / USD 15 minimum is "
                "a representative placeholder — CHECK THE ACTUAL TARIFF before acting."
            ),
        ),
        AccessRoute(
            route_id="th_feeder_fund",
            label="Thai-domiciled Vietnam equity feeder fund (buy in THB)",
            trade_currency="THB",          # no offshore FX leg paid directly
            underlying_currency="VND",
            dividend_source="TH",
            fx_spread_pct_per_leg=0.0,
            commission_pct=0.0,
            commission_min_usd=0.0,
            front_load_pct=1.00,
            back_load_pct=0.0,
            ter_pct=1.90,                  # feeder + master, stacked
            dividend_yield_pct=0.0,        # most Thai feeders accumulate
            us_situs_asset=False,
            confidence="low",
            notes=(
                "GENERIC placeholder, NOT a specific fund. Thai Vietnam feeders typically "
                "stack a local fee on top of the master fund's fee, landing ~1.5-2.5% all-in, "
                "often with a front-end load. Upside: settles in THB, no offshore account, no "
                "US estate-tax situs, simpler Thai tax treatment. The FX exposure does not "
                "disappear — it is embedded in the NAV and usually unhedged. Before using this "
                "route, pull the actual fund factsheet/FCT and replace ter_pct and "
                "front_load_pct with the real numbers."
            ),
        ),
    ]


def vietnam_access_report(
    position_thb: float = 29_700.0,
    horizon_months: int = 24,
    usd_thb: float = 33.10,
) -> dict[str, Any]:
    """
    Worked example for the live Aug-2026 Vietnam question.

    Default position_thb ~= 5% of Tho's ex-gold book (THB 593,460 on the
    2026-08-05 snapshot), which is the largest size a genuinely satellite
    diversifier should take.

    Added by nightly agent 2026-08-06
    """
    report = compare_routes(vietnam_routes(), position_thb, horizon_months, usd_thb)
    report["context"] = (
        "The FTSE Russell frontier->secondary-emerging reclassification is effective "
        "2026-09-21, with the final eligible-securities list published 2026-08-21. The "
        "upgrade itself was confirmed in Oct-2025 and reconfirmed Apr-2026, so it is "
        "long-telegraphed and heavily front-run — the VN-Index was ~1,777 on 2026-08-04. "
        "This report deliberately answers only the COST question, because at Tho's "
        "position size the cost answer arrives before the market view matters."
    )
    report["how_to_read"] = (
        "Compare total_cost_pct against a realistic 2-year return expectation for the "
        "idea. If the cost is a large fraction of the expected return, the correct "
        "decision is to size UP (so fixed costs amortise) or to SKIP — not to proceed "
        "at a small size and hope."
    )
    return report


if __name__ == "__main__":  # pragma: no cover
    import json as _json

    print(_json.dumps(vietnam_access_report(), indent=2))
