from __future__ import annotations
import os
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from utils.common import configure_logging, latest_price, save_recommendation
from utils.db_pool import db_pool

logger = configure_logging("portfolio_engine.opportunities")
UTC = timezone.utc
MODEL = os.getenv("OLLAMA_ADVISORY_MODEL", "hermes3:8b")


def watchlist() -> list[str]:
    return list(
        dict.fromkeys(
            ticker.strip().upper()
            for ticker in os.getenv("WATCHLIST_TICKERS", "").split(",")
            if ticker.strip()
        )
    )


def sentiment_signal(score: float) -> str:
    if score > 0.6:
        return "strong_bullish"
    if score > 0.2:
        return "bullish"
    if score < -0.6:
        return "strong_bearish"
    if score < -0.2:
        return "bearish"
    return "neutral"


def calculate_rsi(prices: list[float], period: int = 14) -> float:
    if len(prices) < period + 1:
        return 50.0
    changes = pd.Series(prices, dtype=float).diff().dropna()
    gains = changes.clip(lower=0).tail(period).mean()
    losses = -changes.clip(upper=0).tail(period).mean()
    if losses == 0:
        return 100.0 if gains > 0 else 50.0
    return float(100 - 100 / (1 + gains / losses))


def composite_score(sentiment: float, rsi: float, volume_ratio: float, trend: float) -> float:
    sentiment_component = np.clip((sentiment + 1) / 2 * 100 + np.clip(trend * 20, -10, 10), 0, 100)
    price_component = 90 if rsi < 30 else 20 if rsi > 70 else 70 if rsi < 45 else 50
    volume_component = 100 if volume_ratio > 1.5 else 50
    return round(float(sentiment_component * 0.4 + price_component * 0.4 + volume_component * 0.2), 2)


async def _sentiment_metrics(pool: Any, ticker: str) -> tuple[float, float]:
    row = await pool.fetchrow(
        """
        SELECT
          AVG(score) FILTER (WHERE analyzed_at >= NOW() - INTERVAL '24 hours') AS avg_24h,
          AVG(score) FILTER (WHERE analyzed_at >= NOW() - INTERVAL '6 hours') AS avg_6h,
          AVG(score) FILTER (
            WHERE analyzed_at < NOW() - INTERVAL '6 hours'
              AND analyzed_at >= NOW() - INTERVAL '24 hours'
          ) AS avg_prior
        FROM sentiment_scores WHERE ticker = $1
        """,
        ticker,
    )
    avg_24h = float(row["avg_24h"] or 0)
    return avg_24h, float(row["avg_6h"] or 0) - float(row["avg_prior"] or 0)


async def _price_metrics(pool: Any, ticker: str) -> dict[str, float]:
    rows = await pool.fetch(
        """
        SELECT close_price, volume FROM market_prices
        WHERE ticker = $1 ORDER BY price_date DESC LIMIT 20
        """,
        ticker,
    )
    ordered = list(reversed(rows))
    prices = [float(row["close_price"]) for row in ordered if row["close_price"] is not None]
    volumes = [float(row["volume"] or 0) for row in ordered]
    current = prices[-1] if prices else 0.0
    sma20 = float(np.mean(prices)) if prices else 0.0
    average_volume = float(np.mean(volumes[:-1] or volumes)) if volumes else 0.0
    return {
        "current": current,
        "sma20": sma20,
        "price_vs_sma20": ((current - sma20) / sma20 * 100) if sma20 else 0.0,
        "rsi": calculate_rsi(prices),
        "volume_ratio": (volumes[-1] / average_volume) if volumes and average_volume else 0.0,
    }


async def scan_opportunities() -> list[dict[str, Any]]:
    pool = await db_pool.get_pool()
    results = []
    for ticker in watchlist():
        try:
            sentiment, trend = await _sentiment_metrics(pool, ticker)
            metrics = await _price_metrics(pool, ticker)
            rsi = metrics["rsi"]
            score = composite_score(sentiment, rsi, metrics["volume_ratio"], trend)
            signal = "strong_opportunity" if score > 70 else "opportunity" if score > 50 else "avoid" if score < 30 else "neutral"
            price_signal = "oversold" if rsi < 30 else "overbought" if rsi > 70 else "neutral"
            suggested_action = "accumulate" if score > 70 else "watch"
            item = {
                "ticker": ticker,
                "opportunity_score": score,
                "signal": signal,
                "sentiment_signal": sentiment_signal(sentiment),
                "sentiment_trend": round(trend, 4),
                "price_signal": price_signal,
                "volume_signal": "high_volume" if metrics["volume_ratio"] > 1.5 else "normal",
                "rsi": round(rsi, 2),
                "price_vs_sma20": f"{metrics['price_vs_sma20']:+.2f}%",
                "suggested_action": suggested_action,
                "confidence": round(min(0.95, score / 100), 4),
                "scanned_at": datetime.now(UTC).isoformat(),
            }
            results.append(item)
            if score > 60:
                await save_recommendation(
                    pool,
                    ticker=ticker,
                    action=suggested_action,
                    confidence=item["confidence"],
                    rationale=f"{signal}: {item['sentiment_signal']}, {price_signal}, {item['volume_signal']}",
                    sentiment_snapshot={"score": sentiment, "trend": trend},
                    price=metrics["current"],
                    llm_model=MODEL,
                )
        except Exception:
            logger.exception("Opportunity scan failed for %s", ticker)
    return sorted(results, key=lambda item: item["opportunity_score"], reverse=True)


# ---------------------------------------------------------------------------
# News → ticker → ranked ADVISORY candidates
# Added 2026-10-07 (improvement #2)
# ---------------------------------------------------------------------------
# Joins news_articles + sentiment_scores (and optional prior recommendations)
# into ranked advisory candidates. Explicitly advisory_only — never auto-trades.


def _impact_weight(level: str | None) -> float:
    mapping = {"high": 1.0, "medium": 0.65, "low": 0.35}
    return mapping.get(str(level or "").lower(), 0.4)


def _advisory_rank_score(
    sentiment_score: float,
    confidence: float,
    impact_level: str | None,
    article_count: int,
) -> float:
    """0–100 rank: magnitude of sentiment × confidence × impact, with a mild article-count boost."""
    magnitude = abs(float(sentiment_score))
    impact = _impact_weight(impact_level)
    conf = max(0.0, min(1.0, float(confidence or 0)))
    count_boost = min(0.15, 0.03 * max(0, article_count - 1))
    return round(min(100.0, (magnitude * conf * impact * 100.0) + count_boost * 100.0), 2)


async def scan_advisory_candidates(
    limit: int = 15,
    lookback_hours: int = 48,
) -> list[dict[str, Any]]:
    """
    Rank news-linked tickers into ADVISORY candidates (no auto-trade).

    Uses existing DB tables: news_articles, sentiment_scores, recommendations.
    Output items are marked advisory_only=True and status=advisory_candidate.
    """
    pool = await db_pool.get_pool()
    rows = await pool.fetch(
        """
        SELECT
          s.ticker,
          COUNT(*)::int AS article_count,
          AVG(s.score)::float AS avg_score,
          AVG(s.confidence)::float AS avg_confidence,
          MAX(s.analyzed_at) AS last_analyzed_at,
          MODE() WITHIN GROUP (ORDER BY s.impact_level) AS dominant_impact,
          MODE() WITHIN GROUP (ORDER BY s.sentiment) AS dominant_sentiment,
          (ARRAY_AGG(a.title ORDER BY s.analyzed_at DESC))[1] AS latest_title,
          (ARRAY_AGG(a.source ORDER BY s.analyzed_at DESC))[1] AS latest_source,
          (ARRAY_AGG(a.published_at ORDER BY s.analyzed_at DESC))[1] AS latest_published_at
        FROM sentiment_scores s
        JOIN news_articles a ON a.id = s.article_id
        WHERE s.ticker IS NOT NULL
          AND TRIM(s.ticker) <> ''
          AND s.analyzed_at >= NOW() - ($1::text || ' hours')::interval
        GROUP BY s.ticker
        HAVING COUNT(*) >= 1
        ORDER BY ABS(AVG(s.score)) * AVG(COALESCE(s.confidence, 0.5)) DESC
        LIMIT $2
        """,
        str(int(lookback_hours)),
        max(limit * 3, limit),
    )

    # Prior recommendations (last 7d) — enrich, do not auto-act
    prior = await pool.fetch(
        """
        SELECT DISTINCT ON (ticker)
          ticker, action, confidence, rationale, created_at
        FROM recommendations
        WHERE created_at >= NOW() - INTERVAL '7 days'
          AND ticker IS NOT NULL
        ORDER BY ticker, created_at DESC
        """
    )
    prior_by_ticker = {str(r["ticker"]).upper(): dict(r) for r in prior}

    candidates: list[dict[str, Any]] = []
    now = datetime.now(UTC).isoformat()
    for row in rows:
        ticker = str(row["ticker"]).upper()
        avg_score = float(row["avg_score"] or 0)
        avg_conf = float(row["avg_confidence"] or 0)
        impact = row["dominant_impact"]
        article_count = int(row["article_count"] or 0)
        rank = _advisory_rank_score(avg_score, avg_conf, impact, article_count)
        signal = sentiment_signal(avg_score)
        if avg_score > 0.2:
            suggested = "review_buy"
        elif avg_score < -0.2:
            suggested = "review_reduce"
        else:
            suggested = "monitor"
        prev = prior_by_ticker.get(ticker)
        item = {
            "ticker": ticker,
            "advisory_only": True,
            "status": "advisory_candidate",
            "rank_score": rank,
            "opportunity_score": rank,  # dashboard-compatible
            "signal": signal,
            "sentiment_score": round(avg_score, 4),
            "sentiment_signal": signal,
            "confidence": round(min(0.95, avg_conf if avg_conf > 0 else rank / 100), 4),
            "impact_level": impact,
            "article_count": article_count,
            "latest_headline": row["latest_title"],
            "latest_source": row["latest_source"],
            "latest_published_at": row["latest_published_at"].isoformat()
            if row["latest_published_at"]
            else None,
            "last_analyzed_at": row["last_analyzed_at"].isoformat()
            if row["last_analyzed_at"]
            else None,
            "suggested_action": suggested,
            "prior_recommendation": (
                {
                    "action": prev.get("action"),
                    "confidence": float(prev["confidence"]) if prev.get("confidence") is not None else None,
                    "rationale": (prev.get("rationale") or "")[:200],
                    "created_at": prev["created_at"].isoformat() if prev.get("created_at") else None,
                }
                if prev
                else None
            ),
            "human_approval_required": True,
            "actionable": False,
            "scanned_at": now,
            "source": "news_sentiment_join",
        }
        candidates.append(item)

    ranked = sorted(candidates, key=lambda x: x["rank_score"], reverse=True)[:limit]

    # Persist as advisory recommendations (deduped by save_recommendation window)
    for item in ranked[:10]:
        if item["rank_score"] < 25:
            continue
        try:
            await save_recommendation(
                pool,
                ticker=item["ticker"],
                action=item["suggested_action"],
                confidence=item["confidence"],
                rationale=(
                    f"[ADVISORY] news→ticker candidate: {item['signal']} "
                    f"({item['article_count']} articles, impact={item['impact_level']}); "
                    f"headline: {item.get('latest_headline') or 'n/a'}"
                ),
                sentiment_snapshot={
                    "advisory_only": True,
                    "status": "advisory_candidate",
                    "rank_score": item["rank_score"],
                    "avg_score": item["sentiment_score"],
                    # 2026-10-31: explicit labels so the dashboard no longer shows every row as NEUTRAL
                    "score": item["sentiment_score"],
                    "signal": item["signal"],
                    "sentiment": ("bullish" if "bullish" in str(item["signal"]) else "bearish" if "bearish" in str(item["signal"]) else "neutral"),
                    "headline": item.get("latest_headline"),
                    "impact_level": item.get("impact_level"),
                    "source": "scan_advisory_candidates",
                },
                price=0.0,
                llm_model=MODEL,
            )
        except Exception:
            logger.exception("Could not persist advisory candidate for %s", item["ticker"])

    logger.info(
        "scan_advisory_candidates: %d ranked advisory candidates (lookback=%dh)",
        len(ranked),
        lookback_hours,
    )
    return ranked



# ---------------------------------------------------------------------------
# Multi-market tech screener — Added by nightly agent 2026-06-11
# ---------------------------------------------------------------------------
# Scans US (Nasdaq), Japan, India, and Vietnam tech/growth stocks for
# momentum signals using yfinance. Returns scored opportunities ranked by
# composite score, compatible with scan_opportunities() output format.
# Requires: yfinance (add to requirements.txt if not present)

_TECH_UNIVERSE: dict[str, dict[str, str]] = {
    # US — AI / Semiconductor / Mega-cap tech
    "NVDA":  {"name": "NVIDIA",             "market": "Nasdaq",  "sector": "semiconductor"},
    "MU":    {"name": "Micron Technology",  "market": "Nasdaq",  "sector": "memory"},
    "AVGO":  {"name": "Broadcom",           "market": "Nasdaq",  "sector": "semiconductor"},
    "MSFT":  {"name": "Microsoft",          "market": "Nasdaq",  "sector": "cloud_ai"},
    "GOOGL": {"name": "Alphabet",           "market": "Nasdaq",  "sector": "cloud_ai"},
    "INTC":  {"name": "Intel",              "market": "Nasdaq",  "sector": "semiconductor"},
    "AMD":   {"name": "AMD",                "market": "Nasdaq",  "sector": "semiconductor"},
    "TSM":   {"name": "TSMC ADR",           "market": "Nasdaq",  "sector": "foundry"},
    # Japan — Semiconductor / AI hardware
    "6857.T": {"name": "Advantest",         "market": "Nikkei",  "sector": "semiconductor"},
    "8035.T": {"name": "Tokyo Electron",    "market": "Nikkei",  "sector": "semiconductor"},
    "6594.T": {"name": "Nidec",             "market": "Nikkei",  "sector": "industrial_tech"},
    # India — IT services / AI
    "INFY":  {"name": "Infosys ADR",        "market": "Nifty",   "sector": "it_services"},
    "WIT":   {"name": "Wipro ADR",          "market": "Nifty",   "sector": "it_services"},
    # Vietnam (via ETF proxy)
    "VNM":   {"name": "VanEck Vietnam ETF", "market": "Vietnam", "sector": "em_proxy"},
    # SET Thailand — AI/data-center beneficiaries
    "GULF.BK":  {"name": "Gulf Energy",    "market": "SET",     "sector": "energy_data_center"},
    "DELTA.BK": {"name": "Delta Electronics TH", "market": "SET", "sector": "electronics"},
}

# SMA windows for trend detection
_SMA_SHORT = 20
_SMA_LONG = 50


def _tech_momentum_signal(
    prices: list[float],
    volumes: list[float],
) -> dict[str, float | str]:
    """
    Compute momentum signals from a price/volume series.
    Returns: rsi, sma20, sma50, trend, volume_ratio, price_vs_sma20.
    Added by nightly agent 2026-06-11
    """
    if not prices:
        return {"rsi": 50.0, "sma20": 0.0, "sma50": 0.0, "trend": 0.0,
                "volume_ratio": 1.0, "price_vs_sma20": 0.0}
    current = prices[-1]
    sma20 = float(np.mean(prices[-_SMA_SHORT:])) if len(prices) >= _SMA_SHORT else float(np.mean(prices))
    sma50 = float(np.mean(prices[-_SMA_LONG:])) if len(prices) >= _SMA_LONG else sma20
    trend = (sma20 - sma50) / sma50 if sma50 else 0.0
    price_vs_sma20 = (current - sma20) / sma20 * 100 if sma20 else 0.0
    avg_vol = float(np.mean(volumes[:-1])) if len(volumes) > 1 else float(volumes[0]) if volumes else 1.0
    volume_ratio = volumes[-1] / avg_vol if avg_vol else 1.0
    return {
        "rsi": calculate_rsi(prices),
        "sma20": round(sma20, 4),
        "sma50": round(sma50, 4),
        "trend": round(trend, 4),
        "volume_ratio": round(volume_ratio, 4),
        "price_vs_sma20": round(price_vs_sma20, 2),
    }


async def tech_screener(top_n: int = 10) -> list[dict[str, Any]]:
    """
    Screen global technology stocks across Nasdaq, Nikkei, Nifty, Vietnam, and SET
    for momentum signals. Uses yfinance for price data (no DB dependency).

    Returns top_n opportunities ranked by composite_score (descending).
    Output format is compatible with scan_opportunities() for unified reporting.

    Added by nightly agent 2026-06-11
    """
    try:
        import yfinance as yf  # type: ignore
    except ImportError:
        logger.warning("yfinance not installed — tech_screener() unavailable. Run: pip install yfinance")
        return []

    results: list[dict[str, Any]] = []
    now = datetime.now(UTC).isoformat()

    for ticker, meta in _TECH_UNIVERSE.items():
        try:
            hist = yf.download(ticker, period="3mo", interval="1d", progress=False, auto_adjust=True)
            if hist is None or hist.empty:
                logger.warning("tech_screener: no data for %s", ticker)
                continue
            close = hist["Close"]
            # Fixed 2026-10-29: newer yfinance returns MultiIndex columns, so
            # hist["Close"] is a 1-column DataFrame (no .tolist()).
            if hasattr(close, "columns"):
                close = close.iloc[:, 0]
            prices = [float(p) for p in close.dropna().tolist()]
            vol = hist["Volume"]
            if hasattr(vol, "columns"):
                vol = vol.iloc[:, 0]
            volumes = [float(v) for v in vol.dropna().tolist()]
            if len(prices) < 5:
                continue
            signals = _tech_momentum_signal(prices, volumes)
            rsi = float(signals["rsi"])
            trend = float(signals["trend"])
            volume_ratio = float(signals["volume_ratio"])
            price_vs_sma20 = float(signals["price_vs_sma20"])
            # Composite score: no DB sentiment available for cross-market tickers,
            # so we use 0.0 sentiment (neutral) and rely on price/volume signals.
            score = composite_score(0.0, rsi, volume_ratio, trend)
            signal = (
                "strong_opportunity" if score > 70
                else "opportunity" if score > 50
                else "avoid" if score < 30
                else "neutral"
            )
            price_signal = "oversold" if rsi < 30 else "overbought" if rsi > 70 else "neutral"
            results.append({
                "ticker": ticker,
                "name": meta["name"],
                "market": meta["market"],
                "sector": meta["sector"],
                "opportunity_score": score,
                "signal": signal,
                "sentiment_signal": "neutral",    # cross-market: no sentiment DB
                "sentiment_trend": 0.0,
                "price_signal": price_signal,
                "volume_signal": "high_volume" if volume_ratio > 1.5 else "normal",
                "rsi": round(rsi, 2),
                "price_vs_sma20": f"{price_vs_sma20:+.2f}%",
                "trend_sma20_vs_50": f"{trend * 100:+.2f}%",
                "suggested_action": "accumulate" if score > 70 else "watch",
                "confidence": round(min(0.85, score / 100), 4),   # cap at 0.85 (no sentiment data)
                "scanned_at": now,
            })
        except Exception:
            logger.exception("tech_screener: scan failed for %s", ticker)

    ranked = sorted(results, key=lambda x: x["opportunity_score"], reverse=True)
    logger.info("tech_screener: scanned %d tickers, returning top %d", len(results), top_n)
    return ranked[:top_n]


async def check_exit_signals() -> list[dict[str, Any]]:
    pool = await db_pool.get_pool()
    holdings = await pool.fetch("SELECT ticker, avg_cost_price FROM holdings ORDER BY ticker")
    from holding_meta import load_attrs, locked_tickers
    locked = locked_tickers(await load_attrs(pool))  # ThaiESG: no exit/reduce signal before lock_until (2026-10-30)
    alerts: list[dict[str, Any]] = []
    for holding in holdings:
        ticker = holding["ticker"]
        if ticker in locked:
            continue
        try:
            sentiment, _ = await _sentiment_metrics(pool, ticker)
            metrics = await _price_metrics(pool, ticker)
            reasons = []
            action = None
            if metrics["rsi"] > 75 and sentiment < -0.2:
                action, reasons = "reduce", ["RSI above 75 with bearish sentiment"]
            avg_cost = float(holding["avg_cost_price"] or 0)
            loss_pct = ((metrics["current"] - avg_cost) / avg_cost * 100) if avg_cost else 0.0
            if loss_pct < -8:
                action, reasons = "stop_loss", [f"price is {loss_pct:.2f}% below average cost"]
            daily = await pool.fetch(
                """
                SELECT analyzed_at::date AS day, AVG(score) AS score
                FROM sentiment_scores
                WHERE ticker = $1 AND analyzed_at >= NOW() - INTERVAL '4 days'
                GROUP BY analyzed_at::date ORDER BY day DESC LIMIT 3
                """,
                ticker,
            )
            if len(daily) == 3 and all(float(row["score"] or 0) < -0.5 for row in daily):
                action, reasons = "sell", ["sentiment below -0.5 for three consecutive scored days"]
            if action:
                alerts.append(
                    {
                        "ticker": ticker,
                        "action": action,
                        "reasons": reasons,
                        "rsi": round(metrics["rsi"], 2),
                        "sentiment_score": round(sentiment, 4),
                        "price_change_from_cost_pct": round(loss_pct, 2),
                        "generated_at": datetime.now(UTC).isoformat(),
                    }
                )
        except Exception:
            logger.exception("Exit signal check failed for %s", ticker)
    return alerts
