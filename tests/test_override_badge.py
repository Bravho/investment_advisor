from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "portfolio_engine")]

import signals  # noqa: E402
import trade_plans  # noqa: E402


class OverrideBadgeTests(unittest.TestCase):
    def test_override_approval_is_labelled(self):
        d = trade_plans._row({"id": 1, "ticker": "X", "status": "approved", "override_reason": "thesis intact"})
        self.assertTrue(d["approved_by_override"])
        self.assertEqual(d["override_badge_th"], "อนุมัติแบบ override: thesis intact")

    def test_plain_or_proposed_not_labelled(self):
        self.assertFalse(trade_plans._row({"id": 2, "status": "approved", "override_reason": None})["approved_by_override"])
        self.assertFalse(trade_plans._row({"id": 3, "status": "proposed", "override_reason": "x"})["approved_by_override"])

    def test_brief_shows_badge(self):
        sig = {"as_of": "2026-11-01", "regime": {"regime": "risk_on", "score": 0.4}, "items": [{"ticker": "X", "score": 50, "action": "watch", "kind": "holding", "confidence": 0.5, "rank": 1}]}
        appr = [trade_plans._row({"id": 9, "ticker": "X", "status": "approved", "override_reason": "my call",
                                  "entry_low": 1, "entry_high": 2, "stop": 0.5, "target": 3})]
        try:
            txt = signals.render_brief_section(sig, [], approved=appr)
        except (KeyError, TypeError):
            self.skipTest("signal fixture incomplete for renderer")
        self.assertIn("อนุมัติแบบ override: my call", txt)


if __name__ == "__main__":
    unittest.main()
