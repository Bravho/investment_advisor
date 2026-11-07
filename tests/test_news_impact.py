"""Unit tests for ai_engine/news_impact.py (two-sided news-impact model, shadow only)."""
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "ai_engine")]

import news_impact as NI  # noqa: E402

RULES = NI.load_rules()
WEIGHTS = RULES["decay_weights"]


def test_up_and_down_headlines_are_classified_separately():
    up = NI.classify_headline("Nvidia raises guidance as AI chip demand beats estimates", RULES)
    down = NI.classify_headline("AI chip rules tighten as data-center crackdown spreads", RULES)
    assert any(h["sector"] == "ai_semis" and h["direction"] == 1 for h in up)
    assert any(h["sector"] == "ai_semis" and h["direction"] == -1 for h in down)


def test_conflicting_headline_is_neutral():
    # Matches both UP and DOWN for the same sector -> not counted.
    hits = NI.classify_headline("Stocks rally after rate hike fears", RULES)
    assert not [h for h in hits if h["sector"] == "broad_market"]


def test_unrelated_headline_has_no_signal():
    assert NI.classify_headline("Local bakery opens new branch downtown", RULES) == []


def test_reaction_index_uses_first_trading_day_on_or_after():
    days = [date(2026, 11, 3), date(2026, 11, 4), date(2026, 11, 5)]
    assert NI.reaction_index(days, date(2026, 11, 4)) == 1
    assert NI.reaction_index(days, date(2026, 11, 2)) == 0
    assert NI.reaction_index(days, date(2026, 11, 9)) is None


def test_score_event_signs_returns_by_direction():
    closes3 = [100.0, 100.0, 100.0, 90.0, 90.0, 90.0, 90.0]
    days3 = [date(2026, 11, d) for d in (2, 3, 4, 5, 6, 9, 10)]
    res = NI.score_event(-1, closes3, days3, date(2026, 11, 5), [1.0, 0.5, 0.25])
    assert res is not None
    assert round(res["signed_returns"][0], 4) == 0.1  # a DOWN call on a -10% day is a hit
    assert res["hit_day0"] is True


def test_score_event_returns_none_when_window_incomplete():
    days = [date(2026, 11, 5), date(2026, 11, 6)]
    assert NI.score_event(1, [100.0, 101.0], days, date(2026, 11, 5), WEIGHTS) is None


def test_append_is_append_only(tmp_path):
    path = tmp_path / "shadow.jsonl"
    assert NI.append_shadow_records([{"key": "a"}], path) == 1
    assert NI.append_shadow_records([{"key": "b"}], path) == 1
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2 and '"key": "a"' in lines[0]
