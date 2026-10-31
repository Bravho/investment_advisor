"""'What moved my portfolio sectors' (2026-10-31, replaces the fabricated sector score bars on /sentiment).

One plain line per sector tied to Tho's holdings: the real 1-month % change of ONE named proxy (yfinance daily
closes, 21 sessions) with its dates, an up/down arrow, and the most relevant recent news story (7 days) from the
existing news pipeline. No composite scores, no multipliers. Missing data -> 'unknown'. The news line is shown as
'related news', not as a proven cause.
"""
from __future__ import annotations

import asyncio
import re
import time
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd

import news_feed as nf
from market_history import download_closes

SECTORS: list[dict[str, Any]] = [
    dict(key="thai_banks", name_th="ธนาคารไทย", holding="SCB", proxy="SCB.BK", proxy_th="ราคาหุ้น SCB",
         topics={"thai_banks"}, tickers={"SCB.BK", "KBANK.BK", "BBL.BK", "KTB.BK", "TTB.BK"},
         headline=r"\bbanks?\b|\bSCBX?\b|KBank|Kasikorn|Bangkok Bank|Krungthai|Bank of Thailand|\blending\b|\bloans?\b"),
    dict(key="energy", name_th="พลังงาน / น้ำมัน", holding="PTTEP", proxy="PTTEP.BK", proxy_th="ราคาหุ้น PTTEP",
         topics={"oil"}, tickers={"PTTEP.BK", "PTT.BK", "TOP.BK", "BZ=F", "CL=F"},
         headline=r"\boil\b|\bcrude\b|\bBrent\b|\bOPEC|\bPTTEP?\b|\bLNG\b|\bgas (price|field|output)"),
    dict(key="gold", name_th="ทองคำ", holding="SCBGOLDE", proxy="XAUTHB", proxy_th="ราคาทองในรูปเงินบาท (ทองโลก × USD/THB)",
         topics={"gold"}, tickers={"GC=F"}, headline=r"\bgold\b|\bbullion\b"),
    dict(key="thai_market", name_th="ตลาดหุ้นไทย", holding="ThaiESG", proxy="TDEX.BK", proxy_th="TDEX (กองทุนดัชนี SET50)",
         topics={"thai_market"}, tickers={"TDEX.BK"},
         headline=r"\bSET\b|SET50|Thai (stocks?|shares|equities|bourse|stock market)|Stock Exchange of Thailand|\bbaht\b|Thai(land's)? (economy|GDP|exports)"),
    dict(key="us_tech", name_th="หุ้นเทคสหรัฐฯ", holding=None, proxy="XLK", proxy_th="กองทุน XLK (หุ้นเทคใน S&P 500)",
         topics=set(), tickers={"XLK", "QQQ", "AAPL", "MSFT", "NVDA", "GOOGL", "GOOG", "AMZN", "META", "AVGO", "AMD", "TSM", "ORCL"},
         headline=r"\btech\b|\bAI\b|\bchips?\b|semiconductor|Nvidia|Apple|Microsoft|Alphabet|Google|Amazon|Meta\b|Nasdaq"),
]
_CACHE: dict[str, Any] = {}
_SENT_END = re.compile(r"(?<=[.!?。])\s+|\n")


def _move(closes: pd.DataFrame, proxy: str) -> dict[str, Any]:
    if proxy == "XAUTHB":
        s = (closes["GC=F"] * closes["THB=X"]).dropna() if "GC=F" in closes and "THB=X" in closes else pd.Series(dtype=float)
    else:
        s = closes[proxy].dropna() if proxy in closes else pd.Series(dtype=float)
    if len(s) <= 21:
        return {"change_1m_pct": None, "status": "unknown"}
    a, b = float(s.iloc[-1]), float(s.iloc[-22])
    return {"change_1m_pct": round((a / b - 1) * 100, 1), "last": a, "as_of": s.index[-1].date().isoformat(),
            "from_date": s.index[-22].date().isoformat(), "status": "ok"}


def _pick_news(items: list[dict[str, Any]], sec: dict[str, Any]) -> Optional[dict[str, Any]]:
    hits = [i for i in items if (set(i.get("topics") or []) & sec["topics"]) or (set(i.get("tickers") or []) & sec["tickers"])]
    if not hits:
        return None
    rx = re.compile(sec["headline"], re.I)
    imp = {"high": 2, "medium": 1}
    # most relevant first: sector named in the headline > impact > strength of sentiment > has Thai summary > newest
    hits.sort(key=lambda i: (bool(rx.search(i.get("title") or "")), imp.get(i.get("impact_level"), 0), round(abs(i.get("score") or 0), 1),
                             i.get("summary_status") == "llm", i.get("published_at") or ""), reverse=True)
    if not rx.search(hits[0].get("title") or ""):
        return {"line_th": None, "title": None, "n_related_7d": len(hits), "none_in_headline": True}
    i = hits[0]
    line = _SENT_END.split(i["summary_th"])[0].strip() if i.get("summary_status") == "llm" and i.get("summary_th") else None
    return {"line_th": line, "title": i.get("title"), "url": i.get("url"), "published_at": i.get("published_at"),
            "sentiment_th": i.get("sentiment_th"), "sentiment": i.get("sentiment"), "n_related_7d": len(hits),
            "sources": i.get("sources")}


async def build(pool: Any, max_age: int = 1800) -> dict[str, Any]:
    hit = _CACHE.get("moves")
    if hit and time.time() - hit[0] < max_age:
        return hit[1]
    tick = sorted({s["proxy"] for s in SECTORS if s["proxy"] != "XAUTHB"} | {"GC=F", "THB=X"})
    closes = await asyncio.to_thread(download_closes, tick, None, "6mo", 1800)
    try:
        feed = await nf.build_feed(pool, hours=168, limit=2000, include_crypto=False)
        items, news_err = feed.get("items") or [], None
    except Exception as exc:  # noqa: BLE001
        items, news_err = [], str(exc)[:200]
    lines = []
    for sec in SECTORS:
        m = _move(closes, sec["proxy"])
        ch = m.get("change_1m_pct")
        lines.append({"key": sec["key"], "name_th": sec["name_th"], "holding": sec["holding"], "proxy": sec["proxy"], "proxy_th": sec["proxy_th"],
                      **m, "direction": None if ch is None else ("up" if ch > 0 else "down" if ch < 0 else "flat"),
                      "news": _pick_news(items, sec)})
    out = {"generated_at": datetime.now(timezone.utc).isoformat(), "lines": lines, "news_error": news_err,
           "method_th": "การเปลี่ยนแปลง 1 เดือน = ราคาปิดล่าสุดเทียบกับ 21 วันทำการก่อนหน้า (yfinance) · "
                        "ข่าว = ข่าวที่เกี่ยวข้องมากที่สุดใน 7 วันจากระบบข่าว (ไม่ได้ยืนยันว่าเป็นสาเหตุ)"}
    _CACHE["moves"] = (time.time(), out)
    return out
