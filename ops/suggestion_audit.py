"""Read-only audit of past recommendations vs a SET benchmark (TDEX.BK).

Usage (from project root):
    ./venv/bin/python ops/suggestion_audit.py [--horizon 7] [--split 2026-09-15]

Reads `recommendations` and `market_prices` from investor_db (SELECT only),
downloads TDEX.BK closes from yfinance (free, read-only GET), and prints:
  - raw hit rate (stock return > 0) by action, the way the live evaluator scores it
  - excess hit rate (stock return > benchmark return) by action
  - average return and average excess return by action
  - the same numbers for a time split (before / after --split) to check stability
Duplicate rows (same ticker, action, created day) are collapsed to one row.
Nothing is written to the database.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import asyncpg  # noqa: E402
import pandas as pd  # noqa: E402
import yfinance as yf  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

BENCH = "TDEX.BK"
BULLISH = {"buy", "accumulate", "review_buy"}
BEARISH = {"sell", "reduce", "review_reduce", "stop_loss"}


async def load_recs() -> list[dict]:
    load_dotenv(ROOT / ".env")
    conn = await asyncpg.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        database=os.getenv("DB_NAME", "investor_db"),
        user=os.getenv("DB_USER", "investor_app"),
        password=os.getenv("DB_PASSWORD", ""),
    )
    try:
        rows = await conn.fetch(
            """
            SELECT id, ticker, action, confidence, llm_model, price_at_recommendation,
                   created_at, (actual_outcome->>'actual_return_pct')::float AS ret_pct,
                   actual_outcome->>'evaluation_status' AS eval_status,
                   (actual_outcome->>'was_correct')::boolean AS was_correct,
                   (actual_outcome->>'price_at_review')::float AS price_at_review,
                   (actual_outcome->>'days_held')::int AS days_held
            FROM recommendations
            WHERE actual_outcome IS NOT NULL
            ORDER BY created_at
            """
        )
        return [dict(r) for r in rows]
    finally:
        await conn.close()


def bench_returns(start: date, end: date) -> pd.Series:
    """Return series of TDEX.BK close over [start, end] (ratio-1)."""
    df = yf.download([BENCH], start=str(start - timedelta(days=10)), end=str(end + timedelta(days=10)),
                     interval="1d", auto_adjust=True, progress=False, threads=False)
    close = df["Close"][BENCH].dropna()
    close.index = pd.to_datetime(close.index).tz_localize(None)
    return close


def bench_move(close: pd.Series, d0: date, days: int) -> float | None:
    s = close[close.index >= pd.Timestamp(d0)]
    if s.empty:
        return None
    p0 = float(s.iloc[0])
    t = pd.Timestamp(d0 + timedelta(days=days))
    s1 = close[close.index >= t]
    if s1.empty:
        return None
    return (float(s1.iloc[0]) / p0 - 1) * 100


def dedupe(recs: list[dict]) -> list[dict]:
    seen: set = set()
    out = []
    for r in recs:
        key = (r["ticker"], r["action"], r["created_at"].date())
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def summarize(rows: list[dict], label: str) -> None:
    print(f"\n== {label}  (n={len(rows)})")
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        groups[r["action"]].append(r)
    print(f"{'action':<16}{'n':>5}{'raw_hit%':>10}{'exc_hit%':>10}{'avg_ret%':>10}{'avg_exc%':>10}")
    for action in sorted(groups, key=lambda a: -len(groups[a])):
        g = [r for r in groups[action] if r["ret_pct"] is not None and r["bench_pct"] is not None]
        if not g:
            continue
        n = len(g)
        # Direction-aware: bullish wins when up, bearish wins when down; others use raw sign.
        def win(r: dict, use_excess: bool) -> bool:
            x = r["exc_pct"] if use_excess else r["ret_pct"]
            if r["action"] in BEARISH:
                return x < 0
            return x > 0
        raw = sum(win(r, False) for r in g) / n * 100
        exc = sum(win(r, True) for r in g) / n * 100
        avg_ret = sum(r["ret_pct"] for r in g) / n
        avg_exc = sum(r["exc_pct"] for r in g) / n
        print(f"{action:<16}{n:>5}{raw:>10.1f}{exc:>10.1f}{avg_ret:>10.2f}{avg_exc:>10.2f}")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--horizon", type=int, default=7)
    ap.add_argument("--split", default="2026-09-15")
    args = ap.parse_args()

    recs = dedupe(await load_recs())
    if not recs:
        print("no reviewed recommendations")
        return
    start = min(r["created_at"].date() for r in recs)
    end = max(r["created_at"].date() for r in recs) + timedelta(days=args.horizon + 5)
    close = bench_returns(start, end)

    usable = []
    for r in recs:
        d0 = r["created_at"].date()
        b = bench_move(close, d0, args.horizon)
        # Exclude rows whose stock price was missing (evaluator stored 0.0) and rows priced
        # more than 3 days after the intended window (stale price from a data gap).
        if b is None or r["ret_pct"] is None or not r["price_at_review"] or r["price_at_review"] <= 0:
            continue
        if (r["days_held"] or 0) > args.horizon + 3:
            continue
        r["bench_pct"] = b
        r["exc_pct"] = r["ret_pct"] - b
        usable.append(r)

    print(f"Deduped reviewed recs: {len(recs)}  usable (valid price, on-window, benchmark ok): {len(usable)}")
    print(f"Date range: {start} .. {max(r['created_at'].date() for r in recs)}  horizon: {args.horizon}d")
    print(f"Benchmark {BENCH} avg move over same windows: "
          f"{sum(r['bench_pct'] for r in usable) / len(usable):.2f}%")

    summarize(usable, "ALL")
    split = date.fromisoformat(args.split)
    summarize([r for r in usable if r["created_at"].date() < split], f"BEFORE {split}")
    summarize([r for r in usable if r["created_at"].date() >= split], f"ON/AFTER {split}")

    legacy = [r for r in usable if r["eval_status"] is None and r["action"] == "watch"]
    print(f"\nLegacy 'watch' rows scored under the old rule (evaluation_status null): {len(legacy)}")


if __name__ == "__main__":
    asyncio.run(main())
