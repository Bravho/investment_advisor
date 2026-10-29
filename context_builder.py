import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from db import DatabaseManager

logger = logging.getLogger("InvestmentAdvisor.Context")


def _first(row: dict, *keys: str, default: Any = None) -> Any:
    for key in keys:
        if row.get(key) is not None:
            return row[key]
    return default


def _format_age(value: Any) -> str:
    if not isinstance(value, datetime):
        return "recently"
    now = datetime.now(value.tzinfo or timezone.utc)
    delta = now - value.replace(tzinfo=value.tzinfo or timezone.utc)
    days = max(0, delta.days)
    return "today" if days == 0 else f"{days} day{'s' if days != 1 else ''} ago"


async def _load_similar_article_context(
    message: str,
    tickers: Optional[list[str]] = None,
    limit: int = 5,
    db_manager: Optional[DatabaseManager] = None,
) -> str:
    """
    Inject top-k similar article embeddings into advisor context (RAG).

    Replaces the reserved semantic-retrieval stub. Uses the advisor DB pool when
    available and talks to Ollama directly so we avoid ai_engine/portfolio_engine
    `utils` import collisions. Fail-soft if embeddings/pgvector/Ollama unavailable.
    Added 2026-10-07 (improvement #3).
    """
    query = (message or "").strip() or "Thai portfolio market outlook gold oil bank aviation"
    ticker = None
    if tickers:
        ticker = next((t for t in tickers if t), None)

    try:
        import os

        import httpx

        ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
        embed_model = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{ollama_url}/api/embeddings",
                json={"model": embed_model, "prompt": query},
            )
            response.raise_for_status()
            embedding = response.json().get("embedding") or []
        if len(embedding) != 768:
            logger.debug("Unexpected embedding dims=%s — skipping RAG", len(embedding))
            return ""

        vector_literal = "[" + ",".join(f"{float(x):.8f}" for x in embedding) + "]"

        pool = None
        owns_pool = False
        if db_manager and db_manager.available and db_manager.pool:
            pool = db_manager.pool
        else:
            import asyncpg

            pool = await asyncpg.create_pool(
                host=os.getenv("DB_HOST", "localhost"),
                port=int(os.getenv("DB_PORT", "5432")),
                database=os.getenv("DB_NAME", "investor_db"),
                user=os.getenv("DB_USER", "investor_app"),
                password=os.getenv("DB_PASSWORD", ""),
                min_size=1,
                max_size=2,
                command_timeout=15,
            )
            owns_pool = True

        try:

            async def _fetch(ticker_filter: Optional[str]):
                return await pool.fetch(
                    """
                    SELECT a.title, a.source, a.published_at, e.chunk_text,
                           e.embedding <=> $1::vector AS distance
                    FROM article_embeddings e
                    JOIN news_articles a ON a.id = e.article_id
                    WHERE ($2::text IS NULL OR EXISTS (
                      SELECT 1 FROM sentiment_scores s
                      WHERE s.article_id = a.id AND s.ticker = $2
                    ))
                    ORDER BY distance ASC
                    LIMIT $3
                    """,
                    vector_literal,
                    ticker_filter,
                    limit,
                )

            rows = await _fetch(ticker)
            if not rows and ticker:
                rows = await _fetch(None)
        finally:
            if owns_pool and pool is not None:
                await pool.close()

        if not rows:
            return ""

        lines = ["=== SIMILAR ARTICLES (RAG / embeddings, advisory) ==="]
        used = len(lines[0])
        for i, row in enumerate(rows, 1):
            title = (row.get("title") or "Untitled").strip()
            source = row.get("source") or "?"
            published = str(row.get("published_at") or "")[:10]
            dist = float(row.get("distance") or 0)
            sim = round(1.0 / (1.0 + dist), 4)
            chunk = (row.get("chunk_text") or "").strip().replace("\n", " ")
            if len(chunk) > 280:
                chunk = chunk[:277] + "..."
            block = f"{i}. {title} [{source} | {published} | sim={sim}]\n   {chunk}"
            if used + len(block) + 2 > 1800:
                break
            lines.append(block)
            used += len(block) + 2
        return "\n".join(lines)
    except Exception as exc:
        logger.debug("RAG similar-articles unavailable: %s", exc)
        return ""


async def build_advisory_context(
    message: str,
    tickers: Optional[list[str]] = None,
    db_manager: Optional[DatabaseManager] = None,
) -> str:
    if not db_manager or not db_manager.available:
        # Still try RAG-only context when DB manager is down but embeddings work
        rag_only = await _load_similar_article_context(message, tickers, db_manager=db_manager)
        return rag_only

    try:
        ticker_list = list(dict.fromkeys(tickers or []))
        sentiment_sets, macro, holdings, recommendations, rag_section = await asyncio.gather(
            asyncio.gather(
                *(db_manager.get_recent_sentiment(ticker) for ticker in ticker_list)
            ),
            db_manager.get_latest_macro_sentiment(),
            db_manager.get_portfolio_holdings(),
            db_manager.get_recent_recommendations(limit=5),
            _load_similar_article_context(message, ticker_list, db_manager=db_manager),
        )

        sections: list[str] = []
        if holdings:
            holding_lines = []
            for holding in holdings:
                ticker = _first(holding, "ticker", "symbol", "asset", default="Unknown")
                name = _first(holding, "name", default="")
                asset_class = _first(holding, "asset_class", "type", default="")
                quantity = _first(holding, "quantity", "shares", "units", "amount", default="?")
                avg_cost = _first(holding, "avg_cost_price", "average_price", "cost", default=None)
                currency = _first(holding, "currency", default="THB")

                if asset_class == "mutual_fund":
                    line = f"  - {ticker}"
                    if name:
                        line += f" ({name})"
                    if avg_cost is not None:
                        line += f": cost basis {float(avg_cost):,.0f} {currency}"
                else:
                    line = f"  - {ticker}"
                    if name:
                        line += f" ({name})"
                    line += f": {quantity} shares"
                    if avg_cost is not None:
                        line += f" @ avg cost {float(avg_cost):,.2f} {currency}"
                holding_lines.append(line)

            sections.append(
                "=== USER PORTFOLIO ===\n" + "\n".join(holding_lines)
            )

        sentiment_lines = []
        for ticker, rows in zip(ticker_list, sentiment_sets):
            if not rows:
                continue
            scores = [
                float(_first(row, "score", "sentiment_score", default=0) or 0)
                for row in rows
            ]
            score = sum(scores) / len(scores)
            label = "Bullish" if score > 0.2 else "Bearish" if score < -0.2 else "Neutral"
            sentiment_lines.append(
                f"{ticker}: {label} (score: {score:.2f}, {len(rows)} articles)"
            )
        if sentiment_lines:
            sections.append(
                "=== MARKET SENTIMENT (last 24h) ===\n" + "\n".join(sentiment_lines)
            )

        if macro:
            overall = _first(macro, "overall", "outlook", "label", default="Unknown")
            score = _first(macro, "score", "sentiment_score", default="N/A")
            themes = _first(macro, "key_themes", "themes", default=[])
            if isinstance(themes, str):
                try:
                    themes = json.loads(themes)
                except json.JSONDecodeError:
                    pass
            if isinstance(themes, (list, tuple)):
                themes = ", ".join(str(theme) for theme in themes)
            sections.append(
                f"=== MACRO OUTLOOK ===\nOverall: {overall} | Score: {score}\n"
                f"Key themes: {themes or 'N/A'}"
            )

        if recommendations:
            lines = []
            for recommendation in recommendations:
                ticker = _first(recommendation, "ticker", default="Portfolio")
                action = str(_first(recommendation, "action", default="REVIEW")).upper()
                confidence = _first(recommendation, "confidence", default="N/A")
                created_at = _first(
                    recommendation, "created_at", "recommended_at", default=None
                )
                lines.append(
                    f"{ticker} -> {action} (confidence: {confidence}, {_format_age(created_at)})"
                )
            sections.append(
                "=== RECENT RECOMMENDATIONS ===\n" + "\n".join(lines)
            )

        if rag_section:
            sections.append(rag_section)

        return "\n\n".join(sections)
    except Exception as exc:
        logger.warning("Could not build advisory DB context: %s", exc)
        try:
            return await _load_similar_article_context(message, tickers, db_manager=db_manager)
        except Exception:
            return ""
