"""Market context for the daily brief and the nightly research (2026-11-01, P2.2).

One deterministic markdown block built from the same data the ข่าวและอารมณ์ตลาด page shows:
  * market mood = PRICE regime (signals.compute_regime) + 24h news tone (crypto excluded) as a secondary line
  * macro trends board (value, 1d / 1m change, as-of; values older than 7 days are marked STALE)
  * policy rates (Fed / BoT / ...)
  * sector moves for Tho's holdings (1-month change of the real proxy)
  * news digest (counts + top takeaways)
  * high-impact crypto events (display-only, never part of the verdict)
Context only: nothing here feeds signals, forecasts or construction weights.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any, Optional

STALE_DAYS = 7


def _age_days(as_of: Any) -> Optional[int]:
    try:
        d = as_of if isinstance(as_of, date) else datetime.fromisoformat(str(as_of)[:10]).date()
        return (date.today() - d).days
    except Exception:  # noqa: BLE001
        return None


def _num(v: Any, d: int = 2) -> str:
    try:
        return f"{float(v):,.{d}f}"
    except (TypeError, ValueError):
        return "unknown"


def _chg(v: Any, basis: str = "%") -> str:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "unknown"
    return f"{f:+.2f}{'%' if basis == '%' else ' ' + basis}"


async def mood(pool: Any) -> dict[str, Any]:
    reg = await pool.fetchrow("SELECT as_of, regime, score FROM market_regime ORDER BY as_of DESC LIMIT 1")
    # macro_sentiment.articles_analyzed added 2026-11-01 by the table owner (additive); readers do not run DDL
    news = await pool.fetchrow("SELECT snapshot_date, overall_score, market_mood, COALESCE(articles_analyzed, cardinality(source_article_ids)) AS articles_analyzed FROM macro_sentiment ORDER BY snapshot_date DESC LIMIT 1")
    news_count = int(news["articles_analyzed"] or 0) if news else 0
    return {"verdict": reg["regime"] if reg else "unknown", "score": float(reg["score"]) if reg else None,
            "as_of": str(reg["as_of"]) if reg else None,
            "news_tone": {"mood": "unknown" if news_count == 0 else news["market_mood"],
                          "score": float(news["overall_score"]) if news_count > 0 and news["overall_score"] is not None else None,
                          "articles_analyzed": news_count, "as_of": str(news["snapshot_date"])} if news else None}


async def gather(pool: Any) -> dict[str, Any]:
    """Direct module calls (used by the brief, inside the engine)."""
    import crypto_events as ce
    import macro_trends as macro_mod
    import news_feed as nf_mod
    import sector_moves as sm_mod
    out: dict[str, Any] = {"errors": {}}
    for key, coro in (("mood", mood(pool)), ("board", macro_mod.build_board(pool, max_age=1800)),
                      ("sectors", sm_mod.build(pool, max_age=1800)), ("feed", nf_mod.build_feed(pool, hours=24, limit=40)),
                      ("crypto", ce.current(pool))):
        try:
            out[key] = await coro
        except Exception as exc:  # noqa: BLE001
            out[key] = None
            out["errors"][key] = type(exc).__name__
    return out


def render(ctx: dict[str, Any], max_cards: int = 21) -> str:
    lines: list[str] = ["## Market context (same data as the ข่าวและอารมณ์ตลาด page; context only, not a signal)"]
    m = ctx.get("mood") or {}
    nt = m.get("news_tone") or {}
    lines.append(f"- Market mood (price regime): {m.get('verdict', 'unknown')} (score {_num(m.get('score'), 3)}, as of {m.get('as_of') or 'unknown'})"
                 f"; news tone 24h, crypto excluded: {nt.get('mood', 'unknown')} ({_num(nt.get('score'), 2)}, {nt.get('as_of') or 'unknown'})")
    board = ctx.get("board") or {}
    cards = [c for c in (board.get("cards") or [])  # crypto stays out of the market context (own card below)
             if not re.search(r"bitcoin|ethereum|crypto|btc|eth\b", f"{c.get('key')} {c.get('name_en')} {c.get('forecast_subject')}", re.I)]
    if cards:
        lines.append("\n### Macro trends board")
        for c in cards[:max_cards]:
            age = _age_days(c.get("as_of"))
            stale = " UNVERIFIED DATE" if age is None else " STALE" if age > STALE_DAYS else ""
            basis = c.get("change_basis") or "%"
            hold = f" -> {', '.join(c['holdings'])}" if c.get("holdings") else ""
            lines.append(f"- {c.get('name_en') or c.get('name_th')}: {_num(c.get('value'))} {c.get('unit') or ''} "
                         f"(1d {_chg(c.get('change_1d'), basis)}, 1m {_chg(c.get('change_1m'), basis)}; as of {c.get('as_of') or 'unknown'}{stale}){hold}")
    elif "board" in (ctx.get("errors") or {}):
        lines.append(f"- Macro board unavailable ({ctx['errors']['board']})")
    pol = board.get("policy") or []
    if pol:
        lines.append("\n### Policy rates")
        for p in pol:
            if p.get("status") != "ok":
                lines.append(f"- {p.get('name_en') or p.get('bank')}: unknown ({p.get('status')})")
                continue
            lines.append(f"- {p.get('name_en') or p.get('bank')}: {p.get('rate_text') or _num(p.get('rate'))}; last change {p.get('last_change_date') or 'unknown'}"
                         f" ({_num(p.get('last_change_bp'), 0)} bp); last meeting {p.get('last_meeting') or 'unknown'} {p.get('last_meeting_outcome') or ''}; next {p.get('next_meeting') or 'unknown'}")
    sec = (ctx.get("sectors") or {}).get("lines") or []
    if sec:
        lines.append("\n### Holding sectors (1-month move of the real proxy)")
        for s in sec:
            news = (s.get("news") or {}).get("title")
            lines.append(f"- {s.get('key')} ({s.get('holding') or '-'}; proxy {s.get('proxy')}): "
                         f"{_chg(s.get('change_1m_pct')) if s.get('change_1m_pct') is not None else 'unknown'} to {s.get('as_of') or 'unknown'}"
                         + (f"; related news: {news}" if news else ""))
    dg = (ctx.get("feed") or {}).get("digest") or {}
    if dg:
        c = dg.get("counts") or {}
        pr = dg.get("portfolio_related") or {}
        lines.append(f"\n### News digest (24h, crypto excluded)\n- {dg.get('stories', 0)} stories: bullish {c.get('bullish', 0)} / bearish {c.get('bearish', 0)} / neutral {c.get('neutral', 0)};"
                     f" portfolio-related {pr.get('stories', 0)} (bullish {pr.get('bullish', 0)} / bearish {pr.get('bearish', 0)})")
        for t in (dg.get("takeaways_th") or [])[:5]:
            lines.append(f"- {t}")
    cr = ctx.get("crypto") or {}
    if cr.get("cards"):
        lines.append("\n### High-impact crypto events (display-only; excluded from mood and signals)")
        for c in cr["cards"]:
            if c.get("type") == "news":
                lines.append(f"- {c.get('category')}: {c.get('headline')} ({c.get('n_sources')} publishers, {str(c.get('at'))[:10]})")
            else:
                lines.append(f"- BTC price: " + "; ".join(f"{t.get('trigger')} {_chg(t.get('value_pct'))}" for t in c.get("triggers") or [c]) + f" ({str(c.get('at'))[:10]})")
    return "\n".join(lines)


async def render_brief_section(pool: Any) -> str:
    return render(await gather(pool))


if __name__ == "__main__":  # dry run: venv/bin/python portfolio_engine/market_context.py
    import asyncio
    import sys
    sys.path.insert(0, ".")
    from utils.db_pool import db_pool

    async def _main() -> None:
        print(await render_brief_section(await db_pool.get_pool()))
    asyncio.run(_main())
