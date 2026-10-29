"""Provenance-first data model.

A `Fact` is never a bare number: it carries where it came from, for which
period, when it was retrieved, and how confident we are. An `Investment`
collects facts for one ticker plus QC flags.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Fact:
    metric: str
    value: Any
    unit: str = ""
    source_name: str = ""
    source_url: str = ""
    period: str = ""  # e.g. "FY2025", "TTM", or an ISO date for spot values
    retrieved_at: str = field(default_factory=_now)
    confidence: float = 1.0
    note: str = ""
    # optional multi-year history for clickable trend charts: [[period, value], ...]
    history: Optional[list[list[Any]]] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Investment:
    ticker: str
    name: str = ""
    asset_class: str = ""
    currency: str = ""
    price: Optional[float] = None
    price_display: str = ""
    change_pct: Optional[float] = None
    facts: dict[str, Fact] = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)  # QC / missing-data flags
    as_of: str = field(default_factory=lambda: datetime.now(timezone.utc).date().isoformat())

    # -- fact helpers -------------------------------------------------------
    def add(self, fact: Fact) -> None:
        self.facts[fact.metric] = fact

    def add_value(self, metric: str, value: Any, **kw: Any) -> Fact:
        f = Fact(metric=metric, value=value, **kw)
        self.add(f)
        return f

    def get(self, metric: str, default: Any = None) -> Any:
        f = self.facts.get(metric)
        return f.value if f is not None else default

    def has(self, metric: str) -> bool:
        return metric in self.facts and self.facts[metric].value is not None

    def flag(self, message: str) -> None:
        if message not in self.flags:
            self.flags.append(message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "name": self.name,
            "asset_class": self.asset_class,
            "currency": self.currency,
            "price": self.price,
            "price_display": self.price_display,
            "change_pct": self.change_pct,
            "as_of": self.as_of,
            "facts": {k: v.to_dict() for k, v in self.facts.items()},
            "flags": list(self.flags),
        }


@dataclass
class Verdict:
    """One field-specialist analyst's scored opinion."""
    analyst: str
    lens: str
    stance: str  # Buy | Accumulate | Wait | Pass | Caution | n/a
    conviction: int  # 0-100 (blended ranking signal)
    confidence: int  # 0-100 (how solid the underlying data was)
    thesis: str
    key_risk: str = ""
    metrics_used: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    engine: str = "heuristic"  # "llm" once a model actually wrote the thesis

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
