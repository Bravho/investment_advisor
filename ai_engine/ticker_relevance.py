"""ticker_relevance.py - is a ticker genuinely mentioned in a news article? (added 2026-10-31)

Why: the sentiment pipeline over-tagged articles. Examples found on 2026-10-31:
  * "TRUE" matched the English word "true" (text was upper-cased before matching) -> 26 TRUE.BK tags in 7 days;
    the same trap exists for DELTA ("delta") and GULF ("Gulf" = Persian Gulf).
  * the LLM returned OTC symbols for companies named once in a list of decliners (SK hynix -> SKHXY,
    Samsung -> SSNLF, Advantest -> ADVTK ...), and one generic Wall Street story got 9 tickers.
Rule now: a ticker is kept only if its SYMBOL appears as a case-sensitive token, or one of its known
company NAMES appears; ambiguous English words need the company name. Max MAX_TICKERS per article.
Pure python, no network - used by ai_engine (writer) and portfolio_engine (feed read-time filter).
"""
from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional

MAX_TICKERS = 6

# symbol -> company names / aliases (case-insensitive phrase match)
ALIASES: Dict[str, List[str]] = {
    "PTTEP.BK": ["PTTEP", "PTT Exploration"], "SCB.BK": ["SCB X", "SCBX", "Siam Commercial Bank", "SCB"],
    "PTT.BK": ["PTT Pcl", "PTT Public", "PTT Group", "PTT"], "KBANK.BK": ["Kasikornbank", "KBank"],
    "BBL.BK": ["Bangkok Bank"], "KTB.BK": ["Krung Thai Bank", "Krungthai"], "TTB.BK": ["TMBThanachart", "ttb bank"],
    "ADVANC.BK": ["Advanced Info Service", "AIS"], "AOT.BK": ["Airports of Thailand"], "TOP.BK": ["Thai Oil", "Thaioil"],
    "IRPC.BK": ["IRPC"], "BAFS.BK": ["Bangkok Aviation Fuel"], "CPALL.BK": ["CP All", "7-Eleven Thailand"],
    "CPF.BK": ["Charoen Pokphand Foods"], "BDMS.BK": ["Bangkok Dusit Medical"],
    "TRUE.BK": ["True Corp", "True Corporation", "TRUE.BK"], "DELTA.BK": ["Delta Electronics", "DELTA.BK"],
    "GULF.BK": ["Gulf Energy", "Gulf Development", "GULF.BK"],
    "SCBGOLDE": ["SCBGOLDE", "SCB Gold"], "GC=F": ["gold price", "gold prices", "bullion", "gold futures", "spot gold"],
    "AAPL": ["Apple"], "MSFT": ["Microsoft"], "GOOGL": ["Alphabet", "Google"], "AMZN": ["Amazon"], "META": ["Meta Platforms", "Facebook"],
    "NVDA": ["Nvidia"], "TSLA": ["Tesla"], "INTC": ["Intel"], "AMD": ["Advanced Micro Devices"], "AVGO": ["Broadcom"],
    "MU": ["Micron"], "TSM": ["TSMC", "Taiwan Semiconductor"], "SPY": ["S&P 500", "S&P500"], "QQQ": ["Nasdaq 100", "Nasdaq-100"],
    "XOM": ["Exxon"], "COIN": ["Coinbase"], "MSTR": ["MicroStrategy", "Strategy Inc"], "HOOD": ["Robinhood"],
    "BTC-USD": ["Bitcoin", "BTC"], "ETH-USD": ["Ethereum", "Ether"], "SOL-USD": ["Solana"],
    "GLDM": ["GLDM"], "IAU": ["iShares Gold"], "GDX": ["gold miners"], "FXI": ["China large-cap", "FXI"],
    "VNM": ["Vietnam ETF", "VNM"], "EWJ": ["MSCI Japan"], "INDA": ["MSCI India"],
}
# symbols that are also ordinary words: bare-symbol matching is never enough
AMBIGUOUS = {"TRUE", "DELTA", "GULF", "AOT", "MU", "ON", "IT", "ALL", "NOW", "META", "COIN", "HOOD", "TOP", "AIS"}
# LLM shorthand -> canonical symbol
CANON = {"BTC": "BTC-USD", "ETH": "ETH-USD", "SOL": "SOL-USD", "XRP": "XRP-USD", "BNB": "BNB-USD",
         "GOOG": "GOOGL", "PTTEP": "PTTEP.BK", "SCB": "SCB.BK", "PTT": "PTT.BK", "KBANK": "KBANK.BK"}


def canonical(ticker: str) -> str:
    t = str(ticker or "").strip().upper()
    return CANON.get(t, t)


def _phrase(text: str, phrase: str) -> bool:
    return re.search(r"(?<![A-Za-z0-9])" + re.escape(phrase) + r"(?![A-Za-z0-9])", text, re.I) is not None


def mentioned(ticker: str, text: str, extra_aliases: Optional[Dict[str, Iterable[str]]] = None) -> bool:
    """True if the ticker's symbol (case-sensitive token) or a known company name appears in text."""
    t = canonical(ticker)
    base = t.split(".")[0].split("-")[0].split("=")[0]
    names = list(ALIASES.get(t, [])) + list((extra_aliases or {}).get(t, []))
    if base and base not in AMBIGUOUS and len(base) >= 2:
        if re.search(r"(?<![A-Za-z0-9$])\$?" + re.escape(base) + r"(?![A-Za-z0-9])", text):  # case-sensitive symbol
            return True
    if t != base and t in text:  # e.g. "PTTEP.BK"
        return True
    for n in names:
        if n.upper() == n and len(n) <= 5:  # short upper-case alias: case-sensitive (avoid "ais"/"scb" noise)
            if re.search(r"(?<![A-Za-z0-9])" + re.escape(n) + r"(?![A-Za-z0-9])", text):
                return True
        elif _phrase(text, n):
            return True
    return False


def filter_tickers(tickers: Iterable[str], text: str, extra_aliases: Optional[Dict[str, Iterable[str]]] = None,
                   max_n: int = MAX_TICKERS) -> List[str]:
    """Keep only tickers genuinely mentioned in text; order of first mention in the text decides the cap."""
    keep = []
    for t in dict.fromkeys(canonical(x) for x in tickers if x):
        if mentioned(t, text, extra_aliases):
            keep.append(t)
    def first_pos(t: str) -> int:
        cands = [t.split(".")[0].split("-")[0]] + list(ALIASES.get(t, [])) + list((extra_aliases or {}).get(t, []))
        pos = [m.start() for c in cands for m in [re.search(re.escape(c), text, re.I)] if m]
        return min(pos) if pos else 10 ** 9
    return sorted(keep, key=first_pos)[:max_n]
