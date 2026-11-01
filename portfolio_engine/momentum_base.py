"""Momentum + base swing/position setup ("momentum_base_swing") - added 2026-10-30.

Adapted (not copied) from Tho's Thai trading lesson parts 1-3 (docs/lessons/momentum_base_setup.md).
Tho is a swing/position investor, NOT a day trader, so every intraday element of the lesson was dropped:

  1. Strong-stock screen   relative strength = weighted percentile of 1/3/6-month returns inside each market
                           (SET vs US separately); top 30% AND a minimum 3m-or-6m return; liquidity filter on
                           20-day average traded value. Weekly chart first (weekly close > EMA10w > EMA30w,
                           EMA10w rising, weekly higher lows), then daily.
  2. Base (VCP-like)       daily higher lows, volatility contraction (ATR10/ATR50, 10d vs 30d range),
                           price back above EMA9 and EMA21 with EMA21 flat or rising.
  3. Breakout + 1st retest close above the prior 50-session pivot high, then the FIRST pullback into support
                           confluence (EMA9/21/50, anchored VWAPs, prior pivots, unfilled gaps, the breakout level).
  4. Daily trigger         break of the prior day's high after that pullback (buy-stop variant) or a close above
                           it (close-confirm variant, enter next open). No intraday data used.
  5. Stop, then size       stop = min(pullback low, signal-bar low) - k x ATR14 (room for normal volatility);
                           size = risk budget / (per-share risk + typical bad overnight gap), then the 25% stock /
                           40% sector caps from risk_limits.json.
  6. Exit                  half at +3R (configurable), stop to breakeven, trail the rest on a daily close below
                           EMA21 / EMA50 / weekly close below EMA10w; time stop 252 sessions. Gaps through the stop
                           exit at the open (gap risk is real and is in the backtest).

NOTHING here places orders. Output = screen rows, levels, and PROPOSED trade plans that Tho may approve or reject;
approval only copies levels to the watch list for alerts. Tho executes every trade himself.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from market_history import SET_PROXY, download_ohlc

LOGGER = logging.getLogger("portfolio_engine.momentum_base")
ICT = ZoneInfo("Asia/Bangkok")
SETUP = "momentum_base_swing"
CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "setups.json"

# Screen universe. Survivorship bias: these are TODAY's liquid names (stated in every backtest result).
THAI = ["ADVANC", "AOT", "BBL", "BDMS", "BEM", "BH", "BJC", "BTS", "CBG", "CENTEL", "CPALL", "CPF", "CPN", "CRC",
        "DELTA", "EA", "EGCO", "GPSC", "GULF", "HMPRO", "IVL", "KBANK", "KCE", "KTB", "KTC", "LH", "MINT", "MTC", "OR",
        "OSP", "PTT", "PTTEP", "PTTGC", "RATCH", "SAWAD", "SCB", "SCC", "SCGP", "TISCO", "TOP", "TRUE", "TTB", "TU",
        "WHA", "BANPU", "BAFS", "IRPC", "BCP", "HANA", "SPRC", "GLOBAL", "COM7", "CK", "STGT", "BCH", "AWC", "AMATA",
        "TIDLOR", "JMT", "PLANB"]
THAI = [f"{t}.BK" for t in THAI]
US = ["SPY", "QQQ", "NVDA", "MSFT", "GOOGL", "TSM", "AVGO", "MU", "AAPL", "AMZN", "META", "TSLA", "AMD", "NFLX", "ORCL",
      "LLY", "JPM", "V", "MA", "COST", "UNH", "XOM", "WMT", "HD", "CAT", "GE", "AMAT", "LRCX", "KLAC", "ASML", "ANET",
      "CRWD", "PANW", "NOW", "UBER", "SHOP", "PLTR", "VRT", "CEG", "ETN", "INTU", "ADBE", "CRM", "QCOM", "TXN", "ISRG",
      "BKNG", "GS", "MS", "AMPX", "VNM", "EWJ", "INDA", "FXI", "GLDM", "GDX"]
# Same names as walkforward.UNIVERSES, for an apples-to-apples comparison with the existing signal backtests.
CORE = {"thai": ["KBANK.BK", "BBL.BK", "KTB.BK", "TTB.BK", "SCB.BK", "PTT.BK", "PTTEP.BK", "TOP.BK", "IRPC.BK", "AOT.BK",
                 "BAFS.BK", "ADVANC.BK"],
        "global": ["SPY", "QQQ", "NVDA", "MSFT", "GOOGL", "TSM", "AVGO", "MU", "VNM", "EWJ", "INDA", "FXI", "GLDM", "IAU", "GDX"]}

DDL = """
CREATE TABLE IF NOT EXISTS setup_screens (
    id         SERIAL PRIMARY KEY,
    as_of      DATE NOT NULL,
    setup      VARCHAR(40) NOT NULL,
    ticker     VARCHAR(30) NOT NULL,
    market     VARCHAR(4),
    state      VARCHAR(30),
    passed     BOOLEAN,
    rs_pct     NUMERIC(6,2),
    score      NUMERIC(6,2),
    data       JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (as_of, setup, ticker)
);
CREATE TABLE IF NOT EXISTS setup_backtests (
    id       SERIAL PRIMARY KEY,
    run_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    setup    VARCHAR(40) NOT NULL,
    results  JSONB NOT NULL DEFAULT '{}'::jsonb
);
"""
_ALTERED = False


async def ensure_tables(pool: Any) -> None:
    """Additive, local-only schema: two new tables + one nullable trade_plans.setup column (run once per process)."""
    global _ALTERED
    import trade_plans as tp
    await tp.ensure_tables(pool)
    async with pool.acquire() as conn:
        await conn.execute(DDL)
        if not _ALTERED:
            await conn.execute("ALTER TABLE trade_plans ADD COLUMN IF NOT EXISTS setup VARCHAR(40)")
            _ALTERED = True


def load_cfg() -> dict[str, Any]:
    try:
        return json.loads(CONFIG_PATH.read_text())[SETUP]
    except Exception:  # noqa: BLE001
        LOGGER.warning("config/setups.json unreadable - using built-in defaults")
        return {"screen": {"rs_weights": {"ret_1m": .2, "ret_3m": .4, "ret_6m": .4}, "min_rs_percentile": 70,
                           "min_return": {"TH": .2, "US": .3}, "min_avg_traded_value": {"TH": 5e7, "US": 2e7},
                           "min_price": {"TH": 1, "US": 5}},
                "base": {"lookback": 60, "max_atr_ratio": 1.0, "ema21_min_slope_5d": -0.002},
                "breakout": {"pivot_lookback": 50, "max_age_sessions": 25},
                "trigger": {"max_sessions_after_pullback": 5, "pullback_atr_band": 0.5},
                "stop": {"atr_buffer": 1.0, "max_risk_pct_of_price": 0.10},
                "exit": {"rule": "ema21", "partial_at_r": 3.0, "partial_fraction": 0.5, "max_hold_sessions": 252},
                "gap": {"quantile": 0.05, "lookback": 252}, "plan_expiry_days": 14, "risk_pct": None}


def market_of(t: str) -> str:
    return "TH" if t.endswith(".BK") else "US"


def thai_tick(p: float) -> float:
    for lim, tk in ((2, .01), (5, .02), (10, .05), (25, .10), (100, .25), (200, .50), (400, 1.0)):
        if p < lim:
            return tk
    return 2.0


def tick_of(t: str, p: float) -> float:
    return thai_tick(p) if t.endswith(".BK") else 0.01


def side_cost(t: str) -> float:
    from trade_plans import COMMISSION_TH, VAT, SLIPPAGE, US_COMMISSION, FX_SPREAD
    return COMMISSION_TH * (1 + VAT) + SLIPPAGE if t.endswith(".BK") else US_COMMISSION + FX_SPREAD + SLIPPAGE


# ------------------------------------------------------------------ indicators (all causal: row t uses data <= t)
def indicators(df: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    d = df[["Open", "High", "Low", "Close", "Volume"]].astype(float).copy()
    d = d[d["Close"] > 0].dropna(subset=["Open", "High", "Low", "Close"])
    c, h, l = d["Close"], d["High"], d["Low"]
    for n in (9, 21, 50):
        d[f"ema{n}"] = c.ewm(span=n, adjust=False).mean()
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    d["atr14"] = tr.ewm(alpha=1 / 14, adjust=False).mean()
    d["atr_ratio"] = tr.rolling(10).mean() / tr.rolling(50).mean()
    d["range_ratio"] = ((h.rolling(10).max() - l.rolling(10).min()) / (h.rolling(30).max() - l.rolling(30).min()))
    for k, n in (("ret_1m", 21), ("ret_3m", 63), ("ret_6m", 126)):
        d[k] = c / c.shift(n) - 1
    d["adv20"] = (c * d["Volume"].fillna(0)).rolling(20).mean()
    d["ema21_slope5"] = d["ema21"] / d["ema21"].shift(5) - 1
    d["ema9_slope3"] = d["ema9"] / d["ema9"].shift(3) - 1
    d["higher_lows"] = l.rolling(10).min() > l.shift(10).rolling(20).min()
    b = cfg["base"]
    d["base_ok"] = (d["higher_lows"] & (c > d["ema9"]) & (c > d["ema21"]) & (d["ema21_slope5"] >= b["ema21_min_slope_5d"])
                    & ((d["atr_ratio"] <= b["max_atr_ratio"]) | (d["range_ratio"] <= 0.6)))
    # base quality 0-100 (for ranking/display only)
    q = pd.concat([d["higher_lows"].astype(float), (c > d["ema9"]).astype(float), (c > d["ema21"]).astype(float),
                   (d["ema21_slope5"] >= 0).astype(float), (1.2 - d["atr_ratio"].clip(0.6, 1.2)) / 0.6,
                   (1 - d["range_ratio"].clip(0, 1))], axis=1)
    d["base_score"] = q.mean(axis=1) * 100
    # weekly chart first: completed weekly bars mapped back to daily rows (no look-ahead)
    w = pd.DataFrame({"c": c.resample("W-FRI").last(), "l": l.resample("W-FRI").min()}).dropna()
    w["e10"] = w["c"].ewm(span=10, adjust=False).mean()
    w["e30"] = w["c"].ewm(span=30, adjust=False).mean()
    w["hl"] = w["l"].rolling(4).min() > w["l"].shift(4).rolling(8).min()
    w["ok"] = (w["c"] > w["e10"]) & (w["e10"] > w["e30"]) & (w["e10"] >= w["e10"].shift(2)) & w["hl"]
    w["close_below_e10"] = w["c"] < w["e10"]
    wk = w.reindex(d.index, method="ffill")
    # a daily row on a Friday may only see the weekly bar that closes that day (fine); midweek rows see last Friday
    d["w_ok"] = wk["ok"].astype(float).fillna(0).astype(bool)
    d["w_ema10"] = wk["e10"]
    d["w_below_e10"] = wk["close_below_e10"].astype(float).fillna(0).astype(bool)
    pl = cfg["breakout"]["pivot_lookback"]
    d["pivot_high"] = h.shift(1).rolling(pl).max()
    d["breakout"] = c > d["pivot_high"]
    g = d["Open"] / c.shift() - 1
    d["gap_q"] = g.rolling(cfg["gap"]["lookback"], min_periods=60).quantile(cfg["gap"]["quantile"]).clip(upper=0).abs()
    return d


def rs_percentiles(frames: dict[str, pd.DataFrame], cfg: dict[str, Any]) -> dict[str, pd.Series]:
    """Per-date cross-sectional RS percentile (0-100) inside each market."""
    wts = cfg["screen"]["rs_weights"]
    out: dict[str, pd.Series] = {}
    for mkt in ("TH", "US"):
        names = [t for t in frames if market_of(t) == mkt]
        if len(names) < 5:
            continue
        comp = None
        for k, wv in wts.items():
            m = pd.DataFrame({t: frames[t][k] for t in names})
            r = m.rank(axis=1, pct=True) * wv
            comp = r if comp is None else comp.add(r, fill_value=0)
        valid = pd.DataFrame({t: frames[t]["ret_6m"] for t in names}).notna()
        pct = comp.where(valid).rank(axis=1, pct=True) * 100
        for t in names:
            out[t] = pct[t]
    return out


def screen_mask(t: str, d: pd.DataFrame, rs: pd.Series, cfg: dict[str, Any]) -> pd.Series:
    s, mkt = cfg["screen"], market_of(t)
    rs = rs.reindex(d.index)
    ret_ok = d[["ret_3m", "ret_6m"]].max(axis=1) >= s["min_return"][mkt]
    return ((rs >= s["min_rs_percentile"]) & ret_ok & (d["adv20"] >= s["min_avg_traded_value"][mkt])
            & (d["Close"] >= s["min_price"][mkt])).fillna(False)


# ------------------------------------------------------------------ support confluence (live levels)
def _avwap(d: pd.DataFrame, start: pd.Timestamp) -> Optional[float]:
    seg = d.loc[start:]
    v = seg["Volume"].fillna(0)
    if v.sum() <= 0:
        return None
    tp = (seg["High"] + seg["Low"] + seg["Close"]) / 3
    return float((tp * v).sum() / v.sum())


def _pivots(s: pd.Series, w: int, kind: str) -> list[tuple[pd.Timestamp, float]]:
    out = []
    for i in range(w, len(s) - w):
        seg = s.iloc[i - w:i + w + 1]
        v = s.iloc[i]
        if (kind == "high" and v == seg.max()) or (kind == "low" and v == seg.min()):
            out.append((s.index[i], float(v)))
    return out


def confluence_levels(d: pd.DataFrame, breakout_date: Optional[pd.Timestamp]) -> dict[str, Any]:
    last = d.iloc[-1]
    price, a = float(last["Close"]), float(last["atr14"])
    lv: list[dict[str, Any]] = []

    def add(v: Optional[float], label: str, kind: str) -> None:
        if v is not None and np.isfinite(v) and v < price * 1.001 and v > price - 4 * a:
            lv.append({"level": round(float(v), 4), "label": label, "kind": kind})

    for n in (9, 21, 50):
        add(float(last[f"ema{n}"]), f"EMA{n} daily", "ema")
    add(float(last["w_ema10"]) if pd.notna(last["w_ema10"]) else None, "EMA10 weekly (~EMA50 daily)", "ema")
    yr = d.iloc[-252:]
    if breakout_date is not None:
        add(_avwap(d, breakout_date), f"AVWAP from breakout {breakout_date.date()}", "avwap")
        add(float(d.loc[breakout_date, "pivot_high"]), f"breakout level (prior 50d high) {breakout_date.date()}", "pivot")
    lo_date = yr["Low"].iloc[-126:].idxmin()
    add(_avwap(d, lo_date), f"AVWAP from 6m swing low {lo_date.date()}", "avwap")
    for dt, v in _pivots(yr["High"], 5, "high")[-8:]:
        add(v, f"prior swing high {dt.date()} (old resistance)", "pivot")
    for dt, v in _pivots(yr["Low"].iloc[-80:], 3, "low")[-4:]:
        add(v, f"swing low {dt.date()}", "pivot")
    seg = d.iloc[-120:]
    for i in range(1, len(seg)):
        prev_h, lo = float(seg["High"].iloc[i - 1]), float(seg["Low"].iloc[i])
        if lo > prev_h:  # gap up
            after = seg["Low"].iloc[i + 1:]
            if after.empty or float(after.min()) > prev_h:
                add(prev_h, f"unfilled gap {seg.index[i].date()} (bottom)", "gap")
    lv.sort(key=lambda x: -x["level"])
    clusters: list[list[dict[str, Any]]] = []
    for x in lv:
        if clusters and clusters[-1][0]["level"] - x["level"] <= 0.5 * a:
            clusters[-1].append(x)
        else:
            clusters.append([x])
    zone = None
    for cl in clusters:  # nearest cluster below price with >=2 independent kinds of evidence, within 3 ATR
        kinds = {x["kind"] for x in cl}
        if len(cl) >= 2 and len(kinds) >= 2 and price - cl[-1]["level"] <= 3 * a:
            zone = cl
            break
    if zone is None:
        zone = next((cl for cl in clusters if len(cl) >= 2 and price - cl[-1]["level"] <= 3 * a), None)
    zinfo = None
    if zone:
        hi, lo = zone[0]["level"], zone[-1]["level"]
        if hi - lo < 0.2 * a:
            mid = (hi + lo) / 2
            hi, lo = mid + 0.1 * a, mid - 0.1 * a
        zinfo = {"low": round(lo, 4), "high": round(hi, 4), "members": [x["label"] for x in zone], "strength": len(zone)}
    return {"price": price, "atr14": a, "levels": lv, "zone": zinfo}


# ------------------------------------------------------------------ event generation (backtest + live state)
def find_entries(t: str, d: pd.DataFrame, scr: pd.Series, cfg: dict[str, Any], trigger: str, atr_k: float,
                 require_base: bool = True, require_retest: bool = True, final: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
    """Walk the daily bars and emit entries. Signals at bar t use data <= t only.
    trigger='stop': buy-stop 1 tick above the prior day's high, filled on day t at max(open, stop) if high >= stop.
    trigger='close': close(t) > high(t-1) -> buy next open."""
    bo_cfg, tr_cfg, st_cfg = cfg["breakout"], cfg["trigger"], cfg["stop"]
    n = len(d)
    O, H, L, C = (d[k].values for k in ("Open", "High", "Low", "Close"))
    e9, e21, e50, A = d["ema9"].values, d["ema21"].values, d["ema50"].values, d["atr14"].values
    piv, bo = d["pivot_high"].values, d["breakout"].values
    base, wok, sc = d["base_ok"].values, d["w_ok"].values, scr.reindex(d.index).astype(float).fillna(0).astype(bool).values
    entries: list[dict[str, Any]] = []
    state, bo_i, bo_lvl, pb_i, pb_low, used_retest = "idle", -1, 0.0, -1, 0.0, False
    i = 60
    while i < n:
        if state == "idle":
            pre_ok = (base[i - 1] or not require_base)
            if bo[i] and sc[i] and wok[i] and pre_ok and np.isfinite(A[i]):
                state, bo_i, bo_lvl, used_retest = "broken_out", i, float(piv[i]), False
                if not require_retest:
                    state, pb_i, pb_low = "pullback", i, float(L[i])
            i += 1
            continue
        if i - bo_i > bo_cfg["max_age_sessions"] or C[i] < e50[i] or C[i] < bo_lvl - 1.5 * A[i]:
            state = "idle"
            i += 1
            continue
        if state == "broken_out":
            band = tr_cfg["pullback_atr_band"] * A[i]
            touched = L[i] <= max(e21[i], bo_lvl) + band or L[i] <= e9[i]
            if touched and not used_retest and i > bo_i:
                state, pb_i, pb_low, used_retest = "pullback", i, float(L[i]), True
            i += 1
            continue
        if state == "pullback":
            pb_low = min(pb_low, float(L[i - 1]))
            if i - pb_i > tr_cfg["max_sessions_after_pullback"]:
                state = "idle"  # first retest failed to trigger -> setup void (no second retest)
                i += 1
                continue
            stop_px = H[i - 1] + tick_of(t, H[i - 1])
            fill, fill_i = None, None
            if trigger == "stop" and H[i] >= stop_px:
                fill, fill_i = max(O[i], stop_px), i
                sig_low = min(L[i - 1], pb_low)
            elif trigger == "close" and C[i] > H[i - 1]:
                if i + 1 >= n:  # triggered on the last bar: entry would be the next open (live only)
                    state = "close_triggered_last_bar"
                    break
                fill, fill_i = O[i + 1], i + 1
                sig_low = min(L[i], pb_low)
            if fill is not None:
                stop = sig_low - atr_k * A[i - 1 if trigger == "stop" else i]
                risk = fill - stop
                if risk > 0 and risk / fill <= st_cfg["max_risk_pct_of_price"]:
                    entries.append({"ticker": t, "i": fill_i, "date": d.index[fill_i], "entry": float(fill), "stop": float(stop),
                                    "risk": float(risk), "breakout_date": d.index[bo_i], "breakout_level": bo_lvl,
                                    "gap_q": float(d["gap_q"].iloc[fill_i]) if pd.notna(d["gap_q"].iloc[fill_i]) else 0.02})
                state = "idle"
                i = fill_i + 1
                continue
        i += 1
    if final is not None:
        final.update(state=state, bo_i=bo_i, bo_level=bo_lvl, pb_i=pb_i, pb_low=pb_low)
    return entries


def run_exit(t: str, d: pd.DataFrame, e: dict[str, Any], rule: str, ex: dict[str, Any]) -> dict[str, Any]:
    O, H, L, C = (d[k].values for k in ("Open", "High", "Low", "Close"))
    e21, e50, wbe = d["ema21"].values, d["ema50"].values, d["w_below_e10"].values
    i0, entry, stop0, risk = e["i"], e["entry"], e["stop"], e["risk"]
    stop, part_done, part_px, part_i, reached_1r = stop0, False, None, None, False
    tgt = entry + ex["partial_at_r"] * risk
    frac = ex["partial_fraction"]
    exit_px, exit_i, reason = None, None, None
    pending_exit = False
    n = len(d)
    for j in range(i0, min(n, i0 + ex["max_hold_sessions"])):
        if j > i0 and pending_exit:
            exit_px, exit_i, reason = O[j], j, f"trail_{rule}"
            break
        if j > i0 and O[j] <= stop:
            exit_px, exit_i, reason = O[j], j, "gap_through_stop" if not part_done else "gap_breakeven"
            break
        if L[j] <= stop:  # conservative: on the entry day a low under the stop counts as stopped
            exit_px, exit_i, reason = stop, j, "stop" if not part_done else "breakeven_stop"
            break
        if not part_done and H[j] >= tgt:
            part_done, part_i = True, j
            part_px = max(tgt, O[j]) if j > i0 else tgt
            stop = max(stop, entry)
        if C[j] >= entry + risk:
            reached_1r = True
        if j > i0:
            if rule == "ema21":
                # trail on EMA21 once the trade has earned +1R; before that only the initial stop or an EMA50 break
                trig = (C[j] < e21[j]) if (reached_1r or part_done) else (C[j] < e50[j])
            elif rule == "ema50":
                trig = C[j] < e50[j]
            else:  # weekly structure: a completed weekly close below the 10-week EMA
                trig = bool(wbe[j]) and d.index[j].weekday() == 4
            if trig:
                pending_exit = True
    if exit_px is None:
        j = min(n - 1, i0 + ex["max_hold_sessions"] - 1)
        exit_px, exit_i, reason = C[j], j, ("open" if j == n - 1 else "time_stop")
    cost = 2 * side_cost(t)
    gross = (frac * (part_px - entry) + (1 - frac) * (exit_px - entry)) if part_done else (exit_px - entry)
    net = gross - cost * entry
    return {**e, "exit_i": exit_i, "exit_date": d.index[exit_i], "exit": float(exit_px), "partial": part_px,
            "partial_date": d.index[part_i] if part_i is not None else None, "reason": reason,
            "r": float(net / risk), "ret": float(net / entry), "hold": int(exit_i - i0)}


GRID = [(tr, k, ex) for tr in ("stop", "close") for k in (0.5, 1.0) for ex in ("ema21", "ema50", "weekly")]


def _stats(tr: list[dict[str, Any]]) -> dict[str, Any]:
    if not tr:
        return {"trades": 0}
    r = np.array([x["r"] for x in tr])
    wins, losses = r[r > 0], r[r <= 0]
    eq = np.cumsum(r)
    dd = float((eq - np.maximum.accumulate(np.concatenate([[0], eq]))[1:]).min())
    return {"trades": int(len(r)), "hit_rate": round(float((r > 0).mean()), 4), "avg_r": round(float(r.mean()), 3),
            "expectancy_r": round(float(r.mean()), 3), "avg_win_r": round(float(wins.mean()), 3) if wins.size else None,
            "avg_loss_r": round(float(losses.mean()), 3) if losses.size else None,
            "profit_factor": round(float(wins.sum() / -losses.sum()), 3) if losses.size and losses.sum() < 0 else None,
            "max_drawdown_r": round(dd, 2), "avg_hold_sessions": round(float(np.mean([x["hold"] for x in tr])), 1),
            "gap_stop_exits": int(sum(1 for x in tr if x["reason"].startswith("gap"))),
            "median_r": round(float(np.median(r)), 3)}


def portfolio_sim(trades: list[dict[str, Any]], frames: dict[str, pd.DataFrame], start: pd.Timestamp, end: pd.Timestamp,
                  risk_pct: float, max_pos: float = 0.25, max_open: int = 6, bench: Optional[pd.Series] = None) -> dict[str, Any]:
    """Daily mark-to-market equity: risk_pct of equity per trade, size haircut by the typical bad overnight gap,
    capped at max_pos of equity, at most max_open concurrent positions, no leverage. Sector cap not modelled."""
    idx = sorted({dt for f in frames.values() for dt in f.loc[start:end].index})
    if not idx:
        return {}
    idx = pd.DatetimeIndex(idx)
    by_entry: dict[pd.Timestamp, list[dict[str, Any]]] = {}
    for x in sorted(trades, key=lambda x: x["date"]):
        by_entry.setdefault(x["date"], []).append(x)
    cash, open_pos, eq, expo = 1.0, [], [], []
    x_frac = 0.5
    closes = {t: f["Close"] for t, f in frames.items()}
    for dt in idx:
        for x in by_entry.get(dt, []):
            if len(open_pos) >= max_open:
                continue
            equity = cash + sum(p["sh"] * float(closes[p["t"]].asof(dt)) for p in open_pos)
            per = x["risk"] + x["gap_q"] * x["entry"]
            sh = equity * risk_pct / 100 / per
            sh = min(sh, equity * max_pos / x["entry"], cash / (x["entry"] * (1 + side_cost(x["ticker"]))))
            if sh <= 0:
                continue
            cash -= sh * x["entry"] * (1 + side_cost(x["ticker"]))
            open_pos.append({"t": x["ticker"], "sh": sh, "x": x, "half": False})
        keep = []
        for p in open_pos:
            x = p["x"]
            if x["partial"] is not None and not p["half"] and x["partial_date"] is not None and dt >= x["partial_date"] \
                    and x["partial_date"] <= x["exit_date"]:
                sold = p["sh"] * x_frac
                cash += sold * x["partial"] * (1 - side_cost(p["t"]))
                p["sh"] -= sold
                p["half"] = True
            if dt >= x["exit_date"]:
                cash += p["sh"] * x["exit"] * (1 - side_cost(p["t"]))
            else:
                keep.append(p)
        open_pos = keep
        inv = sum(p["sh"] * float(closes[p["t"]].asof(dt)) for p in open_pos)
        eq.append(cash + inv)
        expo.append(inv / (cash + inv) if cash + inv > 0 else 0)
    s = pd.Series(eq, index=idx)
    r = s.pct_change().dropna()
    yrs = len(r) / 252
    out = {"cagr": round(float(s.iloc[-1] ** (1 / yrs) - 1), 4) if yrs > 0 else None,
           "sharpe": round(float(r.mean() / r.std() * np.sqrt(252)), 3) if r.std() > 0 else None,
           "max_drawdown": round(float((s / s.cummax() - 1).min()), 4),
           "avg_exposure": round(float(np.mean(expo)), 3) if expo else None,
           "exposure_note": f"risk {risk_pct}%/trade, cap {int(max_pos * 100)}%/position, max {max_open} open, no leverage",
           "from": str(idx[0].date()), "to": str(idx[-1].date())}
    if bench is not None:
        b = bench.loc[start:end].dropna()
        if len(b) > 20:
            byrs = len(b) / 252
            out["benchmark_cagr"] = round(float((b.iloc[-1] / b.iloc[0]) ** (1 / byrs) - 1), 4)
            out["excess_cagr"] = round(out["cagr"] - out["benchmark_cagr"], 4) if out["cagr"] is not None else None
    out["equity_monthly"] = [[str(k.date()), round(float(v), 4)] for k, v in s.resample("ME").last().items()]
    return out


def walk_forward(frames: dict[str, pd.DataFrame], rs: dict[str, pd.Series], cfg: dict[str, Any],
                 require_base: bool = True, require_retest: bool = True, risk_pct: float = 1.0,
                 bench: Optional[pd.Series] = None, train_m: int = 24, step_m: int = 6) -> dict[str, Any]:
    ex = cfg["exit"]
    scr = {t: screen_mask(t, f, rs.get(t, pd.Series(dtype=float)), cfg) for t, f in frames.items()}
    all_tr: dict[tuple, list[dict[str, Any]]] = {}
    for g in GRID:
        trig, k, rule = g
        lst = []
        for t, f in frames.items():
            busy_until = None
            for e in find_entries(t, f, scr[t], cfg, trig, k, require_base, require_retest):
                if busy_until is not None and e["date"] <= busy_until:
                    continue  # one position per ticker: ignore signals while a trade is open
                x = run_exit(t, f, e, rule, ex)
                busy_until = x["exit_date"]
                lst.append(x)
        all_tr[g] = lst
    first = min(f.index[0] for f in frames.values()) + pd.DateOffset(months=12)
    last = max(f.index[-1] for f in frames.values())
    t0 = first + pd.DateOffset(months=train_m)
    oos, chosen = [], []
    while t0 < last:
        t1 = t0 + pd.DateOffset(months=step_m)
        best, best_e = GRID[0], -1e9
        for g, lst in all_tr.items():
            tr = [x for x in lst if t0 - pd.DateOffset(months=train_m) <= x["date"] < t0 and x["exit_date"] < t0]
            if len(tr) < 10:
                continue
            e = float(np.mean([x["r"] for x in tr]))
            if e > best_e:
                best, best_e = g, e
        if best_e == -1e9:
            best = ("stop", 1.0, "ema21")  # too few training trades: fall back to the documented default
        oos += [x for x in all_tr[best] if t0 <= x["date"] < t1]
        chosen.append({"from": str(t0.date()), "to": str((t1 - pd.Timedelta(days=1)).date()),
                       "params": {"trigger": best[0], "atr_k": best[1], "exit": best[2]},
                       "train_expectancy_r": round(best_e, 3) if best_e > -1e9 else None})
        t0 = t1
    oos_start = first + pd.DateOffset(months=train_m)
    st = _stats(oos)
    st["by_market"] = {m: _stats([x for x in oos if market_of(x["ticker"]) == m]) for m in ("TH", "US")}
    st["exit_reasons"] = pd.Series([x["reason"] for x in oos]).value_counts().to_dict() if oos else {}
    st["portfolio"] = portfolio_sim(oos, frames, oos_start, last, risk_pct, bench=bench) if oos else {}
    st["chosen_params"] = chosen
    st["full_sample_by_param"] = {f"{g[0]}/{g[1]}/{g[2]}": _stats(v) for g, v in all_tr.items()}
    st["oos_from"], st["oos_to"] = str(oos_start.date()), str(last.date())
    st["recent_trades"] = [{"ticker": x["ticker"], "entry_date": str(x["date"].date()), "entry": round(x["entry"], 4),
                            "stop": round(x["stop"], 4), "exit_date": str(x["exit_date"].date()), "exit": round(x["exit"], 4),
                            "r": round(x["r"], 2), "reason": x["reason"]} for x in sorted(oos, key=lambda x: x["date"])[-15:]]
    return st


def _frames(tickers: list[str], cfg: dict[str, Any], period: str) -> dict[str, pd.DataFrame]:
    """Chunked yfinance download with a retry pass for names that came back empty (Yahoo drops names under load)."""
    import time
    tickers = sorted(set(tickers))
    raw: dict[str, pd.DataFrame] = {}
    for k in range(0, len(tickers), 20):
        chunk = tickers[k:k + 20]
        try:
            raw.update(download_ohlc(chunk, period, 3600))
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("ohlc chunk %s failed: %s", chunk[:3], exc)
    for attempt in range(2):
        missing = [t for t in tickers if t not in raw or raw[t] is None or len(raw[t].dropna()) < 300]
        if not missing:
            break
        time.sleep(5 * (attempt + 1))
        for t in missing:
            try:
                got = download_ohlc([t], period, 60)
                if t in got:
                    raw[t] = got[t]
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("ohlc retry %s failed: %s", t, exc)
    out = {}
    for t, df in raw.items():
        if df is not None and len(df.dropna()) > 300:
            try:
                out[t] = indicators(df, cfg)
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("indicators %s failed: %s", t, exc)
    missing = sorted(set(tickers) - set(out))
    if missing:
        LOGGER.warning("momentum_base: no usable history for %d names: %s", len(missing), missing)
    return out


def run_backtest_sync(extra: Optional[list[str]] = None) -> dict[str, Any]:
    cfg = load_cfg()
    from risk_engine import load_config as risk_cfg
    risk_pct = float(cfg.get("risk_pct") or risk_cfg().get("risk_budget_per_trade_pct", 1.0))
    ext = sorted(set(THAI + US + list(extra or []) + CORE["thai"] + CORE["global"]))
    frames = {t: drop_partial_bar(t, f) for t, f in _frames(ext + [SET_PROXY], cfg, "10y").items()}
    bench = {"TH": frames.get(SET_PROXY, pd.DataFrame()).get("Close"), "US": frames.get("SPY", pd.DataFrame()).get("Close")}
    frames.pop(SET_PROXY, None)
    rs = rs_percentiles(frames, cfg)  # RS ranks always computed on the full screen universe of each market
    res: dict[str, Any] = {"setup": SETUP, "risk_pct": risk_pct, "grid": [list(g) for g in GRID],
                           "data_to": str(max(f.index[-1] for f in frames.values()).date()), "universes": {}}
    for uni, names, bkey in (("thai_core", CORE["thai"], "TH"), ("global_core", CORE["global"], "US"),
                             ("thai_extended", [t for t in frames if t.endswith(".BK")], "TH"),
                             ("us_extended", [t for t in frames if not t.endswith(".BK")], "US")):
        fr = {t: frames[t] for t in names if t in frames}
        if not fr:
            continue
        r = {"tickers": len(fr), "missing": sorted(set(names) - set(fr)) if uni.endswith("core") else None}
        for variant, rb, rr in (("full_setup", True, True), ("no_base_filter", False, True), ("rs_breakout_only", False, False)):
            try:
                r[variant] = walk_forward(fr, rs, cfg, rb, rr, risk_pct, bench[bkey])
            except Exception as exc:  # noqa: BLE001
                LOGGER.exception("setup backtest %s/%s failed", uni, variant)
                r[variant] = {"error": str(exc)[:200]}
        res["universes"][uni] = r
    res["caveats"] = ["survivorship bias: universes are today's liquid names (extended US list is hindsight-heavy)",
                      "daily bars only; buy-stop fills at max(open, prior high + 1 tick); gaps through stops exit at the open",
                      "RS percentile ranks are inside the screen universe, not the whole market",
                      "parameters chosen on trailing 24m train windows by expectancy (min 10 trades), applied to the next 6m",
                      "costs: SET 0.157% + VAT + 0.10% slippage per side; offshore 0.15% + 0.25% FX + 0.10% per side",
                      "portfolio sim ignores the 40% sector cap and FX P&L (US results in USD)"]
    return res


# ------------------------------------------------------------------ live screen
def drop_partial_bar(t: str, d: pd.DataFrame) -> pd.DataFrame:
    """Drop today's still-forming daily bar (SET closes ~16:40 ICT; US closes 16:00 New York)."""
    if d.empty:
        return d
    last = d.index[-1].date()
    if t.endswith(".BK"):
        now = datetime.now(ICT)
        if last >= now.date() and (now.hour, now.minute) < (17, 15):
            return d.iloc[:-1]
    else:
        now = datetime.now(ZoneInfo("America/New_York"))
        if last >= now.date() and (now.hour, now.minute) < (16, 30):
            return d.iloc[:-1]
    return d


def live_state(t: str, d: pd.DataFrame, scr: pd.Series, cfg: dict[str, Any], atr_k: float, exit_rule: str = "ema21") -> dict[str, Any]:
    """Current state from the SAME state machine the backtest uses (buy-stop trigger)."""
    n = len(d)
    last = d.iloc[-1]
    fin: dict[str, Any] = {}
    ents = find_entries(t, d, scr, cfg, "stop", atr_k, True, True, final=fin)
    out: dict[str, Any] = {}
    bo_date = None
    open_trade = None
    if ents:
        x = run_exit(t, d, ents[-1], exit_rule, cfg["exit"])
        if x["reason"] == "open":
            open_trade = x
    if fin.get("bo_i", -1) >= 0 and fin.get("state") in ("broken_out", "pullback"):
        bo_date = d.index[fin["bo_i"]]
    if ents and ents[-1]["i"] == n - 1:
        e = ents[-1]
        state = "triggered_today"
        bo_date = e["breakout_date"]
        out.update(trigger_fill=round(e["entry"], 4), signal_stop=round(e["stop"], 4))
    elif open_trade is not None:
        state = "in_trade"
        bo_date = open_trade["breakout_date"]
        out["open_trade"] = {"entry_date": str(open_trade["date"].date()), "entry": round(open_trade["entry"], 4),
                             "initial_stop": round(open_trade["stop"], 4), "partial_taken": open_trade["partial"] is not None,
                             "r_now": round((float(last["Close"]) - open_trade["entry"]) / open_trade["risk"], 2),
                             "trail_rule": exit_rule,
                             "trail_level": round(float(last["ema21"] if exit_rule == "ema21" else last["ema50"] if exit_rule == "ema50" else last["w_ema10"]), 4)}
    elif fin.get("state") == "pullback":
        state = "at_support_wait_trigger"
        out["pullback_date"] = str(d.index[fin["pb_i"]].date())
    elif fin.get("state") == "broken_out":
        state = "extended_wait_pullback"
    elif not bool(scr.iloc[-1]):
        state = "fails_screen"
    elif not bool(last["w_ok"]):
        state = "weekly_not_ok"
    elif bool(last["base_ok"]):
        state = "base_forming"
    else:
        state = "no_setup"
    if bo_date is not None:
        bi = d.index.get_loc(bo_date)
        out.update(breakout_date=str(bo_date.date()), breakout_level=round(float(d["pivot_high"].iloc[bi]), 4))
    lv = confluence_levels(d, bo_date)
    a = float(last["atr14"])
    if state == "triggered_today":
        trig_px = out["trigger_fill"]
        stop = out["signal_stop"]
    else:
        trig_px = float(last["High"]) + tick_of(t, float(last["High"]))
        zl = (lv["zone"] or {}).get("low")
        pb_low = float(fin.get("pb_low") or d["Low"].iloc[-3:].min()) if state == "at_support_wait_trigger" else float(d["Low"].iloc[-3:].min())
        sig_low = min([v for v in (float(last["Low"]), pb_low, zl) if v is not None])
        stop = sig_low - atr_k * a
    out.update(state=state, price=round(float(last["Close"]), 4), as_of=str(d.index[-1].date()),
               ret_1m=float(last["ret_1m"]), ret_3m=float(last["ret_3m"]), ret_6m=float(last["ret_6m"]),
               adv20=float(last["adv20"]), base_ok=bool(last["base_ok"]), base_score=round(float(last["base_score"]), 1),
               weekly_ok=bool(last["w_ok"]), atr14=round(a, 4), atr_ratio=round(float(last["atr_ratio"]), 3),
               ema9=round(float(last["ema9"]), 4), ema21=round(float(last["ema21"]), 4), ema50=round(float(last["ema50"]), 4),
               ema21_slope5=round(float(last["ema21_slope5"]), 4),
               gap_q=round(float(last["gap_q"]) if pd.notna(last["gap_q"]) else 0.02, 4),
               zone=lv["zone"], levels=lv["levels"][:12],
               trigger={"type": "daily buy-stop 1 tick above the prior day's high (swing; no intraday data)",
                        "price": round(trig_px, 4),
                        "valid_for": "filled today" if state == "triggered_today" else "next session; re-set daily while the first retest holds (max 5 sessions)"},
               stop=round(stop, 4), risk_per_share=round(trig_px - stop, 4),
               risk_pct_of_price=round((trig_px - stop) / trig_px, 4) if trig_px else None)
    if out.get("breakout_level"):
        bl = out["breakout_level"]
        bi = d.index.get_loc(bo_date)
        base_low = float(d["Low"].iloc[max(0, bi - 60):bi].min())
        mm = bl + (bl - base_low)
        out["target"] = round(max(mm, float(d["High"].iloc[-252:].max())), 4)
        out["target_basis"] = f"measured move {bl:.4g} + base depth {bl - base_low:.4g} (or 52w high if higher)"
    return out


async def run_screen(pool: Any, make_plans: bool = True) -> dict[str, Any]:
    cfg = load_cfg()
    await ensure_tables(pool)
    async with pool.acquire() as conn:
        wl = [r["ticker"] for r in await conn.fetch("SELECT ticker FROM investment_watchlist WHERE status <> 'dropped' AND COALESCE(sector, '') NOT IN ('us_bond')")]
    names = sorted(set(THAI + US + [t for t in wl if t and "=" not in t and not t.startswith("^")]))
    frames = await asyncio.to_thread(_frames, names, cfg, "2y")
    frames = {t: drop_partial_bar(t, f) for t, f in frames.items()}
    newest = max(f.index[-1] for f in frames.values())
    stale = sorted(t for t, f in frames.items() if (newest - f.index[-1]).days > 7)  # price-freshness rule (<= 1 week)
    frames = {t: f for t, f in frames.items() if t not in stale}
    rs = rs_percentiles(frames, cfg)
    bt = await latest_backtest(pool)
    lp = (bt or {}).get("live_params") or {}
    rows = []
    for t, d in frames.items():
        try:
            scr = screen_mask(t, d, rs.get(t, pd.Series(dtype=float)), cfg)
            pm = lp.get(market_of(t)) if isinstance(lp.get(market_of(t)), dict) else {}
            st = live_state(t, d, scr, cfg, float(pm.get("atr_k") or cfg["stop"]["atr_buffer"]), pm.get("exit") or cfg["exit"]["rule"])
            st["params"] = {"atr_k": float(pm.get("atr_k") or cfg["stop"]["atr_buffer"]), "exit": pm.get("exit") or cfg["exit"]["rule"],
                            "source": "latest walk-forward choice" if pm else "config default"}
            st["rs_pct"] = round(float(rs[t].iloc[-1]), 1) if t in rs and pd.notna(rs[t].iloc[-1]) else None
            st["passed_screen"] = bool(scr.iloc[-1])
            st["market"] = market_of(t)
            st["ticker"] = t
            st["watchlist"] = t in wl
            rows.append(st)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("screen %s failed: %s", t, exc)
    as_of = datetime.now(ICT).date()
    order = {"triggered_today": 0, "at_support_wait_trigger": 1, "extended_wait_pullback": 2, "in_trade": 3,
             "base_forming": 4, "retest_expired": 5, "failed_breakout": 6, "weekly_not_ok": 7, "fails_screen": 8, "no_setup": 9}
    rows.sort(key=lambda r: (order.get(r["state"], 9), -(r.get("rs_pct") or 0)))
    async with pool.acquire() as conn:
        for r in rows:
            score = (r.get("rs_pct") or 0) * 0.6 + r["base_score"] * 0.4
            await conn.execute(
                """INSERT INTO setup_screens (as_of, setup, ticker, market, state, passed, rs_pct, score, data)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb)
                   ON CONFLICT (as_of, setup, ticker) DO UPDATE SET market=EXCLUDED.market, state=EXCLUDED.state, passed=EXCLUDED.passed,
                     rs_pct=EXCLUDED.rs_pct, score=EXCLUDED.score, data=EXCLUDED.data, created_at=now()""",
                as_of, SETUP, r["ticker"], r["market"], r["state"], r["passed_screen"], r.get("rs_pct"), round(score, 2),
                json.dumps(r, default=str))
    plans = await propose_plans(pool, rows, cfg) if make_plans else {"skipped": True}
    return {"as_of": as_of.isoformat(), "screened": len(rows), "stale_excluded": stale, "passed": sum(r["passed_screen"] for r in rows),
            "actionable": [r["ticker"] for r in rows if r["state"] in ("triggered_today", "at_support_wait_trigger")],
            "plans": plans}


async def propose_plans(pool: Any, rows: list[dict[str, Any]], cfg: dict[str, Any]) -> dict[str, Any]:
    """PROPOSED plans only (status 'proposed', source 'setup'). They never place orders; approval on /desk only logs
    Tho's decision and copies levels to the watch list for alerts."""
    import trade_plans as tp
    from trade_plans import MIN_RR
    await ensure_tables(pool)
    from risk_engine import load_config as risk_cfg
    risk_pct = float(cfg.get("risk_pct") or risk_cfg().get("risk_budget_per_trade_pct", 1.0))
    bt = await latest_backtest(pool) or {}
    ev = {}
    for mkt, uni in (("TH", "thai_extended"), ("US", "us_extended")):
        f = ((bt.get("universes") or {}).get(uni) or {}).get("full_setup") or {}
        ev[mkt] = {k: f.get(k) for k in ("trades", "hit_rate", "expectancy_r", "profit_factor")}
    made = []
    async with pool.acquire() as conn:
        await conn.execute("UPDATE trade_plans SET status='superseded', updated_at=now() WHERE source='setup' AND setup=$1 AND status='proposed'", SETUP)
        for r in rows:
            if r["state"] not in ("triggered_today", "at_support_wait_trigger"):
                continue
            el = r["trigger"]["price"]
            eh = round(el + 0.3 * r["atr14"], 4)
            stop = r["stop"]
            mid = (el + eh) / 2
            tgt = r.get("target") or round(mid + 3 * (mid - stop), 4)
            rr = (tgt - mid) / (mid - stop) if mid > stop else 0
            viable = rr >= MIN_RR and r["risk_pct_of_price"] <= cfg["stop"]["max_risk_pct_of_price"]
            z = r.get("zone") or {}
            rationale = (f"[{SETUP}] {r['state'].replace('_', ' ')}. RS pct {r.get('rs_pct')} ({r['market']}); 1/3/6m "
                         f"{r['ret_1m']:+.0%}/{r['ret_3m']:+.0%}/{r['ret_6m']:+.0%}. Weekly trend ok; breakout {r.get('breakout_date')} over "
                         f"{r.get('breakout_level')}; first retest {r.get('pullback_date')}. Support zone {z.get('low')}-{z.get('high')} "
                         f"({'; '.join(z.get('members') or [])}). Daily trigger: buy-stop {el} (prior high + 1 tick), don't chase above {eh}. "
                         f"Stop {stop} = below signal-bar/zone low minus ATR buffer (ATR14 {r['atr14']}). Target {tgt} "
                         f"({r.get('target_basis', '3R fallback')}); manage: half at +3R, stop to breakeven, trail rest via {r['params']['exit']} "
                         f"(ema21 = daily close < EMA21 once +1R; ema50 = daily close < EMA50; weekly = weekly close < EMA10w). "
                         f"Size uses {risk_pct}% risk (lesson uses 0.5%) with a {r['gap_q']:.1%} overnight-gap haircut, then 25%/40% caps. "
                         f"Swing/position horizon (weeks-months). Tho executes manually; nothing is ordered automatically.")
            e = ev.get(r["market"]) or {}
            if e.get("expectancy_r") is not None:
                rationale += (f" Backtest evidence ({r['market']} extended universe, walk-forward OOS): {e['trades']} trades, hit {e['hit_rate']:.0%}, "
                              f"expectancy {e['expectancy_r']:+.2f}R, PF {e['profit_factor']}.")
                if e["expectancy_r"] <= 0.1:
                    rationale += " WARNING: weak/no out-of-sample edge in this market - treat as low conviction."
            if not viable:
                rationale += f" NOT VIABLE: R:R {rr:.2f} < {MIN_RR} or stop too wide."
            inputs = {"price": {"value": r["price"], "source": "yfinance daily close", "as_of": r["as_of"]},
                      "setup": SETUP, "screen": {k: r.get(k) for k in ("rs_pct", "ret_1m", "ret_3m", "ret_6m", "adv20", "base_score",
                                                                        "weekly_ok", "state", "breakout_date", "breakout_level", "pullback_date")},
                      "zone": z, "levels": r.get("levels"), "gap_q": r["gap_q"], "risk_pct": risk_pct, "backtest_evidence": e,
                      "stop_for_sizing": round(stop - r["gap_q"] * el, 4)}
            pid = await conn.fetchval(
                """INSERT INTO trade_plans (ticker, source, setup, status, viable, currency, last_price, entry_low, entry_high, stop, target, rr, atr,
                       inputs, rationale, expiry) VALUES ($1,'setup',$2,'proposed',$3,$4,$5,$6,$7,$8,$9,$10,$11,$12::jsonb,$13,$14) RETURNING id""",
                r["ticker"], SETUP, viable, "THB" if r["market"] == "TH" else "USD", r["price"], el, eh, stop, tgt, rr, r["atr14"],
                json.dumps(inputs, default=str), rationale, date.today() + timedelta(days=int(cfg.get("plan_expiry_days", 14))))
            made.append({"id": pid, "ticker": r["ticker"], "viable": viable, "rr": round(rr, 2)})
    if made:
        await tp.refresh_checklists(pool, statuses=("proposed",))
    return {"proposed": made}


async def run_backtest(pool: Any) -> dict[str, Any]:
    await ensure_tables(pool)
    async with pool.acquire() as conn:
        wl = [r["ticker"] for r in await conn.fetch("SELECT ticker FROM investment_watchlist WHERE status <> 'dropped' AND COALESCE(sector, '') NOT IN ('us_bond')")]
    res = await asyncio.to_thread(run_backtest_sync, [t for t in wl if t and "=" not in t and not t.startswith("^")])
    res["comparison"] = await compare_with_existing(pool, res)
    res["live_params"] = _live_params(res)
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO setup_backtests (setup, results) VALUES ($1,$2::jsonb)", SETUP, json.dumps(res, default=str))
    return {k: res[k] for k in ("comparison", "live_params", "data_to")}


def _live_params(res: dict[str, Any]) -> dict[str, Any]:
    """Latest walk-forward parameter choice per market (extended universes) - what the live screen uses."""
    out = {}
    for mkt, uni in (("TH", "thai_extended"), ("US", "us_extended")):
        ch = (((res.get("universes") or {}).get(uni) or {}).get("full_setup") or {}).get("chosen_params") or []
        out[mkt] = ({**ch[-1]["params"], "from_universe": uni, "window_from": ch[-1]["from"]} if ch
                    else {"trigger": "stop", "atr_k": 1.0, "exit": "ema21", "from_universe": "default"})
    return out


async def compare_with_existing(pool: Any, res: dict[str, Any]) -> dict[str, Any]:
    import walkforward as wf
    old = await wf.latest_backtest(pool)
    out = {}
    for uni, key in (("thai_core", "thai"), ("global_core", "global")):
        new = ((res["universes"].get(uni) or {}).get("full_setup") or {})
        p = new.get("portfolio") or {}
        ex = {n: {k: m.get(k) for k in ("cagr", "sharpe", "max_drawdown", "excess_cagr", "hit_rate", "n_positions")}
              for n, m in ((old.get(key) or {}).get("strategies") or {}).items() if "error" not in m}
        best = max(ex.items(), key=lambda kv: kv[1].get("sharpe") or -9) if ex else (None, {})
        adds = bool(new.get("trades", 0) >= 30 and (new.get("expectancy_r") or 0) > 0.15 and (p.get("sharpe") or 0) > (best[1].get("sharpe") or 0)
                    and (p.get("excess_cagr") or -1) > 0)
        out[uni] = {"setup": {**{k: new.get(k) for k in ("trades", "hit_rate", "expectancy_r", "profit_factor", "max_drawdown_r")},
                              **{k: p.get(k) for k in ("cagr", "sharpe", "max_drawdown", "excess_cagr")}},
                    "existing": ex, "best_existing": best[0], "adds_value_oos": adds,
                    "rule": "blend only if OOS trades>=30, expectancy>0.15R, portfolio Sharpe > best existing strategy and excess CAGR > 0"}
    return out


async def latest_backtest(pool: Any) -> Optional[dict[str, Any]]:
    async with pool.acquire() as conn:
        await conn.execute(DDL)
        r = await conn.fetchrow("SELECT run_at, results FROM setup_backtests WHERE setup=$1 ORDER BY run_at DESC LIMIT 1", SETUP)
    if not r:
        return None
    res = json.loads(r["results"]) if isinstance(r["results"], str) else r["results"]
    return {"run_at": r["run_at"].isoformat(), **res}


async def latest_screen(pool: Any, only_passed: bool = False) -> dict[str, Any]:
    async with pool.acquire() as conn:
        await conn.execute(DDL)
        rows = await conn.fetch("""SELECT ticker, market, state, passed, rs_pct, score, data, created_at FROM setup_screens
                                   WHERE setup=$1 AND as_of = (SELECT max(as_of) FROM setup_screens WHERE setup=$1)""", SETUP)
    items = []
    for r in rows:
        d = json.loads(r["data"]) if isinstance(r["data"], str) else r["data"]
        d["created_at"] = r["created_at"].isoformat()
        if only_passed and not r["passed"]:
            continue
        items.append(d)
    order = ["triggered_today", "at_support_wait_trigger", "extended_wait_pullback", "in_trade", "base_forming",
             "retest_expired", "failed_breakout", "weekly_not_ok", "fails_screen", "no_setup"]
    items.sort(key=lambda x: (order.index(x["state"]) if x["state"] in order else 99, -(x.get("rs_pct") or 0)))
    return {"setup": SETUP, "as_of": items[0]["as_of"] if items else None, "items": items, "doc": "docs/lessons/momentum_base_setup.md",
            "method": __doc__}


def advisor_lines(screen: dict[str, Any], bt: Optional[dict[str, Any]], tickers: list[str]) -> list[str]:
    """Compact text for the 8991 advisor (LINE secretary questions)."""
    items = screen.get("items") or []
    lines = [f"=== SETUP: {SETUP} (swing/position adaptation of Tho's lesson; screen as of {screen.get('as_of')}) ==="]
    act = [i for i in items if i["state"] in ("triggered_today", "at_support_wait_trigger")]
    ext = [i for i in items if i["state"] == "extended_wait_pullback"]
    lines.append("  Actionable (first retest at support, daily trigger): " + (", ".join(
        f"{i['ticker']} trigger {i['trigger']['price']} stop {i['stop']} (RS {i.get('rs_pct')})" for i in act[:8]) or "none"))
    lines.append("  Strong but extended (wait for pullback): " + (", ".join(f"{i['ticker']} (RS {i.get('rs_pct')})" for i in ext[:8]) or "none"))
    tk = {t.upper() for t in tickers} | {t.upper().replace(".BK", "") for t in tickers}
    for i in items:
        if i["ticker"] in tk or i["ticker"].replace(".BK", "") in tk:
            z = i.get("zone") or {}
            if i["state"] in ("triggered_today", "at_support_wait_trigger"):
                act_txt = f"daily buy-stop trigger {i['trigger']['price']}, stop {i['stop']}, target {i.get('target')}"
            elif i["state"] == "in_trade":
                ot = i.get("open_trade") or {}
                act_txt = (f"model setup already triggered {ot.get('entry_date')} at {ot.get('entry')} (now {ot.get('r_now')}R) - too late for a new "
                           f"entry; trail level ({ot.get('trail_rule')}) {ot.get('trail_level')}")
            elif i["state"] == "extended_wait_pullback":
                act_txt = f"extended after breakout {i.get('breakout_date')} - wait for the first pullback into the zone, do not chase"
            else:
                act_txt = "no entry setup now"
            lines.append(f"  - {i['ticker']}: state {i['state']}, RS pct {i.get('rs_pct')}, 1/3/6m {i['ret_1m']:+.0%}/{i['ret_3m']:+.0%}/{i['ret_6m']:+.0%}, "
                         f"weekly ok {i['weekly_ok']}, base ok {i['base_ok']}, support zone {z.get('low')}-{z.get('high')} ({'; '.join(z.get('members') or [])}); {act_txt}")
    if bt:
        for uni in ("thai_extended", "us_extended", "thai_core", "global_core"):
            f = (((bt.get("universes") or {}).get(uni) or {}).get("full_setup") or {})
            p = f.get("portfolio") or {}
            if f.get("trades"):
                lines.append(f"  Backtest walk-forward OOS {f.get('oos_from')}..{f.get('oos_to')} {uni}: {f['trades']} trades, hit {f.get('hit_rate'):.0%}, "
                             f"expectancy {f.get('expectancy_r'):+.2f}R, PF {f.get('profit_factor')}, CAGR {p.get('cagr')}, Sharpe {p.get('sharpe')}, maxDD {p.get('max_drawdown')}")
        lines.append("  Verdict: positive edge in US names, none on the broad SET list; weaker than existing rotation signals at portfolio level, "
                     "so NOT blended into the composite/forecasts - a separate entry-timing setup.")
    lines.append("  Rules: swing/position only (no intraday). Advisory only - Tho places every order himself; plans are proposals.")
    return lines
