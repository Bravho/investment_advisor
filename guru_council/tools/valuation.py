"""Deterministic valuation tool.

A transparent, explainable fair-value estimate the analysts call rather than
guessing math. Uses a conservative multiple-reversion (documented assumptions);
swap in a full multi-stage DCF here later without changing callers.
"""
from __future__ import annotations

from ..core.provenance import Investment

# conservative "fair" earnings multiple by asset class
FAIR_PE = {
    "US Equity": 30.0,
    "SET Equity": 12.0,
    "SET Bank": 9.0,
    "SET Energy": 9.0,
    "SET Aviation": 15.0,
}


def compute_valuation(inv: Investment) -> dict:
    pe = inv.get("P/E")
    price = inv.price
    if not isinstance(pe, (int, float)) or pe <= 0 or not price:
        return {"available": False}
    eps = price / pe
    fair_pe = FAIR_PE.get(inv.asset_class, 15.0)
    fair_value = fair_pe * eps
    upside = (fair_value - price) / price * 100.0
    inv.add_value(
        "Fair value (model)",
        round(fair_value, 2),
        unit=inv.currency,
        source_name="valuation.py",
        period="model",
        note=f"conservative {fair_pe:g}× EPS reversion",
    )
    inv.add_value(
        "Upside to fair value",
        round(upside, 1),
        unit="%",
        source_name="valuation.py",
        period="model",
    )
    return {"available": True, "fair_value": round(fair_value, 2), "upside_pct": round(upside, 1), "fair_pe": fair_pe}
