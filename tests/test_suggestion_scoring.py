from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "portfolio_engine")]

from suggestion_scoring import dedupe_key, score_recommendation  # noqa: E402


class SuggestionScoringTests(unittest.TestCase):
    def test_review_buy_and_review_reduce_are_scored(self) -> None:
        up = score_recommendation("review_buy", 3.0, 1.0, 10.0, 7)
        self.assertTrue(up.scored)
        self.assertTrue(up.was_correct)
        down = score_recommendation("review_reduce", -2.0, 1.0, 10.0, 7)
        self.assertTrue(down.scored)
        self.assertTrue(down.was_correct)

    def test_missing_price_is_not_scored_as_zero_return(self) -> None:
        s = score_recommendation("review_buy", 0.0, 0.8, 0.0, 23)
        self.assertFalse(s.scored)
        self.assertEqual(s.status, "no_price")
        self.assertIsNone(s.was_correct)

    def test_stale_window_is_excluded(self) -> None:
        s = score_recommendation("accumulate", 2.0, 1.0, 10.0, 23)
        self.assertFalse(s.scored)
        self.assertEqual(s.status, "stale_window")

    def test_small_lag_is_still_scored(self) -> None:
        s = score_recommendation("accumulate", 2.0, 1.0, 10.0, 9)
        self.assertTrue(s.scored)

    def test_benchmark_relative_win_requires_beating_market(self) -> None:
        # Stock +1%, market +3%: raw sign says win, excess says loss.
        s = score_recommendation("accumulate", 1.0, 3.0, 10.0, 7)
        self.assertTrue(s.scored)
        self.assertFalse(s.was_correct)
        self.assertEqual(s.excess_pct, -2.0)

    def test_reduce_wins_when_stock_lags_market(self) -> None:
        s = score_recommendation("reduce", -1.0, 2.0, 10.0, 7)
        self.assertTrue(s.was_correct)

    def test_watch_is_never_scored_as_hit_or_miss(self) -> None:
        s = score_recommendation("watch", 5.0, 1.0, 10.0, 7)
        self.assertFalse(s.scored)
        self.assertIsNone(s.was_correct)
        self.assertEqual(s.status, "excluded_neutral")

    def test_hold_band(self) -> None:
        self.assertTrue(score_recommendation("hold", 1.0, 0.0, 10.0, 7).was_correct)
        self.assertFalse(score_recommendation("hold", 3.5, 0.0, 10.0, 7).was_correct)

    def test_unknown_action_is_not_guessed(self) -> None:
        s = score_recommendation("strong_buy_maybe", 5.0, 0.0, 10.0, 7)
        self.assertFalse(s.scored)
        self.assertEqual(s.status, "unknown_action")

    def test_dedupe_key_collapses_same_ticker_action_day(self) -> None:
        a = dedupe_key("nvda", "Watch", date(2026, 10, 7))
        b = dedupe_key("NVDA", "watch", date(2026, 10, 7))
        c = dedupe_key("NVDA", "watch", date(2026, 10, 8))
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)


if __name__ == "__main__":
    unittest.main()
