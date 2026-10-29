from __future__ import annotations
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from utils.common import PROJECT_DIR, configure_logging
from utils.db_pool import db_pool

logger = configure_logging("ai_engine.risk")
UTC = timezone.utc

# ---------------------------------------------------------------------------
# Currency risk helpers — Added by nightly agent 2026-06-08
# ---------------------------------------------------------------------------

# USD/THB reference band: outside this range triggers elevated currency risk
_USD_THB_LOW = float(os.getenv("USD_THB_LOW", "30.0"))
_USD_THB_HIGH = float(os.getenv("USD_THB_HIGH", "35.0"))
_USD_THB_MIDPOINT = (_USD_THB_LOW + _USD_THB_HIGH) / 2  # 32.5


def currency_risk_score(usd_thb_rate: float) -> float:
    """
    Return a 0–1 currency risk score for a Thai-based portfolio.

    Logic: risk is highest when THB is very weak (high USD/THB ratio) because
    USD-denominated imports/debt become expensive, inflation rises, and the BOT
    may be forced to hike rates which hurts equities.  Risk is moderate when
    THB is very strong (low ratio) because export earnings compress.
    The midpoint (~32.5 for 2026) is the neutral zone.

    Added by nightly agent 2026-06-08
    """
    rate_range = _USD_THB_HIGH - _USD_THB_LOW  # 5.0
    if rate_range <= 0:
        return 0.5
    # Normalise: 0 = at low end, 1 = at high end
    normalised = (usd_thb_rate - _USD_THB_LOW) / rate_range
    # Skew: higher THB weakness (high normalised) → higher risk
    return round(min(max(normalised * 0.7 + 0.15, 0.0), 1.0), 4)


def concentration_flag(values: dict[str, float], threshold: float = 0.30) -> list[str]:
    """
    Return tickers where the position exceeds `threshold` fraction of total portfolio.
    A position > 30% is flagged as concentration risk per project guidelines.

    Added by nightly agent 2026-06-08
    """
    total = sum(values.values()) or 1.0
    return [
        ticker for ticker, value in values.items()
        if value / total > threshold
    ]


# ---------------------------------------------------------------------------
# THB currency-regime monitor — Added by nightly agent 2026-06-25
# ---------------------------------------------------------------------------
# currency_risk_score() (2026-06-08) is just a linear 0-1 scale and never framed
# the TWO-SIDED impact of a moving baht on Tho's specific book. On 2026-06-24 the
# baht broke PAST 33/USD to ~33.22 — its weakest since May 2025 — as the widening
# US(hawkish)-Thailand(easy) rate gap pulled flows out. That move is genuinely
# two-sided for this portfolio and is the core of the project's "cost and risk of
# currency exchange" mandate, so it deserves a discrete flag (like the fed/oil/
# japan flags) rather than a single linear number:
#   • SCBGOLDE (THB-denominated, USD-priced gold) is CUSHIONED by a weak baht —
#     more THB per unit partly offsets gold's USD drawdown.
#   • Buying any new USD-denominated asset costs MORE THB at a weak baht (worse FX
#     entry), and a weak baht signals imported-inflation / capital-outflow pressure
#     that can weigh on SET foreign appetite. Future USD->THB repatriation only
#     benefits if the baht later reverses.
# Diagnostic only — it does NOT alter the blended portfolio score (consistent with
# the established flag pattern).

# Neutral anchor for USD/THB (2026 mid-band) and the weak-side reference span.
_USD_THB_NEUTRAL = float(os.getenv("USD_THB_NEUTRAL", "32.5"))
# Discrete weak-side threshold ladder (USD/THB -> label); higher = weaker baht.
_USD_THB_WEAK_THRESHOLDS = (33.0, 33.5, 34.0, 35.0)


def currency_regime_flag(
    usd_thb_rate: float,
    prior_1yr_high: float | None = None,
    scbgolde_weight: float = 0.0,
    usd_asset_weight: float = 0.0,
) -> dict[str, Any]:
    """
    Score the baht-regime risk for a Thai-based, gold-heavy book and frame its
    TWO-SIDED effect, from the live USD/THB rate.

    Two score components, combined and capped at 1.0:
      • Weakness level: how far USD/THB sits above the ~32.5 neutral anchor,
        scaled across the weak-side span (neutral -> 35.0).
      • Regime break: a bump if the rate prints a fresh cyclical baht low
        (above the prior 1-yr high) — momentum/positioning risk, not just level.

    Args:
        usd_thb_rate:    latest USD/THB spot (e.g. 33.22).
        prior_1yr_high:  prior 1-yr USD/THB high; a print above it flags a regime
                         break. If None, the break component is skipped.
        scbgolde_weight: SCBGOLDE fraction of portfolio (0-1) for the THB-NAV
                         cushion figure.
        usd_asset_weight: fraction of the book in USD-denominated assets (0-1),
                         for the entry-cost sensitivity figure.

    Returns a dict with risk_level, risk_score, the baht cushion / USD entry-cost
    deltas vs neutral, flags, and a medium-term advisory note.

    Added by nightly agent 2026-06-25
    """
    rate = max(float(usd_thb_rate), 0.0)
    flags: list[str] = []

    # --- Weakness-level component (0.0 – 0.8) ---
    span = max(35.0 - _USD_THB_NEUTRAL, 1.0)  # neutral -> severe span (~2.5)
    gap = max(rate - _USD_THB_NEUTRAL, 0.0)
    level = min(gap / span, 1.0) * 0.80

    # --- Regime-break component (0.0 – 0.20) ---
    regime_break = False
    break_component = 0.0
    if prior_1yr_high is not None and rate > float(prior_1yr_high):
        regime_break = True
        break_component = 0.20
        flags.append(
            f"USD/THB ({rate:.2f}) printed a fresh cyclical baht low above the prior "
            f"1-yr high ({float(prior_1yr_high):.2f}) — a regime break, not just noise."
        )

    score = round(min(level + break_component, 1.0), 4)

    # Discrete weak-side label crossing.
    crossed = max((t for t in _USD_THB_WEAK_THRESHOLDS if rate >= t), default=None)
    if crossed is not None:
        flags.append(
            f"Baht weaker than {crossed:.1f}/USD — imported-inflation & SET-outflow "
            "pressure; worse FX entry for new USD-denominated positions."
        )

    # Two-sided sensitivities vs the neutral anchor (% of THB value).
    cushion_pct = round((rate / _USD_THB_NEUTRAL - 1.0) * 100, 2) if _USD_THB_NEUTRAL else 0.0
    scbgolde_cushion_contrib = round(cushion_pct * min(max(scbgolde_weight, 0.0), 1.0), 3)
    usd_entry_cost_contrib = round(cushion_pct * min(max(usd_asset_weight, 0.0), 1.0), 3)

    if score >= 0.66:
        risk_lv = "high"
        rec = (
            "Baht is materially weak. Do NOT rush new USD-denominated buys (FX entry "
            "is expensive); the weak baht is cushioning SCBGOLDE's THB NAV, so let the "
            "gold position ride. Favour THB-denominated income (SCB ~7.5% yield)."
        )
    elif score >= 0.33:
        risk_lv = "elevated"
        rec = (
            "Baht is moderately weak on the US-Thai rate gap. Stagger any USD purchases "
            "rather than converting in size at once; the weak baht partly offsets gold's "
            "USD drawdown for SCBGOLDE."
        )
    else:
        risk_lv = "low"
        rec = "USD/THB near its neutral band — currency is not a material risk right now."

    return {
        "usd_thb_rate": round(rate, 4),
        "neutral_anchor": _USD_THB_NEUTRAL,
        "risk_level": risk_lv,
        "risk_score": score,
        "regime_break": regime_break,
        "prior_1yr_high": prior_1yr_high,
        "weak_threshold_crossed": crossed,
        "components": {"weakness_level": round(level, 4), "regime_break": round(break_component, 4)},
        # Positive cushion_pct = baht weaker than neutral = more THB per USD-priced unit.
        "baht_vs_neutral_pct": cushion_pct,
        "scbgolde_thb_nav_cushion_pct": scbgolde_cushion_contrib,
        "usd_asset_entry_cost_pct": usd_entry_cost_contrib,
        "flags": flags,
        "recommendation": rec,
        "assessed_at": datetime.now(UTC).isoformat(),
    }


def risk_level(score: float) -> str:
    return "low" if score < 0.33 else "medium" if score < 0.66 else "high"


def volatility_score(prices: list[float]) -> tuple[float, float]:
    if len(prices) < 2:
        return 0.5, 0.0
    returns = [
        prices[index] / prices[index - 1] - 1
        for index in range(1, len(prices))
        if prices[index - 1]
    ]
    if len(returns) < 2:
        return 0.5, 0.0
    mean = sum(returns) / len(returns)
    variance = sum((value - mean) ** 2 for value in returns) / (len(returns) - 1)
    annualized = math.sqrt(variance) * math.sqrt(252)
    return min(max(annualized / 0.5, 0.0), 1.0), annualized


async def calculate_portfolio_risk() -> dict[str, Any]:
    pool = await db_pool.get_pool()
    holdings = await pool.fetch("SELECT ticker, quantity FROM holdings ORDER BY ticker")
    macro = await pool.fetchval(
        "SELECT overall_score FROM macro_sentiment ORDER BY snapshot_date DESC LIMIT 1"
    )
    macro_risk = min(max((1 - float(macro or 0)) / 2, 0.0), 1.0)
    values: dict[str, float] = {}
    for holding in holdings:
        price = await pool.fetchval(
            """
            SELECT close_price FROM market_prices
            WHERE ticker = $1 ORDER BY price_date DESC LIMIT 1
            """,
            holding["ticker"],
        )
        values[holding["ticker"]] = float(holding["quantity"] or 0) * float(price or 0)
    total_value = sum(values.values()) or 1.0

    # --- Currency risk (Added by nightly agent 2026-06-08) ---
    usd_thb_row = await pool.fetchrow(
        """
        SELECT close_price FROM market_prices
        WHERE ticker = 'USD_THB' ORDER BY price_date DESC LIMIT 1
        """
    )
    usd_thb_rate = float(usd_thb_row["close_price"]) if usd_thb_row else _USD_THB_MIDPOINT
    curr_risk = currency_risk_score(usd_thb_rate)

    # --- Concentration flag (Added by nightly agent 2026-06-08) ---
    concentrated_positions = concentration_flag(values, threshold=0.30)

    # --- THB currency-regime flag (Added by nightly agent 2026-06-25) ---
    # Two-sided baht-regime diagnostic, decoupled from the scalar currency_risk
    # score. Reads the prior 1-yr USD/THB high from the watchlist for the
    # regime-break test; SCBGOLDE weight from the live position values.
    try:
        import json as _json6
        _wl_path6 = PROJECT_DIR / "data" / "watchlist.json"
        _wl6 = _json6.loads(_wl_path6.read_text(encoding="utf-8")) if _wl_path6.exists() else {}
        _mc6 = _wl6.get("macro_context", {})
        _raw_high = str(_mc6.get("usd_thb_1yr_high", "")).split()[0] or None
        _thb_1yr_high = float(_raw_high) if _raw_high else None
        _gold_weight = (values.get("SCBGOLDE", 0.0) / total_value) if total_value else 0.0
        _usd_weight = sum(
            v for t, v in values.items() if not t.endswith(".BK") and t != "SCBGOLDE"
        ) / total_value if total_value else 0.0
        currency_regime = currency_regime_flag(
            usd_thb_rate,
            prior_1yr_high=_thb_1yr_high,
            scbgolde_weight=_gold_weight,
            usd_asset_weight=_usd_weight,
        )
    except Exception:
        logger.warning("currency regime flag failed — skipping", exc_info=True)
        currency_regime = {}

    holdings_risk = {}
    weighted_portfolio_risk = 0.0
    for holding in holdings:
        ticker = holding["ticker"]
        price_rows = await pool.fetch(
            """
            SELECT close_price FROM market_prices
            WHERE ticker = $1 ORDER BY price_date DESC LIMIT 30
            """,
            ticker,
        )
        price_risk, volatility = volatility_score(
            list(reversed([float(row["close_price"]) for row in price_rows]))
        )
        sentiment = await pool.fetchval(
            """
            SELECT AVG(score) FROM sentiment_scores
            WHERE ticker = $1 AND analyzed_at >= NOW() - INTERVAL '48 hours'
            """,
            ticker,
        )
        sentiment_risk = min(max((1 - float(sentiment or 0)) / 2, 0.0), 1.0)
        position_weight = values[ticker] / total_value
        # Improved concentration risk: flag positions > 30% explicitly
        # (Added by nightly agent 2026-06-08)
        concentration_risk = min(position_weight * 2, 1.0)
        is_concentrated = ticker in concentrated_positions

        # Blend currency risk into per-holding score with 0.05 weight
        # (offset from macro_risk weight reduction: 0.10 → 0.05)
        # New weights: volatility 0.30, sentiment 0.40, concentration 0.20, macro 0.05, currency 0.05
        score = round(
            price_risk * 0.30
            + sentiment_risk * 0.40
            + concentration_risk * 0.20
            + macro_risk * 0.05
            + curr_risk * 0.05,
            4,
        )
        holdings_risk[ticker] = {
            "score": score,
            "volatility": round(volatility, 4),
            "volatility_risk": round(price_risk, 4),
            "sentiment_risk": round(sentiment_risk, 4),
            "concentration_risk": round(concentration_risk, 4),
            "macro_risk": round(macro_risk, 4),
            "currency_risk": round(curr_risk, 4),       # Added 2026-06-08
            "is_concentrated": is_concentrated,          # Added 2026-06-08
        }
        weighted_portfolio_risk += score * position_weight
    portfolio_score = round(weighted_portfolio_risk, 4)

    # --- Japan carry-trade risk (Added by nightly agent 2026-06-13) ---
    # Reads BOJ rate from watchlist.json macro_context; USD/JPY if available.
    try:
        import json as _json
        _wl_path = PROJECT_DIR / "data" / "watchlist.json"
        _wl = _json.loads(_wl_path.read_text(encoding="utf-8")) if _wl_path.exists() else {}
        _boj_rate = float(_wl.get("macro_context", {}).get("boj_policy_rate_pct", 0.75))
        _jpy_entry = _wl.get("watchlist", {}).get("currencies", {}).get("USD_JPY", {})
        _usd_jpy: float | None = float(_jpy_entry["last_rate"]) if _jpy_entry and "last_rate" in _jpy_entry else None
        # Market-implied next-meeting BOJ hike odds (Added by nightly agent 2026-06-28);
        # None when absent → rate/FX-only read (backward compatible).
        _boj_prob_raw = _wl.get("macro_context", {}).get("boj_hike_prob_next_meeting_pct")
        _boj_prob: float | None = float(_boj_prob_raw) if _boj_prob_raw is not None else None
    except Exception:
        _boj_rate = 0.75
        _usd_jpy = None
        _boj_prob = None

    japan_risk = japan_policy_risk_flag(
        boj_rate=_boj_rate, usd_jpy_rate=_usd_jpy, boj_hike_prob_pct=_boj_prob
    )

    # --- PTTEP oil-scenario commodity risk (Added by nightly agent 2026-06-16) ---
    # Reads current Brent + Iran-deal status from watchlist macro_context and
    # scores PTTEP's premium-unwind / coverage downside. Surfaced as a distinct
    # diagnostic (does not alter the existing blended score for backward compat).
    try:
        import json as _json2
        _wl_path2 = PROJECT_DIR / "data" / "watchlist.json"
        _wl2 = _json2.loads(_wl_path2.read_text(encoding="utf-8")) if _wl_path2.exists() else {}
        _mc = _wl2.get("macro_context", {})
        _brent = float(_mc.get("brent_crude_usd", 87.5))
        _deal_flag = str(_mc.get("us_iran_status_flag", "")).lower()
        _deal_confirmed = any(k in _deal_flag for k in ("confirmed", "signed", "framework", "complete"))
        _pttep_weight = (values.get("PTTEP.BK", 0.0) / total_value) if total_value else 0.0
        oil_risk = oil_scenario_risk_flag(_brent, pttep_weight=_pttep_weight, deal_confirmed=_deal_confirmed)
    except Exception:
        logger.warning("oil scenario risk flag failed — skipping", exc_info=True)
        oil_risk = {}

    # Attach PTTEP position-level oil risk to its per-holding record if present.
    if oil_risk and "PTTEP.BK" in holdings_risk:
        holdings_risk["PTTEP.BK"]["oil_commodity_risk"] = oil_risk.get("position_risk_score")

    # --- Lebanon-spillover Hormuz-reclosure tail (Added by nightly agent 2026-06-24) ---
    # Tracks the regional-spillover oil re-spike tail DISCRETELY from the nuclear
    # talks. Reads the Lebanon->Hormuz status flag + Brent from watchlist
    # macro_context. Diagnostic only — does not alter the blended score.
    try:
        import json as _json5
        _wl_path5 = PROJECT_DIR / "data" / "watchlist.json"
        _wl5 = _json5.loads(_wl_path5.read_text(encoding="utf-8")) if _wl_path5.exists() else {}
        _mc5 = _wl5.get("macro_context", {})
        _leb_status = str(_mc5.get("lebanon_hormuz_status", "walked_back"))
        _brent5 = float(_mc5.get("brent_crude_usd", 77.0))
        _pttep_w5 = (values.get("PTTEP.BK", 0.0) / total_value) if total_value else 0.0
        lebanon_spillover = lebanon_spillover_flag(
            status=_leb_status, current_brent_usd=_brent5, pttep_weight=_pttep_w5
        )
    except Exception:
        logger.warning("lebanon spillover flag failed — skipping", exc_info=True)
        lebanon_spillover = {}

    # --- US Fed / FOMC policy risk (Added by nightly agent 2026-06-18) ---
    # Reads the realised Fed funds rate and the dot-plot bias from watchlist
    # macro_context and scores the headwind a hawkish hold poses to gold + the
    # baht-denominated EM book. Diagnostic only — does not alter the blended
    # score (consistent with the japan/oil flags).
    try:
        import json as _json3
        _wl_path3 = PROJECT_DIR / "data" / "watchlist.json"
        _wl3 = _json3.loads(_wl_path3.read_text(encoding="utf-8")) if _wl_path3.exists() else {}
        _mc3 = _wl3.get("macro_context", {})
        _fed_rate = float(_mc3.get("us_fed_funds_rate_pct", 3.625))
        _dot_bias = str(_mc3.get("fomc_jun17_dot_plot_bias", _mc3.get("fed_dot_plot_bias", "neutral")))
        # Market-implied next-meeting hike odds (Added by nightly agent 2026-06-27);
        # None when absent → text-only bias (backward compatible).
        _hike_prob_raw = _mc3.get("fed_hike_prob_next_meeting_pct")
        _hike_prob = float(_hike_prob_raw) if _hike_prob_raw is not None else None
        fed_risk = fed_policy_risk_flag(_fed_rate, dot_plot_bias=_dot_bias, hike_prob_pct=_hike_prob)
    except Exception:
        logger.warning("fed policy risk flag failed — skipping", exc_info=True)
        fed_risk = {}

    # --- Gold-fund drawdown monitor (Added by nightly agent 2026-06-20) ---
    # Cross-references the gold drawdown depth with the live fed_policy_risk to
    # label a Fed-driven dip (hold/add) vs a possible trend break (review).
    # Prefers gold-fund NAV (THB) if both a current NAV and a trailing-high NAV
    # are available; otherwise falls back to gold spot (USD). Diagnostic only.
    try:
        import json as _json4
        _wl_path4 = PROJECT_DIR / "data" / "watchlist.json"
        _wl4 = _json4.loads(_wl_path4.read_text(encoding="utf-8")) if _wl_path4.exists() else {}
        _mc4 = _wl4.get("macro_context", {})
        _nav_cur = _mc4.get("scbgolde_estimated_nav_thb")
        _nav_high = _mc4.get("scbgolde_trailing_high_nav_thb")
        if _nav_cur is not None and _nav_high is not None:
            _gold_cur, _gold_high = float(_nav_cur), float(_nav_high)
        else:
            _gold_cur = float(_mc4.get("gold_current_usd", _mc4.get("gold_spot_usd", 0)) or 0)
            _gold_high = float(
                _mc4.get("gold_recent_high_usd", _mc4.get("gold_trailing_high_usd", _gold_cur)) or _gold_cur
            )
        # Added by nightly agent 2026-06-21: prefer a self-updating rolling high
        # derived from the snapshot archive; take the max with the static
        # watchlist value so the trailing high never regresses below a known
        # peak and updates automatically as snapshots accumulate.
        _derived_high = derive_gold_trailing_high()
        if _derived_high is not None:
            _gold_high = max(_gold_high, _derived_high)
        gold_drawdown = (
            gold_drawdown_monitor(_gold_cur, _gold_high, fed_policy_risk=fed_risk)
            if _gold_high > 0 else {}
        )
    except Exception:
        logger.warning("gold drawdown monitor failed — skipping", exc_info=True)
        gold_drawdown = {}

    return {
        "portfolio_risk_score": portfolio_score,
        "risk_level": risk_level(portfolio_score),
        "holdings_risk": holdings_risk,
        "usd_thb_rate": usd_thb_rate,                  # Added 2026-06-08
        "currency_risk_score": curr_risk,               # Added 2026-06-08
        "currency_regime": currency_regime,             # Added 2026-06-25
        "concentrated_positions": concentrated_positions,  # Added 2026-06-08
        "japan_carry_risk": japan_risk,                 # Added 2026-06-13
        "oil_commodity_risk": oil_risk,                 # Added 2026-06-16
        "fed_policy_risk": fed_risk,                     # Added 2026-06-18
        "gold_drawdown": gold_drawdown,                  # Added 2026-06-20
        "lebanon_spillover": lebanon_spillover,          # Added 2026-06-24
        "calculated_at": datetime.now(UTC).isoformat(),
    }


# ---------------------------------------------------------------------------
# Japan / BOJ carry-trade risk monitor — Added by nightly agent 2026-06-13
# ---------------------------------------------------------------------------

# Thresholds for JPY/USD (not USD/JPY — this is "yen per dollar", inverted)
# When USD/JPY falls below 148, the carry trade starts unwinding.
# At 140 it is severe. These levels are stored as USD/JPY (conventional).
_USDJPY_CARRY_THRESHOLD = float(os.getenv("USDJPY_CARRY_THRESHOLD", "148.0"))
_USDJPY_SEVERE_THRESHOLD = float(os.getenv("USDJPY_SEVERE_THRESHOLD", "140.0"))

# BOJ rate band: risk is elevated whenever BOJ rate approaches or exceeds
# a level that incentivises repatriation of JPY carry trades
_BOJ_CARRY_RATE_THRESHOLD = float(os.getenv("BOJ_CARRY_RATE_THRESHOLD", "1.0"))


def japan_policy_risk_flag(
    boj_rate: float,
    usd_jpy_rate: float | None = None,
    boj_hike_prob_pct: float | None = None,
) -> dict[str, Any]:
    """
    Assess carry-trade unwinding risk from BOJ policy tightening.

    The yen carry trade (borrow cheap JPY, invest in higher-yield assets)
    is a major driver of EM capital flows. When BOJ hikes or the yen
    strengthens sharply, leveraged carry positions unwind rapidly, causing
    broad EM and Asian equity selloffs.

    Optional refinement (Added by nightly agent 2026-06-28):
      • Market-implied hike probability: when `boj_hike_prob_pct` is supplied
        (the priced odds of a BOJ hike at the next decision), a forward-tightening
        component scales +0.0–+0.20 (100% ⇒ +0.20) and can only SHARPEN the
        score. The cap is deliberately tighter than the Fed flag's (+0.40)
        because Japan's base already carries the rate component close to the
        "high" band once the BOJ sits at the 1.0% carry threshold, so a modest
        priced hike should nudge — not jump — the read. This surfaces *forward*
        repatriation risk even when the spot read
        is benign — e.g. with the yen weak (USD/JPY ~160, carry intact) a high
        priced-hike probability still registers the building tightening headwind,
        mirroring the same treatment already applied to `fed_policy_risk_flag`.

    Args:
        boj_rate:      Current BOJ policy rate (%, e.g. 0.75 or 1.0).
        usd_jpy_rate:  Current USD/JPY spot rate (e.g. 148.5).
                       If None, only rate-based assessment is made.
        boj_hike_prob_pct: optional market-implied probability (0–100) of a BOJ
                       hike at the next meeting; if None, falls back to the
                       rate/FX read only (fully backward compatible).

    Returns:
        {
          "risk_level": "low" | "elevated" | "high" | "severe",
          "risk_score": float 0–1,
          "boj_rate": float,
          "usd_jpy_rate": float | None,
          "carry_threshold_breached": bool,
          "flags": list[str],           # human-readable warning strings
          "recommendation": str,
        }

    Added by nightly agent 2026-06-13
    """
    flags: list[str] = []
    score = 0.0

    # --- Rate-based component (0.0 – 0.5) ---
    # Risk rises as BOJ rate approaches the carry trade pain threshold (1.0%).
    # Above 1.0% the yen repatriation incentive is strong.
    rate_ratio = boj_rate / _BOJ_CARRY_RATE_THRESHOLD  # 1.0 at threshold
    rate_component = min(rate_ratio * 0.35, 0.50)
    score += rate_component
    if boj_rate >= _BOJ_CARRY_RATE_THRESHOLD:
        flags.append(
            f"BOJ rate ({boj_rate:.2f}%) at or above carry threshold "
            f"({_BOJ_CARRY_RATE_THRESHOLD:.2f}%) — repatriation incentive elevated."
        )

    # --- USD/JPY component (0.0 – 0.5) ---
    carry_breached = False
    jpy_component = 0.0
    if usd_jpy_rate is not None:
        # Lower USD/JPY = stronger yen = more carry unwind risk
        if usd_jpy_rate < _USDJPY_SEVERE_THRESHOLD:
            jpy_component = 0.50
            carry_breached = True
            flags.append(
                f"USD/JPY ({usd_jpy_rate:.1f}) below severe carry threshold "
                f"({_USDJPY_SEVERE_THRESHOLD:.1f}) — active carry unwind likely."
            )
        elif usd_jpy_rate < _USDJPY_CARRY_THRESHOLD:
            # Linear scale from threshold (0.2) to severe (0.5)
            fraction = (_USDJPY_CARRY_THRESHOLD - usd_jpy_rate) / (
                _USDJPY_CARRY_THRESHOLD - _USDJPY_SEVERE_THRESHOLD
            )
            jpy_component = 0.20 + fraction * 0.30
            carry_breached = True
            flags.append(
                f"USD/JPY ({usd_jpy_rate:.1f}) below carry threshold "
                f"({_USDJPY_CARRY_THRESHOLD:.1f}) — carry trade under pressure."
            )
        else:
            # USD/JPY above threshold: mild risk from rate direction
            jpy_component = 0.10

    # --- Market-implied BOJ hike-probability refinement (Added by nightly agent 2026-06-28) ---
    # Ground a FORWARD-tightening bump in market pricing when available. A priced
    # BOJ hike only raises repatriation/carry-unwind risk, so the component is
    # always additive (0.0–0.20, 100% ⇒ +0.20) and can only sharpen — it surfaces
    # building risk even while the spot yen is weak (USD/JPY high, carry intact).
    # Cap kept below the Fed flag's (0.40): Japan's rate component already runs
    # the base near the "high" band at the 1.0% carry threshold.
    prob_component = None
    if boj_hike_prob_pct is not None:
        prob = min(max(float(boj_hike_prob_pct), 0.0), 100.0)
        prob_component = round((prob / 100.0) * 0.20, 4)
        if prob_component > 0:
            flags.append(
                f"Market prices a {prob:.0f}% BOJ hike at the next meeting — "
                "forward repatriation/carry-unwind risk building even with the yen weak."
            )

    score = round(min(score + jpy_component + (prob_component or 0.0), 1.0), 4)

    # --- Determine risk level ---
    if score >= 0.70:
        risk_lv = "severe"
        rec = (
            "Reduce EM equity exposure. Gold and USD-denominated assets offer "
            "relative safety during acute yen carry unwind episodes."
        )
    elif score >= 0.50:
        risk_lv = "high"
        rec = (
            "Monitor Nikkei and yen-sensitive positions closely. "
            "Consider partial hedging of THB exposure if USD/JPY drops further."
        )
    elif score >= 0.30:
        risk_lv = "elevated"
        rec = (
            "BOJ rate environment warrants caution for carry-funded EM positions. "
            "SCBGOLDE may benefit from yen-gold correlation if yen strengthens."
        )
    else:
        risk_lv = "low"
        rec = "No immediate carry-trade risk. Monitor BOJ meeting outcomes."

    return {
        "risk_level": risk_lv,
        "risk_score": score,
        "boj_rate": boj_rate,
        "usd_jpy_rate": usd_jpy_rate,
        "boj_hike_prob_pct": (round(min(max(float(boj_hike_prob_pct), 0.0), 100.0), 1)
                              if boj_hike_prob_pct is not None else None),
        "carry_threshold_breached": carry_breached,
        "components": {
            "rate": round(rate_component, 4),
            "jpy": round(jpy_component, 4),
            "hike_prob": prob_component,
        },
        "flags": flags,
        "recommendation": rec,
        "assessed_at": datetime.now(UTC).isoformat(),
    }


# ---------------------------------------------------------------------------
# PTTEP oil-scenario commodity risk — Added by nightly agent 2026-06-16
# ---------------------------------------------------------------------------
# Wires the oil_scenario model's downside into the portfolio risk picture so
# PTTEP's Brent exposure is scored, not just narrated in the brief.
# Self-contained (no cross-package import) and dependency-light by design.

# Brent band anchors (kept consistent with portfolio_engine/oil_scenario.py).
_OIL_DEAL_TARGET_USD = float(os.getenv("OIL_DEAL_TARGET_USD", "75.0"))   # likely floor if Iran deal signs
_OIL_DOWNSIDE_SPAN_USD = float(os.getenv("OIL_DOWNSIDE_SPAN_USD", "30.0"))  # gap that maps to full downside risk
_PTTEP_BREAKEVEN_USD = float(os.getenv("PTTEP_BREAKEVEN_USD", "45.0"))   # dividend-stress reference
_OIL_STRESS_FLOOR_USD = float(os.getenv("OIL_STRESS_FLOOR_USD", "60.0")) # below this, coverage risk rises


def oil_scenario_risk_flag(
    current_brent_usd: float,
    pttep_weight: float = 0.0,
    deal_confirmed: bool = False,
) -> dict[str, Any]:
    """
    Score PTTEP's Brent-crude downside risk and its contribution to the
    portfolio, derived from the same scenario logic the daily brief uses.

    Two components, combined and capped at 1.0:
      • Unwind risk: how far current Brent sits ABOVE the deal-signed floor
        (~$75). The larger the premium still embedded, the more there is to
        give back if/when the Iran deal's Hormuz reopening lands. Scaled up
        when the deal is confirmed (premium more likely to unwind).
      • Stress risk: below ~$60 Brent, dividend-coverage risk rises toward the
        ~$45 breakeven — a different downside that also warrants flagging.

    Args:
        current_brent_usd: latest Brent spot (USD/bbl).
        pttep_weight:      PTTEP.BK fraction of portfolio (0–1) for the
                           portfolio-level contribution figure.
        deal_confirmed:    True once the Iran deal is formally confirmed/signed
                           (raises the unwind weighting from 0.7x to 1.0x).

    Returns a dict with position_risk_score, portfolio_contribution,
    risk_level, components, and an advisory note.

    Added by nightly agent 2026-06-16
    """
    brent = max(float(current_brent_usd), 0.0)

    # Unwind component: premium above the deal floor that could deflate.
    gap_above_floor = max(brent - _OIL_DEAL_TARGET_USD, 0.0)
    unwind_raw = min(gap_above_floor / _OIL_DOWNSIDE_SPAN_USD, 1.0) if _OIL_DOWNSIDE_SPAN_USD > 0 else 0.0
    unwind = unwind_raw * (1.0 if deal_confirmed else 0.7)

    # Stress component: coverage risk as Brent approaches breakeven.
    if brent >= _OIL_STRESS_FLOOR_USD:
        stress = 0.0
    else:
        span = max(_OIL_STRESS_FLOOR_USD - _PTTEP_BREAKEVEN_USD, 1.0)
        stress = min(max((_OIL_STRESS_FLOOR_USD - brent) / span, 0.0), 1.0)

    position_risk = round(min(unwind + stress, 1.0), 4)
    contribution = round(position_risk * min(max(pttep_weight, 0.0), 1.0), 4)

    if position_risk >= 0.66:
        lv = "high"
    elif position_risk >= 0.33:
        lv = "elevated"
    else:
        lv = "low"

    if stress > 0:
        note = (
            f"Brent ${brent:.0f} is below the ${_OIL_STRESS_FLOOR_USD:.0f} stress floor — "
            f"PTTEP earnings/dividend coverage to watch (breakeven ~${_PTTEP_BREAKEVEN_USD:.0f})."
        )
    elif unwind_raw > 0:
        unwind_state = "confirmed" if deal_confirmed else "pending"
        note = (
            f"Brent ${brent:.0f} carries ~${gap_above_floor:.0f} of premium above the "
            f"~${_OIL_DEAL_TARGET_USD:.0f} deal-signed floor (Iran deal {unwind_state}); "
            "an earnings-growth headwind for PTTEP if oil unwinds, not a solvency risk."
        )
    else:
        note = (
            f"Brent ${brent:.0f} already near/below the deal-signed floor — limited further "
            "downside from premium unwind; PTTEP well above breakeven."
        )

    return {
        "ticker": "PTTEP.BK",
        "current_brent_usd": round(brent, 1),
        "deal_confirmed": deal_confirmed,
        "position_risk_score": position_risk,
        "portfolio_contribution": contribution,
        "risk_level": lv,
        "components": {"premium_unwind": round(unwind, 4), "coverage_stress": round(stress, 4)},
        "note": note,
        "assessed_at": datetime.now(UTC).isoformat(),
    }


# ---------------------------------------------------------------------------
# Lebanon-spillover Hormuz-reclosure tail — Added by nightly agent 2026-06-24
# ---------------------------------------------------------------------------
# Through Jun 23 the US-Iran NUCLEAR track de-risked (Swiss talks resumed, a
# roadmap was agreed, IAEA inspectors were invited back, the US granted Iran a
# 60-day oil-sales license, and Hormuz traffic picked up — Brent fell to a
# ~3-month low). But a SECOND, independent oil tail surfaced Jun 19-20: Iran's
# IRGC threatened to RE-CLOSE the Strait of Hormuz in retaliation for Israeli
# strikes in LEBANON — a regional-spillover channel decoupled from the nuclear
# negotiation. Until now that tail was merged into oil_scenario's "deal_collapses"
# case; this flag tracks it DISCRETELY so the Hormuz reclosure risk can be
# raised/lowered on Lebanon-front news ALONE, independent of how the nuclear
# talks read. Diagnostic only — it does not alter the blended portfolio score
# (consistent with the japan/oil/fed/gold flags).

# Brent level the EIA models if Hormuz re-closes (anchors the re-spike case).
_HORMUZ_RECLOSURE_BRENT_USD = float(os.getenv("HORMUZ_RECLOSURE_BRENT_USD", "105.0"))

# Discrete status ladder for the Lebanon -> Hormuz channel (probability proxy).
_LEBANON_STATUS_SCORES = {
    "dormant": 0.05,             # no active Lebanon-front escalation
    "walked_back": 0.12,         # threat surfaced then receded (traffic resuming)
    "threatened": 0.45,          # active IRGC reclosure threat, not executed
    "partial_disruption": 0.70,  # traffic slowing / selective interdiction
    "reclosed": 0.95,            # Strait effectively re-closed
}


def lebanon_spillover_flag(
    status: str = "walked_back",
    current_brent_usd: float = 77.0,
    pttep_weight: float = 0.0,
) -> dict[str, Any]:
    """
    Score the Lebanon-driven Strait-of-Hormuz reclosure tail as a DISCRETE risk,
    tracked independently of the US-Iran nuclear-talks status.

    Unlike oil_scenario_risk_flag (which scores PTTEP's PREMIUM-UNWIND downside as
    oil falls toward the deal floor), this flag scores the OPPOSITE tail: a sudden
    oil RE-SPIKE if the Lebanon front drags Iran into re-closing Hormuz. For Tho's
    PTTEP position that tail is asymmetrically POSITIVE (higher Brent lifts
    earnings/dividend), so the note frames it as a partial hedge — while it remains
    a broader portfolio/inflation risk (SET flows, baht, imported costs).

    Args:
        status:            one of dormant/walked_back/threatened/partial_disruption/
                           reclosed (matched case-insensitively; unknown -> walked_back).
        current_brent_usd: latest Brent spot, for the implied re-spike gap.
        pttep_weight:      PTTEP.BK fraction of portfolio (0-1) for the
                           position-level upside-sensitivity figure.

    Returns a dict with tail_probability_proxy (0-1), risk_level, the implied
    Brent re-spike gap, PTTEP directional read, and an advisory note.

    Added by nightly agent 2026-06-24
    """
    key = (status or "walked_back").lower().strip()
    proxy = _LEBANON_STATUS_SCORES.get(key, _LEBANON_STATUS_SCORES["walked_back"])
    brent = max(float(current_brent_usd), 0.0)

    respike_gap = round(max(_HORMUZ_RECLOSURE_BRENT_USD - brent, 0.0), 1)
    # PTTEP earnings upside if the reclosure-spike lands (reuses the oil model's
    # ~1.5% NI per $1 Brent elasticity around the $90 anchor).
    pttep_upside_ni_pct = round(respike_gap * 0.015 * 100, 1)
    position_upside = round(proxy * min(max(pttep_weight, 0.0), 1.0), 4)

    if proxy >= 0.66:
        lv = "high"
    elif proxy >= 0.33:
        lv = "elevated"
    else:
        lv = "low"

    notes = {
        "dormant": "No active Lebanon-front escalation — the Hormuz-reclosure tail is dormant.",
        "walked_back": (
            "The Jun 19-20 IRGC Hormuz-reclosure THREAT (over Israeli strikes in Lebanon) is "
            "receding: Hormuz traffic is picking up, the US granted Iran a 60-day oil-sales "
            "license, and Brent fell to a ~3-month low. The tail is LOW but kept live and "
            "DISCRETE — it can re-arm on Lebanon-front news alone, independent of the nuclear track."
        ),
        "threatened": (
            "ACTIVE IRGC reclosure threat tied to the Lebanon front — not yet executed. A "
            f"reclosure would re-spike Brent toward the EIA's ~${_HORMUZ_RECLOSURE_BRENT_USD:.0f} anchor."
        ),
        "partial_disruption": (
            "Hormuz traffic slowing / selective interdiction tied to the Lebanon front — an oil "
            "re-spike is underway; watch tanker-transit counts and war-risk insurance rates."
        ),
        "reclosed": (
            f"Strait effectively RE-CLOSED — Brent re-spike toward/above the EIA ~${_HORMUZ_RECLOSURE_BRENT_USD:.0f} "
            "anchor; a broad inflation/EM headwind but a direct PTTEP earnings tailwind."
        ),
    }

    pttep_dir = (
        f"PTTEP UPSIDE hedge: a reclosure re-spike (~${_HORMUZ_RECLOSURE_BRENT_USD:.0f} Brent, "
        f"+${respike_gap:.0f} vs ${brent:.0f}) implies ~{pttep_upside_ni_pct:+.0f}% PTTEP net income "
        "vs base — the position partly hedges this geopolitical tail."
    )

    return {
        "channel": "lebanon_hormuz_reclosure",
        "status": key,
        "tail_probability_proxy": proxy,
        "risk_level": lv,
        "current_brent_usd": round(brent, 1),
        "hormuz_reclosure_brent_anchor_usd": _HORMUZ_RECLOSURE_BRENT_USD,
        "implied_respike_gap_usd": respike_gap,
        "pttep_position_upside": position_upside,
        "pttep_directional": pttep_dir,
        "note": notes.get(key, notes["walked_back"]),
        "decoupled_from_nuclear_talks": True,
        "assessed_at": datetime.now(UTC).isoformat(),
    }


# ---------------------------------------------------------------------------
# US Fed / FOMC policy risk monitor — Added by nightly agent 2026-06-18
# ---------------------------------------------------------------------------
# A hawkish Fed (higher-for-longer, or a dot-plot that adds hikes) lifts real
# US yields and the dollar. For Tho's book that is a two-sided headwind: it
# pressures the non-yielding gold fund (SCBGOLDE) and it tends to weaken the
# baht / pull foreign flows out of SET. This flag turns the FOMC outcome into a
# concrete diagnostic instead of a free-text note in the brief.

# Neutral anchor for the Fed funds midpoint (%). Above this, policy is
# restrictive enough to weigh on gold/EM; the dot-plot bias then amplifies it.
_FED_NEUTRAL_RATE_PCT = float(os.getenv("FED_NEUTRAL_RATE_PCT", "3.0"))
_FED_RESTRICTIVE_SPAN_PCT = float(os.getenv("FED_RESTRICTIVE_SPAN_PCT", "2.0"))


def fed_policy_risk_flag(
    fed_funds_rate_pct: float,
    dot_plot_bias: str = "neutral",
    hike_prob_pct: float | None = None,
) -> dict[str, Any]:
    """
    Score the headwind US monetary policy poses to gold and the baht-denominated
    EM book, from the realised Fed funds rate and the dot-plot's forward bias.

    Two core components, combined and capped at 1.0:
      • Level: how far the funds-rate midpoint sits above the ~3.0% neutral
        anchor (restrictive policy = real-yield drag on gold, USD strength).
      • Bias: the dot-plot's signalled direction — "hawkish"/"hike" (easing bias
        removed or hikes added) adds risk; "dovish"/"cut" subtracts it.

    Optional refinement (Added by nightly agent 2026-06-27):
      • Market-implied hike probability: when `hike_prob_pct` is supplied (the
        market-priced odds of a hike at the next decision, e.g. fed-funds
        futures), the bias bump is grounded in that number instead of a
        free-text guess. The probability scales a +0.0–+0.40 component
        (100% ⇒ full +0.40) and can only SHARPEN — never soften — an already
        hawkish read. This makes the flag robust when `dot_plot_bias` is vague
        or stale: an 80%-priced December hike registers as a concrete headwind
        even if the text bias is merely "neutral".

    Args:
        fed_funds_rate_pct: realised funds-rate midpoint (e.g. 3.625).
        dot_plot_bias:      free-text bias; matched case-insensitively on
                            hawkish/hike/restrictive vs dovish/cut/easing.
        hike_prob_pct:      optional market-implied probability (0–100) of a hike
                            at the next meeting; if None, falls back to the
                            text-only bias (fully backward compatible).

    Returns a dict with risk_level, risk_score, components, flags, and an
    advisory note framed for a medium-term holder.

    Added by nightly agent 2026-06-18
    """
    rate = max(float(fed_funds_rate_pct), 0.0)
    bias = (dot_plot_bias or "neutral").lower()
    flags: list[str] = []

    # --- Level component (0.0 – 0.6) ---
    gap = max(rate - _FED_NEUTRAL_RATE_PCT, 0.0)
    level = min(gap / _FED_RESTRICTIVE_SPAN_PCT, 1.0) * 0.60 if _FED_RESTRICTIVE_SPAN_PCT > 0 else 0.0
    if rate > _FED_NEUTRAL_RATE_PCT:
        flags.append(
            f"Fed funds ({rate:.3f}%) above the ~{_FED_NEUTRAL_RATE_PCT:.1f}% neutral anchor "
            "— restrictive policy is a real-yield drag on gold and the baht."
        )

    # --- Bias component (-0.20 – +0.40) ---
    if any(k in bias for k in ("hawk", "hike", "restrict", "higher")):
        bias_component = 0.40
        flags.append(
            "Dot-plot bias HAWKISH (easing bias removed / hikes added) — "
            "near-term headwind for gold and EM/SET flows."
        )
    elif any(k in bias for k in ("dov", "cut", "eas", "lower")):
        bias_component = -0.20
        flags.append("Dot-plot bias DOVISH (cuts signalled) — supportive for gold/EM.")
    else:
        bias_component = 0.0

    # --- Market-implied hike-probability refinement (Added by nightly agent 2026-06-27) ---
    # Ground the hawkish bump in market pricing when available. The probability
    # scales 0.0–0.40 (100% ⇒ +0.40) and can only sharpen — never soften — an
    # already hawkish text read, so it never cancels a genuine dovish signal.
    prob_component = None
    if hike_prob_pct is not None:
        prob = min(max(float(hike_prob_pct), 0.0), 100.0)
        prob_component = round((prob / 100.0) * 0.40, 4)
        if bias_component >= 0.0:
            # neutral/hawkish text: let the priced odds set the floor of the bump
            if prob_component > bias_component:
                flags.append(
                    f"Market prices a {prob:.0f}% hike at the next meeting — "
                    "concrete real-yield headwind for gold/baht (sharpens the bias read)."
                )
            bias_component = max(bias_component, prob_component)
        else:
            # dovish text but the market still prices a hike: surface the tension,
            # net the dovish cut against the priced-hike pressure (never below the
            # dovish floor) so a credible repricing isn't ignored.
            flags.append(
                f"Text bias dovish yet the market prices a {prob:.0f}% hike — "
                "watch for a hawkish repricing."
            )
            bias_component = max(bias_component, bias_component + prob_component)

    score = round(min(max(level + bias_component, 0.0), 1.0), 4)

    if score >= 0.66:
        risk_lv = "high"
        rec = (
            "Restrictive Fed + hawkish guidance is a live headwind for SCBGOLDE and "
            "baht assets. Avoid adding to gold on strength; favour the SET dividend "
            "names (SCB ~7.5% yield) whose carry cushions higher-for-longer."
        )
    elif score >= 0.33:
        risk_lv = "elevated"
        rec = (
            "Policy is moderately restrictive. Gold's medium-term thesis is intact but "
            "expect rate-driven volatility; let the position ride rather than chase it."
        )
    else:
        risk_lv = "low"
        rec = "Fed stance is not a material headwind for gold/EM at current levels."

    return {
        "risk_level": risk_lv,
        "risk_score": score,
        "fed_funds_rate_pct": round(rate, 3),
        "dot_plot_bias": dot_plot_bias,
        "hike_prob_pct": (round(min(max(float(hike_prob_pct), 0.0), 100.0), 1)
                          if hike_prob_pct is not None else None),
        "components": {
            "rate_level": round(level, 4),
            "bias": round(bias_component, 4),
            "hike_prob": prob_component,
        },
        "flags": flags,
        "recommendation": rec,
        "assessed_at": datetime.now(UTC).isoformat(),
    }


# ---------------------------------------------------------------------------
# Gold-fund drawdown monitor — Added by nightly agent 2026-06-20
# ---------------------------------------------------------------------------
# The gold fund (SCBGOLDE) is Tho's only non-yielding, FX-exposed position, so a
# falling NAV is the holding most likely to trigger a "should I sell?" reaction.
# But not all drawdowns are equal: a pullback driven by a hawkish Fed / stronger
# dollar (real-yield repricing) is a HOLD/ADD situation for a medium-term holder
# — the long-run thesis (GS $5,400 / JPM ~$6,000) is intact — whereas a drawdown
# with NO policy driver may signal a genuine demand/trend break worth trimming.
# This monitor measures drawdown from a trailing high and cross-references the
# live fed_policy_risk_flag to label which kind of dip it is. Diagnostic only —
# it does not alter the blended portfolio score (consistent with the other flags).

# Drawdown thresholds (% from trailing high)
_GOLD_DIP_THRESHOLD_PCT = float(os.getenv("GOLD_DIP_THRESHOLD_PCT", "5.0"))
_GOLD_BREAK_THRESHOLD_PCT = float(os.getenv("GOLD_BREAK_THRESHOLD_PCT", "12.0"))


def gold_drawdown_monitor(
    current_level: float,
    trailing_high: float,
    fed_policy_risk: dict[str, Any] | None = None,
    dip_threshold_pct: float = _GOLD_DIP_THRESHOLD_PCT,
    break_threshold_pct: float = _GOLD_BREAK_THRESHOLD_PCT,
) -> dict[str, Any]:
    """
    Classify a gold / gold-fund drawdown as Fed-driven (hold/add) vs a possible
    trend break (review/trim), by combining the drawdown depth from a trailing
    high with the current Fed-policy risk reading.

    `current_level` and `trailing_high` may be gold-fund NAV (THB) or gold spot
    (USD) — the ratio is unit-free, so use whichever series is available. Pass
    the output of `fed_policy_risk_flag()` as `fed_policy_risk` to enable the
    policy-driver cross-reference; omit it to get a depth-only read.

    Classifications:
      • stable             — drawdown below the dip threshold; no action.
      • fed_driven_dip     — meaningful drawdown WHILE Fed policy is restrictive
                             → most likely a real-yield/USD repricing, not a
                             demand break. HOLD; dips can be add zones.
      • demand_softness_watch — meaningful drawdown with NO policy driver →
                             monitor; the move lacks an obvious macro cause.
      • deep_fed_dip       — drawdown past the break threshold but still under a
                             restrictive Fed → likely policy-driven yet large
                             enough to warrant a position-size review.
      • trend_break_watch  — drawdown past the break threshold with NO policy
                             driver → the highest-attention case; review thesis.

    Added by nightly agent 2026-06-20
    """
    high = max(float(trailing_high), 0.0)
    cur = max(float(current_level), 0.0)
    drawdown_pct = round((high - cur) / high * 100, 2) if high > 0 else 0.0
    drawdown_pct = max(drawdown_pct, 0.0)  # only count downside from the high

    fed_level = str((fed_policy_risk or {}).get("risk_level", "")).lower()
    fed_restrictive = fed_level in ("elevated", "high")
    fed_score = (fed_policy_risk or {}).get("risk_score")

    if drawdown_pct < dip_threshold_pct:
        classification = "stable"
        signal = "hold"
        note = (
            f"Gold fund {drawdown_pct:.1f}% off its trailing high — within normal "
            "noise. No action; the medium-term thesis is unaffected."
        )
    elif drawdown_pct < break_threshold_pct:
        if fed_restrictive:
            classification = "fed_driven_dip"
            signal = "hold_or_add"
            note = (
                f"Gold fund down {drawdown_pct:.1f}% from its trailing high WHILE the "
                f"Fed is restrictive (fed_policy_risk {fed_level}). This reads as a "
                "real-yield / stronger-USD repricing, not a demand break — the kind "
                "of dip a medium-term holder rides or adds into. GS $5,400 / JPM "
                "~$6,000 targets intact."
            )
        else:
            classification = "demand_softness_watch"
            signal = "monitor"
            note = (
                f"Gold fund down {drawdown_pct:.1f}% with NO clear Fed driver "
                f"(fed_policy_risk {fed_level or 'n/a'}). Cause is less obvious — "
                "monitor for a demand/positioning shift before adding."
            )
    else:
        if fed_restrictive:
            classification = "deep_fed_dip"
            signal = "hold_review"
            note = (
                f"Gold fund down {drawdown_pct:.1f}% — a deep move, but the Fed is "
                f"restrictive ({fed_level}), so it is most likely policy-driven. "
                "Hold, but review position sizing given the depth."
            )
        else:
            classification = "trend_break_watch"
            signal = "reduce_review"
            note = (
                f"Gold fund down {drawdown_pct:.1f}% from its trailing high with NO "
                "policy driver — the highest-attention case. Re-examine the thesis "
                "and consider trimming if the trend persists."
            )

    return {
        "classification": classification,
        "signal": signal,
        "drawdown_pct": drawdown_pct,
        "trailing_high": round(high, 4),
        "current_level": round(cur, 4),
        "dip_threshold_pct": dip_threshold_pct,
        "break_threshold_pct": break_threshold_pct,
        "fed_policy_risk_level": fed_level or None,
        "fed_policy_risk_score": fed_score,
        "note": note,
        "assessed_at": datetime.now(UTC).isoformat(),
    }


# ---------------------------------------------------------------------------
# Auto-derived gold trailing-high — Added by nightly agent 2026-06-21
# ---------------------------------------------------------------------------
# Replaces the static `gold_recent_high_usd` watchlist field with a rolling
# N-day max read from the daily snapshot archive (data/snapshots/*.json), so
# the drawdown monitor's trailing high self-updates as snapshots accumulate
# instead of needing a hand-edited watchlist value each night. Until the
# archive has data it returns None and the caller falls back to the watchlist
# value, so this is safe on an empty archive.

_GOLD_TRAILING_WINDOW_DAYS = int(os.getenv("GOLD_TRAILING_WINDOW_DAYS", "60"))


def derive_gold_trailing_high(window_days: int = _GOLD_TRAILING_WINDOW_DAYS) -> float | None:
    """
    Compute the rolling max of the archived gold level over the last
    ``window_days`` daily snapshots in data/snapshots/.

    Reads the ``gold_drawdown_current_level`` field archived by
    save_daily_performance(); that value is in the SAME unit the drawdown
    monitor used that day (gold spot USD, or fund NAV THB if a NAV trailing
    high was configured). Returns the max, or None if no archived levels exist.
    Diagnostic only — never raises.
    """
    try:
        snap_dir = PROJECT_DIR / "data" / "snapshots"
        if not snap_dir.is_dir():
            return None
        files = sorted(
            (p for p in snap_dir.glob("*.json") if p.stem[:4].isdigit()),
            key=lambda p: p.stem,
        )[-max(window_days, 1):]
        levels: list[float] = []
        for p in files:
            try:
                payload = json.loads(p.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue
            lvl = payload.get("gold_drawdown_current_level")
            if isinstance(lvl, (int, float)) and lvl > 0:
                levels.append(float(lvl))
        return round(max(levels), 4) if levels else None
    except Exception:
        logger.warning("derive_gold_trailing_high failed — skipping", exc_info=True)
        return None


def snapshot_path() -> Path:
    configured = os.getenv(
        "PORTFOLIO_SNAPSHOT_PATH", "data_collector/portfolio_snapshot.json"
    )
    path = Path(configured)
    return path if path.is_absolute() else PROJECT_DIR / path


def _build_snapshot_archive_payload(
    snapshot: dict[str, Any], risk: dict[str, Any]
) -> dict[str, Any]:
    """
    Build the data/snapshots/YYYY-MM-DD.json archive payload from a portfolio
    snapshot dict and a calculate_portfolio_risk() result.

    Added by nightly agent 2026-06-22: extracted from save_daily_performance()
    so both the Postgres-backed nightly path AND the standalone
    archive_daily_snapshot() runner produce an identical archive payload (DRY).
    """
    return {
        **snapshot,
        "risk_score": risk["portfolio_risk_score"],
        "risk_level": risk["risk_level"],
        "currency_risk_score": risk.get("currency_risk_score"),
        "usd_thb_rate": risk.get("usd_thb_rate"),
        # THB currency-regime diagnostic (nightly agent 2026-06-25)
        "currency_regime_level": (risk.get("currency_regime") or {}).get("risk_level"),
        "currency_regime_break": (risk.get("currency_regime") or {}).get("regime_break"),
        "baht_vs_neutral_pct": (risk.get("currency_regime") or {}).get("baht_vs_neutral_pct"),
        "concentrated_positions": risk.get("concentrated_positions", []),
        # PTTEP oil-scenario risk + Japan carry risk (nightly agent 2026-06-17)
        "oil_commodity_risk": (risk.get("oil_commodity_risk") or {}).get("position_risk_score"),
        "oil_commodity_risk_level": (risk.get("oil_commodity_risk") or {}).get("risk_level"),
        "japan_carry_risk_level": (risk.get("japan_carry_risk") or {}).get("risk_level"),
        # FOMC policy-risk diagnostic (nightly agent 2026-06-18)
        "fed_policy_risk_level": (risk.get("fed_policy_risk") or {}).get("risk_level"),
        "fed_policy_risk_score": (risk.get("fed_policy_risk") or {}).get("risk_score"),
        # Gold-fund drawdown classification + depth (nightly agent 2026-06-20)
        "gold_drawdown_classification": (risk.get("gold_drawdown") or {}).get("classification"),
        "gold_drawdown_pct": (risk.get("gold_drawdown") or {}).get("drawdown_pct"),
        "gold_drawdown_signal": (risk.get("gold_drawdown") or {}).get("signal"),
        # Gold level for the self-updating rolling high (nightly agent 2026-06-21)
        "gold_drawdown_current_level": (risk.get("gold_drawdown") or {}).get("current_level"),
        # Lebanon-spillover Hormuz-reclosure tail (nightly agent 2026-06-24)
        "lebanon_spillover_status": (risk.get("lebanon_spillover") or {}).get("status"),
        "lebanon_spillover_risk_level": (risk.get("lebanon_spillover") or {}).get("risk_level"),
        "lebanon_spillover_proxy": (risk.get("lebanon_spillover") or {}).get("tail_probability_proxy"),
    }


def _shared_save_daily_snapshot():
    """Load the stdlib-only archiver from the project root by file path.

    Fixed 2026-10-29 (Phase 2): the old ``from portfolio_engine.performance_analytics
    import save_daily_snapshot`` raised ModuleNotFoundError in the ai_engine process
    (and would pick up the wrong ``utils`` package even if found).
    """
    import importlib.util
    from pathlib import Path as _P

    path = _P(__file__).resolve().parent.parent / "snapshot_archive.py"
    spec = importlib.util.spec_from_file_location("ia_snapshot_archive", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module.save_daily_snapshot



async def archive_daily_snapshot() -> dict[str, Any]:
    """
    Standalone nightly snapshot writer — fills data/snapshots/YYYY-MM-DD.json
    WITHOUT touching Postgres.

    Added by nightly agent 2026-06-22 to resolve the long-standing queued item:
    save_daily_performance() archives the snapshot only AFTER a Postgres write
    (db_pool + portfolio_performance UPSERT). When the DB is unavailable on a
    nightly run, that path raises before the archive line, so data/snapshots/
    never fills and derive_gold_trailing_high() / the multi-day drawdown trend
    stay inert. This function computes risk + reads the portfolio snapshot JSON
    and writes the archive directly, so the trend store fills regardless of DB
    state. calculate_portfolio_risk() itself queries the DB for the live
    USD/THB rate but degrades gracefully to watchlist values on failure.

    Returns a small summary dict (path, risk score/level, gold drawdown).
    """
    risk = await calculate_portfolio_risk()
    path = snapshot_path()
    snapshot = json.loads(path.read_text(encoding="utf-8"))

    save_daily_snapshot = _shared_save_daily_snapshot()  # Fixed 2026-10-29: no cross-package import

    archive_payload = _build_snapshot_archive_payload(snapshot, risk)
    archive_path = save_daily_snapshot(archive_payload)
    logger.info("Standalone daily snapshot archived to %s (no DB write)", archive_path)
    return {
        "archive_path": str(archive_path),
        "risk_score": risk["portfolio_risk_score"],
        "risk_level": risk["risk_level"],
        "gold_drawdown": risk.get("gold_drawdown"),
        "db_write": False,
    }


async def save_daily_performance() -> dict[str, Any]:
    risk = await calculate_portfolio_risk()
    path = snapshot_path()
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    total_value = float(snapshot.get("total_market_value_thb", 0))
    daily_pnl = float(snapshot.get("daily_pnl", snapshot.get("total_pnl_thb", 0)))
    daily_pnl_pct = float(snapshot.get("daily_pnl_pct", 0))
    unrealized = float(snapshot.get("total_pnl_thb", daily_pnl))
    pool = await db_pool.get_pool()
    await pool.execute(
        """
        WITH updated AS (
            UPDATE portfolio_performance SET
                total_value_thb = $1, daily_pnl = $2, daily_pnl_pct = $3,
                unrealized_pnl = $4, risk_score = $5, snapshot = $6::jsonb,
                created_at = NOW()
            WHERE record_date = CURRENT_DATE
            RETURNING id
        )
        INSERT INTO portfolio_performance (
            record_date, total_value_thb, daily_pnl, daily_pnl_pct,
            unrealized_pnl, risk_score, snapshot
        )
        SELECT CURRENT_DATE, $1, $2, $3, $4, $5, $6::jsonb
        WHERE NOT EXISTS (SELECT 1 FROM updated)
        """,
        total_value, daily_pnl, daily_pnl_pct, unrealized,
        risk["portfolio_risk_score"], json.dumps(snapshot),
    )
    logger.info("Daily performance saved with risk score %.4f", risk["portfolio_risk_score"])

    # --- Archive daily snapshot to data/snapshots/YYYY-MM-DD.json ---
    # Added by nightly agent 2026-06-11: wire save_daily_snapshot() so every
    # nightly run builds a cumulative archive for trend/drawdown analysis.
    try:
        save_daily_snapshot = _shared_save_daily_snapshot()  # Fixed 2026-10-29: no cross-package import
        # Refactored 2026-06-22: payload now built by the shared helper so the
        # standalone archive_daily_snapshot() runner stays byte-for-byte in sync.
        archive_payload = _build_snapshot_archive_payload(snapshot, risk)
        archive_path = save_daily_snapshot(archive_payload)
        logger.info("Daily portfolio snapshot archived to %s", archive_path)
    except Exception:
        logger.warning("Could not archive daily snapshot — will retry next run", exc_info=True)

    return {"records_saved": 1, **risk}


# Added by nightly agent 2026-06-22: standalone entrypoint so the scheduler can
# fill data/snapshots/ even when Postgres is down, e.g.
#   python -m ai_engine.risk_scorer            → DB-free archive (default)
#   python -m ai_engine.risk_scorer --with-db  → full save_daily_performance()
if __name__ == "__main__":
    import asyncio
    import sys

    async def _main() -> None:
        if "--with-db" in sys.argv:
            result = await save_daily_performance()
            print("save_daily_performance:", result.get("portfolio_risk_score"))
        else:
            result = await archive_daily_snapshot()
            print("archive_daily_snapshot ->", result["archive_path"])
            print("  risk:", result["risk_level"], result["risk_score"])
            gd = result.get("gold_drawdown") or {}
            if gd:
                print("  gold_drawdown:", gd.get("classification"), gd.get("drawdown_pct"))

    asyncio.run(_main())
