import json
import os
import re
from collections import Counter
from typing import Any, Optional

from utils.common import configure_logging, ollama_chat, parse_json_response
from utils.db_pool import db_pool
from ticker_relevance import filter_tickers, mentioned

logger = configure_logging("ai_engine.sentiment")
SENTIMENT_MODEL = os.getenv(
    "OLLAMA_SENTIMENT_MODEL", "scb10x/typhoon2.5-qwen3-4b:latest"
)

THAI_TICKERS = {
    "ADVANC": "ADVANC.BK", "AOT": "AOT.BK", "PTT": "PTT.BK",
    "KBANK": "KBANK.BK", "SCB": "SCB.BK", "CPF": "CPF.BK",
    "CPALL": "CPALL.BK", "DELTA": "DELTA.BK", "GULF": "GULF.BK",
    "TRUE": "TRUE.BK", "BDMS": "BDMS.BK", "KTB": "KTB.BK",
    "PTTEP": "PTTEP.BK", "BBL": "BBL.BK", "TTB": "TTB.BK", "TOP": "TOP.BK", "IRPC": "IRPC.BK", "BAFS": "BAFS.BK",
}
KEYWORD_TICKERS = {
    "BITCOIN": "BTC-USD", "BTC": "BTC-USD", "ETHEREUM": "ETH-USD",
    "ETH": "ETH-USD", "SOLANA": "SOL-USD", "APPLE": "AAPL",
    "S&P 500": "SPY", "SET INDEX": None,
}


async def watchlist() -> set[str]:
    configured = {
        item.strip().upper()
        for item in os.getenv("WATCHLIST_TICKERS", "").split(",")
        if item.strip()
    }
    pool = await db_pool.get_pool()
    rows = await pool.fetch("SELECT ticker FROM holdings")
    return configured | {row["ticker"].upper() for row in rows if row["ticker"]}


def extract_tickers(text: str, allowed_us: set[str]) -> list[str]:
    """Tickers explicitly mentioned in the article (tightened 2026-10-31).

    Before: the text was UPPER-cased first, so the words "true", "delta", "gulf" became TRUE.BK / DELTA.BK /
    GULF.BK. Now symbols must appear case-sensitively and ambiguous symbols need the company name
    (see ticker_relevance.py)."""
    found: list[str] = []
    for keyword, ticker in {**THAI_TICKERS, **KEYWORD_TICKERS}.items():
        if ticker and mentioned(ticker, text):
            found.append(ticker)
    for token in re.findall(r"(?<![A-Za-z0-9])[A-Z]{2,5}(?:\.BK|-[A-Z]{3})?(?![A-Za-z0-9])", text):
        t = THAI_TICKERS.get(token, token)
        if (token in allowed_us or token in THAI_TICKERS) and mentioned(t, text):
            found.append(t)
    return list(dict.fromkeys(found))


_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-=^]{0,19}$")


def normalized_result(raw: dict[str, Any]) -> dict[str, Any]:
    sentiment = str(raw.get("sentiment", "neutral")).lower()
    if sentiment not in {"bullish", "bearish", "neutral"}:
        sentiment = "neutral"
    impact = str(raw.get("impact_level", "low")).lower()
    if impact not in {"high", "medium", "low"}:
        impact = "low"
    return {
        "sentiment": sentiment,
        "score": max(-1.0, min(1.0, float(raw.get("score", 0)))),
        "confidence": max(0.0, min(1.0, float(raw.get("confidence", 0)))),
        "impact_level": impact,
        "affected_tickers": list(
            dict.fromkeys(
                THAI_TICKERS.get(str(ticker).upper(), str(ticker).upper())
                for ticker in raw.get("affected_tickers", [])
                # Fixed 2026-10-29: LLM sometimes returns company names / long
                # strings here, which overflowed sentiment_scores.ticker.
                if ticker and _TICKER_RE.match(str(ticker).strip().upper())
            )
        ),
        "reasoning": str(raw.get("reasoning", ""))[:1000],
    }


async def analyze_article(title: str, content: str) -> dict[str, Any]:
    prompt = f"""Analyze the investment sentiment of this financial news article.
Respond ONLY with valid JSON (no markdown):
{{
  "sentiment": "bullish" | "bearish" | "neutral",
  "score": float between -1.0 and 1.0,
  "confidence": float between 0.0 and 1.0,
  "impact_level": "high" | "medium" | "low",
  "affected_tickers": ["TICKER1", "TICKER2"],
  "reasoning": "one sentence explanation"
}}
Article: {title}\n\n{content[:1500]}"""
    return normalized_result(parse_json_response(await ollama_chat(SENTIMENT_MODEL, prompt, 30)))


async def run_sentiment_pipeline() -> dict[str, Any]:
    pool = await db_pool.get_pool()
    articles = await pool.fetch(
        """
        SELECT id, title, content FROM news_articles
        WHERE is_processed = FALSE
        ORDER BY published_at DESC NULLS LAST, fetched_at DESC
        LIMIT 20
        """
    )
    allowed = await watchlist()
    processed = 0
    scores_created = 0
    confidences: list[float] = []
    distribution: Counter = Counter()
    for article in articles:
        try:
            extracted = extract_tickers(
                f"{article['title']}\n{article['content'] or ''}", allowed
            )
            result = await analyze_article(article["title"], article["content"] or "")
            # 2026-10-31: LLM-proposed tickers are kept only if the symbol or company name is in the article;
            # at most ticker_relevance.MAX_TICKERS per article (was unbounded: one story got 9-31 tags).
            _text = f"{article['title']}\n{article['content'] or ''}"
            affected = filter_tickers(extracted + result["affected_tickers"], _text) or [None]
            async with pool.acquire() as connection:
                async with connection.transaction():
                    for ticker in affected:
                        await connection.execute(
                            """
                            INSERT INTO sentiment_scores (
                                article_id, ticker, sentiment, score, confidence,
                                impact_level, llm_model
                            ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                            """,
                            article["id"], ticker, result["sentiment"], result["score"],
                            result["confidence"], result["impact_level"], SENTIMENT_MODEL,
                        )
                    await connection.execute(
                        "UPDATE news_articles SET is_processed = TRUE WHERE id = $1",
                        article["id"],
                    )
            processed += 1
            scores_created += len(affected)
            confidences.append(result["confidence"])
            distribution[result["sentiment"]] += 1
        except Exception:
            logger.exception("Sentiment processing failed for article %s", article["id"])
    summary = {
        "articles_processed": processed,
        "sentiment_scores_created": scores_created,
        "avg_confidence": round(sum(confidences) / len(confidences), 4) if confidences else 0,
        "distribution": dict(distribution),
    }
    logger.info("Sentiment pipeline complete: %s", json.dumps(summary))
    return summary
