"""Stage 1 driver: run the enabled sources of a Source Set through their
registered extractor methods, collecting facts and per-source status.
"""
from __future__ import annotations

from typing import Any

from ..extractors.base import get_extractor
from .provenance import Investment


def run_extractors(inv: Investment, sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    used: list[dict[str, Any]] = []
    for src in sources:
        entry = {**src}
        if not src.get("enabled", True):
            entry["status"] = "skipped (disabled)"
            used.append(entry)
            continue
        method = src.get("method", "")
        extractor = get_extractor(method)
        if not extractor:
            inv.flag(f"No extractor registered for method '{method}'")
            entry["status"] = "no extractor"
            used.append(entry)
            continue
        try:
            facts = extractor(src, inv)
            for fact in facts:
                inv.add(fact)
            entry["status"] = f"ok · {len(facts)} facts"
        except Exception as exc:  # pragma: no cover - defensive
            inv.flag(f"Extractor '{method}' failed: {exc}")
            entry["status"] = f"error: {exc}"
        used.append(entry)
    return used
