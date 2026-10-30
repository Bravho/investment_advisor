"""Portfolio construction - pro layer #4 (2026-10-30). SUGGESTIONS ONLY; nothing is traded.

Inputs: config/investment_policy.json (DRAFT policy: class ranges/targets, tilt, bands, BL params, tax notes),
config/risk_limits.json (position/sector caps), live positions, macro regime, frozen 1y forecasts.
Outputs, per asset class:
  1. strategic target + tactical tilt from the macro regime (bounded by the policy range)
  2. risk-parity weights (equal risk contribution of the risky classes, THB returns, 1y daily cov)
  3. Black-Litterman weights (equilibrium from the policy weights; views = frozen 1y forecasts,
     confidence-weighted)
  4. recommended = mean of 1-3, clipped to the policy ranges
then rebalancing bands, instrument-level trades (board lots, costs) and tax-aware lot selection.
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

from market_history import SET_PROXY, download_closes
from trade_plans import COMMISSION_TH, VAT, SLIPPAGE, US_COMMISSION, FX_SPREAD

LOGGER = logging.getLogger("portfolio_engine.construction")
ICT = ZoneInfo("Asia/Bangkok")
ROOT = Path(__file__).resolve().parent.parent
POLICY_PATH = ROOT / "config" / "investment_policy.json"
CLASSES = ["thai_equity", "gold", "global_equity", "cash_bonds"]
RISKY = ["thai_equity", "gold", "global_equity"]
DDL = """
CREATE TABLE IF NOT EXISTS portfolio_proposals (
    id         SERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    status     VARCHAR(20) NOT NULL DEFAULT 'suggestion',
    policy     JSONB NOT NULL,
    result     JSONB NOT NULL
);
"""


def load_policy() -> dict[str, Any]:
    return json.loads(POLICY_PATH.read_text())


def classify(ticker: str, pol: dict[str, Any]) -> str:
    c = pol["classification"]
    if ticker in c:
        return c[ticker]
    return c["default_bk"] if ticker.endswith(".BK") else c["default_other"]


def class_returns(px: pd.DataFrame) -> pd.DataFrame:
    thb = px["THB=X"]
    df = pd.DataFrame({"thai_equity": px[SET_PROXY], "gold": px["GC=F"] * thb, "global_equity": px["SPY"] * thb}).dropna()
    return np.log(df).diff().dropna()


def clip_to_ranges(w: dict[str, float], pol: dict[str, Any]) -> dict[str, float]:
    """Project weights (pp, summing to 100) onto the policy box constraints."""
    ac = pol["asset_classes"]
    w = dict(w)
    for _ in range(50):
        for k in CLASSES:
            w[k] = min(max(w[k], ac[k]["min"]), ac[k]["max"])
        gap = 100 - sum(w.values())
        if abs(gap) < 1e-6:
            break
        free = [k for k in CLASSES if (gap > 0 and w[k] < ac[k]["max"]) or (gap < 0 and w[k] > ac[k]["min"])]
        if not free:
            break
        for k in free:
            w[k] += gap / len(free)
    return {k: round(v, 2) for k, v in w.items()}


def strategic_tilt(pol: dict[str, Any], regime: Optional[str]) -> dict[str, float]:
    ac = pol["asset_classes"]
    w = {k: float(ac[k]["target"]) for k in CLASSES}
    tilt = (pol.get("tactical") or {}).get(regime or "", {}) if regime in ("risk_on", "risk_off") else {}
    for k, d in tilt.items():
        w[k] += d
    return clip_to_ranges(w, pol)


def risk_parity(cov: np.ndarray, risky_budget: float) -> np.ndarray:
    n = cov.shape[0]
    w = np.ones(n) / n
    for _ in range(500):
        mrc = cov @ w
        rc = w * mrc
        target = rc.sum() / n
        w = w * (target / np.maximum(rc, 1e-12)) ** 0.5
        w = w / w.sum()
    return w * risky_budget


def black_litterman(cov: np.ndarray, w_eq: np.ndarray, views: dict[int, tuple[float, float]], delta: float, tau: float,
                    floor: float) -> dict[str, Any]:
    pi = delta * cov @ w_eq
    if not views:
        mu = pi
    else:
        idx = sorted(views)
        P = np.zeros((len(idx), len(w_eq)))
        Q = np.zeros(len(idx))
        om = np.zeros(len(idx))
        for r, i in enumerate(idx):
            P[r, i] = 1
            q, c = views[i]
            Q[r] = q
            c = min(max(c, floor), 0.95)
            om[r] = tau * cov[i, i] * (1 - c) / c
        tS = np.linalg.inv(tau * cov)
        Om = np.diag(om)
        mu = np.linalg.inv(tS + P.T @ np.linalg.inv(Om) @ P) @ (tS @ pi + P.T @ np.linalg.inv(Om) @ Q)
    w = np.linalg.solve(delta * cov, mu)
    w = np.clip(w, 0, None)
    return {"pi": pi, "mu": mu, "w": w / w.sum() if w.sum() > 0 else w_eq}


async def _forecast_views(pool: Any) -> dict[str, Any]:
    async with pool.acquire() as conn:
        rows = await conn.fetch("""SELECT DISTINCT ON (subject) subject, exp_return, confidence, made_at, payload_sha256 FROM predictions
                                   WHERE source='live' AND horizon='1y' AND subject = ANY($1::text[]) ORDER BY subject, made_at DESC""",
                                [SET_PROXY, "GC=F", "SPY", "THB=X"])
    return {r["subject"]: {"exp_log_return": float(r["exp_return"]), "confidence": float(r["confidence"]),
                           "made_at": r["made_at"].isoformat(), "sha": r["payload_sha256"][:12]} for r in rows}


def _lot(ticker: str) -> float:
    return 100 if ticker.endswith(".BK") else (0.0001 if ticker == "SCBGOLDE" else 1)


def _cost(ticker: str, notional: float) -> float:
    if ticker.endswith(".BK"):
        return abs(notional) * (COMMISSION_TH * (1 + VAT) + SLIPPAGE)
    if ticker in ("SCBGOLDE", "CASH"):
        return 0.0  # fund subscription/redemption fee assumed 0 (check the fund's fact sheet)
    return abs(notional) * (US_COMMISSION + FX_SPREAD + SLIPPAGE)


async def run_construction(pool: Any) -> dict[str, Any]:
    import risk_engine as re_mod
    pol = load_policy()
    caps = re_mod.load_config()
    positions = await re_mod._positions(pool)
    total = sum(p["value_thb"] for p in positions)
    async with pool.acquire() as conn:
        await conn.execute(DDL)
        reg = await conn.fetchrow("SELECT regime, score, as_of FROM market_regime ORDER BY as_of DESC LIMIT 1")
        hold = {r["ticker"]: dict(r) for r in await conn.fetch("SELECT ticker, quantity, avg_cost_price, currency FROM holdings WHERE quantity > 0")}
        cal = {r["ticker"]: (json.loads(r["data"]) if isinstance(r["data"], str) else r["data"]).get("calendar") or {}
               for r in await conn.fetch("SELECT ticker, data FROM fundamentals_cache")}
        bot = await conn.fetchval("SELECT reading FROM market_factors WHERE key='bot_rate'")
    regime = reg["regime"] if reg else None
    px = await asyncio.to_thread(download_closes, [SET_PROXY, "GC=F", "SPY", "THB=X"], None, "2y", 3600)
    rets = class_returns(px).iloc[-252:]
    cov = rets.cov().values * 252
    usdthb = float(px["THB=X"].dropna().iloc[-1])
    spy = float(px["SPY"].dropna().iloc[-1])

    cur = {k: 0.0 for k in CLASSES}
    by_ticker = {}
    for p in positions:
        c = classify(p["ticker"], pol)
        cur[c] += p["value_thb"]
        by_ticker[p["ticker"]] = p
    cur_pct = {k: round(v / total * 100, 2) for k, v in cur.items()}

    st = strategic_tilt(pol, regime)
    risky_budget = 100 - st["cash_bonds"]
    rp_r = risk_parity(cov, risky_budget)
    rp = clip_to_ranges({**{k: float(rp_r[i]) for i, k in enumerate(RISKY)}, "cash_bonds": st["cash_bonds"]}, pol)

    bl_cfg = pol["black_litterman"]
    w_eq = np.array([pol["asset_classes"][k]["target"] for k in RISKY], dtype=float)
    w_eq = w_eq / w_eq.sum()
    fv = await _forecast_views(pool)
    fx_view = (fv.get("THB=X") or {}).get("exp_log_return", 0.0)
    views, view_info = {}, {}
    for i, (k, subj, add_fx) in enumerate([("thai_equity", SET_PROXY, False), ("gold", "GC=F", True), ("global_equity", "SPY", True)]):
        v = fv.get(subj)
        if v:
            q = v["exp_log_return"] + (fx_view if add_fx else 0.0)
            views[i] = (q, v["confidence"])
            view_info[k] = {"view_1y_thb": round(q, 4), "confidence": v["confidence"], "from": subj, "prediction_sha": v["sha"], "made_at": v["made_at"]}
    bl = black_litterman(cov, w_eq, views, bl_cfg["risk_aversion"], bl_cfg["tau"], bl_cfg["view_confidence_floor"])
    blw = clip_to_ranges({**{k: float(bl["w"][i] * risky_budget) for i, k in enumerate(RISKY)}, "cash_bonds": st["cash_bonds"]}, pol)
    rec = clip_to_ranges({k: (st[k] + rp[k] + blw[k]) / 3 for k in CLASSES}, pol)

    # rebalancing bands
    rb = pol["rebalancing"]
    band_rows, trade_classes = [], []
    for k in CLASSES:
        a = pol["asset_classes"][k]
        band = min(rb["band_abs_pp"], rec[k] * rb["band_rel_pct"] / 100)
        drift = cur_pct[k] - rec[k]
        outside = abs(drift) > band or not (a["min"] <= cur_pct[k] <= a["max"])
        band_rows.append({"class": k, "current_pct": cur_pct[k], "target_pct": rec[k], "drift_pp": round(drift, 2),
                          "band_pp": round(band, 2), "range": [a["min"], a["max"]], "rebalance": outside})
        if outside:
            trade_classes.append(k)

    # instrument targets
    max_pos = float(caps.get("max_position_pct", 25))
    tgt_val: dict[str, float] = {}
    # Tax-locked holdings (ThaiESG until lock_until) are fixed: never sold, switched or trimmed (2026-10-30).
    locked = {t for t, p in by_ticker.items() if p.get("locked")}
    for t in locked:
        tgt_val[t] = by_ticker[t]["value_thb"]
    thai_hold = [t for t, p in by_ticker.items() if classify(t, pol) == "thai_equity" and t not in locked]
    locked_thai = sum(by_ticker[t]["value_thb"] for t in locked if classify(t, pol) == "thai_equity")
    thai_target = max(0.0, rec["thai_equity"] / 100 * total - locked_thai)
    if "thai_equity" in trade_classes:
        cur_thai = sum(by_ticker[t]["value_thb"] for t in thai_hold) or 1
        rem = thai_target
        for t in thai_hold:
            v = min(by_ticker[t]["value_thb"] / cur_thai * thai_target, max_pos / 100 * total)
            tgt_val[t] = v
            rem -= v
        if rem > rb["min_trade_thb"]:
            tgt_val[SET_PROXY] = rem
    else:
        for t in thai_hold:
            tgt_val[t] = by_ticker[t]["value_thb"]
    gold_hold = [t for t in by_ticker if classify(t, pol) == "gold" and t not in locked] or ["SCBGOLDE"]
    for t in gold_hold:
        tgt_val[t] = rec["gold"] / 100 * total / len(gold_hold) if "gold" in trade_classes else by_ticker.get(t, {}).get("value_thb", 0)
    glob = pol["implementation"]["global_equity"]["core_proxy"]
    tgt_val[glob] = rec["global_equity"] / 100 * total if "global_equity" in trade_classes else 0.0
    trades, cash_flow = [], 0.0
    lp = {SET_PROXY: float(px[SET_PROXY].dropna().iloc[-1]), glob: spy}
    for t, tv in tgt_val.items():
        if t in locked:
            continue  # fixed weight; no trade suggested before lock_until
        cv = by_ticker.get(t, {}).get("value_thb", 0.0)
        qty_now = float(hold[t]["quantity"]) if t in hold else 0.0
        price_thb = (cv / qty_now) if qty_now else (lp.get(t, 0) * (usdthb if not t.endswith(".BK") and t != "SCBGOLDE" else 1))
        if not price_thb:
            continue
        d_val = tv - cv
        lot = _lot(t)
        local_px = price_thb / (usdthb if not t.endswith(".BK") and t != "SCBGOLDE" else 1)
        units = math.floor(abs(d_val) / price_thb / lot) * lot * (1 if d_val > 0 else -1)
        if abs(units * price_thb) < rb["min_trade_thb"]:
            continue
        notional = units * price_thb
        cost = _cost(t, notional)
        tr = {"ticker": t, "side": "BUY" if units > 0 else "SELL", "units": round(abs(units), 4), "price_local": round(local_px, 4),
              "notional_thb": round(abs(notional), 0), "est_cost_thb": round(cost, 0), "from_pct": round(cv / total * 100, 2),
              "to_pct": round((cv + notional) / total * 100, 2)}
        if units < 0 and t in hold:
            tr["tax_lot"] = lot_selection(t, abs(units), hold[t], local_px, cal.get(t) or {})
        trades.append(tr)
        cash_flow -= notional + cost
    cash_after = cash_flow  # current cash is not tracked -> starts at 0
    result = {
        "status": "DRAFT suggestion - policy not approved; nothing is traded",
        "as_of": datetime.now(ICT).isoformat(timespec="minutes"),
        "portfolio_value_thb": round(total, 0), "regime": {"value": regime, "as_of": str(reg["as_of"]) if reg else None},
        "current_pct": cur_pct,
        "weights": {"strategic_plus_tilt": st, "risk_parity": rp, "black_litterman": blw, "recommended": rec},
        "black_litterman": {"equilibrium_returns": {k: round(float(bl["pi"][i]), 4) for i, k in enumerate(RISKY)},
                            "posterior_returns": {k: round(float(bl["mu"][i]), 4) for i, k in enumerate(RISKY)},
                            "views": view_info, "tau": bl_cfg["tau"], "risk_aversion": bl_cfg["risk_aversion"]},
        "risk_parity": {"risk_contrib_pct": _rc(cov, rp_r)},
        "class_vol_pct": {k: round(float(math.sqrt(cov[i, i])) * 100, 1) for i, k in enumerate(RISKY)},
        "bands": band_rows,
        "trades": trades,
        "locked_holdings": [{"ticker": t, "tax_wrapper": by_ticker[t].get("tax_wrapper"), "lock_until": by_ticker[t].get("lock_until"),
                             "value_thb": round(by_ticker[t]["value_thb"], 0), "units_status": by_ticker[t].get("units_status")}
                            for t in sorted(locked)],
        "cash_after_trades_thb": round(cash_after, 0),
        "cash_yield_ref": {"bot_policy_rate_pct": float(bot) if bot is not None else None, "source": "market_factors.bot_rate"},
        "notes": ["Cash balance is not tracked in the DB; cash after trades assumes zero starting cash.",
                  f"Global sleeve uses {glob} as a placeholder; USD/THB {usdthb:.2f}. A THB global fund avoids FX costs.",
                  "Prices/covariance: yfinance daily closes, 1y; gold = GC=F x THB=X; Thai = TDEX.BK.",
                  "Phase in large changes (e.g. thirds over 3 months) to limit timing risk.",
                  "Tax-locked holdings (ThaiESG) are held at their current value and never sold/switched before lock_until; "
                  "they count toward the Thai equity class, so the other Thai positions absorb any Thai trim.",
                  "Position cap %.0f%% and sector caps from config/risk_limits.json apply." % max_pos],
        "sources": {"prices": "yfinance", "regime": "market_regime", "views": "predictions (frozen 1y)", "policy": str(POLICY_PATH.name)},
    }
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO portfolio_proposals (policy, result) VALUES ($1::jsonb, $2::jsonb)",
                           json.dumps(pol), json.dumps(result, default=str))
    return result


def _rc(cov: np.ndarray, w: np.ndarray) -> dict[str, float]:
    rc = w * (cov @ w)
    rc = rc / rc.sum()
    return {k: round(float(rc[i]) * 100, 1) for i, k in enumerate(RISKY)}


def lot_selection(ticker: str, units: float, holding: dict[str, Any], price: float, cal: dict[str, Any]) -> dict[str, Any]:
    """Tax-aware lot choice. Only an average-cost lot exists in the DB today, so the method is reported with that caveat."""
    avg = float(holding["avg_cost_price"] or 0)
    gain = (price - avg) * units
    exempt = ticker.endswith(".BK") or ticker == "SCBGOLDE"
    xd = cal.get("ex_dividend_date")
    warn = None
    if xd:
        try:
            d = date.fromisoformat(str(xd)[:10])
            days = np.busday_count(date.today(), d)
            if 0 <= days <= 10:
                warn = f"XD on {d} in {days} trading days - selling before XD forfeits the dividend"
        except ValueError:
            pass
    return {"method": "FIFO (tax-exempt Thai lot)" if exempt else "HIFO",
            "lots_available": [{"lot": "average-cost (single lot in DB)", "units": float(holding["quantity"]), "cost": avg}],
            "est_realised_gain_local": round(gain, 0), "tax": "capital gain exempt for an individual (Thai listed share / Thai mutual fund)" if exempt
            else "foreign-income rules apply if remitted", "xd_warning": warn,
            "caveat": "No per-lot purchase history in the DB; add lots to choose HIFO/FIFO precisely."}


async def latest(pool: Any) -> Optional[dict[str, Any]]:
    async with pool.acquire() as conn:
        await conn.execute(DDL)
        r = await conn.fetchrow("SELECT id, created_at, result FROM portfolio_proposals ORDER BY created_at DESC LIMIT 1")
    if not r:
        return None
    res = json.loads(r["result"]) if isinstance(r["result"], str) else r["result"]
    return {"id": r["id"], "created_at": r["created_at"].astimezone(ICT).isoformat(), **res}
