"""news_feed.py - readable, de-duplicated, Thai-summarised news feed (added 2026-10-31).

Tho: "ข่าวและสัญญาณล่าสุด should be more easy to understand and summarized. there is nothing in Bullish and Bearish tab".

Root cause of the empty tabs: the panel was fed from the `recommendations` table (advisory news->ticker
candidates). Those rows never stored a sentiment label - only a rationale string ("...candidate: strong_bearish...")
and a snapshot with `avg_score` - while the dashboard looked for `sentiment` / `sentiment_snapshot.score`,
found neither and defaulted every row to NEUTRAL. Each ticker of the same story also got its own card.

This module builds the feed from the source data instead (news_articles + sentiment_scores):
  * one card per story (grouped by article and by normalised headline across sources);
  * sentiment label derived from the score (strong_* folded into bullish / bearish);
  * tickers re-checked at read time with ticker_relevance (old over-tagged rows are filtered for display;
    nothing is deleted);
  * relevance to Tho's holdings (direct or via topic: gold -> SCBGOLDE, oil -> PTTEP, Thai banks -> SCB,
    Thai market -> ThaiESG funds) and watch list, sorted first;
  * short Thai summary from the local LLM (hermes3:8b via Ollama, free), cached in news_summaries;
    deterministic Thai template until the summary exists;
  * a daily digest (counts + 3-5 Thai takeaways).
Advisory only.
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from ticker_relevance import filter_tickers

LOGGER = logging.getLogger("portfolio_engine.news_feed")
SUMMARY_MODEL = os.getenv("OLLAMA_NEWS_SUMMARY_MODEL", "hermes3:8b")
DDL = """
CREATE TABLE IF NOT EXISTS news_summaries (
    article_id  UUID PRIMARY KEY,
    summary_th  TEXT NOT NULL,
    why_th      TEXT,
    model       VARCHAR(100),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""
CRYPTO = {"BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "BNB-USD", "BTC", "ETH", "SOL", "XRP", "BNB", "COIN", "MSTR", "IBIT", "HOOD"}
THAI_ESG = ["K-TNZ-ThaiESG", "ES-SETESG-ThaiESG-A", "TDSThaiESG-A"]
# topic -> (keywords, linked holdings, Thai explanation)
TOPICS = [
    ("gold", [r"\bgold\b", r"\bbullion\b"], ["SCBGOLDE"], "ราคาทองคำ → กองทุน SCBGOLDE"),
    ("oil", [r"\boil\b", r"\bbrent\b", r"\bcrude\b", r"\bOPEC\b", r"\bHormuz\b"], ["PTTEP.BK"], "ราคาน้ำมัน → PTTEP"),
    ("thai_banks", [r"Thai banks?", r"Bank of Thailand", r"Siam Commercial", r"\bSCBX?\b"], ["SCB.BK"], "ธนาคารไทย/ดอกเบี้ย → SCB"),
    ("thai_market", [r"\bSET\b index", r"\bSET50\b", r"Stock Exchange of Thailand", r"Thai (stocks|shares|equities|bourse|stock market)",
                     r"Thai(land's)? (economy|GDP|exports)", r"\bbaht\b"],
     THAI_ESG, "ตลาดหุ้น/เศรษฐกิจไทย → กองทุน ThaiESG"),
    ("usd_fed", [r"\bFed\b", r"Federal Reserve", r"\bdollar\b", r"Treasury yields?"], ["SCBGOLDE"], "ดอลลาร์/ดอกเบี้ยสหรัฐ → ทองคำและค่าเงินบาท"),
]
SENT_TH = {"strong_bullish": "บวกมาก", "bullish": "เชิงบวก", "neutral": "เป็นกลาง", "bearish": "เชิงลบ", "strong_bearish": "ลบมาก"}
IMPACT_TH = {"high": "ผลกระทบสูง", "medium": "ผลกระทบปานกลาง", "low": "ผลกระทบต่ำ"}
NAME_TH = {"PTTEP.BK": "PTTEP", "SCB.BK": "SCB", "SCBGOLDE": "SCBGOLDE (ทองคำ)", "K-TNZ-ThaiESG": "K-TNZ-ThaiESG",
           "ES-SETESG-ThaiESG-A": "ES-SETESG", "TDSThaiESG-A": "TDSThaiESG"}


# ------------------------------------------------------------------ labels
def signal_of(score: Optional[float], fallback: Optional[str] = None) -> str:
    if score is None:
        f = str(fallback or "neutral").lower()
        return f if f in SENT_TH else "neutral"
    s = float(score)
    if s > 0.6:
        return "strong_bullish"
    if s > 0.2:
        return "bullish"
    if s < -0.6:
        return "strong_bearish"
    if s < -0.2:
        return "bearish"
    return "neutral"


def base_label(signal: str) -> str:
    return "bullish" if "bullish" in signal else "bearish" if "bearish" in signal else "neutral"


def label_recommendation(row: dict[str, Any]) -> dict[str, Any]:
    """Derive sentiment for a recommendations row (old advisory rows stored no label). Read-only: nothing is updated."""
    snap = row.get("sentiment_snapshot")
    if isinstance(snap, str):
        try:
            snap = json.loads(snap)
        except ValueError:
            snap = {}
    snap = snap or {}
    sig = snap.get("signal")
    if not sig:
        m = re.search(r"candidate:\s*(strong_bullish|strong_bearish|bullish|bearish|neutral)", str(row.get("rationale") or ""))
        sig = m.group(1) if m else None
    if not sig:
        sc = snap.get("score", snap.get("avg_score"))
        if sc is not None:
            sig = signal_of(float(sc))
    if not sig:
        a = str(row.get("action") or "").lower()
        sig = "bullish" if a in ("buy", "review_buy", "accumulate") else "bearish" if a in ("sell", "review_reduce", "reduce") else "neutral"
    row["signal"] = sig
    row["sentiment"] = base_label(sig)
    row["sentiment_label"] = row["sentiment"]
    row["sentiment_th"] = SENT_TH.get(sig, "เป็นกลาง")
    return row


# ------------------------------------------------------------------ helpers
def _norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9ก-๙ ]+", "", str(t or "").lower()).strip()[:80]


def _topics(title: str, content: str) -> list[tuple[str, list[str], str]]:
    """A topic counts only if it is in the HEADLINE or mentioned >= 4 times in the body (a passing mention
    of 'oil' or 'dollar' in a tech/crypto story must not mark it as portfolio news)."""
    out = []
    for key, pats, holds, why in TOPICS:
        in_title = any(re.search(p, title, re.I) for p in pats)
        body_hits = sum(len(re.findall(p, content, re.I)) for p in pats)
        if in_title or body_hits >= 4:
            out.append((key, holds, why))
    return out


def _template_th(story: dict[str, Any]) -> str:
    sig = story["signal"]
    chips = ", ".join(story["tickers"][:5]) or "ตลาดโดยรวม"
    lead = {"bullish": "ข่าวเชิงบวก", "bearish": "ข่าวเชิงลบ", "neutral": "ข่าวทั่วไป"}[base_label(sig)]
    return f"{lead} ({IMPACT_TH.get(story['impact_level'] or 'low', 'ผลกระทบต่ำ')}) เกี่ยวกับ {chips} — (สรุปภาษาไทยกำลังจัดทำ อ่านหัวข้อข่าวด้านล่าง)"


def _why_th(story: dict[str, Any]) -> str:
    parts = []
    if story["holdings_direct"]:
        parts.append("กระทบหุ้น/กองทุนที่คุณถือโดยตรง: " + ", ".join(NAME_TH.get(t, t) for t in story["holdings_direct"]))
    if story["holdings_via_topic"]:
        parts.append("เกี่ยวข้องกับพอร์ตทางอ้อม: " + "; ".join(story["holdings_via_topic"]))
    if story["watchlist"]:
        parts.append("อยู่ในรายการเฝ้าดู: " + ", ".join(t.replace(".BK", "") for t in story["watchlist"]))
    if not parts:
        parts.append("ไม่เกี่ยวกับพอร์ตหรือรายการเฝ้าดูโดยตรง — ใช้ดูภาพรวมตลาด")
    return " · ".join(parts)


async def _context(pool: Any) -> tuple[set[str], set[str]]:
    async with pool.acquire() as conn:
        holds = {r["ticker"] for r in await conn.fetch(
            "SELECT h.ticker FROM holdings h LEFT JOIN holding_attributes a USING (ticker) "
            "WHERE h.quantity > 0 OR a.units_status = 'pending'")}
        watch = {r["ticker"] for r in await conn.fetch("SELECT ticker FROM investment_watchlist WHERE status <> 'dropped'")}
    return holds, watch


# ------------------------------------------------------------------ feed
async def build_feed(pool: Any, hours: int = 72, limit: int = 60, include_crypto: bool = False) -> dict[str, Any]:
    async with pool.acquire() as conn:
        await conn.execute(DDL)
        rows = await conn.fetch(
            """SELECT a.id, a.title, a.content, a.url, a.source, a.published_at, s.ticker, s.sentiment, s.score,
                      s.confidence, s.impact_level, s.llm_model, s.analyzed_at
               FROM sentiment_scores s JOIN news_articles a ON a.id = s.article_id
               WHERE s.analyzed_at >= now() - ($1::text || ' hours')::interval
               ORDER BY s.analyzed_at DESC""", str(int(hours)))
        sums = {r["article_id"]: dict(r) for r in await conn.fetch(
            "SELECT article_id, summary_th, why_th, model, created_at FROM news_summaries WHERE created_at >= now() - interval '10 days'")
            if not _bad_text((r["summary_th"] or "") + (r["why_th"] or ""))}  # garbled LLM output -> template + re-summarise
    holds, watch = await _context(pool)
    by_art: dict[Any, dict[str, Any]] = {}
    for r in rows:
        a = by_art.setdefault(r["id"], {"article_ids": [r["id"]], "title": r["title"], "content": r["content"] or "", "url": r["url"],
                                        "sources": [r["source"]], "published_at": r["published_at"], "analyzed_at": r["analyzed_at"],
                                        "raw_tickers": [], "scores": [], "labels": [], "impacts": [], "confs": [], "model": r["llm_model"]})
        if r["ticker"]:
            a["raw_tickers"].append(r["ticker"])
        if r["score"] is not None:
            a["scores"].append(float(r["score"]))
        a["labels"].append(r["sentiment"])
        a["impacts"].append(r["impact_level"])
        if r["confidence"] is not None:
            a["confs"].append(float(r["confidence"]))
    # merge the same story from several feeds (same normalised headline)
    stories: dict[str, dict[str, Any]] = {}
    for a in by_art.values():
        k = _norm_title(a["title"])
        if k in stories:
            s = stories[k]
            s["article_ids"] += a["article_ids"]
            s["sources"] = list(dict.fromkeys(s["sources"] + a["sources"]))
            for f in ("raw_tickers", "scores", "labels", "impacts", "confs"):
                s[f] += a[f]
            if len(a["content"]) > len(s["content"]):
                s["content"] = a["content"]
        else:
            stories[k] = a
    out = []
    for s in stories.values():
        text = f"{s['title']}\n{s['content']}"
        tickers = filter_tickers(s["raw_tickers"], text)
        dropped = sorted(set(t for t in s["raw_tickers"] if t) - set(tickers))
        score = sum(s["scores"]) / len(s["scores"]) if s["scores"] else None
        sig = signal_of(score, max(set(s["labels"]), key=s["labels"].count) if s["labels"] else None)
        impact = "high" if "high" in s["impacts"] else "medium" if "medium" in s["impacts"] else "low"
        topics = _topics(s["title"], s["content"])
        crypto_only = bool(re.search(r"bitcoin|crypto|binance|ethereum|stablecoin|tether|\bBTC\b|\bETH\b|solana|\bXRP\b", s["title"], re.I)) \
            or (bool(tickers) and all(t in CRYPTO or t.endswith("-USD") or t == "USDT" for t in tickers))
        if crypto_only:  # crypto stories are not portfolio news (crypto is excluded from Tho's advisor)
            topics = []
        direct = [t for t in tickers if t in holds]
        via = list(dict.fromkeys(why for _, hs, why in topics if any(h in holds for h in hs)))
        wl = [t for t in tickers if t in watch and t not in holds]
        tier = 0 if direct else 1 if via else 2 if wl else 3
        if crypto_only and tier >= 2 and not wl and not include_crypto:
            continue
        aid = s["article_ids"][0]
        summ = next((sums[i] for i in s["article_ids"] if i in sums), None)
        st = {"id": str(aid), "title": s["title"], "url": s["url"], "sources": s["sources"],
              "published_at": (s["published_at"] or s["analyzed_at"]).isoformat() if (s["published_at"] or s["analyzed_at"]) else None,
              "analyzed_at": s["analyzed_at"].isoformat() if s["analyzed_at"] else None,
              "signal": sig, "sentiment": base_label(sig), "sentiment_th": SENT_TH[sig], "score": round(score, 3) if score is not None else None,
              "impact_level": impact, "impact_th": IMPACT_TH[impact], "confidence": round(sum(s["confs"]) / len(s["confs"]), 2) if s["confs"] else None,
              "tickers": tickers, "holdings_direct": direct, "holdings_via_topic": via, "watchlist": wl, "topics": [k for k, _, _ in topics],
              "tier": tier, "relevance": ["พอร์ตของคุณ", "พอร์ตของคุณ (ทางอ้อม)", "รายการเฝ้าดู", "ภาพรวมตลาด"][tier],
              "crypto_only": crypto_only,
              "details": {"model": s["model"], "summary_model": summ["model"] if summ else None, "raw_labels": sorted(set(s["labels"])),
                          "raw_tickers_from_pipeline": sorted(set(t for t in s["raw_tickers"] if t)), "tickers_hidden_not_mentioned": dropped,
                          "article_ids": [str(i) for i in s["article_ids"]]}}
        st["summary_th"] = summ["summary_th"] if summ else _template_th(st)
        st["summary_status"] = "llm" if summ else "template"
        st["why_th"] = _why_th(st) + ((" · " + summ["why_th"]) if summ and summ.get("why_th") else "")
        out.append(st)
    out.sort(key=lambda x: (x["tier"], {"high": 0, "medium": 1, "low": 2}[x["impact_level"]], -(datetime.fromisoformat(x["published_at"]).timestamp() if x["published_at"] else 0)))
    dg = digest(out)  # digest over ALL stories in the window, before the display limit
    counts_all = {"bullish": sum(1 for i in out if i["sentiment"] == "bullish"), "bearish": sum(1 for i in out if i["sentiment"] == "bearish"),
                  "neutral": sum(1 for i in out if i["sentiment"] == "neutral"), "total": len(out)}
    return {"generated_at": datetime.now(timezone.utc).isoformat(), "hours": hours, "items": out[:limit], "counts_window": counts_all,
            "digest": dg, "holdings": sorted(holds), "note": "advisory only; sentiment from local LLM on news text; crypto-only stories hidden unless include_crypto=true"}


def digest(items: list[dict[str, Any]], hours: int = 24) -> dict[str, Any]:
    cut = datetime.now(timezone.utc) - timedelta(hours=hours)
    recent = [i for i in items if i.get("published_at") and datetime.fromisoformat(i["published_at"]) >= cut] or items[:20]
    cnt = {"bullish": 0, "bearish": 0, "neutral": 0}
    for i in recent:
        cnt[i["sentiment"]] += 1
    top = sorted(recent, key=lambda x: (x["tier"], {"high": 0, "medium": 1, "low": 2}[x["impact_level"]]))[:5]
    emo = {"bullish": "🟢", "bearish": "🔴", "neutral": "⚪"}
    bullets = []
    for i in top:
        first = re.split(r"(?<=[.!?。])\s+|\n", i["summary_th"])[0] if i["summary_status"] == "llm" else i["title"]
        rel = ("พอร์ต: " + ", ".join(NAME_TH.get(t, t) for t in i["holdings_direct"])) if i["holdings_direct"] else \
              (i["holdings_via_topic"][0] if i["holdings_via_topic"] else ("เฝ้าดู: " + ", ".join(i["watchlist"][:3]) if i["watchlist"] else "ภาพรวมตลาด"))
        bullets.append(f"{emo[i['sentiment']]} {i['sentiment_th']}: {first} — {rel}")
    port = [i for i in recent if i["tier"] <= 1]
    pb = sum(1 for i in port if i["sentiment"] == "bullish")
    pr = sum(1 for i in port if i["sentiment"] == "bearish")
    mood = "เชิงบวก" if cnt["bullish"] > cnt["bearish"] * 1.3 else "เชิงลบ" if cnt["bearish"] > cnt["bullish"] * 1.3 else "ผสม"
    return {"window_hours": hours, "stories": len(recent), "counts": cnt, "mood_th": mood,
            "portfolio_related": {"stories": len(port), "bullish": pb, "bearish": pr},
            "headline_th": f"{len(recent)} ข่าวใน {hours} ชม.: บวก {cnt['bullish']} · ลบ {cnt['bearish']} · กลาง {cnt['neutral']} — โทนตลาด{mood}; "
                           f"เกี่ยวกับพอร์ตคุณ {len(port)} ข่าว (บวก {pb} / ลบ {pr})",
            "takeaways_th": bullets}


# ------------------------------------------------------------------ Thai summaries (local LLM, free)
_FOREIGN_SCRIPT = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af\u0400-\u04ff]")  # CJK / kana / hangul / cyrillic leakage


def _bad_text(text: str) -> bool:
    return bool(_FOREIGN_SCRIPT.search(text or ""))


async def summarize_pending(pool: Any, max_items: int = 12, timeout: float = 90) -> dict[str, Any]:
    from utils.common import ollama_chat
    feed = await build_feed(pool, hours=72, limit=200)
    todo = [i for i in feed["items"] if i["summary_status"] == "template"][:max_items]
    made, failed = 0, 0
    for i in todo:
        async with pool.acquire() as conn:
            content = await conn.fetchval("SELECT content FROM news_articles WHERE id = $1::uuid", i["id"]) or ""
        prompt = f"""You summarise financial news for a Thai retail investor. Write in THAI only.
Use ONLY facts in the article; do not invent numbers, dates or companies. Keep company/ticker names in English.
Return JSON: {{"summary_th": "1-2 short Thai sentences: what happened", "why_th": "1 short Thai sentence: why it matters for investors"}}

Headline: {i['title']}
Article: {content[:1800]}"""
        try:
            summ = why = ""
            for _attempt in range(2):  # hermes occasionally leaks Chinese characters; retry once, else keep template
                raw = await ollama_chat(SUMMARY_MODEL, prompt, timeout, json_mode=True)
                d = json.loads(raw)
                summ = str(d.get("summary_th") or "").strip()[:600]
                why = str(d.get("why_th") or "").strip()[:300]
                if not _bad_text(summ + why):
                    break
            if _bad_text(summ + why):
                raise ValueError("summary contains non-Thai script")
            if len(summ) < 10 or not re.search(r"[\u0E00-\u0E7F]", summ):
                raise ValueError("no Thai summary returned")
            async with pool.acquire() as conn:
                await conn.execute("""INSERT INTO news_summaries (article_id, summary_th, why_th, model) VALUES ($1::uuid,$2,$3,$4)
                                      ON CONFLICT (article_id) DO UPDATE SET summary_th=EXCLUDED.summary_th, why_th=EXCLUDED.why_th,
                                      model=EXCLUDED.model, created_at=now()""", i["id"], summ, why or None, SUMMARY_MODEL)
            made += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            LOGGER.warning("news summary failed for %s: %s", i["id"], exc)
    return {"candidates": len(todo), "summarised": made, "failed": failed, "model": SUMMARY_MODEL}
