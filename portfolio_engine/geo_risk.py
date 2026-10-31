"""Geopolitical / war-risk monitor (added 2026-11-01, Tho's request t26u).

CONTEXT / DISPLAY ONLY. Nothing here feeds signals, forecasts, weights or rebalance math
(that would need the walk-forward gate in ops/backtest_gate.py first).

Inputs (all free):
  * Caldara-Iacoviello GPR index (daily + monthly + country), downloaded from
    https://www.matteoiacoviello.com/gpr.htm (cached under data/geo/, refreshed when > 6 days old)
  * market stress proxies via yfinance: gold, Brent, VIX, OVX, ITA/XAR vs SPY, BDRY (dry-bulk freight ETF),
    USD/THB, USD/JPY, USD/CHF; SCBGOLDE vs SCBGOLDHE (hedged) NAVs from fund_nav_daily
  * conflict news tone from the existing news pipeline (news_articles + sentiment_scores), EN + TH keywords
  * config/geo_conflicts.json: per-conflict status with dated sources and JUDGMENT scenario probabilities
Unknown stays unknown; anything older than its freshness limit is marked STALE.
"""
from __future__ import annotations

import json
import math
import re
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
GEO_DIR = ROOT / "data" / "geo"
CONFIG = ROOT / "config" / "geo_conflicts.json"
GPR_BASE = "https://www.matteoiacoviello.com/gpr_files/"
GPR_FILES = {"daily": "data_gpr_daily_recent.xls", "monthly": "data_gpr_export.xls"}
ICT = timezone(timedelta(hours=7))
PRICE_STALE_DAYS = 7
GPR_DAILY_STALE_DAYS = 14   # published weekly (Mondays) -> > 14 days = stale
ASSESSMENT_STALE_DAYS = 14
PROXIES = {
    "GC=F": "Gold (USD/oz)", "BZ=F": "Brent (USD/bbl)", "^VIX": "VIX", "^OVX": "Oil volatility (OVX)",
    "ITA": "US defense ETF ITA", "XAR": "US defense ETF XAR", "SPY": "S&P 500 ETF", "BDRY": "Dry-bulk freight ETF (BDRY)",
    "THB=X": "USD/THB (up = weaker baht)", "JPY=X": "USD/JPY (down = yen safe-haven bid)", "CHF=X": "USD/CHF (down = franc bid)",
}
COUNTRIES = {"RUS": "Russia", "UKR": "Ukraine", "CHN": "China", "TWN": "Taiwan", "ISR": "Israel", "KOR": "South Korea",
             "SAU": "Saudi Arabia", "USA": "USA", "THA": "Thailand"}
DDL = """
CREATE TABLE IF NOT EXISTS geo_risk_snapshots (
    id         BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    as_of      DATE NOT NULL,
    payload    JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_geo_risk_snapshots_created ON geo_risk_snapshots (created_at DESC);
"""


def _age(d: Any) -> Optional[int]:
    if d is None:
        return None
    try:
        dd = d if isinstance(d, date) else date.fromisoformat(str(d)[:10])
        return (datetime.now(ICT).date() - dd).days
    except Exception:
        return None


def load_config() -> dict[str, Any]:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    age = _age(cfg.get("assessed_at"))
    cfg["assessment_age_days"] = age
    cfg["assessment_stale"] = age is None or age > ASSESSMENT_STALE_DAYS
    return cfg


# ---------------------------------------------------------------- GPR index
def refresh_gpr(max_age_days: int = 6) -> dict[str, Any]:
    GEO_DIR.mkdir(parents=True, exist_ok=True)
    out = {}
    for k, fn in GPR_FILES.items():
        p = GEO_DIR / fn
        fresh = p.exists() and (datetime.now().timestamp() - p.stat().st_mtime) < max_age_days * 86400
        if fresh:
            out[k] = "cached"
            continue
        try:
            req = urllib.request.Request(GPR_BASE + fn, headers={"User-Agent": "Mozilla/5.0 (personal research)"})
            data = urllib.request.urlopen(req, timeout=60).read()
            if len(data) > 100_000:
                tmp = p.with_suffix(".tmp")
                tmp.write_bytes(data)
                tmp.replace(p)
                out[k] = "downloaded"
            else:
                out[k] = "download too small - kept old file"
        except Exception as exc:  # noqa: BLE001
            out[k] = f"download failed: {exc.__class__.__name__}"
    return out


def gpr_summary() -> dict[str, Any]:
    res: dict[str, Any] = {"source": "Caldara & Iacoviello GPR index, https://www.matteoiacoviello.com/gpr.htm",
                           "note": "100 = 1985-2019 average of the share of newspaper articles on adverse geopolitical events"}
    try:
        d = pd.read_excel(GEO_DIR / GPR_FILES["daily"])
        d["date"] = pd.to_datetime(d["date"])
        d = d.dropna(subset=["GPRD"]).sort_values("date")
        last = d.iloc[-1]
        hist = d["GPRD_MA30"].dropna()
        pct = float((hist < float(last["GPRD_MA30"])).mean() * 100)
        y1 = d[d["date"] >= last["date"] - pd.Timedelta(days=365)]["GPRD_MA30"].dropna()
        res["daily"] = {"as_of": str(last["date"].date()), "gprd": round(float(last["GPRD"]), 1),
                        "ma7": round(float(last["GPRD_MA7"]), 1), "ma30": round(float(last["GPRD_MA30"]), 1),
                        "ma30_pctile_since_1985": round(pct, 1),
                        "ma30_1y_range": [round(float(y1.min()), 1), round(float(y1.max()), 1)] if len(y1) else None,
                        "stale": (_age(last["date"].date()) or 99) > GPR_DAILY_STALE_DAYS}
        res["daily_series_90d"] = [{"d": str(r.date.date()), "ma30": round(float(r.GPRD_MA30), 1)}
                                   for r in d.tail(90).itertuples() if not math.isnan(r.GPRD_MA30)][::3]
    except Exception as exc:  # noqa: BLE001
        res["daily"] = {"status": "unknown", "reason": f"daily GPR unavailable ({exc.__class__.__name__})"}
    try:
        m = pd.read_excel(GEO_DIR / GPR_FILES["monthly"])
        m["month"] = pd.to_datetime(m["month"])
        m = m.dropna(subset=["GPR"]).sort_values("month")
        lm = m.iloc[-1]
        res["monthly"] = {"month": str(lm["month"].date())[:7], "gpr": round(float(lm["GPR"]), 1),
                          "threats": round(float(lm["GPRT"]), 1), "acts": round(float(lm["GPRA"]), 1),
                          "pctile_since_1985": round(float((m["GPR"] < lm["GPR"]).mean() * 100), 1)}
        ctry = {}
        for c, name in COUNTRIES.items():
            col = f"GPRC_{c}"
            if col in m:
                s = m[["month", col]].dropna()
                last12 = s[s["month"] > lm["month"] - pd.DateOffset(months=60)][col]
                v = float(s.iloc[-1][col])
                ctry[c] = {"name": name, "value": round(v, 3),
                           "pctile_5y": round(float((last12 < v).mean() * 100), 0) if len(last12) else None}
        res["country"] = ctry
    except Exception as exc:  # noqa: BLE001
        res["monthly"] = {"status": "unknown", "reason": f"monthly GPR unavailable ({exc.__class__.__name__})"}
    return res


# ---------------------------------------------------------------- market stress
def market_stress() -> dict[str, Any]:
    from market_history import download_closes
    px = download_closes(list(PROXIES), None, "4y", 1800)
    out: dict[str, Any] = {}
    for t, name in PROXIES.items():
        if t not in px:
            out[t] = {"name": name, "status": "unknown"}
            continue
        s = px[t].dropna()
        if len(s) < 300:
            out[t] = {"name": name, "status": "unknown", "reason": "insufficient history"}
            continue
        r21 = np.log(s / s.shift(21)).dropna()
        z = float((r21.iloc[-1] - r21.mean()) / r21.std()) if r21.std() > 0 else None
        as_of = s.index[-1].date()
        out[t] = {"name": name, "last": round(float(s.iloc[-1]), 4), "as_of": str(as_of),
                  "chg_1m_pct": round(float((s.iloc[-1] / s.iloc[-22] - 1) * 100), 2),
                  "chg_3m_pct": round(float((s.iloc[-1] / s.iloc[-64] - 1) * 100), 2),
                  "z_1m": round(z, 2) if z is not None else None,
                  "pctile_level_1y": round(float((s.iloc[-252:] < s.iloc[-1]).mean() * 100), 0),
                  "stale": (_age(as_of) or 99) > PRICE_STALE_DAYS}
    rel = {}
    for d in ("ITA", "XAR"):
        if d in px and "SPY" in px:
            a = px[[d, "SPY"]].dropna()
            if len(a) > 70:
                rel[d] = {"rel_1m_pct": round(float(((a[d].iloc[-1] / a[d].iloc[-22]) / (a["SPY"].iloc[-1] / a["SPY"].iloc[-22]) - 1) * 100), 2),
                          "rel_3m_pct": round(float(((a[d].iloc[-1] / a[d].iloc[-64]) / (a["SPY"].iloc[-1] / a["SPY"].iloc[-64]) - 1) * 100), 2)}
    out["_defense_vs_spy"] = rel
    return out


def stress_flags(ms: dict[str, Any]) -> list[dict[str, Any]]:
    """Rule-of-thumb flags (documented, NOT backtested): a proxy is 'elevated' when its 1m move is beyond
    +/-1.5 sd of its own 4y history in the risk-off direction, or VIX/OVX level is in its top 20% of the year."""
    risk_dir = {"GC=F": 1, "BZ=F": 1, "^VIX": 1, "^OVX": 1, "BDRY": 1, "THB=X": 1, "JPY=X": -1, "CHF=X": -1}
    flags = []
    for t, sgn in risk_dir.items():
        v = ms.get(t) or {}
        z = v.get("z_1m")
        if z is None or v.get("stale"):
            continue
        hit = sgn * z >= 1.5 or (t in ("^VIX", "^OVX") and (v.get("pctile_level_1y") or 0) >= 80)
        if hit:
            flags.append({"ticker": t, "name": v["name"], "z_1m": z, "chg_1m_pct": v.get("chg_1m_pct")})
    return flags


# ---------------------------------------------------------------- news tone per conflict
async def conflict_news(pool: Any, cfg: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for c in cfg["conflicts"]:
        rx = c["news_re"]
        rows = await pool.fetch(
            """SELECT a.title, a.source, a.url, a.published_at, a.language,
                      (SELECT avg(s.score) FROM sentiment_scores s WHERE s.article_id = a.id) AS score
               FROM news_articles a
               WHERE a.published_at >= now() - interval '35 days' AND a.title ~* $1
                 AND NOT (coalesce(a.source, '') ~* '(-USD\\)|crypto|coin)' OR a.title ~* '(crypto|bitcoin|binance|hot.wallet|token)')
               ORDER BY a.published_at DESC""", rx)
        now = datetime.now(timezone.utc)
        last7 = [r for r in rows if r["published_at"] >= now - timedelta(days=7)]
        prior = [r for r in rows if r["published_at"] < now - timedelta(days=7)]
        base_week = len(prior) / 4.0
        sc7 = [float(r["score"]) for r in last7 if r["score"] is not None]
        out[c["key"]] = {
            "articles_7d": len(last7), "avg_per_week_prior_4w": round(base_week, 1),
            "volume_ratio": round(len(last7) / base_week, 2) if base_week > 0 else None,
            "thai_articles_7d": sum(1 for r in last7 if (r["language"] or "") == "th"),
            "avg_sentiment_7d": round(sum(sc7) / len(sc7), 3) if sc7 else None, "scored_7d": len(sc7),
            "headlines": [{"title": r["title"][:160], "source": r["source"], "url": r["url"],
                           "published_at": r["published_at"].astimezone(ICT).strftime("%Y-%m-%d %H:%M")} for r in last7[:4]],
        }
    return out


# ---------------------------------------------------------------- holdings: measured sensitivities + analog
async def holding_sensitivity(pool: Any) -> dict[str, Any]:
    """Measured, not assumed: 1y daily-return correlations of holdings to Brent/gold/VIX/USDTHB, and
    the actual move over the Iran-war outbreak window (2026-02-27 -> 2026-03-31; war began 28 Feb 2026)."""
    from market_history import download_closes
    fac = download_closes(["BZ=F", "GC=F", "^VIX", "THB=X", "PTTEP.BK", "SCB.BK", "TDEX.BK", "SPY"], None, "2y", 1800)
    navs = {}
    for code in ("SCBGOLDE", "SCBGOLDHE", "TDSThaiESG-A", "K-TNZ-ThaiESG", "ES-SETESG-ThaiESG-A"):
        rows = await pool.fetch("SELECT nav_date, nav FROM fund_nav_daily WHERE code=$1 ORDER BY nav_date", code)
        if rows:
            navs[code] = pd.Series([float(r["nav"]) for r in rows], index=pd.to_datetime([r["nav_date"] for r in rows]))
    series = {t: fac[t].dropna() for t in ("PTTEP.BK", "SCB.BK", "TDEX.BK") if t in fac} | navs
    out: dict[str, Any] = {}
    w0, w1 = pd.Timestamp("2026-02-27"), pd.Timestamp("2026-03-31")
    for name, s in series.items():
        r = s.pct_change().dropna()
        r = r[r.index >= r.index[-1] - pd.Timedelta(days=365)]
        corr = {}
        for f in ("BZ=F", "GC=F", "^VIX", "THB=X"):
            if f in fac:
                j = pd.concat([r, fac[f].pct_change()], axis=1, join="inner").dropna()
                if len(j) > 60:
                    corr[f] = round(float(j.iloc[:, 0].corr(j.iloc[:, 1])), 2)
        a = s[(s.index >= w0 - pd.Timedelta(days=5)) & (s.index <= w0)]
        b = s[(s.index >= w1 - pd.Timedelta(days=5)) & (s.index <= w1)]
        analog = round(float((b.iloc[-1] / a.iloc[-1] - 1) * 100), 2) if len(a) and len(b) else None
        out[name] = {"corr_1y": corr, "n_days": int(len(r)), "iran_war_outbreak_move_pct": analog,
                     "as_of": str(s.index[-1].date())}
    for f in ("BZ=F", "GC=F", "SPY", "THB=X", "^VIX"):
        if f in fac:
            s = fac[f].dropna()
            a, b = s[s.index <= w0], s[s.index <= w1]
            out.setdefault("_factors_outbreak_move_pct", {})[f] = round(float((b.iloc[-1] / a.iloc[-1] - 1) * 100), 2) if len(a) and len(b) else None
    out["_window"] = "2026-02-27 -> 2026-03-31 (US-Israeli strikes on Iran began 28 Feb 2026); one historical episode, not a forecast"
    return out


def expected_tier_mix(cfg: dict[str, Any]) -> dict[str, Any]:
    mix = {}
    for c in cfg["conflicts"]:
        p_esc = sum(s["p"] for s in c["scenarios"] if s["tier"] in ("regional_escalation", "blockade", "major_power"))
        mix[c["key"]] = {"p_escalation": round(p_esc, 2), "p_major_power": next((s["p"] for s in c["scenarios"] if s["tier"] == "major_power"), None)}
    return mix


# ---------------------------------------------------------------- run / read
async def run(pool: Any, refresh: bool = True) -> dict[str, Any]:
    await pool.execute(DDL)
    cfg = load_config()
    dl = refresh_gpr() if refresh else {}
    gpr = gpr_summary()
    try:
        ms = market_stress()
    except Exception as exc:  # noqa: BLE001
        ms = {"status": "unknown", "reason": f"market data unavailable ({exc.__class__.__name__})"}
    flags = stress_flags(ms) if "status" not in ms else []
    news = await conflict_news(pool, cfg)
    try:
        sens = await holding_sensitivity(pool)
    except Exception as exc:  # noqa: BLE001
        sens = {"status": "unknown", "reason": exc.__class__.__name__}
    gd = gpr.get("daily") or {}
    pct = gd.get("ma30_pctile_since_1985")
    level = ("unknown" if pct is None else "high" if pct >= 90 else "elevated" if pct >= 75 else "normal")
    payload = {
        "as_of": str(datetime.now(ICT).date()), "generated_at": datetime.now(ICT).isoformat(timespec="minutes"),
        "use": "context/display only - not used in signals, forecasts or rebalance math",
        "level": level, "level_basis": "GPR daily 30-day average percentile since 1985 (>=90 high, >=75 elevated) - rule of thumb",
        "gpr": gpr, "gpr_download": dl, "market_stress": ms, "stress_flags": flags, "news": news,
        "holding_sensitivity": sens, "assessment": cfg, "escalation_mix": expected_tier_mix(cfg),
    }
    await pool.execute("INSERT INTO geo_risk_snapshots (as_of, payload) VALUES ($1, $2::jsonb)",
                       datetime.now(ICT).date(), json.dumps(payload, default=str))
    return payload


async def latest(pool: Any) -> Optional[dict[str, Any]]:
    try:
        row = await pool.fetchrow("SELECT payload FROM geo_risk_snapshots ORDER BY created_at DESC LIMIT 1")
    except Exception:
        return None
    if not row:
        return None
    p = row["payload"]
    p = json.loads(p) if isinstance(p, str) else p
    p["assessment"] = load_config()  # always the current file (+ staleness)
    return p


LEVEL_TH = {"high": "สูง", "elevated": "สูงกว่าปกติ", "normal": "ปกติ", "unknown": "ไม่ทราบ"}


def render_text(p: dict[str, Any], lang: str = "en") -> str:
    g = (p.get("gpr") or {}).get("daily") or {}
    gm = (p.get("gpr") or {}).get("monthly") or {}
    cfg = p.get("assessment") or {}
    lines = ["=== GEOPOLITICAL / WAR RISK (context only - not a trading signal; probabilities are JUDGMENT) ===",
             f"Level: {p.get('level')} ({p.get('level_basis')})"]
    if g.get("ma30") is not None:
        lines.append(f"GPR daily (Caldara-Iacoviello) as of {g['as_of']}: 30d avg {g['ma30']} (pctile since 1985 {g['ma30_pctile_since_1985']}%), "
                     f"7d avg {g['ma7']}{' STALE' if g.get('stale') else ''}; monthly {gm.get('month')}: {gm.get('gpr')}")
    else:
        lines.append("GPR index: unknown")
    ms = p.get("market_stress") or {}
    parts = []
    for t in ("BZ=F", "GC=F", "^VIX", "^OVX", "THB=X", "JPY=X", "CHF=X", "BDRY"):
        v = ms.get(t) or {}
        if v.get("last") is not None:
            parts.append(f"{t} {v['last']:g} ({v['chg_1m_pct']:+.1f}% 1m, z {v.get('z_1m')}){' STALE' if v.get('stale') else ''} as of {v['as_of']}")
    lines.append("Market stress proxies: " + ("; ".join(parts) if parts else "unknown"))
    dv = ms.get("_defense_vs_spy") or {}
    if dv:
        lines.append("Defense vs SPY (1m rel): " + ", ".join(f"{k} {v['rel_1m_pct']:+.1f}%" for k, v in dv.items()))
    fl = p.get("stress_flags") or []
    lines.append("Elevated proxies: " + (", ".join(f"{f['ticker']} z{f['z_1m']}" for f in fl) if fl else "none"))
    lines.append(f"Conflict assessment as of {cfg.get('assessed_at')}{' (STALE - re-verify before quoting)' if cfg.get('assessment_stale') else ''}; horizon {cfg.get('horizon')}:")
    news = p.get("news") or {}
    for c in cfg.get("conflicts", []):
        n = news.get(c["key"]) or {}
        sc = "; ".join(f"{s['tier']} {round(s['p'] * 100)}%" for s in c["scenarios"])
        lines.append(f"- {c['name_en']}: {c['status_en'][:420]} | scenarios (judgment): {sc} | news 7d: {n.get('articles_7d', 'unknown')} "
                     f"articles (x{n.get('volume_ratio')} vs prior 4w), avg sentiment {n.get('avg_sentiment_7d')}")
    w = cfg.get("ww3") or {}
    lines.append(f"- Multi-front great-power war (12m, judgment): {w.get('p_12m')} - {w.get('note_en')}")
    lines.append("EU/UK stockpiling facts (verified): " + " | ".join(f"{f['issuer']} {f['date']}: {f['what'][:200]}" for f in cfg.get("eu_preparedness_facts", [])))
    hs = p.get("holding_sensitivity") or {}
    hl = []
    for k in ("PTTEP.BK", "SCB.BK", "SCBGOLDE", "SCBGOLDHE", "TDSThaiESG-A", "K-TNZ-ThaiESG", "ES-SETESG-ThaiESG-A"):
        v = hs.get(k) or {}
        if v:
            hl.append(f"{k}: corr1y Brent {v['corr_1y'].get('BZ=F')}, gold {v['corr_1y'].get('GC=F')}, VIX {v['corr_1y'].get('^VIX')}; "
                      f"Iran-war outbreak window move {v.get('iran_war_outbreak_move_pct')}%")
    if hl:
        lines.append("Holding sensitivities (measured, " + str(hs.get("_window")) + "): " + " | ".join(hl))
    lines.append("Rules: no sell/trim advice for PTTEP/SCB (owner holds); hedge ideas are suggestions only; swing/position horizon; never place orders.")
    return "\n".join(lines)


def render_brief(p: Optional[dict[str, Any]]) -> str:
    if not p:
        return "### ความเสี่ยงภูมิรัฐศาสตร์/สงคราม\n- ไม่มีข้อมูล (unknown)"
    cfg = p.get("assessment") or {}
    g = (p.get("gpr") or {}).get("daily") or {}
    lines = ["### ความเสี่ยงภูมิรัฐศาสตร์/สงคราม (ข้อมูลประกอบ ไม่ใช่สัญญาณ)",
             f"- ระดับรวม: {LEVEL_TH.get(p.get('level'), p.get('level'))} (ดัชนี GPR เฉลี่ย 30 วัน {g.get('ma30', 'unknown')}, สูงกว่า {g.get('ma30_pctile_since_1985', '?')}% ของช่วงปี 1985 ถึงปัจจุบัน ณ {g.get('as_of', '?')})"]
    for c in cfg.get("conflicts", []):
        esc = sum(s["p"] for s in c["scenarios"] if s["tier"] in ("regional_escalation", "blockade", "major_power"))
        lines.append(f"- {c['name_th']}: {c['status_th']} (โอกาสยกระดับ ~{round(esc * 100)}% ใน 3 เดือน เป็นการประเมิน)")
    fl = p.get("stress_flags") or []
    if fl:
        lines.append("- ตัวชี้วัดตลาดที่ตึงตัว: " + ", ".join(f"{f['name']} {f['chg_1m_pct']:+.1f}% 1 เดือน" for f in fl))
    if cfg.get("assessment_stale"):
        lines.append("- หมายเหตุ: การประเมินรายประเทศเก่ากว่า 14 วัน (STALE) ต้องตรวจสอบใหม่")
    return "\n".join(lines)
