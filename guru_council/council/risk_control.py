"""Risk & Control Analyst — Taleb-style fragility/leverage, ranked vs peers."""
from __future__ import annotations

from .base import CouncilAnalyst


class RiskControlAnalyst(CouncilAnalyst):
    name = "Risk & Control"
    lens = "fragility / tail risk / leverage vs peers"
    relevant = ["P/E", "Debt/Equity", "Drawdown", "FX risk", "Repatriation drag", "Dividend yield", "Market cap"]
    peer_metrics = {"Debt/Equity": "low", "P/E": "low"}
    guidance = (
        "Reward lower leverage, lower valuation fragility and larger/more liquid names "
        "relative to peers; flag the most fragile name in the group. Be conservative — "
        "rarely the most enthusiastic voice."
    )
