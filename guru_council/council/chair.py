"""The Chair — Stage 5 synthesis.

Blends the four scored verdicts, surfaces agreement vs disagreement explicitly,
and frames a human decision. Never forces consensus; never auto-trades.
"""
from __future__ import annotations

from typing import Any

from ..core.provenance import Investment, Verdict
from .base import stance_from

POSITIVE = {"Buy", "Accumulate"}
CAUTIOUS = {"Caution", "Pass"}


def _names(vs: list[Verdict]) -> str:
    return ", ".join(v.analyst for v in vs)


def synthesize(verdicts: list[Verdict], inv: Investment) -> dict[str, Any]:
    scored = [v for v in verdicts if v.engine == "llm"]
    if not scored:
        unscored = any(v.engine == "unavailable" for v in verdicts)
        return {"overall_stance": "Unscored", "overall_label": "SCORE UNAVAILABLE (no LLM)",
                "blended_conviction": 0, "agreement": "", "disagreement": "",
                "net": ("AI scoring is required but no LLM was reachable. Configure an LLM "
                        "(OpenAI/Anthropic/Ollama) and re-run." if unscored
                        else "Not enough verified data to form a view."),
                "flip": ""}

    blended = round(sum(v.conviction for v in scored) / len(scored))
    spread = max(v.conviction for v in scored) - min(v.conviction for v in scored)
    overall = stance_from(blended)

    positives = [v for v in scored if v.stance in POSITIVE]
    cautious = [v for v in scored if v.stance in CAUTIOUS]

    if overall in POSITIVE:
        label = "ACCUMULATE"
    elif overall == "Wait":
        label = "WAIT — accumulate on dips" if positives else "WAIT"
    elif overall == "Caution":
        label = "CAUTION — wait for a better setup"
    else:
        label = "PASS"
    if spread >= 25:
        label += " (council split)"

    # agreement / disagreement narrative
    if not positives and not cautious:
        agreement = "all four analysts land on a neutral, wait-and-see stance."
        disagreement = "no material disagreement — differences are of degree, not direction."
    elif positives and cautious:
        agreement = "the business/asset facts themselves are not in dispute."
        disagreement = (f"{_names(positives)} see enough to lean in, while "
                        f"{_names(cautious)} flag valuation or fragility risk.")
    elif positives:
        agreement = f"{_names(positives)} lean constructive; the rest stay neutral."
        disagreement = "mainly about conviction size, not direction."
    else:
        agreement = f"{_names(cautious)} counsel caution; the rest stay neutral."
        disagreement = "the debate is how defensive to be, not whether to chase."

    risk_v = min(scored, key=lambda v: v.conviction)
    val_up = inv.get("Upside to fair value")
    flip_bits = []
    if isinstance(val_up, (int, float)):
        if val_up < 0:
            flip_bits.append(f"a pullback toward fair value (~{val_up:g}% from here)")
        else:
            flip_bits.append("confirmation the discount is real (earnings holding up)")
    if risk_v.key_risk:
        flip_bits.append(f"avoiding the key risk ({risk_v.key_risk})")
    flip = "; ".join(flip_bits) or "new data that resolves the split above."

    net = f"{label}. Blended conviction {blended}/100 across four lenses."
    return {
        "overall_stance": overall,
        "overall_label": label,
        "blended_conviction": blended,
        "agreement": agreement,
        "disagreement": disagreement,
        "net": net,
        "flip": flip,
    }
