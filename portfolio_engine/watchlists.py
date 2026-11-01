"""Investment watch list + market-factor watch list (Phase 3, added 2026-10-29).

Tables (created idempotently, additive only):
  investment_watchlist   - ideas Tho is watching (thesis, entry zone, target, triggers, costs, score, status, price)
  market_factors         - macro/market drivers (reading, source, as-of, trend, affected holdings, threshold)
  market_factor_history  - one row per factor per reading date
  watch_alert_state      - dedupe state for LINE alerts (alert only on a new condition)

Rules: free sources only; every reading carries source + timestamp; prices older
than 7 days are flagged stale; nothing here writes holdings units or cost.
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import math
import os
import re
import subprocess
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

import pandas as pd

from market_history import (SET_PROXY, download_closes, http_bytes, http_json, last_valid,
                            pct_change_over, utcnow)

LOGGER = logging.getLogger("portfolio_engine.watchlists")
ICT = ZoneInfo("Asia/Bangkok")
PROJECT_DIR = Path(__file__).resolve().parents[1]
LEGACY_WATCHLIST = PROJECT_DIR / "data" / "watchlist.json"
COUNCIL_REPORTS = PROJECT_DIR / "data" / "council" / "reports"
STATUS_FILE = PROJECT_DIR / "data" / "watchlists_status.json"
SECRETARY_DIR = Path(os.getenv("SECRETARY_DIR", "/Users/admin/Projects/ai_secretary_brain"))
LINE_NOTIFY = PROJECT_DIR / "ops" / "line_notify.py"
STALE_PRICE_DAYS = 7
HOLDINGS_FALLBACK = ["PTTEP.BK", "SCB.BK", "SCBGOLDE"]

DDL = """
CREATE TABLE IF NOT EXISTS investment_watchlist (
    id            SERIAL PRIMARY KEY,
    ticker        VARCHAR(30) UNIQUE NOT NULL,
    name          TEXT,
    asset_type    VARCHAR(40),
    market        VARCHAR(40),
    sector        VARCHAR(60),
    currency      VARCHAR(10) DEFAULT 'THB',
    thesis        TEXT,
    thesis_as_of  DATE,
    entry_low     NUMERIC(18,6),
    entry_high    NUMERIC(18,6),
    target_price  NUMERIC(18,6),
    stop_price    NUMERIC(18,6),
    triggers      JSONB DEFAULT '[]'::jsonb,
    costs         JSONB DEFAULT '{}'::jsonb,
    score         NUMERIC(6,2),
    score_basis   TEXT,
    status        VARCHAR(20) NOT NULL DEFAULT 'watching'
                  CHECK (status IN ('watching','ready','dropped')),
    status_note   TEXT,
    last_price    NUMERIC(18,6),
    price_source  VARCHAR(80),
    price_as_of   TIMESTAMPTZ,
    price_stale   BOOLEAN DEFAULT TRUE,
    metrics       JSONB DEFAULT '{}'::jsonb,
    seeded_from   TEXT,
    created_at    TIMESTAMPTZ DEFAULT now(),
    updated_at    TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS market_factors (
    key               VARCHAR(40) PRIMARY KEY,
    name              TEXT NOT NULL,
    category          VARCHAR(40),
    reading           NUMERIC(20,6),
    reading_text      TEXT,
    unit              VARCHAR(30),
    source            TEXT,
    source_url        TEXT,
    as_of             TIMESTAMPTZ,
    change_1d         NUMERIC(20,6),
    change_5d         NUMERIC(20,6),
    change_unit       VARCHAR(30),
    trend             VARCHAR(20),
    affected_holdings JSONB DEFAULT '[]'::jsonb,
    threshold         JSONB DEFAULT '{}'::jsonb,
    threshold_text    TEXT,
    breached          BOOLEAN DEFAULT FALSE,
    breach_reason     TEXT,
    stale             BOOLEAN DEFAULT FALSE,
    error             TEXT,
    details           JSONB DEFAULT '{}'::jsonb,
    updated_at        TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS market_factor_history (
    key        VARCHAR(40) NOT NULL,
    as_of      DATE NOT NULL,
    reading    NUMERIC(20,6),
    source     TEXT,
    recorded_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (key, as_of)
);
CREATE TABLE IF NOT EXISTS watch_alert_state (
    alert_key     TEXT PRIMARY KEY,
    active        BOOLEAN NOT NULL DEFAULT FALSE,
    first_seen    TIMESTAMPTZ DEFAULT now(),
    last_change   TIMESTAMPTZ DEFAULT now(),
    alerted_at    TIMESTAMPTZ,
    message       TEXT,
    primed        BOOLEAN DEFAULT FALSE
);
"""


async def ensure_tables(pool: Any) -> None:
    async with pool.acquire() as conn:
        await conn.execute(DDL)


def _j(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, default=str)


# --------------------------------------------------------------------------- seed
_TAX_TH = "Thai individual: SET capital gains exempt; dividends 10% WHT (final or credit)"
_TAX_US = ("US-listed: 15% US dividend WHT (treaty, W-8BEN); foreign income remitted to TH "
           "taxable from 2024 rules - verify with tax adviser")
_COST_TH = {"fees": "SET broker ~0.157% + VAT per side (online)", "hedge": "none (THB)", "tax": _TAX_TH}
_COST_US = {"fees": "offshore broker commission + FX spread (~0.2-0.5% round trip, verify)",
            "hedge": "unhedged USD exposure", "tax": _TAX_US}
DEFAULT_TRIGGERS = [
    {"type": "move_1d_pct", "value": 5, "note": "abs 1-day move >= 5%"},
    {"type": "rsi_below", "value": 30, "note": "RSI14 oversold"},
    {"type": "new_52w_low", "note": "close at a 52-week low"},
]
SEED: list[dict[str, Any]] = [
    # Thai ideas from the guru council (Jun 2026) + legacy watch list
    {"ticker": "KBANK.BK", "name": "Kasikornbank", "asset_type": "stock", "market": "SET", "sector": "banks"},
    {"ticker": "BBL.BK", "name": "Bangkok Bank", "asset_type": "stock", "market": "SET", "sector": "banks"},
    {"ticker": "KTB.BK", "name": "Krung Thai Bank", "asset_type": "stock", "market": "SET", "sector": "banks"},
    {"ticker": "TTB.BK", "name": "TMBThanachart Bank", "asset_type": "stock", "market": "SET", "sector": "banks"},
    {"ticker": "PTT.BK", "name": "PTT", "asset_type": "stock", "market": "SET", "sector": "energy"},
    {"ticker": "TOP.BK", "name": "Thai Oil", "asset_type": "stock", "market": "SET", "sector": "energy"},
    {"ticker": "IRPC.BK", "name": "IRPC", "asset_type": "stock", "market": "SET", "sector": "energy"},
    {"ticker": "AOT.BK", "name": "Airports of Thailand", "asset_type": "stock", "market": "SET", "sector": "transport"},
    {"ticker": "BAFS.BK", "name": "Bangkok Aviation Fuel Services", "asset_type": "stock", "market": "SET", "sector": "energy_services"},
    {"ticker": "ADVANC.BK", "name": "Advanced Info Service", "asset_type": "stock", "market": "SET", "sector": "telecom"},
    # US / EM ETFs and tech (legacy watch list)
    {"ticker": "SPY", "name": "S&P 500 ETF", "asset_type": "etf", "market": "US", "sector": "us_broad"},
    {"ticker": "QQQ", "name": "Nasdaq 100 ETF", "asset_type": "etf", "market": "US", "sector": "us_tech"},
    {"ticker": "NVDA", "name": "NVIDIA", "asset_type": "stock", "market": "US", "sector": "us_tech"},
    {"ticker": "MSFT", "name": "Microsoft", "asset_type": "stock", "market": "US", "sector": "us_tech"},
    {"ticker": "GOOGL", "name": "Alphabet", "asset_type": "stock", "market": "US", "sector": "us_tech"},
    {"ticker": "TSM", "name": "TSMC ADR", "asset_type": "stock", "market": "US", "sector": "us_tech"},
    {"ticker": "AVGO", "name": "Broadcom", "asset_type": "stock", "market": "US", "sector": "us_tech"},
    {"ticker": "MU", "name": "Micron Technology", "asset_type": "stock", "market": "US", "sector": "us_tech"},
    {"ticker": "VNM", "name": "VanEck Vietnam ETF", "asset_type": "etf", "market": "US", "sector": "em"},
    {"ticker": "EWJ", "name": "iShares MSCI Japan ETF", "asset_type": "etf", "market": "US", "sector": "em"},
    {"ticker": "INDA", "name": "iShares MSCI India ETF", "asset_type": "etf", "market": "US", "sector": "em"},
    {"ticker": "FXI", "name": "iShares China Large-Cap ETF", "asset_type": "etf", "market": "US", "sector": "em"},
    # Gold alternatives to SCBGOLDE (fee comparison)
    {"ticker": "GLDM", "name": "SPDR Gold MiniShares", "asset_type": "etf", "market": "US", "sector": "gold", "ter": 0.10},
    {"ticker": "IAU", "name": "iShares Gold Trust", "asset_type": "etf", "market": "US", "sector": "gold", "ter": 0.25},
    {"ticker": "GDX", "name": "VanEck Gold Miners ETF", "asset_type": "etf", "market": "US", "sector": "gold_miners"},
    # US Treasury ETFs (added 2026-11-01, t35u) - price/watch reference for the hedged Thai US-bond funds.
    # sector 'us_bond' is kept OUT of the signal / forecast / screen / trade-plan universes (see SIGNAL_EXCLUDED_SECTORS):
    # adding low-vol bond ETFs to the equity cross-section would change everyone's P3.3 scores without a gate run.
    {"ticker": "SGOV", "name": "iShares 0-3 Month Treasury Bond ETF", "asset_type": "etf", "market": "US", "sector": "us_bond", "ter": 0.09, "thesis": "[US bond reference 2026-11-01] 0-3 month T-bills: cash-like USD reference (no rate risk); THB investor carries full USD/THB risk. Watch/price alerts only - not in signals.", "seeded_from": "t35u US-bond research 2026-11-01"},
    {"ticker": "SHY", "name": "iShares 1-3 Year Treasury Bond ETF", "asset_type": "etf", "market": "US", "sector": "us_bond", "ter": 0.15, "thesis": "[US bond reference 2026-11-01] 1-3y Treasuries: low duration; hurts a little if the Fed hikes. Watch/price alerts only - not in signals.", "seeded_from": "t35u US-bond research 2026-11-01"},
    {"ticker": "IEF", "name": "iShares 7-10 Year Treasury Bond ETF", "asset_type": "etf", "market": "US", "sector": "us_bond", "ter": 0.15, "thesis": "[US bond reference 2026-11-01] 7-10y Treasuries: classic flight-to-quality hedge, but loses if yields rise (Fed hike / inflation). Watch/price alerts only - not in signals.", "seeded_from": "t35u US-bond research 2026-11-01"},
    {"ticker": "TIP", "name": "iShares TIPS Bond ETF", "asset_type": "etf", "market": "US", "sector": "us_bond", "ter": 0.18, "thesis": "[US bond reference 2026-11-01] US inflation-linked Treasuries: hedge for an oil/war inflation shock; still has rate risk. Watch/price alerts only - not in signals.", "seeded_from": "t35u US-bond research 2026-11-01"},
    # sector 'us_income' (covered-call / option-income ETFs): display + price alerts + forecasts only; kept OUT of
    # P3.3 signals, momentum screens, opportunity scanner and trade plans (strategy caps upside; not gated). t41u 2026-11-01.
    {"ticker": "JEPQ", "name": "JPMorgan Nasdaq Equity Premium Income ETF", "asset_type": "etf", "market": "US", "sector": "us_income", "ter": 0.35, "thesis": "[US income reference 2026-11-01] Nasdaq-100 stocks + call-option ELNs: ~11-12% monthly distribution (mostly ordinary income, 15% US WHT with W-8BEN), beta ~0.72 vs QQQ, captured ~72% of up / ~68% of down months since 2022; lagged QQQ ~4 pts/yr. Income tool, not a hedge. UCITS twin JEPQ LN (IE000U9J8HX9) and Thai feeders (KT-JEPQ, TLNDQINCOME-UH-X) avoid US estate tax. Watch/forecast only - not in signals/trade plans. See docs/research/jepq_20261101.md", "seeded_from": "t41u JEPQ research 2026-11-01"},
]

# Watch-list sectors that are display/price-alert only and never enter signals, forecasts, screens or trade plans.
SIGNAL_EXCLUDED_SECTORS = ("us_bond", "us_income")  # us_income: still forecast (predictions excludes us_bond only)
BOND_TRIGGERS = [
    {"type": "move_1d_pct", "value": 1.5, "note": "abs 1-day move >= 1.5% (large for Treasuries)"},
    {"type": "new_52w_low", "note": "close at a 52-week low"},
]
for _it in SEED:
    if _it.get("sector") == "us_bond":
        _it.setdefault("triggers", BOND_TRIGGERS)
SIGNAL_UNIVERSE_SQL = "status <> 'dropped' AND COALESCE(sector, '') NOT IN ('us_bond', 'us_income')"


def _legacy_notes() -> dict[str, tuple[str, Optional[str]]]:
    notes: dict[str, tuple[str, Optional[str]]] = {}
    try:
        data = json.loads(LEGACY_WATCHLIST.read_text(encoding="utf-8"))
        as_of = str((data.get("_meta") or {}).get("last_updated") or "")[:10] or None
        for group in (data.get("watchlist") or {}).values():
            if isinstance(group, dict):
                for t, v in group.items():
                    if isinstance(v, dict) and v.get("note"):
                        notes[t] = (str(v["note"]), as_of)
        for t, v in (data.get("holdings") or {}).items():
            if isinstance(v, dict) and v.get("note"):
                notes.setdefault(t, (str(v["note"]), as_of))
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("legacy watchlist unreadable: %s", exc)
    return notes


def _council_view(ticker: str) -> Optional[dict[str, Any]]:
    path = COUNCIL_REPORTS / f"{ticker}.json"
    if not path.exists():
        return None
    try:
        r = json.loads(path.read_text(encoding="utf-8"))
        chair = r.get("chair") or {}
        return {"label": chair.get("overall_label") or chair.get("overall_stance"),
                "conviction": chair.get("blended_conviction"),
                "as_of": str(r.get("created_at") or (r.get("investment") or {}).get("as_of") or "")[:10] or None}
    except Exception:  # noqa: BLE001
        return None


async def seed_investment_watchlist(pool: Any) -> int:
    """Insert seed rows that are not present yet. Never overwrites Tho's edits."""
    notes = _legacy_notes()
    inserted = 0
    async with pool.acquire() as conn:
        for item in SEED:
            t = item["ticker"]
            council = _council_view(t)
            note, note_as_of = notes.get(t, (None, None))
            thesis_bits = []
            if note:
                thesis_bits.append(f"[legacy watchlist {note_as_of}] {note}")
            if council and council.get("label"):
                thesis_bits.append(f"[guru council {council.get('as_of')}] {council['label']}")
            thesis = item.get("thesis") or "\n".join(thesis_bits) or "Thesis not written yet - Tho to add."
            score, basis = None, None
            if council and isinstance(council.get("conviction"), (int, float)):
                c = float(council["conviction"])
                score = round(c * 100 if abs(c) <= 1 else c, 2)
                basis = f"guru council blended conviction ({council.get('as_of')}); re-score"
            costs = dict(_COST_TH if item["market"] == "SET" else _COST_US)
            if item.get("ter") is not None:
                costs["ter_pct"] = item["ter"]
                costs["vs_holding"] = ("US Treasury ETF reference (unhedged USD): compare with FX-hedged Thai US-bond funds; TER = issuer expense ratio, verify on issuer page"
                                       if item["sector"] == "us_bond" else ("covered-call income ETF (unhedged USD): compare with QQQ total return, UCITS JEPQ LN and Thai feeders (KT-JEPQ / TLNDQINCOME-UH-X)" if item["sector"] == "us_income" else "alternative to SCBGOLDE: compare TER vs SCBGOLDE fees + FX"))
            res = await conn.execute(
                """INSERT INTO investment_watchlist (ticker, name, asset_type, market, sector, currency,
                       thesis, thesis_as_of, triggers, costs, score, score_basis, seeded_from)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb,$10::jsonb,$11,$12,$13)
                   ON CONFLICT (ticker) DO NOTHING""",
                t, item["name"], item["asset_type"], item["market"], item["sector"],
                "THB" if item["market"] == "SET" else "USD", thesis,
                date.fromisoformat(note_as_of or council.get("as_of")) if (note_as_of or (council or {}).get("as_of")) else None,
                _j(item.get("triggers") or DEFAULT_TRIGGERS), _j(costs), score, basis,
                item.get("seeded_from") or "data/watchlist.json + data/council/reports (2026-10-29 seed)",
            )
            inserted += int(res.split()[-1])
    return inserted


# ------------------------------------------------------------ technicals / prices
def _rsi(series: pd.Series, n: int = 14) -> Optional[float]:
    s = series.dropna()
    if len(s) < n + 1:
        return None
    d = s.diff().dropna()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up.iloc[-1] / dn.iloc[-1] if dn.iloc[-1] else math.inf
    return round(100 - 100 / (1 + rs), 2)


def _metrics(series: pd.Series) -> dict[str, Any]:
    s = series.dropna()
    if s.empty:
        return {}
    last = float(s.iloc[-1])
    year = s.iloc[-252:]
    return {
        "change_1d_pct": round(pct_change_over(s, 1), 2) if pct_change_over(s, 1) is not None else None,
        "change_5d_pct": round(pct_change_over(s, 5), 2) if pct_change_over(s, 5) is not None else None,
        "change_20d_pct": round(pct_change_over(s, 20), 2) if pct_change_over(s, 20) is not None else None,
        "rsi14": _rsi(s),
        "high_52w": round(float(year.max()), 4),
        "low_52w": round(float(year.min()), 4),
        "at_52w_low": bool(last <= float(year.min()) * 1.0001),
        "at_52w_high": bool(last >= float(year.max()) * 0.9999),
        "sma50": round(float(s.iloc[-50:].mean()), 4) if len(s) >= 50 else None,
        "sma200": round(float(s.iloc[-200:].mean()), 4) if len(s) >= 200 else None,
    }


async def refresh_investment_prices(pool: Any) -> dict[str, Any]:
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT ticker FROM investment_watchlist WHERE status <> 'dropped'")
    tickers = [r["ticker"] for r in rows]
    if not tickers:
        return {"updated": 0}
    closes = await asyncio.to_thread(download_closes, tickers, None, "1y")
    now = utcnow()
    updated, missing = 0, []
    async with pool.acquire() as conn:
        for t in tickers:
            series = closes[t] if t in closes.columns else pd.Series(dtype=float)
            price, ts = last_valid(series)
            if price is None:
                missing.append(t)
                await conn.execute(
                    """UPDATE investment_watchlist SET price_stale = (price_as_of IS NULL OR price_as_of < now() - interval '7 days'),
                       updated_at = now() WHERE ticker=$1""", t)
                continue
            as_of = ts.to_pydatetime().replace(tzinfo=ICT if t.endswith(".BK") else ZoneInfo("America/New_York"))
            stale = (now - as_of.astimezone(timezone.utc)).days > STALE_PRICE_DAYS
            await conn.execute(
                """UPDATE investment_watchlist SET last_price=$2, price_source=$3, price_as_of=$4, price_stale=$5,
                       metrics=$6::jsonb, updated_at=now() WHERE ticker=$1""",
                t, price, "yfinance daily close", as_of, stale, _j(_metrics(series)))
            updated += 1
    if missing:
        LOGGER.warning("No price for watch-list tickers: %s", missing)
    return {"updated": updated, "missing": missing}


# ------------------------------------------------------------------- alerts
def _conditions(row: dict[str, Any]) -> list[tuple[str, str]]:
    """Active alert conditions for one watch-list row -> [(key, message)]."""
    out: list[tuple[str, str]] = []
    price = row.get("last_price")
    if price is None or row.get("price_stale") or row.get("status") == "dropped":
        return out
    p = float(price)
    t = row["ticker"]
    m = row.get("metrics") or {}
    lo, hi = row.get("entry_low"), row.get("entry_high")
    if lo is not None or hi is not None:
        lo_f = float(lo) if lo is not None else -math.inf
        hi_f = float(hi) if hi is not None else math.inf
        if lo_f <= p <= hi_f:
            out.append((f"{t}:entry_zone", f"{t} entered entry zone {lo or '-'}-{hi or '-'} (price {p:g})"))
    if row.get("target_price") is not None and p >= float(row["target_price"]):
        out.append((f"{t}:target", f"{t} reached target {row['target_price']} (price {p:g})"))
    if row.get("stop_price") is not None and p <= float(row["stop_price"]):
        out.append((f"{t}:stop", f"{t} at/below stop {row['stop_price']} (price {p:g})"))
    for trig in row.get("triggers") or []:
        typ, val = trig.get("type"), trig.get("value")
        hit = False
        if typ == "move_1d_pct" and m.get("change_1d_pct") is not None and val is not None:
            hit = abs(float(m["change_1d_pct"])) >= float(val)
            desc = f"moved {m.get('change_1d_pct')}% in 1 day"
        elif typ == "rsi_below" and m.get("rsi14") is not None and val is not None:
            hit = float(m["rsi14"]) < float(val)
            desc = f"RSI14 {m.get('rsi14')} < {val}"
        elif typ == "rsi_above" and m.get("rsi14") is not None and val is not None:
            hit = float(m["rsi14"]) > float(val)
            desc = f"RSI14 {m.get('rsi14')} > {val}"
        elif typ == "new_52w_low":
            hit = bool(m.get("at_52w_low"))
            desc = "closed at a 52-week low"
        elif typ == "new_52w_high":
            hit = bool(m.get("at_52w_high"))
            desc = "closed at a 52-week high"
        elif typ == "price_below" and val is not None:
            hit, desc = p <= float(val), f"price {p:g} <= {val}"
        elif typ == "price_above" and val is not None:
            hit, desc = p >= float(val), f"price {p:g} >= {val}"
        else:
            continue
        if hit:
            out.append((f"{t}:{typ}:{val}", f"{t} trigger: {desc} (price {p:g})"))
    return out


def _send_line(text: str) -> tuple[bool, str]:
    """Send via the secretary's line_client.send_to_owner (respects DND). Dry-run by env."""
    if os.getenv("WATCH_ALERTS_DRY_RUN", "0") == "1":
        LOGGER.info("DRY-RUN watch alert: %s", text.replace("\n", " | "))
        return True, "dry_run"
    py = SECRETARY_DIR / "venv" / "bin" / "python"
    try:
        proc = subprocess.run([str(py), str(LINE_NOTIFY)], input=text, text=True,
                              capture_output=True, timeout=60, cwd=str(SECRETARY_DIR))
        ok = proc.returncode == 0
        return ok, (proc.stdout.strip() or proc.stderr.strip())[-200:]
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


async def evaluate_alerts(pool: Any) -> dict[str, Any]:
    """Alert once when a condition becomes active (deduped in watch_alert_state).

    First-ever run only primes the state (no message) so pre-existing conditions do
    not flood LINE. Quiet hours 22:00-07:00 ICT: pending alerts wait for the next run.
    """
    async with pool.acquire() as conn:
        rows = [dict(r) for r in await conn.fetch("SELECT * FROM investment_watchlist")]
        for r in rows:
            for k in ("metrics", "triggers"):
                if isinstance(r.get(k), str):
                    r[k] = json.loads(r[k])
        states = {r["alert_key"]: dict(r) for r in await conn.fetch("SELECT * FROM watch_alert_state")}
        first_run = "__primed__" not in states
        active: dict[str, str] = {}
        for r in rows:
            for key, msg in _conditions(r):
                active[key] = msg
            # auto-promote to ready when inside entry zone
            if f"{r['ticker']}:entry_zone" in active and r["status"] == "watching":
                await conn.execute("UPDATE investment_watchlist SET status='ready', status_note=$2, updated_at=now() WHERE ticker=$1",
                                   r["ticker"], f"auto: entered entry zone {datetime.now(ICT):%Y-%m-%d %H:%M} ICT")
        pending: list[tuple[str, str]] = []
        for key, msg in active.items():
            st = states.get(key)
            if st is None:
                await conn.execute(
                    "INSERT INTO watch_alert_state (alert_key, active, message, primed, alerted_at) VALUES ($1, TRUE, $2, $3, NULL)",
                    key, msg, first_run)
                if not first_run:
                    pending.append((key, msg))
            elif not st["active"]:
                await conn.execute("UPDATE watch_alert_state SET active=TRUE, last_change=now(), message=$2, primed=FALSE, alerted_at=NULL WHERE alert_key=$1", key, msg)
                pending.append((key, msg))
            elif st["alerted_at"] is None and not st["primed"]:
                pending.append((key, msg))  # was held by quiet hours / failed send
        for key, st in states.items():
            if key != "__primed__" and st["active"] and key not in active:
                await conn.execute("UPDATE watch_alert_state SET active=FALSE, last_change=now() WHERE alert_key=$1", key)
        if first_run:
            await conn.execute("INSERT INTO watch_alert_state (alert_key, active, message, primed) VALUES ('__primed__', TRUE, $1, TRUE) ON CONFLICT DO NOTHING",
                               f"primed {datetime.now(ICT):%Y-%m-%d %H:%M} ICT with {len(active)} active conditions")
        sent, result = False, "nothing to send"
        hour = datetime.now(ICT).hour
        if pending and (hour >= 22 or hour < 7):
            result = f"quiet hours: {len(pending)} alert(s) held until 07:00 ICT"
        elif pending:
            text = "👀 Watch list alert\n" + "\n".join(f"• {m}" for _, m in pending[:10])
            if len(pending) > 10:
                text += f"\n…and {len(pending) - 10} more (see dashboard)"
            text += "\n(Not advice to trade. Check the dashboard before acting.)"
            sent, result = await asyncio.to_thread(_send_line, text)
            if sent:
                for key, _ in pending:
                    await conn.execute("UPDATE watch_alert_state SET alerted_at=now() WHERE alert_key=$1", key)
    return {"active": len(active), "pending": len(pending), "first_run": first_run, "sent": sent, "result": result,
            "active_conditions": list(active.values())}


# ----------------------------------------------------------------- factors
def _trend(change: Optional[float], flat: float) -> str:
    if change is None:
        return "n/a"
    return "up" if change > flat else "down" if change < -flat else "flat"


def _price_factor(closes: pd.DataFrame, ticker: str, *, unit: str, flat: float,
                  pct: bool = True) -> dict[str, Any]:
    series = closes[ticker] if ticker in closes.columns else pd.Series(dtype=float)
    price, ts = last_valid(series)
    if price is None:
        raise RuntimeError(f"no data for {ticker}")
    s = series.dropna()
    if pct:
        c1, c5 = pct_change_over(s, 1), pct_change_over(s, 5)
        cu = "%"
    else:
        c1 = float(s.iloc[-1] - s.iloc[-2]) if len(s) > 1 else None
        c5 = float(s.iloc[-1] - s.iloc[-6]) if len(s) > 5 else None
        cu = "pt"
    return {"reading": price, "unit": unit, "reading_text": f"{price:,.2f} {unit}", "as_of": ts.to_pydatetime().replace(tzinfo=timezone.utc),
            "change_1d": c1, "change_5d": c5, "change_unit": cu, "trend": _trend(c5, flat),
            "source": f"yfinance {ticker} daily close", "source_url": f"https://finance.yahoo.com/quote/{ticker}"}


async def _news_factor(pool: Any, patterns: list[str]) -> dict[str, Any]:
    where = " OR ".join(f"n.title ILIKE ${i + 1}" for i in range(len(patterns)))
    args = [f"%{p}%" for p in patterns]
    async with pool.acquire() as conn:
        c24 = await conn.fetchval(f"SELECT count(*) FROM news_articles n WHERE ({where}) AND n.published_at > now() - interval '24 hours'", *args)
        c7 = await conn.fetchval(f"SELECT count(*) FROM news_articles n WHERE ({where}) AND n.published_at > now() - interval '7 days'", *args)
        heads = await conn.fetch(f"SELECT n.title, n.source, n.url, n.published_at FROM news_articles n WHERE ({where}) ORDER BY n.published_at DESC NULLS LAST LIMIT 3", *args)
        sent = await conn.fetchrow(
            f"""SELECT avg(CASE s.sentiment WHEN 'bullish' THEN 1 WHEN 'bearish' THEN -1 ELSE 0 END) AS tone, count(*) AS n
                FROM news_articles n JOIN sentiment_scores s ON s.article_id = n.id
                WHERE ({where}) AND n.published_at > now() - interval '72 hours'""", *args)
    avg7 = (c7 or 0) / 7.0
    latest = heads[0] if heads else None
    return {
        "reading": float(c24 or 0), "unit": "articles/24h",
        "reading_text": (latest["title"][:200] if latest else "no matching headlines"),
        "as_of": (latest["published_at"] if latest else utcnow()),
        "change_1d": float(c24 or 0) - avg7, "change_5d": None, "change_unit": "vs 7d avg",
        "trend": _trend(float(c24 or 0) - avg7, max(1.0, avg7 * 0.25)),
        "source": "news_articles (Reuters/Bangkok Post/Yahoo feeds) + local sentiment model",
        "source_url": latest["url"] if latest else None,
        "details": {"count_24h": c24, "count_7d": c7, "avg_per_day_7d": round(avg7, 2),
                    "tone_72h": float(sent["tone"]) if sent and sent["tone"] is not None else None,
                    "scored_72h": sent["n"] if sent else 0,
                    "headlines": [{"title": h["title"], "source": h["source"], "url": h["url"],
                                   "published_at": h["published_at"].isoformat() if h["published_at"] else None} for h in heads]},
    }


def _bot_policy_rate(recent_n: int = 4) -> dict[str, Any]:  # recent_n added 2026-10-31 (macro board needs the last change)
    page_url = "https://www.bot.or.th/en/our-roles/monetary-policy/mpc-publication/policy-interest-rate.html"
    html_text = http_bytes(page_url).decode("utf-8", "replace")
    m = re.search(r'(/content/dam/bot/documents/en/our-roles/monetary-policy/mpc-publication/policy-interest-rate/[^"\'\\&]+\.xlsx)', html_text)
    if not m:
        raise RuntimeError("BoT MPC table link not found")
    xurl = "https://www.bot.or.th" + m.group(1)
    z = zipfile.ZipFile(io.BytesIO(http_bytes(xurl)))
    sx = z.read("xl/sharedStrings.xml").decode()
    ss = ["".join(re.findall(r"<t[^>]*>([^<]*)</t>", si)) for si in re.findall(r"<si>(.*?)</si>", sx, flags=re.S)]
    sheet = z.read("xl/worksheets/sheet1.xml").decode()
    data = []
    for r in re.findall(r"<row[^>]*>(.*?)</row>", sheet, flags=re.S):
        d = {}
        for c in re.finditer(r'<c r="([A-Z]+)\d+"([^>]*?)(?:/>|>(.*?)</c>)', r, flags=re.S):
            v = re.search(r"<v>([^<]*)</v>", c.group(3) or "")
            if v:
                d[c.group(1)] = ss[int(v.group(1))] if 't="s"' in c.group(2) else v.group(1)
        if re.fullmatch(r"\d{5}(\.0)?", d.get("B", "") or "") and d.get("H"):
            data.append((date(1899, 12, 30) + timedelta(days=int(float(d["B"]))), float(d["H"]), d.get("G", "")))
    if not data:
        raise RuntimeError("BoT MPC table empty")
    data.sort()
    last, prev = data[-1], data[-2] if len(data) > 1 else None
    change = (last[1] - prev[1]) if prev else None
    return {"reading": last[1], "unit": "% p.a.", "reading_text": f"MPC {last[0]:%d %b %Y}: {last[2]} at {last[1]:.2f}%",
            "as_of": datetime(last[0].year, last[0].month, last[0].day, tzinfo=ICT),
            "change_1d": change, "change_5d": None, "change_unit": "pp vs prior MPC",
            "trend": _trend(change, 0.01), "source": "Bank of Thailand MPC decisions table (xlsx)",
            "source_url": page_url, "details": {"recent": [(d.isoformat(), r, g) for d, r, g in data[-recent_n:]]}}


def _fred_key() -> Optional[str]:
    key = os.getenv("FRED_API_KEY", "")
    return key if re.fullmatch(r"[a-z0-9]{32}", key or "") else None


def _fred_latest(series_id: str) -> dict[str, Any]:
    key = _fred_key()
    if not key:
        raise RuntimeError("FRED_API_KEY missing/invalid")
    url = (f"https://api.stlouisfed.org/fred/series/observations?series_id={series_id}&api_key={key}"
           "&file_type=json&sort_order=desc&limit=6")
    obs = [o for o in http_json(url)["observations"] if o.get("value") not in (".", None)]
    v0, v1 = float(obs[0]["value"]), float(obs[1]["value"]) if len(obs) > 1 else None
    return {"reading": v0, "as_of": datetime.fromisoformat(obs[0]["date"]).replace(tzinfo=timezone.utc),
            "change_1d": (v0 - v1) if v1 is not None else None, "change_unit": "vs prior obs",
            "source": f"FRED {series_id}", "source_url": f"https://fred.stlouisfed.org/series/{series_id}"}


def _fed_rate() -> dict[str, Any]:
    try:
        r = _fred_latest("DFF")
        r.update(unit="%", trend=_trend(r.get("change_1d"), 0.01))
        return r
    except Exception as exc:  # noqa: BLE001
        LOGGER.info("FRED unavailable for Fed rate (%s); using NY Fed EFFR", exc)
    d = http_json("https://markets.newyorkfed.org/api/rates/unsecured/effr/last/6.json")["refRates"]
    d = sorted(d, key=lambda x: x["effectiveDate"])
    last, first = d[-1], d[0]
    return {"reading": float(last["percentRate"]), "unit": "%",
            "reading_text": f"EFFR {last['percentRate']}% (target {last.get('targetRateFrom')}-{last.get('targetRateTo')}%)",
            "as_of": datetime.fromisoformat(last["effectiveDate"]).replace(tzinfo=timezone.utc),
            "change_1d": float(last["percentRate"]) - float(d[-2]["percentRate"]) if len(d) > 1 else None,
            "change_5d": float(last["percentRate"]) - float(first["percentRate"]), "change_unit": "pp",
            "trend": _trend(float(last["percentRate"]) - float(first["percentRate"]), 0.05),
            "source": "NY Fed EFFR API (FRED fallback - key invalid)",
            "source_url": "https://www.newyorkfed.org/markets/reference-rates/effr",
            "details": {"target_from": last.get("targetRateFrom"), "target_to": last.get("targetRateTo")}}


def _set_foreign_flow() -> dict[str, Any]:
    import http.cookiejar
    import urllib.request as ur
    jar = http.cookiejar.CookieJar()
    opener = ur.build_opener(ur.HTTPCookieProcessor(jar))
    page = "https://www.set.or.th/en/market/statistics/investor-type"
    opener.open(ur.Request(page, headers={"User-Agent": "Mozilla/5.0"}), timeout=20).read()
    d = http_json("https://www.set.or.th/api/set/market/SET/investor-type", headers={"Referer": page}, opener=opener)
    foreign = next(i for i in d["investors"] if i["type"] == "foreign")
    net_bn = float(foreign["netValue"]) / 1e9
    return {"reading": round(net_bn, 3), "unit": "THB bn net (day)",
            "reading_text": f"Foreign {'net BUY' if net_bn >= 0 else 'net SELL'} {abs(net_bn):.2f} bn THB",
            "as_of": datetime.fromisoformat(d["asOfDate"]), "change_unit": "THB bn",
            "source": "SET investor-type statistics", "source_url": page,
            "details": {"total_value_bn": round(float(d["totalValue"]) / 1e9, 2),
                        "by_type": {i["type"]: round(float(i["netValue"]) / 1e9, 3) for i in d["investors"]}}}


def _worldbank_growth(iso3: str) -> dict[str, Any]:
    try:
        series = {"CHN": None, "USA": "A191RL1Q225SBEA"}.get(iso3)
        if series:
            r = _fred_latest(series)
            r.update(unit="% q/q saar", trend=_trend(r.get("change_1d"), 0.2))
            return r
    except Exception as exc:  # noqa: BLE001
        LOGGER.info("FRED unavailable for %s growth (%s); using World Bank", iso3, exc)
    d = http_json(f"https://api.worldbank.org/v2/country/{iso3}/indicator/NY.GDP.MKTP.KD.ZG?format=json&mrv=3", timeout=40)
    pts = [p for p in d[1] if p.get("value") is not None]
    last, prev = pts[0], pts[1] if len(pts) > 1 else None
    ch = float(last["value"]) - float(prev["value"]) if prev else None
    return {"reading": round(float(last["value"]), 2), "unit": "% y/y (annual)",
            "reading_text": f"{iso3} real GDP growth {float(last['value']):.1f}% in {last['date']}",
            "as_of": datetime(int(last["date"]), 12, 31, tzinfo=timezone.utc), "change_1d": ch,
            "change_unit": "pp vs prior year", "trend": _trend(ch, 0.2),
            "source": "World Bank WDI (FRED quarterly preferred once key supplied)",
            "source_url": f"https://data.worldbank.org/indicator/NY.GDP.MKTP.KD.ZG?locations={iso3[:2]}",
            "details": {"annual_only": True}}


def _calendar(holdings: list[str]) -> dict[str, Any]:
    import yfinance as yf
    events = []
    for t in holdings:
        if not t.endswith(".BK") and "." not in t and not t.isalpha():
            continue
        if t == "SCBGOLDE":
            continue
        try:
            cal = yf.Ticker(t).calendar or {}
        except Exception as exc:  # noqa: BLE001
            LOGGER.info("calendar %s failed: %s", t, exc)
            continue
        for d in cal.get("Earnings Date") or []:
            events.append({"ticker": t, "event": "earnings", "date": str(d)})
        if cal.get("Ex-Dividend Date"):
            events.append({"ticker": t, "event": "ex-dividend (XD)", "date": str(cal["Ex-Dividend Date"])})
    today = date.today()
    upcoming = sorted([e for e in events if date.fromisoformat(e["date"]) >= today - timedelta(days=1)], key=lambda e: e["date"])
    recent = sorted([e for e in events if date.fromisoformat(e["date"]) < today - timedelta(days=1)], key=lambda e: e["date"])[-3:]
    nxt = upcoming[0] if upcoming else None
    days = (date.fromisoformat(nxt["date"]) - today).days if nxt else None
    return {"reading": float(days) if days is not None else None, "unit": "days to next event",
            "reading_text": (f"{nxt['ticker']} {nxt['event']} {nxt['date']}" if nxt else "no upcoming events published"),
            "as_of": utcnow(), "change_unit": "days", "trend": "n/a",
            "source": "yfinance calendar (company-published dates; verify on SET)",
            "source_url": "https://www.set.or.th/en/market/stock-calendar/x-calendar",
            "details": {"upcoming": upcoming[:8], "recent": recent}}


FACTORS: list[dict[str, Any]] = [
    {"key": "brent", "name": "Brent crude", "category": "commodities", "yf": "BZ=F", "unit": "USD/bbl", "flat": 1.0,
     "affected": ["PTTEP.BK (+)", "BAFS.BK (-) jet fuel", "Thai CPI/BoT"], "threshold": {"abs_1d": 3.0, "abs_5d": 7.0},
     "threshold_text": "|1d| >= 3% or |5d| >= 7%"},
    {"key": "us_iran_news", "name": "US-Iran / Hormuz news", "category": "geopolitics", "news": ["Iran", "Hormuz", "Tehran"],
     "affected": ["PTTEP.BK", "SCBGOLDE (safe haven)", "Brent"], "threshold": {"count_24h_vs_avg": 2.0, "tone_below": -0.4},
     "threshold_text": "24h headlines >= 2x 7-day average, or 72h tone <= -0.4"},
    {"key": "bot_rate", "name": "Bank of Thailand policy rate", "category": "rates", "fn": "bot",
     "affected": ["SCB.BK (NIM)", "THB", "Thai equities"], "threshold": {"any_change": True},
     "threshold_text": "any change at an MPC meeting"},
    {"key": "fed_rate", "name": "US Fed funds (effective)", "category": "rates", "fn": "fed",
     "affected": ["USD/THB", "SCBGOLDE", "US watch list"], "threshold": {"abs_change": 0.10},
     "threshold_text": "change >= 0.10pp"},
    {"key": "us10y", "name": "US 10-year Treasury yield", "category": "rates", "yf": "^TNX", "unit": "%", "flat": 0.05, "pct": False,
     "affected": ["SCBGOLDE (-)", "growth stocks (-)"], "threshold": {"abs_5d_pt": 0.25}, "threshold_text": "|5d| >= 0.25pp"},
    {"key": "usdthb", "name": "USD/THB", "category": "fx", "yf": "THB=X", "unit": "THB per USD", "flat": 0.3,
     "affected": ["SCBGOLDE (+) unhedged USD gold", "US watch list (+) in THB", "PTTEP.BK (+) USD revenue"],
     "threshold": {"abs_1d": 1.0, "abs_5d": 2.0}, "threshold_text": "|1d| >= 1% or |5d| >= 2%"},
    # 2026-10-31 FX layer: other baht crosses + the broad dollar (free yfinance). Feed fx_risk.py and the brief.
    {"key": "dxy", "name": "US dollar index (DXY)", "category": "fx", "yf": "DX-Y.NYB", "unit": "index", "flat": 0.3,
     "affected": ["USD/THB (+)", "SCBGOLDE (-) gold usually falls when the dollar rises", "EM/Thai equity flows (-)"],
     "threshold": {"abs_1d": 0.8, "abs_5d": 2.0}, "threshold_text": "|1d| >= 0.8% or |5d| >= 2%"},
    {"key": "eurthb", "name": "EUR/THB", "category": "fx", "yf": "EURTHB=X", "unit": "THB per EUR", "flat": 0.3,
     "affected": ["European exposure in THB (+)", "Thai exporters to EU"], "threshold": {"abs_1d": 1.0, "abs_5d": 2.5},
     "threshold_text": "|1d| >= 1% or |5d| >= 2.5%"},
    {"key": "jpythb", "name": "JPY/THB", "category": "fx", "yf": "JPYTHB=X", "unit": "THB per JPY", "flat": 0.3,
     "affected": ["Japan exposure in THB (+)", "Thai auto/industrial supply chain"], "threshold": {"abs_1d": 1.2, "abs_5d": 3.0},
     "threshold_text": "|1d| >= 1.2% or |5d| >= 3%"},
    {"key": "sgdthb", "name": "SGD/THB (regional FX check)", "category": "fx", "yf": "SGDTHB=X", "unit": "THB per SGD", "flat": 0.3,
     "affected": ["regional exposure in THB (+)", "THB-specific vs regional move"], "threshold": {"abs_1d": 0.8, "abs_5d": 2.0},
     "threshold_text": "|1d| >= 0.8% or |5d| >= 2%"},
    {"key": "gold", "name": "Gold (COMEX front month)", "category": "commodities", "yf": "GC=F", "unit": "USD/oz", "flat": 0.5,
     "affected": ["SCBGOLDE (+)"], "threshold": {"abs_1d": 2.0, "abs_5d": 5.0}, "threshold_text": "|1d| >= 2% or |5d| >= 5%"},
    {"key": "set_index", "name": "TDEX (SET50 ETF proxy) - reading is the ETF price, SET level in text", "category": "equity", "yf": SET_PROXY, "unit": "TDEX THB", "flat": 0.5,
     "affected": ["PTTEP.BK (+)", "SCB.BK (+)", "Thai watch list (+)"], "threshold": {"abs_1d": 1.5, "abs_5d": 4.0},
     "threshold_text": "|1d| >= 1.5% or |5d| >= 4%"},
    {"key": "set_foreign_flow", "name": "SET foreign investor net flow", "category": "flows", "fn": "set_flow",
     "affected": ["SCB.BK", "PTTEP.BK", "THB"], "threshold": {"abs_day_bn": 3.0, "abs_5d_bn": 10.0},
     "threshold_text": "|day| >= 3bn THB or |5-day sum| >= 10bn THB"},
    {"key": "thai_econ_politics", "name": "Thai economy & politics news", "category": "thailand",
     "news": ["Thai economy", "Thailand econom", "Thai GDP", "Thai government", "Thai prime minister", "Thai PM", "Thai election",
              "Thai parliament", "Thai budget", "Bank of Thailand", "Thai baht", "Thailand's"],
     "affected": ["SCB.BK", "Thai equities", "THB"], "threshold": {"count_24h_vs_avg": 2.0, "tone_below": -0.4},
     "threshold_text": "24h headlines >= 2x 7-day average, or 72h tone <= -0.4"},
    {"key": "china_growth", "name": "China growth", "category": "global_growth", "fn": "wb_chn",
     "affected": ["PTTEP.BK (oil demand)", "Thai exports/tourism", "FXI"], "threshold": {"below": 4.5},
     "threshold_text": "real GDP growth < 4.5%"},
    {"key": "us_growth", "name": "US growth", "category": "global_growth", "fn": "wb_usa",
     "affected": ["US watch list", "risk appetite"], "threshold": {"below": 1.0}, "threshold_text": "real GDP growth < 1.0%"},
    {"key": "earnings_xd", "name": "Earnings / XD calendar (holdings)", "category": "calendar", "fn": "calendar",
     "affected": [], "threshold": {"days_within": 7}, "threshold_text": "event within 7 days"},
]


def _breach(f: dict[str, Any], r: dict[str, Any], hist5: Optional[float]) -> tuple[bool, Optional[str]]:
    th = f.get("threshold") or {}
    c1, c5 = r.get("change_1d"), r.get("change_5d")
    reasons = []
    if "abs_1d" in th and c1 is not None and abs(c1) >= th["abs_1d"]:
        reasons.append(f"1d {c1:+.2f}%")
    if "abs_5d" in th and c5 is not None and abs(c5) >= th["abs_5d"]:
        reasons.append(f"5d {c5:+.2f}%")
    if "abs_5d_pt" in th and c5 is not None and abs(c5) >= th["abs_5d_pt"]:
        reasons.append(f"5d {c5:+.2f}pp")
    if "abs_change" in th and c1 is not None and abs(c1) >= th["abs_change"]:
        reasons.append(f"change {c1:+.2f}pp")
    if th.get("any_change") and c1 and abs(c1) > 1e-9 and r.get("as_of") and (utcnow() - r["as_of"]).days <= 7:
        reasons.append(f"MPC change {c1:+.2f}pp")
    if "below" in th and r.get("reading") is not None and r["reading"] < th["below"]:
        reasons.append(f"{r['reading']:.2f} < {th['below']}")
    if "days_within" in th and r.get("reading") is not None and 0 <= r["reading"] <= th["days_within"]:
        reasons.append(f"{r.get('reading_text')} in {int(r['reading'])}d")
    if "abs_day_bn" in th and r.get("reading") is not None and abs(r["reading"]) >= th["abs_day_bn"]:
        reasons.append(f"day {r['reading']:+.2f}bn")
    if "abs_5d_bn" in th and hist5 is not None and abs(hist5) >= th["abs_5d_bn"]:
        reasons.append(f"5-day {hist5:+.2f}bn")
    det = r.get("details") or {}
    if "count_24h_vs_avg" in th and det.get("avg_per_day_7d") is not None:
        avg = max(float(det["avg_per_day_7d"]), 1.0)
        if float(det.get("count_24h") or 0) >= th["count_24h_vs_avg"] * avg and (det.get("count_24h") or 0) >= 3:
            reasons.append(f"{det['count_24h']} headlines/24h vs {det['avg_per_day_7d']}/day")
    if "tone_below" in th and det.get("tone_72h") is not None and det.get("scored_72h", 0) >= 3 and det["tone_72h"] <= th["tone_below"]:
        reasons.append(f"tone {det['tone_72h']:+.2f}")
    return bool(reasons), "; ".join(reasons) or None


async def _holding_tickers(pool: Any) -> list[str]:
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT ticker FROM holdings WHERE quantity > 0 ORDER BY ticker")
        return [r["ticker"] for r in rows] or HOLDINGS_FALLBACK
    except Exception:  # noqa: BLE001
        return HOLDINGS_FALLBACK


async def refresh_market_factors(pool: Any) -> dict[str, Any]:
    yf_tickers = [f["yf"] for f in FACTORS if f.get("yf")]
    closes = None
    try:
        closes = await asyncio.to_thread(download_closes, yf_tickers, None, "3mo")
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("factor price download failed: %s", exc)
    holdings = await _holding_tickers(pool)
    ok, failed = [], []
    for f in FACTORS:
        try:
            if f.get("yf"):
                if closes is None:
                    raise RuntimeError("price download failed")
                r = _price_factor(closes, f["yf"], unit=f["unit"], flat=f["flat"], pct=f.get("pct", True))
                if f["key"] == "set_index":
                    try:
                        lvl = await asyncio.to_thread(download_closes, ["^SET.BK"], None, "5d")
                        v, ts = last_valid(lvl["^SET.BK"]) if "^SET.BK" in lvl.columns else (None, None)
                        if v:
                            r["reading_text"] = f"SET {v:,.2f} ({ts:%Y-%m-%d}); trend/changes from {SET_PROXY}"
                    except Exception:  # noqa: BLE001
                        pass
                if f["key"] == "usdthb":
                    r["reading_text"] = f"{r['reading']:.3f} THB/USD (THB {'weaker' if (r.get('change_5d') or 0) > 0 else 'stronger'} over 5d)"
            elif f.get("news"):
                r = await _news_factor(pool, f["news"])
            elif f["fn"] == "bot":
                r = await asyncio.to_thread(_bot_policy_rate)
            elif f["fn"] == "fed":
                r = await asyncio.to_thread(_fed_rate)
            elif f["fn"] == "set_flow":
                r = await asyncio.to_thread(_set_foreign_flow)
            elif f["fn"] == "wb_chn":
                r = await asyncio.to_thread(_worldbank_growth, "CHN")
            elif f["fn"] == "wb_usa":
                r = await asyncio.to_thread(_worldbank_growth, "USA")
            elif f["fn"] == "calendar":
                r = await asyncio.to_thread(_calendar, holdings)
                f = {**f, "affected": sorted({e["ticker"] for e in (r.get("details") or {}).get("upcoming", [])}) or holdings}
            else:
                continue
            async with pool.acquire() as conn:
                hist5 = None
                if r.get("reading") is not None and r.get("as_of"):
                    await conn.execute(
                        """INSERT INTO market_factor_history (key, as_of, reading, source) VALUES ($1,$2,$3,$4)
                           ON CONFLICT (key, as_of) DO UPDATE SET reading=EXCLUDED.reading, source=EXCLUDED.source, recorded_at=now()""",
                        f["key"], r["as_of"].astimezone(ICT).date(), r["reading"], r.get("source"))
                if f["key"] == "set_foreign_flow":
                    hist5 = await conn.fetchval("SELECT sum(reading) FROM (SELECT reading FROM market_factor_history WHERE key=$1 ORDER BY as_of DESC LIMIT 5) x", f["key"])
                    hist5 = float(hist5) if hist5 is not None else None
                    r.setdefault("details", {})["sum_last5_recorded_bn"] = hist5
                    r["change_5d"] = hist5
                breached, reason = _breach(f, r, hist5)
                age_days = (utcnow() - r["as_of"]).days if r.get("as_of") else None
                stale_limit = {"rates": 120, "global_growth": 800, "calendar": 2}.get(f["category"], 5)
                stale = age_days is None or age_days > stale_limit
                await conn.execute(
                    """INSERT INTO market_factors (key, name, category, reading, reading_text, unit, source, source_url, as_of,
                           change_1d, change_5d, change_unit, trend, affected_holdings, threshold, threshold_text, breached,
                           breach_reason, stale, error, details, updated_at)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14::jsonb,$15::jsonb,$16,$17,$18,$19,NULL,$20::jsonb,now())
                       ON CONFLICT (key) DO UPDATE SET name=EXCLUDED.name, category=EXCLUDED.category, reading=EXCLUDED.reading,
                           reading_text=EXCLUDED.reading_text, unit=EXCLUDED.unit, source=EXCLUDED.source, source_url=EXCLUDED.source_url,
                           as_of=EXCLUDED.as_of, change_1d=EXCLUDED.change_1d, change_5d=EXCLUDED.change_5d, change_unit=EXCLUDED.change_unit,
                           trend=EXCLUDED.trend, affected_holdings=EXCLUDED.affected_holdings, threshold=EXCLUDED.threshold,
                           threshold_text=EXCLUDED.threshold_text, breached=EXCLUDED.breached, breach_reason=EXCLUDED.breach_reason,
                           stale=EXCLUDED.stale, error=NULL, details=EXCLUDED.details, updated_at=now()""",
                    f["key"], f["name"], f["category"], r.get("reading"), r.get("reading_text"), r.get("unit", f.get("unit")),
                    r.get("source"), r.get("source_url"), r.get("as_of"), r.get("change_1d"), r.get("change_5d"),
                    r.get("change_unit"), r.get("trend"), _j(f.get("affected", [])), _j(f.get("threshold", {})),
                    f.get("threshold_text"), breached, reason, stale, _j(r.get("details") or {}))
            ok.append(f["key"])
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("factor %s failed: %s", f["key"], exc)
            failed.append(f["key"])
            async with pool.acquire() as conn:
                await conn.execute(
                    """INSERT INTO market_factors (key, name, category, affected_holdings, threshold, threshold_text, stale, error, updated_at)
                       VALUES ($1,$2,$3,$4::jsonb,$5::jsonb,$6,TRUE,$7,now())
                       ON CONFLICT (key) DO UPDATE SET error=EXCLUDED.error, stale=TRUE, updated_at=now()""",
                    f["key"], f["name"], f["category"], _j(f.get("affected", [])), _j(f.get("threshold", {})),
                    f.get("threshold_text"), f"{type(exc).__name__}: {str(exc)[:300]}")
    return {"ok": ok, "failed": failed}


# ----------------------------------------------------------- read / render
def _row(r: Any) -> dict[str, Any]:
    d = dict(r)
    for k, v in list(d.items()):
        if isinstance(v, str) and k in ("metrics", "triggers", "costs", "affected_holdings", "threshold", "details"):
            try:
                d[k] = json.loads(v)
            except Exception:  # noqa: BLE001
                pass
        elif hasattr(v, "isoformat"):
            d[k] = v.isoformat()
        elif v.__class__.__name__ == "Decimal":
            d[k] = float(v)
    return d


async def get_investment_watchlist(pool: Any, include_dropped: bool = True) -> list[dict[str, Any]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM investment_watchlist " + ("" if include_dropped else "WHERE status <> 'dropped' ")
            + "ORDER BY CASE status WHEN 'ready' THEN 0 WHEN 'watching' THEN 1 ELSE 2 END, score DESC NULLS LAST, ticker")
    out = []
    for r in rows:
        d = _row(r)
        d["active_conditions"] = [m for _, m in _conditions({**d})]
        d["entry_zone_set"] = d.get("entry_low") is not None or d.get("entry_high") is not None
        out.append(d)
    return out


async def get_market_factors(pool: Any) -> list[dict[str, Any]]:
    order = {f["key"]: i for i, f in enumerate(FACTORS)}
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM market_factors")
    return sorted((_row(r) for r in rows), key=lambda d: order.get(d["key"], 99))


EDITABLE = {"name", "asset_type", "market", "sector", "currency", "thesis", "thesis_as_of", "entry_low", "entry_high",
            "target_price", "stop_price", "triggers", "costs", "score", "score_basis", "status", "status_note"}


async def upsert_watch_item(pool: Any, ticker: str, fields: dict[str, Any]) -> dict[str, Any]:
    fields = {k: v for k, v in fields.items() if k in EDITABLE}
    if "status" in fields and fields["status"] not in ("watching", "ready", "dropped"):
        raise ValueError("status must be watching/ready/dropped")
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO investment_watchlist (ticker) VALUES ($1) ON CONFLICT (ticker) DO NOTHING", ticker)
        for k, v in fields.items():
            if k in ("triggers", "costs"):
                await conn.execute(f"UPDATE investment_watchlist SET {k}=$2::jsonb, updated_at=now() WHERE ticker=$1", ticker, _j(v))
            elif k == "thesis_as_of":
                await conn.execute(f"UPDATE investment_watchlist SET {k}=$2, updated_at=now() WHERE ticker=$1", ticker,
                                   date.fromisoformat(v) if v else None)
            else:
                await conn.execute(f"UPDATE investment_watchlist SET {k}=$2, updated_at=now() WHERE ticker=$1", ticker, v)
        row = await conn.fetchrow("SELECT * FROM investment_watchlist WHERE ticker=$1", ticker)
    return _row(row)


def _fmt(v: Any, d: int = 2) -> str:
    try:
        return f"{float(v):,.{d}f}"
    except (TypeError, ValueError):
        return "n/a"


async def render_brief_sections(pool: Any) -> dict[str, str]:
    """Markdown blocks for the daily brief: opening factor alerts + watch-list summary."""
    factors = await get_market_factors(pool)
    items = await get_investment_watchlist(pool, include_dropped=False)
    moved = [f for f in factors if f.get("breached") and not f.get("stale")]
    lines = ["**Market factors past their alert thresholds**"]
    if moved:
        for f in moved:
            when = (f.get("as_of") or "")[:10]
            reading = f.get('reading_text') or f"{_fmt(f.get('reading'))} {f.get('unit') or ''}"
            lines.append(f"- ⚠️ {f['name']}: {reading} "
                         f"— {f.get('breach_reason')} (threshold {f.get('threshold_text')}; source {f.get('source')}, {when}). "
                         f"Affects: {', '.join(f.get('affected_holdings') or []) or 'n/a'}")
    else:
        lines.append("- None of the tracked factors crossed its threshold.")
    broken = [f["name"] for f in factors if f.get("error") or f.get("stale")]
    if broken:
        lines.append(f"- ℹ️ Unavailable/stale factor feeds: {', '.join(broken)}")
    opening = "\n".join(lines)

    wl = ["**Watch list**"]
    ready = [i for i in items if i["status"] == "ready"]
    flagged = [i for i in items if i["active_conditions"]]
    stale = [i["ticker"] for i in items if i.get("price_stale")]
    no_zone = [i["ticker"] for i in items if not i["entry_zone_set"]]
    wl.append(f"- {len(items)} active ideas ({len(ready)} ready). Prices: yfinance daily closes.")
    for i in ready:
        wl.append(f"- ✅ READY {i['ticker']} @ {_fmt(i.get('last_price'))} {i.get('currency')} (entry {i.get('entry_low') or '-'}–{i.get('entry_high') or '-'}, target {i.get('target_price') or '-'})")
    for i in flagged[:8]:
        wl.append(f"- 🔔 {'; '.join(i['active_conditions'])}")
    if stale:
        wl.append(f"- ⏳ Stale prices (>7 days): {', '.join(stale)}")
    if no_zone:
        wl.append(f"- Entry zones/targets not set yet for {len(no_zone)} ideas (Tho to define) — only technical triggers are live.")
    return {"opening": opening, "watchlist": "\n".join(wl)}


async def sync_legacy_watchlist(pool: Any) -> dict[str, Any]:
    """Overlay live macro LEVELS from market_factors onto data/watchlist.json.

    risk_scorer and older modules read numeric levels (Brent, gold, Fed/BoT rate,
    USD/THB) from the legacy file, which the paused nightly agent last wrote on
    2026-08-11. We update only those numbers (with source + as-of in
    _meta.live_levels); narrative fields and _meta.last_updated are left as-is so
    stale narrative flags are still recognised as stale. Atomic write.
    """
    if not LEGACY_WATCHLIST.exists():
        return {"skipped": "no legacy watchlist"}
    f = {r["key"]: r for r in await get_market_factors(pool)}
    data = json.loads(LEGACY_WATCHLIST.read_text(encoding="utf-8"))
    mc = data.setdefault("macro_context", {})
    wl = data.setdefault("watchlist", {})
    meta = data.setdefault("_meta", {})
    live: dict[str, Any] = {}

    def ok(k: str) -> Optional[dict[str, Any]]:
        r = f.get(k)
        return r if r and r.get("reading") is not None and not r.get("stale") and not r.get("error") else None

    highs: dict[str, Any] = {}
    try:
        yr = await asyncio.to_thread(download_closes, ["GC=F", "THB=X"], None, "1y", 3600)
        for t in ("GC=F", "THB=X"):
            s = yr[t].dropna()
            highs[t] = (round(float(s.max()), 3), s.idxmax().date().isoformat())
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("1y highs unavailable: %s", exc)
    if (r := ok("brent")):
        mc["brent_crude_usd"] = round(float(r["reading"]), 2)
        b = (wl.setdefault("commodities", {})).setdefault("BRENT", {"name": "Brent Crude"})
        b["last_price_usd"], b["date"] = round(float(r["reading"]), 2), r["as_of"][:10]
        live["brent_crude_usd"] = {"source": r["source"], "as_of": r["as_of"]}
    if (r := ok("gold")):
        mc["gold_current_usd"] = round(float(r["reading"]), 1)
        g = (wl.setdefault("commodities", {})).setdefault("XAU/USD", {"name": "Gold spot"})
        g["last_price_usd"], g["date"] = round(float(r["reading"]), 1), r["as_of"][:10]
        live["gold_current_usd"] = {"source": r["source"] + " (COMEX front month ~ spot)", "as_of": r["as_of"]}
        if "GC=F" in highs:
            mc["gold_recent_high_usd"] = highs["GC=F"][0]
            live["gold_recent_high_usd"] = {"source": "yfinance GC=F 1y max close", "as_of": highs["GC=F"][1]}
    if (r := ok("usdthb")):
        mc["usd_thb"] = round(float(r["reading"]), 3)
        meta["usd_thb_rate"], meta["usd_thb_as_of"] = round(float(r["reading"]), 3), r["as_of"][:10]
        c = (wl.setdefault("currencies", {})).setdefault("USD_THB", {"name": "USD/Thai Baht"})
        c["last_rate"], c["date"] = round(float(r["reading"]), 3), r["as_of"][:10]
        live["usd_thb"] = {"source": r["source"], "as_of": r["as_of"]}
        if "THB=X" in highs:
            mc["usd_thb_1yr_high"] = f"{highs['THB=X'][0]} ({highs['THB=X'][1]})"
            live["usd_thb_1yr_high"] = {"source": "yfinance THB=X 1y max close", "as_of": highs["THB=X"][1]}
    if (r := ok("fed_rate")):
        det = r.get("details") or {}
        if det.get("target_from") is not None and det.get("target_to") is not None:
            mid = (float(det["target_from"]) + float(det["target_to"])) / 2
            mc["us_fed_funds_rate_pct"] = round(mid, 3)
            live["us_fed_funds_rate_pct"] = {"source": r["source"] + " target-range midpoint", "as_of": r["as_of"]}
    if (r := ok("bot_rate")):
        mc["bot_policy_rate_pct"] = float(r["reading"])
        live["bot_policy_rate_pct"] = {"source": r["source"], "as_of": r["as_of"]}
    meta["live_levels"] = live
    meta["live_levels_updated_at"] = utcnow().isoformat()
    meta["live_levels_note"] = ("Numeric levels above are refreshed from investor_db.market_factors (free sources). "
                                "Narrative notes/flags are from the paused nightly agent (see last_updated).")
    tmp = LEGACY_WATCHLIST.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(LEGACY_WATCHLIST)
    return {"updated_fields": sorted(live)}


async def key_points(pool: Any, risk_summary: Optional[dict[str, Any]] = None) -> list[str]:
    """Deterministic statements the AI commentary must not contradict."""
    pts: list[str] = []
    for f in await get_market_factors(pool):
        if not f.get("breached") or f.get("stale"):
            continue
        c1 = f.get("change_1d")
        if f.get("category") in ("commodities", "fx", "equity", "rates") and c1 is not None:
            word = "ROSE" if float(c1) > 0 else "FELL"
            impacts = []
            for a in f.get("affected_holdings") or []:
                if "(+)" in a:
                    impacts.append(f"{'positive' if word == 'ROSE' else 'NEGATIVE'} for {a.replace('(+)', '').strip()}")
                elif "(-)" in a:
                    impacts.append(f"{'NEGATIVE' if word == 'ROSE' else 'positive'} for {a.replace('(-)', '').strip()}")
            pts.append(f"{f['name']} {word} ({f.get('breach_reason')})" + (f" - this is {', '.join(impacts)}" if impacts else ""))
        else:
            pts.append(f"{f['name']}: {f.get('breach_reason')}")
    rs = risk_summary or {}
    if rs.get("limit_breaches"):
        info = [b for b in rs["limit_breaches"] if "INFORMATIONAL" in b]
        act = [b for b in rs["limit_breaches"] if "INFORMATIONAL" not in b]
        if act:
            pts.append("Risk limits ARE exceeded: " + "; ".join(act))
        if info:
            pts.append("Concentration above the position cap (INFORMATIONAL ONLY - Tho has decided to keep these; do NOT suggest selling or trimming them): "
                       + "; ".join(b.replace(" (INFORMATIONAL - owner hold, no sell/trim suggested)", "") for b in info))
    elif rs:
        pts.append("No position/sector risk limits are exceeded.")
    if rs.get("provisional"):
        pts.append("Risk-engine figures are PROVISIONAL (holdings not yet confirmed by Tho).")
    fx = rs.get("fx") or {}
    if fx.get("portfolio_fx_beta") is not None:
        pts.append(f"FX risk: USD/THB {fx.get('usdthb')} (up = weaker baht). Portfolio FX beta {fx['portfolio_fx_beta']:+.2f}; "
                   f"a 10% stronger baht would cost about {abs(fx.get('thb_plus10_pnl_thb') or 0):,} THB (FX leg only, other prices unchanged).")
    return pts


def write_status(info: dict[str, Any]) -> None:
    try:
        current = json.loads(STATUS_FILE.read_text()) if STATUS_FILE.exists() else {}
    except Exception:  # noqa: BLE001
        current = {}
    current.update(info)
    tmp = STATUS_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(current, indent=2, default=str))
    tmp.replace(STATUS_FILE)


async def run_watchlist_cycle(pool: Any, *, prices: bool = True, factors: bool = True, alerts: bool = True) -> dict[str, Any]:
    await ensure_tables(pool)
    out: dict[str, Any] = {}
    if prices:
        out["seeded"] = await seed_investment_watchlist(pool)
        out["prices"] = await refresh_investment_prices(pool)
        write_status({"investment_watchlist_refreshed_at": utcnow().isoformat(), "investment_prices": out["prices"]})
    if factors:
        out["factors"] = await refresh_market_factors(pool)
        try:
            out["legacy_sync"] = await sync_legacy_watchlist(pool)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("legacy watchlist sync failed: %s", exc)
            out["legacy_sync"] = {"error": str(exc)}
        write_status({"market_factors_refreshed_at": utcnow().isoformat(), "market_factors": out["factors"]})
    if alerts:
        out["alerts"] = await evaluate_alerts(pool)
        write_status({"alerts_evaluated_at": utcnow().isoformat(), "alerts": {k: v for k, v in out["alerts"].items() if k != "active_conditions"}})
    return out
