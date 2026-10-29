"""Repatriation & cross-border tax cost for a Thailand-based investor.

Estimates the annual drag of getting returns back to Thailand, as a COST FACTOR
(shown + fed to the council; never an auto-drop). Components:
  1. Source-country dividend withholding (treaty rate, e.g. US 15% with W-8BEN)
  2. Thai tax on remitted foreign income (PIT, with a credit for foreign tax;
     a not-yet-enacted same/next-year exemption is toggleable)
  3. ETF domicile effect (US-domiciled vs Irish-domiciled UCITS)
  4. FX cost of round-tripping THB

All rates are configurable via env / constants. THESE ARE ESTIMATES — confirm
with a tax professional. Sources for the encoded defaults are in REDESIGN notes.
"""
from __future__ import annotations

import os

from ..core.provenance import Investment

# -- configurable rates (defaults from 2025/2026 research) ------------------
THAI_DIVIDEND_WHT = float(os.getenv("TH_DIV_WHT", "0.10"))        # Thai domestic dividend WHT
US_TREATY_DIV_WHT = float(os.getenv("US_TH_DIV_WHT", "0.15"))     # US→Thai treaty (W-8BEN)
DEFAULT_FOREIGN_WHT = float(os.getenv("FOREIGN_DIV_WHT", "0.15"))
# the user's marginal Thai personal income tax rate on remitted foreign income
THAI_MARGINAL_PIT = float(os.getenv("THAI_MARGINAL_PIT", "0.20"))
FX_ROUNDTRIP = float(os.getenv("FX_ROUNDTRIP", "0.01"))           # ~1% out-and-back
MEDIUM_TERM_YEARS = float(os.getenv("MEDIUM_TERM_YEARS", "1.5"))
# toggle ON if the same/next-year remittance exemption becomes law (or you remit fast)
REMIT_EXEMPT = os.getenv("THAI_REMIT_EXEMPT", "0") == "1"

# Irish-domiciled UCITS (more tax-efficient for non-US investors). Extend freely.
IRISH_ETFS = {"CSPX", "VUAA", "VWRA", "VWRP", "IWDA", "EIMI", "SWRD", "VUSA", "CNDX"}
# a small set of common US-domiciled ETFs discovery may surface
US_ETFS = {"SPY", "VOO", "QQQ", "IAU", "GLD", "GDX", "EEM", "VNM", "INDA", "SMH",
           "VWO", "EWJ", "FXI", "SCHD", "JEPI", "ARKK"}


def _origin(inv: Investment) -> str:
    t = inv.ticker.upper()
    if t.endswith(".BK") or (inv.asset_class in ("Fund", "Gold Fund") and inv.currency == "THB"):
        return "TH"
    if t.endswith(".L") or t in IRISH_ETFS:
        return "IE"
    if t.endswith("-USD"):
        return "CRYPTO"
    return "US"  # default: US-listed / USD


def _is_etf(inv: Investment, origin: str) -> bool:
    t = inv.ticker.upper()
    return origin in ("IE",) or t in US_ETFS or "ETF" in (inv.name or "").upper()


def compute_repatriation(inv: Investment) -> dict:
    origin = _origin(inv)
    is_etf = _is_etf(inv, origin)
    div_yield = inv.get("Dividend yield")
    dy = float(div_yield) / 100.0 if isinstance(div_yield, (int, float)) else 0.0

    notes: list[str] = []
    suggestion = ""

    if origin == "TH":
        div_wht = THAI_DIVIDEND_WHT
        eff_div_tax = THAI_DIVIDEND_WHT
        fx_drag = 0.0
        notes.append(f"Thai-domestic: {THAI_DIVIDEND_WHT*100:.0f}% dividend WHT, no remittance tax, no FX.")
    else:
        # source-country dividend withholding
        if origin == "US":
            div_wht = US_TREATY_DIV_WHT
        elif origin == "IE":
            div_wht = 0.0  # no investor-level WHT on UCITS distributions
        else:
            div_wht = DEFAULT_FOREIGN_WHT
        # Thai PIT on remitted foreign income, crediting the WHT already paid
        if REMIT_EXEMPT:
            eff_div_tax = div_wht
            notes.append("Same/next-year remittance exemption assumed ON (proposed, not yet law).")
        else:
            eff_div_tax = max(div_wht, THAI_MARGINAL_PIT)  # DTA credit => pay the higher
            notes.append(
                f"Foreign income remitted to Thailand is taxable at your PIT "
                f"(~{THAI_MARGINAL_PIT*100:.0f}% assumed), crediting {div_wht*100:.0f}% WHT."
            )
        fx_drag = (FX_ROUNDTRIP / MEDIUM_TERM_YEARS) * 100.0
        notes.append(f"FX round-trip ~{FX_ROUNDTRIP*100:.1f}% over ~{MEDIUM_TERM_YEARS:g}yr.")
        if origin == "US" and is_etf:
            suggestion = "An Irish-domiciled accumulating UCITS equivalent would cut withholding for a Thai investor."
            notes.append("US-domiciled ETF: 15% treaty WHT on distributions; Irish UCITS often more efficient.")
        if origin == "IE":
            internal = 0.15 * dy * 100.0
            notes.append(f"Irish UCITS: ~0% investor WHT; ~15% fund-level US WHT (~{internal:.2f}%/yr internal drag).")

    dividend_drag = dy * eff_div_tax * 100.0
    total_drag = round(dividend_drag + fx_drag, 2)

    inv.add_value("Dividend WHT", round(div_wht * 100, 1), unit="%", source_name="repatriation.py", period="treaty")
    inv.add_value("Repatriation drag", total_drag, unit="%/yr", source_name="repatriation.py", period="model",
                  note=("; ".join(notes))[:300])
    if total_drag >= 2.0:
        inv.flag(f"High repatriation drag (~{total_drag:.1f}%/yr) for a Thai investor")

    return {
        "origin": origin,
        "is_etf": is_etf,
        "dividend_wht_pct": round(div_wht * 100, 1),
        "effective_dividend_tax_pct": round(eff_div_tax * 100, 1),
        "dividend_drag_pct": round(dividend_drag, 2),
        "fx_drag_pct": round(fx_drag, 2),
        "total_drag_pct": total_drag,
        "remit_exempt_assumed": REMIT_EXEMPT,
        "notes": " ".join(notes),
        "suggestion": suggestion,
        "disclaimer": "Estimate — confirm with a Thai tax professional.",
    }
