"""Walk-forward backtest + outcome scoring - pro layer #3 (Phase 4, 2026-10-30).

Harness rules (no look-ahead):
  * signals use closes up to and including the month-end signal date t;
  * trades execute at the close of the NEXT trading day (t+1) and earn returns from t+2;
  * parameters are chosen on the trailing 24-month TRAIN window only, then applied to the
    following 6-month OUT-OF-SAMPLE window; only OOS returns are reported.
Costs: Thai shares = 0.157% commission + 7% VAT + 0.10% slippage per side;
offshore = 0.15% commission + 0.25% FX spread + 0.10% slippage per side (assumptions, editable);
fund/ETF expense ratios accrue daily on held weight (approximate published TERs).
Signals tested are price-only (point-in-time fundamentals are not free, so value/quality/
revisions cannot be backtested honestly and are scored live instead).
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Optional
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from market_history import SET_PROXY, download_closes
from trade_plans import COMMISSION_TH, VAT, SLIPPAGE, US_COMMISSION, FX_SPREAD

LOGGER = logging.getLogger("portfolio_engine.walkforward")
ICT = ZoneInfo("Asia/Bangkok")
TOP_K = 3
TRAIN_M, STEP_M = 24, 6
WEAK = {"sharpe": 0.3, "excess": 0.0, "hit": 0.5}
# Approximate published expense ratios (annual). Verify before relying on them.
TER = {"TDEX.BK": 0.0050, "SPY": 0.000945, "QQQ": 0.0020, "EWJ": 0.0050, "INDA": 0.0061, "FXI": 0.0074,
       "VNM": 0.0066, "GLDM": 0.0010, "IAU": 0.0025, "GDX": 0.0051}
UNIVERSES = {
    "thai": {"benchmark": SET_PROXY,
             "tickers": ["KBANK.BK", "BBL.BK", "KTB.BK", "TTB.BK", "SCB.BK", "PTT.BK", "PTTEP.BK", "TOP.BK", "IRPC.BK",
                         "AOT.BK", "BAFS.BK", "ADVANC.BK"]},
    "global": {"benchmark": "SPY",
               "tickers": ["SPY", "QQQ", "NVDA", "MSFT", "GOOGL", "TSM", "AVGO", "MU", "VNM", "EWJ", "INDA", "FXI",
                           "GLDM", "IAU", "GDX"]},
}
DDL = """
CREATE TABLE IF NOT EXISTS backtest_runs (
    id        SERIAL PRIMARY KEY,
    run_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    universe  VARCHAR(20) NOT NULL,
    config    JSONB NOT NULL DEFAULT '{}'::jsonb,
    results   JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS signal_performance (
    id         SERIAL PRIMARY KEY,
    as_of      DATE NOT NULL,
    signal     VARCHAR(40) NOT NULL,
    source     VARCHAR(20) NOT NULL,
    universe   VARCHAR(20) NOT NULL DEFAULT 'all',
    n          INTEGER,
    hit_rate   NUMERIC(6,4),
    avg_win    NUMERIC(10,5),
    avg_loss   NUMERIC(10,5),
    sharpe     NUMERIC(8,3),
    excess     NUMERIC(10,5),
    weak       BOOLEAN,
    sufficient BOOLEAN,
    detail     JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (as_of, signal, source, universe)
);
"""


def side_cost(t: str) -> float:
    return COMMISSION_TH * (1 + VAT) + SLIPPAGE if t.endswith(".BK") else US_COMMISSION + FX_SPREAD + SLIPPAGE


def _rsi_frame(px: pd.DataFrame, n: int = 14) -> pd.DataFrame:
    d = px.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


# Each strategy: (param grid, fn(px_until_t, param) -> target weights Series)
def _top(score: pd.Series, k: int = TOP_K) -> pd.Series:
    s = score.dropna()
    if s.empty:
        return pd.Series(dtype=float)
    pick = s.sort_values(ascending=False).iloc[:k].index
    return pd.Series(1.0 / k, index=pick)  # unfilled slots stay in cash


def s_momentum(h: pd.DataFrame, L: int) -> pd.Series:
    if len(h) <= L:
        return pd.Series(dtype=float)
    sc = h.iloc[-22] / h.iloc[-L] - 1
    return _top(sc[sc > 0])


def s_trend(h: pd.DataFrame, n: int) -> pd.Series:
    if len(h) <= n:
        return pd.Series(dtype=float)
    dist = h.iloc[-1] / h.iloc[-n:].mean() - 1
    return _top(dist[dist > 0])


def s_lowvol(h: pd.DataFrame, w: int) -> pd.Series:
    if len(h) <= w:
        return pd.Series(dtype=float)
    vol = h.iloc[-w:].pct_change(fill_method=None).std()
    vol = vol[h.iloc[-w:].notna().sum() >= w * 0.9]
    return _top(-vol)


def s_rsi_rev(h: pd.DataFrame, th: int) -> pd.Series:
    if len(h) <= 200:
        return pd.Series(dtype=float)
    r = _rsi_frame(h.iloc[-120:]).iloc[-1]
    up = h.iloc[-1] > h.iloc[-200:].mean()
    cand = r[(r < th) & up]
    return _top(-cand)


def s_combined(h: pd.DataFrame, L: int) -> pd.Series:
    if len(h) <= max(L, 200):
        return pd.Series(dtype=float)
    mom = h.iloc[-22] / h.iloc[-L] - 1
    tr = h.iloc[-1] / h.iloc[-200:].mean() - 1
    vol = -h.iloc[-126:].pct_change(fill_method=None).std()
    rk = pd.concat([mom.rank(pct=True), tr.rank(pct=True), vol.rank(pct=True)], axis=1).mean(axis=1)
    rk = rk[(tr > 0)]
    return _top(rk)


STRATEGIES: dict[str, tuple[list[Any], Callable[[pd.DataFrame, Any], pd.Series]]] = {
    "momentum": ([126, 252], s_momentum),
    "trend": ([100, 200], s_trend),
    "low_vol": ([63, 126], s_lowvol),
    "rsi_reversion": ([35, 45], s_rsi_rev),
    "combined": ([126, 252], s_combined),
}


def simulate(px: pd.DataFrame, fn: Callable, param: Any) -> dict[str, Any]:
    """Full-history simulation with month-end signals; returns daily net returns and per-position period returns."""
    px = px.ffill(limit=5)
    rets = px.pct_change(fill_method=None).fillna(0.0)
    idx = px.index
    month_end = pd.Series(idx, index=idx).groupby(idx.to_period("M")).last().values
    sig_dates = [d for d in month_end if idx.get_loc(d) + 1 < len(idx)]
    exec_map = {idx[idx.get_loc(d) + 1]: d for d in sig_dates}
    w = pd.Series(0.0, index=px.columns)
    daily = pd.Series(0.0, index=idx)
    costs = pd.Series(0.0, index=idx)
    periods: list[dict[str, Any]] = []
    cur: Optional[dict[str, Any]] = None
    ter = pd.Series({c: TER.get(c, 0.0) for c in px.columns}) / 252
    sc = pd.Series({c: side_cost(c) for c in px.columns})
    for i, d in enumerate(idx):
        if i > 0:
            day_r = float((w * rets.loc[d]).sum() - (w * ter).sum())
            daily.iloc[i] = day_r
            grown = w * (1 + rets.loc[d])
            tot = 1 + float((w * rets.loc[d]).sum())
            w = grown / tot if tot > 0 else grown
        if d in exec_map:
            t = exec_map[d]
            hist = px.loc[:t]
            tgt = fn(hist, param).reindex(px.columns).fillna(0.0)
            tc = float(((tgt - w).abs() * sc).sum())
            daily.iloc[i] -= tc
            costs.iloc[i] = tc
            if cur is not None:
                for tkr in cur["names"]:
                    p0, p1 = px.at[cur["date"], tkr], px.at[d, tkr]
                    if pd.notna(p0) and pd.notna(p1) and p0 > 0:
                        periods.append({"start": cur["date"], "end": d, "ticker": tkr,
                                        "ret": float(p1 / p0 - 1 - 2 * sc[tkr])})
            cur = {"date": d, "names": list(tgt[tgt > 0].index)}
            w = tgt
    return {"daily": daily, "periods": periods, "costs": costs}


def metrics(r: pd.Series, bench: Optional[pd.Series] = None) -> dict[str, Any]:
    r = r.dropna()
    if len(r) < 20:
        return {}
    eq = (1 + r).cumprod()
    yrs = len(r) / 252
    cagr = float(eq.iloc[-1] ** (1 / yrs) - 1) if yrs > 0 and eq.iloc[-1] > 0 else None
    sd = float(r.std())
    out = {"cagr": cagr, "sharpe": float(r.mean() / sd * np.sqrt(252)) if sd > 0 else None,
           "vol": sd * np.sqrt(252), "max_drawdown": float((eq / eq.cummax() - 1).min()), "days": len(r)}
    if bench is not None:
        b = bench.reindex(r.index).fillna(0)
        beq = (1 + b).cumprod()
        bc = float(beq.iloc[-1] ** (1 / yrs) - 1) if yrs > 0 else None
        out["benchmark_cagr"] = bc
        out["excess_cagr"] = (cagr - bc) if cagr is not None and bc is not None else None
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in out.items()}


def walk_forward(px: pd.DataFrame, bench: pd.Series, name: str) -> dict[str, Any]:
    grid, fn = STRATEGIES[name]
    sims = {p: simulate(px, fn, p) for p in grid}
    idx = px.index
    start = idx[0] + pd.DateOffset(months=12)  # warm-up for 252d lookbacks
    oos_parts, chosen, periods = [], [], []
    t0 = start + pd.DateOffset(months=TRAIN_M)
    while t0 < idx[-1]:
        t1 = min(t0 + pd.DateOffset(months=STEP_M), idx[-1] + pd.Timedelta(days=1))
        train = slice(t0 - pd.DateOffset(months=TRAIN_M), t0 - pd.Timedelta(days=1))
        best, best_s = None, -1e9
        for p, sim in sims.items():
            tr = sim["daily"].loc[train]
            s = tr.mean() / tr.std() * np.sqrt(252) if tr.std() > 0 else -1e9
            if s > best_s:
                best, best_s = p, s
        seg = sims[best]["daily"].loc[t0:t1 - pd.Timedelta(days=1)]
        oos_parts.append(seg)
        periods += [x for x in sims[best]["periods"] if t0 <= x["start"] < t1]
        chosen.append({"from": str(t0.date()), "to": str((t1 - pd.Timedelta(days=1)).date()), "param": best,
                       "train_sharpe": round(float(best_s), 3)})
        t0 = t1
    oos = pd.concat(oos_parts) if oos_parts else pd.Series(dtype=float)
    m = metrics(oos, bench)
    wins = [p["ret"] for p in periods if p["ret"] > 0]
    losses = [p["ret"] for p in periods if p["ret"] <= 0]
    m.update({"n_positions": len(periods), "hit_rate": round(len(wins) / len(periods), 4) if periods else None,
              "avg_win": round(float(np.mean(wins)), 4) if wins else None,
              "avg_loss": round(float(np.mean(losses)), 4) if losses else None,
              "oos_from": str(oos.index[0].date()) if len(oos) else None, "oos_to": str(oos.index[-1].date()) if len(oos) else None})
    weak_reasons = []
    if m.get("sharpe") is None or m["sharpe"] < WEAK["sharpe"]:
        weak_reasons.append(f"OOS Sharpe {m.get('sharpe')} < {WEAK['sharpe']}")
    if m.get("excess_cagr") is not None and m["excess_cagr"] < WEAK["excess"]:
        weak_reasons.append(f"excess CAGR {m['excess_cagr']:+.2%} vs benchmark")
    if m.get("hit_rate") is not None and m["hit_rate"] < WEAK["hit"]:
        weak_reasons.append(f"hit rate {m['hit_rate']:.0%} < 50%")
    m["weak"] = bool(weak_reasons)
    m["weak_reasons"] = weak_reasons
    m["chosen_params"] = chosen
    eq = (1 + oos).cumprod()
    m["equity_monthly"] = [[str(d.date()), round(float(v), 4)] for d, v in eq.resample("ME").last().items()] if len(oos) else []
    return m


def run_backtest_sync() -> dict[str, Any]:
    out = {}
    for uni, spec in UNIVERSES.items():
        tick = spec["tickers"] + [spec["benchmark"]]
        px_all = download_closes(tick, None, "10y", 3600)
        px = px_all[[t for t in spec["tickers"] if t in px_all.columns]].dropna(how="all")
        b = px_all[spec["benchmark"]].ffill(limit=5).pct_change(fill_method=None).fillna(0) - TER.get(spec["benchmark"], 0) / 252
        res = {}
        for name in STRATEGIES:
            try:
                res[name] = walk_forward(px, b, name)
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("backtest %s/%s failed: %s", uni, name, exc)
                res[name] = {"error": str(exc)[:200]}
        bm = metrics(b.loc[px.index[0] + pd.DateOffset(months=12 + TRAIN_M):])
        out[uni] = {"strategies": res, "benchmark": {"ticker": spec["benchmark"], **bm},
                    "data_from": str(px.index[0].date()), "data_to": str(px.index[-1].date()), "tickers": list(px.columns)}
    return out


CONFIG = {"rebalance": "monthly (signal at month-end close, execute next close)", "top_k": TOP_K,
          "train_months": TRAIN_M, "oos_step_months": STEP_M,
          "costs": {"thai_side": round(COMMISSION_TH * (1 + VAT) + SLIPPAGE, 6), "offshore_side": US_COMMISSION + FX_SPREAD + SLIPPAGE,
                    "ter": TER, "note": "commission 0.157% + 7% VAT; slippage 0.10%/side; offshore commission/FX are assumptions"},
          "weak_thresholds": WEAK, "data": "yfinance adjusted closes (10y) - survivorship bias: universe = today's watch list"}


async def run_backtest(pool: Any) -> dict[str, Any]:
    res = await asyncio.to_thread(run_backtest_sync)
    as_of = datetime.now(ICT).date()
    async with pool.acquire() as conn:
        await conn.execute(DDL)
        for uni, r in res.items():
            await conn.execute("INSERT INTO backtest_runs (universe, config, results) VALUES ($1,$2::jsonb,$3::jsonb)",
                               uni, json.dumps(CONFIG), json.dumps(r, default=str))
            for name, m in r["strategies"].items():
                if "error" in m:
                    continue
                await conn.execute(
                    """INSERT INTO signal_performance (as_of, signal, source, universe, n, hit_rate, avg_win, avg_loss, sharpe, excess, weak, sufficient, detail)
                       VALUES ($1,$2,'backtest',$3,$4,$5,$6,$7,$8,$9,$10,$11,$12::jsonb)
                       ON CONFLICT (as_of, signal, source, universe) DO UPDATE SET n=EXCLUDED.n, hit_rate=EXCLUDED.hit_rate,
                         avg_win=EXCLUDED.avg_win, avg_loss=EXCLUDED.avg_loss, sharpe=EXCLUDED.sharpe, excess=EXCLUDED.excess,
                         weak=EXCLUDED.weak, sufficient=EXCLUDED.sufficient, detail=EXCLUDED.detail, created_at=now()""",
                    as_of, name, uni, m.get("n_positions"), m.get("hit_rate"), m.get("avg_win"), m.get("avg_loss"), m.get("sharpe"),
                    m.get("excess_cagr"), m["weak"], (m.get("n_positions") or 0) >= 30,
                    json.dumps({k: m.get(k) for k in ("cagr", "max_drawdown", "benchmark_cagr", "weak_reasons", "oos_from", "oos_to")}))
    return {"as_of": as_of.isoformat(), "summary": {u: {n: {k: m.get(k) for k in ("cagr", "sharpe", "excess_cagr", "hit_rate", "weak")}
                                                       for n, m in r["strategies"].items()} for u, r in res.items()}}


async def latest_backtest(pool: Any) -> dict[str, Any]:
    async with pool.acquire() as conn:
        await conn.execute(DDL)
        rows = await conn.fetch("""SELECT DISTINCT ON (universe) universe, run_at, config, results FROM backtest_runs
                                   ORDER BY universe, run_at DESC""")
    out = {}
    for r in rows:
        out[r["universe"]] = {"run_at": r["run_at"].isoformat(),
                              "config": json.loads(r["config"]) if isinstance(r["config"], str) else r["config"],
                              **(json.loads(r["results"]) if isinstance(r["results"], str) else r["results"])}
    return out


# ------------------------------------------------------------------ live outcome scoring
HORIZON = 20  # trading days
LIVE_SIGNALS = ["composite", "value", "quality", "momentum", "low_vol", "dividend", "technical", "flows", "fundamentals", "sentiment"]


async def score_live_outcomes(pool: Any) -> dict[str, Any]:
    """For stored signal_scores at least HORIZON sessions old: long when percentile/score >= 60;
    report hit rate (fwd return > 0), avg win/loss, annualised Sharpe of 20d returns; n < 30 = insufficient."""
    async with pool.acquire() as conn:
        await conn.execute(DDL)
        rows = [dict(r) for r in await conn.fetch(
            "SELECT as_of, ticker, score, components FROM signal_scores WHERE as_of <= current_date - 28")]
    as_of = datetime.now(ICT).date()
    results = {}
    if rows:
        tick = sorted({r["ticker"] for r in rows if r["ticker"] != "SCBGOLDE"})
        px = await asyncio.to_thread(download_closes, tick, (min(r["as_of"] for r in rows) - timedelta(days=5)).isoformat(), None, 3600)
        obs: dict[str, list[float]] = {s: [] for s in LIVE_SIGNALS}
        for r in rows:
            if r["ticker"] not in px.columns:
                continue
            s = px[r["ticker"]].dropna()
            pos = s.index.searchsorted(pd.Timestamp(r["as_of"]), side="right") - 1
            if pos < 0 or pos + HORIZON >= len(s):
                continue
            fwd = float(s.iloc[pos + HORIZON] / s.iloc[pos] - 1)
            comps = r["components"] if isinstance(r["components"], dict) else json.loads(r["components"] or "{}")
            vals = {"composite": float(r["score"]) if r["score"] is not None else None, **comps}
            for sig in LIVE_SIGNALS:
                v = vals.get(sig)
                if v is not None and float(v) >= 60:
                    obs[sig].append(fwd - 2 * side_cost(r["ticker"]))
        for sig, xs in obs.items():
            results[sig] = _perf(xs)
    else:
        results = {s: _perf([]) for s in LIVE_SIGNALS}
    async with pool.acquire() as conn:
        for sig, m in results.items():
            await conn.execute(
                """INSERT INTO signal_performance (as_of, signal, source, universe, n, hit_rate, avg_win, avg_loss, sharpe, weak, sufficient, detail)
                   VALUES ($1,$2,'live','all',$3,$4,$5,$6,$7,$8,$9,$10::jsonb)
                   ON CONFLICT (as_of, signal, source, universe) DO UPDATE SET n=EXCLUDED.n, hit_rate=EXCLUDED.hit_rate, avg_win=EXCLUDED.avg_win,
                     avg_loss=EXCLUDED.avg_loss, sharpe=EXCLUDED.sharpe, weak=EXCLUDED.weak, sufficient=EXCLUDED.sufficient,
                     detail=EXCLUDED.detail, created_at=now()""",
                as_of, sig, m["n"], m["hit_rate"], m["avg_win"], m["avg_loss"], m["sharpe"], m["weak"], m["sufficient"],
                json.dumps({"horizon_days": HORIZON, "rule": "long when score/percentile >= 60, net of round-trip costs",
                            "weak_reasons": m["weak_reasons"]}))
    return {"as_of": as_of.isoformat(), "observations": len(rows), "signals": results}


def _perf(xs: list[float]) -> dict[str, Any]:
    n = len(xs)
    if n == 0:
        return {"n": 0, "hit_rate": None, "avg_win": None, "avg_loss": None, "sharpe": None, "weak": None,
                "sufficient": False, "weak_reasons": ["no matured observations yet (needs 20 sessions)"]}
    a = np.array(xs)
    wins, losses = a[a > 0], a[a <= 0]
    sh = float(a.mean() / a.std() * np.sqrt(252 / HORIZON)) if a.std() > 0 else None
    hit = float((a > 0).mean())
    reasons = []
    if sh is not None and sh < WEAK["sharpe"]:
        reasons.append(f"Sharpe {sh:.2f} < {WEAK['sharpe']}")
    if hit < WEAK["hit"]:
        reasons.append(f"hit rate {hit:.0%} < 50%")
    suff = n >= 30
    return {"n": n, "hit_rate": round(hit, 4), "avg_win": round(float(wins.mean()), 5) if wins.size else None,
            "avg_loss": round(float(losses.mean()), 5) if losses.size else None, "sharpe": round(sh, 3) if sh is not None else None,
            "weak": bool(reasons) if suff else None, "sufficient": suff,
            "weak_reasons": reasons if suff else reasons + [f"n={n} < 30: insufficient, not flagged"]}


async def signal_performance(pool: Any) -> dict[str, Any]:
    async with pool.acquire() as conn:
        await conn.execute(DDL)
        rows = await conn.fetch("""SELECT DISTINCT ON (signal, source, universe) * FROM signal_performance
                                   ORDER BY signal, source, universe, as_of DESC""")
    out = []
    for r in rows:
        d = dict(r)
        for k, v in list(d.items()):
            if hasattr(v, "isoformat"):
                d[k] = v.isoformat()
            elif v.__class__.__name__ == "Decimal":
                d[k] = float(v)
            elif k == "detail" and isinstance(v, str):
                d[k] = json.loads(v)
        out.append(d)
    return {"items": out, "weak": [f"{d['signal']} ({d['source']}/{d['universe']})" for d in out if d.get("weak")]}


async def weak_signal_names(pool: Any) -> list[str]:
    return (await signal_performance(pool))["weak"]


async def outcome_job(pool: Any, legacy: Optional[Callable] = None) -> dict[str, Any]:
    """08:00 job: legacy recommendation outcomes + live signal scoring + paper ledger."""
    import trade_plans as tp
    out: dict[str, Any] = {}
    if legacy is not None:
        try:
            out["recommendations"] = await legacy()
        except Exception as exc:  # noqa: BLE001
            out["recommendations_error"] = str(exc)[:200]
    out["live"] = await score_live_outcomes(pool)
    out["paper"] = await tp.update_paper_ledger(pool)
    out["weak"] = await weak_signal_names(pool)
    return out
