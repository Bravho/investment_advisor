"""fx_risk.py - foreign-currency (FX) rate risk layer (added 2026-10-31).

Tho: "please don't forget to include the risk of foreign currency rate changing into the analysis structure."

What it adds on top of currency_exposure.py (which held hard-coded rates/assumptions only):
  * live FX data, free sources only (yfinance: THB=X, EURTHB=X, JPYTHB=X, SGDTHB=X, DX-Y.NYB) with
    spot, 1d/5d/1m/3m/1y moves, realised vol and 1y range;
  * per-holding exposure from config/fx_exposure.json: DIRECT foreign-currency share, HEDGE ratio,
    NET direct exposure, ECONOMIC (look-through) beta assumption - plus a beta MEASURED from price
    history (holding THB return on USD/THB return, controlling for SET and, for energy, Brent);
  * portfolio FX beta, FX-only VaR (1d / 1m), FX share of portfolio variance (Euler factor split);
  * USD/THB scenarios: -10 / -5 / +5 / +10 % (negative = baht STRONGER), direct-only and economic;
  * worst / best historical 1-month USD/THB moves replayed on today's book;
  * SCBGOLDE gold-vs-FX return split (1m / 3m / 1y);
  * FX assumptions for the multi-horizon forecasts (frozen USD/THB forecasts per horizon -> FX-leg P&L);
  * open questions (unknown hedge ratios etc.) - unknowns are never guessed.

Convention everywhere: USD/THB = baht per 1 USD. UP = WEAKER baht. Advisory only - nothing is traded.
"""
from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from market_history import SET_PROXY, download_closes

LOGGER = logging.getLogger("portfolio_engine.fx_risk")
PROJECT_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_DIR / "config" / "fx_exposure.json"
CACHE_PATH = PROJECT_DIR / "data" / "fx" / "latest.json"

FX_CONVENTION = ("USD/THB = baht per 1 US dollar. UP = WEAKER baht (good for USD assets held in THB); "
                 "DOWN = STRONGER baht (hurts unhedged USD assets).")
FX_PAIRS: dict[str, dict[str, str]] = {
    "USDTHB": {"yf": "THB=X", "label": "USD/THB", "unit": "THB per USD"},
    "EURTHB": {"yf": "EURTHB=X", "label": "EUR/THB", "unit": "THB per EUR"},
    "JPYTHB": {"yf": "JPYTHB=X", "label": "JPY/THB", "unit": "THB per JPY"},
    "SGDTHB": {"yf": "SGDTHB=X", "label": "SGD/THB", "unit": "THB per SGD"},
    "DXY": {"yf": "DX-Y.NYB", "label": "US dollar index (DXY)", "unit": "index"},
}
SCENARIO_MOVES_PCT = [-10.0, -5.0, 5.0, 10.0]
ENERGY = {"PTTEP.BK", "BAFS.BK", "PTT.BK"}
Z95 = 1.6449


# ------------------------------------------------------------------ config
def load_registry() -> dict[str, Any]:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("fx_exposure.json unreadable (%s)", exc)
        return {"holdings": {}, "defaults": {}}


def exposure_for(ticker: str, reg: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    reg = reg or load_registry()
    if ticker in (reg.get("holdings") or {}):
        return {**reg["holdings"][ticker], "registry": "explicit"}
    d = reg.get("defaults") or {}
    if ticker.endswith(".BK"):
        return {**d.get("thai_listed", {}), "registry": "default thai_listed"}
    if any(c.islower() for c in ticker):  # Thai fund codes like K-TNZ-ThaiESG
        return {**d.get("thai_fif_fund", {}), "registry": "default thai_fif_fund"}
    return {**d.get("usd_listed", {}), "registry": "default usd_listed"}


# ------------------------------------------------------------------ helpers
def _r(x: Optional[float], n: int = 4) -> Optional[float]:
    return None if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))) else round(float(x), n)


def _chg(s: pd.Series, n: int) -> Optional[float]:
    s = s.dropna()
    if len(s) <= n:
        return None
    return float(s.iloc[-1] / s.iloc[-1 - n] - 1) * 100


def pair_stats(s: pd.Series) -> dict[str, Any]:
    s = s.dropna()
    if s.empty:
        return {"status": "no_data"}
    r = s.pct_change(fill_method=None).dropna()
    y = s.iloc[-252:]
    vol = lambda n: float(r.iloc[-n:].std() * math.sqrt(252) * 100) if len(r) >= n else None  # noqa: E731
    return {"last": _r(float(s.iloc[-1]), 4), "as_of": str(s.index[-1].date()),
            "chg_1d_pct": _r(_chg(s, 1), 2), "chg_5d_pct": _r(_chg(s, 5), 2), "chg_1m_pct": _r(_chg(s, 21), 2),
            "chg_3m_pct": _r(_chg(s, 63), 2), "chg_1y_pct": _r(_chg(s, 252), 2),
            "vol_1m_ann_pct": _r(vol(21), 2), "vol_3m_ann_pct": _r(vol(63), 2), "vol_1y_ann_pct": _r(vol(252), 2),
            "high_1y": _r(float(y.max()), 4), "low_1y": _r(float(y.min()), 4),
            "pct_of_1y_range": _r(float((y.iloc[-1] - y.min()) / (y.max() - y.min()) * 100) if y.max() > y.min() else None, 1)}


def _ols(y: pd.Series, X: pd.DataFrame) -> dict[str, Any]:
    df = pd.concat([y.rename("y"), X], axis=1).replace([np.inf, -np.inf], np.nan).dropna()
    if len(df) < 60:
        return {"n": int(len(df)), "error": "insufficient overlapping history"}
    A = np.column_stack([np.ones(len(df)), df[X.columns].values])
    b = df["y"].values
    coef, *_ = np.linalg.lstsq(A, b, rcond=None)
    resid = b - A @ coef
    dof = max(len(df) - A.shape[1], 1)
    s2 = float(resid @ resid) / dof
    try:
        se = np.sqrt(np.diag(s2 * np.linalg.inv(A.T @ A)))
    except np.linalg.LinAlgError:
        se = np.full(A.shape[1], np.nan)
    ss = float(((b - b.mean()) ** 2).sum())
    return {"n": int(len(df)), "r2": _r(1 - float(resid @ resid) / ss if ss else None, 3),
            "betas": {c: _r(float(coef[i + 1]), 4) for i, c in enumerate(X.columns)},
            "t": {c: (_r(float(coef[i + 1] / se[i + 1]), 2) if se[i + 1] and not math.isnan(se[i + 1]) else None)
                  for i, c in enumerate(X.columns)}}


# ------------------------------------------------------------------ core
def compute_fx_risk(positions: list[dict[str, Any]], raw: Optional[pd.DataFrame] = None,
                    fx_forecasts: Optional[dict[str, dict[str, Any]]] = None) -> dict[str, Any]:
    """Pure computation (no DB). positions: [{ticker, value_thb, ...}] as produced by risk_engine._positions."""
    with np.errstate(all="ignore"):
        return _compute(positions, raw, fx_forecasts or {})


def _compute(positions: list[dict[str, Any]], raw: Optional[pd.DataFrame], fx_fc: dict[str, dict[str, Any]]) -> dict[str, Any]:
    import risk_engine as re_mod  # lazy: risk_engine imports this module lazily too
    reg = load_registry()
    held = [p["ticker"] for p in positions]
    real = [t for t in held if t not in re_mod.PROXIES]
    need = sorted(set(real) | {v["yf"] for v in FX_PAIRS.values()} | {"GC=F", "BZ=F", SET_PROXY})
    if raw is None or any(c not in raw.columns for c in need):
        raw = download_closes(need, start="2019-06-01", ttl=3600)
    raw = raw.replace([np.inf, -np.inf], np.nan).where(raw > 0).ffill(limit=5)
    fx = raw["THB=X"].dropna()
    spot = float(fx.iloc[-1])
    fx_ret = raw["THB=X"].pct_change(fill_method=None)
    pairs = {k: {**v, **pair_stats(raw[v["yf"]])} for k, v in FX_PAIRS.items() if v["yf"] in raw.columns}

    prices, notes = re_mod._thb_prices(raw, held)
    rets = prices.pct_change(fill_method=None)
    ctrl = pd.DataFrame({"set": raw[SET_PROXY].pct_change(fill_method=None), "brent": raw["BZ=F"].pct_change(fill_method=None)})
    total = sum(float(p["value_thb"]) for p in positions) or 1.0
    lines, open_q = [], []
    for p in positions:
        t, v = p["ticker"], float(p["value_thb"])
        e = exposure_for(t, reg)
        direct = e.get("direct_foreign")
        direct_usd = None if direct is None else float(sum((direct or {}).values()))
        hedge = e.get("hedge_ratio")
        if direct_usd is None:
            open_q.append(f"{t}: direct foreign-currency share unknown ({e.get('hedge_note') or 'check factsheet'})")
        elif direct_usd > 0 and hedge is None:
            open_q.append(f"{t}: hedge ratio unknown - modelled as UNHEDGED (worst case for a stronger baht)")
        net_direct = None if direct_usd is None else direct_usd * (1 - float(hedge if hedge is not None else 0.0))
        meas = None
        if t in rets.columns and rets[t].dropna().shape[0] > 120:
            # TOTAL beta (USD/THB only): how the position typically moves when the baht moves, including the
            # usual co-movement of SET flows / oil. This is the one used for FX risk (consistent across holdings).
            meas = _ols(rets[t].iloc[-504:], pd.DataFrame({"usdthb": fx_ret}).iloc[-504:])
            set_proxied = (re_mod.PROXIES.get(t) or {}).get("kind") == "set_proxy"
            if not set_proxied:  # PARTIAL beta (diagnostic): FX effect holding SET (and Brent for energy) constant
                X = pd.DataFrame({"usdthb": fx_ret, "set": ctrl["set"]})
                if t in ENERGY:
                    X["brent"] = ctrl["brent"]
                part = _ols(rets[t].iloc[-504:], X.iloc[-504:])
                meas["partial"] = {"beta": (part.get("betas") or {}).get("usdthb"), "t": (part.get("t") or {}).get("usdthb"),
                                   "controls": [c for c in X.columns if c != "usdthb"], "r2": part.get("r2")}
            meas["window"] = "2y daily"
            meas["data"] = notes.get(t, "yfinance daily close (THB)")
        mb, mt = ((meas or {}).get("betas") or {}).get("usdthb"), ((meas or {}).get("t") or {}).get("usdthb")
        assumed = e.get("economic_beta_assumed")
        proxied = t in re_mod.PROXIES
        ptxt = " on proxy " + str((re_mod.PROXIES.get(t) or {}).get("kind")) if proxied else ""
        if e.get("structural") and assumed is not None:
            used, basis = float(assumed), "structural (instrument construction)"
        elif mb is not None and mt is not None and abs(mt) >= 2:
            used, basis = float(mb), f"measured total beta (t={mt}){ptxt}"
        elif assumed is not None:
            used, basis = float(assumed), "assumed (measured beta not significant)" if mb is not None else "assumed"
        elif mb is not None:
            used, basis = float(mb), f"measured, weak (t={mt}){ptxt}"
        else:
            used, basis = 0.0, "unknown -> 0"
            open_q.append(f"{t}: no FX beta (no assumption and no usable history)")
        if assumed is not None and mb is not None and not e.get("structural") and mt is not None and abs(mt) < 2 \
                and (mb > 0) != (float(assumed) > 0):
            open_q.append(f"{t}: assumed FX beta {float(assumed):+.2f} is NOT supported by price history "
                          f"(measured {mb:+.2f}, t={mt}); assumption kept but should be reviewed")
        lines.append({"ticker": t, "value_thb": round(v, 0), "weight_pct": round(v / total * 100, 2),
                      "listing_currency": e.get("listing_currency"), "direct_foreign_share": direct_usd,
                      "hedge_ratio": hedge, "hedge_note": e.get("hedge_note"), "net_direct_fx_share": _r(net_direct, 3),
                      "economic_usd_revenue_share": e.get("economic_usd_revenue_share"),
                      "beta_assumed": assumed, "beta_measured": mb, "beta_measured_t": mt,
                      "beta_partial": ((meas or {}).get("partial") or {}).get("beta"), "beta_partial_t": ((meas or {}).get("partial") or {}).get("t"),
                      "beta_used": round(used, 3),
                      "beta_basis": basis, "confidence": e.get("confidence"), "basis": e.get("basis"),
                      "registry": e.get("registry"), "source": e.get("source"), "measured": meas,
                      "fx_value_at_risk_per_1pct_thb": round(v * used / 100, 0)})

    port_beta = sum(l["weight_pct"] / 100 * l["beta_used"] for l in lines)
    net_direct_thb = sum(l["value_thb"] * (l["net_direct_fx_share"] or 0) for l in lines)
    unknown_direct_thb = sum(l["value_thb"] for l in lines if l["direct_foreign_share"] is None)
    sd = float(fx_ret.iloc[-252:].std())
    fx_var = {"usdthb_daily_vol_pct": round(sd * 100, 3),
              "var95_1d_thb": round(Z95 * sd * abs(port_beta) * total), "var95_1m_thb": round(Z95 * sd * math.sqrt(21) * abs(port_beta) * total),
              "var95_1d_pct": round(Z95 * sd * abs(port_beta) * 100, 3), "var95_1m_pct": round(Z95 * sd * math.sqrt(21) * abs(port_beta) * 100, 2),
              "method": "parametric: 1.645 x USD/THB 1y daily vol x |portfolio FX beta| x value (FX leg only; 1m = sqrt(21) scaling)"}

    # FX share of portfolio variance (Euler factor contribution, 1y daily)
    w = pd.Series({l["ticker"]: l["weight_pct"] / 100 for l in lines})
    rr = rets[[c for c in w.index if c in rets.columns]].iloc[-260:].dropna()
    var_split = {"error": "insufficient history"}
    if len(rr) > 120:
        port = rr @ w.reindex(rr.columns).fillna(0)
        F = pd.DataFrame({"usdthb": fx_ret, "set": ctrl["set"], "gold": raw["GC=F"].pct_change(fill_method=None),
                          "brent": ctrl["brent"]}).reindex(port.index)
        o = _ols(port, F)
        if "betas" in o:
            vp = float(port.var())
            df = pd.concat([port.rename("p"), F], axis=1).dropna()
            contrib = {f: _r(float(o["betas"][f]) * float(df[f].cov(df["p"])) / vp * 100, 1) for f in F.columns}
            var_split = {"share_of_variance_pct": contrib, "residual_pct": _r(100 - (o["r2"] or 0) * 100, 1),
                         "r2": o["r2"], "betas": o["betas"], "t": o["t"], "n": o["n"],
                         "method": "portfolio daily return regressed on USD/THB, SET50(TDEX), gold, Brent; contribution_i = beta_i*cov(f_i,r_p)/var(r_p)"}

    # scenarios
    scen = []
    for m in SCENARIO_MOVES_PCT:
        rows = [{"ticker": l["ticker"], "pnl_thb": round(l["value_thb"] * l["beta_used"] * m / 100),
                 "direct_pnl_thb": round(l["value_thb"] * (l["net_direct_fx_share"] or 0) * m / 100)} for l in lines]
        econ, dirc = sum(r["pnl_thb"] for r in rows), sum(r["direct_pnl_thb"] for r in rows)
        scen.append({"usdthb_move_pct": m, "usdthb_level": round(spot * (1 + m / 100), 3),
                     "label": f"USD/THB {m:+.0f}% ({'baht STRONGER' if m < 0 else 'baht WEAKER'}) -> {spot * (1 + m / 100):.2f}",
                     "economic_pnl_thb": econ, "economic_pnl_pct": round(econ / total * 100, 2),
                     "direct_only_pnl_thb": dirc, "direct_only_pnl_pct": round(dirc / total * 100, 2), "positions": rows})

    # historical 1-month USD/THB extremes replayed on today's book (FX leg only)
    m21 = (fx / fx.shift(21) - 1).dropna()
    hist = {}
    if len(m21):
        for k, idx in (("worst_baht_strengthening_1m", m21.idxmin()), ("worst_baht_weakening_1m", m21.idxmax())):
            mv = float(m21.loc[idx])
            hist[k] = {"end_date": str(idx.date()), "usdthb_move_pct": round(mv * 100, 2),
                       "fx_leg_pnl_thb_on_today_book": round(total * port_beta * mv),
                       "pct": round(port_beta * mv * 100, 2)}
        hist["window"] = f"{fx.index[0].date()} .. {fx.index[-1].date()} (yfinance THB=X)"

    # gold vs FX split for SCBGOLDE (unhedged gold feeder)
    gold_split = {}
    if "SCBGOLDE" in held:
        import currency_exposure as ce
        g = raw["GC=F"].dropna()
        for lab, n in (("1m", 21), ("3m", 63), ("1y", 252)):
            if len(g) > n and len(fx) > n:
                a = ce.fx_attribution(float(g.iloc[-1] / g.iloc[-1 - n] - 1) * 100, float(fx.iloc[-1 - n]), float(fx.iloc[-1]), f"SCBGOLDE {lab}")
                gold_split[lab] = {k: a[k] for k in ("asset_return_usd_pct", "fx_return_pct", "cross_term_pct", "total_return_thb_pct", "fx_share_of_total_pct", "reading")}

    # FX assumptions for the multi-horizon forecasts
    fc_rows = []
    for h in ("3d", "1m", "3m", "6m", "1y"):
        f = fx_fc.get(h)
        if not f:
            fc_rows.append({"horizon": h, "status": "no frozen USD/THB forecast"})
            continue
        med, lo, hi = f.get("median_price"), f.get("band80_low"), f.get("band80_high")
        mv = (med / spot - 1) if med else None
        fc_rows.append({"horizon": h, "usdthb_median": _r(med, 3), "usdthb_80pct": [_r(lo, 3), _r(hi, 3)], "p_up": f.get("p_up"),
                        "confidence": f.get("confidence"), "made_at": f.get("made_at"), "target_date": f.get("target_date"),
                        "fx_leg_pnl_at_median_thb": round(total * port_beta * mv) if mv is not None else None,
                        "fx_leg_pnl_80pct_thb": [round(total * port_beta * (lo / spot - 1)) if lo else None,
                                                 round(total * port_beta * (hi / spot - 1)) if hi else None]})

    usd = pairs.get("USDTHB", {})
    summary = {"usdthb": usd.get("last"), "usdthb_as_of": usd.get("as_of"), "usdthb_chg_1m_pct": usd.get("chg_1m_pct"),
               "usdthb_vol_3m_ann_pct": usd.get("vol_3m_ann_pct"), "portfolio_fx_beta": round(port_beta, 3),
               "net_direct_fx_thb": round(net_direct_thb), "net_direct_fx_pct": round(net_direct_thb / total * 100, 2),
               "unknown_direct_thb": round(unknown_direct_thb), "fx_var95_1m_thb": fx_var["var95_1m_thb"],
               "thb_plus10_pnl_thb": next(s["economic_pnl_thb"] for s in scen if s["usdthb_move_pct"] == -10.0),
               "thb_minus10_pnl_thb": next(s["economic_pnl_thb"] for s in scen if s["usdthb_move_pct"] == 10.0),
               "fx_share_of_variance_pct": (var_split.get("share_of_variance_pct") or {}).get("usdthb"),
               "open_questions": len(open_q)}
    out = {"generated_at": datetime.now(timezone.utc).isoformat(), "fx_convention": FX_CONVENTION, "spot_usdthb": spot,
           "pairs": pairs, "portfolio_value_thb": round(total), "positions": lines, "portfolio_fx_beta": round(port_beta, 3),
           "fx_var": fx_var, "variance_split": var_split, "scenarios": scen, "historical_1m_extremes": hist,
           "scbgolde_gold_vs_fx": gold_split, "forecast_fx_assumptions": fc_rows, "open_questions": open_q,
           "summary": summary, "reading": _reading(summary, lines),
           "caveats": ["Beta used = structural for instruments priced in USD (SCBGOLDE); otherwise the MEASURED total beta (USD/THB only, 2y daily) when |t|>=2, else the registry assumption. Partial betas (holding SET/Brent constant) are shown as diagnostics.",
                       "Thai equities typically FALL when the baht weakens (foreign outflows), so Thai stocks/ThaiESG funds partly offset the USD-linked gold fund and PTTEP.",
                       "ThaiESG funds have no free look-through and no daily NAV history: their FX link is measured on the SET50 proxy (TDEX) only.",
                       "Scenarios move USD/THB alone with everything else held constant; in reality oil, SET flows and gold move with it.",
                       "Units for ThaiESG funds are pending (valued at amount invested) and holdings are not yet confirmed - figures are provisional."],
           "sources": {"fx": "yfinance (free): " + ", ".join(v["yf"] for v in FX_PAIRS.values()), "registry": str(CONFIG_PATH.relative_to(PROJECT_DIR)),
                       "prices": "yfinance daily closes; SCBGOLDE = GC=F x THB=X proxy; ThaiESG = TDEX proxy"},
           "advisory_only": True}
    return out


def _reading(s: dict[str, Any], lines: list[dict[str, Any]]) -> list[str]:
    b = s["portfolio_fx_beta"]
    top = sorted(lines, key=lambda l: -abs(l["value_thb"] * l["beta_used"]))[:3]
    r = [f"USD/THB {s['usdthb']} (as of {s['usdthb_as_of']}; 1m {s['usdthb_chg_1m_pct']:+.2f}%, 3m vol {s['usdthb_vol_3m_ann_pct']}% ann.)."
         if s.get("usdthb") is not None and s.get("usdthb_chg_1m_pct") is not None else "USD/THB unavailable.",
         f"Portfolio FX beta {b:+.2f}: a 1% weaker baht changes the book by about {b:+.2f}% (positive = book gains when the baht weakens).",
         f"Net direct (unhedged) foreign-currency exposure {s['net_direct_fx_thb']:,} THB ({s['net_direct_fx_pct']}%); "
         f"{s['unknown_direct_thb']:,} THB has unknown direct exposure (ThaiESG funds, expected ~0).",
         f"Baht 10% STRONGER: {s['thb_plus10_pnl_thb']:+,} THB; baht 10% WEAKER: {s['thb_minus10_pnl_thb']:+,} THB (FX leg only).",
         f"FX-only VaR95 over 1 month ~{s['fx_var95_1m_thb']:,} THB.",
         "Biggest FX drivers: " + "; ".join(f"{l['ticker']} beta {l['beta_used']:+.2f} ({l['beta_basis']})" for l in top) + "."]
    if s.get("fx_share_of_variance_pct") is not None:
        v = s["fx_share_of_variance_pct"]
        r.append(f"USD/THB's contribution to daily portfolio variance (1y) is {v:+.1f}%"
                 + (" - it slightly DIVERSIFIES the book" if v < 0 else "") + "; most day-to-day risk comes from Thai equities.")
    return r


# ------------------------------------------------------------------ attribution helper
def attribution_fx_leg(px: pd.DataFrame, values: dict[str, float],
                       windows: Optional[dict[str, int]] = None) -> dict[str, Any]:
    """Approximate FX contribution per holding over trailing windows: weight x FX beta x USD/THB move.
    Betas come from the latest fx_risk report (beta_used) or, failing that, the registry assumption."""
    windows = windows or {"1m": 21, "3m": 63, "1y": 252}
    if "THB=X" not in px.columns:
        return {"error": "no USD/THB series"}
    fx = px["THB=X"].dropna()
    cached = {l["ticker"]: l for l in ((latest_cached() or {}).get("positions") or [])}
    reg = load_registry()
    total = sum(values.values()) or 1.0
    betas = {}
    for t in values:
        if t in cached:
            betas[t] = (float(cached[t]["beta_used"]), cached[t]["beta_basis"])
        else:
            a = exposure_for(t, reg).get("economic_beta_assumed")
            betas[t] = (float(a), "registry assumption") if a is not None else (0.0, "unknown -> 0")
    out: dict[str, Any] = {"fx_convention": FX_CONVENTION, "betas": {t: {"beta": b, "basis": k} for t, (b, k) in betas.items()}, "windows": {}}
    for lab, n in windows.items():
        if len(fx) <= n:
            continue
        mv = float(fx.iloc[-1] / fx.iloc[-1 - n] - 1)
        rows = {t: {"weight_pct": round(v / total * 100, 2), "fx_contrib_pct": round(v / total * betas[t][0] * mv * 100, 3),
                    "fx_contrib_thb": round(v * betas[t][0] * mv)} for t, v in values.items()}
        out["windows"][lab] = {"usdthb_start": round(float(fx.iloc[-1 - n]), 4), "usdthb_end": round(float(fx.iloc[-1]), 4),
                               "usdthb_move_pct": round(mv * 100, 2), "positions": rows,
                               "portfolio_fx_contrib_pct": round(sum(r["fx_contrib_pct"] for r in rows.values()), 3),
                               "portfolio_fx_contrib_thb": sum(r["fx_contrib_thb"] for r in rows.values())}
    out["method"] = "current weights x FX beta x trailing USD/THB move (linear approximation; complements the Brinson currency effect)"
    return out


# ------------------------------------------------------------------ DB / service glue
async def fx_forecasts(pool: Any) -> dict[str, dict[str, Any]]:
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT DISTINCT ON (horizon) horizon, median_price, band80_low, band80_high, p_up, confidence, made_at, target_date
                   FROM predictions WHERE subject='THB=X' AND source='live' ORDER BY horizon, made_at DESC""")
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("fx forecasts unavailable: %s", exc)
        return {}
    return {r["horizon"]: {"median_price": float(r["median_price"]) if r["median_price"] is not None else None,
                           "band80_low": float(r["band80_low"]) if r["band80_low"] is not None else None,
                           "band80_high": float(r["band80_high"]) if r["band80_high"] is not None else None,
                           "p_up": float(r["p_up"]) if r["p_up"] is not None else None,
                           "confidence": float(r["confidence"]) if r["confidence"] is not None else None,
                           "made_at": r["made_at"].isoformat(), "target_date": str(r["target_date"])} for r in rows}


async def run_fx_risk(pool: Any, positions: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
    import asyncio
    import risk_engine as re_mod
    positions = positions or await re_mod._positions(pool)
    fc = await fx_forecasts(pool)
    rep = await asyncio.to_thread(compute_fx_risk, positions, None, fc)
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(rep, default=str, ensure_ascii=False), encoding="utf-8")
    except Exception:  # noqa: BLE001
        LOGGER.exception("fx cache write failed")
    return rep


def latest_cached() -> Optional[dict[str, Any]]:
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def advisor_context(rep: Optional[dict[str, Any]]) -> str:
    if not rep:
        return "=== FX RISK ===\n  FX risk report unavailable - do not quote FX numbers."
    s = rep.get("summary") or {}
    lines = [f"=== FX (CURRENCY) RISK (engine, generated {str(rep.get('generated_at'))[:16]}Z; {FX_CONVENTION}) ==="]
    lines += [f"  - {x}" for x in rep.get("reading") or []]
    for l in rep.get("positions") or []:
        h = "unknown" if l["hedge_ratio"] is None else f"{l['hedge_ratio']:.0%}"
        d = "unknown" if l["direct_foreign_share"] is None else f"{l['direct_foreign_share']:.0%}"
        lines.append(f"  - {l['ticker']}: direct foreign {d}, hedged {h}, FX beta used {l['beta_used']:+.2f} ({l['beta_basis']})")
    for f in rep.get("forecast_fx_assumptions") or []:
        if f.get("usdthb_median"):
            lines.append(f"  - FX assumption {f['horizon']}: USD/THB median {f['usdthb_median']} (80% {f['usdthb_80pct'][0]}-{f['usdthb_80pct'][1]}), "
                         f"FX-leg P&L at median {f['fx_leg_pnl_at_median_thb']:+,} THB")
    if rep.get("open_questions"):
        lines.append("  - Open (unknown, do not guess): " + "; ".join(rep["open_questions"]))
    lines.append("  RULE: when discussing risk, returns, gold, PTTEP, global/US ideas or forecasts, mention the FX (USD/THB) effect using ONLY these numbers.")
    return "\n".join(lines)


def render_brief_section(rep: Optional[dict[str, Any]]) -> str:
    if not rep:
        return "**FX risk**\n- No FX risk report yet."
    return "**FX risk (USD/THB; up = weaker baht)**\n" + "\n".join(f"- {x}" for x in (rep.get("reading") or [])[:5])


if __name__ == "__main__":  # pragma: no cover
    import sys
    demo = [{"ticker": "PTTEP.BK", "value_thb": 160000.0}, {"ticker": "SCB.BK", "value_thb": 180000.0},
            {"ticker": "SCBGOLDE", "value_thb": 105000.0}, {"ticker": "K-TNZ-ThaiESG", "value_thb": 100000.0}]
    json.dump(compute_fx_risk(demo)["summary"], sys.stdout, indent=2, default=str)
