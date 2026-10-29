"""Base field-specialist analyst — AI peer-relative scoring.

The specialist AI owns the score, judging the investment MOSTLY by how it ranks
against same-industry competitors (curated peer groups). When no LLM is reachable
the verdict is marked "Unscored" (AI scoring is required by design).
"""
from __future__ import annotations

import statistics
from typing import Any

from ..core import llm
from ..core.provenance import Investment, Verdict

ALLOWED = {"Buy", "Accumulate", "Wait", "Pass", "Caution"}

RELATIVE_GUIDANCE = (
    "Score MOSTLY on how this investment ranks against its same-industry peers on the "
    "metrics below (about 70% peer-relative, 30% absolute level). The cheapest / "
    "highest-quality name in the peer group should score well even if the whole sector "
    "looks expensive; a laggard should score poorly even if the sector is cheap. "
    "If a peer is clearly better, say so in the thesis."
)


def clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> int:
    return int(max(lo, min(hi, round(v))))


def stance_from(score: float) -> str:
    if score >= 80:
        return "Buy"
    if score >= 70:
        return "Accumulate"
    if score >= 50:
        return "Wait"
    if score >= 35:
        return "Caution"
    return "Pass"


class CouncilAnalyst:
    name: str = "Analyst"
    lens: str = ""
    relevant: list[str] = []
    peer_metrics: dict[str, str] = {}  # metric -> "high"/"low" (better direction)
    guidance: str = ""

    # subclasses may override (e.g. value analyst needs earnings)
    def applicable(self, inv: Investment) -> bool:
        return True

    def system_prompt(self) -> str:
        return (
            f"You are the {self.name} on an investment council, judging through this lens: "
            f"{self.lens}. Medium-term horizon (3 months to 2 years). {RELATIVE_GUIDANCE} "
            f"{self.guidance}"
        )

    # -- helpers ------------------------------------------------------------
    def _used(self, inv: Investment) -> tuple[list[str], list[str]]:
        metrics = [m for m in self.relevant if inv.has(m)]
        sources: list[str] = []
        for m in metrics:
            sn = inv.facts[m].source_name
            if sn and sn not in sources:
                sources.append(sn)
        return metrics, sources

    def _facts_block(self, inv: Investment) -> str:
        lines = []
        for m in self.relevant:
            if inv.has(m):
                f = inv.facts[m]
                lines.append(f"- {m}: {f.value}{(' ' + f.unit) if f.unit else ''} ({f.period})")
        if inv.flags:
            lines.append("Data flags: " + "; ".join(inv.flags[:4]))
        return "\n".join(lines) or "(no verified metrics)"

    def _peer_block(self, inv: Investment, table: dict[str, dict[str, float]]) -> str:
        peers = [t for t in table if t != inv.ticker]
        if not peers:
            return "(no peer data available — score on absolute merit and say so)"
        lines = [f"Peers: {', '.join(peers)}"]
        for metric, direction in self.peer_metrics.items():
            tv = inv.get(metric)
            if not isinstance(tv, (int, float)):
                continue
            pv = [table[t][metric] for t in peers if metric in table[t]]
            if not pv:
                continue
            med = statistics.median(pv)
            order = sorted([tv] + pv, reverse=(direction == "high"))
            rank = order.index(tv) + 1
            better = "higher is better" if direction == "high" else "lower is better"
            lines.append(f"- {metric}: this={tv} vs peer median={round(med, 2)} → rank {rank}/{len(order)} ({better})")
        return "\n".join(lines)

    # -- scoring ------------------------------------------------------------
    def assess(self, inv: Investment, peer_table: dict[str, dict[str, float]]) -> Verdict:
        if not self.applicable(inv):
            return self._na(inv, "Outside this lens for this asset type.")
        if not llm.available():
            return self._unscored(inv)
        return self._llm_score(inv, peer_table) or self._unscored(inv)

    def _llm_score(self, inv: Investment, peer_table: dict[str, dict[str, float]]) -> Verdict | None:
        prompt = (
            f"Investment: {inv.name} ({inv.ticker}), {inv.asset_class}, "
            f"price {inv.price_display or inv.price} {inv.currency}.\n"
            f"This investment's verified data (use ONLY these numbers):\n{self._facts_block(inv)}\n\n"
            f"Same-industry peer comparison:\n{self._peer_block(inv, peer_table)}\n\n"
            "Return JSON only:\n"
            '{"stance":"Buy|Accumulate|Wait|Pass|Caution","conviction":0-100,'
            '"confidence":0-100,"thesis":"<=40 words; cite the peer ranking",'
            '"key_risk":"<=15 words"}'
        )
        data = llm.parse_json(
            llm.complete(prompt, self.system_prompt(), max_tokens=400, temperature=0)
        )
        if not data or data.get("conviction") is None:
            return None
        conv = clamp(float(data.get("conviction", 0)))
        stance = str(data.get("stance", "")).title()
        if stance not in ALLOWED:
            stance = stance_from(conv)
        metrics, sources = self._used(inv)
        return Verdict(
            analyst=self.name,
            lens=self.lens,
            stance=stance,
            conviction=conv,
            confidence=clamp(float(data.get("confidence", 60))),
            thesis=str(data.get("thesis", "")).strip(),
            key_risk=str(data.get("key_risk", "")).strip(),
            metrics_used=metrics,
            sources=sources,
            engine="llm",
        )

    def _unscored(self, inv: Investment) -> Verdict:
        return Verdict(self.name, self.lens, "Unscored", 0, 0,
                       "Score unavailable — no LLM reachable (AI scoring required).",
                       "", [], [], engine="unavailable")

    def _na(self, inv: Investment, why: str) -> Verdict:
        return Verdict(self.name, self.lens, "n/a", 0, 0, why, "", [], [], engine="na")


def num(inv: Investment, metric: str, default: float | None = None) -> float | None:
    v = inv.get(metric)
    return float(v) if isinstance(v, (int, float)) else default
