"""Performance measurement & attribution - pro layer #6 (2026-10-30).

Why holdings-based: the DB has no transactions/cash-flow table and the recorded daily totals
(portfolio_performance) mix a June-July portfolio (incl. BAFS, unpriced gold fund), a 12-week gap
and partial valuations (SCBGOLDE unpriced from 15 Oct). So returns are rebuilt from units x daily
total-return prices (yfinance auto-adjusted closes, dividends reinvested), which is flow-neutral by
construction (= time-weighted). Cash flows for MWR are inferred: the current portfolio was
established on the inception date at the recorded average costs.

Windows:
  live      - since inception (first fully valued snapshot; avg costs = that day's prices)
  proforma  - current units held constant over 1y and 3y (what the current mix would have done)
Benchmarks: SET TRI proxy = TDEX.BK total return (^SET.BK has no history on Yahoo), gold in THB
(GC=F x THB=X), policy benchmark = DRAFT strategic weights (TDEX / gold THB / SPY THB / cash at BoT rate),
rebalanced daily.
Attribution (vs policy benchmark, daily Brinson-Fachler on log returns, summed):
  allocation, selection (incl. interaction), currency (USD exposure difference x USD/THB move),
  timing (= buy-and-hold drift vs constant start weights), residual (linking error).
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
from datetime import date, datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from market_history import SET_PROXY, download_closes
from portfolio_construction import CLASSES, classify, load_policy

LOGGER = logging.getLogger("portfolio_engine.attribution")
ICT = ZoneInfo("Asia/Bangkok")
DDL = """
CREATE TABLE IF NOT EXISTS performance_reports (
    id         SERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    result     JSONB NOT NULL
);
"""
FX_EXPOSED = {"gold": 1.0, "global_equity": 1.0, "thai_equity": 0.0, "cash_bonds": 0.0}


def _stats(r: pd.Series, rf_d: float) -> dict[str, Any]:
    r = r.dropna()
    n = len(r)
    if n < 5:
        return {"n_days": n}
    tot = float(np.exp(r.sum()) - 1)
    ann = float(np.exp(r.mean() * 252) - 1)
    vol = float(r.std(ddof=1) * math.sqrt(252))
    ex = r - rf_d
    dn = ex[ex < 0]
    ddev = float(math.sqrt((dn ** 2).sum() / n) * math.sqrt(252)) if len(dn) else float("nan")
    curve = np.exp(r.cumsum())
    mdd = float((curve / curve.cummax() - 1).min())
    return {"n_days": n, "total_return_pct": round(tot * 100, 2), "annualised_pct": round(ann * 100, 2),
            "vol_pct": round(vol * 100, 2), "sharpe": round(float(ex.mean() * 252 / vol), 2) if vol else None,
            "sortino": round(float(ex.mean() * 252 / ddev), 2) if ddev and not math.isnan(ddev) else None,
            "max_drawdown_pct": round(mdd * 100, 2), "calmar": round(ann / abs(mdd), 2) if mdd < 0 else None,
            "significance": "low (<126 days)" if n < 126 else "ok"}


def _regress(y: pd.Series, xs: dict[str, pd.Series], rf_d: float) -> dict[str, Any]:
    df = pd.concat([y.rename("y")] + [v.rename(k) for k, v in xs.items()], axis=1).dropna()
    if len(df) < 20:
        return {"n_days": len(df), "note": "too few days"}
    with np.errstate(all="ignore"):
        return _ols(df, list(xs), rf_d)


def _ols(df: pd.DataFrame, xs: list[str], rf_d: float) -> dict[str, Any]:
    Y = df["y"].values - rf_d
    X = np.column_stack([np.ones(len(df))] + [df[k].values - rf_d for k in xs])
    beta, *_ = np.linalg.lstsq(X, Y, rcond=None)
    res = Y - X @ beta
    s2 = res @ res / (len(Y) - X.shape[1])
    se = np.sqrt(np.diag(s2 * np.linalg.inv(X.T @ X)))
    r2 = 1 - res @ res / ((Y - Y.mean()) @ (Y - Y.mean()))
    out = {"n_days": len(df), "alpha_ann_pct": round(float(beta[0] * 252 * 100), 2), "alpha_t": round(float(beta[0] / se[0]), 2), "r2": round(float(r2), 3)}
    for i, k in enumerate(xs, start=1):
        out[f"beta_{k}"] = round(float(beta[i]), 3)
        out[f"t_{k}"] = round(float(beta[i] / se[i]), 2)
    return out


def _xirr(flows: list[tuple[date, float]]) -> Optional[float]:
    def npv(r: float) -> float:
        t0 = flows[0][0]
        return sum(cf / (1 + r) ** ((d - t0).days / 365.0) for d, cf in flows)
    lo, hi = -0.99, 10.0
    if npv(lo) * npv(hi) > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        if npv(lo) * npv(mid) <= 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def _brinson(vals: pd.DataFrame, cls_of: dict[str, str], bench_w: dict[str, float], bench_local: pd.DataFrame,
             fx: pd.Series, rf_d: float, local_of: dict[str, pd.Series]) -> dict[str, Any]:
    """vals: daily THB value per holding. bench_local: local (pre-FX) log returns per class. local_of: per holding local log return."""
    cls_vals = vals.T.groupby(lambda t: cls_of[t]).sum().T.reindex(columns=CLASSES, fill_value=0.0)
    wp = cls_vals.div(cls_vals.sum(axis=1), axis=0).shift(1).iloc[1:]
    # portfolio local sleeve returns: value-weighted holding local returns
    lp = pd.DataFrame(0.0, index=wp.index, columns=CLASSES)
    for c in CLASSES:
        hs = [h for h in vals.columns if cls_of[h] == c]
        if not hs:
            lp[c] = bench_local[c].reindex(wp.index).fillna(0)  # irrelevant (weight 0)
            continue
        hw = vals[hs].div(vals[hs].sum(axis=1), axis=0).shift(1).reindex(wp.index)
        lp[c] = sum(hw[h] * local_of[h].reindex(wp.index).fillna(0) for h in hs)
    lb = bench_local.reindex(wp.index).fillna(0)
    wb = pd.Series(bench_w)[CLASSES] / 100
    fxr = fx.reindex(wp.index).fillna(0)
    Lb = (lb * wb).sum(axis=1)
    alloc = ((wp - wb).mul(lb.sub(Lb, axis=0))).sum()
    sel = (wp * (lp - lb)).sum()
    ep = pd.Series(FX_EXPOSED)[CLASSES]
    cur = ((wp * ep).sum(axis=1) - float((wb * ep).sum())) * fxr
    rp = (wp * lp).sum(axis=1) + (wp * ep).sum(axis=1) * fxr
    rb = Lb + float((wb * ep).sum()) * fxr
    active = float(rp.sum() - rb.sum())
    out = {"allocation_pct": {c: round(float(alloc[c]) * 100, 2) for c in CLASSES},
           "selection_pct": {c: round(float(sel[c]) * 100, 2) for c in CLASSES},
           "currency_pct": round(float(cur.sum()) * 100, 2)}
    out["allocation_total_pct"] = round(float(alloc.sum()) * 100, 2)
    out["selection_total_pct"] = round(float(sel.sum()) * 100, 2)
    out["active_log_pct"] = round(active * 100, 2)
    out["portfolio_log_pct"] = round(float(rp.sum()) * 100, 2)
    out["benchmark_log_pct"] = round(float(rb.sum()) * 100, 2)
    out["avg_weights_pct"] = {c: round(float(wp[c].mean()) * 100, 1) for c in CLASSES}
    return out


async def run_attribution(pool: Any) -> dict[str, Any]:
    import risk_engine as re_mod
    pol = load_policy()
    positions = await re_mod._positions(pool)
    async with pool.acquire() as conn:
        await conn.execute(DDL)
        hold = {r["ticker"]: dict(r) for r in await conn.fetch("SELECT ticker, quantity, avg_cost_price FROM holdings WHERE quantity > 0")}
        bot = await conn.fetchval("SELECT reading FROM market_factors WHERE key='bot_rate'")
        inception = await conn.fetchval("SELECT min(record_date) FROM portfolio_performance WHERE (snapshot->>'valuation_complete')='true'")
        legacy = await conn.fetch("SELECT record_date, total_value_thb, (snapshot->>'valuation_complete') vc FROM portfolio_performance ORDER BY record_date")
    rf = float(bot or 1.0) / 100
    rf_d = math.log(1 + rf) / 252
    tickers = list(hold)
    listed = [t for t in tickers if t != "SCBGOLDE"]
    px = await asyncio.to_thread(download_closes, listed + [SET_PROXY, "GC=F", "SPY", "THB=X"], None, "3y", 3600)
    px = px.ffill()
    gold_thb = (px["GC=F"] * px["THB=X"]).dropna()
    nav_now = next((p["value_thb"] / p["quantity"] for p in positions if p["ticker"] == "SCBGOLDE" and p.get("quantity")), None)
    P = pd.DataFrame({t: px[t] for t in listed})
    if "SCBGOLDE" in hold:
        P["SCBGOLDE"] = gold_thb * (float(nav_now) / float(gold_thb.iloc[-1]) if nav_now else 1.0)
    P = P.dropna()
    logret = np.log(P).diff()
    local_of = {t: (np.log(px["GC=F"]).diff() if t == "SCBGOLDE" else logret[t]) for t in P.columns}
    fx = np.log(px["THB=X"]).diff()
    bench_local = pd.DataFrame({"thai_equity": np.log(px[SET_PROXY]).diff(), "gold": np.log(px["GC=F"]).diff(),
                                "global_equity": np.log(px["SPY"]).diff(), "cash_bonds": pd.Series(rf_d, index=px.index)})
    bw = {k: pol["asset_classes"][k]["target"] for k in CLASSES}
    wb = pd.Series(bw)[CLASSES] / 100
    bench_policy = (bench_local * wb).sum(axis=1) + float((wb * pd.Series(FX_EXPOSED)[CLASSES]).sum()) * fx
    tdex = np.log(px[SET_PROXY]).diff()
    gold_r = np.log(gold_thb).diff()
    cls_of = {t: classify(t, pol) for t in P.columns}
    units = pd.Series({t: float(hold[t]["quantity"]) for t in P.columns})

    def window(start: pd.Timestamp, label: str) -> dict[str, Any]:
        Pw = P[P.index >= start]
        vals = Pw * units
        v = vals.sum(axis=1)
        r = np.log(v).diff().dropna()
        w0 = vals.iloc[0] / v.iloc[0]
        cm = (logret.reindex(r.index) * w0).sum(axis=1)  # constant-mix at start weights (approx, log)
        timing = float(r.sum() - cm.sum())
        b = _brinson(vals, cls_of, bw, bench_local, fx, rf_d, local_of)
        b["timing_pct"] = round(timing * 100, 2)
        b["residual_pct"] = round(b["active_log_pct"] - b["allocation_total_pct"] - b["selection_total_pct"] - b["currency_pct"], 2)
        return {"label": label, "start": str(Pw.index[0].date()), "end": str(Pw.index[-1].date()),
                "portfolio": _stats(r, rf_d), "benchmarks": {"set_tri_proxy_TDEX": _stats(tdex.reindex(r.index), rf_d),
                "gold_thb": _stats(gold_r.reindex(r.index), rf_d), "policy_benchmark": _stats(bench_policy.reindex(r.index), rf_d)},
                "alpha": {"vs_set_tri_proxy": _regress(r, {"tdex": tdex}, rf_d), "vs_gold": _regress(r, {"gold": gold_r}, rf_d),
                          "two_factor": _regress(r, {"tdex": tdex, "gold": gold_r}, rf_d)},
                "attribution_vs_policy": b, "end_value_thb": round(float(v.iloc[-1]), 0)}

    out: dict[str, Any] = {"as_of": datetime.now(ICT).isoformat(timespec="minutes"), "risk_free_pct": rf * 100,
                           "rf_source": "BoT policy rate (market_factors.bot_rate)"}
    if inception:
        live = window(pd.Timestamp(inception), "live since inception")
        cost = sum(float(hold[t]["quantity"]) * float(hold[t]["avg_cost_price"]) for t in hold)
        end_v = live["end_value_thb"]
        mwr = _xirr([(inception, -cost), (date.fromisoformat(live["end"]), end_v)])
        days = (date.fromisoformat(live["end"]) - inception).days
        live["twr_pct"] = live["portfolio"].get("total_return_pct")
        live["mwr"] = {"period_return_on_cost_pct": round((end_v / cost - 1) * 100, 2), "irr_annualised_pct": round(mwr * 100, 1) if mwr is not None else None,
                       "days": days, "cost_basis_thb": round(cost, 0),
                       "flows": "inferred: one purchase at recorded avg cost on the inception date; dividends reinvested in prices (no cash-flow table)",
                       "note": "annualised IRR over <1 year is not meaningful; use the period return"}
        live["inception"] = str(inception)
        out["live"] = live
    end = P.index[-1]
    out["proforma_1y"] = window(end - pd.Timedelta(days=365), "pro-forma: current units held 1y")
    out["proforma_3y"] = window(P.index[0], "pro-forma: current units held 3y")
    out["recorded_series_audit"] = {
        "rows": len(legacy), "first": str(legacy[0]["record_date"]) if legacy else None,
        "gap": "no rows 2026-07-16 .. 2026-10-06", "partial_rows": sum(1 for r in legacy if r["vc"] == "false"),
        "why_not_used": "June-July portfolio differed (BAFS.BK, unpriced gold fund) and SCBGOLDE was unpriced from 15 Oct, so recorded totals contain flows and gaps; TWR from them would be wrong."}
    out["notes"] = ["SCBGOLDE daily path = GC=F x THB=X scaled to its latest official NAV (proxy; fund TER not deducted).",
                    "Returns are log-additive; attribution effects sum to the active return up to the residual.",
                    "Currency effect = (portfolio USD exposure - benchmark USD exposure) x USD/THB log move; SCBGOLDE treated as USD-exposed (unhedged).",
                    "Timing = buy-and-hold drift vs holding the start weights constant (no trades were recorded in the window).",
                    "Live window is short: ratios and alpha are not statistically meaningful yet."]
    out["sources"] = {"prices": "yfinance auto-adjusted closes", "units_cost": "holdings table", "nav": "risk engine position price (SCBGOLDE official NAV)"}
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO performance_reports (result) VALUES ($1::jsonb)", json.dumps(out, default=str))
    return out


async def latest(pool: Any) -> Optional[dict[str, Any]]:
    async with pool.acquire() as conn:
        await conn.execute(DDL)
        r = await conn.fetchrow("SELECT id, created_at, result FROM performance_reports ORDER BY created_at DESC LIMIT 1")
    if not r:
        return None
    res = json.loads(r["result"]) if isinstance(r["result"], str) else r["result"]
    return {"id": r["id"], "created_at": r["created_at"].astimezone(ICT).isoformat(), **res}
