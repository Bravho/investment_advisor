"""Macro & Technology-Trends Analyst — sector growth & backdrop vs peers."""
from __future__ import annotations

from .base import CouncilAnalyst


class MacroTrendsAnalyst(CouncilAnalyst):
    name = "Macro & Tech-Trends"
    lens = "rates · cycle · sector growth vs peers"
    relevant = ["Revenue growth", "News sentiment", "Drawdown"]
    peer_metrics = {"Revenue growth": "high"}
    guidance = (
        "Reward names growing faster than peers into a supportive macro/sector trend "
        "(rates, cycle, technology adoption); penalize laggards or names facing a sector "
        "headwind even if they screen cheap."
    )
