"""Contagion check (2026-11-01, Tho t31u): is a crypto or geopolitical event spilling into equities?

DISPLAY + ALERT + RISK-CONTEXT ONLY. Not used by signals, forecasts, weights or rebalance math (not backtested).
Triggers: a high-impact crypto card (crypto_events, last 7 days) or a geo event (geo_risk stress flag, or a
conflict whose 7-day news volume is >= 2x normal with >= 8 articles). For each trigger we measure real prices
from the last close BEFORE the event to the latest close (Yahoo Finance via market_history, free).

Documented thresholds (rules of thumb, NOT backtested):
  A crypto_stress    BTC <= -10% since the event, or BTC >= 20% below its 30-day high
  B crypto_equities  COIN or MSTR underperform SPY by >= 10 points since the event
  C vix              VIX up >= 5 points since the event, or VIX >= 25
  D us_equities      SPY <= -3% or QQQ <= -4% since the event
  E safe_havens      gold >= +3%, or USD/JPY <= -2% (yen up), or USD/CHF <= -2% (franc up)
  F thb              USD/THB >= +1.5% (baht weaker)
Level: contagion = at least 2 of C-F and one of them is C or D ("ลามสู่ตลาดหุ้น");
       watch = B, or exactly one of C-F ("เริ่มมีสัญญาณลาม"); contained = none ("ยังไม่ลาม").
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

import pandas as pd

from market_history import download_closes

ICT = ZoneInfo("Asia/Bangkok")
NY = ZoneInfo("America/New_York")
TICKERS = ["BTC-USD", "^VIX", "SPY", "QQQ", "COIN", "MSTR", "GC=F", "JPY=X", "CHF=X", "THB=X"]
TH = {"btc_drop_pct": -10.0, "btc_dd30_pct": -20.0, "crypto_eq_rel_pts": -10.0, "vix_pts": 5.0, "vix_level": 25.0,
      "spy_pct": -3.0, "qqq_pct": -4.0, "gold_pct": 3.0, "jpy_pct": -2.0, "chf_pct": -2.0, "thb_pct": 1.5}
RULE_TH = ("เกณฑ์ (ตั้งเอง ยังไม่ผ่าน backtest): ลามสู่หุ้น = เข้าเกณฑ์อย่างน้อย 2 ข้อจาก VIX ขึ้น ≥5 จุดหรือ ≥25 / SPY ลง ≥3% หรือ QQQ ลง ≥4% /"
           " หลุมหลบภัยถูกซื้อ (ทอง +3%, เยนหรือฟรังก์แข็ง 2%) / บาทอ่อน ≥1.5% โดยต้องมี VIX หรือหุ้นสหรัฐฯ ด้วย;"
           " เริ่มมีสัญญาณ = หุ้นคริปโต (COIN/MSTR) แย่กว่า SPY ≥10 จุด หรือเข้าเกณฑ์ 1 ข้อ; วัดจากราคาปิดก่อนเกิดเหตุถึงล่าสุด")
LEVEL_TH = {"contagion": "ลามสู่ตลาดหุ้นแล้ว", "watch": "เริ่มมีสัญญาณลาม", "contained": "ยังไม่ลามสู่ตลาดหุ้น",
            "pending": "ยังไม่มีราคาปิดหลังเกิดเหตุ"}
NEAR_TH = {"crypto_stress": "BTC ร่วง", "crypto_equities": "หุ้นคริปโตร่วง", "vix": "VIX", "us_equities": "หุ้นสหรัฐฯ/QQQ",
           "safe_havens": "หลุมหลบภัย", "thb": "เงินบาท"}
_CACHE: dict[str, Any] = {"t": 0.0, "v": None}


def _naive(s: pd.Series) -> pd.Series:
    s = s.dropna().copy()
    idx = pd.to_datetime(s.index)
    s.index = idx.tz_localize(None) if idx.tz is not None else idx
    return s.sort_index()


def _anchor_date(ts: datetime, crypto: bool) -> pd.Timestamp:
    """Last close strictly before the event: BTC daily bars are UTC days; other markets close 16:00 New York."""
    if crypto:
        return pd.Timestamp(ts.astimezone(timezone.utc).date()) - pd.Timedelta(days=1)
    ny = ts.astimezone(NY)
    d = pd.Timestamp(ny.date())
    return d if ny.hour >= 16 else d - pd.Timedelta(days=1)


def _move(s: Optional[pd.Series], ts: datetime, crypto: bool = False) -> dict[str, Any]:
    if s is None or s.dropna().empty:
        return {"status": "unknown"}
    s = _naive(s)
    a = _anchor_date(ts, crypto)
    before = s.loc[:a]
    after = s.loc[a + pd.Timedelta(days=1):]
    if before.empty:
        return {"status": "unknown"}
    out = {"anchor_date": str(before.index[-1].date()), "anchor": round(float(before.iloc[-1]), 4),
           "last_date": str(s.index[-1].date()), "last": round(float(s.iloc[-1]), 4)}
    if after.empty:
        out["status"] = "pending"
        return out
    out["chg_pct"] = round((float(s.iloc[-1]) / float(before.iloc[-1]) - 1) * 100, 2)
    out["chg_abs"] = round(float(s.iloc[-1]) - float(before.iloc[-1]), 3)
    out["stale"] = (pd.Timestamp(datetime.now(ICT).date()) - s.index[-1]).days > 7
    return out


def _evaluate(px: pd.DataFrame, ts: datetime) -> dict[str, Any]:
    g = lambda t: px[t] if t in px else None  # noqa: E731
    m = {t: _move(g(t), ts, crypto=(t == "BTC-USD")) for t in TICKERS}
    btc = g("BTC-USD")
    if btc is not None and not btc.dropna().empty:
        b = _naive(btc)
        hi30 = float(b.iloc[-30:].max())
        m["BTC-USD"]["dd_30d_pct"] = round((float(b.iloc[-1]) / hi30 - 1) * 100, 2)
    pend = [t for t in ("SPY", "^VIX") if m[t].get("status") == "pending"]
    c = lambda t: m[t].get("chg_pct")  # noqa: E731
    crit: dict[str, dict[str, Any]] = {}
    crit["crypto_stress"] = {"hit": (c("BTC-USD") is not None and c("BTC-USD") <= TH["btc_drop_pct"])
                             or (m["BTC-USD"].get("dd_30d_pct") is not None and m["BTC-USD"]["dd_30d_pct"] <= TH["btc_dd30_pct"]),
                             "detail_th": f"BTC {c('BTC-USD')}% ตั้งแต่เกิดเหตุ, ต่ำกว่าจุดสูงสุด 30 วัน {m['BTC-USD'].get('dd_30d_pct')}%"}
    rel = {}
    for t in ("COIN", "MSTR"):
        if c(t) is not None and c("SPY") is not None:
            rel[t] = round(c(t) - c("SPY"), 2)
    crit["crypto_equities"] = {"hit": any(v <= TH["crypto_eq_rel_pts"] for v in rel.values()), "rel_vs_spy_pts": rel,
                               "detail_th": "หุ้นคริปโตเทียบ SPY: " + ", ".join(f"{k} {v:+.1f} จุด" for k, v in rel.items()) if rel else "unknown"}
    vix_last = m["^VIX"].get("last")
    crit["vix"] = {"hit": (m["^VIX"].get("chg_abs") is not None and m["^VIX"]["chg_abs"] >= TH["vix_pts"]) or (vix_last is not None and vix_last >= TH["vix_level"]
                   and m["^VIX"].get("status") != "pending"),
                   "detail_th": f"VIX {vix_last} ({m['^VIX'].get('chg_abs')} จุด ตั้งแต่เกิดเหตุ)"}
    crit["us_equities"] = {"hit": (c("SPY") is not None and c("SPY") <= TH["spy_pct"]) or (c("QQQ") is not None and c("QQQ") <= TH["qqq_pct"]),
                           "detail_th": f"SPY {c('SPY')}%, QQQ {c('QQQ')}%"}
    crit["safe_havens"] = {"hit": (c("GC=F") is not None and c("GC=F") >= TH["gold_pct"]) or (c("JPY=X") is not None and c("JPY=X") <= TH["jpy_pct"])
                           or (c("CHF=X") is not None and c("CHF=X") <= TH["chf_pct"]),
                           "detail_th": f"ทอง {c('GC=F')}%, USD/JPY {c('JPY=X')}%, USD/CHF {c('CHF=X')}%"}
    crit["thb"] = {"hit": c("THB=X") is not None and c("THB=X") >= TH["thb_pct"], "detail_th": f"USD/THB {c('THB=X')}%"}
    # "near" = at least 75% of the way to a threshold (shown, never triggers the alert)
    r = lambda v, th: (v / th) if v is not None and th else 0.0  # noqa: E731
    near_ratio = {
        "crypto_stress": max(r(c("BTC-USD"), TH["btc_drop_pct"]), r(m["BTC-USD"].get("dd_30d_pct"), TH["btc_dd30_pct"])),
        "crypto_equities": max([r(v, TH["crypto_eq_rel_pts"]) for v in rel.values()] or [0.0]),
        "vix": max(r(m["^VIX"].get("chg_abs"), TH["vix_pts"]), r(vix_last, TH["vix_level"]) - 0.15),
        "us_equities": max(r(c("SPY"), TH["spy_pct"]), r(c("QQQ"), TH["qqq_pct"])),
        "safe_havens": max(r(c("GC=F"), TH["gold_pct"]), r(c("JPY=X"), TH["jpy_pct"]), r(c("CHF=X"), TH["chf_pct"])),
        "thb": r(c("THB=X"), TH["thb_pct"]),
    }
    for k, v in near_ratio.items():
        crit[k]["pct_of_threshold"] = round(v * 100)
        crit[k]["near"] = (not crit[k]["hit"]) and v >= 0.75
    broad = [k for k in ("vix", "us_equities", "safe_havens", "thb") if crit[k]["hit"]]
    if pend:
        level = "pending"
    elif len(broad) >= 2 and ("vix" in broad or "us_equities" in broad):
        level = "contagion"
    elif crit["crypto_equities"]["hit"] or len(broad) == 1:
        level = "watch"
    else:
        level = "contained"
    near = [k for k, v in crit.items() if v.get("near")]
    level_th = LEVEL_TH[level] + (f" (ใกล้เกณฑ์: {', '.join(NEAR_TH[k] for k in near)})" if near and level in ("contained", "watch") else "")
    return {"level": level, "level_th": level_th, "criteria": crit, "broad_hits": broad, "near": near, "moves": m}


async def _triggers(pool: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        import crypto_events as ce
        cur = await ce.current(pool, hours=168)
        for card in cur.get("cards", []):
            ver = card.get("verified") or {}
            at = ver.get("event_at_utc") or card.get("at")  # verified event time beats the first-article time
            ts = datetime.fromisoformat(str(at)) if at else None
            if ts is None:
                continue
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=ICT)
            title = ver.get("headline_th") or (card.get("headline") if card.get("type") == "news" else "BTC price move")
            out.append({"kind": "crypto", "key": ver.get("key") or f"crypto:{card.get('category', card.get('type'))}:{card.get('entity', '')}:{ts.date()}",
                        "title": title, "category_th": card.get("category_th") or "ราคา BTC", "at": ts})
    except Exception:  # noqa: BLE001
        pass
    try:
        import geo_risk as geo
        p = await geo.latest(pool)
        if p:
            as_of = datetime.fromisoformat(str(p.get("generated_at") or p.get("as_of"))) if (p.get("generated_at") or p.get("as_of")) else datetime.now(ICT)
            if as_of.tzinfo is None:
                as_of = as_of.replace(tzinfo=ICT)
            start = as_of - timedelta(days=7)  # geo events build up: measure over the last week
            names = {c["key"]: c.get("name_th") for c in (p.get("assessment") or {}).get("conflicts", [])}
            for k, n in (p.get("news") or {}).items():
                if (n.get("volume_ratio") or 0) >= 2 and (n.get("articles_7d") or 0) >= 8:
                    out.append({"kind": "geo", "key": f"geo:{k}:{start.date()}", "title": f"ข่าว{names.get(k, k)}เพิ่มขึ้น x{n['volume_ratio']}",
                                "category_th": "ภูมิรัฐศาสตร์", "at": start})
            for f in p.get("stress_flags") or []:
                out.append({"kind": "geo", "key": f"geo:flag:{f['ticker']}:{start.date()}", "title": f"ตัวชี้วัดตึงเครียด: {f['name']}",
                            "category_th": "ภูมิรัฐศาสตร์", "at": start})
    except Exception:  # noqa: BLE001
        pass
    return out


async def status(pool: Any, max_age_s: int = 900) -> dict[str, Any]:
    if _CACHE["v"] is not None and time.time() - _CACHE["t"] < max_age_s:
        return _CACHE["v"]
    trig = await _triggers(pool)
    px = await asyncio.to_thread(download_closes, TICKERS, None, "6mo", 900) if trig else pd.DataFrame()
    events = []
    for t in trig:
        ev = _evaluate(px, t["at"])
        events.append({**{k: v for k, v in t.items() if k != "at"}, "at": t["at"].astimezone(ICT).isoformat(timespec="minutes"), **ev})
    order = {"contagion": 3, "watch": 2, "pending": 1, "contained": 0}
    worst = max(events, key=lambda e: order[e["level"]]) if events else None
    res = {"checked_at": datetime.now(ICT).isoformat(timespec="minutes"), "events": events,
           "level": worst["level"] if worst else "none", "level_th": worst["level_th"] if worst else "ไม่มีเหตุการณ์ที่ต้องตรวจ",
           "thresholds": TH, "rule_th": RULE_TH, "source": "Yahoo Finance daily closes via yfinance (free)",
           "use": "display + LINE alert + advisor risk context only - not used in signals, forecasts or rebalance (not backtested)"}
    _CACHE.update(t=time.time(), v=res)
    return res


def summary_th(ev: dict[str, Any]) -> str:
    m = ev["moves"]
    parts = [f"BTC {m['BTC-USD'].get('chg_pct')}%", f"SPY {m['SPY'].get('chg_pct')}%", f"QQQ {m['QQQ'].get('chg_pct')}%",
             f"VIX {m['^VIX'].get('last')} ({m['^VIX'].get('chg_abs'):+} จุด)" if m["^VIX"].get("chg_abs") is not None else "VIX unknown",
             f"COIN {m['COIN'].get('chg_pct')}%", f"MSTR {m['MSTR'].get('chg_pct')}%", f"USD/THB {m['THB=X'].get('chg_pct')}%"]
    return f"{ev['level_th']} - " + ", ".join(parts) + f" (ตั้งแต่ราคาปิด {m['SPY'].get('anchor_date')} ถึง {m['SPY'].get('last_date')})"


def render_text(st: dict[str, Any]) -> str:
    lines = ["=== CONTAGION CHECK (crypto/geo event -> equities; display/alert/risk context only, thresholds are rules of thumb, not backtested) ==="]
    if not st.get("events"):
        lines.append("  No active crypto/geo trigger in the last 7 days.")
        return "\n".join(lines)
    for e in st["events"]:
        c = e["criteria"]
        lines.append(f"- [{e['kind']}] {e['title']} (event {e['at']}): level={e['level']}; " + summary_th(e))
        lines.append("  criteria hit: " + (", ".join(k for k, v in c.items() if v["hit"]) or "none"))
    lines.append("Rules: no sell/trim advice for PTTEP/SCB; never place orders; context only.")
    return "\n".join(lines)


def render_brief(st: Optional[dict[str, Any]]) -> str:
    if not st or not st.get("events"):
        return "### ตรวจการลามของเหตุการณ์คริปโต/ภูมิรัฐศาสตร์\n- ไม่มีเหตุการณ์ที่ต้องตรวจใน 7 วัน"
    lines = ["### ตรวจการลามของเหตุการณ์คริปโต/ภูมิรัฐศาสตร์ (ข้อมูลประกอบ ไม่ใช่สัญญาณ)"]
    for e in st["events"]:
        lines.append(f"- {e['title'][:90]}: {summary_th(e)}")
    return "\n".join(lines)
