from datetime import date, datetime, timedelta, timezone
from typing import Any

from utils.common import configure_logging, json_dumps
from utils.db_pool import db_pool

logger = configure_logging("portfolio_engine.backtesting")
UTC = timezone.utc


def first_close_on_or_after(rows: list[Any], target: date) -> Any:
    """Return the earliest valid close row on/after a calendar target date."""
    eligible = []
    for row in rows:
        row_date = row["price_date"]
        row_date = row_date if isinstance(row_date, date) else date.fromisoformat(str(row_date)[:10])
        if row_date >= target and row["close_price"] is not None and float(row["close_price"]) > 0:
            eligible.append((row_date, row))
    return min(eligible, key=lambda item: item[0])[1] if eligible else None


async def record_recommendation_outcome(recommendation_id: str, days_later: int = 7) -> dict[str, Any]:
    pool = await db_pool.get_pool()
    recommendation = await pool.fetchrow("SELECT * FROM recommendations WHERE id = $1::uuid", recommendation_id)
    if not recommendation:
        raise ValueError(f"Recommendation {recommendation_id} not found")
    entry = float(recommendation["price_at_recommendation"] or 0)
    if entry <= 0:
        raise ValueError(f"Recommendation {recommendation_id} has no valid entry price")
    created_at = recommendation["created_at"]
    target = created_at.date() + timedelta(days=days_later)
    prices = await pool.fetch(
        """SELECT price_date, close_price FROM market_prices
           WHERE ticker=$1 AND price_date >= $2 ORDER BY price_date ASC LIMIT 10""",
        recommendation["ticker"],
        target,
    )
    target_row = first_close_on_or_after(list(prices), target)
    if target_row is None:
        raise ValueError(f"No close for {recommendation['ticker']} on or after {target}")
    current = float(target_row["close_price"])
    actual_return = ((current - entry) / entry * 100) if entry else 0.0
    action = str(recommendation["action"] or "").lower()
    was_correct = None if action == "watch" else (
        (action in {"buy", "accumulate"} and actual_return > 0)
        or (action in {"sell", "reduce", "stop_loss"} and actual_return < 0)
        or (action == "hold" and abs(actual_return) < 2)
    )
    actual_date = target_row["price_date"]
    actual_date = actual_date if isinstance(actual_date, date) else date.fromisoformat(str(actual_date)[:10])
    days_held = max(0, (actual_date - created_at.date()).days)
    outcome = {
        "price_at_review": current,
        "price_at_review_date": str(actual_date),
        "target_date": str(target),
        "actual_return_pct": round(actual_return, 4),
        "was_correct": was_correct,
        "evaluation_status": "excluded_neutral" if action == "watch" else "directional",
        "days_held": days_held,
        "reviewed_at": datetime.now(UTC).isoformat(),
    }
    await pool.execute(
        "UPDATE recommendations SET actual_outcome = $1::jsonb, reviewed_at = NOW() WHERE id = $2::uuid",
        json_dumps(outcome),
        recommendation_id,
    )
    return {"recommendation_id": recommendation_id, **outcome}


async def record_due_recommendation_outcomes(days_later: int = 7) -> dict[str, Any]:
    pool = await db_pool.get_pool()
    ids = await pool.fetch(
        """
        SELECT id FROM recommendations
        WHERE actual_outcome IS NULL AND created_at <= NOW() - ($1 * INTERVAL '1 day')
        ORDER BY created_at
        """,
        days_later,
    )
    reviewed = 0
    for row in ids:
        try:
            await record_recommendation_outcome(str(row["id"]), days_later)
            reviewed += 1
        except Exception:
            logger.exception("Could not record outcome for %s", row["id"])
    return {"eligible": len(ids), "reviewed": reviewed}


async def get_accuracy_report() -> dict[str, Any]:
    pool = await db_pool.get_pool()
    rows = await pool.fetch(
        """
        SELECT ticker, action, llm_model,
               (actual_outcome->>'was_correct')::boolean AS was_correct,
               (actual_outcome->>'actual_return_pct')::double precision AS actual_return_pct
        FROM recommendations
        WHERE actual_outcome IS NOT NULL
          AND action <> 'watch'
          AND actual_outcome->>'was_correct' IS NOT NULL
        """
    )
    total = len(rows)

    def accuracy(items: list[Any]) -> float:
        return round(sum(bool(item["was_correct"]) for item in items) / len(items), 4) if items else 0.0

    by_action = {action: accuracy([row for row in rows if row["action"] == action]) for action in sorted({row["action"] for row in rows})}
    by_model = {model: accuracy([row for row in rows if row["llm_model"] == model]) for model in sorted({row["llm_model"] for row in rows if row["llm_model"]})}
    correct_returns = [float(row["actual_return_pct"]) for row in rows if row["was_correct"] and row["actual_return_pct"] is not None]
    wrong_returns = [float(row["actual_return_pct"]) for row in rows if not row["was_correct"] and row["actual_return_pct"] is not None]
    ticker_returns: dict[str, list[float]] = {}
    for row in rows:
        if row["actual_return_pct"] is not None:
            ticker_returns.setdefault(row["ticker"], []).append(float(row["actual_return_pct"]))
    averages = {ticker: sum(values) / len(values) for ticker, values in ticker_returns.items()}
    return {
        "total_recommendations_reviewed": total,
        "overall_accuracy": accuracy(list(rows)),
        "accuracy_by_action": by_action,
        "accuracy_by_model": by_model,
        "avg_return_when_correct": round(sum(correct_returns) / len(correct_returns), 4) if correct_returns else 0.0,
        "avg_return_when_wrong": round(sum(wrong_returns) / len(wrong_returns), 4) if wrong_returns else 0.0,
        "best_performing_ticker": max(averages, key=averages.get) if averages else None,
        "worst_performing_ticker": min(averages, key=averages.get) if averages else None,
    }
