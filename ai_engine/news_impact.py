"""Two-sided news-impact model (SHADOW ONLY) - added 2026-11-07.

What it does
- Classifies each headline as UP (+1), DOWN (-1) or neutral (0) per sector, using the
  regex rules in config/news_impact_rules.json. A headline that matches both UP and DOWN
  for one sector is neutral and is not counted.
- Finds the reaction day (first trading day on/after the headline date) and reads the
  sector proxy's close-to-close moves on days 0, +1, +2 (a 3-trading-day fading window).
- Logs each signal with its price check to data/shadow/news_impact_shadow.jsonl.

What it does NOT do
- No database writes, no advice, no signals, no weights, no orders.
- A signal affects scoring only after ops/news_impact_backtest.py passes ops/backtest_gate.py
  and the owner approves that change.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

ROOT = Path(__file__).resolve().parents[1]
RULES_PATH = ROOT / "config" / "news_impact_rules.json"
PRICES_CSV = ROOT / "data" / "news_impact" / "prices_daily.csv"
SHADOW_LOG = ROOT / "data" / "shadow" / "news_impact_shadow.jsonl"


def load_rules(path: Path = RULES_PATH) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        rules = json.load(fh)
    compiled = {}
    for name, spec in rules["sectors"].items():
        compiled[name] = {
            "proxy": spec["proxy"],
            "up": re.compile(spec["up"], re.IGNORECASE),
            "down": re.compile(spec["down"], re.IGNORECASE),
        }
    rules["_compiled"] = compiled
    rules["decay_weights"] = [float(w) for w in rules["decay_weights"]]
    return rules


def classify_headline(title: str, rules: dict[str, Any]) -> list[dict[str, Any]]:
    """Return one entry per sector that matched exactly one direction."""
    out = []
    for sector, spec in rules["_compiled"].items():
        up = bool(spec["up"].search(title or ""))
        down = bool(spec["down"].search(title or ""))
        if up == down:  # neither, or both -> neutral, not counted
            continue
        out.append({
            "sector": sector,
            "proxy": spec["proxy"],
            "direction": 1 if up else -1,
        })
    return out


def reaction_index(trading_dates: list[date], headline_date: date) -> Optional[int]:
    """Index of the first trading day on or after the headline date."""
    for i, d in enumerate(trading_dates):
        if d >= headline_date:
            return i
    return None


def proxy_returns(closes: list[float], start: int, weights_len: int) -> list[Optional[float]]:
    """Close-to-close returns for days start, start+1, ... (uses the prior close)."""
    out: list[Optional[float]] = []
    for k in range(weights_len):
        i = start + k
        if i - 1 < 0 or i >= len(closes) or not closes[i - 1]:
            out.append(None)
        else:
            out.append(closes[i] / closes[i - 1] - 1.0)
    return out


def score_event(
    direction: int,
    closes: list[float],
    dates: list[date],
    headline_date: date,
    weights: list[float],
) -> Optional[dict[str, Any]]:
    """Price check for one signal. Returns None if the price window is not complete."""
    idx = reaction_index(dates, headline_date)
    if idx is None:
        return None
    rets = proxy_returns(closes, idx, len(weights))
    if any(r is None for r in rets):
        return None
    signed = [direction * r for r in rets]
    decayed = sum(w * s for w, s in zip(weights, signed))
    return {
        "reaction_day": dates[idx].isoformat(),
        "returns": [round(r, 6) for r in rets],
        "signed_returns": [round(s, 6) for s in signed],
        "decayed_score": round(decayed, 6),
        "hit_day0": signed[0] > 0,
        "hit_3d": (sum(signed) > 0),
    }


def load_price_table(path: Path = PRICES_CSV) -> tuple[list[date], dict[str, list[float]]]:
    """Read the daily close table into {ticker: [closes]} aligned to one date list."""
    import csv

    with open(path, encoding="utf-8") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        # Two header rows in yfinance output are not used here: the file is written
        # with a single header row (price_date, TICKER, ...).
        tickers = header[1:]
        dates: list[date] = []
        cols: dict[str, list[float]] = {t: [] for t in tickers}
        for row in reader:
            if not row or not row[0]:
                continue
            values = []
            ok = True
            for v in row[1:]:
                if v in ("", "nan", "NaN"):
                    ok = False
                    values.append(float("nan"))
                else:
                    values.append(float(v))
            if not ok:
                continue  # skip dates where any ticker is missing
            dates.append(datetime.strptime(row[0], "%Y-%m-%d").date())
            for t, v in zip(tickers, values):
                cols[t].append(v)
    return dates, cols


def append_shadow_records(records: Iterable[dict[str, Any]], path: Path = SHADOW_LOG) -> int:
    """Append-only JSONL log. Never rewrites or deletes existing lines."""
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with open(path, "a", encoding="utf-8") as fh:
        for rec in records:
            rec = dict(rec)
            rec["logged_at"] = datetime.now(timezone.utc).isoformat()
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
    return n
