from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "portfolio_engine"), str(ROOT / "ops")]

import signals as S  # noqa: E402
import walkforward as wf  # noqa: E402
from signal_score import cross_section_scores, p33_scores  # noqa: E402


def frozen_p33(h: pd.DataFrame, bench_col: str) -> pd.Series:
    """Verbatim copy of the pre-2026-11-01 ops/p3_backtest.p33_composite_weights scoring (before top-k)."""
    BW = S.BASE_WEIGHTS
    wm, wl, wt = BW["momentum"], BW["low_vol"], BW["technical"]
    hh = h.drop(columns=[bench_col], errors="ignore")
    r = hh.pct_change(fill_method=None)
    bench = h[bench_col]
    mom = pd.concat([(hh.iloc[-22] / hh.iloc[-252] - 1).rank(pct=True),
                     (hh.iloc[-1] / hh.iloc[-126] - 1).rank(pct=True)], axis=1).mean(axis=1)
    vol = (r.iloc[-252:].std()).rank(pct=True, ascending=False)
    br = bench.pct_change(fill_method=None).iloc[-252:]
    beta = r.iloc[-252:].apply(lambda c: c.cov(br) / br.var() if br.var() > 0 else np.nan)
    vol = pd.concat([vol, beta.rank(pct=True, ascending=False)], axis=1).mean(axis=1)
    trend = hh.iloc[-1] / hh.iloc[-200:].mean() - 1
    rs3 = (hh.iloc[-1] / hh.iloc[-63] - 1) - (bench.iloc[-1] / bench.iloc[-63] - 1)
    rsi = wf._rsi_frame(hh.iloc[-120:]).iloc[-1]
    rsi_sc = rsi.apply(lambda x: S._rsi_score(float(x)) if pd.notna(x) else np.nan)
    tech = pd.concat([trend.rank(pct=True), rs3.rank(pct=True), rsi_sc.rank(pct=True)], axis=1).mean(axis=1)
    score = (wm * mom + wl * vol + wt * tech) / (wm + wl + wt)
    ok = hh.iloc[-252:].notna().sum() >= 230
    return score[ok].dropna()


def _frame(n: int = 400, k: int = 6, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2024-01-01", periods=n)
    data = {f"T{i}": 100 * np.exp(np.cumsum(rng.normal(0.0004 * i, 0.01 + 0.002 * i, n))) for i in range(k)}
    data["B"] = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.009, n)))
    return pd.DataFrame(data, index=idx)


class P33LiveTests(unittest.TestCase):
    def test_shared_equals_frozen(self):
        h = _frame()
        new = p33_scores(h, "B").dropna() / 100
        old = frozen_p33(h, "B")
        pd.testing.assert_series_equal(new.sort_index(), old.sort_index(), check_names=False, atol=1e-12)

    def test_short_history_not_scored(self):
        h = _frame()
        h.iloc[-100:, 0] = np.nan
        self.assertTrue(np.isnan(p33_scores(h, "B")["T0"]))

    def test_live_flag_is_p33(self):
        self.assertEqual(S.LIVE_FORMULA, "p33")

    def test_ablation_defaults_unchanged(self):
        h = _frame()
        a = cross_section_scores(h.drop(columns=["B"]), None, h["B"], h.index[-1], "risk_on", {"momentum", "low_vol", "technical"})
        b = cross_section_scores(h.drop(columns=["B"]), None, h["B"], h.index[-1], "risk_on", {"momentum", "low_vol", "technical"},
                                 exclude_metrics=set(), use_tilt=True)
        pd.testing.assert_series_equal(a, b)


if __name__ == "__main__":
    unittest.main()
