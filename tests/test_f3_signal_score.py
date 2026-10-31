from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "portfolio_engine"), str(ROOT / "ops")]

import signals as live  # noqa: E402
from signal_score import (BASE_WEIGHTS, REGIME_TILT, composite_score,  # noqa: E402
                          cross_section_scores, price_components)


def _series(seed: int, periods: int = 340) -> pd.Series:
    rng = np.random.RandomState(seed)
    returns = rng.normal(0.0004 + seed * 0.00002, 0.009 + seed * 0.0002, periods)
    index = pd.bdate_range("2024-01-02", periods=periods)
    return pd.Series(100 * np.exp(np.cumsum(returns)), index=index)


class PointInTimeTests(unittest.TestCase):
    def test_future_rows_do_not_change_components_or_cross_section(self) -> None:
        closes = pd.DataFrame({"A": _series(1), "B": _series(2), "C": _series(3), "D": _series(4)})
        bench = _series(8)
        volumes = pd.DataFrame({
            ticker: pd.Series(np.linspace(1_000_000, 1_500_000 + i * 50_000, len(closes)), index=closes.index)
            for i, ticker in enumerate(closes.columns)
        })
        asof = closes.index[289]
        raw_before = price_components(closes["A"], volumes["A"], bench, asof)
        scores_before = cross_section_scores(closes, volumes, bench, asof, "risk_on", live.VALIDATED_COMPONENTS)

        changed_closes = closes.copy()
        changed_volumes = volumes.copy()
        changed_bench = bench.copy()
        changed_closes.loc[changed_closes.index > asof] *= 1000
        changed_volumes.loc[changed_volumes.index > asof] *= 500
        changed_bench.loc[changed_bench.index > asof] /= 100
        raw_after = price_components(changed_closes["A"], changed_volumes["A"], changed_bench, asof)
        scores_after = cross_section_scores(
            changed_closes, changed_volumes, changed_bench, asof, "risk_on", live.VALIDATED_COMPONENTS
        )

        self.assertEqual(raw_before, raw_after)
        pd.testing.assert_series_equal(scores_before, scores_after)

    def test_missing_volume_is_missing_not_zero_and_score_survives(self) -> None:
        closes = pd.DataFrame({"A": _series(1), "B": _series(2), "C": _series(3)})
        bench = _series(9)
        asof = closes.index[-1]
        raw = price_components(closes["A"], None, bench, asof)
        self.assertNotIn("volume_confirm", raw)
        self.assertNotIn("volume_ratio_20_60", raw)
        scores = cross_section_scores(closes, None, bench, asof, "neutral", live.VALIDATED_COMPONENTS)
        self.assertEqual(int(scores.notna().sum()), 3)


class CompositeTests(unittest.TestCase):
    def test_regime_tilt_is_applied_before_available_weight_normalization(self) -> None:
        components = {"momentum": 100.0, "low_vol": 0.0}
        allowed = {"momentum", "low_vol"}
        self.assertAlmostEqual(composite_score(components, "neutral", allowed), 60.0)
        self.assertAlmostEqual(composite_score(components, "risk_on", allowed), 80.0)
        self.assertAlmostEqual(composite_score(components, "risk_off", allowed), 40.0)

    def test_default_off_live_score_matches_frozen_formula(self) -> None:
        close = _series(5)
        bench = _series(6)
        volume = pd.Series(np.linspace(900_000, 1_300_000, len(close)), index=close.index)
        # Also lock the old public raw-metric entry point to the new shared implementation.
        self.assertEqual(live._price_metrics(close, volume, bench),
                         price_components(close, volume, bench, close.index[-1]))

        components = {"momentum": 71.2, "low_vol": 42.6, "technical": 63.4,
                      "value": 99.0, "quality": None}
        weights = dict(BASE_WEIGHTS)
        for key, delta in REGIME_TILT["risk_off"].items():
            weights[key] = max(0.0, weights[key] + delta)
        total = sum(weights.values())
        weights = {key: value / total for key, value in weights.items()}
        available = {key: value for key, value in components.items()
                     if value is not None and key in live.VALIDATED_COMPONENTS}
        old_score = sum(weights[key] * value for key, value in available.items()) / sum(
            weights[key] for key in available
        )
        with patch.object(live, "UNIFIED_SCORE_LIVE", False):
            actual = live._live_composite_score(components, "risk_off", weights)
        self.assertAlmostEqual(actual, old_score)
        with patch.object(live, "UNIFIED_SCORE_LIVE", True):
            unified = live._live_composite_score(components, "risk_off", weights)
        self.assertAlmostEqual(unified, old_score)


if __name__ == "__main__":
    unittest.main()
