"""The workflow runner — the code equivalent of the lesson's visual graph.

Orchestrates: source review -> extract -> clean -> tools -> verify ->
council -> chair -> persist. Re-runnable with an edited source set.
"""
from __future__ import annotations

from typing import Any, Optional

from .. import extractors  # noqa: F401  ensures extractor methods register
from ..council import COUNCIL
from ..council.chair import synthesize
from ..stages.clean import clean
from ..stages.verify import verify
from ..tools.fees import compute_fees
from ..tools.fx import compute_fx
from ..tools.repatriation import compute_repatriation
from ..tools.valuation import compute_valuation
from . import llm, store
from .base_extract import run_extractors  # local helper module
from .peers import build_peer_table, peer_advice
from .provenance import Investment
from .registry import classify, default_source_set


def run_analysis(
    ticker: str,
    sources: Optional[list[dict[str, Any]]] = None,
    save: bool = True,
    peer_override: Optional[list[str]] = None,
) -> dict[str, Any]:
    ticker = ticker.upper()
    inv = Investment(ticker=ticker, asset_class=classify(ticker))

    if sources is None:
        sources = store.load_source_set(ticker) or default_source_set(ticker)

    # Stage 1 — extraction (only enabled sources, via their registered method)
    used = run_extractors(inv, sources)

    # Stage 2 — clean
    clean(inv)

    # Tools (deterministic) — add derived facts before verification
    val = compute_valuation(inv)
    fees = compute_fees(inv)
    fx = compute_fx(inv)
    repat = compute_repatriation(inv)  # Thai-investor cross-border cost factor

    # Stage 3 — verify / provenance
    verify(inv)

    # Peer comparison — fetch competitors and compute the advisory
    peer_info = build_peer_table(ticker, peer_override)
    advice = peer_advice(ticker, peer_info["table"])

    # Stage 4 — council (AI peer-relative scoring)
    verdicts = [analyst.assess(inv, peer_info["table"]) for analyst in COUNCIL]

    # Stage 5 — chair synthesis
    chair = synthesize(verdicts, inv)

    report = {
        "investment": inv.to_dict(),
        "verdicts": [v.to_dict() for v in verdicts],
        "chair": chair,
        "tools": {"valuation": val, "fees": fees, "fx": fx, "repatriation": repat},
        "peers": peer_info,
        "peer_advice": advice,
        "sources": used,
        # truthful: only True if a model actually scored at least one verdict
        "llm_used": any(v.engine == "llm" for v in verdicts),
    }

    if save:
        store.save_source_set(ticker, sources)
        store.save_report(report)
    return report


def run_batch(tickers: list[str], max_candidates: int = 8) -> dict[str, Any]:
    """Analyze requested investments, then DISCOVER better-or-equal alternatives:
    auto-analyze candidate peers and keep, per target, those whose council
    conviction is >= the target's (overall better-or-equal). Filters out the rest.
    """
    reports: dict[str, Any] = {}
    for t in tickers:
        r = run_analysis(t)
        reports[r["investment"]["ticker"]] = r
    primaries = set(reports)

    # candidate expansion only makes sense when scoring is available (LLM)
    if llm.available():
        provisional: list[str] = []
        for r in list(reports.values()):
            for c in (r.get("peer_advice") or {}).get("candidates", []):
                ct = c["ticker"].upper()
                if ct not in primaries and ct not in provisional:
                    provisional.append(ct)
        for c in provisional[:max_candidates]:
            if c not in reports:
                rr = run_analysis(c)
                rr["discovered"] = True
                store.save_report(rr)
                reports[rr["investment"]["ticker"]] = rr

    _finalize_candidates(reports)
    return reports


def _finalize_candidates(reports: dict[str, Any]) -> None:
    """Per target, keep candidates whose council conviction >= the target's."""
    for t, r in reports.items():
        tconv = (r.get("chair") or {}).get("blended_conviction", 0)
        unscored_t = (r.get("chair") or {}).get("overall_stance") == "Unscored"
        cands = []
        for c in (r.get("peer_advice") or {}).get("candidates", []):
            ct = c["ticker"].upper()
            cr = reports.get(ct)
            if not cr or ct == t:
                continue
            cc = cr.get("chair") or {}
            if cc.get("overall_stance") == "Unscored":
                continue
            if unscored_t or cc.get("blended_conviction", 0) >= tconv:
                cands.append({"ticker": ct, "name": cr["investment"]["name"],
                              "conviction": cc.get("blended_conviction", 0)})
        r["candidates"] = sorted(cands, key=lambda x: -x["conviction"])
        store.save_report(r)


def discover(scope: list[str], n: int = 8) -> dict[str, Any]:
    """AI scout proposes brand-new ideas (excluding holdings), validated by data,
    then the council analyzes them. Same-theme ideas peer-compare against each other.
    """
    from ..discovery.scout import propose_ideas

    res = propose_ideas(scope, n=n)
    if not res.get("available"):
        return {"available": False, "reason": res.get("reason", "scout unavailable"), "reports": {}}

    ideas = res["ideas"]
    by_theme: dict[str, list[str]] = {}
    for i in ideas:
        by_theme.setdefault((i.get("theme") or "misc").lower(), []).append(i["ticker"])

    reports: dict[str, Any] = {}
    for i in ideas:
        theme = (i.get("theme") or "misc").lower()
        peers = [t for t in by_theme.get(theme, []) if t != i["ticker"]]
        r = run_analysis(i["ticker"], peer_override=peers or None)
        r["discovered_idea"] = True
        r["idea_theme"] = i.get("theme", "")
        r["idea_reason"] = i.get("reason", "")
        store.save_report(r)
        reports[r["investment"]["ticker"]] = r

    _finalize_candidates(reports)
    return {"available": True, "macro": res.get("macro", {}), "ideas": ideas, "reports": reports}
