"""Shadow run for the two-sided news-impact model. Added 2026-11-07.

Reads recent headlines (SELECT only), classifies UP / DOWN per sector, and appends one
record per signal to data/shadow/news_impact_shadow.jsonl. Signals whose 3-day price window
is not complete yet are logged as 'pending' and scored on a later run.
Append-only and de-duplicated by key. Changes no advice, signals, weights or database rows.
Price data: data/news_impact/prices_daily.csv (refresh it before a run when needed).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "ai_engine"), str(ROOT / "ops")]

import news_impact as NI  # noqa: E402
from news_impact_backtest import fetch_headlines, headline_trading_date  # noqa: E402

LOOKBACK_DAYS = 14


def existing_keys(path: Path) -> set[str]:
    if not path.exists():
        return set()
    keys = set()
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                keys.add(json.loads(line)["key"])
    return keys


def main() -> None:
    rules = NI.load_rules()
    dates, cols = NI.load_price_table()
    weights = rules["decay_weights"]
    cutoff = datetime.now().astimezone() - timedelta(days=LOOKBACK_DAYS)

    seen = existing_keys(NI.SHADOW_LOG)
    records = []
    counts = {"scored": 0, "pending": 0, "duplicate": 0}
    for title, published_at in asyncio.run(fetch_headlines()):
        if published_at < cutoff:
            continue
        hdate = headline_trading_date(published_at)
        for hit in NI.classify_headline(title, rules):
            raw = f"{title}|{published_at.isoformat()}|{hit['sector']}|{hit['direction']}"
            key = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
            if key in seen:
                counts["duplicate"] += 1
                continue
            seen.add(key)
            rec = {
                "key": key,
                "title": title,
                "published_at": published_at.isoformat(),
                "headline_date": hdate.isoformat(),
                "sector": hit["sector"],
                "proxy": hit["proxy"],
                "direction": hit["direction"],
                "rules_version": "v1_2026-11-07",
            }
            closes = cols.get(hit["proxy"])
            res = NI.score_event(hit["direction"], closes, dates, hdate, weights) if closes else None
            if res is None:
                rec["status"] = "pending"
                counts["pending"] += 1
            else:
                rec.update({"status": "scored", **res})
                counts["scored"] += 1
            records.append(rec)

    n = NI.append_shadow_records(records)
    print(json.dumps({"appended": n, **counts, "log": str(NI.SHADOW_LOG)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
