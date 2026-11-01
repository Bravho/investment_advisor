"""Earnings-aware forecast bands - walk-forward gate (2026-11-01, Tho t39u, INTC lesson).

Question: our price forecasts use a volatility sigma that ignores scheduled earnings.  Do bands that
widen when an earnings reaction day falls inside the horizon forecast better?
Design: the live forecast models (predictions.model_outputs + combine, PRIOR_W, no regime/signal inputs)
re-run point-in-time every 5 trading days for the US single stocks on the watch list, horizons 3d and 1m.
  baseline : live sigma
  candidate: sigma x m_h when a company-published earnings date reacts inside (as-of, as-of+h]
m_h is fitted ONLY on as-of dates before 2022-01-01 (ratio of 80th-pct |z| in earnings windows vs normal
windows); everything from 2022-01-01 is out-of-sample.  Scored with the same skill/hit definition as
ops/codex_gate_backtest.py and gated with ops/backtest_gate.py; band-coverage is reported alongside.
Read-only: no DB writes, no advice, no orders.
"""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "portfolio_engine"), str(ROOT / "ops")]

import predictions as P  # noqa: E402
import earnings_risk as ER  # noqa: E402
from backtest_gate import gate  # noqa: E402
from market_history import download_closes  # noqa: E402

TICKERS = ["NVDA", "MSFT", "GOOGL", "TSM", "AVGO", "MU"]
HZ = {"3d": 3, "1m": 21}
SPLIT = pd.Timestamp("2022-01-01")


def main() -> int:
    px = download_closes(TICKERS, None, "10y", 3600)
    dates = ER.fetch_dates(TICKERS)
    rows = []
    for t in TICKERS:
        s = px[t].dropna()
        lp = np.log(s)
        idx = s.index
        rds = sorted({d for d in (ER.reaction_day(e["ts"], idx) for e in dates[t]["events"]) if d is not None})
        for i in range(300, len(idx) - 22, 5):
            asof = idx[i]
            for hn, h in HZ.items():
                if i + h >= len(idx):
                    continue
                mo = P.model_outputs(lp.iloc[: i + 1], h, {"regime": None, "beta": 1.0})
                if "error" in mo:
                    continue
                c = P.combine(mo, P.PRIOR_W, float(s.iloc[i]), h)
                ev = any(asof < d <= idx[i + h] for d in rds)
                rows.append({"t": t, "d": asof, "h": hn, "mu": c["mu"], "sigma": c["sigma"], "ev": ev,
                             "actual": float(lp.iloc[i + h] - lp.iloc[i])})
    df = pd.DataFrame(rows)
    df["z"] = (df.actual - df.mu) / df.sigma
    q80 = P.tq(0.90)
    mult = {}
    for hn in HZ:
        ins = df[(df.h == hn) & (df.d < SPLIT)]
        mult[hn] = round(float(np.quantile(ins[ins.ev].z.abs(), 0.8) / np.quantile(ins[~ins.ev].z.abs(), 0.8)), 3)
    oos = df[df.d >= SPLIT].copy()
    oos["sigma_c"] = oos.apply(lambda r: r.sigma * (mult[r.h] if r.ev else 1.0), axis=1)

    def score(col: str) -> dict:
        out = {}
        for hn, g in oos.groupby("h"):
            err = (((g.actual - g.mu) / g[col]) ** 2).sum()
            base = ((g.actual / g[col]) ** 2).sum()
            dirs = [(m > 0) == (a > 0) for m, a in zip(g.mu, g.actual) if abs(m) > 1e-9]
            cov = (((g.actual - g.mu) / g[col]).abs() <= q80)
            out[hn] = {"n": int(len(g)), "skill": float(1 - err / base), "hit": float(np.mean(dirs)),
                       "cov80_all": round(float(cov.mean()), 3), "cov80_earnings_windows": round(float(cov[g.ev].mean()), 3),
                       "cov80_normal_windows": round(float(cov[~g.ev].mean()), 3), "n_earnings_windows": int(g.ev.sum())}
        return out

    base, cand = score("sigma"), score("sigma_c")
    verdict = gate(base, cand)
    res = {"generated_at": datetime.now().isoformat(timespec="seconds"), "tickers": TICKERS,
           "multipliers_fit_pre2022": mult, "oos_from": str(SPLIT.date()), "baseline": base, "candidate": cand,
           "verdict": verdict, "design": __doc__.strip().splitlines()[0]}
    f = ROOT / "data" / "backtests" / f"earnings_band_gate_{datetime.now():%Y%m%d_%H%M%S}.json"
    f.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    print(json.dumps(res, indent=2, default=str))
    print("saved", f)
    return 0 if verdict["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
