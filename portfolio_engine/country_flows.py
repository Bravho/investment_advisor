"""Cross-border country-allocation pressure monitor (shadow/context only).

The lead score is separate from observed foreign flow. Using today's SET net
buying to predict today's buying would be leakage, so it is confirmation only.
Nothing here changes signals, forecasts, weights, or trade plans.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Mapping, Optional

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "country_flow_model.json"


def _finite(value: Any) -> Optional[float]:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def lead_score(features: Mapping[str, Any], config: Optional[Mapping[str, Any]] = None) -> dict[str, Any]:
    """Combine normalized [-100, 100] point-in-time features without leakage."""
    cfg = dict(config or load_config())
    weights = cfg["lead_weights"]
    used = {name: max(-100.0, min(100.0, number)) for name in weights
            if (number := _finite(features.get(name))) is not None}
    available = sum(float(weights[name]) for name in used)
    total = sum(float(value) for value in weights.values())
    coverage = available / total if total else 0.0
    score = sum(float(weights[name]) * value for name, value in used.items()) / available if available else None
    rules = cfg["rules"]
    if score is None or coverage < float(rules["minimum_lead_coverage"]):
        label = "insufficient_data"
    elif score >= float(rules["strong_score"]):
        label = "strong_inflow_pressure"
    elif score >= float(rules["moderate_score"]):
        label = "moderate_inflow_pressure"
    elif score <= -float(rules["strong_score"]):
        label = "strong_outflow_pressure"
    elif score <= -float(rules["moderate_score"]):
        label = "moderate_outflow_pressure"
    else:
        label = "balanced"
    return {"score": round(score, 2) if score is not None else None, "label": label,
            "coverage": round(coverage, 3), "components": used,
            "horizon": cfg["horizon"], "status": cfg["status"]}


def confirmation_label(daily_flow_bn: Any, five_day_flow_bn: Any,
                       config: Optional[Mapping[str, Any]] = None) -> str:
    rules = dict(config or load_config())["rules"]
    daily, five = _finite(daily_flow_bn), _finite(five_day_flow_bn)
    day_cut, five_cut = float(rules["flow_confirmation_daily_thb_bn"]), float(rules["flow_confirmation_5d_thb_bn"])
    if daily is None and five is None:
        return "unavailable"
    if (daily is not None and daily >= day_cut) or (five is not None and five >= five_cut):
        return "observed_net_buying"
    if (daily is not None and daily <= -day_cut) or (five is not None and five <= -five_cut):
        return "observed_net_selling"
    return "mixed_or_small"


def _scaled(value: Any, scale: float, invert: bool = False) -> Optional[float]:
    number = _finite(value)
    if number is None:
        return None
    result = max(-100.0, min(100.0, number / scale * 100.0))
    return -result if invert else result


async def thailand_report(pool: Any) -> dict[str, Any]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT key, reading, change_1d, change_5d, as_of, stale, details
               FROM market_factors WHERE key = ANY($1::text[])""",
            ["set_foreign_flow", "usdthb", "vix", "fed_rate", "bot_rate", "brent"],
        )
        hist5 = await conn.fetchval(
            """SELECT sum(reading) FROM (SELECT reading FROM market_factor_history
               WHERE key='set_foreign_flow' ORDER BY as_of DESC LIMIT 5) x"""
        )
        regime_inputs = await conn.fetchval(
            "SELECT inputs FROM market_regime ORDER BY as_of DESC LIMIT 1"
        ) or {}
    factors = {row["key"]: dict(row) for row in rows if not row["stale"]}
    fed = _finite(factors.get("fed_rate", {}).get("reading"))
    bot = _finite(factors.get("bot_rate", {}).get("reading"))
    vix = _finite(factors.get("vix", {}).get("reading")) or _finite(regime_inputs.get("vix"))
    set_above = regime_inputs.get("TDEX.BK_above_sma200")
    spy_above = regime_inputs.get("SPY_above_sma200")
    relative_momentum = None
    if isinstance(set_above, bool) and isinstance(spy_above, bool):
        relative_momentum = float((int(set_above) - int(spy_above)) * 100)
    features = {
        "fx_trend": _scaled(factors.get("usdthb", {}).get("change_5d"), 2.0, invert=True),
        "global_risk_appetite": _scaled((vix - 20.0) if vix is not None else None, 10.0, invert=True),
        "rate_carry": _scaled((bot - fed) if bot is not None and fed is not None else None, 3.0),
        "commodity_terms_of_trade": _scaled(factors.get("brent", {}).get("change_5d"), 8.0, invert=True),
        "relative_equity_momentum": relative_momentum,
        "growth_and_earnings_revision": None,
    }
    lead = lead_score(features)
    daily = _finite(factors.get("set_foreign_flow", {}).get("reading"))
    return {
        "country": "Thailand", "asset_channel": "listed_equity", "lead": lead,
        "observed_flow": {"daily_thb_bn": daily,
                          "five_session_thb_bn": round(float(hist5), 3) if hist5 is not None else None,
                          "label": confirmation_label(daily, hist5)},
        "limitations": [
            "Relative SET momentum is a coarse SMA200 state comparison; point-in-time growth/earnings revisions are not yet wired.",
            "Rate carry is nominal, not expected real carry or FX-hedged return.",
            "SET flow cannot represent bonds, FDI, bank flows or resident investment abroad."
        ],
        "use": "context/shadow only; no effect on signals, forecasts, portfolio weights or trade plans"
    }


def advisor_context(report: Mapping[str, Any]) -> str:
    lead, observed = report.get("lead", {}), report.get("observed_flow", {})
    components = ", ".join(f"{k}={v:+.0f}" for k, v in (lead.get("components") or {}).items()) or "none"
    return "\n".join([
        "=== CROSS-BORDER COUNTRY FLOW PRESSURE (SHADOW / CONTEXT ONLY) ===",
        f"Thailand listed equity, {lead.get('horizon', '5-20 sessions')}: {lead.get('label', 'unknown')} "
        f"(lead score {lead.get('score')}, coverage {100 * float(lead.get('coverage') or 0):.0f}%).",
        f"Lead components (-100..100): {components}.",
        f"Observed SET foreign flow, confirmation only: {observed.get('daily_thb_bn')} THB bn day; "
        f"{observed.get('five_session_thb_bn')} THB bn / 5 sessions; {observed.get('label', 'unknown')}.",
        "Do not call this a forecast when coverage is insufficient or infer bond/FDI flows from SET equity flow.",
        "Use it to qualify Thai-index/SCB/ThaiESG advice and FX risk; never override frozen forecasts or owner-hold rules."
    ])
