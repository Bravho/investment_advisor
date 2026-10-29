"""FX cost & risk tool for a THB-based investor."""
from __future__ import annotations

from ..config import BASE_CURRENCY
from ..core.provenance import Investment


def compute_fx(inv: Investment) -> dict:
    cur = (inv.currency or "").upper()
    asset = inv.asset_class
    if asset == "Gold Fund":
        level, score, note = "Med", 2, "THB-quoted but tracks USD gold — partial FX exposure"
    elif cur and cur != BASE_CURRENCY:
        level, score, note = "High", 3, f"{cur} asset for a {BASE_CURRENCY} investor — FX cost on entry/exit"
    else:
        level, score, note = "Low", 1, f"{BASE_CURRENCY}-denominated — negligible FX exposure"
    inv.add_value("FX risk", level, source_name="fx.py", period="model", note=note)
    return {"level": level, "score": score, "note": note}
