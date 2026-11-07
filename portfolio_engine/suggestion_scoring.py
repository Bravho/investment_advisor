"""Benchmark-relative scoring for past recommendations (pure functions, no DB access).

Why this exists (lessons from the June-November 2026 audit, see docs/lessons/suggestion_audit_20261107.md):
  * review_buy / review_reduce were missing from the scoring sets, so every one was marked wrong.
  * A missing price was stored as 0.0 and scored as a 0% return.
  * Rows priced 3+ weeks after the intended 7-day window were scored with a stale price.
  * Raw return sign ignores the market: a +1% stock in a +3% market counted as a win.
  * Repeated identical recommendations inflated the sample about 13x.

This module fixes those in one place. The live evaluator in backtesting.py is NOT
switched to it yet; that needs the user's approval.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

BULLISH = frozenset({"buy", "accumulate", "review_buy"})
BEARISH = frozenset({"sell", "reduce", "review_reduce", "stop_loss"})
HOLD = frozenset({"hold"})
NEUTRAL = frozenset({"watch"})  # no position taken: tracked for missed moves, never scored as hit/miss

HOLD_BAND_PCT = 2.0  # "hold" is correct if the excess move stays inside +/-2%
DEFAULT_HORIZON_DAYS = 7
MAX_LATE_DAYS = 3  # a price more than 3 days after the target window is treated as stale


@dataclass(frozen=True)
class Score:
    status: str  # directional | excluded_neutral | no_price | stale_window | unknown_action
    scored: bool
    was_correct: Optional[bool]
    excess_pct: Optional[float]


def dedupe_key(ticker: str, action: str, created: date) -> tuple[str, str, date]:
    """Same ticker, same action, same day = one suggestion."""
    return (str(ticker or "").upper(), str(action or "").lower(), created)


def score_recommendation(
    action: str,
    stock_ret_pct: Optional[float],
    bench_ret_pct: Optional[float],
    price_at_review: Optional[float],
    days_held: Optional[int],
    horizon_days: int = DEFAULT_HORIZON_DAYS,
) -> Score:
    act = str(action or "").lower()
    if act in NEUTRAL:
        return Score("excluded_neutral", False, None, None)
    if act not in BULLISH | BEARISH | HOLD:
        return Score("unknown_action", False, None, None)
    if price_at_review is None or price_at_review <= 0 or stock_ret_pct is None or bench_ret_pct is None:
        return Score("no_price", False, None, None)
    if days_held is not None and days_held > horizon_days + MAX_LATE_DAYS:
        return Score("stale_window", False, None, None)

    excess = float(stock_ret_pct) - float(bench_ret_pct)
    if act in BULLISH:
        correct = excess > 0
    elif act in BEARISH:
        correct = excess < 0
    else:
        correct = abs(excess) < HOLD_BAND_PCT
    return Score("directional", True, correct, round(excess, 4))
