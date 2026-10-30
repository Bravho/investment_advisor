"""Professional risk layer #1 (Phase 3, added 2026-10-29).

Daily: historical + Monte Carlo VaR / expected shortfall, volatility, max drawdown,
beta to SET (TDEX.BK SET50 ETF proxy - yfinance has no ^SET.BK history),
correlation matrix (holdings + active watch list), factor exposures (Brent, USD/THB,
gold, SET, US10y), stress scenarios and a position-sizing helper.

All prices are free yfinance daily closes, converted to THB. SCBGOLDE has no
daily history feed, so its risk uses a proxy: COMEX gold (GC=F) x USD/THB
(the fund is unhedged USD gold). Results are PROVISIONAL until Tho confirms
holdings units/cost (config/risk_limits.json: holdings_confirmed).
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from market_history import SET_PROXY, download_closes

LOGGER = logging.getLogger("portfolio_engine.risk_engine")
PROJECT_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_DIR / "config" / "risk_limits.json"
FACTOR_TICKERS = {"brent": "BZ=F", "usdthb": "THB=X", "gold": "GC=F", "set": SET_PROXY, "us10y": "^TNX"}
PROXIES = {"SCBGOLDE": {"kind": "gold_thb", "note": "proxy = GC=F x THB=X (unhedged USD gold in THB)"},
           "SCB_GOLD_FUND": {"kind": "gold_thb", "note": "proxy = GC=F x THB=X"},
           # ThaiESG funds (2026-10-30): NAV history not free in bulk -> SET50 ETF proxy (Thai ESG equity,
           # overlaps SET banks/energy). Look-through holdings not available free; treated as one Thai ESG equity bucket.
           "K-TNZ-ThaiESG": {"kind": "set_proxy", "note": f"proxy = {SET_PROXY} (Thai ESG equity fund; no free look-through)"},
           "ES-SETESG-ThaiESG-A": {"kind": "set_proxy", "note": f"proxy = {SET_PROXY} (SETESG index fund; no free look-through)"},
           "TDSThaiESG-A": {"kind": "set_proxy", "note": f"proxy = {SET_PROXY} (Thai ESG dividend equity fund; no free look-through)"}}
SCENARIOS = {
    "brent_minus_30": {"label": "Brent -30%", "shocks": {"brent": -0.30}},
    "thb_plus_10": {"label": "THB +10% (USD/THB -10%)", "shocks": {"usdthb": -0.10}},
    "set_minus_20": {"label": "SET -20%", "shocks": {"set": -0.20}},
    "rate_cut": {"label": "Rate cut (US10y -50bp proxy; BoT -25bp not separately modelled)", "shocks": {"us10y": -0.50}},
}
REPLAYS = {
    "covid_2020": {"label": "2020 COVID crash replay (19 Feb - 23 Mar 2020)", "start": "2020-02-19", "end": "2020-03-23"},
    "year_2022": {"label": "2022 replay (rates/oil shock, 3 Jan - 30 Dec 2022)", "start": "2022-01-03", "end": "2022-12-30"},
}
DDL = """
CREATE TABLE IF NOT EXISTS risk_reports (
    id          SERIAL PRIMARY KEY,
    run_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    as_of       DATE NOT NULL,
    provisional BOOLEAN NOT NULL DEFAULT TRUE,
    summary     JSONB NOT NULL,
    report      JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_risk_reports_run_at ON risk_reports (run_at DESC);
"""


def load_config() -> dict[str, Any]:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("risk config unreadable (%s); using defaults", exc)
        return {"holdings_confirmed": False, "risk_budget_per_trade_pct": 1.0, "max_position_pct": 25.0,
                "max_sector_pct": 40.0, "mc_simulations": 20000, "thai_board_lot": 100,
                "lookback_days": {"cov": 252, "hist_var": 504, "drawdown": 756}, "sectors": {}}


def _is_usd_listed(t: str) -> bool:
    return not t.endswith(".BK") and t not in PROXIES and t not in FACTOR_TICKERS.values()


def _thb_prices(raw: pd.DataFrame, tickers: list[str]) -> tuple[pd.DataFrame, dict[str, str]]:
    fx = raw["THB=X"].ffill()
    out, notes = {}, {}
    for t in tickers:
        if t in PROXIES and PROXIES[t]["kind"] == "set_proxy":
            out[t] = raw[SET_PROXY].ffill()
            notes[t] = PROXIES[t]["note"]
        elif t in PROXIES:
            out[t] = raw["GC=F"].ffill() * fx
            notes[t] = PROXIES[t]["note"]
        elif t in raw.columns:
            s = raw[t]
            out[t] = s * fx if _is_usd_listed(t) else s
            if _is_usd_listed(t):
                notes[t] = "USD price converted to THB at THB=X"
    return pd.DataFrame(out), notes


def _var_es(r: np.ndarray, conf: float) -> tuple[float, float]:
    q = np.quantile(r, 1 - conf)
    tail = r[r <= q]
    return float(-q), float(-tail.mean()) if tail.size else float(-q)


def _mdd(prices: pd.Series) -> dict[str, Any]:
    s = prices.dropna()
    if len(s) < 20:
        return {"max_drawdown_pct": None}
    peak = s.cummax()
    dd = s / peak - 1
    trough = dd.idxmin()
    pk = s.loc[:trough].idxmax()
    return {"max_drawdown_pct": round(float(dd.min()) * 100, 2), "peak": str(pk.date()), "trough": str(trough.date()),
            "current_drawdown_pct": round(float(dd.iloc[-1]) * 100, 2)}


def _beta(y: pd.Series, x: pd.Series) -> Optional[float]:
    df = pd.concat([y, x], axis=1).dropna()
    if len(df) < 60 or df.iloc[:, 1].var() == 0:
        return None
    return float(df.cov().iloc[0, 1] / df.iloc[:, 1].var())


def _ols(y: pd.Series, X: pd.DataFrame) -> dict[str, Any]:
    df = pd.concat([y.rename("y"), X], axis=1).replace([np.inf, -np.inf], np.nan).dropna()
    if len(df) < 60:
        return {"n": len(df), "error": "insufficient overlapping history"}
    A = np.column_stack([np.ones(len(df)), df[X.columns].values])
    b = df["y"].values
    coef, *_ = np.linalg.lstsq(A, b, rcond=None)
    resid = b - A @ coef
    dof = max(len(df) - A.shape[1], 1)
    sigma2 = float(resid @ resid) / dof
    try:
        se = np.sqrt(np.diag(sigma2 * np.linalg.inv(A.T @ A)))
    except np.linalg.LinAlgError:
        se = np.full(A.shape[1], np.nan)
    r2 = 1 - float(resid @ resid) / float(((b - b.mean()) ** 2).sum()) if len(b) > 1 else None
    return {"n": len(df), "r2": round(r2, 3) if r2 is not None else None,
            "betas": {c: round(float(coef[i + 1]), 4) for i, c in enumerate(X.columns)},
            "t_stats": {c: (round(float(coef[i + 1] / se[i + 1]), 2) if se[i + 1] and not math.isnan(se[i + 1]) else None)
                        for i, c in enumerate(X.columns)}}


def _compute(*args: Any, **kwargs: Any) -> dict[str, Any]:
    # numpy 2.x on macOS Accelerate emits spurious matmul FP warnings; inputs are sanitised above.
    with np.errstate(all="ignore"):
        return _compute_inner(*args, **kwargs)


def _compute_inner(positions: list[dict[str, Any]], watch: list[str], cfg: dict[str, Any]) -> dict[str, Any]:
    lb = cfg.get("lookback_days") or {}
    n_cov, n_hist, n_dd = int(lb.get("cov", 252)), int(lb.get("hist_var", 504)), int(lb.get("drawdown", 756))
    held = [p["ticker"] for p in positions]
    real = [t for t in held + watch if t not in PROXIES]
    raw = download_closes(sorted(set(real) | set(FACTOR_TICKERS.values())), start="2019-06-01", ttl=3600)
    raw = raw.replace([np.inf, -np.inf], np.nan).where(raw > 0).ffill(limit=5)
    prices, notes = _thb_prices(raw, list(dict.fromkeys(held + watch)))
    total = sum(p["value_thb"] for p in positions)
    weights = pd.Series({p["ticker"]: p["value_thb"] / total for p in positions}) if total else pd.Series(dtype=float)
    hp = prices[[t for t in held if t in prices.columns]]
    hp = hp.loc[hp.dropna(how="all").index]
    rets = hp.pct_change(fill_method=None).dropna(how="all")
    missing = [t for t in held if t not in hp.columns or hp[t].dropna().empty]
    rets_full = rets.dropna()
    w = weights.reindex(rets_full.columns).fillna(0.0)
    port = rets_full @ w
    port_1y, port_2y = port.iloc[-n_cov:], port.iloc[-n_hist:]

    # VaR / ES
    var = {}
    for conf in cfg.get("var_confidence", [0.95, 0.99]):
        hv, hes = _var_es(port_2y.values, conf)
        var[f"hist_{int(conf * 100)}"] = {"var_pct": round(hv * 100, 3), "es_pct": round(hes * 100, 3),
                                          "var_thb": round(hv * total), "es_thb": round(hes * total)}
    cov = rets_full.iloc[-n_cov:].cov().values
    rng = np.random.default_rng(int(date.today().strftime("%Y%m%d")))
    sims = int(cfg.get("mc_simulations", 20000))
    try:
        draws = rng.multivariate_normal(np.zeros(len(w)), cov, size=sims, method="cholesky")
    except Exception:  # noqa: BLE001
        draws = rng.multivariate_normal(np.zeros(len(w)), cov, size=sims)
    mc_port = draws @ w.values
    # fat-tail variant: Student-t (df=4) scaled to the same covariance
    chi = rng.chisquare(4, size=sims)
    t_port = mc_port * np.sqrt(4 / chi) * math.sqrt(2 / 4)
    for conf in cfg.get("var_confidence", [0.95, 0.99]):
        mv, mes = _var_es(mc_port, conf)
        tv, tes = _var_es(t_port, conf)
        var[f"mc_normal_{int(conf * 100)}"] = {"var_pct": round(mv * 100, 3), "es_pct": round(mes * 100, 3),
                                               "var_thb": round(mv * total), "es_thb": round(mes * total)}
        var[f"mc_t4_{int(conf * 100)}"] = {"var_pct": round(tv * 100, 3), "es_pct": round(tes * 100, 3),
                                           "var_thb": round(tv * total), "es_thb": round(tes * total)}
    var["horizon"] = "1 trading day; 10-day ~= x3.16 (sqrt-time, assumes i.i.d.)"
    var["mc_simulations"] = sims

    # vol, drawdown, beta
    set_ret = prices.get(SET_PROXY, raw[SET_PROXY]).pct_change(fill_method=None)
    per_holding = {}
    for t in hp.columns:
        r = rets[t].dropna()
        per_holding[t] = {
            "weight_pct": round(float(weights.get(t, 0)) * 100, 2),
            "value_thb": round(next(p["value_thb"] for p in positions if p["ticker"] == t), 2),
            "vol_ann_pct": round(float(r.iloc[-n_cov:].std() * math.sqrt(252) * 100), 2) if len(r) > 30 else None,
            "beta_set": round(_beta(r.iloc[-n_cov:], set_ret), 3) if _beta(r.iloc[-n_cov:], set_ret) is not None else None,
            **_mdd(hp[t].iloc[-n_dd:]),
            "data_note": notes.get(t, "yfinance daily close (THB)"),
        }
    port_index = (1 + port).cumprod()
    portfolio = {
        "value_thb": round(total, 2),
        "vol_ann_pct": round(float(port_1y.std() * math.sqrt(252) * 100), 2),
        "beta_set": round(_beta(port_1y, set_ret) or float("nan"), 3),
        **_mdd(port_index.iloc[-n_dd:]),
        "observations_1y": int(len(port_1y)),
    }

    # correlation (holdings + watch list)
    universe = [t for t in list(dict.fromkeys(held + watch)) if t in prices.columns]
    cr = prices[universe].iloc[-(n_cov + 10):].pct_change(fill_method=None)
    cr = cr.loc[:, cr.notna().sum() >= 150]
    corr = cr.corr(min_periods=120).round(2)
    corr_out = {"tickers": list(corr.columns), "matrix": [[None if pd.isna(v) else float(v) for v in row] for row in corr.values]}

    # factor exposures (multivariate, 1y daily)
    fx_df = pd.DataFrame({
        "brent": raw["BZ=F"].pct_change(fill_method=None),
        "usdthb": raw["THB=X"].pct_change(fill_method=None),
        "gold": raw["GC=F"].pct_change(fill_method=None),
        "set": raw[SET_PROXY].pct_change(fill_method=None),
        "us10y": raw["^TNX"].diff(),  # yield change in percentage points
    }).iloc[-(n_cov + 5):]
    exposures = {"portfolio": _ols(port_1y, fx_df)}
    for t in hp.columns:
        exposures[t] = _ols(rets[t].iloc[-n_cov:], fx_df)
    exposures["_units"] = "beta = % move in position per 1% factor move; us10y beta = % move per +1pp yield"

    # stress: single-factor scenarios via univariate (conditional) betas
    stress = {}
    for key, sc in SCENARIOS.items():
        rows, tot = {}, 0.0
        for t in hp.columns:
            f, shock = next(iter(sc["shocks"].items()))
            b = _beta(rets[t].iloc[-n_cov:], fx_df[f])
            impact = (b or 0.0) * shock
            pnl = impact * per_holding[t]["value_thb"]
            rows[t] = {"beta": round(b, 3) if b is not None else None, "move_pct": round(impact * 100, 2), "pnl_thb": round(pnl)}
            tot += pnl
        stress[key] = {"label": sc["label"], "method": "univariate 1y beta x shock (linear)", "positions": rows,
                       "pnl_thb": round(tot), "pnl_pct": round(tot / total * 100, 2) if total else None}
    for key, rp in REPLAYS.items():
        rows, tot, gaps = {}, 0.0, []
        for t in hp.columns:
            s = hp[t].loc[rp["start"]:rp["end"]].dropna()
            basis = "actual"
            if len(s) < 5:
                # No price history in the window (e.g. SCB.BK listed 2022 as SCBX holding co).
                # Proxy: current 1y beta to SET x SET-proxy move over the window.
                ps = prices[SET_PROXY].loc[rp["start"]:rp["end"]].dropna() if SET_PROXY in prices.columns else pd.Series(dtype=float)
                b = per_holding[t].get("beta_set")
                if len(ps) < 5 or b is None:
                    gaps.append(t)
                    continue
                ret = float(ps.iloc[-1] / ps.iloc[0] - 1) * b
                basis = f"proxy: beta {b} x {SET_PROXY} (no own history in window)"
                gaps.append(f"{t} (proxied)")
            else:
                ret = float(s.iloc[-1] / s.iloc[0] - 1)
            pnl = ret * per_holding[t]["value_thb"]
            rows[t] = {"move_pct": round(ret * 100, 2), "pnl_thb": round(pnl), "basis": basis}
            tot += pnl
        stress[key] = {"label": rp["label"], "method": "actual price path replay (THB), current weights",
                       "positions": rows, "pnl_thb": round(tot), "pnl_pct": round(tot / total * 100, 2) if total else None,
                       "no_history": gaps}

    return {"portfolio": portfolio, "var": var, "per_holding": per_holding, "correlation": corr_out,
            "factor_exposures": exposures, "stress": stress, "missing_history": missing,
            "data_notes": {**notes, "SET": f"{SET_PROXY} (SET50 ETF) used as SET proxy - yfinance has no ^SET.BK history"},
            "price_as_of": str(prices.dropna(how="all").index[-1].date())}


async def _positions(pool: Any) -> list[dict[str, Any]]:
    from utils.common import latest_price, load_snapshot
    snap = load_snapshot().get("holdings", {})
    from holding_meta import is_locked, is_pending, load_attrs
    attrs = await load_attrs(pool)
    pending = [t for t, a in attrs.items() if is_pending(a)]
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT ticker, name, asset_class, quantity, avg_cost_price, currency FROM holdings "
                                "WHERE quantity > 0 OR ticker = ANY($1::text[])", pending)
    out = []
    for r in rows:
        sp = snap.get(r["ticker"], {})
        a = attrs.get(r["ticker"])
        value = sp.get("market_value_thb")
        if value is None and is_pending(a):
            value = float(a.get("amount_invested_thb") or 0)  # units pending -> carried at amount invested
        if value is None:
            value = float(await latest_price(pool, r["ticker"])) * float(r["quantity"])
        pos = {"ticker": r["ticker"], "name": r["name"], "quantity": float(r["quantity"]), "value_thb": float(value),
               "price_as_of": sp.get("price_as_of"), "price_source": sp.get("price_source")}
        if a:
            pos.update({"tax_wrapper": a.get("tax_wrapper"), "lock_until": a.get("lock_until"), "locked": is_locked(a),
                        "units_status": a.get("units_status"), "is_estimated": is_pending(a),
                        "amount_invested_thb": a.get("amount_invested_thb"), "look_through": a.get("look_through")})
            if is_pending(a):
                pos["valuation_basis"] = sp.get("valuation_basis") or "carried at amount invested; units pending confirmation"
        out.append(pos)
    return out


def thai_equity_exposure(positions: list[dict[str, Any]], cfg: dict[str, Any]) -> dict[str, Any]:
    """Thai equity share: SET-listed stocks + Thai equity funds (ThaiESG treated as one Thai ESG equity bucket)."""
    total = sum(p["value_thb"] for p in positions) or 1.0
    sectors = cfg.get("sectors") or {}
    direct = sum(p["value_thb"] for p in positions if p["ticker"].endswith(".BK"))
    funds = sum(p["value_thb"] for p in positions if sectors.get(p["ticker"]) == "thai_esg_equity")
    return {"thai_equity_thb": round(direct + funds, 2), "thai_equity_pct": round((direct + funds) / total * 100, 2),
            "direct_set_stocks_pct": round(direct / total * 100, 2), "thai_esg_funds_pct": round(funds / total * 100, 2),
            "note": "ThaiESG funds counted as Thai ESG equity (no free look-through); they very likely also hold SET "
                    "banks/energy, so true SCB/PTTEP-type exposure is somewhat higher than the direct figures."}


async def run_risk_report(pool: Any) -> dict[str, Any]:
    async with pool.acquire() as conn:
        await conn.execute(DDL)
        try:
            watch = [r["ticker"] for r in await conn.fetch("SELECT ticker FROM investment_watchlist WHERE status <> 'dropped'")]
        except Exception:  # noqa: BLE001
            watch = []
    cfg = load_config()
    positions = await _positions(pool)
    if not positions:
        raise RuntimeError("no holdings with quantity > 0")
    report = await asyncio.to_thread(_compute, positions, watch, cfg)
    provisional = not bool(cfg.get("holdings_confirmed"))
    report["provisional"] = provisional
    report["provisional_note"] = ("PROVISIONAL - holdings units/cost not yet confirmed by Tho (SCBGOLDE units in DB "
                                  "conflict with Tho's stated cost). Figures scale with position sizes.") if provisional else None
    if any(p.get("units_status") == "pending" for p in positions):
        report["provisional_note"] = ((report["provisional_note"] or "") + " ThaiESG funds: units pending confirmation - "
                                      "valued at amount invested / estimated from NAV until Tho confirms units.").strip()
    report["positions_input"] = positions
    report["limits"] = {k: cfg.get(k) for k in ("risk_budget_per_trade_pct", "max_position_pct", "max_sector_pct")}
    report["limit_breaches"] = _limit_breaches(positions, cfg)
    report["thai_equity_exposure"] = thai_equity_exposure(positions, cfg)
    report["locked_positions"] = [{"ticker": p["ticker"], "tax_wrapper": p.get("tax_wrapper"), "lock_until": p.get("lock_until"),
                                   "units_status": p.get("units_status")} for p in positions if p.get("locked")]
    report["generated_at"] = datetime.now(timezone.utc).isoformat()
    v95 = report["var"].get("hist_95", {})
    summary = {
        "value_thb": report["portfolio"]["value_thb"], "vol_ann_pct": report["portfolio"]["vol_ann_pct"],
        "beta_set": report["portfolio"]["beta_set"], "max_drawdown_pct": report["portfolio"].get("max_drawdown_pct"),
        "hist_var95_thb": v95.get("var_thb"), "hist_es95_thb": v95.get("es_thb"),
        "mc_var99_thb": report["var"].get("mc_normal_99", {}).get("var_thb"),
        "worst_stress": min(({"key": k, "label": s["label"], "pnl_thb": s["pnl_thb"], "pnl_pct": s["pnl_pct"]}
                             for k, s in report["stress"].items()), key=lambda x: x["pnl_thb"]),
        "limit_breaches": report["limit_breaches"], "provisional": provisional, "price_as_of": report["price_as_of"],
        "thai_equity_pct": report["thai_equity_exposure"]["thai_equity_pct"], "locked_positions": report["locked_positions"],
    }
    report["summary"] = summary
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO risk_reports (as_of, provisional, summary, report) VALUES ($1,$2,$3::jsonb,$4::jsonb)",
                           date.today(), provisional, json.dumps(summary, default=str), json.dumps(report, default=str))
    return report


def _limit_breaches(positions: list[dict[str, Any]], cfg: dict[str, Any]) -> list[str]:
    total = sum(p["value_thb"] for p in positions) or 1.0
    out, sectors = [], {}
    for p in positions:
        w = p["value_thb"] / total * 100
        if w > float(cfg.get("max_position_pct", 25)):
            out.append(f"{p['ticker']} {w:.1f}% > max position {cfg.get('max_position_pct')}%")
        sec = (cfg.get("sectors") or {}).get(p["ticker"], "unclassified")
        sectors[sec] = sectors.get(sec, 0) + w
    for sec, w in sectors.items():
        if w > float(cfg.get("max_sector_pct", 40)):
            out.append(f"sector {sec} {w:.1f}% > max sector {cfg.get('max_sector_pct')}%")
    return out


async def latest_risk_report(pool: Any) -> Optional[dict[str, Any]]:
    async with pool.acquire() as conn:
        await conn.execute(DDL)
        row = await conn.fetchrow("SELECT id, run_at, report FROM risk_reports ORDER BY run_at DESC LIMIT 1")
    if not row:
        return None
    rep = json.loads(row["report"]) if isinstance(row["report"], str) else row["report"]
    rep["report_id"], rep["run_at"] = row["id"], row["run_at"].isoformat()
    return rep


def position_size(ticker: str, entry: float, stop: float, portfolio_value: float, positions: list[dict[str, Any]],
                  cfg: Optional[dict[str, Any]] = None, sector: Optional[str] = None,
                  risk_pct: Optional[float] = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    if entry <= 0 or stop <= 0 or stop >= entry:
        raise ValueError("need entry > stop > 0 (long positions)")
    risk_pct = float(risk_pct if risk_pct is not None else cfg.get("risk_budget_per_trade_pct", 1.0))
    budget = portfolio_value * risk_pct / 100
    per_share = entry - stop
    shares = budget / per_share
    lot = int(cfg.get("thai_board_lot", 100)) if ticker.endswith(".BK") else 1
    max_pos_val = portfolio_value * float(cfg.get("max_position_pct", 25)) / 100
    existing = next((p["value_thb"] for p in positions if p["ticker"] == ticker), 0.0)
    sector = sector or (cfg.get("sectors") or {}).get(ticker, "unclassified")
    sec_used = sum(p["value_thb"] for p in positions if (cfg.get("sectors") or {}).get(p["ticker"], "unclassified") == sector)
    max_sec_val = portfolio_value * float(cfg.get("max_sector_pct", 40)) / 100
    cap_val = max(0.0, min(max_pos_val - existing, max_sec_val - sec_used))
    binding = "risk budget"
    if shares * entry > cap_val:
        shares, binding = cap_val / entry, ("position cap" if (max_pos_val - existing) <= (max_sec_val - sec_used) else "sector cap")
    shares = math.floor(shares / lot) * lot
    return {"ticker": ticker, "entry": entry, "stop": stop, "risk_pct_of_portfolio": risk_pct,
            "risk_budget_thb": round(budget, 2), "risk_per_share": round(per_share, 4), "shares": shares,
            "position_value": round(shares * entry, 2), "position_pct": round(shares * entry / portfolio_value * 100, 2) if portfolio_value else None,
            "loss_at_stop": round(shares * per_share, 2), "board_lot": lot, "binding_constraint": binding,
            "sector": sector, "sector_used_pct": round(sec_used / portfolio_value * 100, 2) if portfolio_value else None,
            "caps": {"max_position_pct": cfg.get("max_position_pct"), "max_sector_pct": cfg.get("max_sector_pct")},
            "note": "Prices in the instrument's currency; portfolio value in THB - convert USD entries first. Not advice."}


def render_brief_section(rep: Optional[dict[str, Any]]) -> str:
    if not rep:
        return "**Risk (engine)**\n- No risk report yet."
    s = rep.get("summary") or {}
    lines = ["**Risk (engine" + (", PROVISIONAL - holdings not confirmed" if s.get("provisional") else "") + ")**"]
    lines.append(f"- 1-day VaR95 (historical): {s.get('hist_var95_thb'):,} THB; ES95 {s.get('hist_es95_thb'):,} THB; "
                 f"MC VaR99 {s.get('mc_var99_thb'):,} THB (prices as of {s.get('price_as_of')}).")
    lines.append(f"- Volatility {s.get('vol_ann_pct')}% ann.; beta to SET {s.get('beta_set')}; max drawdown {s.get('max_drawdown_pct')}% (3y, constant weights).")
    ws = s.get("worst_stress") or {}
    if ws:
        lines.append(f"- Worst scenario: {ws.get('label')} -> {ws.get('pnl_thb'):,} THB ({ws.get('pnl_pct')}%).")
    for b in s.get("limit_breaches") or []:
        lines.append(f"- ⚠️ Limit: {b}")
    return "\n".join(lines)
