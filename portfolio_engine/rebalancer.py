from __future__ import annotations
import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from utils.common import (
    configure_logging,
    json_dumps,
    latest_price,
    load_snapshot,
    ollama_chat,
    save_recommendation,
)
from utils.db_pool import db_pool

PROJECT_DIR = Path(__file__).resolve().parent.parent
AI_ENGINE_DIR = PROJECT_DIR / "ai_engine"
if str(AI_ENGINE_DIR) not in sys.path:
    sys.path.append(str(AI_ENGINE_DIR))

logger = configure_logging("portfolio_engine.rebalancer")
UTC = timezone.utc
MODEL = os.getenv("OLLAMA_ADVISORY_MODEL", "hermes3:8b")


def target_allocations() -> dict[str, float]:
    default = '{"equity":0.50,"crypto":0.15,"bond":0.25,"cash":0.10}'
    try:
        values = json.loads(os.getenv("TARGET_ALLOCATIONS", default))
        return {str(key).lower(): float(value) for key, value in values.items()}
    except (TypeError, ValueError, json.JSONDecodeError):
        logger.exception("Invalid TARGET_ALLOCATIONS; using defaults")
        return json.loads(default)


def _snapshot_price(snapshot: dict[str, Any], ticker: str) -> float:
    item = snapshot.get("holdings", {}).get(ticker, {})
    if not isinstance(item, dict):
        return 0.0
    for key in ("current_price", "price", "market_price", "close_price"):
        if item.get(key) is not None:
            return float(item[key])
    return 0.0


def _snapshot_value(snapshot: dict[str, Any], ticker: str) -> float:
    item = snapshot.get("holdings", {}).get(ticker, {})
    return float(item.get("market_value_thb") or 0) if isinstance(item, dict) else 0.0


def _as_of_date(value: Any) -> Any:
    try:
        return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


async def _holding_mark(pool: Any, snapshot: dict[str, Any], ticker: str) -> tuple[float, Any, str]:
    item = snapshot.get("holdings", {}).get(ticker, {})
    if isinstance(item, dict):
        price = _snapshot_price(snapshot, ticker)
        as_of = _as_of_date(item.get("price_as_of") or item.get("as_of"))
        if price and as_of:
            return price, as_of, str(item.get("price_source") or "portfolio snapshot")
    row = await pool.fetchrow(
        "SELECT close_price, price_date FROM market_prices WHERE ticker=$1 ORDER BY price_date DESC LIMIT 1",
        ticker,
    )
    if row and row["close_price"] is not None and float(row["close_price"]) != 0:
        return float(row["close_price"]), _as_of_date(row["price_date"]), "market_prices"
    return _snapshot_price(snapshot, ticker), None, "unknown"


async def generate_rebalancing_plan() -> dict[str, Any]:
    pool = await db_pool.get_pool()
    holdings = await pool.fetch(
        "SELECT ticker, name, asset_class, quantity, avg_cost_price, currency FROM holdings ORDER BY ticker"
    )
    snapshot = load_snapshot()
    from holding_meta import is_pending, load_attrs, locked_tickers
    attrs = await load_attrs(pool)
    locked = locked_tickers(attrs)  # ThaiESG etc.: never a sell/switch/trim candidate before lock_until (2026-10-30)
    # 2026-10-31: owner holds (PTTEP.BK, SCB.BK) - Tho will not sell until satisfied with the project -> never a sell candidate.
    from holding_meta import owner_hold_tickers
    owner_holds = owner_hold_tickers()
    locked = set(locked) | owner_holds
    base_currency = snapshot.get("base_currency", os.getenv("BASE_CURRENCY", "THB"))
    values_by_class: dict[str, float] = defaultdict(float)
    positions: list[dict[str, Any]] = []
    stale_marks: list[dict[str, Any]] = []

    for row in holdings:
        ticker = row["ticker"]
        price, price_as_of, price_source = await _holding_mark(pool, snapshot, ticker)
        mark_age = (date.today() - price_as_of).days if price_as_of is not None else None
        mark_fresh = bool(price > 0 and mark_age is not None and mark_age <= 7)
        value = _snapshot_value(snapshot, ticker) or float(row["quantity"] or 0) * price
        if not value and is_pending(attrs.get(ticker)):
            value = float(attrs[ticker].get("amount_invested_thb") or 0)  # units pending -> amount invested
        asset_class = str(row["asset_class"] or "other").lower()
        values_by_class[asset_class] += value
        positions.append({**dict(row), "price": price, "value_thb": value, "asset_class": asset_class,
                          "price_as_of": str(price_as_of) if price_as_of else None,
                          "price_source": price_source, "mark_fresh": mark_fresh})
        if not mark_fresh:
            stale_marks.append({"ticker": ticker, "status": "unknown", "price_as_of": str(price_as_of) if price_as_of else None,
                                "reason": "mark is older than 7 calendar days" if mark_age is not None else "mark date is unknown"})

    total_value = sum(values_by_class.values())
    targets = target_allocations()
    current = {
        asset_class: round(values_by_class.get(asset_class, 0) / total_value, 4) if total_value else 0.0
        for asset_class in sorted(set(targets) | set(values_by_class))
    }
    threshold = float(os.getenv("REBALANCE_THRESHOLD", "0.05"))
    trades: list[dict[str, Any]] = []

    for asset_class, target in targets.items():
        drift = current.get(asset_class, 0.0) - target
        if abs(drift) <= threshold or total_value <= 0:
            continue
        action = "sell" if drift > 0 else "buy"
        amount = abs(drift) * total_value
        candidates = [position for position in positions if position["asset_class"] == asset_class and position["mark_fresh"]
                      and not (action == "sell" and position["ticker"] in locked)]
        class_positions = [position for position in positions if position["asset_class"] == asset_class]
        if not candidates and class_positions and any(not position["mark_fresh"] for position in class_positions):
            # The drift can still be displayed, but no amount is sized from an
            # unknown/stale mark for the holding that would implement it.
            continue
        if not candidates and action == "sell" and any(p["asset_class"] == asset_class for p in positions):
            trades.append(
                {
                    "ticker": asset_class.upper(),
                    "action": "hold",
                    "amount_thb": 0.0,
                    "reason": f"{asset_class} is overweight by {drift:+.1%} (INFORMATIONAL) but every holding in it is tax-locked or an owner hold "
                              f"({', '.join(sorted(t for t in locked if any(p['ticker'] == t for p in positions)))}); no sell suggested",
                    "sentiment_conflict": False,
                    "validated": False,
                    "tradable": False,
                    "confidence": 0.0,
                }
            )
            continue
        if not candidates:
            trades.append(
                {
                    "ticker": asset_class.upper(),
                    "action": action,
                    "amount_thb": round(amount, 2),
                    "reason": f"{asset_class} allocation drift is {drift:+.1%}; no current ticker available",
                    "sentiment_conflict": False,
                    "validated": False,
                    "tradable": False,
                    "confidence": round(min(0.95, 0.65 + abs(drift)), 4),
                }
            )
            continue
        candidate = max(candidates, key=lambda item: item["value_thb"])
        sentiment = await pool.fetchval(
            """
            SELECT AVG(score) FROM sentiment_scores
            WHERE ticker = $1 AND analyzed_at >= NOW() - INTERVAL '48 hours'
            """,
            candidate["ticker"],
        )
        sentiment_score = float(sentiment or 0)
        confidence = round(min(0.95, 0.65 + abs(drift)), 4)
        trades.append(
            {
                "ticker": candidate["ticker"],
                "action": action,
                "amount_thb": round(amount, 2),
                "reason": f"{asset_class} is {'overweight' if drift > 0 else 'underweight'} by {abs(drift):.1%}",
                "sentiment_score": round(sentiment_score, 4),
                "sentiment_conflict": action == "buy" and sentiment_score < -0.2,
                "validated": False,
                "tradable": True,
                "confidence": confidence,
            }
        )

    context = {
        "base_currency": base_currency,
        "total_value_thb": total_value,
        "current_allocations": current,
        "target_allocations": targets,
        "trades": trades,
        "locked_holdings": sorted(locked),
        "stale_marks": stale_marks,
    }
    narrative = "No rebalancing is required."
    if trades:
        prompt = (
            "You are a portfolio manager. Given this rebalancing analysis, provide a prioritized "
            "action plan with reasoning for each trade. Consider sentiment conflicts and market "
            "conditions. Respond in the same language as the portfolio currency context. "
            f"Context: {json_dumps(context)}"
        )
        try:
            narrative = await ollama_chat(MODEL, prompt, 120)
        except Exception:
            logger.exception("Rebalancing narrative generation failed")
            narrative = "Rebalancing trades were calculated, but the advisory narrative is unavailable."

    try:
        from multi_llm_validator import validate_recommendation
    except Exception:
        logger.exception("Could not import multi-LLM validator")
        validate_recommendation = None

    for trade in trades:
        validation: dict[str, Any] = {}
        if trade.get("tradable") and trade["confidence"] > 0.7 and validate_recommendation:
            try:
                validation = await validate_recommendation(
                    trade["ticker"],
                    trade["action"],
                    trade["reason"],
                    {"score": trade.get("sentiment_score", 0), "confidence": trade["confidence"]},
                )
                trade["validated"] = bool(validation.get("validated"))
                trade["validation"] = validation
            except Exception:
                logger.exception("Validation failed for %s", trade["ticker"])
        if trade["validated"]:
            try:
                await save_recommendation(
                    pool,
                    ticker=trade["ticker"],
                    action=trade["action"],
                    confidence=trade["confidence"],
                    rationale=trade["reason"],
                    sentiment_snapshot={"score": trade.get("sentiment_score", 0)},
                    price=await latest_price(pool, trade["ticker"]),
                    llm_model=MODEL,
                    validated_by=validation.get("validated_by", []),
                )
            except Exception:
                logger.exception("Could not save rebalancing recommendation for %s", trade["ticker"])

    return {
        "rebalancing_needed": bool(trades),
        "current_allocations": current,
        "target_allocations": targets,
        "trades": trades,
        "stale_marks": stale_marks,
        "llm_narrative": narrative,
        "generated_at": datetime.now(UTC).isoformat(),
    }


# ---------------------------------------------------------------------------
# Single-name / single-country concentration review
# ---------------------------------------------------------------------------
# Added by nightly agent 2026-08-06
#
# WHY THIS EXISTS. `generate_rebalancing_plan()` above rebalances by ASSET CLASS
# against TARGET_ALLOCATIONS. That is structurally blind to Tho's actual problem
# in two separate ways:
#
#   1. It cannot see single-NAME concentration. A book that is 100% "equity"
#      looks perfectly on-target to it whether that is thirty names or three.
#   2. It cannot see single-COUNTRY concentration at all. Nothing in the class
#      model distinguishes three Thai stocks from a globally diversified sleeve.
#
# The 2026-08-05 snapshot has all three ex-gold positions at or above the 30%
# flag (SCB 35.7 / PTTEP 34.2 / BAFS 30.1) and 100% of the ex-gold book in a
# single country. Recurring notes in the nightly log have flagged this for weeks
# without it ever becoming a proposal, because no code path could express it.
# This function is that path.
#
# It deliberately runs OFF THE SNAPSHOT JSON — no Postgres, no LLM, no network —
# so it is exercisable in any environment, and it PROPOSES rather than trades.

SINGLE_NAME_FLAG_PCT = 30.0
SINGLE_COUNTRY_FLAG_PCT = 70.0

# MATERIALITY THRESHOLD — Added by nightly agent 2026-08-07
#
# The 2026-08-06 run surfaced BAFS at 30.05% against a 30.00% flag as an
# "action_suggested" item: a 0.05pp breach, a THB 322 trim, 32 shares. That is
# noise presented as a decision, and it is worse than useless because it trains
# the reader to skim the action list.
#
# Two independent reasons a sub-threshold breach cannot be real:
#   1. Commission and the 0.1% SET transaction levy make a THB 322 trade cost a
#      meaningful fraction of itself. There is no economic content in it.
#   2. Marks in this series are frequently CARRIED rather than confirmed closes
#      (see any snapshot's `price_caveats`). A 0.05pp weight difference is far
#      inside the uncertainty of the mark that produced it. Acting on it is
#      acting on a stale price, not on a portfolio fact.
#
# Breaches below this margin are still REPORTED — with `material: False` — so
# nothing is hidden. They just no longer drive `status` to action_suggested.
MATERIALITY_MARGIN_PCT = 1.0
MIN_MATERIAL_TRIM_THB = 5000.0


def _load_snapshot_json(path: str | Path | None = None) -> dict[str, Any]:
    """Load a dated snapshot from data/snapshots, defaulting to the newest."""
    snap_dir = PROJECT_DIR / "data" / "snapshots"
    if path is None:
        candidates = sorted(snap_dir.glob("[0-9]*.json"))
        if not candidates:
            return {}
        path = candidates[-1]
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        logger.exception("Could not load snapshot %s", path)
        return {}


def single_name_concentration_review(
    snapshot: dict[str, Any] | None = None,
    name_flag_pct: float = SINGLE_NAME_FLAG_PCT,
    country_flag_pct: float = SINGLE_COUNTRY_FLAG_PCT,
    materiality_margin_pct: float = MATERIALITY_MARGIN_PCT,  # Added by nightly agent 2026-08-07
    min_material_trim_thb: float = MIN_MATERIAL_TRIM_THB,  # Added by nightly agent 2026-08-07
) -> dict[str, Any]:
    """
    Turn the standing concentration note into a formal, costed proposal.

    Returns per-position weights, breach flags, the trim size that would bring
    each breaching name back to the threshold, and an explicit statement of what
    the proposal does NOT solve.

    This is analysis, not an instruction to trade.

    Added by nightly agent 2026-08-06
    """
    snapshot = snapshot if snapshot is not None else _load_snapshot_json()
    values: dict[str, float] = dict(snapshot.get("position_values_thb") or {})
    prices: dict[str, float] = dict(snapshot.get("prices_thb") or {})
    total = float(snapshot.get("total_ex_gold_thb") or sum(values.values()) or 0.0)

    if total <= 0:
        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "status": "no_data",
            "note": "No priced positions found in the snapshot; nothing to review.",
        }

    positions: list[dict[str, Any]] = []
    for ticker, value in sorted(values.items(), key=lambda kv: -float(kv[1] or 0)):
        weight = float(value) / total * 100.0
        excess_pct = max(0.0, weight - name_flag_pct)
        trim_thb = total * excess_pct / 100.0
        price = float(prices.get(ticker) or 0.0)
        positions.append(
            {
                "ticker": ticker,
                "value_thb": round(float(value), 2),
                "weight_pct": round(weight, 2),
                "breaches_name_flag": weight > name_flag_pct,
                "excess_over_flag_pct": round(excess_pct, 2),
                "trim_to_flag_thb": round(trim_thb, 2),
                "trim_to_flag_shares": int(trim_thb // price) if price > 0 else None,
                # Added by nightly agent 2026-08-07 — a breach is only MATERIAL if it
                # clears the flag by a real margin AND implies a tradeable ticket.
                "material": bool(
                    excess_pct >= materiality_margin_pct
                    and trim_thb >= min_material_trim_thb
                ),
            }
        )

    breaches = [p for p in positions if p["breaches_name_flag"]]
    # Added by nightly agent 2026-08-07 — only material breaches drive the status.
    material_breaches = [p for p in breaches if p["material"]]
    immaterial_breaches = [p for p in breaches if not p["material"]]
    total_trim_thb = round(sum(p["trim_to_flag_thb"] for p in breaches), 2)
    material_trim_thb = round(sum(p["trim_to_flag_thb"] for p in material_breaches), 2)

    # Country concentration. The snapshot is SET-only today; infer from suffix
    # rather than hard-coding, so this keeps working if a foreign name is added.
    by_country: dict[str, float] = defaultdict(float)
    for ticker, value in values.items():
        country = "TH" if str(ticker).upper().endswith(".BK") else "OTHER"
        by_country[country] += float(value or 0)
    country_weights = {k: round(v / total * 100.0, 2) for k, v in by_country.items()}
    country_breaches = {k: v for k, v in country_weights.items() if v > country_flag_pct}

    proposal: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "snapshot_date": (snapshot.get("_meta") or {}).get("date"),
        "total_ex_gold_thb": round(total, 2),
        "name_flag_pct": name_flag_pct,
        "country_flag_pct": country_flag_pct,
        "positions": positions,
        "name_breaches": [p["ticker"] for p in breaches],
        "country_weights_pct": country_weights,
        "country_breaches_pct": country_breaches,
        "total_trim_to_clear_name_flags_thb": total_trim_thb,
        # Added by nightly agent 2026-08-07 — materiality split
        "materiality_margin_pct": materiality_margin_pct,
        "min_material_trim_thb": min_material_trim_thb,
        "material_name_breaches": [p["ticker"] for p in material_breaches],
        "immaterial_name_breaches": [p["ticker"] for p in immaterial_breaches],
        "material_trim_thb": material_trim_thb,
        "status": (
            "action_suggested"
            if (material_breaches or country_breaches)
            else "within_limits"
        ),
    }
    # Added by nightly agent 2026-08-07
    if immaterial_breaches:
        proposal["immaterial_breach_note"] = (
            "Breach(es) reported but NOT actioned: "
            + ", ".join(
                f"{p['ticker']} at {p['weight_pct']:.2f}% "
                f"(+{p['excess_over_flag_pct']:.2f}pp, THB {p['trim_to_flag_thb']:,.0f})"
                for p in immaterial_breaches
            )
            + f". Below the {materiality_margin_pct:.2f}pp / THB "
            f"{min_material_trim_thb:,.0f} materiality floor — inside the uncertainty "
            "of a carried mark, and too small to survive commission and the SET "
            "transaction levy. Reported for completeness, not as an action."
        )

    # ---- the honest part ----
    proposal["what_this_does_not_solve"] = (
        "Trimming every name back to the 30% flag redistributes weight WITHIN a book that "
        "is still 100% single-country Thai equity. It reduces single-stock risk and does "
        "nothing whatsoever about country risk. Treating the trim as 'diversification' "
        "would be the mistake this review exists to prevent."
    )
    proposal["mechanical_trim_caveat"] = (
        "A pure weight-based trim sells the position that has PERFORMED, which is momentum-"
        "negative and tax- and commission-inefficient. Weights here are also driven by marks "
        "that are not all confirmed official SET closes — see the snapshot's price_caveats. "
        "Do not act on a weight breach that is inside the mark uncertainty."
    )
    proposal["sequencing_note"] = (
        "Two dated constraints bind before any PTTEP action: the THB 4.50 interim dividend "
        "goes ex on 2026-08-14 (last cum day 2026-08-13), and BAFS reports H1 around the same "
        "week. Selling PTTEP before 08-13 forfeits ~THB 6,300 gross of entitled income to "
        "correct a weight breach of a few percent — the timing is worth more than the trim."
    )
    proposal["cheapest_correction_first"] = (
        "If the goal is genuinely less concentration rather than tidier weights, the cheapest "
        "correction is the one already available: adding to the existing SCBGOLDE sleeve costs "
        "~0.50% TER, settles in THB, needs no new account and is the only non-Thai-equity "
        "exposure on the book. See data/research/vietnam_ftse_2026.json for why a new foreign "
        "equity position is roughly ten times more expensive to establish at this book size."
    )
    proposal["disclaimer"] = (
        "Analysis only. Not licensed financial advice, and no trade is executed or scheduled "
        "by this function."
    )
    # 2026-10-31: owner holds - Tho will not sell PTTEP/SCB until satisfied with the project.
    # Any breach on those names is INFORMATIONAL: keep the numbers, drop the action framing.
    try:
        from holding_meta import load_owner_holds
        holds = load_owner_holds()
    except Exception:  # noqa: BLE001
        holds = {}
    if holds:
        for p in proposal.get("positions") or []:
            if p.get("ticker") in holds:
                p["owner_hold"] = True
                p["informational_only"] = True
        proposal["owner_holds"] = sorted(holds)
        actionable = [t for t in proposal.get("material_name_breaches") or [] if t not in holds]
        if proposal.get("status") == "action_suggested" and not actionable:
            proposal["status"] = "informational_owner_hold"
        proposal["owner_hold_note"] = (
            "INFORMATIONAL ONLY for " + ", ".join(sorted(holds)) + ": Tho has decided not to sell these until he is "
            "satisfied with the project. Trim sizes are shown for context, not as a suggested action.")
    return proposal
