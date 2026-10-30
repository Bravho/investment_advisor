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
from brief_generator import ensure_daily_briefs_table, generate_daily_brief, is_failed_brief, retry_daily_brief_if_needed
from opportunity_scanner import check_exit_signals, scan_advisory_candidates, scan_opportunities, tech_screener
from performance_analytics import get_performance_summary
from rebalancer import generate_rebalancing_plan
from utils.common import configure_logging, latest_price, load_snapshot, to_jsonable
from utils.db_pool import db_pool
import watchlists as watch_mod
import risk_engine as risk_mod
import trade_plans as plans_mod
import signals as signals_mod
import walkforward as wf_mod
import predictions as pred_mod
import portfolio_construction as pc_mod
import attribution as attr_mod
import momentum_base as mb_mod
from fastapi import Body

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


async def _watch_prices_job() -> dict[str, Any]:
    return await watch_mod.run_watchlist_cycle(await db_pool.get_pool(), prices=True, factors=False, alerts=True)


async def _factors_job() -> dict[str, Any]:
    return await watch_mod.run_watchlist_cycle(await db_pool.get_pool(), prices=False, factors=True, alerts=False)


async def _risk_job() -> dict[str, Any]:
    rep = await risk_mod.run_risk_report(await db_pool.get_pool())
    return rep.get("summary", {})


async def _startup_phase3() -> None:
    pool = await db_pool.get_pool()
    await watch_mod.ensure_tables(pool)
    await _safe_job("watchlist_startup", lambda: watch_mod.run_watchlist_cycle(pool))
    latest = await risk_mod.latest_risk_report(pool)
    _ict = ZoneInfo("Asia/Bangkok")
    _last_day = (datetime.fromisoformat(latest["run_at"]).astimezone(_ict).date() if latest and latest.get("run_at") else None)
    if _last_day != datetime.now(_ict).date():
        await _safe_job("risk_report_startup", _risk_job)
    await plans_mod.ensure_tables(pool)
    async with pool.acquire() as _c:
        _last_prop = await _c.fetchval("SELECT max(created_at) FROM trade_plans WHERE source='engine'")
    if _last_prop is None or _last_prop.astimezone(_ict).date() != datetime.now(_ict).date():
        await _safe_job("trade_plan_proposals_startup", _proposals_job)
    async with pool.acquire() as _c:
        await _c.execute(signals_mod.DDL)
        _last_sig = await _c.fetchval("SELECT max(as_of) FROM signal_scores")
    if _last_sig != datetime.now(_ict).date():
        await _safe_job("signals_startup", _signals_job)
    async with pool.acquire() as _c:
        await _c.execute(wf_mod.DDL)
        _last_bt = await _c.fetchval("SELECT max(run_at) FROM backtest_runs")
    if _last_bt is None or (datetime.now(timezone.utc) - _last_bt).days >= 7:
        await _safe_job("walkforward_backtest_startup", _backtest_job)
    await _safe_job("paper_ledger_startup", _paper_job)
    await pred_mod.ensure_tables(pool)
    async with pool.acquire() as _c:
        _bf = await _c.fetchval("SELECT count(*) FROM predictions WHERE source='backfill'")
    if not _bf:
        await _safe_job("predictions_backfill_startup", lambda: pred_mod.run_backfill(pool))
    await _safe_job("predictions_generate_startup", _predictions_job)
    _pc = await pc_mod.latest(pool)
    if not _pc or _pc["created_at"][:10] != datetime.now(_ict).date().isoformat():
        await _safe_job("portfolio_construction_startup", _construction_job)


async def _attribution_job() -> dict[str, Any]:
    r = await attr_mod.run_attribution(await db_pool.get_pool())
    return {"live_twr_pct": (r.get("live") or {}).get("twr_pct")}


async def _construction_job() -> dict[str, Any]:
    r = await pc_mod.run_construction(await db_pool.get_pool())
    return {"recommended": r["weights"]["recommended"], "trades": len(r["trades"])}


async def _predictions_job() -> dict[str, Any]:
    return await pred_mod.generate_live(await db_pool.get_pool())


async def _predictions_validate_job() -> dict[str, Any]:
    pool = await db_pool.get_pool()
    v = await pred_mod.validate_matured(pool)
    w = await pred_mod.learn(pool) if v.get("validated") else {"skipped": "nothing newly matured"}
    return {"validated": v, "learned": bool(v.get("validated"))}


async def _predictions_monthly_job() -> dict[str, Any]:
    return await pred_mod.send_monthly_summary(await db_pool.get_pool())


async def _outcome_job() -> dict[str, Any]:
    return await wf_mod.outcome_job(await db_pool.get_pool(), legacy=record_due_recommendation_outcomes)


async def _paper_job() -> dict[str, Any]:
    return await plans_mod.update_paper_ledger(await db_pool.get_pool())


async def _backtest_job() -> dict[str, Any]:
    return await wf_mod.run_backtest(await db_pool.get_pool())


async def _signals_job() -> dict[str, Any]:
    return await signals_mod.run_signals(await db_pool.get_pool(), council=True)


async def _proposals_job() -> dict[str, Any]:
    return await plans_mod.generate_proposals(await db_pool.get_pool())


async def _setup_screen_job() -> dict[str, Any]:
    return await mb_mod.run_screen(await db_pool.get_pool(), make_plans=True)


async def _setup_backtest_job() -> dict[str, Any]:
    return await mb_mod.run_backtest(await db_pool.get_pool())


def configure_schedules() -> None:
    scheduler.add_job(_safe_job, "interval", args=["scan_opportunities", scan_opportunities, opportunity_cache], minutes=30, id="scan_opportunities", replace_existing=True)
    scheduler.add_job(_safe_job, "interval", args=["check_exit_signals", check_exit_signals, exit_cache], minutes=15, id="check_exit_signals", replace_existing=True)
    scheduler.add_job(_safe_job, "cron", args=["generate_daily_brief", generate_daily_brief], hour=7, minute=0, id="generate_daily_brief", replace_existing=True)
    # Phase 2 (2026-10-29): retry a failed/missing brief instead of leaving it empty
    for _h, _m in ((7, 30), (8, 30), (10, 0), (13, 0)):
        scheduler.add_job(_safe_job, "cron", args=["retry_daily_brief", retry_daily_brief_if_needed], hour=_h, minute=_m, id=f"retry_daily_brief_{_h:02d}{_m:02d}", replace_existing=True)
    scheduler.add_job(_safe_job, "cron", args=["save_daily_performance", save_daily_performance], hour=17, minute=30, id="save_daily_performance", replace_existing=True)
    # Phase 4: the 08:00 outcome job also scores live signals (hit rate/avg win-loss/Sharpe) and updates the paper ledger.
    scheduler.add_job(_safe_job, "cron", args=["record_recommendation_outcomes", _outcome_job], hour=8, minute=0, id="record_recommendation_outcomes", replace_existing=True)
    scheduler.add_job(_safe_job, "cron", args=["paper_ledger", _paper_job], hour=18, minute=0, id="paper_ledger", replace_existing=True)
    scheduler.add_job(_safe_job, "cron", args=["walkforward_backtest", _backtest_job], day_of_week="sun", hour=5, minute=0, id="walkforward_backtest", replace_existing=True)
    # Phase 3 (2026-10-29): watch lists, market factors, risk engine
    scheduler.add_job(_safe_job, "interval", args=["watchlist_prices_alerts", _watch_prices_job], minutes=30, id="watchlist_prices_alerts", replace_existing=True)
    scheduler.add_job(_safe_job, "interval", args=["market_factors", _factors_job], minutes=60, id="market_factors", replace_existing=True)
    scheduler.add_job(_safe_job, "cron", args=["market_factors_prebrief", _factors_job], hour=6, minute=40, id="market_factors_prebrief", replace_existing=True)
    scheduler.add_job(_safe_job, "cron", args=["risk_report", _risk_job], hour=6, minute=30, id="risk_report", replace_existing=True)
    scheduler.add_job(_safe_job, "cron", args=["trade_plan_proposals", _proposals_job], hour=6, minute=45, id="trade_plan_proposals", replace_existing=True)
    scheduler.add_job(_safe_job, "cron", args=["signals", _signals_job], hour=6, minute=50, id="signals", replace_existing=True)
    # 2026-10-30: momentum_base_swing setup (Tho's lesson, swing adaptation). Screen after the SET close (daily bars complete)
    # and again pre-brief; weekly walk-forward backtest. Proposals only - no order code exists.
    scheduler.add_job(_safe_job, "cron", args=["setup_screen_evening", _setup_screen_job], day_of_week="mon-fri", hour=17, minute=45, id="setup_screen_evening", replace_existing=True)
    scheduler.add_job(_safe_job, "cron", args=["setup_screen_prebrief", _setup_screen_job], hour=6, minute=47, id="setup_screen_prebrief", replace_existing=True)
    scheduler.add_job(_safe_job, "cron", args=["setup_backtest", _setup_backtest_job], day_of_week="sun", hour=5, minute=30, id="setup_backtest", replace_existing=True)
    scheduler.add_job(_safe_job, "cron", args=["predictions_generate", _predictions_job], hour=6, minute=55, id="predictions_generate", replace_existing=True)
    scheduler.add_job(_safe_job, "cron", args=["predictions_validate", _predictions_validate_job], hour=8, minute=5, id="predictions_validate", replace_existing=True)
    scheduler.add_job(_safe_job, "cron", args=["portfolio_construction", _construction_job], hour=7, minute=10, id="portfolio_construction", replace_existing=True)
    scheduler.add_job(_safe_job, "cron", args=["performance_attribution", _attribution_job], hour=18, minute=15, id="performance_attribution", replace_existing=True)
    scheduler.add_job(_safe_job, "cron", args=["predictions_monthly_summary", _predictions_monthly_job], day=1, hour=9, minute=0, id="predictions_monthly_summary", replace_existing=True)


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
    _p3 = asyncio.create_task(_startup_phase3())
    active_tasks.add(_p3)
    _p3.add_done_callback(active_tasks.discard)
    logger.info("Portfolio engine started on ICT schedule")
    logger.info("Scheduled jobs: %s", ", ".join(sorted(j.id for j in scheduler.get_jobs())))
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
    if not row:
        return await generate_daily_brief()
    out = to_jsonable(dict(row))
    out["status"] = "failed" if is_failed_brief(out.get("content")) else "ok"
    return out


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


# --------------------------------------------------------------------------
# Phase 3 (2026-10-29): watch lists, market factors, risk engine
# --------------------------------------------------------------------------
@app.get("/watchlist")
async def watchlist(include_dropped: bool = True) -> dict[str, Any]:
    pool = await db_pool.get_pool()
    await watch_mod.ensure_tables(pool)
    items = await watch_mod.get_investment_watchlist(pool, include_dropped=include_dropped)
    return {"items": items, "count": len(items), "stale_after_days": watch_mod.STALE_PRICE_DAYS,
            "note": "Entry zone/target/stop are set by Tho (PUT /watchlist/{ticker}); technical triggers are live."}


@app.put("/watchlist/{ticker}")
async def watchlist_update(ticker: str, fields: dict[str, Any] = Body(...)) -> dict[str, Any]:
    pool = await db_pool.get_pool()
    await watch_mod.ensure_tables(pool)
    try:
        return await watch_mod.upsert_watch_item(pool, ticker.upper(), fields)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/watchlist/refresh")
async def watchlist_refresh(factors: bool = True) -> dict[str, Any]:
    return to_jsonable(await watch_mod.run_watchlist_cycle(await db_pool.get_pool(), prices=True, factors=factors, alerts=True))


@app.get("/factors")
async def factors() -> dict[str, Any]:
    pool = await db_pool.get_pool()
    await watch_mod.ensure_tables(pool)
    rows = await watch_mod.get_market_factors(pool)
    return {"factors": rows, "breached": [r["key"] for r in rows if r.get("breached") and not r.get("stale")],
            "fred_key_valid": watch_mod._fred_key() is not None}


@app.get("/risk/report")
async def risk_report() -> dict[str, Any]:
    rep = await risk_mod.latest_risk_report(await db_pool.get_pool())
    if not rep:
        raise HTTPException(status_code=404, detail="no risk report yet; POST /risk/run")
    return rep


@app.post("/risk/run")
async def risk_run() -> dict[str, Any]:
    rep = await risk_mod.run_risk_report(await db_pool.get_pool())
    return rep.get("summary", {})


@app.get("/risk/position-size")
async def risk_position_size(ticker: str, entry: float, stop: float, sector: Optional[str] = None,
                             risk_pct: Optional[float] = None) -> dict[str, Any]:
    pool = await db_pool.get_pool()
    positions = await risk_mod._positions(pool)
    total = sum(p["value_thb"] for p in positions)
    try:
        return risk_mod.position_size(ticker.upper(), entry, stop, total, positions, sector=sector, risk_pct=risk_pct)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# --------------------------------------------------------------------------
# Phase 4 (2026-10-30): trade plans (engine proposals need Tho's approval)
# --------------------------------------------------------------------------
@app.get("/trade-plans")
async def trade_plans_list(status: Optional[str] = None) -> dict[str, Any]:
    plans = await plans_mod.list_plans(await db_pool.get_pool(), status)
    return {"plans": plans, "count": len(plans),
            "note": "Engine plans are 'proposed' and never trigger alerts. PATCH status=approved copies the zone/stop/target "
                    "to the watch list, which then drives 'ready' alerts. Not financial advice."}


@app.post("/trade-plans/propose")
async def trade_plans_propose() -> dict[str, Any]:
    return await _proposals_job()


@app.post("/trade-plans")
async def trade_plans_create(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    try:
        return await plans_mod.create_manual_plan(await db_pool.get_pool(), body)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"bad plan: {exc}") from exc


@app.patch("/trade-plans/{plan_id}")
async def trade_plans_patch(plan_id: int, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    try:
        return await plans_mod.update_plan(await db_pool.get_pool(), plan_id, body)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="plan not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# --------------------------------------------------------------------------
# Phase 4 (2026-10-30): signals (pro layer #2)
# --------------------------------------------------------------------------
@app.get("/signals")
async def signals_latest(kind: Optional[str] = None) -> dict[str, Any]:
    out = await signals_mod.latest_signals(await db_pool.get_pool())
    if kind:
        out["items"] = [i for i in out["items"] if i["kind"] == kind]
    return out


@app.post("/signals/run")
async def signals_run(council: bool = False) -> dict[str, Any]:
    return await signals_mod.run_signals(await db_pool.get_pool(), council=council)


# --------------------------------------------------------------------------
# Phase 4 (2026-10-30): backtesting, outcome scoring, paper ledger (pro layer #3)
# --------------------------------------------------------------------------
@app.get("/backtest/latest")
async def backtest_latest() -> dict[str, Any]:
    out = await wf_mod.latest_backtest(await db_pool.get_pool())
    return {"universes": out, "method": wf_mod.__doc__}


@app.post("/backtest/run")
async def backtest_run() -> dict[str, Any]:
    return await _backtest_job()


@app.get("/signals/performance")
async def signals_performance() -> dict[str, Any]:
    return await wf_mod.signal_performance(await db_pool.get_pool())


@app.post("/signals/outcomes/run")
async def signals_outcomes_run() -> dict[str, Any]:
    pool = await db_pool.get_pool()
    return {"live": await wf_mod.score_live_outcomes(pool), "paper": await plans_mod.update_paper_ledger(pool)}


@app.get("/paper-trades")
async def paper_trades() -> dict[str, Any]:
    return await plans_mod.paper_summary(await db_pool.get_pool())


# --------------------------------------------------------------------------
# Phase 4 (2026-10-30): trade discipline - plan record/checklist + journal (pro layer #5)
# --------------------------------------------------------------------------
@app.get("/trade-plans/{plan_id}")
async def trade_plan_get(plan_id: int, refresh_checklist: bool = False) -> dict[str, Any]:
    pool = await db_pool.get_pool()
    if refresh_checklist:
        try:
            return await plans_mod.update_plan(pool, plan_id, {})
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="plan not found") from exc
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM trade_plans WHERE id=$1", plan_id)
    if not row:
        raise HTTPException(status_code=404, detail="plan not found")
    return plans_mod._row(row)


@app.get("/journal")
async def journal_list() -> dict[str, Any]:
    items = await plans_mod.journal_list(await db_pool.get_pool())
    return {"items": items, "count": len(items), "fields": sorted(plans_mod.JOURNAL_FIELDS)}


@app.post("/journal")
async def journal_create(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    try:
        return await plans_mod.journal_upsert(await db_pool.get_pool(), body)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.patch("/journal/{entry_id}")
async def journal_patch(entry_id: int, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    try:
        return await plans_mod.journal_upsert(await db_pool.get_pool(), body, entry_id)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# --------------------------------------------------------------------------
# Phase 4+ (2026-10-30): prediction system (frozen forecasts, validation, RCA, learning)
# --------------------------------------------------------------------------
@app.get("/predictions")
async def predictions_latest(subject: Optional[str] = None, with_method: bool = False) -> dict[str, Any]:
    items = await pred_mod.latest_predictions(await db_pool.get_pool(), subject.upper() if subject else None, with_method)
    return {"items": items, "count": len(items), "horizons": pred_mod.HORIZONS, "cadence": pred_mod.CADENCE,
            "note": "Frozen (insert-only) quantitative forecasts. Not financial advice."}


@app.get("/predictions/scoreboard")
async def predictions_scoreboard() -> dict[str, Any]:
    return await pred_mod.scoreboard(await db_pool.get_pool())


@app.get("/predictions/lessons")
async def predictions_lessons() -> dict[str, Any]:
    sb = await pred_mod.scoreboard(await db_pool.get_pool())
    return {"lessons": sb["lessons"], "model_weights": sb["model_weights"]}


@app.get("/predictions/advisor-context")
async def predictions_advisor_context(tickers: str = "") -> dict[str, Any]:
    t = [x.strip().upper() for x in tickers.split(",") if x.strip()]
    return {"context": await pred_mod.advisor_context(await db_pool.get_pool(), t)}


@app.get("/predictions/monthly-summary")
async def predictions_monthly_preview() -> dict[str, Any]:
    return {"text": await pred_mod.monthly_summary_text(await db_pool.get_pool()), "note": "Preview only; sent by the 1st-of-month 09:00 job."}


@app.post("/predictions/run")
async def predictions_run() -> dict[str, Any]:
    return await _predictions_job()


@app.post("/predictions/validate")
async def predictions_validate() -> dict[str, Any]:
    return await _predictions_validate_job()


@app.get("/predictions/{prediction_id}")
async def prediction_get(prediction_id: int) -> dict[str, Any]:
    pool = await db_pool.get_pool()
    async with pool.acquire() as conn:
        p = await conn.fetchrow("SELECT * FROM predictions WHERE id=$1", prediction_id)
        o = await conn.fetchrow("SELECT * FROM prediction_outcomes WHERE prediction_id=$1", prediction_id)
    if not p:
        raise HTTPException(status_code=404, detail="prediction not found")
    out = pred_mod._prow(p)
    if o:
        od = dict(o)
        for k, v in list(od.items()):
            if hasattr(v, "isoformat"):
                od[k] = v.isoformat()
            elif isinstance(v, str) and k in ("rca_labels", "rca_detail", "model_returns"):
                od[k] = json.loads(v)
        out["outcome"] = od
    out["explanation"] = pred_mod.explain(out)
    return out


# --------------------------------------------------------------------------
# Pro #4 (2026-10-30): portfolio construction - DRAFT policy, suggestions only
# --------------------------------------------------------------------------
@app.get("/portfolio/construction")
async def portfolio_construction() -> dict[str, Any]:
    r = await pc_mod.latest(await db_pool.get_pool())
    if not r:
        r = await pc_mod.run_construction(await db_pool.get_pool())
    return r


@app.post("/portfolio/construction/run")
async def portfolio_construction_run() -> dict[str, Any]:
    return await pc_mod.run_construction(await db_pool.get_pool())


# --------------------------------------------------------------------------
# Pro #6 (2026-10-30): performance measurement & attribution
# --------------------------------------------------------------------------
@app.get("/performance/attribution")
async def performance_attribution() -> dict[str, Any]:
    pool = await db_pool.get_pool()
    r = await attr_mod.latest(pool)
    if not r or r["created_at"][:10] != datetime.now(ZoneInfo("Asia/Bangkok")).date().isoformat():
        r = await attr_mod.run_attribution(pool)
    return r


@app.post("/performance/attribution/run")
async def performance_attribution_run() -> dict[str, Any]:
    return await attr_mod.run_attribution(await db_pool.get_pool())


# --------------------------------------------------------------------------
# 2026-10-30: momentum_base_swing setup (docs/lessons/momentum_base_setup.md). Advisory only: no orders.
# --------------------------------------------------------------------------
@app.get("/setups/momentum-base")
async def setup_mb_screen(passed: bool = False) -> dict[str, Any]:
    pool = await db_pool.get_pool()
    out = await mb_mod.latest_screen(pool, only_passed=passed)
    bt = await mb_mod.latest_backtest(pool)
    out["backtest"] = {k: bt.get(k) for k in ("run_at", "comparison", "live_params", "data_to", "caveats", "risk_pct")} if bt else None
    return out


@app.post("/setups/momentum-base/run")
async def setup_mb_run(plans: bool = True) -> dict[str, Any]:
    return await mb_mod.run_screen(await db_pool.get_pool(), make_plans=plans)


@app.get("/setups/momentum-base/backtest")
async def setup_mb_backtest() -> dict[str, Any]:
    return await mb_mod.latest_backtest(await db_pool.get_pool()) or {"note": "no setup backtest yet"}


@app.post("/setups/momentum-base/backtest/run")
async def setup_mb_backtest_run() -> dict[str, Any]:
    return await _setup_backtest_job()


@app.get("/setups/momentum-base/advisor-context")
async def setup_mb_advisor_context(tickers: str = "") -> dict[str, Any]:
    pool = await db_pool.get_pool()
    scr = await mb_mod.latest_screen(pool)
    bt = await mb_mod.latest_backtest(pool)
    tk = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    return {"context": "\n".join(mb_mod.advisor_lines(scr, bt, tk))}

