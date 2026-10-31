"""News coverage report (2026-11-01, P2.1): scored articles per watch-list / holding ticker, by language.

Usage: venv/bin/python ops/news_coverage_report.py [days]   (read-only; prints JSON)
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "portfolio_engine")]
from utils.db_pool import db_pool  # noqa: E402


async def report(days: int = 14) -> dict:
    pool = await db_pool.get_pool()
    rows = await pool.fetch(
        """WITH u AS (SELECT ticker FROM investment_watchlist WHERE status <> 'dropped'
                      UNION SELECT ticker FROM holdings WHERE quantity > 0)
           SELECT u.ticker,
                  count(DISTINCT s.article_id) AS articles,
                  count(DISTINCT s.article_id) FILTER (WHERE a.title ~ '[ก-๙]') AS thai_lang,
                  count(DISTINCT a.source) AS sources
           FROM u LEFT JOIN sentiment_scores s ON s.ticker = u.ticker AND s.analyzed_at >= now() - make_interval(days => $1)
                  LEFT JOIN news_articles a ON a.id = s.article_id
           GROUP BY u.ticker ORDER BY u.ticker""", days)
    src = await pool.fetch(
        """SELECT split_part(source, ' (', 1) AS src, count(*) n, count(*) FILTER (WHERE title ~ '[ก-๙]') thai
           FROM news_articles WHERE fetched_at >= now() - make_interval(days => $1) GROUP BY 1 ORDER BY 2 DESC""", days)
    items = [dict(r) for r in rows]
    thai = [i for i in items if i["ticker"].endswith(".BK")]
    return {"days": days, "tickers": items,
            "thai_names_with_zero": [i["ticker"] for i in thai if not i["articles"]],
            "zero_total": [i["ticker"] for i in items if not i["articles"]],
            "sources": [dict(r) for r in src]}


if __name__ == "__main__":
    d = int(sys.argv[1]) if len(sys.argv) > 1 else 14
    print(json.dumps(asyncio.run(report(d)), ensure_ascii=False, default=str, indent=1))
