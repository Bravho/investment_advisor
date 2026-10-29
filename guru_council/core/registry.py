"""Source-set resolution and asset classification.

A *Source Set* is the list of data sources used to analyze an investment.
The user reviews/edits it before a run; each entry names an extraction
*method* (kept in the extractor registry for reuse).
"""
from __future__ import annotations

from typing import Any

FUND_TICKERS = {"SCBGOLDE", "SCBGOLDHE", "SCBGOLDH", "SCBGOLD"}


def classify(ticker: str) -> str:
    t = ticker.upper()
    if t in FUND_TICKERS:
        return "Fund"
    if t.endswith("-USD"):
        return "Crypto"
    if t.endswith(".BK"):
        return "SET Equity"
    return "US Equity"


def default_source_set(ticker: str) -> list[dict[str, Any]]:
    """Propose the data sources for a ticker (user can edit before running)."""
    t = ticker.upper()
    asset = classify(t)
    sources = [
        {
            "name": "Yahoo Finance — quote",
            "url": f"https://finance.yahoo.com/quote/{t}",
            "method": "yahoo_quote",
            "data_type": "price",
            "enabled": True,
        },
        {
            "name": "Fundamentals (Macrotrends / Yahoo)",
            "url": f"https://www.macrotrends.net/stocks/charts/{t}/",
            "method": "fundamentals",
            "data_type": "ratios",
            "enabled": True,
        },
        {
            "name": "News headlines (RSS)",
            "url": f"https://news.google.com/rss/search?q={t}",
            "method": "news_rss",
            "data_type": "news",
            "enabled": True,
        },
    ]
    if asset in ("US Equity", "SET Equity"):
        sources.insert(
            2,
            {
                "name": "SEC / filings (fundamentals detail)",
                "url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company={t}",
                "method": "fundamentals",
                "data_type": "ratios",
                "enabled": False,
            },
        )
    return sources
