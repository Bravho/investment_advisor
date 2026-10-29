"""Extractor registry.

An extractor is a function: (source: dict, inv: Investment) -> list[Fact].
It may also set price/quote metadata on `inv`. Methods are registered by name
so a Source Set can reference them and they stay reusable.
"""
from __future__ import annotations

from typing import Callable

from ..core.provenance import Fact, Investment

Extractor = Callable[[dict, Investment], list]
_REGISTRY: dict[str, Extractor] = {}


def register(method: str) -> Callable[[Extractor], Extractor]:
    def deco(fn: Extractor) -> Extractor:
        _REGISTRY[method] = fn
        return fn

    return deco


def get_extractor(method: str) -> Extractor | None:
    return _REGISTRY.get(method)


def registered_methods() -> list[str]:
    return sorted(_REGISTRY)
