"""Stage 3 — verification: QC rules + provenance enforcement.

Every fact must trace to a source; obviously-wrong values are flagged; required
metrics that are missing are reported explicitly (never invented).
"""
from __future__ import annotations

from ..core.provenance import Investment

# metrics we expect for a given asset class (missing -> explicit flag)
REQUIRED = {
    "US Equity": ["P/E", "ROE", "Dividend yield"],
    "SET Equity": ["P/E", "ROE", "Dividend yield"],
    "SET Bank": ["P/E", "ROE", "Dividend yield"],
    "SET Energy": ["P/E", "ROE", "Dividend yield"],
    "SET Aviation": ["P/E", "ROE", "Dividend yield"],
    "Fund": ["NAV", "TER"],
    "Gold Fund": ["NAV", "TER"],
    "Crypto": ["Market cap"],
}


def verify(inv: Investment) -> Investment:
    # provenance: every fact needs a source
    for metric, fact in inv.facts.items():
        if not fact.source_name:
            inv.flag(f"{metric}: missing source (provenance incomplete)")

    # required-metric presence
    for metric in REQUIRED.get(inv.asset_class, []):
        if not inv.has(metric):
            inv.flag(f"{metric} unavailable — analysis treats it as unconfirmed")

    # sanity checks
    pe = inv.get("P/E")
    if isinstance(pe, (int, float)) and (pe < 0 or pe > 200):
        inv.flag(f"P/E={pe} is out of sane range — verify source")
    dy = inv.get("Dividend yield")
    if isinstance(dy, (int, float)) and dy > 20:
        inv.flag(f"Dividend yield={dy}% implausibly high — verify source")
    de = inv.get("Debt/Equity")
    if isinstance(de, (int, float)) and de < 0:
        inv.flag(f"Debt/Equity={de} negative — verify source")

    return inv
