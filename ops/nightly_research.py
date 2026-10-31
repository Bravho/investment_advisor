"""Nightly research-only runner (2026-10-30). Free/local: news DB + engine endpoints + local Ollama.

Writes ONLY: data/market_intel/YYYY-MM-DD.md (append), data/watchlist.json (_meta + engine_snapshot),
DEVLOG.md (append). No code edits, no git, no LINE, no paid APIs.
Usage: venv/bin/python ops/nightly_research.py [--dry-run] [--no-llm]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "portfolio_engine"))
ICT = ZoneInfo("Asia/Bangkok")
ENGINE = "http://127.0.0.1:8996"
MODEL = os.getenv("NIGHTLY_OLLAMA_MODEL", "hermes3:8b")
BUCKETS = {
    "Thailand": r"\bthai|thailand|\bset\b|bangkok|baht|\bbot\b|pttep|\bscb\b|kbank|ptt\b",
    "US / Tech": r"\bfed\b|wall street|s&p|nasdaq|dow|nvidia|apple|microsoft|alphabet|google|amazon|meta\b|semiconductor|\bai\b|treasur",
    "China / HK": r"china|chinese|hong kong|hang seng|beijing|yuan",
    "Japan": r"japan|nikkei|\bboj\b|yen|tokyo",
    "India": r"india|nifty|sensex|rupee|\brbi\b",
    "Vietnam": r"vietnam|vn-index|hanoi",
    "Europe": r"europe|\becb\b|euro\b|dax|cac|germany|france|\buk\b|britain",
    "Global macro (gold, oil, FX, rates)": r"gold|oil|brent|opec|crude|inflation|dollar|rate cut|rate hike|yield",
}
EXCLUDE = re.compile(r"bitcoin|crypto|ethereum|btc|\beth\b", re.I)


def get(path: str):
    with urllib.request.urlopen(ENGINE + path, timeout=60) as r:
        return json.loads(r.read())


async def news(hours: int = 26) -> list[dict]:
    from utils.db_pool import db_pool
    await db_pool.connect()
    pool = await db_pool.get_pool()
    rows = await pool.fetch("""SELECT source, title, url, published_at FROM news_articles
                               WHERE fetched_at > now() - make_interval(hours => $1) ORDER BY published_at DESC NULLS LAST LIMIT 600""", hours)
    seen, out = set(), []
    for r in rows:
        t = (r["title"] or "").strip()
        if not t or EXCLUDE.search(t) or EXCLUDE.search(r["source"] or "") or t.lower() in seen:
            continue
        seen.add(t.lower())
        out.append(dict(r))
    return out


async def summarise(market: str, items: list[dict], use_llm: bool) -> list[str]:
    heads = items[:12]
    if not use_llm or not heads:
        return [f"{h['title']} ({h['source']})" for h in heads[:3]]
    from utils.common import ollama_chat
    lines = "\n".join(f"- {h['title']} [{h['source']}, {h['published_at']:%Y-%m-%d}]" for h in heads)
    prompt = (f"You are a careful markets analyst. From ONLY these headlines about {market}, write 2-3 short factual bullets "
              f"for a Thai medium-term investor (holds PTTEP, SCB, a gold fund). Do not invent numbers not in the headlines. "
              f"Return JSON {{\"bullets\": [..]}}.\n{lines}")
    try:
        from utils.common import parse_json_response
        txt = await ollama_chat(MODEL, prompt, timeout=150, json_mode=True)
        b = parse_json_response(txt).get("bullets") or []
        return [str(x).strip() for x in b][:3] or [heads[0]["title"]]
    except Exception as exc:  # local LLM unavailable -> headlines only
        return [f"{h['title']} ({h['source']})" for h in heads[:3]] + [f"(local LLM summary unavailable: {type(exc).__name__})"]


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-llm", action="store_true")
    a = ap.parse_args()
    cfg = json.loads((ROOT / "config" / "self_develop.json").read_text())
    if cfg.get("mode") != "research_only":
        print("self_develop.json mode is not research_only - research runner exits without writing")
        return 0
    now = datetime.now(ICT)
    day = now.strftime("%Y-%m-%d")
    arts = await news()
    by = {m: [x for x in arts if re.search(rx, x["title"], re.I)] for m, rx in BUCKETS.items()}
    sections = {m: await summarise(m, items, not a.no_llm) for m, items in by.items()}
    wl = get("/watchlist")
    fac = get("/factors")
    risk = get("/risk/report")
    sig = get("/signals")
    items = wl.get("items", [])
    movers = sorted([i for i in items if i.get("metrics", {}).get("change_1d_pct") is not None], key=lambda i: -abs(i["metrics"]["change_1d_pct"]))[:6]
    breached = [f for f in fac.get("factors", []) if f.get("breached")]
    hold = {p["ticker"]: p for p in risk.get("positions_input", [])}
    md = [f"\n# Market intel - {day} (research-only nightly run {now:%H:%M} ICT)\n",
          f"_Local runner: news DB ({len(arts)} headlines, last 26h, crypto excluded) + engine endpoints + {'headlines only' if a.no_llm else 'local Ollama ' + MODEL}. No paid APIs._\n"]
    for m, bl in sections.items():
        md.append(f"\n## {m}\n" + ("\n".join(f"- {b}" for b in bl) if bl else "- no headlines in the window"))
        src = by[m][:3]
        if src:
            md.append("  Sources: " + "; ".join(f"[{s['source']}]({s['url']})" for s in src if s.get("url")))
    md.append("\n## Holdings watch")
    for t, p in hold.items():
        md.append(f"- {t}: value {p.get('value_thb'):,.0f} THB, price as of {p.get('price_as_of')} ({p.get('price_source')})")
    md.append(f"- Risk: VaR95 {risk.get('summary', {}).get('hist_var95_thb')} THB; limit breaches: {', '.join(risk.get('summary', {}).get('limit_breaches') or []) or 'none'}")
    md.append("\n## Factor alerts")
    md += [f"- {f['name']}: {f.get('reading_text')} - {f.get('breach_reason')} ({f.get('source')})" for f in breached] or ["- none"]
    md.append("\n## Watch list movers (1d)")
    md += [f"- {i['ticker']} {i['metrics']['change_1d_pct']:+.1f}% last {i.get('last_price')} ({i.get('price_as_of', '')[:10]})" for i in movers] or ["- n/a"]
    md.append(f"\n## Regime\n- {sig.get('regime', {}).get('regime')} (score {sig.get('regime', {}).get('score')}, as of {sig.get('regime', {}).get('as_of')})")
    # 2026-11-01 (P2.2): same market context as the brief / ข่าวและอารมณ์ตลาด page (engine endpoints; context only)
    try:
        import market_context as mc
        ctx: dict = {"errors": {}}
        for key, path in (("mood", "/market/mood"), ("board", "/macro/trends"), ("sectors", "/sectors/moves"),
                          ("feed", "/news/feed?hours=24&limit=40"), ("crypto", "/crypto/events")):
            try:
                ctx[key] = get(path)
            except Exception as exc:  # noqa: BLE001
                ctx[key] = None
                ctx["errors"][key] = type(exc).__name__
        md.append("\n" + mc.render(ctx).replace("## Market context", "## Market context", 1))
    except Exception as exc:  # noqa: BLE001
        md.append(f"\n## Market context\n- unavailable ({type(exc).__name__})")
    try:  # 2026-11-01: geopolitical/war-risk layer (context only)
        md.append("\n## Geopolitical / war risk\n" + get("/geo/advisor-context").get("context", "unknown"))
    except Exception as exc:  # noqa: BLE001
        md.append(f"\n## Geopolitical / war risk\n- unavailable ({type(exc).__name__})")
    text = "\n".join(md) + "\n"
    snap = {"as_of": now.isoformat(timespec="minutes"), "source": "engine GET /watchlist",
            "items": [{k: i.get(k) for k in ("ticker", "last_price", "price_as_of", "status", "score", "price_stale")} for i in items]}
    dev = (f"\n## Nightly Run - {day} {now:%H:%M} ICT (research-only)\n- Mode: research_only (config/self_develop.json); no code edited.\n"
           f"- Wrote data/market_intel/{day}.md ({len(arts)} headlines) and data/watchlist.json engine_snapshot ({len(items)} items).\n"
           f"- Factor alerts: {', '.join(f['key'] for f in breached) or 'none'}; regime {sig.get('regime', {}).get('regime')}.\n")
    if a.dry_run:
        print(text[:4000]); print(dev); print("watchlist snapshot items:", len(snap["items"]))
        return 0
    intel = ROOT / "data" / "market_intel" / f"{day}.md"
    intel.parent.mkdir(parents=True, exist_ok=True)
    with intel.open("a") as fh:
        fh.write(text)
    wpath = ROOT / "data" / "watchlist.json"
    w = json.loads(wpath.read_text())
    w.setdefault("_meta", {})["last_updated"] = now.isoformat(timespec="minutes")
    w["_meta"]["updated_by"] = "nightly-research (local, research-only)"
    w["engine_snapshot"] = snap
    tmp = wpath.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(w, indent=2, ensure_ascii=False))
    tmp.replace(wpath)
    with (ROOT / "DEVLOG.md").open("a") as fh:
        fh.write(dev)
    print(f"ok: {intel.name}, watchlist {len(items)}, headlines {len(arts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
