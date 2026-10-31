"""Trade plans, pre-trade checklist, paper-trading ledger and trade journal (Phase 4, 2026-10-30).

Engine proposals are stored with status 'proposed'. They NEVER drive LINE alerts:
alerts only use the entry zone on investment_watchlist, which is copied there
only when Tho approves a plan (PATCH /trade-plans/{id} status=approved).

Proposal method (every input stored with source + date):
  - ATR(14) from daily OHLC                        -> stop distance (1.5 x ATR below zone)
  - swing-low supports / SMA50 / SMA200            -> entry zone
  - swing-high resistance / 52w high / analyst mean target (free Yahoo consensus) -> target
  - valuation vs history (dividend yield vs 5y avg, forward vs trailing P/E, P/B)
  - reward:risk must be >= 2.0 or the plan is marked not viable.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

import numpy as np
import pandas as pd

from market_history import SET_PROXY, download_closes, download_ohlc
from fundamentals import get_fundamentals

LOGGER = logging.getLogger("portfolio_engine.trade_plans")
MIN_RR = 2.0
PLAN_EXPIRY_DAYS = 60
COMMISSION_TH = 0.00157   # online SET commission per side
VAT = 0.07                # VAT on commission
SLIPPAGE = 0.0010         # per side
US_COMMISSION = 0.0015    # offshore broker commission per side (assumption, verify)
FX_SPREAD = 0.0025        # THB<->USD conversion spread per side (assumption, verify)

DDL = """
CREATE TABLE IF NOT EXISTS trade_plans (
    id             SERIAL PRIMARY KEY,
    ticker         VARCHAR(30) NOT NULL,
    source         VARCHAR(20) NOT NULL DEFAULT 'engine',
    status         VARCHAR(20) NOT NULL DEFAULT 'proposed'
                   CHECK (status IN ('proposed','approved','rejected','open','closed','expired','cancelled','superseded')),
    viable         BOOLEAN NOT NULL DEFAULT TRUE,
    side           VARCHAR(5) NOT NULL DEFAULT 'long',
    currency       VARCHAR(10),
    last_price     NUMERIC(18,6),
    entry_low      NUMERIC(18,6),
    entry_high     NUMERIC(18,6),
    stop           NUMERIC(18,6),
    target         NUMERIC(18,6),
    rr             NUMERIC(8,3),
    atr            NUMERIC(18,6),
    inputs         JSONB NOT NULL DEFAULT '{}'::jsonb,
    rationale      TEXT,
    size           JSONB DEFAULT '{}'::jsonb,
    catalyst       TEXT,
    expiry         DATE,
    checklist      JSONB DEFAULT '[]'::jsonb,
    checklist_pass BOOLEAN,
    review_note    TEXT,
    override_reason TEXT,
    reviewed_at    TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE trade_plans ADD COLUMN IF NOT EXISTS override_reason TEXT;
CREATE INDEX IF NOT EXISTS idx_trade_plans_ticker_status ON trade_plans (ticker, status);
CREATE TABLE IF NOT EXISTS paper_trades (
    id           SERIAL PRIMARY KEY,
    plan_id      INTEGER NOT NULL REFERENCES trade_plans(id),
    ticker       VARCHAR(30) NOT NULL,
    status       VARCHAR(20) NOT NULL DEFAULT 'waiting' CHECK (status IN ('waiting','open','closed','expired')),
    qty          NUMERIC(18,4),
    entry_date   DATE,
    entry_price  NUMERIC(18,6),
    exit_date    DATE,
    exit_price   NUMERIC(18,6),
    exit_reason  VARCHAR(30),
    costs        NUMERIC(18,4),
    gross_pnl    NUMERIC(18,4),
    net_pnl      NUMERIC(18,4),
    r_multiple   NUMERIC(10,3),
    currency     VARCHAR(10),
    last_checked DATE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (plan_id)
);
CREATE TABLE IF NOT EXISTS trade_plan_audit (
    id              BIGSERIAL PRIMARY KEY,
    plan_id         INTEGER NOT NULL,
    ticker          VARCHAR(30),
    action          VARCHAR(30) NOT NULL,
    by_override     BOOLEAN NOT NULL DEFAULT false,
    override_reason TEXT,
    checklist_pass  BOOLEAN,
    note            TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_trade_plan_audit_plan ON trade_plan_audit (plan_id, created_at DESC);
CREATE TABLE IF NOT EXISTS trade_journal (
    id               SERIAL PRIMARY KEY,
    plan_id          INTEGER REFERENCES trade_plans(id),
    ticker           VARCHAR(30) NOT NULL,
    side             VARCHAR(5) NOT NULL DEFAULT 'long',
    opened_at        DATE,
    entry_price      NUMERIC(18,6),
    qty              NUMERIC(18,4),
    fees             NUMERIC(18,4),
    closed_at        DATE,
    exit_price       NUMERIC(18,6),
    pnl              NUMERIC(18,4),
    r_multiple       NUMERIC(10,3),
    setup            TEXT,
    thesis           TEXT,
    followed_plan    BOOLEAN,
    exit_reason      TEXT,
    what_went_well   TEXT,
    what_went_wrong  TEXT,
    lessons          TEXT,
    emotion          TEXT,
    grade            VARCHAR(2),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


async def ensure_tables(pool: Any) -> None:
    async with pool.acquire() as conn:
        await conn.execute(DDL)


def _f(v: Any) -> Optional[float]:
    try:
        x = float(v)
        return None if math.isnan(x) or math.isinf(x) else x
    except (TypeError, ValueError):
        return None


def atr(df: pd.DataFrame, n: int = 14) -> Optional[float]:
    if len(df) < n + 2:
        return None
    h, l, c = df["High"], df["Low"], df["Close"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return float(tr.ewm(alpha=1 / n, adjust=False).mean().iloc[-1])


def swing_points(series: pd.Series, window: int = 5, kind: str = "low") -> list[tuple[pd.Timestamp, float]]:
    s = series.dropna()
    pts = []
    for i in range(window, len(s) - window):
        seg = s.iloc[i - window:i + window + 1]
        v = s.iloc[i]
        if (kind == "low" and v == seg.min()) or (kind == "high" and v == seg.max()):
            pts.append((s.index[i], float(v)))
    return pts


def valuation_view(info: dict[str, Any]) -> dict[str, Any]:
    dy, dy5 = _f(info.get("dividendYield")), _f(info.get("fiveYearAvgDividendYield"))
    tpe, fpe, pb = _f(info.get("trailingPE")), _f(info.get("forwardPE")), _f(info.get("priceToBook"))
    points, notes = 0, []
    if dy is not None and dy5:
        rel = dy / dy5 - 1
        notes.append(f"div yield {dy:.2f}% vs 5y avg {dy5:.2f}% ({rel:+.0%})")
        points += 1 if rel > 0.10 else -1 if rel < -0.10 else 0
    if tpe and fpe:
        notes.append(f"P/E {tpe:.1f} trailing -> {fpe:.1f} forward")
        points += 1 if fpe < tpe * 0.9 else -1 if fpe > tpe * 1.1 else 0
    if pb is not None:
        notes.append(f"P/B {pb:.2f}")
    verdict = "cheap vs own history" if points >= 1 else "rich vs own history" if points <= -1 else "fair / mixed"
    return {"verdict": verdict, "points": points, "notes": notes,
            "caveat": "Yahoo snapshot; no point-in-time P/E history available free - yield vs 5y avg is the historical anchor"}


def propose_for(ticker: str, ohlc: pd.DataFrame, fund: dict[str, Any]) -> dict[str, Any]:
    info = (fund or {}).get("info") or {}
    retrieved = (fund or {}).get("retrieved_at")
    df = ohlc.dropna()
    close = df["Close"]
    price = float(close.iloc[-1])
    px_date = str(df.index[-1].date())
    a = atr(df)
    inputs: dict[str, Any] = {
        "price": {"value": round(price, 4), "source": "yfinance daily close", "as_of": px_date},
        "atr14": {"value": round(a, 4) if a else None, "source": "computed from yfinance OHLC (Wilder 14)", "as_of": px_date},
    }
    if not a or len(df) < 120:
        return {"viable": False, "reason": "insufficient price history for ATR/supports", "inputs": inputs, "last_price": price}
    year = df.iloc[-252:]
    sma50, sma200 = float(close.iloc[-50:].mean()), float(close.iloc[-200:].mean()) if len(close) >= 200 else None
    lows = [p for p in swing_points(year["Low"], 5, "low") if p[1] < price]
    highs = [p for p in swing_points(year["High"], 5, "high") if p[1] > price]
    cands = [(v, f"swing low {d.date()}") for d, v in lows]
    cands += [(sma50, "SMA50")] if sma50 < price else []
    cands += [(sma200, "SMA200")] if sma200 and sma200 < price else []
    # nearest support within 3 ATR below price; otherwise the deepest one within 12%
    near = sorted([c for c in cands if price - c[0] <= 3 * a], key=lambda c: -c[0])
    support = near[0] if near else (sorted([c for c in cands if c[0] >= price * 0.88], key=lambda c: -c[0]) or [None])[0]
    inputs.update({
        "sma50": {"value": round(sma50, 4), "source": "computed", "as_of": px_date},
        "sma200": {"value": round(sma200, 4) if sma200 else None, "source": "computed", "as_of": px_date},
        "high_52w": {"value": round(float(year["High"].max()), 4), "source": "yfinance OHLC", "as_of": px_date},
        "low_52w": {"value": round(float(year["Low"].min()), 4), "source": "yfinance OHLC", "as_of": px_date},
    })
    val = valuation_view(info)
    inputs["valuation"] = {"value": val, "source": "Yahoo Finance fundamentals (free)", "as_of": (retrieved or "")[:10]}
    tgt_mean, n_an = _f(info.get("targetMeanPrice")), _f(info.get("numberOfAnalystOpinions"))
    inputs["analyst_target_mean"] = {"value": tgt_mean, "analysts": n_an, "low": _f(info.get("targetLowPrice")),
                                     "high": _f(info.get("targetHighPrice")), "source": "Yahoo Finance analyst consensus (free)",
                                     "as_of": (retrieved or "")[:10]}
    if support is None:
        return {"viable": False, "reason": "no support level within 12% below price (falling knife / at lows)",
                "inputs": inputs, "last_price": price, "atr": a}
    s_val, s_label = support
    inputs["support"] = {"value": round(s_val, 4), "label": s_label, "source": "computed from yfinance OHLC", "as_of": px_date}
    entry_low = s_val
    entry_high = min(price, s_val + 0.5 * a)
    if val["points"] <= -1:  # rich vs own history -> demand a deeper entry
        entry_high = min(entry_high, s_val + 0.25 * a)
    stop = entry_low - 1.5 * a
    entry_mid = (entry_low + entry_high) / 2
    risk = entry_mid - stop
    res = sorted(v for _, v in highs if v > entry_mid)
    tgt_cands = []
    if tgt_mean and (n_an or 0) >= 3:
        tgt_cands.append((tgt_mean, "analyst mean target"))
    if res:
        # first resistance that offers >= 2R, else the highest swing high
        r2 = [v for v in res if (v - entry_mid) >= MIN_RR * risk]
        tgt_cands.append(((r2[0] if r2 else res[-1]), "swing-high resistance"))
    tgt_cands.append((float(year["High"].max()), "52-week high"))
    # conservative: the lowest candidate that still clears 2R; else the best available
    ok = sorted([c for c in tgt_cands if (c[0] - entry_mid) >= MIN_RR * risk], key=lambda c: c[0])
    target, t_label = ok[0] if ok else max(tgt_cands, key=lambda c: c[0])
    rr = (target - entry_mid) / risk if risk > 0 else 0
    inputs["target_basis"] = {"value": round(target, 4), "label": t_label, "candidates": [(round(v, 4), l) for v, l in tgt_cands]}
    viable = rr >= MIN_RR and target > entry_high
    rationale = (f"Entry {entry_low:.4g}-{entry_high:.4g} at {s_label} support; stop {stop:.4g} = zone low - 1.5xATR({a:.3g}); "
                 f"target {target:.4g} ({t_label}); R:R {rr:.2f}. Valuation: {val['verdict']} ({'; '.join(val['notes'])}).")
    if not viable:
        rationale += f" NOT VIABLE: reward/risk {rr:.2f} < {MIN_RR}."
    return {"viable": bool(viable), "entry_low": entry_low, "entry_high": entry_high, "stop": stop, "target": target,
            "rr": rr, "atr": a, "last_price": price, "inputs": inputs, "rationale": rationale,
            "reason": None if viable else f"R:R {rr:.2f} < {MIN_RR}"}


async def generate_proposals(pool: Any) -> dict[str, Any]:
    await ensure_tables(pool)
    async with pool.acquire() as conn:
        items = [dict(r) for r in await conn.fetch(
            "SELECT ticker, currency FROM investment_watchlist WHERE status <> 'dropped' ORDER BY ticker")]
    tickers = [i["ticker"] for i in items]
    ohlc = await asyncio.to_thread(download_ohlc, tickers, "2y")
    funds = await get_fundamentals(pool, tickers)
    made, viable = 0, 0
    for it in items:
        t = it["ticker"]
        if t not in ohlc:
            LOGGER.warning("no OHLC for %s", t)
            continue
        p = propose_for(t, ohlc[t], funds.get(t, {}))
        cal = (funds.get(t) or {}).get("calendar") or {}
        today_s = date.today().isoformat()
        e_future = [d for d in (cal.get("earnings_dates") or []) if d[:10] >= today_s]
        xd = cal.get("ex_dividend_date")
        catalyst = "; ".join(filter(None, [
            ("earnings " + ", ".join(e_future)) if e_future else None,
            (f"XD {xd}" if xd and xd[:10] >= today_s else (f"last XD {xd[:10]}" if xd else None))])) or None
        if catalyst:
            catalyst += " (Yahoo calendar, retrieved " + str((funds.get(t) or {}).get("retrieved_at", ""))[:10] + ")"
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("UPDATE trade_plans SET status='superseded', updated_at=now() WHERE ticker=$1 AND source='engine' AND status='proposed'", t)
                await conn.execute(
                    """INSERT INTO trade_plans (ticker, source, status, viable, currency, last_price, entry_low, entry_high, stop, target, rr, atr,
                           inputs, rationale, catalyst, expiry)
                       VALUES ($1,'engine','proposed',$2,$3,$4,$5,$6,$7,$8,$9,$10,$11::jsonb,$12,$13,$14)""",
                    t, p["viable"], it["currency"], p.get("last_price"), p.get("entry_low"), p.get("entry_high"), p.get("stop"),
                    p.get("target"), p.get("rr"), p.get("atr"), json.dumps(p["inputs"], default=str),
                    p.get("rationale") or p.get("reason"), catalyst, date.today() + timedelta(days=PLAN_EXPIRY_DAYS))
        made += 1
        viable += int(p["viable"])
    await refresh_checklists(pool, statuses=("proposed", "approved"))
    return {"proposed": made, "viable": viable}


# ------------------------------------------------------------------ checklist
async def _context(pool: Any) -> dict[str, Any]:
    import risk_engine as re_mod
    positions = await re_mod._positions(pool)
    cfg = re_mod.load_config()
    total = sum(p["value_thb"] for p in positions)
    async with pool.acquire() as conn:
        sectors = {r["ticker"]: r["sector"] for r in await conn.fetch("SELECT ticker, sector FROM investment_watchlist")}
        regime_row = None
        try:
            regime_row = await conn.fetchrow("SELECT regime FROM signal_scores ORDER BY as_of DESC LIMIT 1")
        except Exception:  # noqa: BLE001
            pass
        scores = {}
        try:
            scores = {r["ticker"]: float(r["score"]) for r in await conn.fetch(
                "SELECT ticker, score FROM signal_scores WHERE as_of = (SELECT max(as_of) FROM signal_scores)")}
        except Exception:  # noqa: BLE001
            pass
    rep = await re_mod.latest_risk_report(pool)
    port_fx = ((rep or {}).get("factor_exposures") or {}).get("portfolio") or {}
    return {"positions": positions, "cfg": cfg, "total": total, "sectors": {**(cfg.get("sectors") or {}), **sectors},
            "regime": regime_row["regime"] if regime_row else None, "scores": scores, "port_fx": port_fx}


def factor_betas(ticker: str) -> dict[str, Any]:
    """1y daily OLS betas of the candidate (in THB terms) to the same factors the risk engine uses."""
    import risk_engine as re_mod
    fac = re_mod.FACTOR_TICKERS
    raw = download_closes(sorted({ticker, *fac.values()}), None, "1y", 3600)
    y = raw[ticker] if ticker.endswith(".BK") else raw[ticker] * raw["THB=X"]
    X = pd.DataFrame({k: (raw[v].diff() if k == "us10y" else raw[v].pct_change(fill_method=None)) for k, v in fac.items()})
    with np.errstate(all="ignore"):  # macOS Accelerate emits spurious matmul warnings
        return re_mod._ols(y.pct_change(fill_method=None), X)


def _usdthb() -> float:
    try:
        s = download_closes(["THB=X"], None, "5d", 3600)["THB=X"].dropna()
        return float(s.iloc[-1])
    except Exception:  # noqa: BLE001
        return 33.7


async def build_checklist(pool: Any, plan: dict[str, Any], ctx: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    import risk_engine as re_mod
    ctx = ctx or await _context(pool)
    cfg, total, positions = ctx["cfg"], ctx["total"], ctx["positions"]
    t = plan["ticker"]
    fx = 1.0 if (plan.get("currency") or "THB") == "THB" else await asyncio.to_thread(_usdthb)
    entry = _f(plan.get("entry_high")) or _f(plan.get("last_price"))
    stop, target = _f(plan.get("stop")), _f(plan.get("target"))
    items: list[dict[str, Any]] = []

    def add(key: str, ok: Optional[bool], detail: str, required: bool = True) -> None:
        items.append({"check": key, "pass": ok, "required": required, "detail": detail})

    rr = _f(plan.get("rr"))
    add("reward_risk", rr is not None and rr >= MIN_RR, f"R:R {rr:.2f} (min {MIN_RR})" if rr is not None else "no R:R")
    add("stop_defined", bool(stop and entry and stop < entry), f"stop {stop} below entry {entry}" if stop else "no stop")
    size: dict[str, Any] = {}
    if entry and stop and stop < entry:
        sector = ctx["sectors"].get(t, "unclassified")
        _inp = plan.get("inputs") or {}
        if isinstance(_inp, str):
            _inp = json.loads(_inp)
        # setup plans (e.g. momentum_base_swing) size off a gap-adjusted stop and their own risk % (default = config)
        size_stop = _f(_inp.get("stop_for_sizing")) if _f(_inp.get("stop_for_sizing")) and _f(_inp.get("stop_for_sizing")) < stop else stop
        size = re_mod.position_size(t, entry * fx, size_stop * fx, total, positions, cfg, sector=sector,
                                    risk_pct=_f(_inp.get("risk_pct")))
        size["fx_used"] = fx
        if size_stop != stop:
            size["gap_adjusted_stop"] = size_stop
            size["note"] = (size.get("note") or "") + " Sized on a gap-adjusted stop (typical bad overnight gap) - real stop is the plan stop."
        after_pos = size["position_pct"] or 0
        add("position_cap", after_pos <= float(cfg.get("max_position_pct", 25)),
            f"size {size['shares']} sh = {after_pos}% of portfolio (cap {cfg.get('max_position_pct')}%; binding: {size['binding_constraint']})")
        sec_after = (size.get("sector_used_pct") or 0) + after_pos
        add("sector_cap", sec_after <= float(cfg.get("max_sector_pct", 40)),
            f"sector {sector} {sec_after:.1f}% after trade (cap {cfg.get('max_sector_pct')}%)")
        add("size_nonzero", size["shares"] > 0, f"{size['shares']} shares (lot {size['board_lot']})")
    inputs = plan.get("inputs") or {}
    if isinstance(inputs, str):
        inputs = json.loads(inputs)
    px_date = ((inputs.get("price") or {}).get("as_of"))
    fresh = px_date is not None and (date.today() - date.fromisoformat(px_date)).days <= 7
    add("price_fresh", fresh, f"price as of {px_date}")
    cat = plan.get("catalyst") or ""
    expiry = plan.get("expiry")
    exp_d = expiry if isinstance(expiry, date) else (date.fromisoformat(str(expiry)[:10]) if expiry else None)
    add("expiry_set", exp_d is not None, f"expires {exp_d}")
    ev_warn = []
    for part in cat.split(";"):
        for tok in part.replace(",", " ").split():
            try:
                d = date.fromisoformat(tok[:10])
            except ValueError:
                continue
            if exp_d and date.today() <= d <= exp_d:
                ev_warn.append(f"{part.strip().split()[0]} {d}")
    add("events_in_window", None if not ev_warn else False,
        ("event inside plan window: " + ", ".join(ev_warn) + " - size/hold decision needed") if ev_warn else "no earnings/XD inside window (per Yahoo calendar)",
        required=False)
    # factor overlap: correlation with current holdings
    try:
        held = [p["ticker"] for p in positions if p["ticker"] not in ("SCBGOLDE", "SCB_GOLD_FUND")]
        px = await asyncio.to_thread(download_closes, held + [t], None, "1y", 3600)
        r = px.pct_change(fill_method=None)
        corrs = {h: round(float(r[t].corr(r[h])), 2) for h in held if h in r.columns and t in r.columns and h != t}
        mx = max(corrs.values()) if corrs else None
        same_sector = [p["ticker"] for p in positions if ctx["sectors"].get(p["ticker"]) == ctx["sectors"].get(t)]
        add("correlation_overlap", (mx is None or mx <= 0.6) and not same_sector,
            f"max corr with holdings {mx} {corrs}; same-sector holdings: {same_sector or 'none'}", required=False)
    except Exception as exc:  # noqa: BLE001
        add("correlation_overlap", None, f"not computed ({exc})", required=False)
    try:
        cb = await asyncio.to_thread(factor_betas, t)
        pf = ctx.get("port_fx") or {}
        shared = []
        # Market beta ('set') is judged by the regime/beta checks; here we look for concentration in the
        # macro factors the portfolio already carries: the candidate must be significant (|t|>=3), same sign
        # as a significant portfolio exposure (|t|>=2) and at least 1.5x the portfolio's own beta.
        for k, tv in (cb.get("t_stats") or {}).items():
            if k == "set":
                continue
            pt, pb, cbeta = (pf.get("t_stats") or {}).get(k), (pf.get("betas") or {}).get(k), (cb.get("betas") or {}).get(k)
            if None in (tv, pt, pb, cbeta):
                continue
            if abs(tv) >= 3 and abs(pt) >= 2 and (cbeta > 0) == (pb > 0) and abs(cbeta) >= 1.5 * abs(pb):
                shared.append(f"{k} (candidate beta {cbeta:+.2f} vs portfolio {pb:+.2f})")
        add("factor_beta_overlap", not shared,
            ("adds to existing portfolio factor exposure: " + "; ".join(shared)) if shared else
            f"no significant same-sign factor exposure shared with the portfolio (betas {cb.get('betas')})", required=False)
    except Exception as exc:  # noqa: BLE001
        add("factor_beta_overlap", None, f"not computed ({exc})", required=False)
    try:
        df = (await asyncio.to_thread(download_ohlc, [t], "6mo")).get(t)
        adv = float((df["Close"] * df["Volume"]).iloc[-20:].mean()) * fx if df is not None else None
        pos_val = size.get("position_value") or 0
        add("liquidity", adv is not None and adv >= 20 * pos_val, f"avg daily traded value {adv:,.0f} THB vs position {pos_val:,.0f}" if adv else "no volume data")
    except Exception as exc:  # noqa: BLE001
        add("liquidity", None, f"not computed ({exc})")
    sc = ctx["scores"].get(t)
    try:  # 2026-11-01 (P3.3): Thai price-only composite was WEAK in walk-forward -> score is display-only there
        from signals import validation_for
        _val = validation_for(t)
    except Exception:  # noqa: BLE001
        _val = {"status": "unknown", "detail": ""}
    if sc is not None and _val.get("status") != "pass":
        add("signal_score", None, f"signal score {sc} - display only, not validated ({_val.get('status')}: {_val.get('detail')})", required=False)
    else:
        add("signal_score", None if sc is None else sc >= 50, f"signal score {sc} (validated components only)" if sc is not None else "no signal score yet", required=False)
    if ctx.get("regime"):
        add("regime", ctx["regime"] != "risk_off", f"macro regime {ctx['regime']}", required=False)
    req_ok = all(i["pass"] for i in items if i["required"] and i["pass"] is not None) and \
        all(i["pass"] is not None for i in items if i["required"])
    return {"items": items, "pass": bool(req_ok and plan.get("viable", True)), "size": size}


async def refresh_checklists(pool: Any, statuses: tuple[str, ...] = ("proposed", "approved")) -> int:
    ctx = await _context(pool)
    async with pool.acquire() as conn:
        plans = [dict(r) for r in await conn.fetch("SELECT * FROM trade_plans WHERE status = ANY($1::text[])", list(statuses))]
    for p in plans:
        try:
            cl = await build_checklist(pool, p, ctx)
            async with pool.acquire() as conn:
                await conn.execute("UPDATE trade_plans SET checklist=$2::jsonb, checklist_pass=$3, size=$4::jsonb, updated_at=now() WHERE id=$1",
                                   p["id"], json.dumps(cl["items"], default=str), cl["pass"], json.dumps(cl["size"], default=str))
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("checklist for plan %s failed: %s", p["id"], exc)
    return len(plans)


# ----------------------------------------------------------------- read/update
def _row(r: Any) -> dict[str, Any]:
    d = dict(r)
    for k, v in list(d.items()):
        if isinstance(v, str) and k in ("inputs", "size", "checklist"):
            try:
                d[k] = json.loads(v)
            except Exception:  # noqa: BLE001
                pass
        elif hasattr(v, "isoformat"):
            d[k] = v.isoformat()
        elif v.__class__.__name__ == "Decimal":
            d[k] = float(v)
    # 2026-11-01 (Tho t27u): a plan approved via override is always visibly labelled with its reason.
    reason = (d.get("override_reason") or "").strip() if isinstance(d.get("override_reason"), str) else ""
    d["approved_by_override"] = bool(reason) and d.get("status") in ("approved", "open", "closed")
    d["override_badge_th"] = f"อนุมัติแบบ override: {reason}" if d["approved_by_override"] else None
    return d


async def list_plans(pool: Any, status: Optional[str] = None) -> list[dict[str, Any]]:
    await ensure_tables(pool)
    async with pool.acquire() as conn:
        if status:
            rows = await conn.fetch("SELECT * FROM trade_plans WHERE status=$1 ORDER BY viable DESC, rr DESC NULLS LAST", status)
        else:
            rows = await conn.fetch("SELECT * FROM trade_plans WHERE status NOT IN ('superseded') ORDER BY created_at DESC LIMIT 200")
    return [_row(r) for r in rows]


PLAN_EDITABLE = {"entry_low", "entry_high", "stop", "target", "catalyst", "expiry", "review_note"}


async def update_plan(pool: Any, plan_id: int, fields: dict[str, Any]) -> dict[str, Any]:
    await ensure_tables(pool)
    status = fields.get("status")
    override_reason = str(fields.get("override_reason") or "").strip()
    async with pool.acquire() as conn:
        plan = await conn.fetchrow("SELECT * FROM trade_plans WHERE id=$1", plan_id)
        if not plan:
            raise KeyError(plan_id)
        for k, v in fields.items():
            if k in PLAN_EDITABLE:
                if k == "expiry":
                    v = date.fromisoformat(v) if v else None
                await conn.execute(f"UPDATE trade_plans SET {k}=$2, updated_at=now() WHERE id=$1", plan_id, v)
        plan = dict(await conn.fetchrow("SELECT * FROM trade_plans WHERE id=$1", plan_id))
        el, eh, st, tg = (_f(plan[k]) for k in ("entry_low", "entry_high", "stop", "target"))
        if el and eh and st and tg and any(k in fields for k in ("entry_low", "entry_high", "stop", "target")):
            mid = (el + eh) / 2
            rr = (tg - mid) / (mid - st) if mid > st else 0
            await conn.execute("UPDATE trade_plans SET rr=$2, viable=$3 WHERE id=$1", plan_id, rr, rr >= MIN_RR)
        row = await conn.fetchrow("SELECT * FROM trade_plans WHERE id=$1", plan_id)

    allowed = {"approved", "rejected", "cancelled", "open", "closed", "expired"}
    if status and status not in allowed:
        raise ValueError(f"status must be one of {sorted(allowed)}")

    # Always rebuild before approval.  No status/watch-list mutation happens
    # until viability, required checks, and price freshness are known.
    cl = await build_checklist(pool, dict(row))
    async with pool.acquire() as conn:
        await conn.execute("UPDATE trade_plans SET checklist=$2::jsonb, checklist_pass=$3, size=$4::jsonb WHERE id=$1",
                           plan_id, json.dumps(cl["items"], default=str), cl["pass"], json.dumps(cl["size"], default=str))
    if status == "approved":
        current = dict(row)
        price_check = next((item for item in cl["items"] if item.get("check") == "price_fresh"), None)
        price_fresh = bool(price_check and price_check.get("pass") is True)
        viable = bool(current.get("viable"))
        problems_found = []
        if not viable:
            problems_found.append("not viable")
        if not price_fresh:
            problems_found.append("price missing/stale")
        if not cl["pass"]:
            problems_found.append("checklist failed")
        if not problems_found:
            override_reason = ""  # nothing to override -> a plain approval, never labelled as override
        if (not viable or not cl["pass"] or not price_fresh) and not override_reason:
            problems = []
            if not viable:
                problems.append("plan is not viable")
            if not price_fresh:
                problems.append("price is missing or older than 7 calendar days")
            if not cl["pass"]:
                failed = [item.get("check") for item in cl["items"] if item.get("required") and item.get("pass") is not True]
                problems.append("required checklist failed: " + ", ".join(str(key) for key in failed))
            raise ValueError(
                "cannot approve trade plan: " + "; ".join(problems)
                + "; provide a non-empty override_reason to override"
            )
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """UPDATE trade_plans SET status='approved', override_reason=$2,
                              reviewed_at=now(), updated_at=now() WHERE id=$1""",
                    plan_id,
                    override_reason or None,
                )
                # Only an APPROVED plan drives watch-list entry-zone alerts.
                await conn.execute(
                    """UPDATE investment_watchlist SET entry_low=$2, entry_high=$3, stop_price=$4, target_price=$5,
                           status_note=$6, updated_at=now() WHERE ticker=$1""",
                    current["ticker"], current["entry_low"], current["entry_high"], current["stop"], current["target"],
                    f"zone from approved trade plan #{plan_id} ({datetime.now(timezone(timedelta(hours=7))):%Y-%m-%d} ICT)"
                    + (f" - APPROVED BY OVERRIDE (อนุมัติแบบ override): {override_reason}" if override_reason else ""))
                if override_reason:
                    await conn.execute(
                        """UPDATE trade_plans SET review_note = trim(both ' ' from coalesce(review_note, '') || ' [APPROVED BY OVERRIDE: ' || $2 || ']')
                           WHERE id=$1""", plan_id, override_reason)
                await conn.execute(
                    """INSERT INTO trade_plan_audit (plan_id, ticker, action, by_override, override_reason, checklist_pass, note)
                       VALUES ($1,$2,'approved',$3,$4,$5,$6)""",
                    plan_id, current["ticker"], bool(override_reason), override_reason or None, cl["pass"],
                    "; ".join(problems_found) if problems_found else None)
        if override_reason:
            LOGGER.warning("trade plan %s approval override: %s", plan_id, override_reason)
    elif status:
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE trade_plans SET status=$2, reviewed_at=now(), updated_at=now() WHERE id=$1",
                plan_id,
                status,
            )
            await conn.execute("INSERT INTO trade_plan_audit (plan_id, ticker, action, checklist_pass) VALUES ($1,$2,$3,$4)",
                               plan_id, row["ticker"], status, cl["pass"])
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM trade_plans WHERE id=$1", plan_id)
    return _row(row)


async def plan_audit(pool: Any, limit: int = 50) -> list[dict[str, Any]]:
    await ensure_tables(pool)
    rows = await pool.fetch("SELECT * FROM trade_plan_audit ORDER BY created_at DESC LIMIT $1", limit)
    out = []
    for r in rows:
        d = {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in dict(r).items()}
        d["badge_th"] = f"อนุมัติแบบ override: {d['override_reason']}" if d.get("by_override") else None
        out.append(d)
    return out


async def create_manual_plan(pool: Any, body: dict[str, Any]) -> dict[str, Any]:
    await ensure_tables(pool)
    t = str(body["ticker"]).upper()
    el, eh, st, tg = (float(body[k]) for k in ("entry_low", "entry_high", "stop", "target"))
    mid = (el + eh) / 2
    rr = (tg - mid) / (mid - st) if mid > st else 0
    async with pool.acquire() as conn:
        pid = await conn.fetchval(
            """INSERT INTO trade_plans (ticker, source, status, viable, currency, entry_low, entry_high, stop, target, rr, inputs,
                   rationale, catalyst, expiry) VALUES ($1,'manual','proposed',$2,$3,$4,$5,$6,$7,$8,$9::jsonb,$10,$11,$12) RETURNING id""",
            t, rr >= MIN_RR, body.get("currency", "THB" if t.endswith(".BK") else "USD"), el, eh, st, tg, rr,
            json.dumps({"price": {"value": None, "source": "manual", "as_of": date.today().isoformat()}}),
            body.get("rationale"), body.get("catalyst"),
            date.fromisoformat(body["expiry"]) if body.get("expiry") else date.today() + timedelta(days=PLAN_EXPIRY_DAYS))
    return await update_plan(pool, pid, {})


# ------------------------------------------------------------------ paper ledger
def trade_costs(ticker: str, notional: float) -> float:
    """Fees for one fill in instrument currency (slippage is applied to the fill price instead)."""
    if ticker.endswith(".BK"):
        return notional * COMMISSION_TH * (1 + VAT)
    return notional * (US_COMMISSION + FX_SPREAD)


async def update_paper_ledger(pool: Any) -> dict[str, Any]:
    """Simulate every viable proposed/approved plan on daily bars (no look-ahead:
    a fill needs a bar whose range touches the zone AFTER the plan was created;
    if stop and target are both inside one bar the stop is assumed first)."""
    await ensure_tables(pool)
    async with pool.acquire() as conn:
        plans = [dict(r) for r in await conn.fetch(
            "SELECT * FROM trade_plans WHERE viable AND status IN ('proposed','approved','open')")]
        # waiting paper orders of superseded/rejected plans lapse; filled ones keep running to exit
        await conn.execute("""UPDATE paper_trades pt SET status='expired', exit_reason='plan_'||tp.status, exit_date=current_date
                              FROM trade_plans tp WHERE tp.id = pt.plan_id AND pt.status='waiting'
                              AND tp.status IN ('superseded','rejected','cancelled','expired')""")
        open_t = {r["ticker"] for r in await conn.fetch("SELECT ticker FROM paper_trades WHERE status='open'")}
        for p in plans:
            if p["ticker"] in open_t:
                continue
            qty = (json.loads(p["size"]) if isinstance(p["size"], str) else (p["size"] or {})).get("shares") or 0
            await conn.execute("""INSERT INTO paper_trades (plan_id, ticker, qty, currency) VALUES ($1,$2,$3,$4)
                                  ON CONFLICT (plan_id) DO NOTHING""", p["id"], p["ticker"], qty or 100, p["currency"])
        trades = [dict(r) for r in await conn.fetch(
            "SELECT pt.*, tp.entry_low, tp.entry_high, tp.stop, tp.target, tp.expiry, tp.created_at AS plan_created "
            "FROM paper_trades pt JOIN trade_plans tp ON tp.id = pt.plan_id WHERE pt.status IN ('waiting','open')")]
    if not trades:
        return {"open": 0, "closed": 0}
    ohlc = await asyncio.to_thread(download_ohlc, sorted({t["ticker"] for t in trades}), "6mo")
    opened = closed = 0
    for tr in trades:
        df = ohlc.get(tr["ticker"])
        if df is None:
            continue
        start = (tr["plan_created"].date() + timedelta(days=1))
        bars = df.loc[pd.Timestamp(start):]
        if tr["last_checked"]:
            pass
        el, eh, st, tg = (float(tr[k]) for k in ("entry_low", "entry_high", "stop", "target"))
        status, entry_price, entry_date = tr["status"], _f(tr["entry_price"]), tr["entry_date"]
        exit_price = exit_reason = exit_date = None
        for ts, bar in bars.iterrows():
            d = ts.date()
            if status == "waiting":
                if bar["Low"] <= eh and bar["High"] >= el:
                    entry_price = min(eh, float(bar["Open"])) if bar["Open"] > el else float(bar["Open"])
                    entry_price *= (1 + SLIPPAGE)
                    entry_date, status = d, "open"
                    opened += 1
                    if bar["Low"] <= st:  # conservative: stopped out on the fill day
                        exit_price, exit_reason = st * (1 - SLIPPAGE), "stop_same_day"
                        exit_date, status = d, "closed"
                        closed += 1
                        break
                    continue
                if tr["expiry"] and d > tr["expiry"]:
                    status, exit_reason, exit_date = "expired", "expired_unfilled", d
                    break
            elif status == "open":
                if bar["Low"] <= st:
                    exit_price, exit_reason = min(st, float(bar["Open"])), "stop"
                elif bar["High"] >= tg:
                    exit_price, exit_reason = max(tg, float(bar["Open"])) if bar["Open"] > tg else tg, "target"
                elif tr["expiry"] and d > tr["expiry"]:
                    exit_price, exit_reason = float(bar["Close"]), "expiry"
                if exit_price is not None:
                    exit_price *= (1 - SLIPPAGE)
                    exit_date, status = d, "closed"
                    closed += 1
                    break
        qty = float(tr["qty"] or 0)
        fields = {"status": status, "entry_price": entry_price, "entry_date": entry_date, "last_checked": date.today()}
        if status == "closed" and entry_price:
            costs = trade_costs(tr["ticker"], entry_price * qty) + trade_costs(tr["ticker"], exit_price * qty)
            gross = (exit_price - entry_price) * qty
            risk = (entry_price - st) * qty
            fields.update(exit_price=exit_price, exit_date=exit_date, exit_reason=exit_reason, costs=costs, gross_pnl=gross,
                          net_pnl=gross - costs, r_multiple=(gross - costs) / risk if risk > 0 else None)
        elif status == "expired":
            fields.update(exit_date=exit_date, exit_reason=exit_reason)
        sets = ", ".join(f"{k}=${i + 2}" for i, k in enumerate(fields))
        async with pool.acquire() as conn:
            await conn.execute(f"UPDATE paper_trades SET {sets} WHERE id=$1", tr["id"], *fields.values())
    return {"opened": opened, "closed": closed, "tracked": len(trades)}


async def paper_summary(pool: Any) -> dict[str, Any]:
    await ensure_tables(pool)
    async with pool.acquire() as conn:
        rows = [_row(r) for r in await conn.fetch(
            "SELECT pt.*, tp.status AS plan_status FROM paper_trades pt JOIN trade_plans tp ON tp.id = pt.plan_id ORDER BY pt.id DESC LIMIT 200")]
    closed = [r for r in rows if r["status"] == "closed"]
    wins = [r for r in closed if (r.get("net_pnl") or 0) > 0]
    return {"trades": rows, "counts": {s: sum(1 for r in rows if r["status"] == s) for s in ("waiting", "open", "closed", "expired")},
            "hit_rate": round(len(wins) / len(closed), 3) if closed else None,
            "avg_r": round(float(np.mean([r["r_multiple"] for r in closed if r.get("r_multiple") is not None])), 3) if closed else None,
            "note": "Paper ledger: simulated fills on daily bars after plan creation; costs = SET commission+VAT / offshore fees + slippage. "
                    "Qty = checklist size (100 notional when caps give 0). Unfilled orders lapse when the plan is re-proposed."}


# ------------------------------------------------------------------ journal
JOURNAL_FIELDS = {"plan_id", "ticker", "side", "opened_at", "entry_price", "qty", "fees", "closed_at", "exit_price", "pnl",
                  "r_multiple", "setup", "thesis", "followed_plan", "exit_reason", "what_went_well", "what_went_wrong",
                  "lessons", "emotion", "grade"}


def _coerce(k: str, v: Any) -> Any:
    if v is None:
        return None
    if k in ("opened_at", "closed_at"):
        return date.fromisoformat(str(v)[:10])
    if k in ("entry_price", "qty", "fees", "exit_price", "pnl", "r_multiple"):
        return float(v)
    if k == "plan_id":
        return int(v)
    if k == "followed_plan":
        return bool(v)
    return str(v)


async def journal_upsert(pool: Any, body: dict[str, Any], entry_id: Optional[int] = None) -> dict[str, Any]:
    await ensure_tables(pool)
    f = {k: _coerce(k, v) for k, v in body.items() if k in JOURNAL_FIELDS}
    async with pool.acquire() as conn:
        if entry_id is None:
            if "ticker" not in f:
                raise ValueError("ticker required")
            f["ticker"] = f["ticker"].upper()
            cols = ", ".join(f)
            vals = ", ".join(f"${i + 1}" for i in range(len(f)))
            entry_id = await conn.fetchval(f"INSERT INTO trade_journal ({cols}) VALUES ({vals}) RETURNING id", *f.values())
        elif f:
            sets = ", ".join(f"{k}=${i + 2}" for i, k in enumerate(f))
            await conn.execute(f"UPDATE trade_journal SET {sets}, updated_at=now() WHERE id=$1", entry_id, *f.values())
        row = dict(await conn.fetchrow("SELECT * FROM trade_journal WHERE id=$1", entry_id))
        # derive P&L and R if prices are present and not supplied
        if row["exit_price"] is not None and row["entry_price"] is not None and row["qty"] is not None and row["pnl"] is None:
            pnl = (float(row["exit_price"]) - float(row["entry_price"])) * float(row["qty"]) - float(row["fees"] or 0)
            await conn.execute("UPDATE trade_journal SET pnl=$2 WHERE id=$1", entry_id, pnl)
            if row["plan_id"]:
                st = await conn.fetchval("SELECT stop FROM trade_plans WHERE id=$1", row["plan_id"])
                if st and float(row["entry_price"]) > float(st):
                    await conn.execute("UPDATE trade_journal SET r_multiple=$2 WHERE id=$1", entry_id,
                                       pnl / ((float(row["entry_price"]) - float(st)) * float(row["qty"])))
        row = await conn.fetchrow("SELECT * FROM trade_journal WHERE id=$1", entry_id)
    return _row(row)


async def journal_list(pool: Any) -> list[dict[str, Any]]:
    await ensure_tables(pool)
    async with pool.acquire() as conn:
        return [_row(r) for r in await conn.fetch("SELECT * FROM trade_journal ORDER BY COALESCE(opened_at, created_at::date) DESC LIMIT 200")]
