"""Curated peer groups + peer-data collection + peer advisory.

Each investment is compared against same-industry competitors. The peer groups
are curated (editable in data/council/peers.json) so you control the comparison
set. `peer_advice` ranks the whole group on the comparable metrics and flags any
peer that beats the target on a field or overall — so the report can suggest a
better alternative.
"""
from __future__ import annotations

import json
from typing import Any

from ..config import DATA_DIR
from .provenance import Investment
from .registry import classify

# direction: "high" = higher is better, "low" = lower is better
PEER_METRIC_DIRECTION: dict[str, str] = {
    "P/E": "low",
    "FCF yield": "high",
    "ROE": "high",
    "Dividend yield": "high",
    "Revenue growth": "high",
    "Debt/Equity": "low",
}

DEFAULT_PEER_GROUPS: dict[str, list[str]] = {
    "MSFT": ["AAPL", "GOOGL", "AMZN", "META", "ORCL"],
    "SCB.BK": ["KBANK.BK", "BBL.BK", "KTB.BK", "TTB.BK"],
    "PTTEP.BK": ["PTT.BK", "BCP.BK", "TOP.BK", "IRPC.BK"],
    "BAFS.BK": ["AOT.BK", "PSL.BK", "BA.BK"],
    "SCBGOLDE": ["GLD", "IAU", "SGOL"],
}

_PEERS_FILE = DATA_DIR / "peers.json"
_CACHE: dict[str, dict[str, float]] = {}


def _ensure_file() -> None:
    if not _PEERS_FILE.exists():
        _PEERS_FILE.write_text(
            json.dumps(DEFAULT_PEER_GROUPS, indent=2, ensure_ascii=False), encoding="utf-8"
        )


def get_peers(ticker: str) -> list[str]:
    _ensure_file()
    try:
        groups = json.loads(_PEERS_FILE.read_text(encoding="utf-8"))
    except Exception:
        groups = DEFAULT_PEER_GROUPS
    return groups.get(ticker.upper(), DEFAULT_PEER_GROUPS.get(ticker.upper(), []))


def _metrics_for(ticker: str) -> dict[str, float]:
    """Fetch comparable numeric metrics for one ticker (cached per process)."""
    key = ticker.upper()
    if key in _CACHE:
        return _CACHE[key]
    from ..extractors.base import get_extractor  # late import (avoids cycle)

    inv = Investment(ticker=key, asset_class=classify(key))
    for method in ("yahoo_quote", "fundamentals"):
        extractor = get_extractor(method)
        if not extractor:
            continue
        src = {"name": method, "url": "", "method": method}
        try:
            for fact in extractor(src, inv):
                inv.add(fact)
        except Exception:
            pass
    vals = {m: float(f.value) for m, f in inv.facts.items() if isinstance(f.value, (int, float))}
    _CACHE[key] = vals
    return vals


def build_peer_table(ticker: str, peers: list[str] | None = None) -> dict[str, Any]:
    # peers override (e.g. same-theme discovery ideas) takes precedence over the
    # curated group; falls back to the curated peers for the ticker.
    peers = peers if peers is not None else get_peers(ticker)
    table = {ticker.upper(): _metrics_for(ticker)}
    for p in peers:
        table[p.upper()] = _metrics_for(p)
    return {"peers": [p.upper() for p in peers], "table": table}


def peer_advice(target: str, table: dict[str, dict[str, float]]) -> dict[str, Any]:
    """Composite-rank the peer group and flag peers that beat the target."""
    target = target.upper()
    names = [t for t in table if table.get(t)]  # only names that returned data
    if target not in names or len(names) < 2:
        return {"available": False}

    metrics = [m for m in PEER_METRIC_DIRECTION if sum(1 for t in names if m in table[t]) >= 2]
    composite: dict[str, list[float]] = {t: [] for t in names}
    field_winners: dict[str, dict[str, Any]] = {}
    for m in metrics:
        vals = {t: table[t][m] for t in names if m in table[t]}
        lo, hi = min(vals.values()), max(vals.values())
        rng = (hi - lo) or 1.0
        direction = PEER_METRIC_DIRECTION[m]
        for t, v in vals.items():
            pct = (v - lo) / rng
            composite[t].append(pct if direction == "high" else 1 - pct)
        winner = max(vals, key=lambda t: vals[t] if direction == "high" else -vals[t])
        field_winners[m] = {"winner": winner, "target_value": vals.get(target), "best_value": vals[winner]}

    scores = {t: round(sum(v) / len(v) * 100) for t, v in composite.items() if v}
    if target not in scores:
        return {"available": False}
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    order = [t for t, _ in ranked]
    target_rank = order.index(target) + 1
    better_overall = [{"ticker": t, "score": s} for t, s in ranked if t != target and s > scores[target]]
    # candidates = peers that are overall better OR equivalent to the target
    # (composite >= target). These get auto-analyzed and surfaced for review.
    candidates = [{"ticker": t, "score": s} for t, s in ranked
                  if t != target and s >= scores[target]]
    field_beats = [
        {"metric": m, "winner": fw["winner"],
         "winner_value": fw["best_value"], "target_value": fw["target_value"]}
        for m, fw in field_winners.items()
        if fw["winner"] != target
    ]
    return {
        "available": True,
        "scores": scores,
        "ranked": ranked,
        "target": target,
        "target_rank": target_rank,
        "total": len(order),
        "better_overall": better_overall,
        "candidates": candidates,
        "field_beats": field_beats,
        "metrics_used": metrics,
    }
