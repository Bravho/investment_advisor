"""Two-sided news-impact backtest (read-only). Added 2026-11-07.

- Reads headlines from news_articles (SELECT only).
- Classifies UP / DOWN per sector with config/news_impact_rules.json.
- Price check on the sector proxy from data/news_impact/prices_daily.csv.
- Groups signals by (sector, direction, reaction day) so one event that many outlets
  repeat counts once.
- Gates UP and DOWN separately with ops/backtest_gate.py.
  Baseline = no signal (skill 0, hit 0.5). Candidate = signed proxy return and hit rate.
- Writes data/news_impact/backtest_2026-11-07.json. No database writes.
"""
from __future__ import annotations

import asyncio
import json
import sys
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "ai_engine"), str(ROOT / "ops")]

from backtest_gate import gate  # noqa: E402
import news_impact as NI  # noqa: E402

NY = ZoneInfo("America/New_York")
OUT = ROOT / "data" / "news_impact" / "backtest_2026-11-07.json"
START = date(2024, 6, 3)  # first date in the price table


def headline_trading_date(published_at: datetime) -> date:
    """US trading date a headline can first affect. After 16:00 ET -> next calendar day."""
    et = published_at.astimezone(NY)
    if et.time() >= time(16, 0):
        return et.date() + timedelta(days=1)
    return et.date()


async def fetch_headlines() -> list[tuple[str, datetime]]:
    from utils.db_pool import db_pool

    pool = await db_pool.get_pool()
    rows = await pool.fetch(
        "SELECT title, published_at FROM news_articles "
        "WHERE published_at IS NOT NULL AND published_at >= $1 ORDER BY published_at",
        datetime.combine(START, time(0, 0), tzinfo=NY),
    )
    await db_pool.close()
    return [(r["title"], r["published_at"]) for r in rows]


def summarize(events: list[dict]) -> dict:
    if not events:
        return {"n_events": 0}
    n = len(events)
    d0 = [e["signed_day0"] for e in events]
    d3 = [e["signed_3d"] for e in events]
    return {
        "n_events": n,
        "mean_signed_day0": round(sum(d0) / n, 6),
        "hit_day0": round(sum(1 for x in d0 if x > 0) / n, 4),
        "mean_signed_3d": round(sum(d3) / n, 6),
        "hit_3d": round(sum(1 for x in d3 if x > 0) / n, 4),
    }


def gate_for(events: list[dict]) -> dict:
    if not events:
        return {"pass": False, "reason": "no events"}
    n = len(events)
    cand = {
        "day0": {
            "skill": sum(e["signed_day0"] for e in events) / n,
            "hit": sum(1 for e in events if e["signed_day0"] > 0) / n,
        },
        "3d": {
            "skill": sum(e["signed_3d"] for e in events) / n,
            "hit": sum(1 for e in events if e["signed_3d"] > 0) / n,
        },
    }
    base = {"day0": {"skill": 0.0, "hit": 0.5}, "3d": {"skill": 0.0, "hit": 0.5}}
    return gate(base, cand)


def main() -> None:
    rules = NI.load_rules()
    dates, cols = NI.load_price_table()
    weights = rules["decay_weights"]
    titles = asyncio.run(fetch_headlines())

    # Collect signals, then de-duplicate by (sector, direction, reaction day).
    grouped: dict[tuple, list[float]] = defaultdict(list)
    grouped_3d: dict[tuple, list[float]] = defaultdict(list)
    skipped_incomplete = 0
    n_headlines = len(titles)
    n_matched = 0
    for title, published_at in titles:
        hits = NI.classify_headline(title, rules)
        if not hits:
            continue
        n_matched += 1
        hdate = headline_trading_date(published_at)
        for h in hits:
            closes = cols.get(h["proxy"])
            if closes is None:
                continue
            res = NI.score_event(h["direction"], closes, dates, hdate, weights)
            if res is None:
                skipped_incomplete += 1
                continue
            key = (h["sector"], h["direction"], res["reaction_day"])
            grouped[key].append(res["signed_returns"][0])
            grouped_3d[key].append(sum(res["signed_returns"]))

    events = []
    for key in grouped:
        sector, direction, rday = key
        events.append({
            "sector": sector,
            "direction": direction,
            "reaction_day": rday,
            "n_headlines": len(grouped[key]),
            "signed_day0": sum(grouped[key]) / len(grouped[key]),
            "signed_3d": sum(grouped_3d[key]) / len(grouped_3d[key]),
        })

    results: dict = {
        "generated_for": "2026-11-07",
        "headlines_read": n_headlines,
        "headlines_matched": n_matched,
        "signals_skipped_incomplete_window": skipped_incomplete,
        "events_deduplicated": len(events),
        "by_direction": {},
        "by_sector_direction": {},
        "gate": {},
    }
    for label, d in (("UP", 1), ("DOWN", -1)):
        sub = [e for e in events if e["direction"] == d]
        results["by_direction"][label] = summarize(sub)
        results["gate"][label] = gate_for(sub)
        for sector in sorted({e["sector"] for e in sub}):
            results["by_sector_direction"][f"{sector}:{label}"] = summarize(
                [e for e in sub if e["sector"] == sector]
            )

    # Case check: the Nov 5, 2026 selloff. Day-0 only, because the 3-day window is incomplete.
    case = []
    for h_sector, spec in rules["_compiled"].items():
        proxy = spec["proxy"]
        closes = cols.get(proxy)
        if not closes or dates[-1] != date(2026, 11, 6):
            continue
        i = dates.index(date(2026, 11, 5))
        case.append({"sector": h_sector, "proxy": proxy,
                     "day0_pct_2026_11_05": round((closes[i] / closes[i - 1] - 1) * 100, 2)})
    results["case_2026_11_05"] = case

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2, ensure_ascii=False)
    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
