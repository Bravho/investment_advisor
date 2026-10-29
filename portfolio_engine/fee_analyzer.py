"""
fee_analyzer.py — Total cost of ownership calculator for all holdings.

Computes annual management fees for funds, SET brokerage commissions, and
SET transaction tax for equities. Compares fund costs against lower-cost
equivalents and flags cases where switching would materially improve net
returns over a 3-month to 2-year medium-term holding horizon.

Added by nightly agent 2026-06-09
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from utils.common import PROJECT_DIR, configure_logging

logger = configure_logging("portfolio_engine.fee_analyzer")

# ---------------------------------------------------------------------------
# Fee registry — known funds and their costs
# ---------------------------------------------------------------------------

# Thai mutual fund Total Expense Ratios (TER) — annual %, approximate
FUND_FEES: dict[str, dict[str, Any]] = {
    "SCBGOLDE": {
        "name": "SCB Gold Open End (E-channel)",
        "ter_pct": 0.50,
        "front_load_pct": 0.0,
        "back_load_pct": 0.0,
        "currency": "THB",
        "asset_class": "gold",
    },
    "SCBGOLDHE": {
        "name": "SCB Gold THB Hedged OE (E-channel)",
        "ter_pct": 0.65,
        "front_load_pct": 0.0,
        "back_load_pct": 0.0,
        "currency": "THB",
        "asset_class": "gold",
    },
    "SCBGOLDH": {
        "name": "SCB Gold THB Hedged OE (Accum)",
        "ter_pct": 0.65,
        "front_load_pct": 0.0,
        "back_load_pct": 0.0,
        "currency": "THB",
        "asset_class": "gold",
    },
}

# Lower-cost ETF alternatives for comparison (US-listed, USD)
ETF_ALTERNATIVES: dict[str, list[dict[str, Any]]] = {
    "gold": [
        {"ticker": "GLD",  "name": "SPDR Gold Shares",     "ter_pct": 0.40, "currency": "USD"},
        {"ticker": "IAU",  "name": "iShares Gold Trust",   "ter_pct": 0.25, "currency": "USD"},
        {"ticker": "SGOL", "name": "abrdn Physical Gold",  "ter_pct": 0.17, "currency": "USD"},
        {"ticker": "GLDM", "name": "SPDR Gold MiniShares", "ter_pct": 0.10, "currency": "USD"},
    ],
}

# SET equity transaction costs (round-trip)
# SET brokerage: varies by broker 0.15%–0.25% per leg; standard retail ~0.15%
# VAT on brokerage: 7%
# SET transaction fee: 0.005% per leg (charged by exchange)
# No capital gains tax in Thailand for individual investors (as of 2026)
SET_BROKERAGE_PCT = 0.15      # per leg, retail broker estimate
SET_VAT_PCT = 7.0             # applied to brokerage commission only
SET_TRANSACTION_FEE_PCT = 0.005  # per leg, exchange fee


# ---------------------------------------------------------------------------
# Core calculations
# ---------------------------------------------------------------------------

@dataclass
class FundCostResult:
    """Annual cost breakdown for a single fund position."""
    ticker: str
    name: str
    position_thb: float
    ter_pct: float
    annual_fee_thb: float
    holding_months: int
    period_fee_thb: float
    alternatives: list[dict[str, Any]] = field(default_factory=list)
    savings_vs_cheapest_thb: float = 0.0
    note: str = ""


@dataclass
class EquityCostResult:
    """Round-trip transaction cost for a SET equity trade."""
    ticker: str
    position_thb: float
    brokerage_each_leg_thb: float
    vat_each_leg_thb: float
    exchange_fee_each_leg_thb: float
    total_round_trip_thb: float
    total_round_trip_pct: float
    note: str = ""


def calculate_fund_cost(
    ticker: str,
    position_thb: float,
    holding_months: int = 12,
    usd_thb_rate: float = 32.8,
) -> FundCostResult:
    """
    Compute annual management fee cost for a fund position in THB.

    Args:
        ticker: Fund ticker (e.g. 'SCBGOLDE')
        position_thb: Current position value in THB
        holding_months: Expected holding period in months (default 12)
        usd_thb_rate: Current USD/THB for converting ETF alternatives

    Returns:
        FundCostResult with full cost breakdown
    """
    if ticker not in FUND_FEES:
        raise ValueError(f"Unknown fund ticker: {ticker}. Add to FUND_FEES registry.")

    info = FUND_FEES[ticker]
    ter = info["ter_pct"] / 100
    annual_fee = position_thb * ter
    period_fee = annual_fee * (holding_months / 12)

    # Build alternatives comparison
    asset_class = info.get("asset_class", "")
    alternatives = []
    cheapest_annual_thb = annual_fee

    for alt in ETF_ALTERNATIVES.get(asset_class, []):
        alt_ter = alt["ter_pct"] / 100
        # Convert USD ETF cost to THB for comparison (assume same exposure size)
        alt_annual_thb = position_thb * alt_ter
        alt_period_thb = alt_annual_thb * (holding_months / 12)
        saving_annual = annual_fee - alt_annual_thb
        saving_period = period_fee - alt_period_thb

        alternatives.append({
            "ticker": alt["ticker"],
            "name": alt["name"],
            "ter_pct": alt["ter_pct"],
            "currency": alt["currency"],
            "annual_fee_thb_equiv": round(alt_annual_thb, 2),
            "period_fee_thb_equiv": round(alt_period_thb, 2),
            "saving_annual_thb": round(saving_annual, 2),
            "saving_period_thb": round(saving_period, 2),
            "saving_annual_pct": round((saving_annual / position_thb) * 100, 4) if position_thb else 0,
        })
        if alt_annual_thb < cheapest_annual_thb:
            cheapest_annual_thb = alt_annual_thb

    savings_vs_cheapest = annual_fee - cheapest_annual_thb

    note_parts = []
    if savings_vs_cheapest > 0:
        note_parts.append(
            f"Switching to cheapest ETF equivalent saves ~{savings_vs_cheapest:,.0f} THB/year "
            f"({savings_vs_cheapest / position_thb * 100:.3f}% of position). "
            f"Note: USD-listed ETFs require currency exchange (USD/THB ~{usd_thb_rate:.2f}), "
            f"adding ~0.5–1.0% round-trip FX cost."
        )
    else:
        note_parts.append("No cheaper equivalent found in registry.")

    return FundCostResult(
        ticker=ticker,
        name=info["name"],
        position_thb=position_thb,
        ter_pct=info["ter_pct"],
        annual_fee_thb=round(annual_fee, 2),
        holding_months=holding_months,
        period_fee_thb=round(period_fee, 2),
        alternatives=alternatives,
        savings_vs_cheapest_thb=round(savings_vs_cheapest, 2),
        note=" ".join(note_parts),
    )


def calculate_set_equity_cost(
    ticker: str,
    position_thb: float,
    brokerage_pct: float = SET_BROKERAGE_PCT,
) -> EquityCostResult:
    """
    Compute round-trip transaction cost for a SET equity position.

    Round-trip = buy leg + sell leg. VAT applies only to brokerage, not exchange fee.

    Args:
        ticker: SET ticker (e.g. 'PTTEP.BK')
        position_thb: Position value in THB
        brokerage_pct: Broker commission per leg (default 0.15%)

    Returns:
        EquityCostResult with full cost breakdown
    """
    brokerage_each = position_thb * (brokerage_pct / 100)
    vat_each = brokerage_each * (SET_VAT_PCT / 100)
    exchange_fee_each = position_thb * (SET_TRANSACTION_FEE_PCT / 100)
    total_per_leg = brokerage_each + vat_each + exchange_fee_each
    total_round_trip = total_per_leg * 2
    total_pct = (total_round_trip / position_thb * 100) if position_thb else 0

    return EquityCostResult(
        ticker=ticker,
        position_thb=position_thb,
        brokerage_each_leg_thb=round(brokerage_each, 2),
        vat_each_leg_thb=round(vat_each, 2),
        exchange_fee_each_leg_thb=round(exchange_fee_each, 2),
        total_round_trip_thb=round(total_round_trip, 2),
        total_round_trip_pct=round(total_pct, 4),
        note=(
            f"Round-trip cost includes broker commission ({brokerage_pct}% × 2 legs), "
            f"VAT on commission ({SET_VAT_PCT}%), and SET exchange fee "
            f"({SET_TRANSACTION_FEE_PCT}% × 2 legs). No capital gains tax for Thai individual investors."
        ),
    )


def breakeven_holding_months_for_switch(
    current_ter_pct: float,
    alt_ter_pct: float,
    fx_round_trip_pct: float = 0.75,
) -> float:
    """
    Compute how many months you must hold an ETF alternative before the fee
    savings offset the one-time currency conversion cost.

    Useful for deciding whether it's worth switching from a Thai fund to a
    USD-listed ETF given FX friction.

    Args:
        current_ter_pct: Annual TER of current fund (e.g. 0.50)
        alt_ter_pct: Annual TER of ETF alternative (e.g. 0.10)
        fx_round_trip_pct: Estimated FX round-trip cost in % (default 0.75%)

    Returns:
        Breakeven in months (float); infinity if alt is more expensive
    """
    annual_saving_pct = current_ter_pct - alt_ter_pct
    if annual_saving_pct <= 0:
        return float("inf")
    monthly_saving_pct = annual_saving_pct / 12
    return round(fx_round_trip_pct / monthly_saving_pct, 1)


# ---------------------------------------------------------------------------
# FX-hedged vs unhedged gold-fund comparison — Added by nightly agent 2026-06-18
# ---------------------------------------------------------------------------
# Tho's gold exposure (SCBGOLDE) is UNHEDGED: its THB NAV moves with both gold
# (USD) and USD/THB. The hedged sibling (SCBGOLDHE/SCBGOLDH) strips out the FX
# leg for an extra ~0.15% TER. With USD/THB now range-bound ~32.5, this helper
# quantifies whether paying the hedge premium is worth it for a medium-term hold.

def compare_hedged_vs_unhedged_gold(
    position_thb: float,
    holding_months: int = 12,
    unhedged_ticker: str = "SCBGOLDE",
    hedged_ticker: str = "SCBGOLDHE",
    usd_thb_rate: float = 32.5,
    expected_usd_thb_move_pct: float = 0.0,
) -> dict[str, Any]:
    """
    Compare the cost and FX exposure of the unhedged vs THB-hedged SCB gold fund.

    The trade-off: the hedged fund removes USD/THB swings from the NAV but costs
    an extra hedge premium (TER differential). Whether that is worth paying
    depends on the holder's view of the baht over the holding period.

    Args:
        position_thb: Position size in THB.
        holding_months: Expected hold (months).
        unhedged_ticker / hedged_ticker: fund tickers (must be in FUND_FEES).
        usd_thb_rate: current USD/THB (context only).
        expected_usd_thb_move_pct: holder's view of USD/THB change over the hold
            (e.g. +2.0 = baht weakens 2% → helps the UNHEDGED fund; -2.0 = baht
            strengthens → hurts unhedged). 0.0 (default) = no FX view, range-bound.

    Returns a dict with the per-fund period fee, the hedge premium in THB, the
    FX P&L the hedge would have neutralised, the net advantage, and a verdict.

    Added by nightly agent 2026-06-18
    """
    if unhedged_ticker not in FUND_FEES or hedged_ticker not in FUND_FEES:
        raise ValueError("Both tickers must be present in FUND_FEES registry.")

    unhedged_ter = FUND_FEES[unhedged_ticker]["ter_pct"] / 100
    hedged_ter = FUND_FEES[hedged_ticker]["ter_pct"] / 100
    frac = holding_months / 12

    unhedged_fee = position_thb * unhedged_ter * frac
    hedged_fee = position_thb * hedged_ter * frac
    hedge_premium_thb = hedged_fee - unhedged_fee          # extra cost of hedging
    hedge_premium_pct = (FUND_FEES[hedged_ticker]["ter_pct"] - FUND_FEES[unhedged_ticker]["ter_pct"]) * frac

    # FX P&L on the unhedged position over the hold. Baht weakness (positive
    # move) LIFTS the THB NAV of an unhedged USD-gold fund; the hedge would have
    # given that up. Baht strength (negative) HURTS unhedged; the hedge avoids it.
    fx_pnl_unhedged_thb = position_thb * (expected_usd_thb_move_pct / 100.0)

    # Net advantage of HEDGING = FX loss it avoids − hedge premium paid.
    # (If FX move is positive/baht weak, hedging gives up gain AND costs premium → negative.)
    net_hedge_advantage_thb = (-fx_pnl_unhedged_thb) - hedge_premium_thb

    if abs(expected_usd_thb_move_pct) < 0.25:
        verdict = (
            f"USD/THB range-bound (~{usd_thb_rate:.2f}): the hedge premium "
            f"(~{hedge_premium_pct:.2f}% over {holding_months}m, ~{hedge_premium_thb:,.0f} THB) "
            "buys little when FX is flat. UNHEDGED (SCBGOLDE) is the lower-cost default; "
            "keep the hedge optional unless a baht view develops."
        )
    elif net_hedge_advantage_thb > 0:
        verdict = (
            f"Hedging looks worthwhile here: it would avoid ~{-fx_pnl_unhedged_thb:,.0f} THB of "
            f"baht-strength drag, more than the ~{hedge_premium_thb:,.0f} THB hedge premium "
            f"(net +{net_hedge_advantage_thb:,.0f} THB). Consider SCBGOLDHE if you expect a stronger baht."
        )
    else:
        verdict = (
            f"Stay UNHEDGED: a weaker baht is expected to add ~{fx_pnl_unhedged_thb:,.0f} THB to the "
            f"unhedged NAV, which the hedge would forfeit on top of its ~{hedge_premium_thb:,.0f} THB "
            f"premium (net {net_hedge_advantage_thb:,.0f} THB against hedging)."
        )

    return {
        "position_thb": round(position_thb, 2),
        "holding_months": holding_months,
        "usd_thb_rate": usd_thb_rate,
        "expected_usd_thb_move_pct": expected_usd_thb_move_pct,
        "unhedged": {
            "ticker": unhedged_ticker, "ter_pct": FUND_FEES[unhedged_ticker]["ter_pct"],
            "period_fee_thb": round(unhedged_fee, 2),
        },
        "hedged": {
            "ticker": hedged_ticker, "ter_pct": FUND_FEES[hedged_ticker]["ter_pct"],
            "period_fee_thb": round(hedged_fee, 2),
        },
        "hedge_premium_thb": round(hedge_premium_thb, 2),
        "hedge_premium_pct_of_position": round(hedge_premium_pct, 4),
        "fx_pnl_unhedged_thb": round(fx_pnl_unhedged_thb, 2),
        "net_hedge_advantage_thb": round(net_hedge_advantage_thb, 2),
        "verdict": verdict,
    }


# ---------------------------------------------------------------------------
# Portfolio-level fee summary
# ---------------------------------------------------------------------------

def portfolio_fee_summary(
    holdings: list[dict[str, Any]],
    usd_thb_rate: float = 32.8,
) -> dict[str, Any]:
    """
    Generate a complete fee analysis report for all holdings.

    Args:
        holdings: List of dicts with keys: ticker, asset_class, position_thb,
                  holding_months (optional, defaults to 12)
        usd_thb_rate: Current USD/THB rate

    Returns:
        Full summary dict with per-holding breakdown and totals
    """
    results: list[dict[str, Any]] = []
    total_annual_fees_thb = 0.0
    total_position_thb = 0.0

    for h in holdings:
        ticker = h["ticker"]
        asset_class = h.get("asset_class", "equity")
        position_thb = float(h.get("position_thb", 0))
        holding_months = int(h.get("holding_months", 12))
        total_position_thb += position_thb

        if asset_class == "fund" or ticker in FUND_FEES:
            try:
                result = calculate_fund_cost(ticker, position_thb, holding_months, usd_thb_rate)
                total_annual_fees_thb += result.annual_fee_thb
                results.append({
                    "ticker": ticker,
                    "type": "fund",
                    "name": result.name,
                    "position_thb": position_thb,
                    "ter_pct": result.ter_pct,
                    "annual_fee_thb": result.annual_fee_thb,
                    "period_fee_thb": result.period_fee_thb,
                    "holding_months": holding_months,
                    "savings_vs_cheapest_thb": result.savings_vs_cheapest_thb,
                    "alternatives": result.alternatives,
                    "note": result.note,
                })
            except ValueError as exc:
                logger.warning("Fee calc skipped for %s: %s", ticker, exc)
                results.append({"ticker": ticker, "type": "fund", "error": str(exc)})

        else:
            # SET equity — show round-trip transaction cost
            eq_result = calculate_set_equity_cost(ticker, position_thb)
            # For equities, there's no ongoing management fee — only round-trip trade cost
            results.append({
                "ticker": ticker,
                "type": "equity",
                "position_thb": position_thb,
                "round_trip_cost_thb": eq_result.total_round_trip_thb,
                "round_trip_cost_pct": eq_result.total_round_trip_pct,
                "brokerage_each_leg_thb": eq_result.brokerage_each_leg_thb,
                "vat_each_leg_thb": eq_result.vat_each_leg_thb,
                "exchange_fee_each_leg_thb": eq_result.exchange_fee_each_leg_thb,
                "note": eq_result.note,
            })

    blended_ter = (total_annual_fees_thb / total_position_thb * 100) if total_position_thb else 0

    return {
        "generated_date": __import__("datetime").date.today().isoformat(),
        "base_currency": "THB",
        "usd_thb_rate": usd_thb_rate,
        "total_position_thb": round(total_position_thb, 2),
        "total_annual_fund_fees_thb": round(total_annual_fees_thb, 2),
        "blended_fund_ter_pct": round(blended_ter, 4),
        "holdings": results,
        "summary_note": (
            f"Blended fund TER is {blended_ter:.3f}% p.a. "
            f"Equities show round-trip trade cost only (no ongoing management fee). "
            f"All figures in THB. USD/THB used for ETF comparison: {usd_thb_rate:.2f}."
        ),
    }


# ---------------------------------------------------------------------------
# Convenience: save fee report to disk
# ---------------------------------------------------------------------------

def save_fee_report(report: dict[str, Any], output_dir: Path | None = None) -> Path:
    """
    Persist fee analysis report as JSON to data/fee_reports/YYYY-MM-DD.json.

    Added by nightly agent 2026-06-09
    """
    base = output_dir or (PROJECT_DIR / "data" / "fee_reports")
    base.mkdir(parents=True, exist_ok=True)
    date_str = report.get("generated_date", __import__("datetime").date.today().isoformat())
    out_path = base / f"{date_str}.json"
    out_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    logger.info("Fee report saved to %s", out_path)
    return out_path


# ---------------------------------------------------------------------------
# Quick-access example usage (for manual testing / REPL)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Example: analyse SCBGOLDE with THB 500,000 position, 12-month hold
    import json as _json
    result = calculate_fund_cost("SCBGOLDE", position_thb=500_000, holding_months=12, usd_thb_rate=32.77)
    print(_json.dumps(result.__dict__, indent=2, default=str))
    be = breakeven_holding_months_for_switch(
        current_ter_pct=result.ter_pct,
        alt_ter_pct=0.10,  # GLDM
        fx_round_trip_pct=0.75,
    )
    print(f"\nBreakeven holding for GLDM switch: {be} months")
