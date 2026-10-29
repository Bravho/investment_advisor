import logging
import os
from uuid import uuid4
from typing import Any, Optional

import asyncpg
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("InvestmentAdvisor.Database")


class DatabaseManager:
    def __init__(self) -> None:
        self.pool: Optional[asyncpg.Pool] = None

    @property
    def available(self) -> bool:
        return self.pool is not None

    async def connect(self) -> bool:
        try:
            self.pool = await asyncpg.create_pool(
                host=os.getenv("DB_HOST", "localhost"),
                port=int(os.getenv("DB_PORT", "5432")),
                database=os.getenv("DB_NAME", "investor_db"),
                user=os.getenv("DB_USER", "investor_app"),
                password=os.getenv("DB_PASSWORD", ""),
                min_size=1,
                max_size=5,
                command_timeout=10,
            )
            await self._ensure_query_logs_table()
            logger.info("PostgreSQL connection pool initialized")
            return True
        except Exception as exc:
            self.pool = None
            logger.warning("PostgreSQL unavailable; continuing without DB: %s", exc)
            return False

    async def close(self) -> None:
        if self.pool:
            await self.pool.close()
            self.pool = None

    def _require_pool(self) -> asyncpg.Pool:
        if not self.pool:
            raise ConnectionError("Database connection pool is unavailable")
        return self.pool

    async def _ensure_query_logs_table(self) -> None:
        pool = self._require_pool()
        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS query_logs (
                id UUID PRIMARY KEY,
                sender VARCHAR,
                query TEXT,
                response TEXT,
                success BOOL,
                llm_model_used VARCHAR,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
            """
        )

    async def get_recent_sentiment(self, ticker: str, hours: int = 24) -> list[dict]:
        pool = self._require_pool()
        rows = await pool.fetch(
            """
            SELECT ss.*, na.*
            FROM sentiment_scores ss
            JOIN news_articles na ON na.id = ss.article_id
            WHERE ss.ticker = $1
              AND ss.analyzed_at >= NOW() - ($2 * INTERVAL '1 hour')
            ORDER BY ss.analyzed_at DESC
            LIMIT 10
            """,
            ticker,
            hours,
        )
        return [dict(row) for row in rows]

    async def get_portfolio_holdings(self) -> list[dict]:
        pool = self._require_pool()
        rows = await pool.fetch("SELECT * FROM holdings")
        return [dict(row) for row in rows]

    async def get_latest_macro_sentiment(self) -> Optional[dict]:
        pool = self._require_pool()
        row = await pool.fetchrow(
            "SELECT * FROM macro_sentiment ORDER BY snapshot_date DESC LIMIT 1"
        )
        return dict(row) if row else None

    async def get_recent_recommendations(
        self, ticker: Optional[str] = None, limit: int = 5
    ) -> list[dict]:
        pool = self._require_pool()
        if ticker:
            rows = await pool.fetch(
                """
                SELECT * FROM recommendations
                WHERE ticker = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                ticker,
                limit,
            )
        else:
            rows = await pool.fetch(
                "SELECT * FROM recommendations ORDER BY created_at DESC LIMIT $1",
                limit,
            )
        return [dict(row) for row in rows]

    async def save_recommendation(
        self,
        ticker: str,
        action: str,
        confidence: float,
        rationale: str,
        llm_model: str,
        sentiment_snapshot: Any,
        price_at_recommendation: Optional[float],
    ) -> str:
        pool = self._require_pool()
        recommendation_id = await pool.fetchval(
            """
            INSERT INTO recommendations (
                ticker, action, confidence, rationale, llm_model,
                sentiment_snapshot, price_at_recommendation
            )
            VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7)
            RETURNING id
            """,
            ticker,
            action,
            confidence,
            rationale,
            llm_model,
            sentiment_snapshot,
            price_at_recommendation,
        )
        return str(recommendation_id)

    async def log_query(
        self,
        sender: str,
        query: str,
        response: str,
        success: bool,
        llm_model_used: str,
    ) -> None:
        pool = self._require_pool()
        await pool.execute(
            """
            INSERT INTO query_logs (
                id, sender, query, response, success, llm_model_used
            )
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            uuid4(),
            sender,
            query,
            response,
            success,
            llm_model_used,
        )

    async def get_recent_query_logs(self, limit: int = 50) -> list[dict]:
        pool = self._require_pool()
        rows = await pool.fetch(
            "SELECT * FROM query_logs ORDER BY created_at DESC LIMIT $1", limit
        )
        return [dict(row) for row in rows]

    async def get_latest_sentiment_overview(self, limit: int = 10) -> list[dict]:
        pool = self._require_pool()
        rows = await pool.fetch(
            """
            SELECT DISTINCT ON (ss.ticker) ss.*, na.*
            FROM sentiment_scores ss
            JOIN news_articles na ON na.id = ss.article_id
            WHERE ss.ticker IS NOT NULL
            ORDER BY ss.ticker, ss.analyzed_at DESC
            LIMIT $1
            """,
            limit,
        )
        return [dict(row) for row in rows]
