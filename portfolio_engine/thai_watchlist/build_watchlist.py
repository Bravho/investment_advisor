"""Build data/thai_watchlist.json from the raw yfinance pulls and the scoring + XD analysis.

Run from this folder, after pull_stocks.py, pull_funds.py, analyze_stocks.py and analyze_funds.py:
    ../../venv/bin/python build_watchlist.py

Research only. Not backtested. No orders are placed.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import argparse
import os

import xd_analysis

HERE = Path(__file__).resolve().parent
OUT = HERE.parents[1] / "data" / "thai_watchlist.json"
TODAY = dt.date.today()

# Confirmed XD dates from a dated news source. Everything else is estimated from last year.
CONFIRMED_NEXT_XD = {"DIF.BK": "2026-11-16"}

HELD = {"BAFS.BK", "PTTEP.BK", "SCB.BK"}

NEWS = {
    "KBANK.BK": ["Citi rates Buy (post-1Q26 note, date approx.)", "JPMorgan lists KBANK as a top pick among Thai banks (date not shown in source)", "Interim dividend 2.00 THB, XD 9 Sep 2026 (Thairath)"],
    "KTB.BK": ["DBS upgraded to Buy, target THB 38.50 (post-1Q26). Price is ABOVE this target", "Citi favours KTB (post-1Q26)"],
    "TTB.BK": ["Citi rates Buy (post-1Q26 note)"],
    "BBL.BK": ["Citi rates Neutral (post-1Q26). Limited visibility on earnings and payouts"],
    "SCB.BK": ["Citi rates Neutral; 1Q26 was weak, rebound expected but not yet visible", "Interim dividend 2.00 THB, XD 8 Sep 2026 (Thairath)"],
    "PTTEP.BK": ["Kiatnakin target THB 151.8 (date not shown)", "Finansia Speculative Buy; IAA consensus target about THB 164 (date not shown)", "Early estimate: about +1.5% profit per +USD 1/bbl"],
    "PTT.BK": ["PTT (Apr 2026): 2026 Brent assumption USD 88/bbl; oil could ease in Q3 if conflict cools"],
    "TOP.BK": ["CLSA upgraded to Hold, target THB 36 (from 25). Price is ABOVE this target (2026 note)"],
    "DIF.BK": ["Dividend 0.2222 THB/unit, XD 16 Nov 2026, payment 8 Dec 2026 (Kaohoon)"],
}
DEFAULT_NEWS = ["No dated news item verified in this run."]


def stock_rating(score: float) -> str:
    if score >= 70:
        return "accumulate (สะสมได้)"
    if score >= 55:
        return "watch (รอดู)"
    return "avoid for now (ยังไม่น่าซื้อ)"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=HERE, help="folder with the *_raw.json and *_scored.json files")
    ap.add_argument("--out", type=Path, default=OUT, help="output JSON path")
    args = ap.parse_args()
    src, out_path = args.src, args.out
    stocks = json.loads((src / "stocks_scored.json").read_text(encoding="utf-8"))
    funds = json.loads((src / "funds_scored.json").read_text(encoding="utf-8"))
    stock_raw = json.loads((src / "stocks_raw.json").read_text(encoding="utf-8"))
    fund_raw = json.loads((src / "funds_raw.json").read_text(encoding="utf-8"))

    for s in stocks:
        s["xd"] = xd_analysis.analyze(s["ticker"], stock_raw[s["ticker"]], TODAY, CONFIRMED_NEXT_XD)
        s["rating"] = stock_rating(s["scores"]["overall"]) + (" | held: no sell/trim advice" if s["ticker"] in HELD else "")
        s["held"] = s["ticker"] in HELD
        s["news"] = NEWS.get(s["ticker"], DEFAULT_NEWS)

    for f in funds:
        f["xd"] = xd_analysis.analyze(f["ticker"], fund_raw[f["ticker"]], TODAY, CONFIRMED_NEXT_XD)
        if f["scores"]["income"] is None:
            f["rating"] = "not scored (distribution data stale)"
        else:
            f["rating"] = stock_rating(f["scores"]["overall"])
        f["news"] = NEWS.get(f["ticker"], DEFAULT_NEWS)

    out = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "as_of_prices": max(x["last_date"] for x in stocks + funds),
        "price_source": "yfinance (free, read-only), 3 years of daily data",
        "methodology": {
            "stock_weights": {"dividend": 0.25, "growth": 0.15, "value": 0.15, "quality": 0.15, "technical": 0.15, "xd_timing": 0.15},
            "fund_weights": {"income": 0.30, "total_return": 0.25, "stability": 0.20, "trend": 0.10, "xd_timing": 0.15},
            "scale": "0-100, higher is better",
            "rating_bands": {"accumulate": ">=70", "watch": "55-69", "avoid for now": "<55"},
            "xd_next_date": "Estimated as last year's XD date + 365 days (the earliest one that is still in the future). Confirmed only when a dated news source is listed. A note appears when XD is within 60 days.",
            "xd_timing": "For each past XD event: dividend payout (% of prior close); price move 5 and 10 trading days before and after XD; 20-day recovery of the pre-XD close. Entry A = buy 10 days before XD, hold through XD, sell 10 days after (dividend included, net of 10% withholding). Entry B = buy the day after XD, sell 10 trading days later. Fewer than 3 events = no timing view.",
            "withholding": "10% assumed on dividends (usual rate for Thai individuals). Confirm for your own tax position.",
            "caveats": [
                "Not backtested. Research only. No order is placed by this system.",
                "XD statistics use 3 years; a typical item has 3 to 7 events, so small samples can mislead.",
                "Next XD dates are estimates unless marked confirmed. Check the SET calendar before acting.",
                "yfinance dividend data is incomplete for some names; the yield is flagged when history disagrees by more than 1 point.",
                "Open-end mutual funds are excluded: no free long-run NAV history. Listed Thai funds (REITs, infrastructure, one ETF) are included.",
                "Dated news is shown only where the source gives a date. Many search results were older or undated and are not used as current facts.",
            ],
        },
        "global_context": [
            "Bank of Thailand policy rate 1.00%, held for the 4th straight meeting (Oct 2026). DBS and UOB expect no change through 2026 (TradingEconomics / FXStreet, 2026).",
            "Oil: UBS sees Brent USD 110 by end-2026, Goldman USD 105 for December (roundup dated 2 Nov 2026). KKPS uses USD 82 Brent with a 70-80 range for H2 (date unclear). Views conflict.",
            "JPMorgan: Thai equities Neutral (later note, date unclear).",
            "Average Thai market dividend yield about 4-4.5% (FSSIA, 2026), above the 3-3.5% historical level.",
        ],
        "sources": [
            "yfinance (free) - prices, dividends, fundamentals",
            "Thairath, XD 4-11 Sep 2026 bank list - https://www.thairath.co.th/money/investment/stocks/2956633",
            "Thansettakij, XD 9-16 Nov 2026 list - https://www.thansettakij.com/finance/stockmarket/672952",
            "Kaohoon, DIF XD 16 Nov 2026 - https://www.kaohoon.com/news/877896",
            "Kaohoon International, Market Roundup 2 Nov 2026 - https://www.kaohooninternational.com/?p=593724",
            "Kaohoon International, Citi and DBS on Thai banks after 1Q26 - https://www.kaohooninternational.com/?p=581885",
            "Kaohoon International, CLSA upgrades Thai Oil - https://www.kaohooninternational.com/markets/573656",
            "TradingEconomics, BOT holds rate for 4th straight meeting - https://tradingeconomics.com/thailand/interest-rate/news/595680",
            "Kaohoon International, JPMorgan sees Thai stocks outperform - https://www.kaohooninternational.com/markets/587337",
        ],
        "stocks": stocks,
        "funds": funds,
    }
    # Atomic write: readers see either the old file or the complete new file, never a partial one.
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, out_path)
    print(f"wrote {out_path}: {len(stocks)} stocks, {len(funds)} funds, as of {out['as_of_prices']}")


if __name__ == "__main__":
    main()
