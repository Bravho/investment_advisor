"""Prediction system (Phase 4+, 2026-10-30).

For every holding, watch-list idea and key market factor, forecasts at 3d / 1m / 3m / 6m / 1y:
direction + P(up), expected return, median price, 50/80/95% price bands, confidence.

* Each prediction is FROZEN: insert-only table guarded by a trigger that rejects UPDATE/DELETE,
  plus a SHA-256 of the canonical payload. The record stores HOW it was made: every model's
  output and weight, inputs with source + as-of date, factor readings, news, analyst inputs and
  the key assumptions.
* Validation (when a horizon matures): direction hit, error, band coverage, PIT and Brier score
  -> calibration. Misses get a labelled root cause: stale_data / surprise_event /
  broken_assumption / wrong_signal (stored, insert-only).
* Learning loop: per-horizon model weights from track record (skill vs random-walk baseline,
  hit rate); weak models are retired; lessons are stored and fed to the advisor + brief.
* Backfill: a historical walk-forward run (price-only models, data <= each as-of date) so the
  scoreboard has statistics from day one; backfill rows are labelled source='backfill'.
Local computation + local Ollama only; no paid APIs.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from market_history import SET_PROXY, download_closes

LOGGER = logging.getLogger("portfolio_engine.predictions")
ICT = ZoneInfo("Asia/Bangkok")
HORIZONS = {"3d": 3, "1m": 21, "3m": 63, "6m": 126, "1y": 252}
CADENCE = {"3d": "daily", "1m": "weekly", "3m": "monthly", "6m": "monthly", "1y": "monthly"}
FACTORS = {"BZ=F": "Brent crude (USD/bbl)", "THB=X": "USD/THB (up = baht weaker)", "GC=F": "Gold (USD/oz)",
           SET_PROXY: "SET proxy TDEX.BK (THB)", "^TNX": "US 10y yield (%)", "^VIX": "VIX"}
PROXY = {"SCBGOLDE": ("GC=F", "THB=X")}  # NAV history not free -> gold x USD/THB
# 2026-10-31 macro board: gold in THB per troy oz (computed, same legs; not a fund)
PROXY["XAUTHB"] = ("GC=F", "THB=X")
MODELS = ["drift", "momentum", "meanrev", "regime", "signal", "analyst"]
PRIOR_W = {"drift": .20, "momentum": .25, "meanrev": .25, "regime": .10, "signal": .10, "analyst": .10}
# 2026-11-01 (P3.3): models with NO matured track record (signal, analyst: n=0, no point-in-time history to backtest)
# are display-only - their outputs are still recorded in method.models so they can earn weight later:
# activated with ACTIVATE_W only after >= MIN_N_RETIRE matured outcomes with skill > 0 and hit > 50%.
DISPLAY_ONLY_UNTIL_VALIDATED = {"signal", "analyst"}
ACTIVATE_W = {m: PRIOR_W[m] for m in DISPLAY_ONLY_UNTIL_VALIDATED}
PRIOR_W = {m: (0.0 if m in DISPLAY_ONLY_UNTIL_VALIDATED else w) for m, w in PRIOR_W.items()}
# 2026-11-01 (P3.1): learning policy per forecast family, decided by ops/p3_backtest.py
# (data/backtests/p3_20261101_0056.json; OOS last 3y, expanding yearly re-learning):
#   core: segmented weights + live regime rule for backfill rows  -> PASS (mean skill .0386 -> .0582, hit .599 -> .636) LIVE
#   macro_trends: segmented -> FAIL on hit (.624 -> .596): keeps pooled weights; segmented kept as shadow
FAMILY_POLICY = {"core": {"segmented": True, "regime_rule": "live"},
                 "macro_trends": {"segmented": False, "regime_rule": "backfill_proxy"}}
# SHADOW ONLY.  Default-off preserves all live forecast numbers.  Backtests may
# enable it to distinguish missing beta (use 1.0) from an intentional 0.0 beta.
ZERO_BETA_FIX = False
REGIME_COEF = {"risk_on": 0.1, "risk_off": -0.15}
T_DF = 5
T_SCALE = math.sqrt((T_DF - 2) / T_DF)  # unit-variance Student-t
MIN_N_RETIRE = 30
MODEL_VERSION = "v3"  # v2: learned sigma calibration; v3: confidence = |2P(up)-1| x agreement (no x4 stretch)

DDL = """
CREATE TABLE IF NOT EXISTS predictions (
    id            BIGSERIAL PRIMARY KEY,
    uid           CHAR(64) NOT NULL UNIQUE,
    source        VARCHAR(10) NOT NULL CHECK (source IN ('live','backfill')),
    subject       VARCHAR(30) NOT NULL,
    subject_type  VARCHAR(10) NOT NULL,
    horizon       VARCHAR(3) NOT NULL,
    horizon_days  INTEGER NOT NULL,
    made_at       TIMESTAMPTZ NOT NULL,
    as_of_date    DATE NOT NULL,
    target_date   DATE NOT NULL,
    base_price    DOUBLE PRECISION NOT NULL,
    direction     VARCHAR(4) NOT NULL,
    p_up          DOUBLE PRECISION NOT NULL,
    exp_return    DOUBLE PRECISION NOT NULL,
    sigma         DOUBLE PRECISION NOT NULL,
    median_price  DOUBLE PRECISION NOT NULL,
    band50_low    DOUBLE PRECISION, band50_high DOUBLE PRECISION,
    band80_low    DOUBLE PRECISION, band80_high DOUBLE PRECISION,
    band95_low    DOUBLE PRECISION, band95_high DOUBLE PRECISION,
    confidence    DOUBLE PRECISION NOT NULL,
    method        JSONB NOT NULL,
    payload_sha256 CHAR(64) NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_predictions_target ON predictions (target_date);
CREATE INDEX IF NOT EXISTS idx_predictions_subject ON predictions (subject, horizon, as_of_date);
CREATE TABLE IF NOT EXISTS prediction_outcomes (
    id             BIGSERIAL PRIMARY KEY,
    prediction_id  BIGINT NOT NULL UNIQUE REFERENCES predictions(id),
    validated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    actual_date    DATE NOT NULL,
    actual_price   DOUBLE PRECISION NOT NULL,
    actual_return  DOUBLE PRECISION NOT NULL,
    direction_hit  BOOLEAN NOT NULL,
    error_return   DOUBLE PRECISION NOT NULL,
    abs_pct_error  DOUBLE PRECISION NOT NULL,
    in50 BOOLEAN, in80 BOOLEAN, in95 BOOLEAN,
    pit            DOUBLE PRECISION,
    brier          DOUBLE PRECISION,
    realized_vol_ratio DOUBLE PRECISION,
    model_returns  JSONB,
    miss           BOOLEAN NOT NULL,
    rca_primary    VARCHAR(30),
    rca_labels     JSONB,
    rca_detail     JSONB
);
CREATE TABLE IF NOT EXISTS prediction_model_weights (
    id        BIGSERIAL PRIMARY KEY,
    as_of     DATE NOT NULL,
    horizon   VARCHAR(3) NOT NULL,
    model     VARCHAR(20) NOT NULL,
    weight    DOUBLE PRECISION NOT NULL,
    status    VARCHAR(10) NOT NULL,
    n         INTEGER, hit_rate DOUBLE PRECISION, skill DOUBLE PRECISION,
    basis     TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (as_of, horizon, model)
);
CREATE TABLE IF NOT EXISTS prediction_model_weights_family (
    id        BIGSERIAL PRIMARY KEY,
    as_of     DATE NOT NULL,
    family    VARCHAR(30) NOT NULL,
    horizon   VARCHAR(3) NOT NULL,
    model     VARCHAR(20) NOT NULL,
    weight    DOUBLE PRECISION NOT NULL,
    status    VARCHAR(10) NOT NULL,
    n         INTEGER, hit_rate DOUBLE PRECISION, skill DOUBLE PRECISION,
    basis     TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (as_of, family, horizon, model)
);
CREATE TABLE IF NOT EXISTS prediction_lessons (
    id         BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    as_of      DATE NOT NULL,
    horizon    VARCHAR(3),
    subject    VARCHAR(30),
    kind       VARCHAR(20) NOT NULL,
    lesson     TEXT NOT NULL,
    evidence   JSONB,
    UNIQUE (as_of, kind, horizon, subject)
);
CREATE OR REPLACE FUNCTION predictions_immutable() RETURNS trigger LANGUAGE plpgsql AS $f$
BEGIN
    RAISE EXCEPTION 'table % is insert-only (frozen predictions/outcomes)', TG_TABLE_NAME;
END $f$;
DO $d$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_predictions_frozen') THEN
        CREATE TRIGGER trg_predictions_frozen BEFORE UPDATE OR DELETE ON predictions
            FOR EACH ROW EXECUTE FUNCTION predictions_immutable();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_prediction_outcomes_frozen') THEN
        CREATE TRIGGER trg_prediction_outcomes_frozen BEFORE UPDATE OR DELETE ON prediction_outcomes
            FOR EACH ROW EXECUTE FUNCTION predictions_immutable();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_predictions_no_truncate') THEN
        CREATE TRIGGER trg_predictions_no_truncate BEFORE TRUNCATE ON predictions
            FOR EACH STATEMENT EXECUTE FUNCTION predictions_immutable();
    END IF;
END $d$;
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


_T5_PPF = {0.025: -2.570582, 0.10: -1.475884, 0.25: -0.726687, 0.75: 0.726687, 0.90: 1.475884, 0.975: 2.570582}


def tq(p: float) -> float:
    """Quantile of the unit-variance Student-t(5) (tabulated; no scipy dependency)."""
    return _T5_PPF[round(p, 3)] * T_SCALE


def _t5_cdf(t: float) -> float:
    th = math.atan(t / math.sqrt(5))
    c = math.cos(th)
    return 0.5 + (th + math.sin(th) * c * (1 + 2 / 3 * c * c)) / math.pi


def tcdf(z: float) -> float:
    """CDF of the unit-variance Student-t(5) (closed form for 5 d.f.)."""
    return _t5_cdf(z / T_SCALE)


# ------------------------------------------------------------------ models (data <= as-of only)
def _coef(x: np.ndarray, y: np.ndarray, shrink: float = 0.5) -> tuple[float, int]:
    m = np.isfinite(x) & np.isfinite(y)
    x, y = x[m], y[m]
    if len(x) < 60 or np.var(x) == 0:
        return 0.0, len(x)
    b = float(np.cov(x, y)[0, 1] / np.var(x))
    return b * shrink, len(x)


def model_outputs(lp: pd.Series, h: int, extras: dict[str, Any]) -> dict[str, Any]:
    """lp = log price series up to the as-of date. Returns {model: expected log return} + sigma."""
    lp = lp.dropna()
    r = lp.diff().dropna()
    out: dict[str, Any] = {}
    if len(r) < 260:
        return {"error": "insufficient history"}
    ew = float(np.sqrt((r.iloc[-260:] ** 2).ewm(alpha=0.06).mean().iloc[-1]))
    yv = float(r.iloc[-252:].std())
    vol_d = 0.5 * ew + 0.5 * yv
    sigma = vol_d * math.sqrt(h)
    hist = r.iloc[-1260:]
    out["drift"] = float(hist.mean()) * h * 0.5
    # time-series momentum: fwd h return on trailing L return, estimated on this asset's own past
    L = max(h, 21)
    fwd = (lp.shift(-h) - lp).values
    past = (lp - lp.shift(L)).values
    usable = len(lp) - h  # forward returns beyond the as-of date do not exist -> no look-ahead
    b_m, n_m = _coef(past[:usable], fwd[:usable])
    out["momentum"] = b_m * float(lp.iloc[-1] - lp.iloc[-1 - L])
    n_sma = 50 if h <= 21 else 200
    dev = (lp - lp.rolling(n_sma).mean()).values
    b_r, n_r = _coef(dev[:usable], fwd[:usable])
    out["meanrev"] = b_r * float(dev[-1]) if np.isfinite(dev[-1]) else 0.0
    reg = extras.get("regime")
    beta = extras.get("beta")
    if extras.get("_zero_beta_fix", ZERO_BETA_FIX):
        beta = 1.0 if beta is None else float(beta)
    else:
        beta = beta or 1.0
    out["regime"] = (0.1 if reg == "risk_on" else -0.15 if reg == "risk_off" else 0.0) * sigma * max(min(beta, 2), -1)
    sc = extras.get("signal_score")
    out["signal"] = 0.1 * sigma * (sc - 50) / 25 if sc is not None and h >= 21 else None
    tgt, px = extras.get("analyst_target"), math.exp(float(lp.iloc[-1]))
    out["analyst"] = 0.5 * math.log(tgt / px) * min(h / 252, 1) if tgt and h >= 63 else None
    return {"models": out, "sigma": sigma, "vol_d": vol_d,
            "diag": {"ewma_vol_d": ew, "vol_1y_d": yv, "momentum_coef": b_m, "momentum_n": n_m, "meanrev_coef": b_r,
                     "meanrev_n": n_r, "lookback": L, "sma": n_sma}}


def combine(mo: dict[str, Any], weights: dict[str, float], base: float, h: int, sigma_scale: float = 1.0) -> dict[str, Any]:
    models = {k: v for k, v in mo["models"].items() if v is not None and weights.get(k, 0) > 0 and not k.startswith("_")}
    wsum = sum(weights[k] for k in models)
    mu = sum(weights[k] * v for k, v in models.items()) / wsum if wsum else 0.0
    s = mo["sigma"] * sigma_scale
    p_up = tcdf(mu / s) if s > 0 else 0.5
    signs = [np.sign(v) for v in models.values() if abs(v) > 1e-9]
    agreement = abs(sum(signs)) / len(signs) if signs else 0.0
    conf = round(abs(2 * p_up - 1) * (0.5 + 0.5 * agreement), 3)
    band = lambda q: base * math.exp(mu + tq(q) * s)  # noqa: E731
    return {"mu": mu, "sigma": s, "p_up": p_up, "direction": "up" if p_up >= 0.5 else "down", "confidence": conf,
            "median": base * math.exp(mu), "b50": (band(.25), band(.75)), "b80": (band(.10), band(.90)),
            "b95": (band(.025), band(.975)), "used_weights": {k: round(weights[k] / wsum, 4) for k in models} if wsum else {},
            "agreement": agreement}


def assumptions(h: str, subj: str, mo: dict[str, Any], extras: dict[str, Any]) -> list[str]:
    a = [f"Volatility stays near the blended EWMA/1y level ({mo['vol_d'] * math.sqrt(252):.1%} annualised); Student-t(5) tails.",
         f"Macro regime stays '{extras.get('regime') or 'n/a'}' over the horizon.",
         "No discontinuity (corporate action, policy shock, war escalation) beyond what price history already contains.",
         "Momentum / mean-reversion coefficients estimated on this asset's own history persist (shrunk 50% toward zero)."]
    if extras.get("analyst_target") and HORIZONS[h] >= 63:
        a.append(f"Analyst mean target {extras['analyst_target']:.4g} is unbiased (implied move shrunk 50%).")
    if subj in PROXY:
        a.append("Fund NAV tracks gold (GC=F) x USD/THB less fees; tracking error ignored.")
    if subj == "THB=X":
        a.append("USD/THB 'up' means the baht weakens.")
    return a


def target_date(as_of: date, h: int) -> date:
    return (pd.Timestamp(as_of) + pd.offsets.BDay(h)).date()


def canonical_sha(rec: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(rec, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()


# ------------------------------------------------------------------ data
def _series_for(subj: str, closes: pd.DataFrame, base_override: Optional[float] = None) -> Optional[pd.Series]:
    if subj in PROXY:
        a, b = PROXY[subj]
        if a in closes and b in closes:
            s = (closes[a] * closes[b]).dropna()
            if base_override:
                s = s / s.iloc[-1] * base_override  # anchor to the latest official NAV
            return s
        return None
    return closes[subj].dropna() if subj in closes else None


async def _subjects(pool: Any) -> list[dict[str, Any]]:
    import risk_engine as re_mod
    # Locked ThaiESG funds are not forecast separately (no free NAV history; their SET exposure is covered by the
    # TDEX.BK factor forecast) - added 2026-10-30.
    held = [p for p in await re_mod._positions(pool) if not p.get("locked")]
    async with pool.acquire() as conn:
        ideas = [r["ticker"] for r in await conn.fetch("SELECT ticker FROM investment_watchlist WHERE status <> 'dropped' ORDER BY ticker")]
    out = [{"subject": p["ticker"], "type": "holding", "value_thb": p["value_thb"], "qty": p["quantity"]} for p in held]
    have = {o["subject"] for o in out}
    out += [{"subject": t, "type": "idea"} for t in ideas if t not in have]
    out += [{"subject": t, "type": "factor", "label": l} for t, l in FACTORS.items()]
    return out


async def current_weights(pool: Any, family: str = "core") -> dict[str, dict[str, float]]:
    """core -> prediction_model_weights (core-segmented since 2026-11-01); other families -> prediction_model_weights_family."""
    async with pool.acquire() as conn:
        rows = []
        if family != "core":
            try:
                rows = await conn.fetch("""SELECT DISTINCT ON (horizon, model) horizon, model, weight, status FROM prediction_model_weights_family
                                           WHERE family = $1 ORDER BY horizon, model, as_of DESC, created_at DESC""", family)
            except Exception:  # noqa: BLE001 - table not created yet
                rows = []
        if not rows:
            rows = await conn.fetch("""SELECT DISTINCT ON (horizon, model) horizon, model, weight, status FROM prediction_model_weights
                                       ORDER BY horizon, model, as_of DESC, created_at DESC""")
    w = {h: {**PRIOR_W, "_sigma_scale": 1.0} for h in HORIZONS}
    for r in rows:
        w[r["horizon"]][r["model"]] = 0.0 if r["status"] == "retired" else float(r["weight"])
    return w


async def _news_for(pool: Any, subj: str) -> dict[str, Any]:
    keys = [subj, subj.replace(".BK", "")]
    async with pool.acquire() as conn:
        rows = await conn.fetch("""SELECT n.title, n.source, n.published_at, s.score FROM sentiment_scores s JOIN news_articles n ON n.id = s.article_id
                                   WHERE s.ticker = ANY($1::text[]) AND s.analyzed_at > now() - interval '14 days'
                                   ORDER BY abs(s.score) DESC NULLS LAST LIMIT 3""", keys)
        agg = await conn.fetchrow("""SELECT count(*) n, avg(score)::float s FROM sentiment_scores WHERE ticker = ANY($1::text[])
                                     AND analyzed_at > now() - interval '14 days'""", keys)
    return {"n_14d": agg["n"], "avg_sentiment": round(agg["s"], 3) if agg["s"] is not None else None,
            "top_headlines": [{"title": r["title"][:160], "source": r["source"], "published": r["published_at"].isoformat() if r["published_at"] else None,
                               "score": float(r["score"]) if r["score"] is not None else None} for r in rows],
            "source": "news_articles + local Ollama sentiment (14d)"}


# 2026-11-01 (P3.2): cross-asset drivers tested in ops/p3_backtest.py -> FAILED (OOS skill with cross < without;
# cross alone negative) -> shadow only.
CROSS_DRIVERS = {"PTTEP.BK": "BZ=F", "PTT.BK": "BZ=F", "TOP.BK": "BZ=F", "IRPC.BK": "BZ=F", "GDX": "GC=F"}


def _shadow_features(subj: str, closes: pd.DataFrame, h: int, news: Optional[dict]) -> dict[str, Any]:
    out: dict[str, Any] = {"note": "shadow only - not used in this forecast (failed or not yet testable in walk-forward)"}
    drv = CROSS_DRIVERS.get(subj)
    if drv and drv in closes and subj in closes:
        try:
            j = pd.concat([np.log(closes[subj]), np.log(closes[drv])], axis=1, keys=["s", "d"]).dropna()
            L = max(h, 21)
            usable = len(j) - h
            b, n = _coef((j.d - j.d.shift(L)).values[:usable], (j.s.shift(-h) - j.s).values[:usable])
            out["cross_asset"] = {"driver": drv, "exp_log_return": round(float(b * (j.d.iloc[-1] - j.d.iloc[-1 - L])), 6),
                                  "coef": round(float(b), 4), "n": int(n), "status": "shadow (P3.2 walk-forward FAIL)"}
        except Exception as exc:  # noqa: BLE001
            out["cross_asset"] = {"driver": drv, "error": type(exc).__name__}
    if news and news.get("avg_sentiment") is not None:
        out["news_sentiment_14d"] = {"value": news["avg_sentiment"], "n": news.get("n_14d"),
                                     "status": "shadow (P3.4: 7 weekly ICs, mean IC -0.075, t -0.49 - insufficient history)"}
    return out


# ------------------------------------------------------------------ live generation
def _due(h: str, today: date, last: Optional[date]) -> bool:
    if last is None:
        return True
    if CADENCE[h] == "daily":
        return last < today
    if CADENCE[h] == "weekly":
        return today.isocalendar()[:2] != last.isocalendar()[:2]
    return (today.year, today.month) != (last.year, last.month)


async def generate_live(pool: Any, force: bool = False) -> dict[str, Any]:
    await ensure_tables(pool)
    today = datetime.now(ICT).date()
    async with pool.acquire() as conn:
        lasts = {(r["subject"], r["horizon"]): r["d"] for r in await conn.fetch(
            """SELECT subject, horizon, max(as_of_date) d FROM predictions
               WHERE source='live' AND method->>'family' IS DISTINCT FROM 'macro_trends'
               GROUP BY subject, horizon""")}
        lastmade = {r["horizon"]: r["d"] for r in await conn.fetch(
            # 2026-10-31: macro-board forecasts (method.family='macro_trends') keep their own cadence - excluded here
            "SELECT horizon, max(made_at AT TIME ZONE 'Asia/Bangkok')::date d FROM predictions WHERE source='live' AND method->>'family' IS DISTINCT FROM 'macro_trends' GROUP BY horizon")}
    due = [h for h in HORIZONS if force or _due(h, today, lastmade.get(h))]
    if not due:
        return {"due": [], "made": 0}
    subs = await _subjects(pool)
    tick = sorted({s["subject"] for s in subs if s["subject"] not in PROXY} | {"GC=F", "THB=X", SET_PROXY, "SPY"})
    closes = await asyncio.to_thread(download_closes, tick, None, "10y", 3600)
    weights = await current_weights(pool)
    from fundamentals import get_fundamentals
    funds = await get_fundamentals(pool, [s["subject"] for s in subs if s["type"] != "factor" and s["subject"] not in PROXY])
    async with pool.acquire() as conn:
        sig = {r["ticker"]: (float(r["score"]) if r["score"] is not None else None, r["as_of"]) for r in await conn.fetch(
            "SELECT ticker, score, as_of FROM signal_scores WHERE as_of = (SELECT max(as_of) FROM signal_scores)")}
        reg = await conn.fetchrow("SELECT regime, score, as_of FROM market_regime ORDER BY as_of DESC LIMIT 1")
        facs = {r["key"]: {"reading": float(r["reading"]) if r["reading"] is not None else None, "as_of": r["as_of"].isoformat() if r["as_of"] else None}
                for r in await conn.fetch("SELECT key, reading, as_of FROM market_factors")}
    track = await scoreboard(pool, brief=True)
    made = 0
    unchanged = 0
    now = datetime.now(timezone.utc)
    # 2026-10-31 FX layer: forecast USD/THB first so every other subject can carry an explicit FX assumption
    # (informational: the models already see FX inside THB price history; the FX leg is NOT added on top).
    subs = sorted(subs, key=lambda x: 0 if x["subject"] == "THB=X" else 1)
    fx_fc: dict[str, dict[str, Any]] = {}
    fx_ret_all = closes["THB=X"].pct_change(fill_method=None) if "THB=X" in closes else None
    try:
        import fx_risk as _fx
        _fx_reg = _fx.load_registry()
    except Exception:  # noqa: BLE001
        _fx, _fx_reg = None, {}
    for s in subs:
        subj = s["subject"]
        base_override = (s["value_thb"] / s["qty"]) if subj in PROXY and s.get("qty") else None
        ser = _series_for(subj, closes, base_override)
        if ser is None or len(ser) < 300:
            continue
        bench = closes.get(SET_PROXY if (subj.endswith(".BK") or subj in PROXY) else "SPY")
        beta = None
        if bench is not None:
            j = pd.concat([ser.pct_change(fill_method=None), bench.pct_change(fill_method=None)], axis=1, join="inner").dropna().iloc[-252:]
            beta = float(j.iloc[:, 0].cov(j.iloc[:, 1]) / j.iloc[:, 1].var()) if len(j) > 60 else None
        info = ((funds.get(subj) or {}).get("info") or {})
        tgt = _f(info.get("targetMeanPrice")) if (_f(info.get("numberOfAnalystOpinions")) or 0) >= 3 else None
        sc = sig.get(subj, (None, None))
        extras = {"regime": reg["regime"] if reg else None, "beta": beta if s["type"] != "factor" else 0.0,
                  "signal_score": sc[0], "analyst_target": tgt}
        news = await _news_for(pool, subj) if s["type"] != "factor" else None
        base = float(ser.iloc[-1])
        as_of = ser.index[-1].date()
        for h in due:
            # Even a forced run must not freeze a second forecast from the same
            # underlying close for this subject/horizon.
            last_as_of = lasts.get((subj, h))
            if last_as_of is not None and as_of <= last_as_of:
                unchanged += 1
                continue
            hd = HORIZONS[h]
            mo = model_outputs(np.log(ser), hd, extras)
            if "error" in mo:
                continue
            c = combine(mo, weights[h], base, hd, weights[h].get("_sigma_scale", 1.0))
            method = {
                "model_version": MODEL_VERSION,
                "sigma_scale": round(weights[h].get("_sigma_scale", 1.0), 4),
                "confidence_def": "|2*P(up)-1| x (0.5+0.5*model sign agreement); <0.1 low, 0.1-0.3 medium, >0.3 high",
                "ensemble": "weighted mean of model expected log-returns; Student-t(5) bands",
                "models": {k: (round(v, 6) if v is not None else None) for k, v in mo["models"].items()},
                "weights_used": c["used_weights"], "weights_source": "prediction_model_weights (learning loop, family=core segmented since 2026-11-01) or prior",
                "model_diagnostics": {k: (round(v, 6) if isinstance(v, float) else v) for k, v in mo["diag"].items()},
                "agreement": round(c["agreement"], 3),
                "inputs": {
                    "price": {"value": base, "as_of": str(as_of), "source": "yfinance daily close" if subj not in PROXY else "proxy GC=F x THB=X anchored to latest SCBAM NAV"},
                    "beta": {"value": round(beta, 3) if beta is not None else None, "benchmark": SET_PROXY if (subj.endswith(".BK") or subj in PROXY) else "SPY"},
                    "signal_score": {"value": sc[0], "as_of": str(sc[1]) if sc[1] else None, "source": "signals module"},
                    "regime": {"value": reg["regime"] if reg else None, "score": float(reg["score"]) if reg else None,
                               "as_of": str(reg["as_of"]) if reg else None, "source": "signals.compute_regime"},
                    "analyst": {"target_mean": tgt, "n": _f(info.get("numberOfAnalystOpinions")), "low": _f(info.get("targetLowPrice")),
                                "high": _f(info.get("targetHighPrice")), "source": "Yahoo Finance consensus (free)",
                                "retrieved": str((funds.get(subj) or {}).get("retrieved_at", ""))[:10] or None} if s["type"] != "factor" else None,
                    "factor_readings": facs, "news": news,
                },
                "assumptions": assumptions(h, subj, mo, extras),
                "track_record_at_creation": (track.get("by_horizon") or {}).get(h),
                # 2026-11-01 (P3.2/P3.4): SHADOW features - recorded for future validation, NOT used in the forecast
                "shadow": _shadow_features(subj, closes, hd, news),
            }
            if subj == "THB=X":
                fx_fc[h] = {"median": c["median"], "mu": c["mu"], "b80": c["b80"], "p_up": c["p_up"], "base": base}
            elif fx_ret_all is not None and fx_fc.get(h):
                jj = pd.concat([ser.pct_change(fill_method=None), fx_ret_all], axis=1, join="inner").dropna().iloc[-252:]
                fxb = float(jj.iloc[:, 0].cov(jj.iloc[:, 1]) / jj.iloc[:, 1].var()) if len(jj) > 60 and jj.iloc[:, 1].var() > 0 else None
                ex = _fx.exposure_for(subj, _fx_reg) if _fx else {}
                f = fx_fc[h]
                method["inputs"]["fx"] = {
                    "usdthb_spot": round(f["base"], 4), "usdthb_forecast_median": round(f["median"], 4),
                    "usdthb_80pct": [round(f["b80"][0], 4), round(f["b80"][1], 4)], "usdthb_p_up": round(f["p_up"], 4),
                    "usdthb_exp_log_return": round(f["mu"], 6), "asset_fx_beta_1y": round(fxb, 3) if fxb is not None else None,
                    "fx_implied_log_return": round(fxb * f["mu"], 6) if fxb is not None else None,
                    "direct_foreign_share": ex.get("direct_foreign") and sum(ex["direct_foreign"].values()),
                    "hedge_ratio": ex.get("hedge_ratio"), "economic_beta_assumed": ex.get("economic_beta_assumed"),
                    "note": "Informational FX leg: the ensemble already uses THB-denominated history, so this is NOT added on top.",
                    "source": "frozen THB=X forecast for the same horizon (this run) + config/fx_exposure.json"}
                if fxb is not None:
                    method["assumptions"].append(
                        f"FX: USD/THB {f['base']:.3f} -> median {f['median']:.3f} over {h} (80% {f['b80'][0]:.2f}-{f['b80'][1]:.2f}; up = weaker baht); "
                        f"this asset's 1y FX beta {fxb:+.2f} implies {fxb * f['mu']:+.2%} from FX alone (already inside the price history, not added).")
            rec = {"version": MODEL_VERSION, "source": "live", "subject": subj, "subject_type": s["type"], "horizon": h, "horizon_days": hd,
                   "made_at": now.isoformat(), "as_of_date": str(as_of), "target_date": str(target_date(as_of, hd)),
                   "base_price": base, "direction": c["direction"], "p_up": round(c["p_up"], 4), "exp_return": round(c["mu"], 6),
                   "sigma": round(c["sigma"], 6), "median_price": c["median"], "bands": [c["b50"], c["b80"], c["b95"]],
                   "confidence": c["confidence"], "method": method}
            if await _insert(pool, rec):
                made += 1
    return {"due": due, "made": made, "unchanged_close_skipped": unchanged}


async def _insert(pool: Any, rec: dict[str, Any]) -> bool:
    sha = canonical_sha(rec)
    uid = hashlib.sha256(f"{rec.get('version', 'v1')}|{rec['source']}|{rec['subject']}|{rec['horizon']}|{rec['as_of_date']}|{rec['made_at'][:10]}".encode()).hexdigest()
    b50, b80, b95 = rec["bands"]
    async with pool.acquire() as conn:
        r = await conn.execute(
            """INSERT INTO predictions (uid, source, subject, subject_type, horizon, horizon_days, made_at, as_of_date, target_date,
                   base_price, direction, p_up, exp_return, sigma, median_price, band50_low, band50_high, band80_low, band80_high,
                   band95_low, band95_high, confidence, method, payload_sha256)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23::jsonb,$24)
               ON CONFLICT (uid) DO NOTHING""",
            uid, rec["source"], rec["subject"], rec["subject_type"], rec["horizon"], rec["horizon_days"],
            datetime.fromisoformat(rec["made_at"]), date.fromisoformat(rec["as_of_date"]), date.fromisoformat(rec["target_date"]),
            rec["base_price"], rec["direction"], rec["p_up"], rec["exp_return"], rec["sigma"], rec["median_price"],
            b50[0], b50[1], b80[0], b80[1], b95[0], b95[1], rec["confidence"], json.dumps(rec["method"], default=str), sha)
    return r.endswith("1")


# ------------------------------------------------------------------ validation + RCA
def _realized(ser: pd.Series, start: date, end: date) -> Optional[float]:
    seg = ser.loc[pd.Timestamp(start):pd.Timestamp(end)]
    r = np.log(seg).diff().dropna()
    return float(r.std()) if len(r) >= 2 else None


def evaluate(p: dict[str, Any], ser: pd.Series, regimes: dict[date, str], news_window: Optional[list] = None) -> Optional[dict[str, Any]]:
    s = ser.dropna()
    after = s.loc[pd.Timestamp(p["target_date"]):]
    if after.empty:
        return None
    a_date, a_px = after.index[0].date(), float(after.iloc[0])
    base = float(p["base_price"])
    ar = math.log(a_px / base)
    mu, sig = float(p["exp_return"]), float(p["sigma"])
    up = ar > 0
    hit = (p["direction"] == "up") == up
    z = (ar - mu) / sig if sig > 0 else 0.0
    in50 = p["band50_low"] <= a_px <= p["band50_high"]
    in80 = p["band80_low"] <= a_px <= p["band80_high"]
    in95 = p["band95_low"] <= a_px <= p["band95_high"]
    method = p["method"] if isinstance(p["method"], dict) else json.loads(p["method"])
    vol_d = (method.get("model_diagnostics") or {})
    pred_vol_d = sig / math.sqrt(p["horizon_days"])
    rv = _realized(s, p["as_of_date"], a_date)
    vratio = rv / pred_vol_d if rv and pred_vol_d > 0 else None
    miss = (not hit) or (not in80)
    labels, detail = [], {}
    if miss:
        price_as_of = ((method.get("inputs") or {}).get("price") or {}).get("as_of")
        made = p["made_at"].date() if hasattr(p["made_at"], "date") else date.fromisoformat(str(p["made_at"])[:10])
        if price_as_of and np.busday_count(date.fromisoformat(price_as_of), made) > 3:
            labels.append("stale_data")
            detail["stale_data"] = f"price input as of {price_as_of}, prediction made {made}"
        sig_in = ((method.get("inputs") or {}).get("signal_score") or {}).get("as_of")
        if sig_in and np.busday_count(date.fromisoformat(sig_in), made) > 3:
            labels.append("stale_data")
            detail["stale_signal"] = f"signal score as of {sig_in}"
        seg = np.log(s.loc[pd.Timestamp(p["as_of_date"]):pd.Timestamp(a_date)]).diff().dropna()
        big_day = float(seg.abs().max()) if len(seg) else 0.0
        if abs(z) > 2.5 or big_day > 4 * pred_vol_d:
            labels.append("surprise_event")
            day = seg.abs().idxmax().date() if len(seg) else None
            detail["surprise_event"] = {"z": round(z, 2), "largest_day_move": round(big_day, 4), "on": str(day),
                                        "headlines": (news_window or [])[:3]}
        reg0 = ((method.get("inputs") or {}).get("regime") or {}).get("value")
        reg1 = regimes.get(a_date) or (regimes[max(d for d in regimes if d <= a_date)] if regimes and any(d <= a_date for d in regimes) else None)
        if reg0 and reg1 and reg0 != reg1:
            labels.append("broken_assumption")
            detail["regime_change"] = f"{reg0} -> {reg1}"
        if vratio and vratio > 1.75:
            labels.append("broken_assumption")
            detail["vol_assumption"] = f"realised daily vol {rv:.4f} = {vratio:.1f}x predicted"
        mods = method.get("models") or {}
        w = method.get("weights_used") or {}
        wrong = sorted([(k, w.get(k, 0) * v) for k, v in mods.items() if v is not None and w.get(k) and np.sign(v) != np.sign(ar) and abs(v) > 1e-6],
                       key=lambda kv: -abs(kv[1]))
        if not hit and wrong:
            labels.append("wrong_signal")
            detail["wrong_signal"] = [{"model": k, "weighted_contrib": round(c, 5)} for k, c in wrong[:3]]
        if not labels:
            labels.append("noise_within_model")
            detail["noise"] = f"z={z:.2f}; no data, event or assumption failure detected"
    order = ["stale_data", "surprise_event", "broken_assumption", "wrong_signal", "noise_within_model"]
    primary = next((l for l in order if l in labels), None)
    mods = method.get("models") or {}
    return {"actual_date": a_date, "actual_price": a_px, "actual_return": ar, "direction_hit": hit, "error_return": ar - mu,
            "abs_pct_error": abs(a_px / float(p["median_price"]) - 1), "in50": in50, "in80": in80, "in95": in95,
            "pit": tcdf(z), "brier": (float(p["p_up"]) - (1.0 if up else 0.0)) ** 2, "realized_vol_ratio": vratio,
            "model_returns": {k: v for k, v in mods.items()}, "miss": miss, "rca_primary": primary,
            "rca_labels": sorted(set(labels)), "rca_detail": detail}


async def validate_matured(pool: Any, closes: Optional[pd.DataFrame] = None) -> dict[str, Any]:
    await ensure_tables(pool)
    async with pool.acquire() as conn:
        rows = [dict(r) for r in await conn.fetch(
            """SELECT p.* FROM predictions p LEFT JOIN prediction_outcomes o ON o.prediction_id = p.id
               WHERE o.id IS NULL AND p.target_date <= current_date ORDER BY p.target_date LIMIT 50000""")]
        regimes = {r["as_of"]: r["regime"] for r in await conn.fetch("SELECT as_of, regime FROM market_regime")}
    if not rows:
        return {"validated": 0}
    subs = sorted({r["subject"] for r in rows})
    if closes is None:
        tick = sorted({s for s in subs if s not in PROXY} | {"GC=F", "THB=X"})
        start = (min(r["as_of_date"] for r in rows) - timedelta(days=10)).isoformat()
        closes = await asyncio.to_thread(download_closes, tick, start, None, 3600)
    done = 0
    batch = []
    for p in rows:
        ser = _series_for(p["subject"], closes)
        if ser is None:
            continue
        if p["subject"] in PROXY:  # rescale proxy to the NAV the prediction used
            ser = ser / float(ser.loc[:pd.Timestamp(p["as_of_date"])].iloc[-1]) * float(p["base_price"])
        news = None
        if p["source"] == "live":
            async with pool.acquire() as conn:
                news = [dict(title=r["title"][:140], published=r["published_at"].isoformat() if r["published_at"] else None) for r in await conn.fetch(
                    """SELECT n.title, n.published_at FROM sentiment_scores s JOIN news_articles n ON n.id=s.article_id
                       WHERE s.ticker = ANY($1::text[]) AND n.published_at BETWEEN $2 AND $3 ORDER BY abs(s.score) DESC NULLS LAST LIMIT 3""",
                    [p["subject"], p["subject"].replace(".BK", "")], datetime.combine(p["as_of_date"], datetime.min.time(), ICT),
                    datetime.combine(p["target_date"], datetime.max.time(), ICT))]
        ev = evaluate(p, ser, regimes, news)
        if ev is None:
            continue
        batch.append((p["id"], ev))
    async with pool.acquire() as conn:
        for pid, ev in batch:
            r = await conn.execute(
                """INSERT INTO prediction_outcomes (prediction_id, actual_date, actual_price, actual_return, direction_hit, error_return,
                       abs_pct_error, in50, in80, in95, pit, brier, realized_vol_ratio, model_returns, miss, rca_primary, rca_labels, rca_detail)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14::jsonb,$15,$16,$17::jsonb,$18::jsonb)
                   ON CONFLICT (prediction_id) DO NOTHING""",
                pid, ev["actual_date"], ev["actual_price"], ev["actual_return"], ev["direction_hit"], ev["error_return"], ev["abs_pct_error"],
                ev["in50"], ev["in80"], ev["in95"], ev["pit"], ev["brier"], ev["realized_vol_ratio"], json.dumps(ev["model_returns"]),
                ev["miss"], ev["rca_primary"], json.dumps(ev["rca_labels"]), json.dumps(ev["rca_detail"], default=str))
            done += int(r.endswith("1"))
    return {"validated": done, "pending_checked": len(rows)}


# ------------------------------------------------------------------ learning loop
def _regime_live_rule_by_date(dates: list[date]) -> dict[date, Optional[str]]:
    """Point-in-time regime with the LIVE rule (signals.regime_from_closes) for backfill as-of dates (P3.1)."""
    if not dates:
        return {}
    import signals as _sg
    px = download_closes(_sg.REGIME_TICKERS, None, "10y", 3600)
    out: dict[date, Optional[str]] = {}
    for d in sorted(set(dates)):
        sub = px.loc[:pd.Timestamp(d)].iloc[-260:]
        out[d] = _sg.regime_from_closes(sub)["regime"] if len(sub) > 200 else None
    return out


def _learn_weights(rs: list[dict[str, Any]], regime_override: Optional[dict[int, float]] = None) -> tuple[dict, dict, float]:
    """Same formula as before 2026-11-01, applied to a subset of matured outcomes."""
    stats_m: dict[str, Any] = {}
    for m in MODELS:
        es, eb, hits, wts = [], [], [], []
        for r in rs:
            mr = r["model_returns"] if isinstance(r["model_returns"], dict) else json.loads(r["model_returns"] or "{}")
            v = mr.get(m)
            if m == "regime" and regime_override is not None and r["id"] in regime_override:
                v = regime_override[r["id"]]
            if v is None:
                continue
            a = float(r["actual_return"])
            w = 2.0 if r["source"] == "live" else 1.0
            s2 = float(r["sigma"]) ** 2 or 1e-9
            es.append(w * (a - v) ** 2 / s2)
            eb.append(w * a ** 2 / s2)  # random-walk (zero) baseline
            if abs(v) > 1e-9:
                hits.append((w, (v > 0) == (a > 0)))
            wts.append(w)
        n = len(wts)
        if n == 0:
            stats_m[m] = {"n": 0}
            continue
        skill = 1 - sum(es) / sum(eb) if sum(eb) > 0 else 0.0
        hit = sum(w for w, k in hits if k) / sum(w for w, _ in hits) if hits else None
        stats_m[m] = {"n": n, "skill": skill, "hit": hit}
    raw = {}
    for m, st in stats_m.items():
        if m in DISPLAY_ONLY_UNTIL_VALIDATED:
            if st["n"] >= MIN_N_RETIRE and (st.get("skill") or 0) > 0 and (st.get("hit") or 0) > 0.5:
                raw[m] = (ACTIVATE_W[m] * max(0.25, 1 + 20 * st["skill"]) * (0.5 + st["hit"]), "active",
                          f"validated: n={st['n']}, skill {st['skill']:+.3f}, hit {st['hit']}")
            else:
                raw[m] = (0.0, "display", f"display-only until validated (n={st['n']}, need >= {MIN_N_RETIRE} with skill > 0 and hit > 50%)")
        elif st["n"] < MIN_N_RETIRE:
            raw[m] = (PRIOR_W[m], "prior", f"n={st['n']} < {MIN_N_RETIRE}: prior weight kept")
        elif st["skill"] < -0.02 and (st["hit"] is None or st["hit"] < 0.5):
            raw[m] = (0.0, "retired", f"skill {st['skill']:+.3f} vs random walk, hit {st['hit']}")
        else:
            raw[m] = (PRIOR_W[m] * max(0.25, 1 + 20 * st["skill"]) * (0.5 + (st["hit"] or 0.5)),
                      "active", f"skill {st['skill']:+.3f}, hit {st['hit']}")
    tot = sum(v[0] for v in raw.values()) or 1
    # calibration: scale sigma so that the 80% band would have covered 80% of outcomes
    zs = []
    for r in rs:
        sc0 = r.get("sigma_scale") or 1.0
        if r["sigma"]:
            zs.append(abs((float(r["actual_return"]) - float(r["exp_return"])) / (float(r["sigma"]) / float(sc0))))
    if len(zs) >= MIN_N_RETIRE:
        sc = float(np.quantile(zs, 0.8)) / tq(0.90)
        sc = min(2.5, max(0.8, sc))
        stats_m["_sigma_scale"] = {"n": len(zs)}
        raw["_sigma_scale"] = (sc * tot, "active", f"80th pct |z| / t(0.9): raw-sigma multiplier {sc:.3f} (n={len(zs)})")
    return raw, stats_m, tot


async def _write_weights(pool: Any, table: str, today: date, h: str, raw: dict, stats_m: dict, tot: float,
                         family: Optional[str] = None, prefix: str = "") -> None:
    async with pool.acquire() as conn:
        for m, (w, status, basis) in raw.items():
            st = stats_m[m]
            if table == "prediction_model_weights":
                await conn.execute(
                    """INSERT INTO prediction_model_weights (as_of, horizon, model, weight, status, n, hit_rate, skill, basis)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
                       ON CONFLICT (as_of, horizon, model) DO UPDATE SET weight=EXCLUDED.weight, status=EXCLUDED.status, n=EXCLUDED.n,
                         hit_rate=EXCLUDED.hit_rate, skill=EXCLUDED.skill, basis=EXCLUDED.basis, created_at=now()""",
                    today, h, m, w / tot, status[:10], st.get("n"), st.get("hit"), st.get("skill"), prefix + basis)
            else:
                await conn.execute(
                    """INSERT INTO prediction_model_weights_family (as_of, family, horizon, model, weight, status, n, hit_rate, skill, basis)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                       ON CONFLICT (as_of, family, horizon, model) DO UPDATE SET weight=EXCLUDED.weight, status=EXCLUDED.status, n=EXCLUDED.n,
                         hit_rate=EXCLUDED.hit_rate, skill=EXCLUDED.skill, basis=EXCLUDED.basis, created_at=now()""",
                    today, family, h, m, w / tot, status[:10], st.get("n"), st.get("hit"), st.get("skill"), prefix + basis)


async def learn(pool: Any) -> dict[str, Any]:
    """Re-weight models per horizon from matured predictions (live counted double).

    2026-11-01 (P3.1): weights are learned PER FAMILY according to FAMILY_POLICY (walk-forward tested):
      * core (holdings / watch list / factors): own outcomes only; backfill rows' regime model re-evaluated with the
        LIVE regime rule at each as-of date (same definition as live). Written to prediction_model_weights (read by
        the core generator) and to prediction_model_weights_family (family='core').
      * macro_trends: pooled outcomes (segmented failed the test) -> family='macro_trends';
        segmented weights kept as family='macro_trends_shadow' (not used).
    """
    await ensure_tables(pool)
    today = datetime.now(ICT).date()
    async with pool.acquire() as conn:
        rows = [dict(r) for r in await conn.fetch(
            """SELECT p.id, p.horizon, p.source, p.sigma, p.exp_return, p.as_of_date, p.subject_type,
                      COALESCE(p.method->>'family', 'core') AS family,
                      COALESCE((p.method->>'sigma_scale')::float, 1) AS sigma_scale,
                      o.actual_return, o.model_returns
               FROM prediction_outcomes o JOIN predictions p ON p.id = o.prediction_id""")]
    # live-rule regime for core backfill asset rows (factors use beta 0 -> regime model is 0 either way)
    core_bf = [r for r in rows if r["family"] == "core" and r["source"] == "backfill" and r["subject_type"] != "factor"]
    try:
        reg_by_date = await asyncio.to_thread(_regime_live_rule_by_date, [r["as_of_date"] for r in core_bf])
        override = {r["id"]: REGIME_COEF.get(reg_by_date.get(r["as_of_date"]), 0.0) * float(r["sigma"]) for r in core_bf}
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("live-rule regime for backfill failed (%s) - using stored regime model values", exc)
        override = None
    out: dict[str, Any] = {}
    for h in HORIZONS:
        hr = [r for r in rows if r["horizon"] == h]
        core = [r for r in hr if r["family"] == "core"]
        macro = [r for r in hr if r["family"] == "macro_trends"]
        raw_c, st_c, tot_c = _learn_weights(core, override)
        pre = "family=core (segmented), regime=live rule; "
        await _write_weights(pool, "prediction_model_weights", today, h, raw_c, st_c, tot_c, prefix=pre)
        await _write_weights(pool, "prediction_model_weights_family", today, h, raw_c, st_c, tot_c, family="core", prefix=pre)
        raw_p, st_p, tot_p = _learn_weights(hr)
        await _write_weights(pool, "prediction_model_weights_family", today, h, raw_p, st_p, tot_p, family="macro_trends",
                             prefix="family=macro_trends uses POOLED weights (segmented failed walk-forward); ")
        if macro:
            raw_m, st_m, tot_m = _learn_weights(macro)
            await _write_weights(pool, "prediction_model_weights_family", today, h, raw_m, st_m, tot_m, family="macro_trends_shadow",
                                 prefix="SHADOW (not used): macro_trends-only weights; ")
        out[h] = {m: {"weight": round(v[0] / tot_c, 3), "status": v[1]} for m, v in raw_c.items()}  # _sigma_scale stored as multiplier
    await write_lessons(pool)
    return out


async def write_lessons(pool: Any) -> int:
    today = datetime.now(ICT).date()
    async with pool.acquire() as conn:
        rca = await conn.fetch("""SELECT p.horizon, p.subject, o.rca_primary, count(*) n FROM prediction_outcomes o JOIN predictions p ON p.id=o.prediction_id
                                  WHERE o.miss AND o.validated_at > now() - interval '120 days' OR (o.miss AND p.source='backfill')
                                  GROUP BY 1,2,3 HAVING count(*) >= 3 ORDER BY n DESC LIMIT 40""")
        cal = await conn.fetch("""SELECT p.horizon, count(*) n, avg(o.in80::int)::float c80, avg(o.in50::int)::float c50,
                                         avg(o.direction_hit::int)::float hit FROM prediction_outcomes o JOIN predictions p ON p.id=o.prediction_id GROUP BY 1""")
        wts = await conn.fetch("""SELECT DISTINCT ON (horizon, model) horizon, model, status, skill, hit_rate FROM prediction_model_weights
                                  ORDER BY horizon, model, as_of DESC""")
    lessons = []
    for r in cal:
        if r["n"] >= 30:
            if r["c80"] < 0.72:
                lessons.append((r["horizon"], None, "calibration", f"{r['horizon']}: 80% bands only contained {r['c80']:.0%} of outcomes (n={r['n']}) - ranges are too narrow; widen or treat tails as fatter.", dict(r)))
            elif r["c80"] > 0.88:
                lessons.append((r["horizon"], None, "calibration", f"{r['horizon']}: 80% bands contained {r['c80']:.0%} (n={r['n']}) - ranges are too wide / conservative.", dict(r)))
            if r["hit"] < 0.5:
                lessons.append((r["horizon"], None, "direction", f"{r['horizon']}: direction hit rate {r['hit']:.0%} (n={r['n']}) is no better than a coin flip - do not lean on direction calls at this horizon.", dict(r)))
    for r in rca[:15]:
        lessons.append((r["horizon"], r["subject"], f"rca_{r['rca_primary']}"[:20],
                        f"{r['subject']} {r['horizon']}: {r['n']} misses mainly from {str(r['rca_primary']).replace('_', ' ')}.", dict(r)))
    for r in wts:
        if r["status"] == "retired":
            lessons.append((r["horizon"], None, f"retired_{r['model']}"[:20],
                            f"{r['horizon']}: '{r['model']}' model retired (skill {r['skill']:+.3f} vs random walk, hit {r['hit_rate']:.0%}).", dict(r)))
    n = 0
    async with pool.acquire() as conn:
        for h, subj, kind, text, ev in lessons:
            # Idempotent (2026-10-30 fix): one lesson per (as_of, kind, horizon, subject) - the unique key. Re-runs on the same
            # day refresh the text/evidence instead of crashing when counts changed; nothing is deleted.
            r = await conn.execute("""INSERT INTO prediction_lessons (as_of, horizon, subject, kind, lesson, evidence)
                                      VALUES ($1,$2,$3,$4,$5,$6::jsonb)
                                      ON CONFLICT (as_of, kind, horizon, subject) DO UPDATE
                                        SET lesson = EXCLUDED.lesson, evidence = EXCLUDED.evidence
                                        WHERE prediction_lessons.lesson IS DISTINCT FROM EXCLUDED.lesson
                                           OR prediction_lessons.evidence IS DISTINCT FROM EXCLUDED.evidence""",
                                   today, h, subj or "*", kind, text, json.dumps(ev, default=str))
            n += int(r.endswith("1"))
    return n


# ------------------------------------------------------------------ backfill
def _backfill_sync(closes: pd.DataFrame, subjects: list[str], years: int = 3) -> list[dict[str, Any]]:
    """Walk-forward: at each historical as-of date use only data <= that date (price-only models)."""
    recs = []
    end = closes.index[-1]
    start = end - pd.DateOffset(years=years)
    idx = closes.index[closes.index >= start]
    weekly = idx[::5]
    monthly = pd.DatetimeIndex(pd.Series(idx, index=idx).groupby(idx.to_period("M")).first().values)
    tdex = closes.get(SET_PROXY)
    for subj in subjects:
        ser_full = _series_for(subj, closes)
        if ser_full is None or len(ser_full) < 600:
            continue
        lp_full = np.log(ser_full)
        for h, hd in HORIZONS.items():
            dates = weekly if h in ("3d", "1m") else monthly
            for d in dates:
                if (pd.Timestamp(d) + pd.offsets.BDay(hd)) > end:
                    continue
                lp = lp_full.loc[:d]
                if len(lp) < 400:
                    continue
                reg = None
                if tdex is not None:
                    tt = tdex.loc[:d].dropna()
                    reg = ("risk_on" if tt.iloc[-1] > tt.iloc[-200:].mean() else "risk_off") if len(tt) > 200 else None
                mo = model_outputs(lp, hd, {"regime": reg, "beta": 0.0 if subj in FACTORS else 1.0})
                if "error" in mo:
                    continue
                base = float(np.exp(lp.iloc[-1]))
                c = combine(mo, PRIOR_W, base, hd)
                as_of = lp.index[-1].date()
                recs.append({"source": "backfill", "subject": subj, "subject_type": "factor" if subj in FACTORS else "asset",
                             "horizon": h, "horizon_days": hd, "made_at": datetime.combine(as_of, datetime.min.time(), timezone.utc).isoformat(),
                             "as_of_date": str(as_of), "target_date": str(target_date(as_of, hd)), "base_price": base,
                             "direction": c["direction"], "p_up": round(c["p_up"], 4), "exp_return": round(c["mu"], 6),
                             "sigma": round(c["sigma"], 6), "median_price": c["median"], "bands": [c["b50"], c["b80"], c["b95"]],
                             "confidence": c["confidence"],
                             "method": {"ensemble": "backfill walk-forward, prior weights, price-only models (no point-in-time analyst/news/signal data)",
                                        "models": {k: (round(v, 6) if v is not None else None) for k, v in mo["models"].items()},
                                        "weights_used": c["used_weights"], "inputs": {"price": {"value": base, "as_of": str(as_of), "source": "yfinance (historical)"},
                                                                                     "regime": {"value": reg, "source": "TDEX vs SMA200 (backfill proxy)"}},
                                        "model_diagnostics": {k: (round(v, 6) if isinstance(v, float) else v) for k, v in mo["diag"].items()},
                                        "assumptions": ["historical simulation; data <= as-of date only"]}})
    return recs


async def run_backfill(pool: Any, years: int = 3) -> dict[str, Any]:
    await ensure_tables(pool)
    async with pool.acquire() as conn:
        n = await conn.fetchval("SELECT count(*) FROM predictions WHERE source='backfill'")
    if n:
        return {"skipped": f"backfill already present ({n} rows); predictions are immutable"}
    subs = [s["subject"] for s in await _subjects(pool)]
    tick = sorted({s for s in subs if s not in PROXY} | {"GC=F", "THB=X", SET_PROXY})
    closes = await asyncio.to_thread(download_closes, tick, None, "10y", 3600)
    recs = await asyncio.to_thread(_backfill_sync, closes, subs, years)
    made = 0
    for rec in recs:
        made += int(await _insert(pool, rec))
    val = await validate_matured(pool, closes)
    w = await learn(pool)
    return {"backfill_predictions": made, "validated": val, "weights": w}


# ------------------------------------------------------------------ reporting
async def scoreboard(pool: Any, brief: bool = False) -> dict[str, Any]:
    await ensure_tables(pool)
    async with pool.acquire() as conn:
        rows = await conn.fetch("""SELECT p.horizon, p.source, count(*) n, avg(o.direction_hit::int)::float hit, avg(o.in50::int)::float c50,
                                          avg(o.in80::int)::float c80, avg(o.in95::int)::float c95, avg(o.brier)::float brier,
                                          avg(o.abs_pct_error)::float mape, avg(o.miss::int)::float miss_rate
                                   FROM prediction_outcomes o JOIN predictions p ON p.id=o.prediction_id GROUP BY 1,2""")
        pend = {r["horizon"]: r["n"] for r in await conn.fetch(
            """SELECT p.horizon, count(*) n FROM predictions p LEFT JOIN prediction_outcomes o ON o.prediction_id=p.id
               WHERE o.id IS NULL AND p.source='live' GROUP BY 1""")}
        if brief:
            return {"by_horizon": {r["horizon"]: {"n": r["n"], "hit": round(r["hit"], 3), "cov80": round(r["c80"], 3)}
                                   for r in rows if r["source"] == "backfill"}}
        pits = await conn.fetch("SELECT p.horizon, o.pit FROM prediction_outcomes o JOIN predictions p ON p.id=o.prediction_id")
        rca = await conn.fetch("""SELECT p.horizon, o.rca_primary, count(*) n FROM prediction_outcomes o JOIN predictions p ON p.id=o.prediction_id
                                  WHERE o.miss GROUP BY 1,2""")
        rel = await conn.fetch("""SELECT p.horizon, width_bucket(p.p_up, 0, 1, 5) b, count(*) n, avg(p.p_up)::float pred, avg((o.actual_return>0)::int)::float obs
                                  FROM prediction_outcomes o JOIN predictions p ON p.id=o.prediction_id GROUP BY 1,2 ORDER BY 1,2""")
        wts = await conn.fetch("""SELECT DISTINCT ON (horizon, model) horizon, model, weight, status, n, hit_rate, skill, basis, as_of
                                  FROM prediction_model_weights ORDER BY horizon, model, as_of DESC, created_at DESC""")
        lessons = await conn.fetch("""SELECT DISTINCT ON (lesson) as_of, horizon, subject, kind, lesson, created_at FROM prediction_lessons
                                      WHERE as_of = (SELECT max(as_of) FROM prediction_lessons) ORDER BY lesson, created_at DESC""")
        lessons = sorted(lessons, key=lambda r: (0 if r["kind"] in ("calibration", "direction") else 1 if r["kind"].startswith("retired") else 2, r["horizon"] or ""))
        misses = await conn.fetch("""SELECT p.subject, p.horizon, p.as_of_date, p.direction, p.p_up, o.actual_return, o.rca_primary, o.rca_labels, o.rca_detail
                                     FROM prediction_outcomes o JOIN predictions p ON p.id=o.prediction_id WHERE o.miss AND p.source='live'
                                     ORDER BY o.validated_at DESC LIMIT 20""")
    hist: dict[str, list[int]] = {}
    for r in pits:
        if r["pit"] is not None:
            hist.setdefault(r["horizon"], [0] * 10)[min(9, int(r["pit"] * 10))] += 1
    order = list(HORIZONS)
    def jl(v: Any) -> Any:
        return json.loads(v) if isinstance(v, str) else v
    return {
        "rows": sorted([{k: (round(v, 4) if isinstance(v, float) else v) for k, v in dict(r).items()} for r in rows],
                       key=lambda r: (r["source"], order.index(r["horizon"]))),
        "pending_live": pend, "pit_histogram": hist,
        "reliability": [dict(r) for r in rel],
        "rca_counts": [dict(r) for r in rca],
        "model_weights": [{**{k: v for k, v in dict(r).items() if k != "as_of"}, "as_of": r["as_of"].isoformat()} for r in wts],
        "lessons": [{**{k: v for k, v in dict(r).items() if k != "created_at"}, "as_of": r["as_of"].isoformat()} for r in lessons],
        "recent_live_misses": [{**dict(r), "as_of_date": r["as_of_date"].isoformat(), "rca_labels": jl(r["rca_labels"]), "rca_detail": jl(r["rca_detail"])} for r in misses],
        "nominal": {"in50": 0.5, "in80": 0.8, "in95": 0.95},
    }


def _prow(r: Any) -> dict[str, Any]:
    d = dict(r)
    for k, v in list(d.items()):
        if hasattr(v, "isoformat"):
            d[k] = v.isoformat()
        elif k == "method" and isinstance(v, str):
            d[k] = json.loads(v)
    return d


async def latest_predictions(pool: Any, subject: Optional[str] = None, with_method: bool = False) -> list[dict[str, Any]]:
    await ensure_tables(pool)
    cols = "p.*" if with_method else ("p.id, p.subject, p.subject_type, p.horizon, p.made_at, p.as_of_date, p.target_date, p.base_price, p.direction, "
                                      "p.p_up, p.exp_return, p.median_price, p.band50_low, p.band50_high, p.band80_low, p.band80_high, "
                                      "p.band95_low, p.band95_high, p.confidence, p.payload_sha256")
    q = f"""SELECT DISTINCT ON (p.subject, p.horizon) {cols} FROM predictions p WHERE p.source='live'
            {"AND p.subject = $1" if subject else ""} ORDER BY p.subject, p.horizon, p.made_at DESC"""
    async with pool.acquire() as conn:
        rows = await conn.fetch(q, subject) if subject else await conn.fetch(q)
    order = list(HORIZONS)
    return sorted([_prow(r) for r in rows], key=lambda r: (r["subject"], order.index(r["horizon"])))


def explain(p: dict[str, Any]) -> str:
    m = p.get("method") or {}
    mods = m.get("models") or {}
    w = m.get("weights_used") or {}
    parts = [f"{k} {v * 100:+.2f}% (w {w.get(k, 0):.2f})" for k, v in mods.items() if v is not None and w.get(k)]
    made = p["made_at"]
    try:
        made = datetime.fromisoformat(str(made)).astimezone(ICT).strftime("%Y-%m-%d %H:%M ICT")
    except ValueError:
        made = str(made)[:16]
    return (f"{p['subject']} {p['horizon']} (made {made}, target {p.get('target_date')}, frozen sha {p['payload_sha256'][:10]}): {p['direction']} "
            f"P(up) {p['p_up']:.0%}, median {p['median_price']:.4g}, 80% range {p['band80_low']:.4g}-{p['band80_high']:.4g}, "
            f"confidence {p['confidence']:.2f}. How: " + "; ".join(parts) + ". Assumptions: " + " ".join((m.get("assumptions") or [])[:3])
            + _fx_line(m))


def _fx_line(m: dict[str, Any]) -> str:
    """2026-10-31: explicit FX assumption for the advisor (from method.inputs.fx, if this forecast carries one)."""
    fx = (m.get("inputs") or {}).get("fx") or {}
    if not fx.get("usdthb_forecast_median"):
        return ""
    b = fx.get("asset_fx_beta_1y")
    return (f" FX assumption: USD/THB {fx['usdthb_spot']} -> {fx['usdthb_forecast_median']} (up = weaker baht)"
            + (f"; FX beta {b:+.2f} -> FX alone {fx['fx_implied_log_return']:+.2%} (inside the forecast, not added)" if b is not None else "")
            + (f"; hedge ratio {fx['hedge_ratio']}" if fx.get("hedge_ratio") is not None else "") + ".")


async def advisor_context(pool: Any, tickers: list[str]) -> str:
    """Compact text block for the advisor LLM: forecasts (with how), track record and lessons."""
    import risk_engine as re_mod
    held = [p["ticker"] for p in await re_mod._positions(pool)]
    subs = list(dict.fromkeys([t for t in tickers] + held + ["BZ=F", "THB=X", "GC=F", SET_PROXY]))
    lines = ["=== FORECASTS (frozen predictions; quantitative ensemble, not advice) ==="]
    for s in subs:
        ps = await latest_predictions(pool, s, with_method=True)
        for p in ps:
            if p["horizon"] in ("3d", "1m", "3m", "1y") or s in tickers:
                lines.append("  - " + explain(p))
    sb = await scoreboard(pool)
    lines.append("=== FORECAST TRACK RECORD (validated) ===")
    for r in sb["rows"]:
        lines.append(f"  - {r['source']} {r['horizon']}: n={r['n']}, direction hit {r['hit']:.0%}, 80% band coverage {r['c80']:.0%} (nominal 80%), Brier {r['brier']:.3f}")
    if sb["lessons"]:
        lines.append("=== LESSONS FROM PAST MISSES ===")
        lines += [f"  - {l['lesson']}" for l in sb["lessons"][:8]]
    lines.append("When asked for a forecast, quote these numbers, state the reasoning (models, inputs, assumptions) and the track record; "
                 "do not invent other forecasts.")
    return "\n".join(lines)


def render_brief_section(sb: dict[str, Any], preds: list[dict[str, Any]]) -> str:
    lines = ["**Forecasts (frozen, quantitative ensemble)**"]
    for p in preds:
        if p["subject_type"] == "holding" and p["horizon"] in ("1m", "3m"):
            lines.append(f"- {p['subject']} {p['horizon']}: {p['direction']} P(up) {p['p_up']:.0%}, 80% range {p['band80_low']:.4g}–{p['band80_high']:.4g} (conf {p['confidence']:.2f})")
    for r in sb.get("rows", []):
        if r["source"] == "live" or not any(x["source"] == "live" and x["horizon"] == r["horizon"] for x in sb["rows"]):
            lines.append(f"- Track record {r['horizon']} ({r['source']}, n={r['n']}): hit {r['hit']:.0%}, 80% coverage {r['c80']:.0%}")
    for l in (sb.get("lessons") or [])[:3]:
        lines.append(f"- Lesson: {l['lesson']}")
    return "\n".join(lines)


async def monthly_summary_text(pool: Any) -> str:
    sb = await scoreboard(pool)
    m = datetime.now(ICT)
    lines = [f"📊 Forecast scoreboard {m:%b %Y}"]
    for r in sb["rows"]:
        lines.append(f"{r['horizon']} {r['source']}: n={r['n']} hit {r['hit']:.0%} | 80% band {r['c80']:.0%}")
    rc = {}
    for r in sb["rca_counts"]:
        rc[r["rca_primary"]] = rc.get(r["rca_primary"], 0) + r["n"]
    if rc:
        lines.append("Miss causes: " + ", ".join(f"{k} {v}" for k, v in sorted(rc.items(), key=lambda kv: -kv[1])))
    retired = [f"{w['horizon']}:{w['model']}" for w in sb["model_weights"] if w["status"] == "retired"]
    if retired:
        lines.append("Retired models: " + ", ".join(retired))
    for l in sb["lessons"][:3]:
        lines.append("• " + l["lesson"])
    lines.append("Details: dashboard → Forecasts. Not financial advice.")
    return "\n".join(lines)


async def send_monthly_summary(pool: Any) -> dict[str, Any]:
    """1st of month: LINE summary via ops/line_notify.py (send_to_owner, DND respected), once per month."""
    import os
    import subprocess
    from pathlib import Path
    key = datetime.now(ICT).strftime("%Y-%m")
    async with pool.acquire() as conn:
        await conn.execute("CREATE TABLE IF NOT EXISTS prediction_summary_sent (month VARCHAR(7) PRIMARY KEY, sent_at TIMESTAMPTZ DEFAULT now(), result TEXT)")
        if await conn.fetchval("SELECT 1 FROM prediction_summary_sent WHERE month=$1", key):
            return {"skipped": "already sent this month"}
    text = await monthly_summary_text(pool)
    root = Path(__file__).resolve().parent.parent
    py = os.getenv("SECRETARY_PYTHON", "/Users/admin/Projects/ai_secretary_brain/venv/bin/python")
    proc = await asyncio.to_thread(subprocess.run, [py, str(root / "ops" / "line_notify.py")], input=text, text=True,
                                   capture_output=True, timeout=60, env={**os.environ})
    dry = os.getenv("WATCH_ALERTS_DRY_RUN") == "1"
    result = "dry_run" if dry and proc.returncode == 0 else {0: "sent", 2: "skipped"}.get(proc.returncode, "error")
    if result == "sent":
        async with pool.acquire() as conn:
            await conn.execute("INSERT INTO prediction_summary_sent (month, result) VALUES ($1,$2) ON CONFLICT DO NOTHING", key, result)
    return {"result": result, "dry_run": dry, "chars": len(text), "text": text if dry else None}
