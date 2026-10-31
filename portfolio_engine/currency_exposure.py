"""
currency_exposure.py — LOOK-THROUGH currency exposure of a THB-based book.

Why this module exists
----------------------
On 2026-08-06 `rebalancer.single_name_concentration_review()` reported the
ex-gold book as **100% country-weight TH** and flagged it. That number is
correct and it is also misleading, because it measures the currency a position
is *listed and settled* in, not the currency the underlying business actually
*earns*. Those are different things, and for this specific book the difference
is large enough to change the conclusion.

PTTEP is the clean case. It is listed on the SET, quoted in THB, and settles in
THB — so every country/currency screen in this project counts it as 100% Thai.
But it sells oil and gas at USD-referenced prices; its economics are USD. When
the baht falls, PTTEP's THB-translated earnings rise. The position is a THB
*instrument* wrapped around a USD *business*.

The trigger for writing this tonight is that the baht went to a 13-15 month low
(33.39-33.64 vs 33.09 the session before) and the stated cause chain is:

    high global oil price
      -> Thailand's energy IMPORT bill rises (net energy importer)
      -> current account deteriorates
      -> THB weakens
      -> the USD-denominated gold sleeve gains in THB terms
      -> and PTTEP's USD-linked earnings translate up

which means the single macro variable this project already models most
carefully — Brent — reaches the portfolio through a SECOND channel that no
existing module expresses. `oil_scenario.py` prices the direct effect on PTTEP
earnings and BAFS costs. Nothing priced the currency leg. This module is that
leg, and it is also the "cost and risk of currency exchange" mandate applied to
holdings rather than to transactions (`foreign_access_cost.py` already covers
transactions).

What this module does NOT claim
-------------------------------
The sensitivities below are STRUCTURAL ASSUMPTIONS derived from how each
business is known to earn, not regression betas measured from price history.
They are labelled with a confidence level and a `how_to_falsify` string, and the
report refuses to present them as measured. Running the actual regression needs
a clean multi-year daily price + USDTHB series, which this project does not yet
have loaded; `NEXT_STEP_TO_MEASURE` at the bottom of this file says exactly what
would be required.

Design notes
------------
* Pure python. No network, no DB, no third-party imports, no LLM. Runnable and
  testable in isolation — `python3 currency_exposure.py` prints a full report.
* Every FX number is expressed in USD/THB (baht per dollar), so "up" = weaker
  baht throughout. This is stated on every output to prevent sign errors, which
  are the single most common mistake in FX attribution.

Added by nightly agent 2026-08-07
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(__file__).resolve().parent.parent
SNAPSHOT_DIR = PROJECT_DIR / "data" / "snapshots"

# FX convention, stated once and referenced everywhere below.
FX_CONVENTION = (
    "All FX is quoted USD/THB = baht per one US dollar. A RISE in this number is "
    "a WEAKER baht. Percent moves described as 'THB depreciation' are increases "
    "in USD/THB."
)


# --------------------------------------------------------------------------
# Look-through exposure assumptions
# --------------------------------------------------------------------------
# usd_revenue_share : fraction of the underlying economics referenced to USD.
# thb_depreciation_beta : estimated change in the THB-quoted value of the
#   position for a 1% depreciation of the baht, holding everything else equal.
#   This is NOT a measured beta. See module docstring.
#
# Added by nightly agent 2026-08-07
CURRENCY_EXPOSURE_ASSUMPTIONS: dict[str, dict[str, Any]] = {
    "PTTEP.BK": {
        "listing_currency": "THB",
        "usd_revenue_share": 0.95,
        "thb_depreciation_beta": 0.50,
        "confidence": "high_on_direction_medium_on_magnitude",
        "basis": (
            "Upstream oil and gas sold at USD-referenced benchmark prices. PTTEP "
            "reports in a USD functional currency and translates to THB for SET "
            "reporting, so a weaker baht mechanically raises THB-reported earnings. "
            "Costs are a mix, which is why the beta is well below the revenue share."
        ),
        "second_order": (
            "The dominant cause of THB weakness right now is a high oil import bill. "
            "That same high oil price is directly positive for PTTEP. The currency "
            "and commodity channels therefore REINFORCE each other for this name — "
            "the two effects are not independent and must not be added as if they were."
        ),
        "how_to_falsify": (
            "Regress daily PTTEP.BK THB returns on daily USDTHB returns over 3 years "
            "with Brent as a control. If the USDTHB coefficient is not reliably "
            "positive once Brent is controlled for, the 0.50 is wrong."
        ),
    },
    "BAFS.BK": {
        "listing_currency": "THB",
        "usd_revenue_share": 0.02,
        "thb_depreciation_beta": 0.10,
        "confidence": "medium",
        "basis": (
            "Revenue is a THB service fee per litre of jet fuel handled — domestic, "
            "and explicitly NOT a fuel-price margin (the standing project correction). "
            "The FX linkage is therefore indirect and runs through DEMAND: a weaker "
            "baht makes Thailand cheaper for inbound travellers, which supports "
            "arrivals and therefore throughput, which is the metric that matters."
        ),
        "second_order": (
            "Small positive FX linkage, long lag (arrivals respond over months, not "
            "days), and it is swamped by the arrivals cycle itself. Do not treat this "
            "as an FX hedge."
        ),
        "how_to_falsify": (
            "Compare Thai inbound arrivals growth against lagged real effective "
            "exchange rate. If arrivals show no relationship to REER, drop the beta "
            "to zero."
        ),
    },
    "SCB.BK": {
        "listing_currency": "THB",
        "usd_revenue_share": 0.05,
        "thb_depreciation_beta": -0.30,
        "confidence": "medium_low",
        "basis": (
            "A domestic THB lender: net interest income, fees and credit costs are "
            "essentially all local. The FX linkage is negative and runs through FLOWS "
            "rather than earnings — sustained baht weakness accompanies foreign "
            "selling of Thai equities, and Thai banks are the most liquid, most "
            "foreign-held part of the index, so they absorb a disproportionate share "
            "of that selling."
        ),
        "second_order": (
            "Imported energy inflation with the policy rate pinned at 1.00% squeezes "
            "household real income, which is a slow credit-cost negative. This is a "
            "quarters-long effect, not a session-long one."
        ),
        "how_to_falsify": (
            "Check whether foreign net selling days in Thai equities coincide with "
            "SCB underperformance vs the SET. If bank relative performance is "
            "uncorrelated with foreign flow, the -0.30 is unsupported."
        ),
    },
    "SCBGOLDE": {
        "listing_currency": "THB",
        "usd_revenue_share": 1.00,
        "thb_depreciation_beta": 1.00,
        "confidence": "high",
        "basis": (
            "An unhedged feeder into USD-priced gold. NAV in THB is, by construction, "
            "gold in USD multiplied by USD/THB. The beta is 1.00 by definition of the "
            "instrument, not by estimation."
        ),
        "second_order": (
            "This is the only position in the book with a deliberate, full, "
            "acknowledged foreign-currency exposure. It is what makes the FX line "
            "two-sided rather than a pure cost."
        ),
        "how_to_falsify": "Not falsifiable — it follows from the fund's unhedged structure.",
    },
}


def _load_snapshot_json(path: str | Path | None = None) -> dict[str, Any]:
    """Load a dated snapshot from data/snapshots, defaulting to the newest.

    Added by nightly agent 2026-08-07
    """
    if path is None:
        try:
            candidates = sorted(SNAPSHOT_DIR.glob("[0-9]*.json"))
        except OSError:
            return {}
        if not candidates:
            return {}
        path = candidates[-1]
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {}


# --------------------------------------------------------------------------
# 1. Listed vs economic currency exposure
# --------------------------------------------------------------------------
def look_through_currency_exposure(
    snapshot: dict[str, Any] | None = None,
    gold_sleeve_thb: float | None = None,
) -> dict[str, Any]:
    """
    Split the book by LISTING currency and by ECONOMIC currency exposure.

    The gap between the two lines is the entire point of this module: a screen
    that only sees listing currency reports a 100% THB book and concludes there
    is no FX exposure to manage.

    `gold_sleeve_thb` is optional because the snapshot series tracks the gold
    sleeve by NAV per unit without a unit count. If it is omitted the report
    covers the ex-gold book only and says so explicitly rather than guessing.

    Added by nightly agent 2026-08-07
    """
    snapshot = snapshot if snapshot is not None else _load_snapshot_json()
    values: dict[str, float] = dict(snapshot.get("position_values_thb") or {})

    if gold_sleeve_thb is not None and gold_sleeve_thb > 0:
        values["SCBGOLDE"] = float(gold_sleeve_thb)

    total = sum(float(v or 0) for v in values.values())
    if total <= 0:
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "no_data",
            "note": "No priced positions found in the snapshot; nothing to decompose.",
            "fx_convention": FX_CONVENTION,
        }

    lines: list[dict[str, Any]] = []
    listed_thb = 0.0
    economic_usd = 0.0
    weighted_beta = 0.0
    unmapped: list[str] = []

    for ticker, value in sorted(values.items(), key=lambda kv: -float(kv[1] or 0)):
        value = float(value or 0)
        weight = value / total * 100.0
        assumption = CURRENCY_EXPOSURE_ASSUMPTIONS.get(ticker)
        if assumption is None:
            unmapped.append(ticker)
            assumption = {
                "listing_currency": "THB" if str(ticker).upper().endswith(".BK") else "UNKNOWN",
                "usd_revenue_share": 0.0,
                "thb_depreciation_beta": 0.0,
                "confidence": "none_no_assumption_on_file",
                "basis": "No exposure assumption on file for this ticker; treated as fully domestic.",
            }

        usd_share = float(assumption.get("usd_revenue_share") or 0.0)
        beta = float(assumption.get("thb_depreciation_beta") or 0.0)

        if str(assumption.get("listing_currency")) == "THB":
            listed_thb += value
        economic_usd += value * usd_share
        weighted_beta += weight / 100.0 * beta

        lines.append(
            {
                "ticker": ticker,
                "value_thb": round(value, 2),
                "weight_pct": round(weight, 2),
                "listing_currency": assumption.get("listing_currency"),
                "usd_revenue_share": usd_share,
                "usd_linked_value_thb": round(value * usd_share, 2),
                "thb_depreciation_beta": beta,
                "confidence": assumption.get("confidence"),
                "exposure_unknown": ticker in unmapped,
            }
        )

    listed_thb_pct = listed_thb / total * 100.0
    economic_usd_pct = economic_usd / total * 100.0
    unknown_value = sum(float(values[ticker] or 0) for ticker in unmapped)

    result: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "snapshot_date": (snapshot.get("_meta") or {}).get("date"),
        "fx_convention": FX_CONVENTION,
        "total_thb": round(total, 2),
        "includes_gold_sleeve": "SCBGOLDE" in values,
        "positions": lines,
        "listed_currency_thb_pct": round(listed_thb_pct, 2),
        "economic_usd_exposure_pct": round(economic_usd_pct, 2),
        "economic_thb_exposure_pct": round(100.0 - economic_usd_pct, 2),
        "portfolio_thb_depreciation_beta": round(weighted_beta, 3),
        "unmapped_tickers": unmapped,
        "unknown_exposure_weight": round(unknown_value / total, 4),
        "unknown_exposure_pct": round(unknown_value / total * 100, 2),
    }

    result["headline"] = (
        f"By listing currency the book is {listed_thb_pct:.1f}% THB. By the currency "
        f"the underlying businesses actually earn, roughly {economic_usd_pct:.1f}% of it "
        f"is USD-linked. The concentration screen sees the first number and none of the second."
    )
    result["net_position_read"] = (
        f"Portfolio beta to a 1% baht depreciation is estimated at "
        f"{weighted_beta:+.2f}%. The book is therefore NET LONG the US dollar / "
        f"NET SHORT the baht in economic terms, which is the opposite of what a "
        f"'100% Thailand' label implies. A weaker baht is, on these assumptions, "
        f"mildly HELPFUL to this specific portfolio."
    )
    result["what_this_does_not_change"] = (
        "This does not reduce COUNTRY risk. A Thai political, regulatory, SET-liquidity "
        "or sovereign event hits all four positions regardless of what currency the "
        "revenue is denominated in. Look-through FX exposure and country concentration "
        "are different risks and this module only addresses the first. The 100% TH "
        "country flag from rebalancer.single_name_concentration_review() STANDS."
    )
    result["the_dangerous_reading"] = (
        "Do not use this to argue the book is already diversified. It says the book is "
        "less exposed to a falling baht than it looks — not that it is exposed to "
        "anything other than Thailand."
    )
    return result


# --------------------------------------------------------------------------
# 2. FX attribution of a realised move
# --------------------------------------------------------------------------
def fx_attribution(
    asset_return_usd_pct: float,
    usd_thb_start: float,
    usd_thb_end: float,
    label: str = "position",
) -> dict[str, Any]:
    """
    Split a THB-measured return into the asset leg and the currency leg.

    This is the arithmetic the nightly log has been doing by hand for the gold
    sleeve every night. Putting it in code makes it reproducible and removes the
    recurring sign-error risk.

    Added by nightly agent 2026-08-07
    """
    if usd_thb_start <= 0 or usd_thb_end <= 0:
        return {"status": "bad_input", "note": "USD/THB rates must be positive."}

    asset_factor = 1.0 + asset_return_usd_pct / 100.0
    fx_factor = usd_thb_end / usd_thb_start
    total_factor = asset_factor * fx_factor

    fx_return_pct = (fx_factor - 1.0) * 100.0
    total_return_pct = (total_factor - 1.0) * 100.0
    # Cross term, reported rather than silently absorbed into one of the legs.
    cross_term_pct = total_return_pct - asset_return_usd_pct - fx_return_pct

    if abs(total_return_pct) > 1e-9:
        fx_share = fx_return_pct / total_return_pct * 100.0
    else:
        fx_share = 0.0

    return {
        "label": label,
        "fx_convention": FX_CONVENTION,
        "asset_return_usd_pct": round(asset_return_usd_pct, 4),
        "usd_thb_start": usd_thb_start,
        "usd_thb_end": usd_thb_end,
        "thb_move_pct": round(fx_return_pct, 4),
        "thb_direction": "weaker_baht" if fx_return_pct > 0 else "stronger_baht",
        "fx_return_pct": round(fx_return_pct, 4),
        "cross_term_pct": round(cross_term_pct, 6),
        "total_return_thb_pct": round(total_return_pct, 4),
        "fx_share_of_total_pct": round(fx_share, 1),
        "reading": (
            f"{label}: {asset_return_usd_pct:+.2f}% in USD became "
            f"{total_return_pct:+.2f}% in THB. The currency contributed "
            f"{fx_return_pct:+.2f}pp of that."
        ),
    }


# --------------------------------------------------------------------------
# 3. The oil -> THB -> portfolio transmission chain
# --------------------------------------------------------------------------
def oil_thb_transmission(brent_usd: float) -> dict[str, Any]:
    """
    Describe and roughly size the SECOND channel by which Brent reaches this book.

    `oil_scenario.py` prices the direct channel (PTTEP earnings, BAFS costs).
    This prices the currency channel, which for a net energy importer runs the
    other way and lands on a different set of positions.

    The elasticity here is deliberately crude and flagged as such. The point is
    the SIGN and the STRUCTURE, not a forecast.

    Added by nightly agent 2026-08-07
    """
    # Rough anchor: Thailand imports on the order of 1m bbl/day of crude and
    # products. A USD 10/bbl move is therefore order USD 3.5-4bn/yr on the
    # current account of a ~USD 550bn economy, i.e. ~0.7pp of GDP. Historically
    # a current-account swing of that size has been associated with a low
    # single-digit percent move in the baht, other things equal.
    NEUTRAL_BRENT = 75.0
    THB_PCT_PER_10_USD_BRENT = 1.2  # LOW confidence, order-of-magnitude only

    excess = brent_usd - NEUTRAL_BRENT
    implied_thb_pressure_pct = excess / 10.0 * THB_PCT_PER_10_USD_BRENT

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fx_convention": FX_CONVENTION,
        "brent_usd": brent_usd,
        "neutral_brent_assumption_usd": NEUTRAL_BRENT,
        "elasticity_thb_pct_per_10usd": THB_PCT_PER_10_USD_BRENT,
        "elasticity_confidence": "low_order_of_magnitude_only",
        "implied_thb_depreciation_pressure_pct": round(implied_thb_pressure_pct, 2),
        "chain": [
            "Brent rises",
            "Thailand's energy import bill rises (structural net energy importer)",
            "current account deteriorates",
            "THB depreciates against USD",
            "SCBGOLDE THB NAV rises (unhedged USD asset, beta 1.00)",
            "PTTEP THB-translated earnings rise (USD-referenced revenue, beta ~0.50)",
            "SCB pressured via foreign equity outflow (beta ~-0.30)",
            "BAFS mildly supported via cheaper-destination arrivals, long lag (beta ~0.10)",
        ],
        "why_this_matters": (
            "High oil is a genuine negative for Thailand as a country and is currently "
            "the stated driver of the baht's 13-15 month low. For THIS book it is "
            "substantially SELF-HEDGING: the same shock that weakens the currency also "
            "lifts the largest USD-linked earner and the gold sleeve. The portfolio and "
            "the country are not exposed to oil in the same direction."
        ),
        "where_it_breaks": (
            "The hedge is asymmetric and fails on the downside. If Brent collapses "
            "because global demand is failing rather than because Hormuz reopened, then "
            "PTTEP earnings fall, the baht does NOT necessarily strengthen (risk-off "
            "usually means dollar strength), and gold's direction depends entirely on "
            "whether the Fed is cutting. A demand-led oil collapse is the scenario where "
            "every leg of this loses at once."
        ),
        "not_a_forecast": (
            "This does not predict the baht. FX at a 1-3 month horizon is dominated by "
            "rate differentials and positioning, not the current account. The "
            "BOT-at-1.00% vs Fed differential is currently the larger driver and is not "
            "modelled here."
        ),
    }


# --------------------------------------------------------------------------
# 4. THB stress test
# --------------------------------------------------------------------------
DEFAULT_THB_SCENARIOS: list[dict[str, Any]] = [
    {
        "name": "baht_recovers",
        "usd_thb": 32.00,
        "narrative": "Fed cuts land, differential narrows, tourism season returns, oil falls.",
    },
    {
        "name": "current_mark",
        "usd_thb": 33.39,
        "narrative": "2026-08-06 mark. 13-15 month low; -5.5% year to date.",
    },
    {
        "name": "drift_continues",
        "usd_thb": 34.50,
        "narrative": "BOT pinned at 1.00%, current account stays negative on the energy bill.",
    },
    {
        "name": "stress",
        "usd_thb": 36.00,
        "narrative": "Sustained foreign outflow plus an oil re-spike; disorderly move.",
    },
]


def thb_scenario_table(
    snapshot: dict[str, Any] | None = None,
    base_usd_thb: float = 33.39,
    gold_sleeve_thb: float | None = None,
    scenarios: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Estimated THB value of the book across USD/THB scenarios, using the
    look-through betas. Holds asset prices in their own currency constant so the
    output isolates the FX leg alone.

    Added by nightly agent 2026-08-07
    """
    exposure = look_through_currency_exposure(snapshot, gold_sleeve_thb=gold_sleeve_thb)
    if exposure.get("status") == "no_data":
        return exposure

    scenarios = scenarios if scenarios is not None else DEFAULT_THB_SCENARIOS
    base_total = float(exposure["total_thb"])
    rows: list[dict[str, Any]] = []

    for scenario in scenarios:
        rate = float(scenario["usd_thb"])
        thb_move_pct = (rate / base_usd_thb - 1.0) * 100.0
        total = 0.0
        for line in exposure["positions"]:
            beta = float(line["thb_depreciation_beta"])
            total += float(line["value_thb"]) * (1.0 + beta * thb_move_pct / 100.0)
        rows.append(
            {
                "name": scenario["name"],
                "usd_thb": rate,
                "thb_move_vs_base_pct": round(thb_move_pct, 2),
                "est_portfolio_thb": round(total, 2),
                "est_change_thb": round(total - base_total, 2),
                "est_change_pct": round((total / base_total - 1.0) * 100.0, 2),
                "narrative": scenario.get("narrative", ""),
            }
        )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fx_convention": FX_CONVENTION,
        "base_usd_thb": base_usd_thb,
        "base_portfolio_thb": round(base_total, 2),
        "portfolio_thb_depreciation_beta": exposure["portfolio_thb_depreciation_beta"],
        "scenarios": rows,
        "isolates_fx_only": (
            "Asset prices in their own currency are held constant. These are NOT price "
            "forecasts — they are the currency leg alone, which is the leg no other "
            "module in this project reports."
        ),
        "magnitude_caveat": (
            "The spread across this table is small relative to a single day's equity "
            "move. That is the honest finding: for a book this size, FX is a real but "
            "second-order driver of value, and it is a FIRST-order driver only of the "
            "gold sleeve. Sizing decisions should not be made on this table alone."
        ),
    }


# --------------------------------------------------------------------------
# 5. Report
# --------------------------------------------------------------------------
NEXT_STEP_TO_MEASURE = (
    "To replace these structural assumptions with measured betas, load a 3-year daily "
    "series of BAFS.BK / PTTEP.BK / SCB.BK closes and USDTHB into data/research/, then "
    "regress each name's daily THB return on the USDTHB daily return with Brent as a "
    "control. Until that exists, every beta in this module is an assumption with a "
    "stated rationale, and the report says so on every line."
)


def run_currency_exposure_report(
    base_usd_thb: float = 33.39,
    brent_usd: float = 83.64,
    gold_sleeve_thb: float | None = None,
) -> dict[str, Any]:
    """
    Full currency report: look-through exposure, the oil->THB chain, and a
    THB scenario table.

    Added by nightly agent 2026-08-07
    """
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fx_convention": FX_CONVENTION,
        "look_through_exposure": look_through_currency_exposure(
            gold_sleeve_thb=gold_sleeve_thb
        ),
        "oil_thb_transmission": oil_thb_transmission(brent_usd),
        "thb_scenarios": thb_scenario_table(
            base_usd_thb=base_usd_thb, gold_sleeve_thb=gold_sleeve_thb
        ),
        "assumptions_are_not_measurements": NEXT_STEP_TO_MEASURE,
    }


if __name__ == "__main__":  # pragma: no cover
    report = run_currency_exposure_report()
    json.dump(report, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
