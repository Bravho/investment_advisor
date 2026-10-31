"""P3 walk-forward / time-split backtests (2026-11-01). Read-only: no DB writes, results -> data/backtests/.

Tests (Tho's rule: anything affecting signals or forecasts must pass a walk-forward backtest first):
  P3.1  learning weights segmented by family (core vs macro_trends) vs pooled; regime definition
        (backfill proxy TDEX>SMA200 / SPY>SMA200) vs the live multi-input rule (signals.regime_from_closes)
  P3.2  cross-asset feature (driver trailing return -> subject forward return) for Thai energy <- Brent, GDX <- gold
  P3.3  price-only signal composite (momentum + low_vol + technical, the components that have price history)
        through the existing walk-forward simulator (walkforward.simulate / metrics, same costs and weak thresholds)
  P3.4  news sentiment as a forecast feature (IC vs forward returns; history length check)
  P3.5  macro-board forecasts as construction views: track record available (live / backfill)
Method for forecasts: in-memory regeneration of the frozen backfill design (price-only models, data <= as-of),
expanding-window re-learning of weights each year (same formula as predictions.learn), evaluated out-of-sample.
"""
from __future__ import annotations

import asyncio
import json
import math
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "portfolio_engine"), str(ROOT / "ai_engine")]
import predictions as P  # noqa: E402
import signals as S  # noqa: E402
from market_history import SET_PROXY, download_closes  # noqa: E402

H_TEST = {"1m": 21, "3m": 63, "6m": 126}
YEARS = 6
CROSS = {"PTTEP.BK": "BZ=F", "PTT.BK": "BZ=F", "TOP.BK": "BZ=F", "IRPC.BK": "BZ=F", "GDX": "GC=F"}
CROSS_PRIOR = 0.10


def regime_proxy(px: pd.DataFrame, d, equity_ref: str) -> str | None:
    s = px[equity_ref].loc[:d].dropna() if equity_ref in px else None
    if s is None or len(s) <= 200:
        return None
    return "risk_on" if s.iloc[-1] > s.iloc[-200:].mean() else "risk_off"


def cross_model(lp: pd.Series, ld: pd.Series, h: int) -> float | None:
    """b * driver trailing L-day log return; b = shrunk OLS of the subject's fwd h return on it, data <= as-of only."""
    j = pd.concat([lp, ld], axis=1, keys=["s", "d"]).dropna()
    if len(j) < 400:
        return None
    L = max(h, 21)
    fwd = (j.s.shift(-h) - j.s).values
    past = (j.d - j.d.shift(L)).values
    usable = len(j) - h
    b, n = P._coef(past[:usable], fwd[:usable])
    return float(b * (j.d.iloc[-1] - j.d.iloc[-1 - L]))


def generate(closes: pd.DataFrame, subjects: dict[str, str]) -> list[dict]:
    recs = []
    end = closes.index[-1]
    idx = closes.index[closes.index >= end - pd.DateOffset(years=YEARS)]
    monthly = pd.DatetimeIndex(pd.Series(idx, index=idx).groupby(idx.to_period("M")).first().values)
    reg_tick = [t for t in S.REGIME_TICKERS if t in closes]
    reg_cache = {}
    for d in monthly:
        sub = closes[reg_tick].loc[:d].iloc[-260:]
        reg_cache[d] = S.regime_from_closes(sub)["regime"]
    for subj, fam in subjects.items():
        ser = P._series_for(subj, closes)
        if ser is None or len(ser) < 600:
            continue
        lp_full = np.log(ser)
        is_factor = subj in P.FACTORS or fam == "macro_trends"
        for h, hd in H_TEST.items():
            for d in monthly:
                if (pd.Timestamp(d) + pd.offsets.BDay(hd)) > end:
                    continue
                lp = lp_full.loc[:d]
                if len(lp) < 400:
                    continue
                beta = 0.0 if subj in P.FACTORS else 1.0
                out = {}
                for rk, reg in (("A", regime_proxy(closes, d, SET_PROXY if fam == "core" else "SPY")), ("B", reg_cache.get(d))):
                    mo = P.model_outputs(lp, hd, {"regime": reg, "beta": beta})
                    if "error" in mo:
                        break
                    out[rk] = mo
                if len(out) < 2:
                    continue
                fut = lp_full.loc[d:]
                if len(fut) <= hd:
                    continue
                actual = float(fut.iloc[hd] - fut.iloc[0])
                m = {k: v for k, v in out["A"]["models"].items() if v is not None}
                m["regime_B"] = out["B"]["models"]["regime"]
                if subj in CROSS and CROSS[subj] in closes:
                    m["cross"] = cross_model(lp, np.log(closes[CROSS[subj]].dropna()).loc[:d], hd)
                recs.append({"subject": subj, "family": fam, "h": h, "as_of": pd.Timestamp(d), "sigma": out["A"]["sigma"],
                             "actual": actual, "models": m})
    return recs


def learn_w(rs: list[dict], models: list[str], prior: dict[str, float]) -> dict[str, float]:
    raw = {}
    for m in models:
        es, eb, hits = [], [], []
        for r in rs:
            v = r["models"].get(m)
            if v is None:
                continue
            a, s2 = r["actual"], r["sigma"] ** 2 or 1e-9
            es.append((a - v) ** 2 / s2)
            eb.append(a ** 2 / s2)
            if abs(v) > 1e-9:
                hits.append((v > 0) == (a > 0))
        n = len(es)
        if n < P.MIN_N_RETIRE:
            raw[m] = prior[m]
            continue
        skill = 1 - sum(es) / sum(eb) if sum(eb) > 0 else 0.0
        hit = sum(hits) / len(hits) if hits else None
        if skill < -0.02 and (hit is None or hit < 0.5):
            raw[m] = 0.0
        else:
            raw[m] = prior[m] * max(0.25, 1 + 20 * skill) * (0.5 + (hit or 0.5))
    tot = sum(raw.values()) or 1
    return {k: v / tot for k, v in raw.items()}


def combo(r: dict, w: dict[str, float], regime_key: str = "regime") -> float:
    num = den = 0.0
    for m, wt in w.items():
        key = "regime_B" if (m == "regime" and regime_key == "regime_B") else m
        v = r["models"].get(key)
        if v is None or wt <= 0:
            continue
        num += wt * v
        den += wt
    return num / den if den else 0.0


def score(rs: list[dict], mus: list[float]) -> dict:
    if not rs:
        return {"n": 0}
    es = sum((r["actual"] - mu) ** 2 / r["sigma"] ** 2 for r, mu in zip(rs, mus))
    eb = sum(r["actual"] ** 2 / r["sigma"] ** 2 for r in rs)
    hits = [(mu > 0) == (r["actual"] > 0) for r, mu in zip(rs, mus) if abs(mu) > 1e-9]
    return {"n": len(rs), "skill_vs_rw": round(1 - es / eb, 4) if eb else None,
            "hit": round(sum(hits) / len(hits), 4) if hits else None}


def walk(recs: list[dict], train_filter, test_filter, models: list[str], prior: dict, regime_key="regime",
         test_years: int = 3) -> dict:
    """Expanding window: for each test year Y, learn on records whose target matured before Y starts."""
    end = max(r["as_of"] for r in recs)
    out = {}
    for h, hd in H_TEST.items():
        tested, mus = [], []
        for k in range(test_years, 0, -1):
            y0 = end - pd.DateOffset(years=k)
            y1 = y0 + pd.DateOffset(years=1)
            train = [r for r in recs if r["h"] == h and train_filter(r) and r["as_of"] + pd.offsets.BDay(hd) < y0]
            test = [r for r in recs if r["h"] == h and test_filter(r) and y0 <= r["as_of"] < y1]
            if regime_key == "regime_B":
                train = [{**r, "models": {**r["models"], "regime": r["models"].get("regime_B")}} for r in train]
            w = learn_w(train, models, prior)
            tested += test
            mus += [combo(r, w, regime_key) for r in test]
        out[h] = score(tested, mus)
    return out


def p33_signals(closes_g: pd.DataFrame, closes_t: pd.DataFrame) -> dict:
    import walkforward as wf
    BW = S.BASE_WEIGHTS
    wm, wl, wt = BW["momentum"], BW["low_vol"], BW["technical"]

    def composite(h: pd.DataFrame, bench_col) -> pd.Series:
        if len(h) <= 260:
            return pd.Series(dtype=float)
        hh = h.drop(columns=[bench_col], errors="ignore")
        r = hh.pct_change(fill_method=None)
        bench = h[bench_col] if bench_col in h else None
        mom = pd.concat([(hh.iloc[-22] / hh.iloc[-252] - 1).rank(pct=True), (hh.iloc[-1] / hh.iloc[-126] - 1).rank(pct=True)], axis=1).mean(axis=1)
        vol = (r.iloc[-252:].std()).rank(pct=True, ascending=False)
        if bench is not None:
            br = bench.pct_change(fill_method=None).iloc[-252:]
            beta = r.iloc[-252:].apply(lambda c: c.cov(br) / br.var() if br.var() > 0 else np.nan)
            vol = pd.concat([vol, beta.rank(pct=True, ascending=False)], axis=1).mean(axis=1)
        trend = (hh.iloc[-1] / hh.iloc[-200:].mean() - 1)
        rs3 = (hh.iloc[-1] / hh.iloc[-63] - 1) - ((bench.iloc[-1] / bench.iloc[-63] - 1) if bench is not None else 0)
        rsi = wf._rsi_frame(hh.iloc[-120:]).iloc[-1]
        rsi_sc = rsi.apply(lambda x: S._rsi_score(float(x)) if pd.notna(x) else np.nan)
        tech = pd.concat([trend.rank(pct=True), rs3.rank(pct=True), rsi_sc.rank(pct=True)], axis=1).mean(axis=1)
        sc = (wm * mom + wl * vol + wt * tech) / (wm + wl + wt)
        ok = hh.iloc[-252:].notna().sum() >= 230
        return wf._top(sc[ok].dropna())

    out = {}
    for name, px, bench in (("global", closes_g, "SPY"), ("thai", closes_t, SET_PROXY)):
        cols = [c for c in px.columns if c != bench]
        sim_px = px[cols]
        fn = lambda h, _p, b=bench, full=px: composite(full.loc[: h.index[-1]], b)  # noqa: E731
        sim = wf.simulate(sim_px, fn, None)
        start = px.index[0] + pd.DateOffset(months=12 + wf.TRAIN_M)
        oos = sim["daily"].loc[start:]
        m = wf.metrics(oos, px[bench].pct_change(fill_method=None))
        per = [p for p in sim["periods"] if p["start"] >= start]
        m["hit_rate"] = round(sum(p["ret"] > 0 for p in per) / len(per), 4) if per else None
        m["n_positions"] = len(per)
        reasons = []
        if m.get("sharpe") is None or m["sharpe"] < wf.WEAK["sharpe"]:
            reasons.append(f"Sharpe {m.get('sharpe')} < {wf.WEAK['sharpe']}")
        if m.get("excess_cagr") is not None and m["excess_cagr"] < wf.WEAK["excess"]:
            reasons.append(f"excess CAGR {m['excess_cagr']:+.2%}")
        if m.get("hit_rate") is not None and m["hit_rate"] < wf.WEAK["hit"]:
            reasons.append(f"hit {m['hit_rate']:.0%} < 50%")
        m["weak"] = bool(reasons)
        m["weak_reasons"] = reasons
        m["oos_from"] = str(oos.index[0].date()) if len(oos) else None
        out[name] = m
    return out


async def p34_sentiment(pool, closes: pd.DataFrame) -> dict:
    rows = await pool.fetch("""SELECT s.ticker, date_trunc('day', a.published_at)::date d, avg(s.score) sc, count(*) n
                               FROM sentiment_scores s JOIN news_articles a ON a.id = s.article_id
                               WHERE s.ticker IS NOT NULL AND a.published_at IS NOT NULL GROUP BY 1,2""")
    if not rows:
        return {"status": "no data"}
    df = pd.DataFrame([dict(r) for r in rows])
    df["d"] = pd.to_datetime(df["d"])
    first, last = df["d"].min(), df["d"].max()
    pts = []
    for t, g in df.groupby("ticker"):
        if t not in closes:
            continue
        px = closes[t].dropna()
        s = g.set_index("d")["sc"].astype(float).sort_index()
        for wk in pd.date_range(first + pd.Timedelta(days=7), last, freq="7D"):
            win = s.loc[wk - pd.Timedelta(days=7):wk]
            if win.empty:
                continue
            p0 = px.loc[:wk]
            fut = px.loc[wk:]
            if p0.empty or len(fut) <= 21:
                continue
            pts.append({"t": t, "wk": wk, "sent": float(win.mean()), "fwd": float(np.log(fut.iloc[21] / p0.iloc[-1]))})
    if not pts:
        return {"status": "insufficient", "history_days": int((last - first).days)}
    p = pd.DataFrame(pts)
    ics = [g["sent"].rank().corr(g["fwd"].rank()) for _, g in p.groupby("wk") if len(g) >= 5]
    ics = [x for x in ics if pd.notna(x)]
    ic = float(np.mean(ics)) if ics else None
    t_stat = float(ic / (np.std(ics, ddof=1) / math.sqrt(len(ics)))) if len(ics) >= 3 and np.std(ics) > 0 else None
    return {"history_from": str(first.date()), "history_to": str(last.date()), "history_days": int((last - first).days),
            "obs": len(p), "weeks_with_ic": len(ics), "mean_weekly_ic_1m": round(ic, 4) if ic is not None else None,
            "t_stat": round(t_stat, 2) if t_stat is not None else None,
            "pass_rule": ">= 52 weekly ICs (1y of overlapping weeks) and t >= 2 and mean IC > 0"}


async def p35_macro(pool) -> dict:
    rows = await pool.fetch("""SELECT p.source, p.horizon, count(*) n, avg((o.direction_hit)::int) hit,
                                      1 - sum(power(o.actual_return - p.exp_return, 2) / power(p.sigma, 2)) / NULLIF(sum(power(o.actual_return, 2) / power(p.sigma, 2)), 0) skill
                               FROM prediction_outcomes o JOIN predictions p ON p.id = o.prediction_id
                               WHERE p.subject = ANY($1::text[]) GROUP BY 1, 2 ORDER BY 1, 2""",
                            [SET_PROXY, "GC=F", "SPY", "THB=X"])
    return {"views_subjects": [SET_PROXY, "GC=F", "SPY", "THB=X"],
            "track": [{k: (round(float(v), 4) if isinstance(v, (float,)) or hasattr(v, "as_integer_ratio") and not isinstance(v, int) else v) for k, v in dict(r).items()} for r in rows]}


async def main() -> int:
    from utils.db_pool import db_pool
    import macro_trends as MT
    pool = await db_pool.get_pool()
    core = [s["subject"] for s in await P._subjects(pool)]
    subjects = {s: "core" for s in core}
    subjects.update({s: "macro_trends" for s in MT.MACRO_SUBJECTS if s not in subjects})
    tick = sorted({s for s in subjects if s not in P.PROXY} | {"GC=F", "THB=X", SET_PROXY, "SPY"} | set(S.REGIME_TICKERS) | set(CROSS.values()))
    tick = [t for t in tick if not any(c in t for c in ("XAUTHB",))]
    closes = await asyncio.to_thread(download_closes, tick, None, "10y", 3600)
    closes.index = pd.to_datetime(closes.index).tz_localize(None) if getattr(closes.index, "tz", None) is not None else pd.to_datetime(closes.index)
    recs = await asyncio.to_thread(generate, closes, subjects)
    base_models = ["drift", "momentum", "meanrev", "regime"]
    prior = {m: P.PRIOR_W[m] for m in base_models}
    is_core = lambda r: r["family"] == "core"  # noqa: E731
    is_macro = lambda r: r["family"] == "macro_trends"  # noqa: E731
    res: dict = {"generated_at": datetime.now().isoformat(timespec="minutes"), "records": len(recs),
                 "by_family": {f: sum(1 for r in recs if r["family"] == f) for f in ("core", "macro_trends")},
                 "design": "monthly as-of dates over 6y, price-only models, expanding-window yearly re-learning, last 3 years out-of-sample"}
    res["P3.1"] = {
        "core_pooled_weights": walk(recs, lambda r: True, is_core, base_models, prior),
        "core_segmented_weights": walk(recs, is_core, is_core, base_models, prior),
        "macro_pooled_weights": walk(recs, lambda r: True, is_macro, base_models, prior),
        "macro_segmented_weights": walk(recs, is_macro, is_macro, base_models, prior),
        "core_segmented_regime_live_rule": walk(recs, is_core, is_core, base_models, prior, "regime_B"),
        "macro_segmented_regime_live_rule": walk(recs, is_macro, is_macro, base_models, prior, "regime_B"),
        "prior_weights_core": walk(recs, lambda r: False, is_core, base_models, prior),
    }
    cross_subj = lambda r: r["subject"] in CROSS and r["models"].get("cross") is not None  # noqa: E731
    prior_x = {**prior, "cross": CROSS_PRIOR}
    res["P3.2"] = {"subjects": CROSS,
                   "without_cross": walk(recs, is_core, cross_subj, base_models, prior),
                   "with_cross": walk(recs, is_core, cross_subj, base_models + ["cross"], prior_x),
                   "cross_alone": walk(recs, cross_subj, cross_subj, ["cross"], {"cross": 1.0})}
    g_t = ["SPY", "QQQ", "NVDA", "MSFT", "GOOGL", "TSM", "AVGO", "MU", "VNM", "EWJ", "INDA", "FXI", "GLDM", "IAU", "GDX"]
    t_t = ["KBANK.BK", "BBL.BK", "KTB.BK", "TTB.BK", "SCB.BK", "PTT.BK", "PTTEP.BK", "TOP.BK", "IRPC.BK", "AOT.BK", "BAFS.BK", "ADVANC.BK", SET_PROXY]
    pxg = await asyncio.to_thread(download_closes, g_t, None, "10y", 3600)
    pxt = await asyncio.to_thread(download_closes, t_t, None, "10y", 3600)
    res["P3.3"] = await asyncio.to_thread(p33_signals, pxg, pxt)
    res["P3.4"] = await p34_sentiment(pool, closes)
    res["P3.5"] = await p35_macro(pool)
    out = ROOT / "data" / "backtests" / f"p3_{datetime.now():%Y%m%d_%H%M}.json"
    out.write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps(res, indent=1, default=str))
    print("saved", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
