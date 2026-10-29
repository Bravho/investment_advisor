from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional
from zoneinfo import ZoneInfo

ENGINE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = ENGINE_DIR.parent
AI_ENGINE_DIR = PROJECT_DIR / "ai_engine"
for import_path in (str(AI_ENGINE_DIR), str(ENGINE_DIR)):
    if import_path in sys.path:
        sys.path.remove(import_path)
    sys.path.insert(0, import_path)

import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from backtesting import get_accuracy_report, record_due_recommendation_outcomes, record_recommendation_outcome
from brief_generator import ensure_daily_briefs_table, generate_daily_brief
from opportunity_scanner import check_exit_signals, scan_advisory_candidates, scan_opportunities, tech_screener
from performance_analytics import get_performance_summary
from rebalancer import generate_rebalancing_plan
from utils.common import configure_logging, latest_price, load_snapshot, to_jsonable
from utils.db_pool import db_pool

from risk_scorer import calculate_portfolio_risk, save_daily_performance

logger = configure_logging("portfolio_engine.api")
ICT = ZoneInfo("Asia/Bangkok")
UTC = timezone.utc
scheduler = AsyncIOScheduler(
    timezone=ICT,
    job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 300},
)
opportunity_cache: dict[str, Any] = {"value": [], "updated": 0.0}
exit_cache: dict[str, Any] = {"value": [], "updated": 0.0}
advisory_candidate_cache: dict[str, Any] = {"value": [], "updated": 0.0}
# Human-approve gate for rebalance DISPLAY only — never executes trades.
# Persisted under data/rebalance_approvals.json (improvement #4, 2026-10-07).
_REBALANCE_APPROVAL_PATH = PROJECT_DIR / "data" / "rebalance_approvals.json"
_pending_rebalance_plan: dict[str, Any] = {}


def _load_rebalance_approvals() -> dict[str, Any]:
    try:
        if _REBALANCE_APPROVAL_PATH.exists():
            return json.loads(_REBALANCE_APPROVAL_PATH.read_text(encoding="utf-8"))
    except Exception:
        logger.debug("rebalance approval file unreadable", exc_info=True)
    return {"approvals": {}}


def _save_rebalance_approvals(payload: dict[str, Any]) -> None:
    try:
        _REBALANCE_APPROVAL_PATH.parent.mkdir(parents=True, exist_ok=True)
        _REBALANCE_APPROVAL_PATH.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except Exception:
        logger.exception("Could not persist rebalance approval status")


def _annotate_rebalance_plan(plan: dict[str, Any], *, approved: bool) -> dict[str, Any]:
    """Mark plan/trades as advisory; unlock display only when human-approved."""
    out = dict(plan)
    out["advisory_only"] = True
    out["approval_required"] = True
    out["human_approval_status"] = "approved" if approved else "pending"
    out["actionable"] = bool(approved)
    out["execution"] = "none"  # hard constraint: never auto-execute
    out["approval_note"] = (
        "Human approval unlocks display of this suggestion as actionable. "
        "It does NOT execute trades or change TARGET_ALLOCATIONS."
    )
    trades = []
    for trade in out.get("trades") or []:
        item = dict(trade)
        item["advisory_only"] = True
        item["actionable"] = bool(approved)
        item["display_status"] = "actionable_display" if approved else "advisory_pending_approval"
        trades.append(item)
    out["trades"] = trades
    return out

active_tasks: set[asyncio.Task] = set()


async def _safe_job(name: str, function: Callable[[], Awaitable[Any]], cache: Optional[dict[str, Any]] = None) -> None:
    try:
        result = await function()
        if cache is not None:
            cache.update(value=result, updated=time.monotonic())
        logger.info("Scheduled job %s completed", name)
    except Exception:
        logger.exception("Scheduled job %s failed without stopping service", name)


def configure_schedules() -> None:
    scheduler.add_job(_safe_job, "interval", args=["scan_opportunities", scan_opportunities, opportunity_cache], minutes=30, id="scan_opportunities", replace_existing=True)
    scheduler.add_job(_safe_job, "interval", args=["check_exit_signals", check_exit_signals, exit_cache], minutes=15, id="check_exit_signals", replace_existing=True)
    scheduler.add_job(_safe_job, "cron", args=["generate_daily_brief", generate_daily_brief], hour=7, minute=0, id="generate_daily_brief", replace_existing=True)
    scheduler.add_job(_safe_job, "cron", args=["save_daily_performance", save_daily_performance], hour=17, minute=30, id="save_daily_performance", replace_existing=True)
    scheduler.add_job(_safe_job, "cron", args=["record_recommendation_outcomes", record_due_recommendation_outcomes], hour=8, minute=0, id="record_recommendation_outcomes", replace_existing=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    del app
    await db_pool.connect()
    await ensure_daily_briefs_table()
    configure_schedules()
    scheduler.start()
    for name, function, cache in (
        ("scan_opportunities", scan_opportunities, opportunity_cache),
        ("check_exit_signals", check_exit_signals, exit_cache),
    ):
        task = asyncio.create_task(_safe_job(name, function, cache))
        active_tasks.add(task)
        task.add_done_callback(active_tasks.discard)
    logger.info("Portfolio engine started on ICT schedule")
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)
        if active_tasks:
            await asyncio.gather(*active_tasks, return_exceptions=True)
        await db_pool.close()


app = FastAPI(title="Portfolio Intelligence Engine", version="3.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": "3.0.0"}


@app.get("/portfolio/summary")
async def portfolio_summary() -> dict[str, Any]:
    pool = await db_pool.get_pool()
    rows = await pool.fetch("SELECT * FROM holdings ORDER BY ticker")
    snapshot = load_snapshot()
    positions = []
    total_value = 0.0
    total_pnl = 0.0
    for row in rows:
        price = await latest_price(pool, row["ticker"])
        snapshot_position = snapshot.get("holdings", {}).get(row["ticker"], {})
        quantity = float(row["quantity"] or 0)
        cost = float(row["avg_cost_price"] or 0)
        value = float(snapshot_position.get("market_value_thb") or price * quantity)
        pnl = float(snapshot_position.get("pnl_thb") or (price - cost) * quantity)
        total_value += value
        total_pnl += pnl
        # Standing rule (Tho 2026-10-07): flag marks older than 7 days.
        price_as_of = snapshot_position.get("price_as_of")
        price_age_days = snapshot_position.get("price_age_days")
        price_stale = bool(snapshot_position.get("price_stale"))
        positions.append(
            {
                **to_jsonable(dict(row)),
                "live_price": price,
                "market_value_thb": round(value, 2),
                "unrealized_pnl_thb": round(pnl, 2),
                "unrealized_pnl_pct": round(
                    float(snapshot_position.get("pnl_pct"))
                    if snapshot_position.get("pnl_pct") is not None
                    else ((price - cost) / cost * 100 if cost else 0.0),
                    4,
                ),
                "price_as_of": price_as_of,
                "price_age_days": price_age_days,
                "price_stale": price_stale,
                "price_source": snapshot_position.get("price_source"),
            }
        )
    return {
        "base_currency": snapshot.get("base_currency", "THB"),
        "total_value_thb": round(total_value, 2),
        "total_unrealized_pnl_thb": round(total_pnl, 2),
        "holdings": positions,
        "generated_at": datetime.now(UTC).isoformat(),
    }


@app.get("/portfolio/performance")
async def portfolio_performance(days: int = Query(30, ge=1, le=3650)) -> dict[str, Any]:
    return await get_performance_summary(days)


@app.get("/portfolio/risk")
async def portfolio_risk() -> dict[str, Any]:
    pool = await db_pool.get_pool()
    row = await pool.fetchrow("SELECT risk_score, record_date FROM portfolio_performance ORDER BY record_date DESC LIMIT 1")
    if row and row["risk_score"] is not None:
        return {"portfolio_risk_score": float(row["risk_score"]), "record_date": row["record_date"].isoformat(), "source": "portfolio_performance"}
    return await calculate_portfolio_risk()


@app.post("/portfolio/rebalance")
async def rebalance() -> dict[str, Any]:
    """
    Generate an ADVISORY rebalancing suggestion.

    Trades are NOT actionable until a human approves via
    POST /portfolio/rebalance/approve. Approval unlocks display only —
    it never executes trades or mutates TARGET_ALLOCATIONS.
    """
    plan = await generate_rebalancing_plan()
    plan_id = f"rebalance-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    annotated = _annotate_rebalance_plan(plan, approved=False)
    annotated["plan_id"] = plan_id
    _pending_rebalance_plan.clear()
    _pending_rebalance_plan.update(annotated)
    return annotated


@app.get("/portfolio/rebalance/status")
async def rebalance_status() -> dict[str, Any]:
    """Current pending advisory rebalance plan + approval status."""
    if not _pending_rebalance_plan:
        return {
            "pending": False,
            "advisory_only": True,
            "human_approval_status": "none",
            "actionable": False,
            "execution": "none",
        }
    return {
        "pending": True,
        **{k: _pending_rebalance_plan.get(k) for k in (
            "plan_id", "advisory_only", "human_approval_status",
            "actionable", "execution", "rebalancing_needed", "generated_at",
        )},
        "trade_count": len(_pending_rebalance_plan.get("trades") or []),
    }


@app.post("/portfolio/rebalance/approve")
async def approve_rebalance(plan_id: Optional[str] = Query(None)) -> dict[str, Any]:
    """
    Human approve-gate: unlock advisory rebalance suggestion for DISPLAY.
    Does NOT execute trades, place orders, or change TARGET_ALLOCATIONS.
    """
    if not _pending_rebalance_plan:
        raise HTTPException(status_code=404, detail="No pending rebalance plan to approve")
    current_id = _pending_rebalance_plan.get("plan_id")
    if plan_id and current_id and plan_id != current_id:
        raise HTTPException(
            status_code=409,
            detail=f"plan_id mismatch: pending={current_id}, requested={plan_id}",
        )
    approved_plan = _annotate_rebalance_plan(_pending_rebalance_plan, approved=True)
    approved_plan["plan_id"] = current_id
    approved_plan["approved_at"] = datetime.now(UTC).isoformat()
    _pending_rebalance_plan.clear()
    _pending_rebalance_plan.update(approved_plan)

    store = _load_rebalance_approvals()
    store.setdefault("approvals", {})[str(current_id)] = {
        "approved_at": approved_plan["approved_at"],
        "trade_count": len(approved_plan.get("trades") or []),
        "execution": "none",
        "note": "display unlock only",
    }
    _save_rebalance_approvals(store)

    return {
        "ok": True,
        "plan_id": current_id,
        "human_approval_status": "approved",
        "actionable": True,
        "execution": "none",
        "advisory_only": True,
        "message": "Approved for display only — no trades executed.",
        "plan": approved_plan,
    }



@app.get("/opportunities")
async def opportunities() -> list[dict[str, Any]]:
    if time.monotonic() - opportunity_cache["updated"] >= 1800:
        await _safe_job("scan_opportunities", scan_opportunities, opportunity_cache)
    return opportunity_cache["value"]


@app.get("/opportunities/tech")
async def tech_opportunities(top_n: int = Query(10, ge=1, le=20)) -> list[dict[str, Any]]:
    """
    Screen global technology stocks (Nasdaq, Nikkei, Nifty, Vietnam, SET)
    for momentum buy signals. Uses yfinance — no DB dependency.
    Added by nightly agent 2026-06-11
    """
    return await tech_screener(top_n=top_n)



@app.get("/opportunities/advisory")
async def advisory_opportunities(
    limit: int = Query(15, ge=1, le=50),
    lookback_hours: int = Query(48, ge=6, le=168),
) -> dict[str, Any]:
    """
    Ranked ADVISORY candidates from news→ticker sentiment joins.
    Never auto-trades. Human approval required before treating as actionable.
    Added 2026-10-07 (improvement #2/#4).
    """
    # Refresh at most every 10 minutes unless cache empty
    if (
        not advisory_candidate_cache["value"]
        or time.monotonic() - float(advisory_candidate_cache["updated"] or 0) >= 600
    ):
        await _safe_job(
            "scan_advisory_candidates",
            lambda: scan_advisory_candidates(limit=limit, lookback_hours=lookback_hours),
            advisory_candidate_cache,
        )
    return {
        "advisory_only": True,
        "human_approval_required": True,
        "actionable": False,
        "execution": "none",
        "candidates": advisory_candidate_cache["value"],
        "updated_monotonic": advisory_candidate_cache["updated"],
        "generated_at": datetime.now(UTC).isoformat(),
    }


@app.post("/opportunities/advisory/refresh")
async def refresh_advisory_opportunities(
    limit: int = Query(15, ge=1, le=50),
    lookback_hours: int = Query(48, ge=6, le=168),
) -> dict[str, Any]:
    """Force-refresh advisory candidates (still advisory-only)."""
    await _safe_job(
        "scan_advisory_candidates",
        lambda: scan_advisory_candidates(limit=limit, lookback_hours=lookback_hours),
        advisory_candidate_cache,
    )
    return {
        "advisory_only": True,
        "candidates": advisory_candidate_cache["value"],
        "generated_at": datetime.now(UTC).isoformat(),
    }



@app.get("/opportunities/exits")
async def exits() -> list[dict[str, Any]]:
    if time.monotonic() - exit_cache["updated"] >= 900:
        await _safe_job("check_exit_signals", check_exit_signals, exit_cache)
    return exit_cache["value"]


@app.get("/brief/today")
async def today_brief() -> dict[str, Any]:
    pool = await db_pool.get_pool()
    row = await pool.fetchrow("SELECT * FROM daily_briefs WHERE brief_date = CURRENT_DATE")
    return to_jsonable(dict(row)) if row else await generate_daily_brief()


@app.get("/brief/history")
async def brief_history(limit: int = Query(7, ge=1, le=100)) -> list[dict[str, Any]]:
    pool = await db_pool.get_pool()
    rows = await pool.fetch("SELECT * FROM daily_briefs ORDER BY brief_date DESC LIMIT $1", limit)
    return to_jsonable([dict(row) for row in rows])


@app.get("/analytics/accuracy")
async def accuracy() -> dict[str, Any]:
    return await get_accuracy_report()


@app.get("/analytics/performance")
async def analytics_performance(days: int = Query(30, ge=1, le=3650)) -> dict[str, Any]:
    return await get_performance_summary(days)


@app.post("/recommendations/{recommendation_id}/outcome")
async def recommendation_outcome(recommendation_id: str) -> dict[str, Any]:
    try:
        return await record_recommendation_outcome(recommendation_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/recommendations/history")
async def recommendation_history(ticker: Optional[str] = None, limit: int = Query(10, ge=1, le=100)) -> list[dict[str, Any]]:
    pool = await db_pool.get_pool()
    if ticker:
        rows = await pool.fetch("SELECT * FROM recommendations WHERE ticker = $1 ORDER BY created_at DESC LIMIT $2", ticker.upper(), limit)
    else:
        rows = await pool.fetch("SELECT * FROM recommendations ORDER BY created_at DESC LIMIT $1", limit)
    return to_jsonable([dict(row) for row in rows])


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORTFOLIO_ENGINE_PORT", "8996")))
