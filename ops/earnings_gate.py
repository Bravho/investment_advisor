"""Earnings-event overlays on the live P3.3 signal - walk-forward gate (2026-11-01, Tho t39u, INTC lesson).

Same OOS setup as ops/p33_gate.py / ops/f3_backtest.py (monthly top-3, walkforward costs, yearly folds,
skill = net excess return vs benchmark, hit = positive-month rate), global universe (Thai names have no
free historical earnings dates).  Baseline = signal_score.p33_scores (live).  Candidates:
  pre_excl_10d : skip a name whose earnings reaction day falls in the first 10 trading days after the signal
  pre_excl_month: skip a name with earnings anywhere in the coming ~month (22 trading days)
  haircut_month: keep it but at half weight (other half in cash) if earnings fall inside the coming month
  post_gap_block: skip a name whose last earnings reaction (within 20 trading days) was <= -7%
Earnings dates are company-published in advance (yfinance get_earnings_dates), so using the next date is
not look-ahead; the post-gap rule only uses past reactions.  Read-only: no DB, no advice, no orders.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "portfolio_engine"), str(ROOT / "ops")]

import walkforward as wf  # noqa: E402
from backtest_gate import gate  # noqa: E402
from f3_backtest import _history_frames, _summary  # noqa: E402
from p3_backtest import P33_UNIVERSES  # noqa: E402
from signal_score import p33_scores  # noqa: E402
import earnings_risk as ER  # noqa: E402


def main() -> int:
    spec = P33_UNIVERSES["global"]
    bt = spec["benchmark"]
    close_all, _ = _history_frames(sorted(set(spec["tickers"] + [bt])))
    full = close_all[[t for t in dict.fromkeys(spec["tickers"] + [bt]) if t in close_all.columns]].dropna(how="all")
    tickers = [t for t in spec["tickers"] if t != bt and t in full.columns]
    px = full[tickers]
    idx = full.index
    bench = full[bt].ffill(limit=5).pct_change(fill_method=None).fillna(0.0)
    start = idx[0] + pd.DateOffset(months=12 + wf.TRAIN_M)

    dates = ER.fetch_dates(tickers)
    react: Dict[str, list] = {}
    moves: Dict[str, list] = {}
    for t, rec in dates.items():
        evs = [e for e in rec.get("events") or []]
        rds = sorted({d for d in (ER.reaction_day(e["ts"], idx) for e in evs) if d is not None})
        if rds:
            react[t] = rds
        moves[t] = ER.reaction_moves(evs, full[t]) if t in full.columns else []
    covered = sorted(react)

    def next_react_td(t: str, asof: pd.Timestamp) -> int | None:
        i0 = idx.get_loc(asof)
        for d in react.get(t, []):
            if d > asof:
                return idx.get_loc(d) - i0
        return None

    def last_gap(t: str, asof: pd.Timestamp) -> bool:
        i0 = idx.get_loc(asof)
        past = [m for m in moves.get(t, []) if pd.Timestamp(m["reaction_day"]) <= asof]
        if not past:
            return False
        m = past[-1]
        return m["move_pct"] <= -ER.BIG_GAP_PCT and i0 - idx.get_loc(pd.Timestamp(m["reaction_day"])) <= 20

    def scores(h: pd.DataFrame) -> pd.Series:
        return p33_scores(full.loc[: h.index[-1]], bt).dropna()

    def base_fn(h, _p):
        return wf._top(scores(h))

    def excl(window: int) -> Callable:
        def fn(h, _p):
            asof = h.index[-1]
            s = scores(h)
            keep = [t for t in s.index if not ((n := next_react_td(t, asof)) is not None and n <= window + 1)]
            return wf._top(s.loc[keep])
        return fn

    def haircut(h, _p):
        asof = h.index[-1]
        w = wf._top(scores(h))
        for t in w.index:
            n = next_react_td(t, asof)
            if n is not None and n <= 23:
                w[t] = w[t] * 0.5
        return w

    def post_gap(h, _p):
        asof = h.index[-1]
        s = scores(h)
        return wf._top(s.loc[[t for t in s.index if not last_gap(t, asof)]])

    variants = {"pre_excl_10d": excl(10), "pre_excl_month": excl(22), "haircut_month": haircut, "post_gap_block": post_gap}
    runs = {"baseline_p33": _summary(wf.simulate(px, base_fn, None), start, bench)}
    for k, fn in variants.items():
        runs[k] = _summary(wf.simulate(px, fn, None), start, bench)
    gates = {k: gate(runs["baseline_p33"]["folds"], runs[k]["folds"]) for k in variants}
    res = {"generated_at": datetime.now().isoformat(timespec="seconds"), "benchmark": bt, "tickers": tickers,
           "earnings_covered": covered, "config": __doc__.strip().splitlines()[0],
           "runs": runs, "gates": gates, "any_pass": any(g["pass"] for g in gates.values())}
    od = ROOT / "data" / "backtests"; od.mkdir(parents=True, exist_ok=True)
    f = od / ("earnings_gate_%s.json" % datetime.now().strftime("%Y%m%d_%H%M%S"))
    f.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    for k, r in runs.items():
        print(k, {m: r.get(m) for m in ("sharpe", "cagr", "excess_cagr", "hit_rate", "max_dd", "n_months", "oos_from")})
    for k, g in gates.items():
        print("GATE", k, json.dumps(g))
    print("covered", covered, "saved", f)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
