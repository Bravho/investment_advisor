"""Key macro indicator trends board (2026-10-31, Tho: 'prediction trends of important indicators').

Markets (gold, oil, US/China/HK/VN/Thai equity, US yields, DXY, USD/THB, BTC, copper, VIX):
  * forecasts at 3d / 1m / 3m / 6m / 1y made with the SAME frozen-prediction machinery as holdings
    (predictions.model_outputs + combine + _insert -> insert-only `predictions` table, SHA-256),
    validated/scored by predictions.validate_matured and fed into predictions.learn like every other forecast.
  * method.family = 'macro_trends' so the holdings generator keeps its own cadence.
  * indices without free daily history on Yahoo (SET, SET50, CSI 300, HS TECH, VN-Index) are forecast on a
    labelled ETF proxy; the board scales the proxy's % range onto the index level ("approx.").
Policy rates (Fed, Bank of Thailand, PBoC LPR): fetched from official/free pages only; never invented.
  A failed fetch shows 'unknown' and is logged in macro_fetch_log. Expected path is market-implied where free
  data exists (US: T-bill/2Y vs target), otherwise a labelled model-based heuristic; calls are frozen in
  policy_path_calls and scored after the next meeting (policy_path_outcomes).
Free data + local computation only; no paid APIs, no orders.
"""
from __future__ import annotations

import asyncio
import csv
import html as html_mod
import io
import json
import logging
import math
import re
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

import predictions as P
from market_history import UA, download_closes, http_bytes, http_json

LOGGER = logging.getLogger("portfolio_engine.macro_trends")
ICT = ZoneInfo("Asia/Bangkok")
FAMILY = "macro_trends"

# ------------------------------------------------------------------ registry
G_ASSETS, G_RATES, G_FX = "assets", "rates", "fx_crypto"
GROUPS = [(G_ASSETS, "สินทรัพย์ / หุ้น"), (G_RATES, "พันธบัตร & ดอกเบี้ย"), (G_FX, "สกุลเงิน & คริปโต")]

INDICATORS: list[dict[str, Any]] = [
    dict(key="gold_usd", group=G_ASSETS, name_th="ทองคำ (USD)", name_en="Gold XAU/USD", unit="USD/oz", subject="GC=F", display="GC=F",
         holdings=["SCBGOLDE"], link_th="ทอง → กองทุน SCBGOLDE",
         drivers_th=["ดอกเบี้ยแท้จริงสหรัฐฯ / ทิศทาง Fed", "ค่าเงินดอลลาร์ (DXY)", "ความเสี่ยงภูมิรัฐศาสตร์", "การซื้อทองของธนาคารกลาง"],
         source="yfinance GC=F (COMEX gold futures, front month) daily close"),
    dict(key="gold_thb", group=G_ASSETS, name_th="ทองคำ (บาท)", name_en="Gold in THB", unit="THB/oz", subject="XAUTHB", display="XAUTHB",
         holdings=["SCBGOLDE"], link_th="ทองในรูปเงินบาท → SCBGOLDE (ไม่ป้องกันค่าเงิน)",
         drivers_th=["ราคาทองโลก (USD)", "ค่าเงินบาท USD/THB"],
         proxy_th="คำนวณ GC=F × THB=X (บาทต่อทรอยออนซ์) — ไม่ใช่ราคาทองแท่ง 96.5% ของสมาคมค้าทองคำ",
         source="computed GC=F x THB=X (yfinance)"),
    dict(key="brent", group=G_ASSETS, name_th="น้ำมันดิบ Brent", name_en="Brent crude", unit="USD/bbl", subject="BZ=F", display="BZ=F",
         holdings=["PTTEP"], link_th="น้ำมัน → PTTEP",
         drivers_th=["นโยบายการผลิต OPEC+", "สถานการณ์ตะวันออกกลาง / อิหร่าน", "อุปสงค์จีนและเศรษฐกิจโลก", "สต็อกน้ำมันสหรัฐฯ"],
         source="yfinance BZ=F (ICE Brent futures) daily close"),
    dict(key="wti", group=G_ASSETS, name_th="น้ำมันดิบ WTI", name_en="WTI crude", unit="USD/bbl", subject="CL=F", display="CL=F",
         holdings=["PTTEP"], link_th="น้ำมัน → PTTEP",
         drivers_th=["นโยบายการผลิต OPEC+", "สต็อก/การผลิตน้ำมันสหรัฐฯ", "อุปสงค์โลก"],
         source="yfinance CL=F (NYMEX WTI futures) daily close"),
    dict(key="spx", group=G_ASSETS, name_th="หุ้นสหรัฐฯ S&P 500", name_en="S&P 500", unit="index", subject="^GSPC", display="^GSPC", equity=True,
         drivers_th=["ผลประกอบการบริษัท", "ดอกเบี้ย Fed / yield พันธบัตร", "เงินเฟ้อสหรัฐฯ"], source="yfinance ^GSPC daily close"),
    dict(key="ndx", group=G_ASSETS, name_th="หุ้นเทคสหรัฐฯ Nasdaq-100", name_en="Nasdaq-100", unit="index", subject="^NDX", display="^NDX", equity=True,
         drivers_th=["หุ้น AI / เทคยักษ์ใหญ่", "yield 10 ปีสหรัฐฯ", "ผลประกอบการไตรมาส"], source="yfinance ^NDX daily close"),
    dict(key="xlk", group=G_ASSETS, name_th="กองทุนหุ้นเทค XLK", name_en="Tech Select Sector ETF", unit="USD", subject="XLK", display="XLK", equity=True,
         drivers_th=["หุ้นเทคขนาดใหญ่ (Apple, Microsoft, Nvidia)", "yield 10 ปีสหรัฐฯ"], source="yfinance XLK daily close"),
    dict(key="shcomp", group=G_ASSETS, name_th="หุ้นจีน Shanghai Composite", name_en="Shanghai Composite", unit="index", subject="000001.SS", display="000001.SS", equity=True,
         drivers_th=["มาตรการกระตุ้นของรัฐบาลจีน / PBoC", "ภาคอสังหาฯ จีน", "ความสัมพันธ์การค้าสหรัฐฯ–จีน"], source="yfinance 000001.SS daily close"),
    dict(key="csi300", group=G_ASSETS, name_th="หุ้นจีน CSI 300", name_en="CSI 300", unit="index", subject="510300.SS", display="000300.SS", equity=True, scale=True,
         drivers_th=["มาตรการกระตุ้นของรัฐบาลจีน", "กำไรบริษัทจดทะเบียนขนาดใหญ่", "เงินทุนต่างชาติ (Northbound)"],
         proxy_th="พยากรณ์จาก ETF 510300.SS (ติดตาม CSI 300) เพราะ Yahoo ไม่ให้ประวัติดัชนีฟรี; ช่วงของดัชนีคำนวณจาก % ของ ETF",
         source="level: yfinance 000300.SS quote; forecast: 510300.SS daily close (proxy)"),
    dict(key="hstech", group=G_ASSETS, name_th="หุ้นเทคจีน Hang Seng TECH", name_en="Hang Seng TECH", unit="index", subject="3033.HK", display="HSTECH.HK", equity=True, scale=True,
         drivers_th=["กฎระเบียบภาครัฐจีนต่อบริษัทเทค", "การบริโภคในจีน", "ค่าเงิน HKD/ดอกเบี้ยสหรัฐฯ"],
         proxy_th="พยากรณ์จาก ETF 3033.HK (CSOP Hang Seng TECH, ประวัติตั้งแต่ ส.ค. 2020); ช่วงของดัชนีคำนวณจาก % ของ ETF",
         source="level: yfinance HSTECH.HK quote; forecast: 3033.HK daily close (proxy)"),
    dict(key="kweb", group=G_ASSETS, name_th="กองทุนหุ้นอินเทอร์เน็ตจีน KWEB", name_en="KraneShares China Internet", unit="USD", subject="KWEB", display="KWEB", equity=True,
         drivers_th=["Alibaba / Tencent / PDD", "กฎระเบียบจีน", "ความสัมพันธ์สหรัฐฯ–จีน"], source="yfinance KWEB daily close"),
    dict(key="vnindex", group=G_ASSETS, name_th="หุ้นเวียดนาม VN-Index", name_en="VN-Index", unit="index", subject="E1VFVN30.VN", display="^VNINDEX.VN", equity=True, scale=True,
         drivers_th=["การยกระดับเป็นตลาด Emerging (FTSE)", "ส่งออก/FDI เวียดนาม", "สภาพคล่องรายย่อยในประเทศ"],
         proxy_th="พยากรณ์จาก ETF E1VFVN30.VN (ติดตาม VN30 — 30 หุ้นใหญ่ ไม่ใช่ VN-Index ทั้งตลาด); ช่วงของ VN-Index ประมาณจาก % ของ ETF",
         source="level: yfinance ^VNINDEX.VN quote; forecast: E1VFVN30.VN daily close (proxy)"),
    dict(key="set", group=G_ASSETS, name_th="หุ้นไทย SET / SET50", name_en="SET index", unit="index", subject="TDEX.BK", display="^SET.BK", display2="^SET50.BK", equity=True, scale=True,
         holdings=["SCB", "ThaiESG"], link_th="ตลาดหุ้นไทย → SCB และกองทุน ThaiESG",
         drivers_th=["เงินทุนต่างชาติ (fund flow)", "การเมือง/งบประมาณไทย", "ดอกเบี้ย ธปท.", "ราคาน้ำมัน (หุ้นพลังงาน)"],
         proxy_th="พยากรณ์จาก TDEX.BK (ETF ติดตาม SET50) เพราะ Yahoo ไม่ให้ประวัติดัชนี SET ฟรี; ช่วงของ SET คำนวณจาก % ของ TDEX",
         source="level: yfinance ^SET.BK / ^SET50.BK quote; forecast: TDEX.BK daily close (proxy)"),
    dict(key="copper", group=G_ASSETS, name_th="ทองแดง", name_en="Copper", unit="USD/lb", subject="HG=F", display="HG=F",
         drivers_th=["อุตสาหกรรม/อสังหาฯ จีน", "การลงทุนพลังงานสะอาด/EV", "อุปทานเหมือง"], source="yfinance HG=F daily close"),
    dict(key="vix", group=G_ASSETS, name_th="ดัชนีความกลัว VIX", name_en="VIX", unit="index", subject="^VIX", display="^VIX",
         drivers_th=["ข่าวช็อก/ความเสี่ยงภูมิรัฐศาสตร์", "การปรับฐานหุ้นสหรัฐฯ"], source="yfinance ^VIX daily close",
         note_th="VIX ขึ้น = ตลาดกังวลมากขึ้น (มักสวนทางกับหุ้น)"),
    dict(key="us10y", group=G_RATES, name_th="Yield พันธบัตรสหรัฐฯ 10 ปี", name_en="US 10Y Treasury yield", unit="%", subject="^TNX", display="UST10", rate=True,
         holdings=["SCB", "ThaiESG"], link_th="ดอกเบี้ยโลก → มูลค่าหุ้นไทย/SCB",
         drivers_th=["เงินเฟ้อสหรัฐฯ", "นโยบาย Fed", "การขาดดุลงบประมาณ/อุปทานพันธบัตร"],
         source="level: US Treasury daily par yield curve (official); forecast: yfinance ^TNX"),
    dict(key="us2y", group=G_RATES, name_th="Yield พันธบัตรสหรัฐฯ 2 ปี", name_en="US 2Y Treasury yield", unit="%", subject="2YY=F", display="UST2", rate=True,
         drivers_th=["ความคาดหวังต่อดอกเบี้ย Fed", "ตัวเลขเงินเฟ้อ/ตลาดแรงงาน"],
         proxy_th="พยากรณ์จาก 2YY=F (CBOT 2-Year Yield futures, ประวัติตั้งแต่ 2021) — ใกล้เคียงแต่ไม่เท่ากับ yield ทางการ",
         source="level: US Treasury daily par yield curve (official); forecast: yfinance 2YY=F (proxy)"),
    dict(key="usdthb", group=G_FX, name_th="ค่าเงิน USD/THB", name_en="USD/THB", unit="THB/USD", subject="THB=X", display="THB=X",
         holdings=["FX"], link_th="ค่าเงิน → ความเสี่ยงค่าเงินของทั้งพอร์ต (SCBGOLDE ไม่ป้องกันค่าเงิน)",
         drivers_th=["ส่วนต่างดอกเบี้ย Fed–ธปท.", "ดุลบัญชีเดินสะพัด/ท่องเที่ยว", "ราคาทอง (บาทมักเคลื่อนตามทอง)"],
         note_th="ขึ้น = บาทอ่อน", source="yfinance THB=X daily close"),
    dict(key="dxy", group=G_FX, name_th="ดัชนีดอลลาร์ DXY", name_en="US Dollar Index", unit="index", subject="DX-Y.NYB", display="DX-Y.NYB",
         drivers_th=["ส่วนต่างดอกเบี้ยสหรัฐฯ กับประเทศอื่น", "ความเสี่ยงโลก (safe haven)"], source="yfinance DX-Y.NYB daily close"),
    dict(key="btc", group=G_FX, name_th="บิตคอยน์", name_en="Bitcoin", unit="USD", subject="BTC-USD", display="BTC-USD", weekdays=True,
         drivers_th=["เงินไหลเข้า ETF บิตคอยน์", "สภาพคล่อง/ดอกเบี้ยโลก", "กฎระเบียบคริปโต"],
         note_th="ความผันผวนสูงมาก", source="yfinance BTC-USD daily close (weekdays only in the model)"),
]
BY_KEY = {i["key"]: i for i in INDICATORS}
# forecast subjects that the holdings generator (predictions.FACTORS) does not already produce
MACRO_SUBJECTS = sorted({i["subject"] for i in INDICATORS} - set(P.FACTORS))
SUBJECT_TO_KEY = {i["subject"]: i["key"] for i in INDICATORS}

DDL = """
CREATE TABLE IF NOT EXISTS policy_rate_observations (
    id             BIGSERIAL PRIMARY KEY,
    bank           VARCHAR(10) NOT NULL,
    series         VARCHAR(20) NOT NULL,
    obs_date       DATE NOT NULL,
    rate           DOUBLE PRECISION,
    rate_text      TEXT,
    decision_date  DATE,
    last_change_date DATE,
    last_change_bp DOUBLE PRECISION,
    next_meeting   DATE,
    source         TEXT,
    source_url     TEXT,
    status         VARCHAR(10) NOT NULL,
    detail         JSONB,
    retrieved_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (bank, series, obs_date)
);
CREATE TABLE IF NOT EXISTS policy_path_calls (
    id            BIGSERIAL PRIMARY KEY,
    bank          VARCHAR(10) NOT NULL,
    made_on       DATE NOT NULL,
    next_meeting  DATE,
    current_rate  DOUBLE PRECISION NOT NULL,
    expected      VARCHAR(5) NOT NULL CHECK (expected IN ('hold','cut','hike')),
    lean_12m      VARCHAR(5),
    basis         VARCHAR(20) NOT NULL,
    confidence    VARCHAR(6) NOT NULL,
    rationale     JSONB NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (bank, next_meeting, made_on)
);
CREATE TABLE IF NOT EXISTS policy_path_outcomes (
    id          BIGSERIAL PRIMARY KEY,
    call_id     BIGINT NOT NULL UNIQUE REFERENCES policy_path_calls(id),
    scored_on   DATE NOT NULL,
    rate_after  DOUBLE PRECISION NOT NULL,
    actual      VARCHAR(5) NOT NULL,
    hit         BOOLEAN NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS macro_fetch_log (
    id      BIGSERIAL PRIMARY KEY,
    at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    key     VARCHAR(40) NOT NULL,
    ok      BOOLEAN NOT NULL,
    detail  TEXT
);
DO $d$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_policy_path_calls_frozen') THEN
        CREATE TRIGGER trg_policy_path_calls_frozen BEFORE UPDATE OR DELETE ON policy_path_calls
            FOR EACH ROW EXECUTE FUNCTION predictions_immutable();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_policy_path_outcomes_frozen') THEN
        CREATE TRIGGER trg_policy_path_outcomes_frozen BEFORE UPDATE OR DELETE ON policy_path_outcomes
            FOR EACH ROW EXECUTE FUNCTION predictions_immutable();
    END IF;
END $d$;
"""


async def ensure_tables(pool: Any) -> None:
    await P.ensure_tables(pool)  # creates predictions_immutable()
    async with pool.acquire() as conn:
        await conn.execute(DDL)


async def _log(pool: Any, key: str, ok: bool, detail: str) -> None:
    try:
        async with pool.acquire() as conn:
            await conn.execute("INSERT INTO macro_fetch_log (key, ok, detail) VALUES ($1,$2,$3)", key, ok, detail[:2000])
    except Exception:  # noqa: BLE001
        LOGGER.exception("macro_fetch_log insert failed")


# ------------------------------------------------------------------ series helpers
def _series(subj: str, closes: pd.DataFrame) -> Optional[pd.Series]:
    s = P._series_for(subj, closes)
    if s is None:
        return None
    s = s.dropna()
    ind = BY_KEY.get(SUBJECT_TO_KEY.get(subj, ""), {})
    if ind.get("weekdays"):
        s = s[s.index.dayofweek < 5]
    return s


def _price_tickers(subjects: list[str]) -> list[str]:
    out = set()
    for s in subjects:
        if s in P.PROXY:
            out |= set(P.PROXY[s])
        else:
            out.add(s)
    return sorted(out | {"SPY"})


def _beta(ser: pd.Series, bench: Optional[pd.Series]) -> Optional[float]:
    if bench is None:
        return None
    j = pd.concat([ser.pct_change(fill_method=None), bench.pct_change(fill_method=None)], axis=1, join="inner").dropna().iloc[-252:]
    return float(j.iloc[:, 0].cov(j.iloc[:, 1]) / j.iloc[:, 1].var()) if len(j) > 60 and j.iloc[:, 1].var() > 0 else None


def _assumptions(ind: dict[str, Any], mo: dict[str, Any], regime: Optional[str]) -> list[str]:
    a = [f"Volatility stays near the blended EWMA/1y level ({mo['vol_d'] * math.sqrt(252):.1%} annualised); Student-t(5) tails.",
         "No discontinuity (policy shock, war escalation, exchange intervention) beyond what price history already contains.",
         "Momentum / mean-reversion coefficients estimated on this series' own history persist (shrunk 50% toward zero).",
         f"Macro regime '{regime or 'n/a'}' persists (regime model only matters for equity indices)."]
    if ind.get("proxy_th"):
        a.append("Proxy: " + ind["source"] + " — tracking difference between proxy and the headline index is ignored.")
    if ind.get("rate"):
        a.append("Yield modelled in log space (multiplicative moves); a policy surprise can move short yields more than the bands show.")
    if ind.get("weekdays"):
        a.append("Weekend prices dropped so horizons are business days like other assets.")
    return a


# ------------------------------------------------------------------ forecast generation (frozen)
async def generate_macro(pool: Any, force: bool = False) -> dict[str, Any]:
    await ensure_tables(pool)
    today = datetime.now(ICT).date()
    async with pool.acquire() as conn:
        last = {(r["subject"], r["horizon"]): (r["a"], r["m"]) for r in await conn.fetch(
            """SELECT subject, horizon, max(as_of_date) a, max(made_at AT TIME ZONE 'Asia/Bangkok')::date m FROM predictions
               WHERE source='live' AND subject = ANY($1::text[]) GROUP BY 1,2""", MACRO_SUBJECTS)}
        reg = await conn.fetchrow("SELECT regime, score, as_of FROM market_regime ORDER BY as_of DESC LIMIT 1")
    closes = await asyncio.to_thread(download_closes, _price_tickers(MACRO_SUBJECTS), None, "10y", 3600)
    weights = await P.current_weights(pool)
    track = await P.scoreboard(pool, brief=True)
    now = datetime.now(timezone.utc)
    made, skipped = 0, []
    for subj in MACRO_SUBJECTS:
        ind = BY_KEY[SUBJECT_TO_KEY[subj]]
        ser = _series(subj, closes)
        if ser is None or len(ser) < 300:
            skipped.append(subj)
            await _log(pool, f"forecast:{subj}", False, f"insufficient history ({0 if ser is None else len(ser)} rows)")
            continue
        beta = _beta(ser, closes.get("SPY")) if ind.get("equity") else 0.0
        extras = {"regime": reg["regime"] if reg else None, "beta": beta if beta is not None else 1.0, "signal_score": None, "analyst_target": None}
        base = float(ser.iloc[-1])
        as_of = ser.index[-1].date()
        for h, hd in P.HORIZONS.items():
            la, lm = last.get((subj, h), (None, None))
            if not force:
                if not P._due(h, today, lm):
                    continue
                if la is not None and as_of <= la:  # no new close since the last forecast -> nothing new to freeze
                    continue
            mo = P.model_outputs(np.log(ser), hd, extras)
            if "error" in mo:
                continue
            c = P.combine(mo, weights[h], base, hd, weights[h].get("_sigma_scale", 1.0))
            method = {
                "family": FAMILY, "indicator": ind["key"], "model_version": P.MODEL_VERSION,
                "sigma_scale": round(weights[h].get("_sigma_scale", 1.0), 4),
                "confidence_def": "|2*P(up)-1| x (0.5+0.5*model sign agreement); <0.1 low, 0.1-0.3 medium, >0.3 high",
                "ensemble": "weighted mean of model expected log-returns (drift, momentum, mean-reversion, regime); Student-t(5) bands",
                "models": {k: (round(v, 6) if v is not None else None) for k, v in mo["models"].items()},
                "weights_used": c["used_weights"], "weights_source": "prediction_model_weights (shared learning loop) or prior",
                "model_diagnostics": {k: (round(v, 6) if isinstance(v, float) else v) for k, v in mo["diag"].items()},
                "agreement": round(c["agreement"], 3),
                "inputs": {"price": {"value": base, "as_of": str(as_of), "source": ind["source"]},
                           "beta_vs_SPY": round(beta, 3) if isinstance(beta, float) else None,
                           "regime": {"value": reg["regime"] if reg else None, "as_of": str(reg["as_of"]) if reg else None, "source": "signals.compute_regime"}},
                "proxy": ind.get("proxy_th"), "drivers_th": ind.get("drivers_th"),
                "assumptions": _assumptions(ind, mo, reg["regime"] if reg else None),
                "track_record_at_creation": (track.get("by_horizon") or {}).get(h),
            }
            rec = {"version": P.MODEL_VERSION, "source": "live", "subject": subj, "subject_type": "factor", "horizon": h, "horizon_days": hd,
                   "made_at": now.isoformat(), "as_of_date": str(as_of), "target_date": str(P.target_date(as_of, hd)),
                   "base_price": base, "direction": c["direction"], "p_up": round(c["p_up"], 4), "exp_return": round(c["mu"], 6),
                   "sigma": round(c["sigma"], 6), "median_price": c["median"], "bands": [c["b50"], c["b80"], c["b95"]],
                   "confidence": c["confidence"], "method": method}
            made += int(await P._insert(pool, rec))
    return {"made": made, "subjects": len(MACRO_SUBJECTS), "skipped": skipped}


def _backfill_sync(closes: pd.DataFrame, subjects: list[str], years: int = 3) -> list[dict[str, Any]]:
    """Walk-forward history (data <= each as-of only; prior weights) - same design as predictions._backfill_sync."""
    recs = []
    for subj in subjects:
        ind = BY_KEY[SUBJECT_TO_KEY[subj]]
        ser_full = _series(subj, closes)
        if ser_full is None or len(ser_full) < 600:
            continue
        lp_full = np.log(ser_full)
        end = ser_full.index[-1]
        idx = ser_full.index[ser_full.index >= end - pd.DateOffset(years=years)]
        weekly = idx[::5]
        monthly = pd.DatetimeIndex(pd.Series(idx, index=idx).groupby(idx.to_period("M")).first().values)
        spy = closes.get("SPY")
        for h, hd in P.HORIZONS.items():
            for d in (weekly if h in ("3d", "1m") else monthly):
                if (pd.Timestamp(d) + pd.offsets.BDay(hd)) > end:
                    continue
                lp = lp_full.loc[:d]
                if len(lp) < 400:
                    continue
                reg = None
                if spy is not None and ind.get("equity"):
                    ss = spy.loc[:d].dropna()
                    reg = ("risk_on" if ss.iloc[-1] > ss.iloc[-200:].mean() else "risk_off") if len(ss) > 200 else None
                mo = P.model_outputs(lp, hd, {"regime": reg, "beta": 1.0 if ind.get("equity") else 0.0})
                if "error" in mo:
                    continue
                base = float(np.exp(lp.iloc[-1]))
                c = P.combine(mo, P.PRIOR_W, base, hd)
                as_of = lp.index[-1].date()
                recs.append({"source": "backfill", "subject": subj, "subject_type": "factor", "horizon": h, "horizon_days": hd,
                             "made_at": datetime.combine(as_of, datetime.min.time(), timezone.utc).isoformat(),
                             "as_of_date": str(as_of), "target_date": str(P.target_date(as_of, hd)), "base_price": base,
                             "direction": c["direction"], "p_up": round(c["p_up"], 4), "exp_return": round(c["mu"], 6),
                             "sigma": round(c["sigma"], 6), "median_price": c["median"], "bands": [c["b50"], c["b80"], c["b95"]],
                             "confidence": c["confidence"],
                             "method": {"family": FAMILY, "indicator": ind["key"],
                                        "ensemble": "backfill walk-forward, prior weights, price-only models",
                                        "models": {k: (round(v, 6) if v is not None else None) for k, v in mo["models"].items()},
                                        "weights_used": c["used_weights"],
                                        "inputs": {"price": {"value": base, "as_of": str(as_of), "source": ind["source"] + " (historical)"},
                                                   "regime": {"value": reg, "source": "SPY vs SMA200 (backfill proxy, equities only)"}},
                                        "model_diagnostics": {k: (round(v, 6) if isinstance(v, float) else v) for k, v in mo["diag"].items()},
                                        "assumptions": ["historical simulation; data <= as-of date only"]}})
    return recs


async def backfill_macro(pool: Any, years: int = 3) -> dict[str, Any]:
    await ensure_tables(pool)
    async with pool.acquire() as conn:
        have = {r["subject"] for r in await conn.fetch(
            "SELECT DISTINCT subject FROM predictions WHERE source='backfill' AND subject = ANY($1::text[])", MACRO_SUBJECTS)}
    todo = [s for s in MACRO_SUBJECTS if s not in have]
    if not todo:
        return {"skipped": "macro backfill already present (predictions are immutable)"}
    closes = await asyncio.to_thread(download_closes, _price_tickers(MACRO_SUBJECTS), None, "10y", 3600)
    recs = await asyncio.to_thread(_backfill_sync, closes, todo, years)
    made = 0
    for rec in recs:
        made += int(await P._insert(pool, rec))
    val = await P.validate_matured(pool, closes)
    w = await P.learn(pool)
    return {"subjects": todo, "backfill_predictions": made, "validated": val, "weights": w}


# ------------------------------------------------------------------ official / free fetchers (never invent)
def _post_json(url: str, referer: str, timeout: float = 20) -> Any:
    req = urllib.request.Request(url, data=b"", method="POST", headers={"User-Agent": UA, "Referer": referer, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _text(url: str) -> str:
    s = html_mod.unescape(http_bytes(url).decode("utf-8", "replace"))  # BoT embeds escaped HTML inside JSON attributes
    s = s.replace("\\r\\n", " ").replace('\\"', '"').replace("\\/", "/")
    s = html_mod.unescape(re.sub(r"<[^>]+>", " ", s)).replace("\xa0", " ")
    return re.sub(r"\s+", " ", s)


_MON = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def treasury_curve() -> dict[str, Any]:
    """Official US Treasury daily par yield curve (CSV, free)."""
    rows: list[dict[str, Any]] = []
    y = datetime.now(ICT).year
    for yr in (y, y - 1):
        url = (f"https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/{yr}/all"
               f"?type=daily_treasury_yield_curve&field_tdr_date_value={yr}&page&_format=csv")
        rd = csv.DictReader(io.StringIO(http_bytes(url).decode("utf-8", "replace")))
        for r in rd:
            try:
                rows.append({"date": datetime.strptime(r["Date"], "%m/%d/%Y").date(),
                             **{k: float(v) for k, v in r.items() if k != "Date" and v not in ("", None, "N/A")}})
            except ValueError:
                continue
        if len(rows) >= 140:
            break
    rows.sort(key=lambda r: r["date"])
    if not rows:
        raise RuntimeError("Treasury CSV empty")
    return {"rows": rows, "source": "U.S. Department of the Treasury - Daily Treasury Par Yield Curve Rates",
            "source_url": "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve"}


def us_cpi() -> dict[str, Any]:
    d = http_json("https://api.bls.gov/publicAPI/v1/timeseries/data/CUUR0000SA0")
    obs = []
    for o in d["Results"]["series"][0]["data"]:
        if o["period"].startswith("M") and o["period"] != "M13" and re.fullmatch(r"[\d.]+", o.get("value") or ""):  # '-' = not published
            obs.append((date(int(o["year"]), int(o["period"][1:]), 1), float(o["value"])))
    obs.sort()
    m = dict(obs)
    yoy = [(dt, (v / m[date(dt.year - 1, dt.month, 1)] - 1) * 100) for dt, v in obs if date(dt.year - 1, dt.month, 1) in m]
    if not yoy:
        raise RuntimeError("BLS CPI: not enough months for y/y")
    return {"latest_month": yoy[-1][0].isoformat()[:7], "yoy": round(yoy[-1][1], 2), "series": [(d.isoformat()[:7], round(v, 2)) for d, v in yoy[-13:]],
            "source": "BLS CPI-U all items, not seasonally adjusted (CUUR0000SA0), public API v1",
            "source_url": "https://data.bls.gov/timeseries/CUUR0000SA0"}


def fed_policy(today: date) -> dict[str, Any]:
    d = sorted(http_json("https://markets.newyorkfed.org/api/rates/unsecured/effr/last/5.json")["refRates"], key=lambda x: x["effectiveDate"])
    last = d[-1]
    lo, hi = float(last["targetRateFrom"]), float(last["targetRateTo"])
    out: dict[str, Any] = {"bank": "FED", "series": "target_range", "rate": (lo + hi) / 2, "rate_text": f"{lo:.2f}–{hi:.2f}%",
                           "target_low": lo, "target_high": hi, "effr": float(last["percentRate"]), "effr_date": last["effectiveDate"],
                           "source": "NY Fed EFFR API (target range) + federalreserve.gov open-market & FOMC calendar pages",
                           "source_url": "https://www.federalreserve.gov/monetarypolicy/openmarket.htm"}
    # last change (effective date) from the Fed's own table
    t = _text("https://www.federalreserve.gov/monetarypolicy/openmarket.htm")
    changes = []
    for blk in re.finditer(r"(\d{4}) Date Increase Decrease Level \(%\) (.*?) Back to year navigation", t):
        yr = int(blk.group(1))
        for m in re.finditer(r"([A-Z][a-z]+) (\d{1,2}) (\d+) (\d+) ([\d.]+-[\d.]+)", blk.group(2)):
            try:
                dt = datetime.strptime(f"{m.group(1)} {m.group(2)} {yr}", "%B %d %Y").date()
            except ValueError:
                continue
            changes.append((dt, int(m.group(3)) - int(m.group(4)), m.group(5)))
    changes.sort()
    if changes:
        out["last_change_date"], out["last_change_bp"] = changes[-1][0], float(changes[-1][1])
        out["last_change_level"] = changes[-1][2]
        out["recent_changes"] = [(c[0].isoformat(), c[1], c[2]) for c in changes[-4:]]
    # meetings (decision = last day of the meeting)
    t2 = _text("https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm")
    meetings = []
    for blk in re.finditer(r"(\d{4}) FOMC Meetings (.*?)(?=\d{4} FOMC Meetings|$)", t2):
        yr = int(blk.group(1))
        for m in re.finditer(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)(?:/(\w+))? (\d{1,2})(?:-(\d{1,2}))?\*?", blk.group(2)[:6000]):
            mon = m.group(2) or m.group(1)
            day = m.group(4) or m.group(3)
            try:
                meetings.append(datetime.strptime(f"{mon} {day} {yr}", "%B %d %Y").date())
            except ValueError:
                continue
    meetings = sorted(set(meetings))
    past = [m for m in meetings if m <= today]
    fut = [m for m in meetings if m > today]
    out["last_meeting"] = past[-1] if past else None
    out["next_meeting"] = fut[0] if fut else None
    if out.get("last_change_date"):
        dec = [m for m in meetings if m < out["last_change_date"]]
        out["decision_date"] = dec[-1] if dec and (out["last_change_date"] - dec[-1]).days <= 3 else None
    if out.get("last_meeting") and out.get("last_change_date"):
        out["last_meeting_outcome"] = "change" if out["last_change_date"] > out["last_meeting"] else "hold"
    return out


def bot_policy(today: date) -> dict[str, Any]:
    import watchlists as wl
    r = wl._bot_policy_rate(recent_n=40)
    rec = (r.get("details") or {}).get("recent") or []
    out = {"bank": "BOT", "series": "policy_rate", "rate": float(r["reading"]), "rate_text": f"{float(r['reading']):.2f}%",
           "decision_date": r["as_of"].date(), "source": r["source"], "source_url": r["source_url"], "recent": rec[-6:],
           "decision_text": r.get("reading_text")}
    ch = [(date.fromisoformat(d), rt) for d, rt, _ in rec]
    for i in range(len(ch) - 1, 0, -1):
        if abs(ch[i][1] - ch[i - 1][1]) > 1e-9:
            out["last_change_date"], out["last_change_bp"] = ch[i][0], round((ch[i][1] - ch[i - 1][1]) * 100, 1)
            break
    t = _text("https://www.bot.or.th/en/our-roles/monetary-policy/mpc-meeting.html")
    dates = []
    for y in re.finditer(r"Schedule (\d{4}) (.*?)(?=Schedule \d{4}|$)", t):
        for m in re.finditer(r"(?:^|\s)(\d) +Wed\. *(\d{1,2}) *([A-Z][a-z]{2})\.? *(\d{4})", y.group(2)[:4000]):
            try:
                dates.append(date(int(m.group(4)), _MON[m.group(3).lower()], int(m.group(2))))
            except (KeyError, ValueError):
                continue
    fut = sorted(d for d in set(dates) if d > today)
    out["next_meeting"] = fut[0] if fut else None
    out["schedule_source"] = "https://www.bot.or.th/en/our-roles/monetary-policy/mpc-meeting.html"
    return out


def pboc_lpr(today: date) -> dict[str, Any]:
    ref = "https://www.chinamoney.com.cn/english/bmkcpr/"
    d = http_json("https://www.chinamoney.com.cn/r/cms/www/chinamoney/data/currency/bk-lpr.json", headers={"Referer": ref})
    recs = {r["termCode"]: r for r in d.get("records") or []}
    one, five = float(recs["1Y"]["shibor"]), float(recs["5Y"]["shibor"])
    pub = datetime.strptime(d["data"]["showDateCN"][:10], "%Y-%m-%d").date()
    out = {"bank": "PBOC", "series": "lpr_1y", "rate": one, "rate_5y": five, "rate_text": f"LPR 1Y {one:.2f}% · 5Y {five:.2f}%",
           "decision_date": pub, "updown": {k: v.get("shibIdUpDown") for k, v in recs.items()},
           "source": "China Foreign Exchange Trade System (chinamoney.com.cn) LPR, published monthly on the 20th",
           "source_url": "https://www.chinamoney.com.cn/english/bmklpr/"}
    try:  # change history (best effort; endpoint is rate limited)
        hist = []
        for start, end in ((today - timedelta(days=365), today), (today - timedelta(days=730), today - timedelta(days=366))):
            j = _post_json(f"https://www.chinamoney.com.cn/ags/ms/cm-u-bk-currency/LprHis?lang=CN&strStartDate={start}&strEndDate={end}", ref)
            hist += [(date.fromisoformat(x["showDateCN"]), float(x["1Y"]), float(x["5Y"])) for x in j.get("records") or []]
            time.sleep(1.5)
        hist.sort()
        for i in range(len(hist) - 1, 0, -1):
            if (hist[i][1], hist[i][2]) != (hist[i - 1][1], hist[i - 1][2]):
                out["last_change_date"] = hist[i][0]
                out["last_change_bp"] = round((hist[i][1] - hist[i - 1][1]) * 100, 1)
                out["last_change_bp_5y"] = round((hist[i][2] - hist[i - 1][2]) * 100, 1)
                break
        if hist and "last_change_date" not in out:
            out["unchanged_since_at_least"] = hist[0][0]
        out["history_points"] = len(hist)
    except Exception as exc:  # noqa: BLE001
        out["history_error"] = str(exc)[:200]
    nm = date(today.year, today.month, 20)
    if nm <= today:
        nm = date(today.year + (today.month == 12), today.month % 12 + 1, 20)
    out["next_meeting"] = nm  # LPR fixing date (20th; moved to next business day on holidays - not adjusted here)
    out["next_meeting_note"] = "LPR is fixed on the 20th of each month (next business day if a holiday)"
    return out


# ------------------------------------------------------------------ expected path (labelled)
def _fed_path(f: dict[str, Any], curve: Optional[dict[str, Any]]) -> dict[str, Any]:
    if not curve:
        return {"expected": None, "basis": "unknown", "confidence": "-", "rationale_th": ["ไม่มีข้อมูล yield ทางการ — ไม่ประเมิน"]}
    r = curve["rows"][-1]
    t3, t2 = r.get("3 Mo"), r.get("2 Yr")
    mid, effr = f["rate"], f["effr"]
    s3 = t3 - effr if t3 is not None else None
    s2 = t2 - mid if t2 is not None else None
    exp = "hold" if s3 is None or abs(s3) <= 0.15 else ("hike" if s3 > 0 else "cut")
    lean = None if s2 is None else ("hike" if s2 > 0.35 else "cut" if s2 < -0.35 else "hold")
    th = {"hold": "คงดอกเบี้ย", "hike": "ขึ้นดอกเบี้ย", "cut": "ลดดอกเบี้ย"}
    rat = [f"T-bill 3 เดือน {t3:.2f}% เทียบ EFFR {effr:.2f}% (ส่วนต่าง {s3 * 100:+.0f} bp) → ตลาดคาดว่า{th[exp]}ในการประชุมถัดไป" if s3 is not None else "ไม่มี T-bill 3 เดือน",
           f"Yield 2 ปี {t2:.2f}% เทียบกึ่งกลางกรอบ {mid:.3f}% ({s2 * 100:+.0f} bp) → แนวโน้ม 12 เดือน: {th[lean]}" if s2 is not None else "ไม่มี yield 2 ปี",
           f"ข้อมูล yield ณ {r['date']} (กระทรวงการคลังสหรัฐฯ)"]
    return {"expected": exp, "lean_12m": lean, "basis": "market_implied", "confidence": "medium",
            "basis_th": "ประเมินจากราคาตลาด (ส่วนต่าง T-bill/Yield 2 ปี กับดอกเบี้ยนโยบาย) — ประมาณการหยาบ ไม่ใช่ CME FedWatch",
            "rationale_th": rat, "inputs": {"t3m": t3, "t2y": t2, "effr": effr, "mid": mid, "curve_date": str(r["date"])}}


def _heuristic_path(bank: str, last_change_bp: Optional[float], last_change_date: Optional[date], today: date,
                    extra_th: list[str]) -> dict[str, Any]:
    recent = last_change_date is not None and (today - last_change_date).days <= 200
    lean = None
    if recent and last_change_bp:
        lean = "cut" if last_change_bp < 0 else "hike"
    rat = []
    if last_change_date:
        rat.append(f"เปลี่ยนแปลงครั้งล่าสุด {last_change_bp:+.0f} bp เมื่อ {last_change_date:%d/%m/%Y}")
    else:
        rat.append("ไม่ทราบวันที่เปลี่ยนแปลงครั้งล่าสุด (ดึงประวัติไม่ได้)")
    rat.append("ธนาคารกลางมักคงดอกเบี้ยในการประชุมส่วนใหญ่ → ค่าตั้งต้น = คงดอกเบี้ย" + (f"; ทิศทางรอบล่าสุดคือ{'ลด' if lean == 'cut' else 'ขึ้น'} (เอนเอียงต่อ 12 เดือน)" if lean else ""))
    rat += extra_th
    return {"expected": "hold", "lean_12m": lean or "hold", "basis": "model_heuristic", "confidence": "low",
            "basis_th": "ประเมินด้วยกฎง่าย ๆ (ไม่มีข้อมูลตลาดที่บ่งชี้ดอกเบี้ยแบบฟรี) — ความเชื่อมั่นต่ำ", "rationale_th": rat}


async def refresh_policy(pool: Any) -> dict[str, Any]:
    await ensure_tables(pool)
    today = datetime.now(ICT).date()
    res: dict[str, Any] = {}
    curve = None
    try:
        curve = await asyncio.to_thread(treasury_curve)
        await _log(pool, "treasury_curve", True, f"{len(curve['rows'])} rows to {curve['rows'][-1]['date']}")
    except Exception as exc:  # noqa: BLE001
        await _log(pool, "treasury_curve", False, str(exc))
    for name, fn in (("FED", fed_policy), ("BOT", bot_policy), ("PBOC", pboc_lpr)):
        try:
            res[name] = await asyncio.to_thread(fn, today)
            res[name]["status"] = "ok"
            await _log(pool, f"policy:{name}", True, res[name]["rate_text"])
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("policy rate %s unavailable: %s", name, exc)
            await _log(pool, f"policy:{name}", False, str(exc))
            res[name] = {"bank": name, "status": "unknown", "error": str(exc)[:200]}
    fed = res["FED"]
    bot = res["BOT"]
    if fed.get("status") == "ok":
        fed["path"] = _fed_path(fed, curve)
    if bot.get("status") == "ok":
        extra = []
        if fed.get("status") == "ok":
            extra.append(f"ส่วนต่างดอกเบี้ย Fed–ธปท. {fed['rate'] - bot['rate']:+.2f} จุด → กดดันให้บาทอ่อนถ้าส่วนต่างกว้างขึ้น")
        extra.append("ไม่มีข้อมูลเงินเฟ้อไทย/ตลาดพันธบัตรไทยแบบฟรีในระบบ — ยังไม่ใช้ในการประเมิน")
        bot["path"] = _heuristic_path("BOT", bot.get("last_change_bp"), bot.get("last_change_date"), today, extra)
    pb = res["PBOC"]
    if pb.get("status") == "ok":
        extra = [f"LPR 5 ปี {pb['rate_5y']:.2f}% (อ้างอิงสินเชื่อบ้าน)", "อัตรา 7-day reverse repo (ดอกเบี้ยนโยบายหลักของ PBoC) ยังไม่ได้ดึงข้อมูล — unknown"]
        if pb.get("unchanged_since_at_least"):
            extra.insert(0, f"ไม่เปลี่ยนแปลงตั้งแต่อย่างน้อย {pb['unchanged_since_at_least']:%d/%m/%Y}")
        pb["path"] = _heuristic_path("PBOC", pb.get("last_change_bp"), pb.get("last_change_date"), today, extra)
    async with pool.acquire() as conn:
        for name, r in res.items():
            series = r.get("series") or {"FED": "target_range", "BOT": "policy_rate", "PBOC": "lpr_1y"}[name]
            detail = {k: v for k, v in r.items() if k not in ("bank", "series", "rate", "rate_text", "decision_date", "last_change_date",
                                                              "last_change_bp", "next_meeting", "source", "source_url", "status")}
            await conn.execute(
                """INSERT INTO policy_rate_observations (bank, series, obs_date, rate, rate_text, decision_date, last_change_date, last_change_bp,
                       next_meeting, source, source_url, status, detail)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13::jsonb) ON CONFLICT (bank, series, obs_date) DO NOTHING""",
                name, series, today, r.get("rate"), r.get("rate_text"), r.get("decision_date"), r.get("last_change_date"), r.get("last_change_bp"),
                r.get("next_meeting"), r.get("source"), r.get("source_url"), r["status"], json.dumps(detail, default=str))
            pth = r.get("path") or {}
            if r["status"] == "ok" and pth.get("expected"):
                await conn.execute(
                    """INSERT INTO policy_path_calls (bank, made_on, next_meeting, current_rate, expected, lean_12m, basis, confidence, rationale)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb) ON CONFLICT (bank, next_meeting, made_on) DO NOTHING""",
                    name, today, r.get("next_meeting"), r["rate"], pth["expected"], pth.get("lean_12m"), pth["basis"], pth["confidence"],
                    json.dumps(pth, default=str, ensure_ascii=False))
    scored = await score_policy_calls(pool, res)
    _CACHE["policy"] = (time.time(), res, curve)
    return {"banks": {k: v.get("status") for k, v in res.items()}, "scored": scored}


async def score_policy_calls(pool: Any, current: dict[str, Any]) -> int:
    today = datetime.now(ICT).date()
    n = 0
    async with pool.acquire() as conn:
        calls = await conn.fetch("""SELECT c.* FROM policy_path_calls c LEFT JOIN policy_path_outcomes o ON o.call_id = c.id
                                    WHERE o.id IS NULL AND c.next_meeting IS NOT NULL AND c.next_meeting + 2 <= $1""", today)
        for c in calls:
            cur = current.get(c["bank"]) or {}
            if cur.get("status") != "ok":
                continue
            diff = float(cur["rate"]) - float(c["current_rate"])
            actual = "hold" if abs(diff) < 1e-6 else ("hike" if diff > 0 else "cut")
            r = await conn.execute("""INSERT INTO policy_path_outcomes (call_id, scored_on, rate_after, actual, hit)
                                      VALUES ($1,$2,$3,$4,$5) ON CONFLICT (call_id) DO NOTHING""",
                                   c["id"], today, float(cur["rate"]), actual, actual == c["expected"])
            n += int(r.endswith("1"))
    return n


# ------------------------------------------------------------------ board
_CACHE: dict[str, Any] = {}
DIR_TH = {"up": "ขึ้น", "down": "ลง", "flat": "ทรงตัว"}
CONF_TH = {"low": "ต่ำ", "medium": "กลาง", "high": "สูง"}


def _dir(p_up: float) -> str:
    return "up" if p_up >= 0.55 else "down" if p_up <= 0.45 else "flat"


def _conf(c: float) -> str:
    return "low" if c < 0.1 else "medium" if c < 0.3 else "high"


def _reason_th(p: dict[str, Any], ind: dict[str, Any]) -> str:
    m = (p.get("method") or {}).get("models") or {}
    sig = float(p.get("sigma") or 0) or 1e-9
    bits = []
    mom, mr, dr = m.get("momentum"), m.get("meanrev"), m.get("drift")
    if mom is not None and abs(mom) / sig > 0.03:
        bits.append("โมเมนตัมเป็น" + ("ขาขึ้น" if mom > 0 else "ขาลง"))
    if mr is not None and abs(mr) / sig > 0.03:
        bits.append("ราคา" + ("ต่ำกว่าเส้นเฉลี่ย มีแรงดีดกลับ" if mr > 0 else "สูงกว่าเส้นเฉลี่ย มีแรงย่อ"))
    if dr is not None and abs(dr) / sig > 0.03:
        bits.append("แนวโน้มระยะยาว" + ("เป็นบวก" if dr > 0 else "เป็นลบ"))
    if not bits:
        bits.append("สัญญาณแต่ละโมเดลอ่อน/ขัดกัน")
    vol = ((p.get("method") or {}).get("model_diagnostics") or {})
    v = 0.5 * (vol.get("ewma_vol_d") or 0) + 0.5 * (vol.get("vol_1y_d") or 0)
    if v:
        bits.append(f"ความผันผวน ~{v * math.sqrt(252) * 100:.0f}%/ปี")
    return " · ".join(bits)


async def _stats(pool: Any, subjects: list[str]) -> dict[tuple, dict[str, Any]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch("""SELECT p.subject, p.horizon, p.source, count(*) n, avg(o.direction_hit::int)::float hit, avg(o.in80::int)::float c80
                                   FROM prediction_outcomes o JOIN predictions p ON p.id=o.prediction_id
                                   WHERE p.subject = ANY($1::text[]) GROUP BY 1,2,3""", subjects)
        pend = await conn.fetch("""SELECT p.subject, p.horizon, count(*) n FROM predictions p LEFT JOIN prediction_outcomes o ON o.prediction_id=p.id
                                   WHERE o.id IS NULL AND p.source='live' AND p.subject = ANY($1::text[]) GROUP BY 1,2""", subjects)
    out: dict[tuple, dict[str, Any]] = {}
    for r in rows:
        out.setdefault((r["subject"], r["horizon"]), {})[r["source"]] = {"n": r["n"], "hit": round(r["hit"], 3), "cov80": round(r["c80"], 3)}
    for r in pend:
        out.setdefault((r["subject"], r["horizon"]), {})["pending_live"] = r["n"]
    return out


def _chg(s: pd.Series, n: int, rate: bool) -> Optional[float]:
    s = s.dropna()
    if len(s) <= n:
        return None
    a, b = float(s.iloc[-1]), float(s.iloc[-1 - n])
    return round(a - b, 4) if rate else round((a / b - 1) * 100, 3)


async def build_board(pool: Any, max_age: int = 1800) -> dict[str, Any]:
    hit = _CACHE.get("board")
    if hit and time.time() - hit[0] < max_age:
        return hit[1]
    await ensure_tables(pool)
    disp = sorted({i["display"] for i in INDICATORS if i["display"] not in ("XAUTHB", "UST2", "UST10")} | {i["display2"] for i in INDICATORS if i.get("display2")}
                  | {i["subject"] for i in INDICATORS if i["subject"] not in P.PROXY} | {"GC=F", "THB=X"})
    closes = await asyncio.to_thread(download_closes, disp, None, "1y", 1800)
    pol = _CACHE.get("policy")
    if not pol or time.time() - pol[0] > 6 * 3600:
        await refresh_policy(pool)
        pol = _CACHE.get("policy")
    _, policy, curve = pol
    subjects = [i["subject"] for i in INDICATORS]
    preds: dict[tuple, dict[str, Any]] = {}
    for s in subjects:
        for p in await P.latest_predictions(pool, s, with_method=True):
            preds[(s, p["horizon"])] = p
    stats = await _stats(pool, subjects)
    cards = []
    for ind in INDICATORS:
        subj = ind["subject"]
        ps = _series(subj, closes) if subj in P.PROXY or subj in closes else None
        if ind["display"] in ("UST2", "UST10"):
            col = "2 Yr" if ind["display"] == "UST2" else "10 Yr"
            ds = pd.Series({pd.Timestamp(r["date"]): r[col] for r in (curve or {}).get("rows", []) if col in r}, dtype=float)
            dsrc = (curve or {}).get("source", "unknown")
        elif ind["display"] == "XAUTHB":
            ds, dsrc = ps, ind["source"]
        else:
            ds = closes[ind["display"]].dropna() if ind["display"] in closes else pd.Series(dtype=float)
            dsrc = ind["source"]
        value = float(ds.iloc[-1]) if ds is not None and len(ds) else None
        as_of = ds.index[-1].date().isoformat() if ds is not None and len(ds) else None
        spark_s, spark_src = (ds, "display") if ds is not None and len(ds) >= 30 else (ps, "proxy") if ps is not None else (None, None)
        chg_s = spark_s
        rate = bool(ind.get("rate"))
        card: dict[str, Any] = {
            "key": ind["key"], "group": ind["group"], "name_th": ind["name_th"], "name_en": ind["name_en"], "unit": ind["unit"],
            "value": value, "as_of": as_of, "value_source": dsrc, "forecast_subject": subj, "proxy_th": ind.get("proxy_th"),
            "holdings": ind.get("holdings") or [], "link_th": ind.get("link_th"), "note_th": ind.get("note_th"),
            "drivers_th": ind.get("drivers_th") or [], "is_rate": rate,
            "change_1d": _chg(chg_s, 1, rate) if chg_s is not None else None, "change_1m": _chg(chg_s, 21, rate) if chg_s is not None else None,
            "change_basis": "pp" if rate else "%", "change_from": spark_src,
            "spark": [round(float(v), 4) for v in spark_s.dropna().iloc[-120:]] if spark_s is not None else [], "spark_src": spark_src,
        }
        if value is None:
            card["value_status"] = "unknown"
        if ind.get("display2") and ind["display2"] in closes:
            s2 = closes[ind["display2"]].dropna()
            if len(s2):
                card["value2"] = {"label": "SET50", "value": float(s2.iloc[-1]), "as_of": s2.index[-1].date().isoformat()}
        scale = (value / float(ps.iloc[-1])) if ind.get("scale") and value and ps is not None and len(ps) else 1.0
        if ind["display"] in ("UST2", "UST10") and ps is not None and len(ps) and value:
            scale = value / float(ps.iloc[-1])  # show forecast range on the official yield level
        hz = []
        for h in P.HORIZONS:
            p = preds.get((subj, h))
            st = stats.get((subj, h), {})
            live, back = st.get("live"), st.get("backfill")
            if not p:
                hz.append({"horizon": h, "status": "none"})
                continue
            d = _dir(float(p["p_up"]))
            hz.append({
                "horizon": h, "direction": d, "direction_th": DIR_TH[d], "p_up": p["p_up"],
                "median": p["median_price"] * scale, "low80": p["band80_low"] * scale, "high80": p["band80_high"] * scale,
                "low50": p["band50_low"] * scale, "high50": p["band50_high"] * scale,
                "exp_change_pct": round((math.exp(float(p["exp_return"])) - 1) * 100, 2),
                "confidence": p["confidence"], "confidence_lvl": _conf(float(p["confidence"])), "confidence_th": CONF_TH[_conf(float(p["confidence"]))],
                "scaled_from_proxy": scale != 1.0, "base_price": p["base_price"], "made_at": p["made_at"], "as_of_date": p["as_of_date"],
                "target_date": p["target_date"], "sha": p["payload_sha256"][:12], "reason_th": _reason_th(p, ind),
                "assumptions": (p.get("method") or {}).get("assumptions") or [], "models": (p.get("method") or {}).get("models"),
                "weights": (p.get("method") or {}).get("weights_used"),
                "live_track": live, "backtest_track": back, "pending_live": st.get("pending_live", 0),
                "validation_th": (f"live: ทาย{'ถูก'} {live['hit']:.0%} จาก {live['n']} ครั้ง" if live else "ใหม่ — ยังไม่ผ่านการตรวจกับราคาจริง"),
            })
        card["horizons"] = hz
        h1 = next((x for x in hz if x.get("horizon") == "1m" and x.get("direction")), None)
        card["summary_th"] = (f"1 เดือน: {h1['direction_th']} (ช่วง 80% {_n(h1['low80'])}–{_n(h1['high80'])}), ความมั่นใจ{h1['confidence_th']} — {h1['reason_th']}"
                              if h1 else "ยังไม่มีการพยากรณ์")
        cards.append(card)
    # CPI info card (no forecast)
    try:
        cpi = await asyncio.to_thread(us_cpi)
        ser = cpi["series"]
        tr = "up" if len(ser) >= 4 and ser[-1][1] > ser[-4][1] + 0.1 else "down" if len(ser) >= 4 and ser[-1][1] < ser[-4][1] - 0.1 else "flat"
        cards.append({"key": "us_cpi", "group": G_RATES, "name_th": "เงินเฟ้อสหรัฐฯ (CPI y/y)", "name_en": "US CPI y/y", "unit": "% y/y",
                      "value": cpi["yoy"], "as_of": cpi["latest_month"], "value_source": cpi["source"], "is_rate": True, "info_only": True,
                      "spark": [v for _, v in ser], "spark_src": "display", "trend_3m": tr, "trend_3m_th": DIR_TH[tr],
                      "change_1m": round(ser[-1][1] - ser[-2][1], 2) if len(ser) > 1 else None, "change_basis": "pp",
                      "drivers_th": ["ราคาพลังงาน", "ค่าเช่าที่อยู่อาศัย", "ค่าจ้าง"], "holdings": [], "horizons": [],
                      "summary_th": f"เงินเฟ้อ {cpi['yoy']:.1f}% ({cpi['latest_month']}); 3 เดือนล่าสุด{DIR_TH[tr]} — แสดงข้อมูลเท่านั้น ไม่ได้พยากรณ์",
                      "link_th": "เงินเฟ้อ → ทิศทาง Fed → yield/ทอง/บาท"})
    except Exception as exc:  # noqa: BLE001
        await _log(pool, "us_cpi", False, str(exc))
        cards.append({"key": "us_cpi", "group": G_RATES, "name_th": "เงินเฟ้อสหรัฐฯ (CPI y/y)", "value": None, "value_status": "unknown",
                      "info_only": True, "horizons": [], "spark": [], "summary_th": "ดึงข้อมูลไม่ได้ (unknown)", "holdings": []})
    pol_cards = []
    names = {"FED": ("ดอกเบี้ยนโยบาย Fed (สหรัฐฯ)", "US Fed funds target"), "BOT": ("ดอกเบี้ยนโยบาย ธปท. (ไทย)", "Bank of Thailand policy rate"),
             "PBOC": ("ดอกเบี้ย LPR ธนาคารกลางจีน", "PBoC Loan Prime Rate")}
    hold_links = {"FED": "ดอกเบี้ยสหรัฐฯ → ทอง (SCBGOLDE), ค่าเงินบาท", "BOT": "ดอกเบี้ยไทย → SCB (ส่วนต่างดอกเบี้ยธนาคาร), ThaiESG, ค่าเงินบาท",
                  "PBOC": "นโยบายจีน → หุ้นจีน/ราคาสินค้าโภคภัณฑ์ (น้ำมัน → PTTEP)"}
    for b, r in policy.items():
        pth = r.get("path") or {}
        pol_cards.append({"key": b.lower(), "bank": b, "name_th": names[b][0], "name_en": names[b][1], "status": r.get("status"),
                          "rate": r.get("rate"), "rate_text": r.get("rate_text") or "unknown", "decision_date": str(r.get("decision_date") or "") or None,
                          "last_change_date": str(r.get("last_change_date") or "") or None, "last_change_bp": r.get("last_change_bp"),
                          "last_meeting": str(r.get("last_meeting") or "") or None, "last_meeting_outcome": r.get("last_meeting_outcome"),
                          "next_meeting": str(r.get("next_meeting") or "") or None, "next_meeting_note": r.get("next_meeting_note"),
                          "effr": r.get("effr"), "source": r.get("source"), "source_url": r.get("source_url"), "error": r.get("error"),
                          "expected": pth.get("expected"), "expected_th": {"hold": "คงดอกเบี้ย", "cut": "ลดดอกเบี้ย", "hike": "ขึ้นดอกเบี้ย"}.get(pth.get("expected") or "", "unknown"),
                          "lean_12m": pth.get("lean_12m"), "basis": pth.get("basis"), "basis_th": pth.get("basis_th"),
                          "confidence": pth.get("confidence"), "confidence_th": CONF_TH.get(pth.get("confidence") or "", "-"),
                          "rationale_th": pth.get("rationale_th") or [], "link_th": hold_links[b], "decision_text": r.get("decision_text"),
                          "history_note": r.get("history_error") and "ประวัติการเปลี่ยนแปลงดึงไม่ได้ในรอบนี้ (unknown)"})
    async with pool.acquire() as conn:
        ptrack = await conn.fetch("""SELECT c.bank, count(*) n, avg(o.hit::int)::float hit FROM policy_path_outcomes o
                                     JOIN policy_path_calls c ON c.id=o.call_id GROUP BY 1""")
    pt = {r["bank"]: {"n": r["n"], "hit": round(r["hit"], 3)} for r in ptrack}
    for c in pol_cards:
        c["track"] = pt.get(c["bank"])
        c["validation_th"] = f"ทายถูก {pt[c['bank']]['hit']:.0%} จาก {pt[c['bank']]['n']} ครั้ง" if c["bank"] in pt else "ใหม่ — ยังไม่ผ่านการตรวจ (จะตรวจหลังการประชุมถัดไป)"
    board = {"generated_at": datetime.now(timezone.utc).isoformat(), "groups": [{"key": k, "name_th": n} for k, n in GROUPS],
             "cards": cards, "policy": pol_cards, "horizons": list(P.HORIZONS),
             "legend_th": {"direction": "ขึ้น = P(ขึ้น) ≥ 55%, ลง = ≤ 45%, ทรงตัว = ระหว่างนั้น", "range": "ช่วงที่มีโอกาส 80% (จากโมเดล)",
                           "confidence": "ต่ำ < 0.10 ≤ กลาง < 0.30 ≤ สูง", "validation": "live = พยากรณ์จริงที่ล็อกไว้แล้วตรวจกับราคาจริง; ย้อนหลัง = walk-forward backtest"},
             "disclaimer_th": "ตัวเลขจากโมเดลสถิติ (ฟรี/ในเครื่อง) ไม่ใช่คำแนะนำซื้อขาย — ความไม่แน่นอนสูง ดูช่วงราคาประกอบเสมอ"}
    _CACHE["board"] = (time.time(), board)
    return board


def _n(v: float) -> str:
    return f"{v:,.0f}" if abs(v) >= 1000 else f"{v:.4g}"


async def advisor_context(pool: Any) -> str:
    b = await build_board(pool)
    lines = ["=== KEY MACRO INDICATOR TRENDS (frozen quantitative forecasts; ranges = 80%; not advice) ==="]
    for c in b["cards"]:
        if c.get("value") is None:
            lines.append(f"  - {c['name_en'] if c.get('name_en') else c['key']}: value unknown (fetch failed)")
            continue
        hs = [h for h in c.get("horizons") or [] if h.get("direction") and h["horizon"] in ("1m", "3m", "1y")]
        hz = "; ".join(f"{h['horizon']} {h['direction']} P(up) {h['p_up']:.0%} range {_n(h['low80'])}-{_n(h['high80'])} conf {h['confidence_lvl']}"
                       for h in hs)
        bt = next((h.get("backtest_track") for h in hs if h["horizon"] == "1m" and h.get("backtest_track")), None)
        lv = next((h.get("live_track") for h in hs if h["horizon"] == "1m" and h.get("live_track")), None)
        trk = (f"live 1m hit {lv['hit']:.0%} n={lv['n']}" if lv else "live: new, not yet validated") + (f"; backtest 1m hit {bt['hit']:.0%} n={bt['n']}" if bt else "")
        prox = (" [computed GC=F x THB=X]" if c["forecast_subject"] == "XAUTHB" else " [forecast on proxy " + c["forecast_subject"] + "]") if c.get("proxy_th") else ""
        lines.append(f"  - {c.get('name_en')} {_n(c['value'])} {c.get('unit', '')} (as of {c['as_of']}){prox}: " + (hz or c.get("summary_th", "")) + (f" | {trk}" if hs else ""))
    for p in b["policy"]:
        if p["status"] != "ok":
            lines.append(f"  - {p['name_en']}: unknown (fetch failed) - do not quote a value")
            continue
        lm = f"last meeting {p['last_meeting']} = {p.get('last_meeting_outcome')}; " if p.get("last_meeting") else ""
        lines.append(f"  - {p['name_en']}: {p['rate_text']} ({lm}latest rate decision {p.get('decision_date') or 'n/a'}; last change {p.get('last_change_bp')}bp on {p.get('last_change_date') or 'unknown'}; "
                     f"next meeting {p.get('next_meeting') or 'unknown'}); expected next: {p.get('expected')} (basis {p.get('basis')}, confidence {p.get('confidence')}; 12m lean {p.get('lean_12m')})")
    lines.append("Holdings links: gold->SCBGOLDE, oil->PTTEP, SET & Thai rates->SCB/ThaiESG, USD/THB->FX risk. Quote these with their ranges and "
                 "say they are model forecasts (new ones are not yet validated); never invent other values.")
    return "\n".join(lines)
