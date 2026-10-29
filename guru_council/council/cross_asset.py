"""Cross-Asset / Commodity-Linkage Analyst — inter-market positioning vs peers."""
from __future__ import annotations

from .base import CouncilAnalyst


class CrossAssetAnalyst(CouncilAnalyst):
    name = "Cross-Asset Linkage"
    lens = "commodity / FX / rate linkages vs peers"
    relevant = ["FX risk", "Repatriation drag", "Brent", "Gold spot", "Jet fuel", "Dividend yield", "Drawdown"]
    peer_metrics = {"Dividend yield": "high"}
    guidance = (
        "Judge how favorably this name's commodity/FX/rate sensitivities are positioned "
        "right now relative to its peers — lower FX friction for a THB investor and a "
        "supportive commodity/rate linkage should score better than peers exposed the wrong way. "
        "Penalize a high repatriation drag (cross-border tax + FX cost to bring money back to Thailand)."
    )
