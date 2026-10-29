"""
Investment Guru Council
=======================
A model-agnostic, multi-agent investment-analysis pipeline.

Stages: source review -> extract -> clean -> verify(provenance) ->
tools + knowledge -> council (4 field specialists) -> chair synthesis -> report.

The core runs on the Python standard library alone (offline, with sample data
and heuristic analysts). Live data (yfinance) and LLM providers (Ollama / OpenAI /
Anthropic) are used automatically when available.
"""

__version__ = "0.1.0"
