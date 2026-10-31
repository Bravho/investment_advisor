"""Crypto high-impact events card (2026-11-01, Tho).

Tho: the crypto card shows ONLY high-impact events that strongly affect the trend; routine crypto news is filtered
out; show 'ไม่มีเหตุการณ์สำคัญ' when nothing qualifies. Crypto stays OUT of the main market-mood verdict and OUT of
signals (display only - nothing here is read by signals, predictions, construction or trade plans).

Rule (thresholds in THRESHOLDS, chosen by replay() so the card yields 0-3 cards/week):
  A  event news   - a crypto story (crypto ticker or crypto words in the headline) whose headline matches an event
                    category (regulation/SEC/ban/lawsuit, ETF approval/rejection/flows, exchange hack/collapse/
                    withdrawal halt, stablecoin de-peg, government BTC reserve, >= $1bn liquidations) AND the local
                    LLM rated it impact='high' AND |sentiment| >= min_abs_score; at least min_sources distinct sources.
  B  price move   - BTC-USD daily close: |1-day return| >= k_sigma x trailing 1y daily stdev, or |7-day return| >=
                    pct_7d (fires once per 7 days), or the close crosses its 200-day average (fires once per side
                    per cross_cooldown days).
  Grouping        - stories about the same event (category + main entity, e.g. 'hack:binance') within 72h form ONE
                    card; a price card gets the most relevant crypto story of that day attached (labelled
                    'related news', not proven cause). At most max_cards cards in any 72h window (strongest kept).
"""
from __future__ import annotations

import asyncio
import math
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

import pandas as pd

ICT = ZoneInfo("Asia/Bangkok")
CRYPTO_TICKER_RE = r"^(BTC|ETH|SOL|XRP|DOGE|ADA|BNB|AVAX|DOT|LINK|LTC|TRX|TON|SHIB|MATIC|USDT|USDC)(-USD)?$|^(MSTR|COIN|IBIT|FBTC|GBTC|ETHA|MARA|RIOT)$"
CRYPTO_TITLE_RE = r"bitcoin|\mbtc\M|ethereum|\meth\M|crypto|stablecoin|binance|coinbase|solana|\mxrp\M|dogecoin|blockchain|\mdefi\M|tether|altcoin|คริปโต|บิตคอยน์"
CATEGORIES: dict[str, tuple[str, str]] = {
    "regulation": ("กฎหมาย/หน่วยงานกำกับ", r"\bsec\b (approv|reject|charg|sues|su(ed|ing)|rul|drops?|ends?|clos)|\bcftc\b|regulat(or|ion|ory) (crack|ban|approv|framework|bill|law)|\bban(s|ned)?\b (crypto|bitcoin|trading|mining)|(crypto|bitcoin|stablecoin|market.structure) (bill|law|act)\b|legislat|senate|congress|supreme court|white house|executive order|mica\b|ก\.ล\.ต|กฎหมาย"),
    "etf": ("ETF (อนุมัติ/เงินไหล)", r"\betfs?\b.*(approv|reject|inflow|outflow|pull|record|launch|flows?)|(approv|reject|inflow|outflow).*\betfs?\b"),
    "exchange": ("exchange ถูกแฮ็ก/ล้ม", r"hack|exploit|breach|stolen|collapse|insolven|bankrupt|halt(s|ed)? withdraw|freez(e|es) withdraw|withdrawals? (halt|paus|suspend)"),
    "stablecoin": ("stablecoin หลุด peg", r"de-?peg|lost (its )?peg|stablecoin (crash|collapse|run)"),
    "reserve": ("ทุนสำรอง BTC ของรัฐ", r"strategic (bitcoin |crypto )?reserve|government (buys|sells) bitcoin|national bitcoin"),
    "liquidation": ("liquidation ขนาดใหญ่", r"liquidat\w* .*\$?\d+(\.\d+)? ?(bn|billion)|\$\d+(\.\d+)? ?(bn|billion) .*liquidat"),
}
ENTITIES = ["binance", "coinbase", "kraken", "bybit", "okx", "ftx", "tether", "usdc", "circle", "blackrock", "ibit", "grayscale",
            "fidelity", "sec", "cftc", "strategy", "microstrategy", "mt gox", "el salvador", "china", "trump", "congress", "senate"]
THRESHOLDS: dict[str, Any] = {"min_abs_score": 0.6, "min_sources": 1, "k_sigma": 2.5, "pct_7d": 15.0, "cross_cooldown_days": 30,
                              "group_hours": 72, "max_cards": 3, "window_hours": 72}
# ladder tried by replay() until cards/week <= 3 (each step stricter than the last)
LADDER: list[dict[str, Any]] = [
    {},
    {"min_sources": 2},
    {"min_sources": 3},
    {"min_sources": 3, "min_abs_score": 0.7},
    {"min_sources": 4, "min_abs_score": 0.7},
    {"min_sources": 4, "min_abs_score": 0.8, "max_cards": 2},
    {"min_sources": 4, "min_abs_score": 0.8, "max_cards": 2, "k_sigma": 3.0, "pct_7d": 20.0},
    {"min_sources": 5, "min_abs_score": 0.8, "max_cards": 1, "k_sigma": 3.5, "pct_7d": 25.0},
]


def _category(title: str) -> Optional[str]:
    t = title.lower()
    for k, (_, rx) in CATEGORIES.items():
        if re.search(rx, t):
            if k == "liquidation" and _bn_amount(t) < MIN_LIQUIDATION_BN:
                continue  # ~$1bn liquidation days are routine in crypto; only mega-liquidations qualify
            return k
    return None


MIN_LIQUIDATION_BN = 2.0


def _bn_amount(t: str) -> float:
    vals = [float(m.group(1)) for m in re.finditer(r"\$?(\d+(?:\.\d+)?) ?(?:bn|billion)", t)]
    return max(vals) if vals else 0.0


def _entity(title: str) -> str:
    t = title.lower()
    for e in ENTITIES:
        if re.search(r"\b" + re.escape(e) + r"\b", t):
            return "strategy" if e == "microstrategy" else e
    return "-"


async def _crypto_stories(pool: Any, since: datetime, until: datetime, th: dict[str, Any]) -> list[dict[str, Any]]:
    rows = await pool.fetch(
        """SELECT a.id, a.title, a.source, a.url, a.published_at, max(abs(s.score)) AS abs_s,
                  (array_agg(s.score ORDER BY abs(s.score) DESC))[1] AS score
           FROM sentiment_scores s JOIN news_articles a ON a.id = s.article_id
           WHERE a.published_at >= $1 AND a.published_at < $2 AND s.impact_level = 'high' AND abs(s.score) >= $3
             AND (COALESCE(s.ticker,'') ~* $4 OR a.title ~* $5)
           GROUP BY a.id, a.title, a.source, a.url, a.published_at""",
        since, until, float(th["min_abs_score"]), CRYPTO_TICKER_RE, CRYPTO_TITLE_RE)
    out = []
    for r in rows:
        cat = _category(r["title"] or "")
        if cat:
            out.append({"id": r["id"], "title": r["title"], "source": r["source"], "url": r["url"], "published_at": r["published_at"],
                        "score": float(r["score"]), "category": cat, "entity": _entity(r["title"] or "")})
    return out


def _news_cards(stories: list[dict[str, Any]], th: dict[str, Any]) -> list[dict[str, Any]]:
    stories = sorted(stories, key=lambda s: s["published_at"])
    groups: list[dict[str, Any]] = []
    seen_titles: set[str] = set()
    for s in stories:
        tkey = re.sub(r"[^a-z0-9]+", " ", (s["title"] or "").lower()).strip()[:90]
        if tkey in seen_titles:  # same article syndicated into several feeds (e.g. Yahoo BTC-USD and ETH-USD)
            continue
        seen_titles.add(tkey)
        key = f"{s['category']}:{s['entity']}"
        # same category within group_hours = same story if the named entity matches or either side names none
        g = next((g for g in groups if g["cat"] == s["category"]
                  and (g["entity"] == s["entity"] or "-" in (g["entity"], s["entity"]))
                  and s["published_at"] - g["first"] <= timedelta(hours=th["group_hours"])), None)
        if g is not None and g["entity"] == "-" and s["entity"] != "-":
            g["entity"] = s["entity"]
        if g is None:
            g = {"key": key, "cat": s["category"], "entity": s["entity"], "first": s["published_at"], "items": []}
            groups.append(g)
        g["items"].append(s)
    cards = []
    for g in groups:
        srcs = {_publisher(i["url"], i["source"]) for i in g["items"]}  # distinct publishers, not feed names
        if len(srcs) < th["min_sources"]:
            continue
        lead = max(g["items"], key=lambda i: abs(i["score"]))
        avg = sum(i["score"] for i in g["items"]) / len(g["items"])
        cat = g["items"][0]["category"]
        cards.append({"type": "news", "category": cat, "category_th": CATEGORIES[cat][0], "entity": g["entity"],
                      "at": g["first"], "headline": lead["title"], "url": lead["url"], "source": lead["source"],
                      "n_stories": len(g["items"]), "n_sources": len(srcs), "avg_score": round(avg, 2),
                      "direction": "ลบ" if avg < 0 else "บวก",
                      "strength": len(srcs) * abs(avg),
                      "headlines": [{"title": i["title"], "source": i["source"], "url": i["url"]} for i in sorted(g["items"], key=lambda i: -abs(i["score"]))[:4]]})
    return cards


def _price_cards(close: pd.Series, th: dict[str, Any], start: date) -> list[dict[str, Any]]:
    close = close.dropna()
    r1 = close.pct_change()
    sd = r1.rolling(365, min_periods=200).std().shift(1)  # trailing 1y of daily returns (crypto trades 7 days)
    r7 = close / close.shift(7) - 1
    sma = close.rolling(200).mean()
    cards, last7, lastx = [], None, {}
    for d in close.index:
        if d.date() < start or pd.isna(sd.get(d)):
            continue
        px = float(close[d])
        if abs(r1[d]) >= th["k_sigma"] * sd[d]:
            cards.append({"type": "price", "trigger": "1d", "at": _ts(d), "value_pct": round(float(r1[d]) * 100, 2),
                          "threshold": f"±{th['k_sigma']}×SD รายวัน 1 ปี (= ±{th['k_sigma'] * float(sd[d]) * 100:.1f}%)", "price": round(px, 0),
                          "strength": abs(float(r1[d])) / float(sd[d])})
        if not pd.isna(r7.get(d)) and abs(r7[d]) * 100 >= th["pct_7d"] and (last7 is None or (d - last7).days >= 7):
            last7 = d
            cards.append({"type": "price", "trigger": "7d", "at": _ts(d), "value_pct": round(float(r7[d]) * 100, 2),
                          "threshold": f"±{th['pct_7d']:.0f}% ใน 7 วัน", "price": round(px, 0), "strength": abs(float(r7[d])) * 100 / th["pct_7d"] * 2})
        prev = close.index.get_loc(d) - 1
        if prev >= 0 and not pd.isna(sma.get(d)) and not pd.isna(sma.iloc[prev]):
            above_now, above_prev = px > sma[d], float(close.iloc[prev]) > float(sma.iloc[prev])
            side = "up" if above_now else "down"
            if above_now != above_prev and (side not in lastx or (d - lastx[side]).days >= th["cross_cooldown_days"]):
                lastx[side] = d
                cards.append({"type": "price", "trigger": "sma200", "at": _ts(d), "value_pct": round((px / float(sma[d]) - 1) * 100, 2),
                              "threshold": "ราคาปิดตัดเส้นเฉลี่ย 200 วัน " + ("ขึ้น" if above_now else "ลง"), "price": round(px, 0), "strength": 1.5})
    return cards


def _group_price(cards: list[dict[str, Any]], th: dict[str, Any]) -> list[dict[str, Any]]:
    """Price triggers within group_hours of each other are ONE market event (e.g. a crash fires 1d, 7d and SMA200)."""
    out: list[dict[str, Any]] = []
    for c in sorted(cards, key=lambda c: c["at"]):
        g = out[-1] if out and (c["at"] - out[-1]["_last"]).total_seconds() <= th["group_hours"] * 3600 else None
        if g is None:
            out.append({**c, "triggers": [{k: c[k] for k in ("trigger", "at", "value_pct", "threshold")}], "_last": c["at"]})
            continue
        g["triggers"].append({k: c[k] for k in ("trigger", "at", "value_pct", "threshold")})
        g["_last"] = c["at"]
        if c["strength"] > g["strength"]:
            g.update({k: c[k] for k in ("trigger", "at", "value_pct", "threshold", "price", "strength")})
    for g in out:
        g.pop("_last", None)
    return out


def _cap(cards: list[dict[str, Any]], th: dict[str, Any]) -> list[dict[str, Any]]:
    """Keep at most max_cards in any window_hours window, strongest first."""
    kept: list[dict[str, Any]] = []
    for c in sorted(cards, key=lambda c: -c["strength"]):
        at = c["at"]
        near = [k for k in kept if abs((k["at"] - at).total_seconds()) < th["window_hours"] * 3600]
        if len(near) < th["max_cards"]:
            kept.append(c)
    return sorted(kept, key=lambda c: c["at"], reverse=True)


def _ts(x: Any) -> pd.Timestamp:
    t = pd.Timestamp(x)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


async def _btc(period: str = "2y") -> pd.Series:
    from market_history import download_closes
    df = await asyncio.to_thread(download_closes, ["BTC-USD"], None, period, 1800)
    return df["BTC-USD"].dropna()


async def build(pool: Any, since: datetime, until: datetime, th: dict[str, Any], btc: Optional[pd.Series] = None) -> list[dict[str, Any]]:
    news = _news_cards(await _crypto_stories(pool, since, until, th), th)
    btc = btc if btc is not None else await _btc()
    price = _price_cards(btc, th, since.date())
    price = _group_price([p for p in price if p["at"].date() < until.date() + timedelta(days=1)], th)
    for c in news:
        c["at"] = _ts(c["at"])
    for p in price:
        p["at"] = _ts(p["at"])
    return _cap(news + price, th)


async def _attach_related(pool: Any, card: dict[str, Any]) -> None:
    d0 = card["at"].to_pydatetime()
    r = await pool.fetchrow(
        """SELECT a.title, a.source, a.url FROM sentiment_scores s JOIN news_articles a ON a.id = s.article_id
           WHERE a.published_at BETWEEN $1 AND $2 AND (COALESCE(s.ticker,'') ~* $3 OR a.title ~* $4)
           ORDER BY (s.impact_level='high') DESC, abs(s.score) DESC LIMIT 1""",
        d0 - timedelta(days=1), d0 + timedelta(days=1), CRYPTO_TICKER_RE, CRYPTO_TITLE_RE)
    if r:
        card["related_news"] = {"title": r["title"], "source": r["source"], "url": r["url"], "note": "ข่าวที่เกี่ยวข้อง ไม่ใช่สาเหตุที่พิสูจน์แล้ว"}


def _jsonable(c: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in c.items() if k != "strength"}
    out["at"] = c["at"].tz_convert(ICT).isoformat(timespec="minutes")
    if out.get("triggers"):
        out["triggers"] = [{**t, "at": _ts(t["at"]).tz_convert(ICT).isoformat(timespec="minutes")} for t in out["triggers"]]
    return out


def _publisher(url: Any, source: Any) -> str:
    """Publisher = registrable domain of the article URL (uk.finance.yahoo.com -> yahoo.com)."""
    try:
        from urllib.parse import urlparse
        host = (urlparse(str(url or "")).netloc or "").lower().split(":")[0]
        parts = [p for p in host.split(".") if p]
        if len(parts) >= 3 and parts[-2] in ("co", "com", "or", "go", "ac", "in") and len(parts[-1]) == 2:
            return ".".join(parts[-3:])
        if len(parts) >= 2:
            return ".".join(parts[-2:])
    except Exception:  # noqa: BLE001
        pass
    return re.sub(r"\s*\(.*\)$", "", str(source or "unknown")).strip().lower()


async def current(pool: Any, hours: int = 72) -> dict[str, Any]:
    th = {**THRESHOLDS, **await active_thresholds(pool)}
    now = datetime.now(timezone.utc)
    cards = await build(pool, now - timedelta(hours=hours), now, th)
    cards = [c for c in cards if c["at"] >= _ts(now - timedelta(hours=hours))]
    for c in cards:
        if c["type"] == "price":
            await _attach_related(pool, c)
    return {"checked_at": datetime.now(ICT).isoformat(timespec="minutes"), "window_hours": hours, "cards": [_jsonable(c) for c in cards],
            "empty_text_th": "ไม่มีเหตุการณ์สำคัญ" if not cards else None, "thresholds": th,
            "rule_th": "แสดงเฉพาะเหตุการณ์คริปโตที่กระทบแนวโน้มแรง: ข่าวหมวดกฎหมาย/ETF/exchange ถูกแฮ็ก/stablecoin/ทุนสำรองรัฐ/liquidation ที่ผลกระทบสูง"
                       f" และ |sentiment| ≥ {th['min_abs_score']} จาก ≥ {th['min_sources']} แหล่ง หรือ BTC เคลื่อน ≥ {th['k_sigma']}×SD ใน 1 วัน / ≥ {th['pct_7d']:.0f}% ใน 7 วัน / ตัดเส้น 200 วัน"
                       f" · รวมข่าวเรื่องเดียวกันเป็น 1 การ์ด · ไม่เกิน {th['max_cards']} การ์ดใน 72 ชม. · ไม่นับในอารมณ์ตลาดหลักและไม่เข้า signals",
            "display_only": True}


DDL = """CREATE TABLE IF NOT EXISTS crypto_event_rule (
    id SERIAL PRIMARY KEY, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), thresholds JSONB NOT NULL, replay JSONB NOT NULL, active BOOLEAN NOT NULL DEFAULT true)"""


async def active_thresholds(pool: Any) -> dict[str, Any]:
    await pool.execute(DDL)
    r = await pool.fetchrow("SELECT thresholds FROM crypto_event_rule WHERE active ORDER BY id DESC LIMIT 1")
    if not r:
        return {}
    import json
    t = r["thresholds"]
    return json.loads(t) if isinstance(t, str) else dict(t)


async def replay(pool: Any, save: bool = True) -> dict[str, Any]:
    """Replay the rule over all stored scored news (A+B) and 1y of BTC (B alone); walk the LADDER until max cards/week <= 3."""
    import json
    first = await pool.fetchval("SELECT min(analyzed_at) FROM sentiment_scores")
    now = datetime.now(timezone.utc)
    btc = await _btc("2y")
    news_start = max(first, now - timedelta(days=365))
    tries = []
    chosen = None
    for step, extra in enumerate(LADDER):
        th = {**THRESHOLDS, **extra}
        cards = await build(pool, news_start, now, th, btc)
        price_1y = _cap(_group_price(_price_cards(btc, th, (now - timedelta(days=365)).date()), th), th)
        def weekly(cs: list[dict[str, Any]], start: datetime) -> dict[str, Any]:
            weeks = max(1, math.ceil((now - start).days / 7))
            counts = [0] * weeks
            for c in cs:
                i = int((c["at"] - _ts(start)).days // 7)
                if 0 <= i < weeks:
                    counts[i] += 1
            return {"weeks": weeks, "cards": len(cs), "per_week_mean": round(len(cs) / weeks, 2), "per_week_max": max(counts),
                    "weeks_over_3": sum(1 for c in counts if c > 3), "weeks_zero": sum(1 for c in counts if c == 0)}
        res = {"step": step, "thresholds": th, "news_plus_price": weekly(cards, news_start),
               "price_only_1y": weekly(price_1y, now - timedelta(days=365)),
               "by_type": {"news": sum(1 for c in cards if c["type"] == "news"), "price": sum(1 for c in cards if c["type"] == "price")},
               "sample": [_jsonable(c) | {"headlines": None} for c in cards[:6]]}
        tries.append(res)
        if res["news_plus_price"]["per_week_max"] <= 3 and res["price_only_1y"]["per_week_max"] <= 3:
            chosen = res
            break
    out = {"news_period": [str(news_start.date()), str(now.date())], "tries": tries, "chosen_step": chosen["step"] if chosen else None,
           "pass": chosen is not None, "criterion": "every calendar week 0-3 cards (news+price replay and price-only 1y replay)"}
    if save and chosen:
        await pool.execute(DDL)
        await pool.execute("UPDATE crypto_event_rule SET active=false WHERE active")
        await pool.execute("INSERT INTO crypto_event_rule (thresholds, replay) VALUES ($1::jsonb, $2::jsonb)",
                           json.dumps(chosen["thresholds"]), json.dumps(out, default=str))
    return out
