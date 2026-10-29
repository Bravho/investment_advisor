"""Value Analyst — Buffett-style valuation & quality, ranked vs peers."""
from __future__ import annotations

from ..core.provenance import Investment
from .base import CouncilAnalyst


class ValueAnalyst(CouncilAnalyst):
    name = "Value Analyst"
    lens = "Buffett-style · valuation & quality vs peers"
    relevant = ["P/E", "ROE", "ROIC", "FCF yield", "Dividend yield",
                "Debt/Equity", "Upside to fair value"]
    peer_metrics = {"P/E": "low", "FCF yield": "high", "ROE": "high", "Dividend yield": "high"}
    guidance = (
        "Favor the cheapest, highest-return-on-capital name with the strongest free cash "
        "flow in the peer group. Reward a genuine margin of safety vs peers."
    )

    def applicable(self, inv: Investment) -> bool:
        # need an earnings multiple to value (funds/commodities excluded)
        return inv.has("P/E")
