from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "portfolio_engine"), str(ROOT / "ops")]

from advice_policy import OWNER_HOLD_NOTE, apply_owner_hold_policy  # noqa: E402
from backtest_gate import gate  # noqa: E402
from backtesting import first_close_on_or_after  # noqa: E402
from portfolio_construction import _core_proxy_target_value  # noqa: E402


class OwnerHoldPolicyTests(unittest.TestCase):
    def test_owner_hold_aliases_block_reduce_actions(self) -> None:
        for ticker in ("PTTEP", "PTTEP.BK", "SCB.BK"):
            with self.subTest(ticker=ticker):
                action, payload = apply_owner_hold_policy(ticker, "ReViEw_ReDuCe", {"existing": 1})
                self.assertEqual(action, "info_risk_alert")
                self.assertFalse(payload["actionable"])
                self.assertEqual(payload["note"], OWNER_HOLD_NOTE)
                self.assertEqual(payload["existing"], 1)

    def test_non_owner_is_unchanged(self) -> None:
        original = {"actionable": True}
        action, payload = apply_owner_hold_policy("AOT.BK", "trim", original)
        self.assertEqual(action, "trim")
        self.assertIs(payload, original)


class BacktestGateTests(unittest.TestCase):
    def test_gate_passes_only_with_better_skill_and_allowed_hit_drop(self) -> None:
        baseline = {"1m": {"skill": 0.10, "hit": 0.60}, "3m": {"skill": 0.20, "hit": 0.58}}
        candidate = {"1m": {"skill": 0.14, "hit": 0.59}, "3m": {"skill": 0.22, "hit": 0.58}}
        verdict = gate(baseline, candidate)
        self.assertTrue(verdict["pass"])

    def test_gate_fails_on_skill_or_hit(self) -> None:
        baseline = {"1m": {"skill": 0.10, "hit": 0.60}, "3m": {"skill": 0.20, "hit": 0.60}}
        no_skill = {"1m": {"skill": 0.09, "hit": 0.61}, "3m": {"skill": 0.19, "hit": 0.61}}
        low_hit = {"1m": {"skill": 0.20, "hit": 0.57}, "3m": {"skill": 0.30, "hit": 0.58}}
        self.assertFalse(gate(baseline, no_skill)["pass"])
        self.assertFalse(gate(baseline, low_hit)["pass"])


class ConstructionInvariantTests(unittest.TestCase):
    def test_in_band_global_proxy_keeps_current_value(self) -> None:
        current = {"SPY": {"value_thb": 123456.0}}
        target = _core_proxy_target_value("SPY", 30.0, 1_000_000.0, [], current)
        self.assertEqual(target, 123456.0)

    def test_out_of_band_global_proxy_uses_target(self) -> None:
        current = {"SPY": {"value_thb": 123456.0}}
        target = _core_proxy_target_value("SPY", 30.0, 1_000_000.0, ["global_equity"], current)
        self.assertEqual(target, 300000.0)


class BacktestingTargetDateTests(unittest.TestCase):
    def test_selects_first_close_on_or_after_target(self) -> None:
        rows = [
            {"price_date": date(2026, 1, 12), "close_price": 102.0},
            {"price_date": date(2026, 1, 9), "close_price": 101.0},
            {"price_date": date(2026, 1, 8), "close_price": 99.0},
        ]
        selected = first_close_on_or_after(rows, date(2026, 1, 9))
        self.assertEqual(selected["price_date"], date(2026, 1, 9))
        self.assertEqual(selected["close_price"], 101.0)


if __name__ == "__main__":
    unittest.main()
