"""Stage 2 — cleaning / normalization.

Coerce numeric strings, trim text, and drop empty facts so downstream tools and
analysts get consistent types. Garbage-in guard before anything reasons.
"""
from __future__ import annotations

from ..core.provenance import Investment

_NUMERIC_HINTS = ("×", "%", "$", "฿", "bn", "/bbl", "/oz", "/unit", "")


def _coerce(value):
    if isinstance(value, str):
        s = value.strip().replace(",", "")
        for junk in ("×", "%", "$", "฿"):
            s = s.replace(junk, "")
        s = s.strip()
        try:
            return float(s)
        except ValueError:
            return value.strip()
    return value


def clean(inv: Investment) -> Investment:
    for metric, fact in list(inv.facts.items()):
        # numeric coercion for ratio-like values
        if isinstance(fact.value, str) and any(h in fact.unit for h in _NUMERIC_HINTS):
            coerced = _coerce(fact.value)
            fact.value = coerced
        if isinstance(fact.note, str):
            fact.note = fact.note.strip()
        # normalize history values to floats
        if fact.history:
            cleaned = []
            for point in fact.history:
                try:
                    cleaned.append([point[0], float(point[1])])
                except (TypeError, ValueError, IndexError):
                    continue
            fact.history = cleaned or None
    return inv
