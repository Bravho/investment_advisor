"""Free fundamentals/analyst data (yfinance) with a daily DB cache (Phase 4, 2026-10-30).

Every value is returned with its source and retrieval timestamp. yfinance data is
Yahoo's aggregation of exchange filings and broker estimates; treat analyst targets
as third-party opinion. No paid APIs.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
from datetime import date, datetime, timezone
from typing import Any, Optional

LOGGER = logging.getLogger("portfolio_engine.fundamentals")
INFO_KEYS = ["trailingPE", "forwardPE", "priceToBook", "dividendYield", "fiveYearAvgDividendYield", "payoutRatio",
             "returnOnEquity", "profitMargins", "debtToEquity", "targetMeanPrice", "targetHighPrice", "targetLowPrice",
             "targetMedianPrice", "numberOfAnalystOpinions", "recommendationMean", "averageVolume", "currentPrice",
             "trailingEps", "forwardEps", "earningsGrowth", "revenueGrowth", "beta", "sector", "industry",
             "currency", "longName", "fiftyTwoWeekHigh", "fiftyTwoWeekLow"]
DDL = """
CREATE TABLE IF NOT EXISTS fundamentals_cache (
    ticker     VARCHAR(30) PRIMARY KEY,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    data       JSONB NOT NULL
);
"""


def _clean(v: Any) -> Any:
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return v


def fetch_one(ticker: str) -> dict[str, Any]:
    import yfinance as yf

    tk = yf.Ticker(ticker)
    now = datetime.now(timezone.utc).isoformat()
    out: dict[str, Any] = {"ticker": ticker, "retrieved_at": now, "source": "Yahoo Finance via yfinance (free)"}
    try:
        info = tk.info or {}
        out["info"] = {k: _clean(info.get(k)) for k in INFO_KEYS}
    except Exception as exc:  # noqa: BLE001
        out["info"], out["info_error"] = {}, str(exc)[:200]
    try:
        eh = tk.earnings_history
        if eh is not None and not eh.empty:
            out["earnings_history"] = [
                {"quarter": str(idx)[:10], "eps_actual": _clean(r.get("epsActual")), "eps_estimate": _clean(r.get("epsEstimate")),
                 "surprise_pct": _clean(r.get("surprisePercent"))} for idx, r in eh.tail(4).iterrows()]
    except Exception as exc:  # noqa: BLE001
        out["earnings_history_error"] = str(exc)[:200]
    try:
        rv = tk.eps_revisions
        if rv is not None and not rv.empty:
            out["eps_revisions"] = {str(col): {str(i): _clean(v) for i, v in rv[col].items()} for col in rv.columns}
    except Exception as exc:  # noqa: BLE001
        out["eps_revisions_error"] = str(exc)[:200]
    try:
        cal = tk.calendar or {}
        out["calendar"] = {"earnings_dates": [str(d) for d in (cal.get("Earnings Date") or [])],
                           "ex_dividend_date": str(cal["Ex-Dividend Date"]) if cal.get("Ex-Dividend Date") else None}
    except Exception as exc:  # noqa: BLE001
        out["calendar_error"] = str(exc)[:200]
    return out


async def get_fundamentals(pool: Any, tickers: list[str], max_age_hours: float = 20) -> dict[str, dict[str, Any]]:
    async with pool.acquire() as conn:
        await conn.execute(DDL)
        rows = await conn.fetch("SELECT ticker, fetched_at, data FROM fundamentals_cache WHERE ticker = ANY($1::text[])", tickers)
    cached = {r["ticker"]: (r["fetched_at"], json.loads(r["data"]) if isinstance(r["data"], str) else r["data"]) for r in rows}
    out: dict[str, dict[str, Any]] = {}
    now = datetime.now(timezone.utc)
    for t in tickers:
        hit = cached.get(t)
        if hit and (now - hit[0]).total_seconds() < max_age_hours * 3600:
            out[t] = hit[1]
            continue
        try:
            data = await asyncio.to_thread(fetch_one, t)
            async with pool.acquire() as conn:
                await conn.execute(
                    """INSERT INTO fundamentals_cache (ticker, fetched_at, data) VALUES ($1, now(), $2::jsonb)
                       ON CONFLICT (ticker) DO UPDATE SET fetched_at = now(), data = EXCLUDED.data""",
                    t, json.dumps(data, default=str))
            out[t] = data
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("fundamentals %s failed: %s", t, exc)
            if hit:
                out[t] = {**hit[1], "stale_cache": True}
        await asyncio.sleep(0.3)  # be gentle with Yahoo
    return out
