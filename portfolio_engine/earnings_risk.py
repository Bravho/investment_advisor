"""earnings_risk.py - earnings-event gap risk for US watch-list names + sector bellwethers.

Added 2026-11-01 (Tho t39u) after INTC fell -28.6% on 30 Oct 2026: a Q4-guidance cut released
after the close gapped the stock -25.8% at the open, and the read-through hit AVGO/MU/TSM -5..-6%
and SOX -7.2%. Our system had no US earnings-date awareness outside proposed trade plans.

DISPLAY / CONTEXT ONLY.  Nothing here feeds signal scores, forecasts, weights or rebalance advice.
Scoring variants (pre-earnings exclusion, post-gap block, size haircut) were tested in
ops/earnings_gate.py against ops/backtest_gate.py; see docs/research/intel_drop_20261030.md.

Free data only: yfinance get_earnings_dates (company-published dates + EPS estimate/actual) and
daily closes via market_history.download_closes.  Cached in data/earnings/us_earnings_cache.json.
"""
from __future__ import annotations

import json
import logging
import statistics
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

import pandas as pd

LOGGER = logging.getLogger("portfolio_engine.earnings_risk")
ROOT = Path(__file__).resolve().parents[1]
CACHE_FILE = ROOT / "data" / "earnings" / "us_earnings_cache.json"
CACHE_TTL_H = 20
ET = ZoneInfo("America/New_York")
ICT = ZoneInfo("Asia/Bangkok")

# Reports whose read-through moved our watch list (not in the watch list themselves).
BELLWETHERS: dict[str, dict[str, Any]] = {
    "INTC": {"name": "Intel", "read_through": ["MU", "TSM", "AVGO", "NVDA", "QQQ"],
             "why": "PC/server CPU demand + memory-cost read; 30 Oct 2026 guide cut: SOX -7.2%, AVGO -5.5%, MU -5.3%, TSM -6.0%"},
    "AMD": {"name": "AMD", "read_through": ["NVDA", "TSM", "MU", "AVGO", "QQQ"], "why": "AI GPU + PC/server CPU demand"},
    "ASML": {"name": "ASML", "read_through": ["TSM", "MU", "NVDA"], "why": "fab-equipment orders = chip capex cycle"},
    "AMZN": {"name": "Amazon", "read_through": ["NVDA", "AVGO", "MU", "QQQ"], "why": "hyperscaler AI capex guidance"},
    "META": {"name": "Meta", "read_through": ["NVDA", "AVGO", "QQQ"], "why": "hyperscaler AI capex guidance"},
    "AAPL": {"name": "Apple", "read_through": ["TSM", "QQQ", "SPY"], "why": "largest TSMC customer, index weight"},
}
IMMINENT_TD = 5    # trading days
SOON_TD = 15
BIG_GAP_PCT = 7.0  # |reaction| at or above this counts as a gap event


def _load_cache() -> dict[str, Any]:
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _save_cache(c: dict[str, Any]) -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(c, indent=1, default=str), encoding="utf-8")


def fetch_dates(tickers: list[str], ttl_h: float = CACHE_TTL_H, limit: int = 48) -> dict[str, dict[str, Any]]:
    """{ticker: {"events": [{"ts": iso ET, "eps_est", "eps_act", "surprise_pct"}], "fetched_at", "error"}}"""
    import yfinance as yf

    cache = _load_cache()
    changed = False
    out: dict[str, dict[str, Any]] = {}
    for t in tickers:
        hit = cache.get(t)
        if hit and time.time() - float(hit.get("fetched_epoch", 0)) < ttl_h * 3600:
            out[t] = hit
            continue
        rec: dict[str, Any] = {"events": [], "fetched_at": datetime.now(ICT).isoformat(timespec="seconds"),
                               "fetched_epoch": time.time(), "error": None}
        try:
            df = yf.Ticker(t).get_earnings_dates(limit=limit)
            if df is not None and not df.empty:
                for ts, row in df.iterrows():
                    def num(k: str) -> Optional[float]:
                        v = row.get(k)
                        return None if v is None or pd.isna(v) else float(v)
                    rec["events"].append({"ts": pd.Timestamp(ts).tz_convert(ET).isoformat(),
                                          "eps_est": num("EPS Estimate"), "eps_act": num("Reported EPS"),
                                          "surprise_pct": num("Surprise(%)")})
        except Exception as exc:  # noqa: BLE001  (ETFs have no earnings -> error/empty)
            rec["error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
        if hit and not rec["events"] and hit.get("events"):  # keep last good copy on a transient failure
            rec = {**hit, "error": rec["error"], "refresh_failed_at": rec["fetched_at"]}
        cache[t] = rec
        out[t] = rec
        changed = True
    if changed:
        _save_cache(cache)
    return out


def reaction_day(ts_iso: str, idx: pd.DatetimeIndex) -> Optional[pd.Timestamp]:
    """First trading session that can react: same day if released before 09:30 ET, else next session."""
    ts = pd.Timestamp(ts_iso)
    d = pd.Timestamp(ts.date())
    pre_open = ts.hour < 9 or (ts.hour == 9 and ts.minute < 30)
    pos = idx.searchsorted(d, side="left" if pre_open else "right")
    return idx[pos] if pos < len(idx) else None


def reaction_moves(events: list[dict[str, Any]], closes: pd.Series) -> list[dict[str, Any]]:
    s = closes.dropna()
    if s.empty:
        return []
    idx = s.index
    vol = s.pct_change().rolling(60).std()
    out = []
    for e in events:
        if e.get("eps_act") is None:
            continue
        rd = reaction_day(e["ts"], idx)
        if rd is None or idx.get_loc(rd) == 0:
            continue
        i = idx.get_loc(rd)
        r = float(s.iloc[i] / s.iloc[i - 1] - 1) * 100
        fwd20 = float(s.iloc[i + 20] / s.iloc[i] - 1) * 100 if i + 20 < len(s) else None
        sd = vol.iloc[i - 1]
        out.append({"report_ts": e["ts"], "reaction_day": str(rd.date()), "move_pct": round(r, 2),
                    "z": round(r / (float(sd) * 100), 1) if sd and not pd.isna(sd) else None,
                    "next20d_pct": round(fwd20, 2) if fwd20 is not None else None,
                    "surprise_pct": e.get("surprise_pct")})
    return sorted(out, key=lambda x: x["reaction_day"])


def _q(v: list[float], q: float) -> Optional[float]:
    if not v:
        return None
    v = sorted(v)
    k = (len(v) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (k - lo)


def _trading_days_between(a: date, b: date) -> int:
    return int(len(pd.bdate_range(a + timedelta(days=1), b))) if b > a else 0


def build(watch_us: list[str], holdings_us: Optional[list[str]] = None, lookback_events: int = 12) -> dict[str, Any]:
    from market_history import download_closes

    holdings_us = holdings_us or []
    names = list(dict.fromkeys(holdings_us + watch_us))
    allt = list(dict.fromkeys(names + list(BELLWETHERS)))
    dates = fetch_dates(allt)
    try:
        px = download_closes(allt, period="5y", ttl=3600)
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("closes unavailable: %s", exc)
        px = pd.DataFrame()
    today = datetime.now(ET).date()
    items, pooled_neg = [], []
    for t in allt:
        rec = dates.get(t) or {}
        evs = rec.get("events") or []
        if not evs:
            continue  # ETFs / no published dates
        fut = sorted(e["ts"] for e in evs if e.get("eps_act") is None and pd.Timestamp(e["ts"]).date() >= today)
        nxt = fut[0] if fut else None
        nd = pd.Timestamp(nxt).date() if nxt else None
        tdays = _trading_days_between(today, nd) if nd else None
        moves = reaction_moves(evs, px[t]) if t in px.columns else []
        recent = moves[-lookback_events:]
        absm = [abs(m["move_pct"]) for m in recent]
        pooled_neg += [m for m in moves if m["move_pct"] <= -BIG_GAP_PCT and m["next20d_pct"] is not None]
        last = moves[-1] if moves else None
        post_gap = bool(last and last["move_pct"] <= -BIG_GAP_PCT
                        and _trading_days_between(date.fromisoformat(last["reaction_day"]), today) <= 20)
        level = "none"
        if tdays is not None and tdays <= IMMINENT_TD:
            level = "imminent"
        elif tdays is not None and tdays <= SOON_TD:
            level = "soon"
        role = "holding" if t in holdings_us else ("watch" if t in watch_us else "bellwether")
        bw = BELLWETHERS.get(t)
        timing = None
        if nxt:
            h = pd.Timestamp(nxt).hour
            timing = "after close (reaction next session)" if h >= 16 else ("before open" if h < 9 else "during session/unspecified")
        items.append({
            "ticker": t, "role": role, "name": bw["name"] if bw else None,
            "read_through": bw["read_through"] if bw else None, "why": bw["why"] if bw else None,
            "next_earnings_et": nxt, "next_earnings_ict": pd.Timestamp(nxt).tz_convert(ICT).isoformat() if nxt else None,
            "timing": timing, "trading_days_to": tdays, "level": level,
            "hist_n": len(recent), "median_abs_move_pct": round(statistics.median(absm), 2) if absm else None,
            "p90_abs_move_pct": round(_q(absm, 0.9), 2) if absm else None,
            "worst_move_pct": min((m["move_pct"] for m in recent), default=None),
            "best_move_pct": max((m["move_pct"] for m in recent), default=None),
            "last_reaction": last, "post_gap_watch": post_gap,
            "source": "yfinance get_earnings_dates (company-published) + Yahoo daily closes",
            "dates_fetched_at": rec.get("fetched_at"), "dates_error": rec.get("error"),
        })
    order = {"holding": 0, "watch": 1, "bellwether": 2}
    items.sort(key=lambda x: (order[x["role"]], x["trading_days_to"] if x["trading_days_to"] is not None else 999))
    fw = [m["next20d_pct"] for m in pooled_neg]
    pead = {"n": len(fw), "median_next20d_pct": round(statistics.median(fw), 2) if fw else None,
            "share_lower_after_20d": round(sum(1 for x in fw if x < 0) / len(fw), 2) if fw else None,
            "definition": f"reaction-day move <= -{BIG_GAP_PCT:.0f}%, pooled over all names above, 5y Yahoo closes (in-sample, descriptive)"}
    return {"generated_at": datetime.now(ICT).isoformat(timespec="seconds"), "items": items, "post_gap_stats": pead,
            "levels": {"imminent": f"<= {IMMINENT_TD} trading days", "soon": f"<= {SOON_TD} trading days"},
            "use": "display/context only - not used in signal scores, forecasts, weights or rebalance",
            "thai_note": "SET holdings' earnings dates are tracked separately by earnings_tracker (morning brief)."}


def advisor_context(rep: dict[str, Any]) -> str:
    lines = ["=== EARNINGS EVENT RISK (US watch list + bellwethers; display/context only, not in scores) ==="]
    items = rep.get("items") or []
    if not items:
        return lines[0] + "\n  unavailable - do not quote earnings dates."
    for i in items:
        if i["level"] == "none" and not i["post_gap_watch"] and i["role"] != "bellwether":
            continue
        if i["role"] == "bellwether" and (i["trading_days_to"] is None or i["trading_days_to"] > SOON_TD) and not i["post_gap_watch"]:
            continue
        d = (i.get("next_earnings_ict") or "")[:16].replace("T", " ")
        s = f"  - {i['ticker']} ({i['role']}): next earnings {d + ' ICT' if d else 'unknown'}"
        if i["trading_days_to"] is not None:
            s += f" (~{i['trading_days_to']} trading days, {i['timing']})"
        if i["median_abs_move_pct"] is not None:
            s += f"; last {i['hist_n']} reports: median |move| {i['median_abs_move_pct']}%, p90 {i['p90_abs_move_pct']}%, worst {i['worst_move_pct']}%"
        if i["level"] != "none":
            s += f" [{i['level'].upper()}: a gap can jump straight through a stop - size for the gap or wait until after the report]"
        if i["post_gap_watch"] and i.get("last_reaction"):
            s += f" [POST-GAP: fell {i['last_reaction']['move_pct']}% on {i['last_reaction']['reaction_day']} - wait for a base before any swing entry]"
        if i.get("read_through"):
            s += f"; read-through to {', '.join(i['read_through'])}"
        lines.append(s)
    p = rep.get("post_gap_stats") or {}
    if p.get("n"):
        lines.append(f"  Post-earnings gaps <= -7% in this basket (5y, n={p['n']}): median next-20d {p['median_next20d_pct']}%, "
                     f"lower after 20d in {int(round((p['share_lower_after_20d'] or 0) * 100))}% of cases (descriptive, not a forecast).")
    lines.append("  Lesson (INTC 30 Oct 2026): beat on the quarter, cut the next-quarter guide -> -25.8% gap, -28.6% close; "
                 "guidance matters more than the reported quarter. Never advise selling PTTEP/SCB on this.")
    return "\n".join(lines)


def gap_stats(ticker: str, lookback_events: int = 12) -> Optional[dict[str, Any]]:
    """Historical earnings-day reaction stats for one US ticker (cached dates + Yahoo closes); None if n/a."""
    if not ticker or "." in ticker or "=" in ticker or ticker.startswith("^"):
        return None
    from market_history import download_closes
    rec = fetch_dates([ticker]).get(ticker) or {}
    if not rec.get("events"):
        return None
    try:
        px = download_closes([ticker], period="5y", ttl=3600)[ticker]
    except Exception:  # noqa: BLE001
        return None
    mv = reaction_moves(rec["events"], px)
    recent = mv[-lookback_events:]
    if not recent:
        return None
    absm = [abs(m["move_pct"]) for m in recent]
    last = mv[-1]
    days_since = _trading_days_between(date.fromisoformat(last["reaction_day"]), datetime.now(ET).date())
    return {"n": len(recent), "median_abs_move_pct": round(statistics.median(absm), 2),
            "p90_abs_move_pct": round(_q(absm, 0.9), 2), "worst_move_pct": min(m["move_pct"] for m in recent),
            "last_reaction": last, "trading_days_since_last": days_since,
            "post_gap_watch": last["move_pct"] <= -BIG_GAP_PCT and days_since <= 20}


SHADOW_FILE = ROOT / "data" / "shadow" / "earnings_post_gap_shadow.jsonl"


def log_post_gap_shadow(signal_items: list[dict[str, Any]], rep: dict[str, Any]) -> Optional[dict[str, Any]]:
    """SHADOW only: which current top-3 P3.3 names a 'post-earnings-gap block' (<= -7%, 20 trading days) would skip.
    Gate passed on a single affected rebalance in 7y (GOOGL Jul 2026) -> too thin to go live; logged once per day."""
    flagged = {i["ticker"] for i in rep.get("items") or [] if i.get("post_gap_watch")}
    scored = sorted([i for i in signal_items if i.get("score") is not None and "." not in i["ticker"]], key=lambda i: -float(i["score"]))[:3]
    row = {"date": datetime.now(ICT).date().isoformat(), "top3": [i["ticker"] for i in scored],
           "would_block": [i["ticker"] for i in scored if i["ticker"] in flagged], "post_gap_names": sorted(flagged),
           "rule": "skip if last earnings reaction <= -7% within 20 trading days", "status": "shadow"}
    try:
        SHADOW_FILE.parent.mkdir(parents=True, exist_ok=True)
        lines = SHADOW_FILE.read_text(encoding="utf-8").splitlines() if SHADOW_FILE.exists() else []
        if lines and json.loads(lines[-1]).get("date") == row["date"]:
            return row  # already logged today
        with SHADOW_FILE.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
    except Exception as exc:  # noqa: BLE001
        LOGGER.info("shadow log failed: %s", exc)
    return row
