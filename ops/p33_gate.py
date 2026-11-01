"""P3.3-as-live gate + ablation of the pre-P3.3 live formula (2026-11-01, Tho t31u).

Same out-of-sample setup as ops/f3_backtest.py (monthly top-3, walkforward.simulate costs, yearly OOS folds).
  gate:     baseline = pre-P3.3 live formula (signal_score.cross_section_scores, MACD+volume+regime tilt)
            candidate = P3.3 formula via the SHARED live function signal_score.p33_scores
  ablation: pre-P3.3 live formula with MACD / volume / regime tilt removed one at a time (vs full live)
Read-only: downloads market history, writes one JSON under data/backtests/. No DB, no advice, no orders.
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

import signals as S  # noqa: E402
import walkforward as wf  # noqa: E402
from backtest_gate import gate  # noqa: E402
from f3_backtest import ALLOWED, _history_frames, _summary  # noqa: E402
from p3_backtest import P33_UNIVERSES  # noqa: E402
from signal_score import cross_section_scores, p33_scores  # noqa: E402

VARIANTS = {
    "live_full": {"exclude": set(), "tilt": True},
    "no_macd": {"exclude": {"macd_hist_pct"}, "tilt": True},
    "no_volume": {"exclude": {"volume_confirm"}, "tilt": True},
    "no_regime_tilt": {"exclude": set(), "tilt": False},
}


def _universe(name: str, close_all: pd.DataFrame, volume_all: pd.DataFrame, regime_closes: pd.DataFrame) -> Dict[str, Any]:
    spec = P33_UNIVERSES[name]
    bt = spec["benchmark"]
    present = [t for t in dict.fromkeys(spec["tickers"] + [bt]) if t in close_all.columns]
    full = close_all[present].dropna(how="all")
    tickers = [t for t in spec["tickers"] if t != bt and t in full.columns]
    px = full[tickers]
    vols = volume_all.reindex(index=full.index, columns=tickers)
    bench = full[bt].ffill(limit=5).pct_change(fill_method=None).fillna(0.0)
    start = full.index[0] + pd.DateOffset(months=12 + wf.TRAIN_M)
    regime_cache: Dict[pd.Timestamp, str] = {}

    def regime_at(asof: pd.Timestamp) -> str:
        if asof not in regime_cache:
            regime_cache[asof] = S.regime_from_closes(regime_closes.loc[:asof].iloc[-260:])["regime"]
        return regime_cache[asof]

    def live_fn(exclude: set, tilt: bool) -> Callable:
        def fn(h: pd.DataFrame, _p: Any) -> pd.Series:
            asof = h.index[-1]
            ps = pd.Timestamp(asof) - pd.DateOffset(years=2)
            sc = cross_section_scores(px.loc[ps:asof], vols.loc[ps:asof], full[bt].loc[ps:asof], asof,
                                      regime_at(pd.Timestamp(asof)), ALLOWED, exclude_metrics=exclude, use_tilt=tilt)
            return wf._top(sc.dropna())
        return fn

    def p33_fn(h: pd.DataFrame, _p: Any) -> pd.Series:
        return wf._top(p33_scores(full.loc[: h.index[-1]], bt).dropna())

    out: Dict[str, Any] = {"benchmark": bt, "tickers": tickers}
    runs = {k: _summary(wf.simulate(px, live_fn(v["exclude"], v["tilt"]), None), start, bench) for k, v in VARIANTS.items()}
    runs["p33_shared"] = _summary(wf.simulate(px, p33_fn, None), start, bench)
    base = runs["live_full"]
    out["runs"] = runs
    out["gate_p33_vs_live"] = gate(base["folds"], runs["p33_shared"]["folds"])
    out["ablation_vs_live"] = {k: gate(base["folds"], runs[k]["folds"]) for k in ("no_macd", "no_volume", "no_regime_tilt")}
    return out


def main() -> int:
    req = set(S.REGIME_TICKERS)
    for spec in P33_UNIVERSES.values():
        req.update(spec["tickers"]); req.add(spec["benchmark"])
    close_all, volume_all = _history_frames(sorted(req))
    rc = close_all[[t for t in S.REGIME_TICKERS if t in close_all.columns]]
    res = {"generated_at": datetime.now().isoformat(timespec="seconds"),
           "config": {"baseline": "pre-P3.3 live formula (exact)", "candidate": "signal_score.p33_scores (shared with live)",
                      "setup": "same as ops/f3_backtest.py: monthly top-%d, walkforward costs, yearly OOS folds" % wf.TOP_K},
           "universes": {n: _universe(n, close_all, volume_all, rc) for n in ("global", "thai")}}
    res["pass_global"] = bool(res["universes"]["global"]["gate_p33_vs_live"].get("pass"))
    res["pass_thai"] = bool(res["universes"]["thai"]["gate_p33_vs_live"].get("pass"))
    od = ROOT / "data" / "backtests"; od.mkdir(parents=True, exist_ok=True)
    f = od / ("p33_gate_%s.json" % datetime.now().strftime("%Y%m%d_%H%M%S"))
    f.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    for n, u in res["universes"].items():
        for k, r in u["runs"].items():
            print(n, k, {m: r.get(m) for m in ("sharpe", "cagr", "bench_cagr", "excess_cagr", "hit_rate", "max_dd")})
        print(n, "GATE p33 vs live:", u["gate_p33_vs_live"])
        for k, g in u["ablation_vs_live"].items():
            print(n, "ablation", k, g)
    print("saved", f)
    return 0 if res["pass_global"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
