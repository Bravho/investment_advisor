"""Signals module - pro layer #2 (Phase 4, 2026-10-30).

Per idea (investment_watchlist) and per holding:
  factor scores   value, quality, momentum, low_vol, dividend (safety)
  technical       trend (SMA50/200), relative strength vs benchmark (TDEX.BK for Thai, SPY for US),
                  RSI14, MACD histogram, volume confirmation
  flows           SET NVDR per-stock net (5 sessions, % of turnover) - Thai only; SET foreign net feeds the regime
  fundamentals    EPS revisions (30d up vs down) + last-4Q earnings surprise (Yahoo, free)
  sentiment       existing local-LLM news sentiment (sentiment_scores, 14d)
Each raw metric is turned into a cross-sectional percentile (0-100) across the universe;
the composite is a regime-adjusted weighted mean of available components.
Confidence = coverage (weight share with data) x agreement (1 - dispersion of components).
A guru-council bull/bear case for the top ideas uses local Ollama only.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from market_history import SET_PROXY, download_closes, download_ohlc, http_json
from fundamentals import get_fundamentals
from signal_score import (BASE_WEIGHTS, PRICE_METRIC_MAP, REGIME_TILT, composite_score, p33_components,
                          price_components, rsi_score as shared_rsi_score)

LOGGER = logging.getLogger("portfolio_engine.signals")
ICT = ZoneInfo("Asia/Bangkok")
COUNCIL_MODEL = "hermes3:8b"
# F3 shadow switch: the shared scorer is recorded on every run, but changing the
# score/rank used by the live API remains opt-in until its exact backtest passes.
UNIFIED_SCORE_LIVE = False
# 2026-11-01 (Tho t31u "ใช้สูตร P3.3 ไปก่อน"): live score = P3.3 price composite (signal_score.p33_components:
# momentum + low_vol + technical, no MACD / volume / regime tilt, percentiles within global or Thai group).
# Gate (ops/p33_gate.py, data/backtests/p33_gate_20261101_104145.json) vs the pre-P3.3 live formula: PASS global
# (Sharpe 0.903 -> 1.084, excess CAGR +8.3% -> +16.7%, hit 61.2% -> 67.1%) and PASS thai (Sharpe 0.196 -> 0.311;
# Thai remains display-only/"weak"). "legacy" restores the pre-P3.3 live score; it is always stored as a shadow.
LIVE_FORMULA = "p33"
HOLDING_PROXY = {"SCBGOLDE": "GC=F*THB=X"}
# 2026-11-01 (P3.3): only components with price history could be walk-forward tested (ops/p3_backtest.py,
# data/backtests/p3_20261101_0056.json, walkforward.simulate, same costs/weak thresholds):
#   price-only composite (momentum + low_vol + technical): global PASS (OOS Sharpe 1.05, excess CAGR +15.2%, hit 52.6%)
#                                                         thai   WEAK (Sharpe 0.31, excess +0.1%, hit 48.6% < 50%)
# value / quality / dividend / flows / fundamentals / sentiment have no point-in-time history -> weight 0 in the live
# score (display-only). The previous all-component composite is kept as `score_all` for display.
VALIDATED_COMPONENTS = {"momentum", "low_vol", "technical"}
VALIDATION = {"global": {"status": "pass", "detail": "P3.3 formula OOS Sharpe 1.08, excess CAGR +16.7%/yr vs SPY, positive months 67.1% (2019-10..2026-10, monthly top-3)"},
              "thai": {"status": "weak", "detail": "P3.3 formula OOS Sharpe 0.31, excess CAGR -0.2%/yr vs SET proxy, positive months 51.8% - display only (2019-10..2026-10)"}}


def validation_for(ticker: str) -> dict[str, str]:
    return VALIDATION["thai" if ticker.endswith(".BK") or ticker in HOLDING_PROXY else "global"]

DDL = """
CREATE TABLE IF NOT EXISTS signal_scores (
    id          SERIAL PRIMARY KEY,
    as_of       DATE NOT NULL,
    ticker      VARCHAR(30) NOT NULL,
    kind        VARCHAR(10) NOT NULL DEFAULT 'idea',
    score       NUMERIC(6,2),
    confidence  NUMERIC(5,3),
    rank        INTEGER,
    regime      VARCHAR(10),
    components  JSONB NOT NULL DEFAULT '{}'::jsonb,
    inputs      JSONB NOT NULL DEFAULT '{}'::jsonb,
    council     JSONB,
    price       NUMERIC(18,6),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (as_of, ticker)
);
CREATE TABLE IF NOT EXISTS market_regime (
    as_of      DATE PRIMARY KEY,
    regime     VARCHAR(10) NOT NULL,
    score      NUMERIC(6,3),
    inputs     JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def _f(v: Any) -> Optional[float]:
    try:
        x = float(v)
        return None if math.isnan(x) or math.isinf(x) else x
    except (TypeError, ValueError):
        return None


def rsi(close: pd.Series, n: int = 14) -> Optional[float]:
    d = close.diff().dropna()
    if len(d) < n + 1:
        return None
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up.iloc[-1] / dn.iloc[-1] if dn.iloc[-1] > 0 else np.inf
    return float(100 - 100 / (1 + rs))


def macd_hist(close: pd.Series) -> Optional[float]:
    if len(close) < 40:
        return None
    m = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
    h = m - m.ewm(span=9, adjust=False).mean()
    return float(h.iloc[-1] / close.iloc[-1] * 100)  # % of price, comparable across tickers


# ------------------------------------------------------------------ regime
REGIME_TICKERS = [SET_PROXY, "SPY", "^VIX", "^TNX", "THB=X", "GC=F", "BZ=F"]


def regime_points(px: pd.DataFrame) -> tuple[dict[str, Any], list[int]]:
    """2026-11-01 (P3.1): point-in-time price part of the regime rule. `px` = closes up to the as-of date.
    Shared by the live regime (compute_regime) and the prediction backtest/learning, so both use ONE definition."""
    inputs, pts = {}, []

    def last(t: str) -> Optional[pd.Series]:
        return px[t].dropna() if t in px.columns and px[t].dropna().size > 30 else None

    for t, label in ((SET_PROXY, "SET (TDEX proxy)"), ("SPY", "S&P 500")):
        s = last(t)
        if s is not None and len(s) >= 200:
            above = s.iloc[-1] > s.iloc[-200:].mean()
            inputs[f"{t}_above_sma200"] = bool(above)
            pts.append(1 if above else -1)
    v = last("^VIX")
    if v is not None:
        inputs["vix"] = round(float(v.iloc[-1]), 2)
        pts.append(1 if v.iloc[-1] < 18 else -1 if v.iloc[-1] > 25 else 0)
    for t, key, up_is_bad, thr in (("^TNX", "us10y_1m_chg_bp", True, 0.25), ("THB=X", "usdthb_1m_pct", True, 2.0),
                                   ("GC=F", "gold_1m_pct", True, 6.0), ("BZ=F", "brent_1m_pct", True, 12.0)):
        s = last(t)
        if s is None or len(s) < 22:
            continue
        if t == "^TNX":
            chg = float(s.iloc[-1] - s.iloc[-22])
            inputs[key] = round(chg * 100, 1)
        else:
            chg = float(s.iloc[-1] / s.iloc[-22] - 1) * 100
            inputs[key] = round(chg, 2)
        pts.append(-1 if chg > thr else (1 if chg < -thr and t in ("^TNX", "THB=X") else 0))
    return inputs, pts


def regime_label(score: float) -> str:
    return "risk_on" if score >= 0.25 else "risk_off" if score <= -0.25 else "neutral"


def regime_from_closes(px: pd.DataFrame) -> dict[str, Any]:
    """Point-in-time regime from prices only (no SET foreign flow - no free history)."""
    inputs, pts = regime_points(px)
    score = float(np.mean(pts)) if pts else 0.0
    return {"regime": regime_label(score), "score": round(score, 3), "n_inputs": len(pts), "inputs": inputs}


def compute_regime() -> dict[str, Any]:
    px = download_closes(REGIME_TICKERS, None, "1y", 1800)
    inputs, pts = regime_points(px)
    try:
        from watchlists import _set_foreign_flow  # reuse the free SET investor-type fetch
        ff = _set_foreign_flow()
        inputs["set_foreign_net_bn"] = ff["reading"]
        inputs["set_foreign_as_of"] = str(ff["as_of"])[:10]
        pts.append(1 if ff["reading"] > 1 else -1 if ff["reading"] < -1 else 0)
    except Exception as exc:  # noqa: BLE001
        inputs["set_foreign_error"] = str(exc)[:120]
    score = float(np.mean(pts)) if pts else 0.0
    regime = regime_label(score)
    return {"regime": regime, "score": round(score, 3), "inputs": inputs, "n_inputs": len(pts),
            "source": "yfinance (TDEX, SPY, VIX, ^TNX, THB=X, GC=F, BZ=F) + SET investor-type; rule-based",
            "as_of": str(px.index[-1].date())}


# ------------------------------------------------------------------ flows (NVDR)
def nvdr_flows(symbols: list[str], sessions: int = 5) -> dict[str, Any]:
    import http.cookiejar
    import urllib.request as ur
    if not symbols:
        return {}
    jar = http.cookiejar.CookieJar()
    opener = ur.build_opener(ur.HTTPCookieProcessor(jar))
    page = "https://www.set.or.th/en/market/statistics/nvdr/trading-by-stock"
    opener.open(ur.Request(page, headers={"User-Agent": "Mozilla/5.0"}), timeout=20).read()
    agg: dict[str, dict[str, float]] = {s: {"net": 0.0, "under": 0.0, "days": 0} for s in symbols}
    got, d, dates = 0, datetime.now(ICT).date(), []
    for _ in range(14):
        if got >= sessions:
            break
        d -= timedelta(days=1)
        if d.weekday() >= 5:
            continue
        url = ("https://www.set.or.th/api/set/nvdr-trade/stock-trading?sortBy=symbol&date="
               f"{d:%d/%m/%Y}&symbols={','.join(symbols)}")
        try:
            rows = (http_json(url, timeout=20, attempts=2, headers={"Referer": page}, opener=opener) or {}).get("nvdrTradings") or []
        except Exception:  # noqa: BLE001
            rows = []
        if not rows:
            continue
        got += 1
        dates.append(d.isoformat())
        for r in rows:
            a = agg.get(r["symbol"])
            if a is not None:
                a["net"] += float(r.get("netValue") or 0)
                a["under"] += float(r.get("underlyingValue") or 0)
                a["days"] += 1
    return {s: {"net_thb_m": round(a["net"] / 1e6, 1), "net_pct_turnover": round(a["net"] / a["under"] * 100, 2) if a["under"] else None,
                "sessions": a["days"], "dates": dates, "source": "SET NVDR trading by stock (free)", "source_url": page}
            for s, a in agg.items()}


# ------------------------------------------------------------------ raw metrics
def _price_metrics(close: pd.Series, vol: Optional[pd.Series], bench: Optional[pd.Series]) -> dict[str, Any]:
    """Compatibility wrapper around the shared point-in-time implementation."""
    c = close.dropna()
    return price_components(close, vol, bench, c.index[-1]) if not c.empty else {}


def _fund_metrics(f: dict[str, Any]) -> dict[str, Any]:
    info = f.get("info") or {}
    m: dict[str, Any] = {}
    fpe, tpe, pb = _f(info.get("forwardPE")), _f(info.get("trailingPE")), _f(info.get("priceToBook"))
    pe = fpe if fpe and fpe > 0 else (tpe if tpe and tpe > 0 else None)
    m["earnings_yield"] = 1 / pe if pe else None
    m["book_yield"] = 1 / pb if pb and pb > 0 else None
    dy, dy5 = _f(info.get("dividendYield")), _f(info.get("fiveYearAvgDividendYield"))
    m["div_yield"] = dy
    m["yield_vs_5y"] = (dy / dy5 - 1) if dy is not None and dy5 else None
    m["roe"] = _f(info.get("returnOnEquity"))
    m["margin"] = _f(info.get("profitMargins"))
    de = _f(info.get("debtToEquity"))
    m["neg_leverage"] = -de if de is not None and info.get("sector") != "Financial Services" else None
    pr = _f(info.get("payoutRatio"))
    m["payout"] = pr
    if dy is not None and dy > 0:
        safety = 1.0
        if pr is not None:
            safety -= max(0.0, pr - 0.6) * 1.5  # payout above 60% erodes safety
        eg = _f(info.get("earningsGrowth"))
        if eg is not None and eg < -0.1:
            safety -= 0.3
        m["div_safety"] = safety * min(dy, 8) / 8 + (0.2 * safety)
    revs = f.get("eps_revisions") or {}
    up = sum((_f((revs.get("upLast30days") or {}).get(p)) or 0) for p in ("0y", "+1y"))
    dn = sum((_f((revs.get("downLast30days") or {}).get(p)) or 0) for p in ("0y", "+1y"))
    if revs and (up + dn) > 0:
        m["revision_breadth"] = (up - dn) / (up + dn)
    elif revs:
        m["revision_breadth"] = 0.0
    eh = [e for e in (f.get("earnings_history") or []) if _f(e.get("surprise_pct")) is not None]
    if eh:
        m["avg_surprise"] = float(np.mean([_f(e["surprise_pct"]) for e in eh]))
        m["beat_rate"] = sum(1 for e in eh if _f(e["surprise_pct"]) > 0) / len(eh)
    m["analyst_upside"] = (_f(info.get("targetMeanPrice")) / _f(info.get("currentPrice")) - 1) \
        if _f(info.get("targetMeanPrice")) and _f(info.get("currentPrice")) and (_f(info.get("numberOfAnalystOpinions")) or 0) >= 3 else None
    return m


# metric -> (component, higher_is_better)
METRIC_MAP = {
    "earnings_yield": ("value", True), "book_yield": ("value", True), "yield_vs_5y": ("value", True),
    "roe": ("quality", True), "margin": ("quality", True), "neg_leverage": ("quality", True),
    "div_safety": ("dividend", True),
    **PRICE_METRIC_MAP,
    "nvdr_net_pct": ("flows", True),
    "revision_breadth": ("fundamentals", True), "avg_surprise": ("fundamentals", True), "analyst_upside": ("fundamentals", True),
    "sentiment": ("sentiment", True),
}


def _rsi_score(r: Optional[float]) -> Optional[float]:
    return shared_rsi_score(r)


def _legacy_live_score(components: dict[str, Optional[float]], weights: dict[str, float]) -> Optional[float]:
    """Frozen pre-F3 arithmetic used while ``UNIFIED_SCORE_LIVE`` is false."""
    available = {k: v for k, v in components.items() if v is not None and k in VALIDATED_COMPONENTS}
    weight_sum = sum(weights[k] for k in available)
    return sum(weights[k] * v for k, v in available.items()) / weight_sum if weight_sum else None


def _live_composite_score(components: dict[str, Optional[float]], regime: Optional[str],
                          weights: dict[str, float]) -> Optional[float]:
    """Select the frozen live calculation or the opt-in shared calculation."""
    if UNIFIED_SCORE_LIVE:
        return composite_score(components, regime, VALIDATED_COMPONENTS)
    return _legacy_live_score(components, weights)


async def _sentiment(pool: Any, tickers: list[str]) -> dict[str, dict[str, Any]]:
    keys = {t: [t, t.replace(".BK", "")] for t in tickers}
    flat = sorted({k for v in keys.values() for k in v})
    async with pool.acquire() as conn:
        rows = await conn.fetch("""SELECT ticker, avg(score)::float AS s, count(*) AS n, max(analyzed_at) AS last
                                   FROM sentiment_scores WHERE analyzed_at > now() - interval '14 days' AND ticker = ANY($1::text[])
                                   GROUP BY ticker""", flat)
    by = {r["ticker"]: r for r in rows}
    out = {}
    for t, ks in keys.items():
        rs = [by[k] for k in ks if k in by]
        n = sum(r["n"] for r in rs)
        if n >= 3:
            s = sum(r["s"] * r["n"] for r in rs) / n
            out[t] = {"score": round(s, 3), "n": n, "last": max(r["last"] for r in rs).isoformat(),
                      "source": "local Ollama news sentiment (sentiment_scores, 14d)"}
    return out


async def _universe(pool: Any) -> list[dict[str, Any]]:
    async with pool.acquire() as conn:
        ideas = [dict(r) for r in await conn.fetch("SELECT ticker, name, sector, currency FROM investment_watchlist WHERE status <> 'dropped' AND COALESCE(sector, '') NOT IN ('us_bond', 'us_income', 'thai_dividend')")]
    import risk_engine as re_mod
    # Locked tax-wrapper funds (ThaiESG, lock_until in the future) get no buy/sell signal: nothing may be sold or
    # switched before the lock ends, and they have no free daily NAV history (2026-10-30).
    held = [p for p in await re_mod._positions(pool) if not p.get("locked")]
    uni = [{**i, "kind": "idea"} for i in ideas]
    have = {i["ticker"] for i in uni}
    for p in held:
        if p["ticker"] not in have:
            uni.append({"ticker": p["ticker"], "name": p.get("name"), "sector": None,
                        "currency": "THB", "kind": "holding"})
        else:
            next(u for u in uni if u["ticker"] == p["ticker"])["kind"] = "holding"
    return uni


def _price_series(t: str, ohlc: dict[str, pd.DataFrame], closes: pd.DataFrame) -> tuple[Optional[pd.Series], Optional[pd.Series], str]:
    if t in HOLDING_PROXY:
        if "GC=F" in closes and "THB=X" in closes:
            s = (closes["GC=F"] * closes["THB=X"]).dropna()
            return s, None, "proxy GC=F x THB=X (fund NAV history not free)"
        return None, None, "no proxy"
    df = ohlc.get(t)
    if df is None:
        return None, None, "no data"
    return df["Close"], df["Volume"], "yfinance daily OHLC"


async def run_signals(pool: Any, council: bool = True) -> dict[str, Any]:
    async with pool.acquire() as conn:
        await conn.execute(DDL)
    uni = await _universe(pool)
    tickers = [u["ticker"] for u in uni]
    yf_t = [t for t in tickers if t not in HOLDING_PROXY]
    ohlc = await asyncio.to_thread(download_ohlc, yf_t, "2y")
    closes = await asyncio.to_thread(download_closes, [SET_PROXY, "SPY", "GC=F", "THB=X"], None, "2y", 1800)
    funds = await get_fundamentals(pool, yf_t)
    regime = await asyncio.to_thread(compute_regime)
    thai = [t.replace(".BK", "") for t in tickers if t.endswith(".BK")]
    try:
        nvdr = await asyncio.to_thread(nvdr_flows, thai)
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("NVDR fetch failed: %s", exc)
        nvdr = {}
    sent = await _sentiment(pool, tickers)
    raw: dict[str, dict[str, Any]] = {}
    srcs: dict[str, dict[str, Any]] = {}
    for u in uni:
        t = u["ticker"]
        c, v, src = _price_series(t, ohlc, closes)
        bench = closes.get(SET_PROXY) if (t.endswith(".BK") or t in HOLDING_PROXY) else closes.get("SPY")
        m: dict[str, Any] = {}
        if c is not None and c.dropna().size > 60:
            m.update(price_components(c, v, bench, c.dropna().index[-1]))
        m.update(_fund_metrics(funds.get(t) or {}))
        sym = t.replace(".BK", "")
        if sym in nvdr and nvdr[sym]["sessions"]:
            m["nvdr_net_pct"] = nvdr[sym]["net_pct_turnover"]
        if t in sent:
            m["sentiment"] = sent[t]["score"]
        raw[t] = m
        srcs[t] = {"price": {"source": src, "as_of": m.get("as_of")},
                   "fundamentals": {"source": "Yahoo Finance via yfinance (free)", "as_of": str((funds.get(t) or {}).get("retrieved_at", ""))[:10] or None},
                   "benchmark": SET_PROXY if (t.endswith(".BK") or t in HOLDING_PROXY) else "SPY",
                   "nvdr": nvdr.get(sym), "sentiment": sent.get(t)}
    # 2026-11-01: P3.3 live score - percentiles within each validated group (global vs SPY, Thai vs SET proxy)
    p33: dict[str, dict[str, Optional[float]]] = {}
    for group, bench_t in (("thai", SET_PROXY), ("global", "SPY")):
        members = [u["ticker"] for u in uni if (validation_for(u["ticker"]) is VALIDATION[group])]
        series = {}
        for t in members:
            c, _v, _src = _price_series(t, ohlc, closes)
            if c is not None and c.dropna().size > 0:
                series[t] = c
        if not series or bench_t not in closes:
            continue
        frame = pd.concat(series, axis=1)
        frame.index = pd.to_datetime(frame.index).tz_localize(None) if getattr(frame.index, "tz", None) is not None else pd.to_datetime(frame.index)
        b = closes[bench_t].copy()
        b.index = pd.to_datetime(b.index).tz_localize(None) if getattr(b.index, "tz", None) is not None else pd.to_datetime(b.index)
        frame = frame.join(b.rename("__bench__"), how="outer").sort_index().ffill(limit=5)
        frame = frame[frame["__bench__"].notna()]
        comp = p33_components(frame, "__bench__")
        for t in members:
            if not comp.empty and t in comp.index:
                row = comp.loc[t]
                p33[t] = {k: (round(float(row[k]), 2) if pd.notna(row[k]) else None) for k in ("momentum", "low_vol", "technical", "score")}
    # cross-sectional percentiles
    metric_pct: dict[str, dict[str, float]] = {t: {} for t in tickers}
    for metric, (comp, hib) in METRIC_MAP.items():
        vals = {t: raw[t].get(metric) for t in tickers if _f(raw[t].get(metric)) is not None}
        if len(vals) < 3:
            continue
        s = pd.Series(vals, dtype=float)
        pct = s.rank(pct=True, ascending=hib) * 100
        for t, p in pct.items():
            metric_pct[t][metric] = float(p)
    weights = dict(BASE_WEIGHTS)
    for k, dv in REGIME_TILT[regime["regime"]].items():
        weights[k] = max(0.0, weights[k] + dv)
    tot = sum(weights.values())
    weights = {k: v / tot for k, v in weights.items()}
    results = []
    for u in uni:
        t = u["ticker"]
        comps: dict[str, Optional[float]] = {}
        for comp in BASE_WEIGHTS:
            ps = [metric_pct[t][m] for m, (c, _) in METRIC_MAP.items() if c == comp and m in metric_pct[t]]
            comps[comp] = round(float(np.mean(ps)), 1) if ps else None
        avail_all = {k: v for k, v in comps.items() if v is not None}
        wsum_all = sum(weights[k] for k in avail_all)
        score_all = sum(weights[k] * v for k, v in avail_all.items()) / wsum_all if wsum_all else None
        avail = {k: v for k, v in avail_all.items() if k in VALIDATED_COMPONENTS}  # P3.3: untested parts display-only
        wsum = sum(weights[k] for k in avail)
        score_unified = composite_score(comps, regime["regime"], VALIDATED_COMPONENTS)
        score_legacy = _live_composite_score(comps, regime["regime"], weights)
        p33_t = p33.get(t) or {}
        if LIVE_FORMULA == "p33":
            score = p33_t.get("score")
            raw[t]["score_formula"] = "p33" if score is not None else "p33: not scored (needs 230 closes in the last 252 days)"
            if p33_t.get("score") is not None:
                avail = {k: p33_t[k] for k in ("momentum", "low_vol", "technical") if p33_t.get(k) is not None}
                wsum = sum(weights[k] for k in avail)
        else:
            score = score_legacy
            raw[t]["score_formula"] = "legacy"
        raw[t]["score_legacy_shadow"] = round(score_legacy, 2) if score_legacy is not None else None
        raw[t]["score_p33"] = p33_t.get("score")
        raw[t]["p33_components"] = {k: p33_t.get(k) for k in ("momentum", "low_vol", "technical")} if p33_t else None
        coverage = wsum / (sum(weights[k] for k in VALIDATED_COMPONENTS) or 1)
        agreement = 1 - min(1.0, float(np.std(list(avail.values()))) / 35) if len(avail) >= 2 else 0.3
        conf = round(coverage * (0.5 + 0.5 * agreement), 3)
        raw[t]["score_all_components"] = round(score_all, 2) if score_all is not None else None
        raw[t]["score_unified_shadow"] = round(score_unified, 2) if score_unified is not None else None
        raw[t]["validation"] = validation_for(t)
        results.append({"ticker": t, "kind": u["kind"], "name": u.get("name"), "score": round(score, 2) if score is not None else None,
                        "confidence": conf, "components": comps,
                        "raw": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in raw[t].items()},
                        "sources": srcs[t], "price": raw[t].get("price")})
    ranked = sorted([r for r in results if r["score"] is not None], key=lambda r: -r["score"])
    for i, r in enumerate(ranked, 1):
        r["rank"] = i
    as_of = datetime.now(ICT).date()
    if council:
        top = [r for r in ranked if r["kind"] == "idea"][:5]
        for r in top:
            r["council"] = await guru_council(r, regime)
    async with pool.acquire() as conn:
        await conn.execute("""INSERT INTO market_regime (as_of, regime, score, inputs) VALUES ($1,$2,$3,$4::jsonb)
                              ON CONFLICT (as_of) DO UPDATE SET regime=EXCLUDED.regime, score=EXCLUDED.score, inputs=EXCLUDED.inputs, created_at=now()""",
                           as_of, regime["regime"], regime["score"], json.dumps(regime, default=str))
        for r in results:
            await conn.execute(
                """INSERT INTO signal_scores (as_of, ticker, kind, score, confidence, rank, regime, components, inputs, council, price)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9::jsonb,$10::jsonb,$11)
                   ON CONFLICT (as_of, ticker) DO UPDATE SET kind=EXCLUDED.kind, score=EXCLUDED.score, confidence=EXCLUDED.confidence,
                     rank=EXCLUDED.rank, regime=EXCLUDED.regime, components=EXCLUDED.components, inputs=EXCLUDED.inputs,
                     council=COALESCE(EXCLUDED.council, signal_scores.council), price=EXCLUDED.price, created_at=now()""",
                as_of, r["ticker"], r["kind"], r["score"], r["confidence"], r.get("rank"), regime["regime"],
                json.dumps(r["components"]), json.dumps({"raw": r["raw"], "sources": r["sources"], "weights": weights}, default=str),
                json.dumps(r["council"]) if r.get("council") else None, r.get("price"))
    return {"as_of": as_of.isoformat(), "regime": regime, "weights": weights, "count": len(results),
            "top": [{"ticker": r["ticker"], "score": r["score"], "confidence": r["confidence"]} for r in ranked[:5]]}


def _readable_facts(m: dict[str, Any]) -> list[str]:
    def pct(k: str, label: str, mult: float = 100) -> Optional[str]:
        v = _f(m.get(k))
        return f"{label}: {v * mult:+.1f}%" if v is not None else None
    out = [
        f"price {m.get('price'):.4g} (as of {m.get('as_of')})" if _f(m.get("price")) else None,
        pct("mom_12_1", "12-month return excl. last month"), pct("mom_6m", "6-month return"),
        pct("rs_3m", "3-month return relative to benchmark"), pct("vol_1y", "annualised volatility"),
        f"beta to benchmark {m['beta']:.2f}" if _f(m.get("beta")) is not None else None,
        f"RSI(14) {m['rsi14']:.0f}" if _f(m.get("rsi14")) is not None else None,
        f"trend score {m['trend']} of +3 (price/SMA50/SMA200 alignment)" if m.get("trend") is not None else None,
        f"P/E {1 / m['earnings_yield']:.1f}" if _f(m.get("earnings_yield")) else None,
        f"P/B {1 / m['book_yield']:.2f}" if _f(m.get("book_yield")) else None,
        f"dividend yield {m['div_yield']:.2f}%" if _f(m.get("div_yield")) is not None else None,
        pct("yield_vs_5y", "dividend yield vs own 5-year average"), pct("payout", "payout ratio"),
        pct("roe", "return on equity"), pct("margin", "net profit margin"),
        f"EPS revision breadth (30d) {m['revision_breadth']:+.2f} (-1 all down, +1 all up)" if _f(m.get("revision_breadth")) is not None else None,
        pct("avg_surprise", "average earnings surprise, last 4 quarters"),
        pct("analyst_upside", "analyst mean target vs price"),
        f"NVDR (foreign proxy) net buying {m['nvdr_net_pct']:+.2f}% of turnover, last 5 sessions" if _f(m.get("nvdr_net_pct")) is not None else None,
        f"news sentiment {m['sentiment']:+.2f} (-1..+1)" if _f(m.get("sentiment")) is not None else None,
    ]
    return [x for x in out if x]


async def guru_council(r: dict[str, Any], regime: dict[str, Any]) -> dict[str, Any]:
    from utils.common import ollama_chat_stream, parse_json_response
    facts = {"ticker": r["ticker"], "name": r.get("name"), "macro_regime": regime["regime"],
             "rank_percentiles_vs_28_peers (100=best, 50=middle)": {k: v for k, v in r["components"].items() if v is not None},
             "facts": _readable_facts(r["raw"]), "macro_facts": regime["inputs"]}
    prompt = (
        "You are a council of three investors: a value investor (Buffett/Graham style), a macro investor (Dalio style) and a "
        "momentum/technical trader (Druckenmiller style). Using ONLY the facts below (do not invent numbers, news or events), "
        "give the strongest bull case and the strongest bear case for this idea for a Thai-baht investor. "
        "Percentiles rank this idea against 28 peers (100 = best); they are NOT returns or yields. Quote facts exactly as given. "
        'Reply as JSON: {"bull_case": [3 short bullets], "bear_case": [3 short bullets], '
        '"value_view": "1 sentence", "macro_view": "1 sentence", "momentum_view": "1 sentence", '
        '"verdict": "bullish|neutral|bearish", "key_risk": "1 sentence"}.\n\nFACTS:\n' + json.dumps(facts, default=str))
    try:
        txt = await ollama_chat_stream(COUNCIL_MODEL, prompt, json_mode=True, num_ctx=4096, num_predict=600, total_timeout=240)
        out = parse_json_response(txt) or {}
        if not isinstance(out, dict) or not out.get("bull_case"):
            raise ValueError("empty council JSON")
        out["model"] = f"ollama:{COUNCIL_MODEL} (local)"
        out["generated_at"] = datetime.now(timezone.utc).isoformat()
        return out
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("council for %s failed: %s", r["ticker"], exc)
        return {"error": str(exc)[:200], "model": f"ollama:{COUNCIL_MODEL} (local)"}


def _row(r: Any) -> dict[str, Any]:
    d = dict(r)
    for k, v in list(d.items()):
        if isinstance(v, str) and k in ("components", "inputs", "council"):
            try:
                d[k] = json.loads(v)
            except Exception:  # noqa: BLE001
                pass
        elif hasattr(v, "isoformat"):
            d[k] = v.isoformat()
        elif v.__class__.__name__ == "Decimal":
            d[k] = float(v)
    return d


async def latest_signals(pool: Any) -> dict[str, Any]:
    async with pool.acquire() as conn:
        await conn.execute(DDL)
        rows = await conn.fetch("SELECT * FROM signal_scores WHERE as_of = (SELECT max(as_of) FROM signal_scores) ORDER BY rank NULLS LAST")
        reg = await conn.fetchrow("SELECT * FROM market_regime ORDER BY as_of DESC LIMIT 1")
    return {"as_of": rows[0]["as_of"].isoformat() if rows else None, "regime": _row(reg) if reg else None,
            "items": [_row(r) for r in rows],
            "method": "Live score = P3.3 price composite (momentum 12-1/6m, low vol/beta, price vs 200d, 3m excess return, RSI band; weights .15/.10/.15; percentiles within global or Thai group; no MACD/volume/regime tilt) since 2026-11-01; pre-P3.3 score kept as raw.score_legacy_shadow; confidence = coverage x agreement. "
                      "Free data: yfinance, SET NVDR/investor-type, local sentiment. Not financial advice."}


def render_brief_section(sig: dict[str, Any], plans: list[dict[str, Any]], weak: Optional[list[str]] = None,
                         paper: Optional[dict[str, Any]] = None, approved: Optional[list[dict[str, Any]]] = None) -> str:
    if not sig or not sig.get("items"):
        return "**Signals**\n- No signal run yet."
    reg = sig.get("regime") or {}
    ri = (reg.get("inputs") or {}).get("inputs") or {}
    lines = [f"**Signals (as of {sig['as_of']}) - macro regime: {str(reg.get('regime', '?')).upper()} (score {reg.get('score')})**"]
    if ri:
        lines.append("- Regime inputs: " + ", ".join(f"{k}={v}" for k, v in list(ri.items())[:8]))
    pmap = {p["ticker"]: p for p in plans}
    ideas = [i for i in sig["items"] if i["kind"] == "idea" and i.get("score") is not None][:5]
    for i in ideas:
        p = pmap.get(i["ticker"])
        plan_txt = (f"proposed plan: entry {p['entry_low']:.4g}-{p['entry_high']:.4g}, stop {p['stop']:.4g}, target {p['target']:.4g}, "
                    f"R:R {p['rr']:.1f}{'' if p['viable'] else ' (NOT viable)'}") if p and p.get("entry_low") else "no viable plan"
        c = i.get("council") or {}
        verdict = f"; council: {c.get('verdict')}" if c.get("verdict") else ""
        lines.append(f"- #{i['rank']} {i['ticker']} score {i['score']:.0f} (conf {i['confidence']:.2f}) - {plan_txt}{verdict}")
    held = [i for i in sig["items"] if i["kind"] == "holding"]
    if held:
        lines.append("- Holdings: " + "; ".join(f"{h['ticker']} score {h['score']:.0f} (rank {h.get('rank')}, conf {h['confidence']:.2f})"
                                              for h in held if h.get("score") is not None))
    if weak:
        lines.append("- Weak signals (backtest/outcomes): " + ", ".join(weak))
    if paper:
        cnt = paper.get("counts") or {}
        lines.append(f"- Paper ledger: {cnt.get('waiting', 0)} waiting, {cnt.get('open', 0)} open, {cnt.get('closed', 0)} closed"
                     + (f", hit rate {paper['hit_rate']:.0%}, avg {paper['avg_r']:+.2f}R" if paper.get("hit_rate") is not None else ""))
    lines.append("- All plans are PROPOSED (engine) - they need Tho's approval before they drive alerts.")
    if approved:
        lines.append("- Approved plans (drive watch-list alerts; no order is ever placed): " + "; ".join(
            f"#{p['id']} {p['ticker']} entry {p['entry_low']:.4g}-{p['entry_high']:.4g} stop {p['stop']:.4g} target {p['target']:.4g}"
            + (f" [อนุมัติแบบ override: {p.get('override_reason')}]" if p.get("approved_by_override") else "")
            for p in approved if p.get("entry_low") is not None))
    return "\n".join(lines)


async def brief_section(pool: Any) -> str:
    """Signals + proposed plans (+ weak signals / paper ledger when available) for the morning brief."""
    import trade_plans as tp
    sig = await latest_signals(pool)
    plans = await tp.list_plans(pool, "proposed")
    weak, paper = None, None
    try:
        import walkforward as wf
        weak = await wf.weak_signal_names(pool)
    except Exception:  # noqa: BLE001
        pass
    try:
        paper = await tp.paper_summary(pool)
    except Exception:  # noqa: BLE001
        pass
    try:
        approved = await tp.list_plans(pool, "approved")
    except Exception:  # noqa: BLE001
        approved = None
    return render_brief_section(sig, plans, weak, paper, approved)
