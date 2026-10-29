"""Curated offline sample dataset.

Used when no network/live source is available so the whole pipeline runs and
is testable anywhere. Numbers are illustrative but internally consistent with
the project's real holdings. Each metric carries a category (which source would
provide it) and optional multi-year history for trend charts.
"""
from __future__ import annotations

from typing import Any

# category: "price" -> yahoo_quote, "ratios" -> fundamentals, "news" -> news_rss
SAMPLE: dict[str, dict[str, Any]] = {
    "MSFT": {
        "meta": {"name": "Microsoft", "asset_class": "US Equity", "currency": "USD",
                 "price": 498.20, "price_display": "$498.20", "change_pct": 0.9},
        "facts": {
            "P/E": {"value": 37.0, "unit": "×", "period": "TTM", "category": "ratios",
                     "history": [[2020, 32], [2021, 35], [2022, 28], [2023, 34], [2024, 37], [2025, 36], [2026, 37]]},
            "ROIC": {"value": 30.0, "unit": "%", "period": "FY2025", "category": "ratios",
                      "history": [[2020, 24], [2021, 30], [2022, 28], [2023, 27], [2024, 29], [2025, 30], [2026, 30]]},
            "ROE": {"value": 35.0, "unit": "%", "period": "FY2025", "category": "ratios",
                     "history": [[2020, 40], [2021, 43], [2022, 44], [2023, 39], [2024, 37], [2025, 36], [2026, 35]]},
            "Debt/Equity": {"value": 0.30, "unit": "", "period": "FY2025", "category": "ratios"},
            "Dividend yield": {"value": 0.7, "unit": "%", "period": "TTM", "category": "ratios",
                                "history": [[2020, 1.0], [2021, 0.8], [2022, 1.0], [2023, 0.8], [2024, 0.7], [2025, 0.7], [2026, 0.7]]},
            "FCF yield": {"value": 2.9, "unit": "%", "period": "TTM", "category": "ratios",
                           "history": [[2020, 3.6], [2021, 3.0], [2022, 3.2], [2023, 2.6], [2024, 2.5], [2025, 2.8], [2026, 2.9]]},
            "Revenue growth": {"value": 14.0, "unit": "%", "period": "TTM", "category": "ratios",
                                "history": [[2020, 14], [2021, 18], [2022, 18], [2023, 7], [2024, 16], [2025, 15], [2026, 14]]},
            "Price/FCF": {"value": 35.0, "unit": "×", "period": "TTM", "category": "ratios",
                           "history": [[2020, 28], [2021, 34], [2022, 30], [2023, 38], [2024, 40], [2025, 36], [2026, 35]]},
            "Market cap": {"value": 3700.0, "unit": "USD bn", "period": "spot", "category": "ratios", "note": "$3.7T"},
            "News sentiment": {"value": 0.35, "unit": "score", "period": "24h", "category": "news", "note": "Bullish — AI capex / Copilot"},
        },
    },
    "SCB.BK": {
        "meta": {"name": "SCB X", "asset_class": "SET Bank", "currency": "THB",
                 "price": 142.50, "price_display": "฿142.50", "change_pct": 0.4},
        "facts": {
            "P/E": {"value": 8.0, "unit": "×", "period": "TTM", "category": "ratios",
                     "history": [[2020, 9.5], [2021, 10], [2022, 8.5], [2023, 8], [2024, 7.6], [2025, 8], [2026, 8]]},
            "ROE": {"value": 9.0, "unit": "%", "period": "FY2025", "category": "ratios",
                     "history": [[2020, 7], [2021, 8], [2022, 8.5], [2023, 9], [2024, 9.2], [2025, 9], [2026, 9]]},
            "Debt/Equity": {"value": None, "unit": "", "period": "FY2025", "category": "ratios", "note": "n/m (bank)"},
            "Dividend yield": {"value": 7.5, "unit": "%", "period": "TTM", "category": "ratios",
                                "history": [[2020, 4], [2021, 5], [2022, 6], [2023, 7], [2024, 7.2], [2025, 7.5], [2026, 7.5]]},
            "FCF yield": {"value": None, "unit": "%", "period": "TTM", "category": "ratios", "note": "n/m (bank)"},
            "Revenue growth": {"value": 5.0, "unit": "%", "period": "TTM", "category": "ratios"},
            "NPL ratio": {"value": 3.3, "unit": "%", "period": "Q1", "category": "ratios"},
            "Market cap": {"value": 14.0, "unit": "USD bn", "period": "spot", "category": "ratios", "note": "฿470B"},
            "Next earnings": {"value": "2026-07-17", "unit": "", "period": "event", "category": "news", "note": "27 days"},
            "News sentiment": {"value": 0.2, "unit": "score", "period": "24h", "category": "news", "note": "Neutral-positive — rate beneficiary"},
        },
    },
    "PTTEP.BK": {
        "meta": {"name": "PTT E&P", "asset_class": "SET Energy", "currency": "THB",
                 "price": 118.50, "price_display": "฿118.50", "change_pct": 0.2},
        "facts": {
            "P/E": {"value": 9.0, "unit": "×", "period": "TTM", "category": "ratios",
                     "history": [[2020, 13], [2021, 10], [2022, 6], [2023, 8], [2024, 9], [2025, 9], [2026, 9]]},
            "ROE": {"value": 13.0, "unit": "%", "period": "FY2025", "category": "ratios",
                     "history": [[2020, 6], [2021, 9], [2022, 18], [2023, 15], [2024, 13], [2025, 13], [2026, 13]]},
            "Debt/Equity": {"value": 0.30, "unit": "", "period": "FY2025", "category": "ratios"},
            "Dividend yield": {"value": 4.5, "unit": "%", "period": "TTM", "category": "ratios",
                                "history": [[2020, 4], [2021, 4.2], [2022, 6], [2023, 5], [2024, 4.8], [2025, 4.5], [2026, 4.5]]},
            "FCF yield": {"value": 8.0, "unit": "%", "period": "TTM", "category": "ratios",
                           "history": [[2020, 3], [2021, 6], [2022, 12], [2023, 10], [2024, 8], [2025, 8], [2026, 8]]},
            "Revenue growth": {"value": -5.0, "unit": "%", "period": "TTM", "category": "ratios"},
            "Market cap": {"value": 14.0, "unit": "USD bn", "period": "spot", "category": "ratios", "note": "฿470B"},
            "Brent": {"value": 80.6, "unit": "$/bbl", "period": "spot", "category": "price"},
            "Breakeven": {"value": 45.0, "unit": "$/bbl", "period": "FY2025", "category": "ratios"},
            "News sentiment": {"value": 0.0, "unit": "score", "period": "24h", "category": "news", "note": "Neutral — oil premium unwound"},
        },
    },
    "SCBGOLDE": {
        "meta": {"name": "SCB Gold", "asset_class": "Gold Fund", "currency": "THB",
                 "price": 4.24, "price_display": "฿4.24 / unit", "change_pct": -1.4},
        "facts": {
            "NAV": {"value": 4.24, "unit": "฿/unit", "period": "spot", "category": "price",
                     "history": [[2020, 3.0], [2021, 3.1], [2022, 3.3], [2023, 3.6], [2024, 4.0], [2025, 4.5], [2026, 4.24]]},
            "TER": {"value": 0.50, "unit": "% p.a.", "period": "FY2025", "category": "ratios"},
            "Gold spot": {"value": 4140.0, "unit": "$/oz", "period": "spot", "category": "price",
                           "history": [[2020, 1900], [2021, 1830], [2022, 1820], [2023, 2060], [2024, 2630], [2025, 4500], [2026, 4140]]},
            "Drawdown": {"value": -8.0, "unit": "% off high", "period": "spot", "category": "ratios", "note": "Fed-driven dip"},
            "Dividend yield": {"value": 0.0, "unit": "%", "period": "TTM", "category": "ratios"},
            "News sentiment": {"value": -0.1, "unit": "score", "period": "24h", "category": "news", "note": "Cautious — higher-for-longer Fed"},
        },
    },
    "BAFS.BK": {
        "meta": {"name": "Bangkok Aviation Fuel", "asset_class": "SET Aviation", "currency": "THB",
                 "price": 26.50, "price_display": "฿26.50", "change_pct": 0.1},
        "facts": {
            "P/E": {"value": 18.0, "unit": "×", "period": "TTM", "category": "ratios",
                     "history": [[2020, 24], [2021, 28], [2022, 26], [2023, 22], [2024, 19], [2025, 18], [2026, 18]]},
            "ROE": {"value": 8.0, "unit": "%", "period": "FY2025", "category": "ratios",
                     "history": [[2020, 6], [2021, 4], [2022, 6], [2023, 7], [2024, 8], [2025, 8], [2026, 8]]},
            "Debt/Equity": {"value": 0.60, "unit": "", "period": "FY2025", "category": "ratios"},
            "Dividend yield": {"value": 3.0, "unit": "%", "period": "TTM", "category": "ratios",
                                "history": [[2020, 2.5], [2021, 2], [2022, 2.5], [2023, 3], [2024, 3], [2025, 3], [2026, 3]]},
            "FCF yield": {"value": 4.0, "unit": "%", "period": "TTM", "category": "ratios"},
            "Revenue growth": {"value": 6.0, "unit": "%", "period": "TTM", "category": "ratios"},
            "Market cap": {"value": 0.7, "unit": "USD bn", "period": "spot", "category": "ratios", "note": "฿22B"},
            "Jet fuel": {"value": 80.0, "unit": "$/bbl", "period": "spot", "category": "price"},
            "News sentiment": {"value": 0.1, "unit": "score", "period": "24h", "category": "news", "note": "Stable tourism demand"},
        },
    },
}


def get_sample(ticker: str) -> dict[str, Any] | None:
    return SAMPLE.get(ticker.upper())


def sample_tickers() -> list[str]:
    return list(SAMPLE)
