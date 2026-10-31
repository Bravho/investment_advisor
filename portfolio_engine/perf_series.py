"""Time-weighted daily performance series for the 'ผลตอบแทนพอร์ต' chart (2026-10-31).

Why: the old chart compared the first and last recorded *total value* (portfolio_performance). Those totals
jump on every purchase/new holding and on days a holding was unpriced, so new money (the 300k ThaiESG
entries on 30 Oct) and SCBGOLDE's missing NAV (15-29 Oct) were counted as gains/losses (63.8% / MDD -20.7%),
daily_pnl_pct was always 0 (Sharpe 0) and benchmarks read tickers absent from market_prices (flat 0%).

Method (flow-neutral = time-weighted):
  * units per holding come from each daily snapshot (market_value / price). A holding whose price errored that
    day keeps the units of the last priced snapshot (flagged 'carried'). Unit changes are cash flows, never returns.
  * daily return r_t = sum(units_{t-1} x price_t) / sum(units_{t-1} x price_{t-1}) - 1, with units held at the close
    of the previous trading day (latest snapshot on/before it). Stocks: yfinance auto-adjusted closes
    (dividends reinvested); funds: official NAV history (fund_nav_daily, Finnomena) - weights use raw values.
  * pending purchases (is_modelled snapshot rows: ThaiESG buys effective 2026-11-02, units unconfirmed) are
    excluded until their effective date - they are contributions, not performance.
  * days between snapshots are reconstructed from prices with the previous snapshot's units (labelled); if the last
    snapshot is more than MAX_GAP_DAYS old the chain breaks (portfolio unknown), so a window never spans the
    16 Jul - 6 Oct gap (the June-July book held BAFS and an unpriced gold fund).
Benchmarks: SET -> TDEX.BK (SET50 ETF, total-return proxy; ^SET.BI/^SET.BK have no usable Yahoo history),
S&P 500 -> ^GSPC (USD, price index). Both rebased to the portfolio window start.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
from datetime import date, timedelta
from typing import Any, Optional

import numpy as np
import pandas as pd

LOGGER = logging.getLogger("portfolio_engine.perf_series")
MAX_GAP_DAYS = 5
MIN_RETURNS_SHARPE = 20
MIN_POINTS_MDD = 5
SET_BENCH, SP_BENCH = "TDEX.BK", "^GSPC"
# pending contributions: ThaiESG buys placed 30 Oct, effective (NAV date) 2026-11-02 per the snapshot lock_until (5y)
DEFAULT_EFFECTIVE = "2026-11-02"


def _effective_date(h: dict[str, Any]) -> Optional[date]:
    lu = h.get("lock_until")
    if lu:
        try:
            d = date.fromisoformat(str(lu)[:10])
            return date(d.year - 5, d.month, d.day)
        except ValueError:
            pass
    return date.fromisoformat(DEFAULT_EFFECTIVE)


async def _snapshots(pool: Any) -> list[dict[str, Any]]:
    rows = await pool.fetch("SELECT record_date, snapshot FROM portfolio_performance WHERE snapshot IS NOT NULL ORDER BY record_date")
    out, prev_units = [], {}
    for r in rows:
        snap = r["snapshot"]
        snap = json.loads(snap) if isinstance(snap, str) else (snap or {})
        hold = snap.get("holdings") or {}
        d = r["record_date"]
        units, raw, flags = {}, {}, {}
        for t, h in hold.items():
            if not isinstance(h, dict):
                continue
            if h.get("is_modelled"):
                eff = _effective_date(h)
                if eff and d < eff:
                    flags[t] = f"pending contribution (effective {eff})"
                    continue
                flags[t] = "modelled value (units unconfirmed)"
            mv, px = h.get("market_value_thb"), h.get("current_price")
            if mv and px and float(px) > 0:
                units[t] = float(mv) / float(px)
                raw[t] = float(px)
            elif t in prev_units:
                units[t] = prev_units[t]
                flags[t] = "unpriced in snapshot - units carried from previous snapshot"
            else:
                flags[t] = "unpriced, no earlier units - excluded"
        prev_units = units
        out.append({"date": d, "units": units, "flags": flags})
    return out


async def _fund_navs(pool: Any, codes: list[str], start: date) -> pd.DataFrame:
    if not codes:
        return pd.DataFrame()
    rows = await pool.fetch("SELECT code, nav_date, nav FROM fund_nav_daily WHERE code = ANY($1::text[]) AND nav_date >= $2 ORDER BY nav_date",
                            codes, start)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame([(r["code"], pd.Timestamp(r["nav_date"]), float(r["nav"])) for r in rows], columns=["code", "d", "nav"])
    return df.pivot_table(index="d", columns="code", values="nav")


async def _raw_closes(pool: Any, tickers: list[str], start: date) -> pd.DataFrame:
    if not tickers:
        return pd.DataFrame()
    rows = await pool.fetch("SELECT ticker, price_date, close_price FROM market_prices WHERE ticker = ANY($1::text[]) AND price_date >= $2",
                            tickers, start)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame([(r["ticker"], pd.Timestamp(r["price_date"]), float(r["close_price"])) for r in rows], columns=["t", "d", "c"])
    return df.pivot_table(index="d", columns="t", values="c")


def _adj_closes(tickers: list[str], start: date) -> tuple[pd.DataFrame, Optional[str]]:
    try:
        from market_history import download_closes
        df = download_closes(tickers, start=str(start), ttl=1800)
        return df.reindex(columns=tickers), None
    except Exception as exc:  # noqa: BLE001
        return pd.DataFrame(), f"{type(exc).__name__}: {exc}"


def _stats(r: pd.Series, curve: pd.Series, rf_annual: Optional[float]) -> dict[str, Any]:
    n = int(len(r))
    out: dict[str, Any] = {"n_returns": n}
    out["return_pct"] = round(float(curve.iloc[-1] - 1) * 100, 2) if len(curve) else None
    if n >= MIN_RETURNS_SHARPE:
        rf_d = (rf_annual or 0.0) / 252
        sd = float(r.std(ddof=1))
        out["sharpe"] = round(float((r.mean() - rf_d) / sd * math.sqrt(252)), 2) if sd > 0 else None
        out["vol_pct"] = round(sd * math.sqrt(252) * 100, 2)
        out["sharpe_note"] = None if sd > 0 else "volatility 0"
    else:
        out["sharpe"] = None
        out["vol_pct"] = None
        out["sharpe_note"] = f"ต้องมีผลตอบแทนรายวันอย่างน้อย {MIN_RETURNS_SHARPE} วัน (มี {n})"
    if len(curve) >= MIN_POINTS_MDD:
        out["max_drawdown_pct"] = round(float((curve / curve.cummax() - 1).min()) * 100, 2)
        out["mdd_note"] = None
    else:
        out["max_drawdown_pct"] = None
        out["mdd_note"] = f"ต้องมีอย่างน้อย {MIN_POINTS_MDD} จุดข้อมูล (มี {len(curve)})"
    out["win_rate"] = round(float((r > 0).mean()), 4) if n else None
    out["best_day_pct"] = round(float(r.max()) * 100, 2) if n else None
    out["worst_day_pct"] = round(float(r.min()) * 100, 2) if n else None
    return out


async def build(pool: Any, days: int) -> dict[str, Any]:
    today = date.today()
    want_start = today - timedelta(days=days)
    snaps = await _snapshots(pool)
    if not snaps:
        return {"error": "no portfolio snapshots", "series": []}
    fetch_from = want_start - timedelta(days=15)
    tickers = sorted({t for s in snaps if s["date"] >= fetch_from for t in s["units"]})
    navs = await _fund_navs(pool, tickers, fetch_from)
    fund_codes = [t for t in tickers if t in navs.columns]
    stock = [t for t in tickers if t not in fund_codes]
    raw = await _raw_closes(pool, stock, fetch_from)
    adj, adj_err = await asyncio.to_thread(_adj_closes, sorted(set(stock + [SET_BENCH, SP_BENCH])), fetch_from)
    no_price = [t for t in tickers if t not in fund_codes and (raw.empty or t not in raw.columns) and (adj.empty or t not in adj.columns or adj[t].dropna().empty)]

    idx = sorted(set((raw.index.tolist() if not raw.empty else []) + (navs.index.tolist() if not navs.empty else [])
                     + (adj[[c for c in stock if c in adj.columns]].dropna(how="all").index.tolist() if not adj.empty and stock else [])))
    idx = [d for d in idx if d.date() <= today]
    cols = stock + fund_codes
    rawp = pd.DataFrame(index=pd.DatetimeIndex(idx), columns=cols, dtype=float)
    retp = pd.DataFrame(index=pd.DatetimeIndex(idx), columns=cols, dtype=float)
    for t in stock:
        if not raw.empty and t in raw.columns:
            rawp[t] = raw[t].reindex(rawp.index)
        if not adj.empty and t in adj.columns:
            retp[t] = adj[t].reindex(rawp.index)
        if retp[t].isna().all():
            retp[t] = rawp[t]
        if rawp[t].isna().all():
            rawp[t] = retp[t]
    for t in fund_codes:
        rawp[t] = navs[t].reindex(rawp.index)
        retp[t] = rawp[t]
    rawp, retp = rawp.ffill(), retp.ffill()

    def units_at(d: date) -> tuple[Optional[dict[str, float]], Optional[date]]:
        cand = [s for s in snaps if s["date"] <= d]
        if not cand:
            return None, None
        s = cand[-1]
        if (d - s["date"]).days > MAX_GAP_DAYS:
            return None, s["date"]
        return s["units"], s["date"]

    dates = [d for d in rawp.index if d.date() >= want_start - timedelta(days=7)]
    rets, reconstructed, breaks = {}, {}, []
    for i in range(1, len(dates)):
        d0, d1 = dates[i - 1], dates[i]
        u, sd = units_at(d0.date())
        if u is None:
            breaks.append(str(d1.date()))
            rets[d1] = None
            continue
        num = den = 0.0
        for t, q in u.items():
            if t not in rawp.columns:
                continue
            p0r, a0, a1 = rawp.at[d0, t], retp.at[d0, t], retp.at[d1, t]
            if any(pd.isna(x) for x in (p0r, a0, a1)) or a0 <= 0:
                continue
            w = q * p0r
            den += w
            num += w * (a1 / a0 - 1)
        rets[d1] = (num / den) if den > 0 else None
        reconstructed[d1] = not any(s["date"] == d0.date() for s in snaps)
    # window: start at the first date >= want_start after the last break inside the window
    # anchor at the last close on/before the requested start (so 1D = last trading day's move)
    before = [d for d in dates if d.date() <= want_start]
    win = ([before[-1]] if before else []) + [d for d in dates if d.date() > want_start]
    if len(win) == 1 and len(before) >= 2:  # e.g. 1D on a weekend: last session vs the one before
        win = before[-2:]
    if win:
        last_break = max([i for i, d in enumerate(win) if rets.get(d) is None and i > 0] or [-1])
        if last_break >= 0:
            win = win[last_break:]
    while len(win) > 1 and rets.get(win[1]) is None:
        win = win[1:]
    if not win:
        return {"error": "no priced dates in window", "series": []}
    start = win[0]
    r = pd.Series({d: rets[d] for d in win[1:] if rets.get(d) is not None}, dtype=float)
    curve = pd.concat([pd.Series({start: 1.0}), (1 + r).cumprod()]) if len(r) else pd.Series({start: 1.0})

    bench_out, bench_curve, bench_err = {}, {}, {}
    for key, tk in (("SET", SET_BENCH), ("SP500", SP_BENCH)):
        if adj.empty or tk not in adj.columns or adj[tk].dropna().empty:
            bench_err[key] = adj_err or f"{tk} unavailable"
            continue
        s = adj[tk].dropna()
        s = s[s.index <= curve.index[-1]]
        base = s[s.index <= start]
        if base.empty:
            bench_err[key] = f"{tk}: no price on/before {start.date()}"
            continue
        aligned = s.reindex(curve.index.union(s.index)).ffill().reindex(curve.index)
        bc = aligned / float(base.iloc[-1])
        bench_curve[key] = bc
        bench_out[key] = {"ticker": tk, **_stats(bc.pct_change().dropna(), bc, None)}

    bot = await pool.fetchval("SELECT reading FROM market_factors WHERE key='bot_rate'")
    rf = float(bot) / 100 if bot is not None else None
    stats = _stats(r, curve, rf)
    series = []
    for d in curve.index:
        row = {"date": str(d.date()), "portfolio": round(float(curve[d] - 1) * 100, 3),
               "reconstructed": bool(reconstructed.get(d, False))}
        for k, bc in bench_curve.items():
            v = bc.get(d)
            row[k] = None if v is None or pd.isna(v) else round(float(v - 1) * 100, 3)
        series.append(row)
    last_snap = [s for s in snaps if s["date"] <= curve.index[-1].date()][-1]
    pending = {t: f for t, f in last_snap["flags"].items() if f.startswith("pending")}
    carried = sorted({t for s in snaps if win[0].date() <= s["date"] <= win[-1].date() for t, f in s["flags"].items() if "carried" in f})
    notes = []
    if start.date() > want_start + timedelta(days=3):
        notes.append(f"ไม่มีข้อมูลพอร์ตต่อเนื่องก่อน {start.date()} (ช่องว่างของ snapshot) — กราฟเริ่มที่ {start.date()} แทน {want_start}")
    if pending:
        notes.append("ไม่นับเงินซื้อใหม่ที่ยังไม่มีผล: " + ", ".join(f"{t} ({f.split('effective ')[-1].rstrip(')')})" for t, f in pending.items()) + " — เป็นเงินลงทุนเพิ่ม ไม่ใช่กำไร")
    if carried:
        notes.append("วันที่ snapshot ไม่มีราคา " + ", ".join(carried) + " ใช้จำนวนหน่วยเดิม × NAV ทางการรายวัน")
    if no_price:
        notes.append("ไม่มีราคารายวัน (ไม่รวมในผลตอบแทน): " + ", ".join(no_price))
    if sum(1 for d in curve.index if reconstructed.get(d)) :
        notes.append("บางวันไม่มี snapshot — คำนวณจากราคารายวัน × หน่วยจาก snapshot ก่อนหน้า (reconstructed)")
    provisional = ("ตัวเลขเบื้องต้น (provisional): ต้นทุนและจำนวนหน่วย SCBGOLDE ยังไม่ยืนยัน และจำนวนหน่วย ThaiESG ที่ซื้อ (มีผล 2 พ.ย. 2569) ยังไม่ทราบ"
                   " — เมื่อยืนยันแล้วผลตอบแทนอาจเปลี่ยน")
    return {
        "method": "time-weighted (flow-neutral): daily return = Σ units(t−1)×price(t) / Σ units(t−1)×price(t−1) − 1; purchases/new holdings are cash flows",
        "window": {"requested_start": str(want_start), "start": str(start.date()), "end": str(curve.index[-1].date()), "points": len(curve)},
        "portfolio": stats, "benchmarks": bench_out, "benchmark_errors": bench_err,
        "benchmark_labels": {"SET": "SET (proxy: TDEX.BK SET50 ETF, total return, THB)", "SP500": "S&P 500 (^GSPC, price index, USD)"},
        "risk_free": {"annual_pct": rf * 100 if rf is not None else None, "source": "BoT policy rate (market_factors.bot_rate)" if rf is not None else "unknown - Sharpe uses rf = 0"},
        "series": series, "pending_contributions": pending, "notes": notes, "provisional_note_th": provisional,
        "breaks": breaks[-5:],
    }
