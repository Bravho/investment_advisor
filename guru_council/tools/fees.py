"""Deterministic fee / cost-of-ownership tool (medium-term hold lens)."""
from __future__ import annotations

from ..core.provenance import Investment

# SET round-trip cost estimate (brokerage + VAT + exchange/clearing)
SET_ROUNDTRIP_PCT = 0.18


def compute_fees(inv: Investment) -> dict:
    asset = inv.asset_class
    if asset in ("Fund", "Gold Fund"):
        ter = inv.get("TER")
        drag = float(ter) if isinstance(ter, (int, float)) else None
        display = f"{drag:.2f}% p.a." if drag is not None else "n/a"
        numeric = drag if drag is not None else -1
    elif asset.startswith("SET"):
        drag = SET_ROUNDTRIP_PCT
        display = f"~{drag:.2f}% round-trip"
        numeric = drag
    else:  # US / other equities
        drag = None
        display = "broker comm. (varies)"
        numeric = 0.0
    inv.add_value("Cost drag", display, source_name="fees.py", period="model")
    return {"display": display, "annual_pct": numeric}
