import json
import re
from collections import Counter, defaultdict
from typing import Any

from utils.common import configure_logging
from utils.db_pool import db_pool

logger = configure_logging("ai_engine.macro")
# Expanded keyword set — Added by nightly agent 2026-06-08
# Now covers BOT (Thailand), Fed (US), BOJ (Japan), ECB (EU), RBI (India)
# plus gold, currency, and Vietnam FTSE upgrade catalyst
KEYWORDS = [
    # Thailand
    "Fed", "interest rate", "inflation", "GDP", "recession", "BOT",
    "ธนาคารแห่งประเทศไทย", "เงินเฟ้อ", "SET index",
    # US monetary policy
    "Federal Reserve", "FOMC", "rate cut", "rate hike", "CPI", "PCE",
    # Japan
    "BOJ", "Bank of Japan", "Nikkei", "yen",
    # Europe
    "ECB", "European Central Bank", "DAX", "euro",
    # India
    "RBI", "Reserve Bank of India", "Nifty", "Sensex",
    # Vietnam
    "VN-Index", "Vietnam", "FTSE emerging market",
    # Gold & commodities
    "gold price", "XAU", "oil price", "OPEC",
    # Currency
    "USD THB", "baht", "dollar",
    # AI / tech macro
    "AI investment", "semiconductor", "data center",
]
SECTORS = {
    # Thai stocks
    "AAPL": "technology", "ADVANC.BK": "technology", "DELTA.BK": "technology",
    "GULF.BK": "energy", "PTT.BK": "energy", "PTTEP.BK": "energy",
    "KBANK.BK": "financials", "SCB.BK": "financials", "KTB.BK": "financials",
    "BAFS.BK": "energy_services",
    # US tech (Added 2026-06-08)
    "NVDA": "technology", "MU": "technology", "AVGO": "technology",
    "MSFT": "technology", "GOOGL": "technology", "META": "technology",
    # Gold
    "GLD": "gold", "IAU": "gold", "SCBGOLDE": "gold",
    # EM ETFs (Added 2026-06-08)
    "VNM": "vietnam", "INDA": "india", "EWJ": "japan", "FXI": "china",
    # Crypto (kept for completeness, not a focus)
    "BTC-USD": "crypto", "ETH-USD": "crypto", "SOL-USD": "crypto",
}
IMPACT = {"high": 1.5, "medium": 1.0, "low": 0.5}
# 2026-11-01: crypto exclusion (tickers + headline words) - see portfolio_engine/crypto_events.py for the crypto card
CRYPTO_TICKER_RE = r"^(BTC|ETH|SOL|XRP|DOGE|ADA|BNB|AVAX|DOT|LINK|LTC|TRX|TON|SHIB|MATIC|USDT|USDC)(-USD)?$|^(MSTR|COIN|IBIT|FBTC|GBTC|ETHA|MARA|RIOT)$"
CRYPTO_TITLE_RE = r"bitcoin|\mbtc\M|ethereum|\meth\M|crypto|stablecoin|binance|coinbase|solana|\mxrp\M|dogecoin|blockchain|\mdefi\M|\mnft|tether|altcoin|memecoin|คริปโต|บิตคอยน์"


async def aggregate_macro_sentiment() -> dict[str, Any]:
    pool = await db_pool.get_pool()
    rows = await pool.fetch(
        """
        SELECT DISTINCT s.id, s.article_id, s.ticker, s.score, s.confidence,
               s.impact_level, a.title
        FROM sentiment_scores s
        JOIN news_articles a ON a.id = s.article_id
        WHERE s.analyzed_at >= NOW() - INTERVAL '24 hours'
          -- 2026-11-01 (Tho): crypto stays OUT of the market-mood verdict; high-impact crypto events have their own card
          AND NOT (COALESCE(s.ticker, '') ~* $2 OR COALESCE(a.title, '') ~* $3)
          AND (
            s.ticker IS NULL OR
            a.title ILIKE ANY($1::text[]) OR
            a.content ILIKE ANY($1::text[])
          )
        """,
        [f"%{keyword}%" for keyword in KEYWORDS],
        CRYPTO_TICKER_RE,
        CRYPTO_TITLE_RE,
    )
    weighted_sum = 0.0
    total_weight = 0.0
    sector_values: dict[str, list[float]] = defaultdict(list)
    theme_counts: Counter = Counter()
    article_ids = set()
    for row in rows:
        weight = float(row["confidence"] or 0) * IMPACT.get(row["impact_level"], 1.0)
        weighted_sum += float(row["score"] or 0) * weight
        total_weight += weight
        article_ids.add(row["article_id"])
        if row["ticker"] in SECTORS:
            sector_values[SECTORS[row["ticker"]]].append(float(row["score"] or 0))
        title = row["title"] or ""
        for keyword in KEYWORDS:
            if re.search(re.escape(keyword), title, re.IGNORECASE):
                theme_counts[keyword] += 1
    overall = round(weighted_sum / total_weight, 4) if total_weight else 0.0
    mood = "risk-on" if overall > 0.2 else "risk-off" if overall < -0.2 else "neutral"
    sector_scores = {
        sector: round(sum(scores) / len(scores), 4)
        for sector, scores in sector_values.items()
    }
    themes = [theme for theme, _ in theme_counts.most_common(5)]
    await pool.execute(
        """
        INSERT INTO macro_sentiment (
            snapshot_date, overall_score, market_mood, sector_scores,
            key_themes, source_article_ids
        ) VALUES (CURRENT_DATE, $1, $2, $3::jsonb, $4::text[], $5::uuid[])
        ON CONFLICT (snapshot_date) DO UPDATE SET
            overall_score = EXCLUDED.overall_score,
            market_mood = EXCLUDED.market_mood,
            sector_scores = EXCLUDED.sector_scores,
            key_themes = EXCLUDED.key_themes,
            source_article_ids = EXCLUDED.source_article_ids,
            created_at = NOW()
        """,
        overall, mood, json.dumps(sector_scores), themes, list(article_ids),
    )
    result = {
        "records_saved": 1, "overall_score": overall, "market_mood": mood,
        "sector_scores": sector_scores, "key_themes": themes,
        "articles_analyzed": len(article_ids),
    }
    logger.info("Macro aggregation complete: %s", result)
    return result
