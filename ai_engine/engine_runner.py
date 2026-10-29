import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable
from zoneinfo import ZoneInfo

import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI

from embedding_pipeline import run_embedding_pipeline
from macro_aggregator import aggregate_macro_sentiment
from risk_scorer import archive_daily_snapshot, calculate_portfolio_risk, save_daily_performance
from sentiment_pipeline import run_sentiment_pipeline
from utils.common import configure_logging
from utils.db_pool import db_pool

logger = configure_logging("ai_engine.runner")
ICT = ZoneInfo("Asia/Bangkok")
UTC = timezone.utc
scheduler = AsyncIOScheduler(
    timezone=ICT,
    job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 300},
)
pipeline_state: dict[str, dict[str, Any]] = {
    name: {"status": "never_run", "last_run": None, "duration_seconds": None, "result": None}
    for name in ("sentiment_pipeline", "embedding_pipeline", "macro_aggregator", "save_daily_performance", "archive_daily_snapshot")
}
pipeline_locks = {name: asyncio.Lock() for name in pipeline_state}
active_tasks: set[asyncio.Task] = set()


async def execute_pipeline(name: str, function: Callable[[], Awaitable[dict]]) -> None:
    current_task = asyncio.current_task()
    if current_task:
        active_tasks.add(current_task)
    lock = pipeline_locks[name]
    if lock.locked():
        logger.warning("Skipping overlapping run of %s", name)
        if current_task:
            active_tasks.discard(current_task)
        return
    try:
        async with lock:
            started = time.perf_counter()
            pipeline_state[name]["status"] = "running"
            try:
                result = await function()
                pipeline_state[name].update(
                    status="ok",
                    last_run=datetime.now(UTC).isoformat(),
                    duration_seconds=round(time.perf_counter() - started, 3),
                    result=result,
                )
                logger.info("%s completed in %.3fs: %s", name, time.perf_counter() - started, result)
            except Exception as exc:
                pipeline_state[name].update(
                    status="error",
                    last_run=datetime.now(UTC).isoformat(),
                    duration_seconds=round(time.perf_counter() - started, 3),
                    result={"error": str(exc)},
                )
                logger.exception("%s failed without stopping runner", name)
    finally:
        if current_task:
            active_tasks.discard(current_task)


def schedule_pipeline(name: str, function: Callable[[], Awaitable[dict]], trigger: str, **kwargs: Any) -> None:
    scheduler.add_job(
        execute_pipeline,
        trigger,
        args=[name, function],
        id=name,
        replace_existing=True,
        **kwargs,
    )


def configure_schedules() -> None:
    schedule_pipeline("sentiment_pipeline", run_sentiment_pipeline, "interval", minutes=10)
    schedule_pipeline("embedding_pipeline", run_embedding_pipeline, "interval", minutes=15)
    schedule_pipeline("macro_aggregator", aggregate_macro_sentiment, "interval", hours=2)
    schedule_pipeline(
        "save_daily_performance", save_daily_performance, "cron", hour=17, minute=30
    )
    # Added by nightly agent 2026-06-23 — resolves the long-standing queued #1.
    # save_daily_performance() archives data/snapshots/ only AFTER its Postgres
    # write, so when the DB is down the archive line never runs and the trend
    # store stays empty (derive_gold_trailing_high / multi-day drawdown stay
    # inert). archive_daily_snapshot() is the DB-free writer; schedule it 5 min
    # AFTER save_daily_performance so the archive fills regardless of DB state.
    # It's idempotent (writes today's dated file), so running both is harmless.
    schedule_pipeline(
        "archive_daily_snapshot", archive_daily_snapshot, "cron", hour=17, minute=35
    )


async def run_initial_pipelines() -> None:
    for name, function in (
        ("sentiment_pipeline", run_sentiment_pipeline),
        ("embedding_pipeline", run_embedding_pipeline),
        ("macro_aggregator", aggregate_macro_sentiment),
    ):
        task = asyncio.create_task(execute_pipeline(name, function))
        active_tasks.add(task)
        task.add_done_callback(active_tasks.discard)


@asynccontextmanager
async def lifespan(app: FastAPI):
    del app
    await db_pool.connect()
    configure_schedules()
    scheduler.start()
    await run_initial_pipelines()
    logger.info("AI engine runner started")
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)
        if active_tasks:
            logger.info("Waiting for %s active pipeline batch(es)", len(active_tasks))
            await asyncio.gather(*active_tasks, return_exceptions=True)
        await db_pool.close()
        logger.info("AI engine runner stopped")


app = FastAPI(title="Investor AI Analysis Engine", version="2.0.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "pipelines": {
            name: {"status": state["status"], "last_run": state["last_run"]}
            for name, state in pipeline_state.items()
        },
    }


@app.get("/metrics")
async def metrics() -> dict[str, Any]:
    pool = await db_pool.get_pool()
    row = await pool.fetchrow(
        """
        SELECT
          (SELECT COUNT(*) FROM news_articles
           WHERE is_processed = TRUE AND fetched_at::date = CURRENT_DATE) AS articles,
          (SELECT COUNT(*) FROM article_embeddings
           WHERE created_at::date = CURRENT_DATE) AS embeddings,
          (SELECT COUNT(*) FROM sentiment_scores
           WHERE analyzed_at::date = CURRENT_DATE) AS sentiments,
          (SELECT MAX(created_at) FROM macro_sentiment) AS macro_updated,
          (SELECT risk_score FROM portfolio_performance
           ORDER BY record_date DESC LIMIT 1) AS portfolio_risk
        """
    )
    risk = row["portfolio_risk"]
    if risk is None:
        try:
            risk = (await calculate_portfolio_risk())["portfolio_risk_score"]
        except Exception:
            logger.exception("Live risk metric calculation failed")
    return {
        "articles_processed_today": row["articles"],
        "embeddings_created_today": row["embeddings"],
        "sentiment_scores_today": row["sentiments"],
        "macro_last_updated": row["macro_updated"].isoformat() if row["macro_updated"] else None,
        "portfolio_risk_score": float(risk) if risk is not None else None,
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("AI_ENGINE_PORT", "8997")))
