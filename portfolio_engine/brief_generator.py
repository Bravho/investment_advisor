from __future__ import annotations
import json
import os
from datetime import date
from pathlib import Path
from typing import Any

from catalyst_monitor import catalyst_alert_summary  # Added by nightly agent 2026-06-16
from earnings_tracker import pre_earnings_brief, run_nightly_earnings_check, validate_earnings_dates, load_earnings_actual  # Added 2026-06-13; validate_earnings_dates 2026-07-05; load_earnings_actual 2026-07-25
from oil_scenario import probability_weighted_outlook, run_oil_scenario_report  # Added 2026-06-14, weighted 2026-06-19
from opportunity_scanner import check_exit_signals, scan_opportunities, tech_screener
from utils.common import PROJECT_DIR, compact_json, configure_logging, json_dumps, ollama_chat, ollama_chat_stream, parse_json_response, to_jsonable
from utils.db_pool import db_pool

logger = configure_logging("portfolio_engine.brief")
MODEL = os.getenv("OLLAMA_ADVISORY_MODEL", "hermes3:8b")

# --- Brief reliability settings — Added 2026-10-29 (Phase 2) ---------------
BRIEF_FAILED_PREFIX = "[BRIEF GENERATION FAILED]"
BRIEF_NUM_CTX = int(os.getenv("BRIEF_NUM_CTX", "12288"))
BRIEF_CONTEXT_MAX_CHARS = int(os.getenv("BRIEF_CONTEXT_MAX_CHARS", "16000"))
BRIEF_PER_KEY_MAX_CHARS = int(os.getenv("BRIEF_PER_KEY_MAX_CHARS", "2500"))
BRIEF_STALE_DAYS = int(os.getenv("BRIEF_STALE_DAYS", "3"))
BRIEF_MIN_CONTENT_CHARS = 300
BRIEF_ATTEMPTS = int(os.getenv("BRIEF_ATTEMPTS", "2"))
# Context keys derived from the nightly-agent watchlist macro_context. When the
# watchlist is stale these are dropped so stale levels are never presented as current.
_WATCHLIST_DERIVED_KEYS = (
    "multi_market_macro", "pttep_oil_scenarios", "pttep_oil_risk_flag",
    "pttep_oil_weighted_outlook", "fed_policy_risk_flag", "gold_drawdown_flag",
    "currency_regime_flag", "japan_policy_risk_flag",
)


def is_failed_brief(content: Any) -> bool:
    text = str(content or "").strip()
    return (not text) or text.startswith(BRIEF_FAILED_PREFIX) or text.startswith(
        "Daily brief generation is temporarily unavailable"
    )


def _age_days(iso_date: Any) -> int | None:
    try:
        return (date.today() - date.fromisoformat(str(iso_date)[:10])).days
    except (TypeError, ValueError):
        return None


def _latest_market_intel_date() -> str | None:
    intel_dir = PROJECT_DIR / "data" / "market_intel"
    files = sorted(intel_dir.glob("*.md"), reverse=True) if intel_dir.exists() else []
    return files[0].stem if files else None


def _prepare_brief_context(context: dict[str, Any], watchlist_updated: Any) -> dict[str, Any]:
    """Drop stale watchlist-derived inputs and shrink everything to fit num_ctx."""
    ctx = dict(context)
    omitted: list[str] = []
    wl_age = _age_days(watchlist_updated)
    if wl_age is None or wl_age > BRIEF_STALE_DAYS:
        for key in _WATCHLIST_DERIVED_KEYS:
            if key in ctx:
                ctx.pop(key)
                omitted.append(key)
    ctx["data_freshness"] = {
        "today": date.today().isoformat(),
        "watchlist_macro_last_updated": watchlist_updated,
        "watchlist_macro_age_days": wl_age,
        "omitted_stale_inputs": omitted,
        "note": "Inputs listed in omitted_stale_inputs are older than %d days and were removed. "
                "Write 'data unavailable' for them; do not estimate." % BRIEF_STALE_DAYS,
    }
    perf = ctx.get("portfolio_performance_7d")
    if isinstance(perf, list):
        ctx["portfolio_performance_7d"] = [
            {k: v for k, v in row.items() if k != "snapshot"} if isinstance(row, dict) else row
            for row in perf
        ]
    ctx = {k: compact_json(v, BRIEF_PER_KEY_MAX_CHARS) for k, v in ctx.items()}
    return compact_json(ctx, BRIEF_CONTEXT_MAX_CHARS)

# ---------------------------------------------------------------------------
# Multi-market context loader — Added by nightly agent 2026-06-09
# ---------------------------------------------------------------------------

def _load_latest_market_intel() -> str:
    """
    Load the most recent nightly market intelligence file from
    data/market_intel/ to inject into the brief prompt.

    Returns a concise text snippet (≤1500 chars) or empty string if not found.
    Added by nightly agent 2026-06-09
    """
    intel_dir = PROJECT_DIR / "data" / "market_intel"
    if not intel_dir.exists():
        return ""
    md_files = sorted(intel_dir.glob("*.md"), reverse=True)
    if not md_files:
        return ""
    try:
        content = md_files[0].read_text(encoding="utf-8")
        # Trim to keep context window manageable
        return content[:1500] if len(content) > 1500 else content
    except OSError:
        return ""


def _load_watchlist_snapshot() -> dict[str, Any]:
    """
    Load watchlist.json for latest price signals.
    Added by nightly agent 2026-06-09
    """
    wl_path = PROJECT_DIR / "data" / "watchlist.json"
    if wl_path.exists():
        try:
            return json.loads(wl_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _load_snapshot_trend(days: int = 7) -> list[dict[str, Any]]:
    """
    Load the last `days` daily portfolio snapshots for trend analysis.
    Returns a compact list (date, total_value_thb, risk_score) sorted oldest-first.
    Falls back to empty list if data unavailable.
    Added by nightly agent 2026-06-12
    """
    try:
        from performance_analytics import load_snapshot_history  # type: ignore
        history = load_snapshot_history(days=days)
        return [
            {
                "snapshot_date": h.get("snapshot_date"),
                "total_value_thb": h.get("total_market_value_thb"),
                "risk_score": h.get("risk_score"),
                "risk_level": h.get("risk_level"),
                "usd_thb_rate": h.get("usd_thb_rate"),
            }
            for h in history
        ]
    except Exception:
        logger.debug("Snapshot trend unavailable — skipping")
        return []


def _load_oil_position_risk(
    brent_usd: float, deal_confirmed: bool, pttep_weight: float = 0.0
) -> dict[str, Any]:
    """
    Compute PTTEP's position-level oil risk via risk_scorer.oil_scenario_risk_flag,
    so the brief can show the numeric risk score / level alongside the scenario
    narrative (rather than the scenario table alone). Tries both import paths
    (the engine runner adds ai_engine to sys.path); degrades to {} on any failure.
    Added by nightly agent 2026-06-17
    """
    try:
        try:
            from risk_scorer import oil_scenario_risk_flag  # type: ignore
        except Exception:
            from ai_engine.risk_scorer import oil_scenario_risk_flag  # type: ignore
        return oil_scenario_risk_flag(
            brent_usd, pttep_weight=pttep_weight, deal_confirmed=deal_confirmed
        )
    except Exception:
        logger.debug("oil position risk unavailable — skipping")
        return {}


def _load_fed_policy_risk(
    fed_funds_rate_pct: float,
    dot_plot_bias: str,
    hike_prob_pct: float | None = None,
) -> dict[str, Any]:
    """
    Compute the US-monetary-policy headwind on gold + the baht book via
    risk_scorer.fed_policy_risk_flag, so the brief's Gold & Currency section can
    state the numeric risk_level + score (not just narrate the dot-plot). Tries
    both import paths (engine runner adds ai_engine to sys.path); degrades to {}.
    Added by nightly agent 2026-06-19
    `hike_prob_pct` (market-implied next-meeting odds) added 2026-06-27 — optional,
    None falls back to the text-only bias.
    """
    try:
        try:
            from risk_scorer import fed_policy_risk_flag  # type: ignore
        except Exception:
            from ai_engine.risk_scorer import fed_policy_risk_flag  # type: ignore
        return fed_policy_risk_flag(
            fed_funds_rate_pct, dot_plot_bias=dot_plot_bias, hike_prob_pct=hike_prob_pct
        )
    except Exception:
        logger.debug("fed policy risk unavailable — skipping")
        return {}


def _load_gold_drawdown(
    current_level: float, trailing_high: float, fed_policy_risk: dict[str, Any]
) -> dict[str, Any]:
    """
    Classify the gold-fund drawdown (Fed-driven dip vs possible trend break) via
    risk_scorer.gold_drawdown_monitor, so Section 2 can tell Tho whether a
    falling gold NAV is a hold/add dip or a reason to review. Tries both import
    paths; degrades to {}.
    Added by nightly agent 2026-06-20
    """
    try:
        try:
            from risk_scorer import gold_drawdown_monitor  # type: ignore
        except Exception:
            from ai_engine.risk_scorer import gold_drawdown_monitor  # type: ignore
        return gold_drawdown_monitor(current_level, trailing_high, fed_policy_risk=fed_policy_risk)
    except Exception:
        logger.debug("gold drawdown monitor unavailable — skipping")
        return {}


def _parse_leading_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    """
    Parse a leading float out of a value that may be a number or a string with
    trailing annotation (e.g. "33.22 (Jun 24, 2026)" -> 33.22). Used because some
    watchlist macro_context fields carry a numeric value plus a dated note.
    Added by nightly agent 2026-06-26
    """
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        import re
        m = re.search(r"-?\d+(?:\.\d+)?", value)
        if m:
            try:
                return float(m.group(0))
            except ValueError:
                return default
    return default


def _load_scbgolde_weight() -> Optional[float]:
    """
    Estimate the SCBGOLDE (gold fund) fraction of the portfolio from the live
    portfolio snapshot, for the currency-regime THB-NAV cushion figure. The gold
    sleeve is the book's only USD-priced exposure, so its weight drives how much
    a weak baht cushions the THB NAV. Missing valuation data stays unknown.
    Added by nightly agent 2026-06-26
    """
    try:
        snap_path = PROJECT_DIR / "data_collector" / "portfolio_snapshot.json"
        if not snap_path.exists():
            return None
        snap = json.loads(snap_path.read_text(encoding="utf-8"))
        holdings = snap.get("holdings", {})
        total = float(snap.get("total_market_value_thb") or 0)
        gold_val = 0.0
        for k, v in holdings.items():
            if "GOLD" in k.upper() or "SCBGOLDE" in k.upper():
                if isinstance(v, dict):
                    gold_val = float(v.get("market_value_thb") or 0)
        if gold_val > 0 and total > 0:
            # total may exclude the gold leg when its price is missing; normalise
            denom = total if gold_val <= total else (total + gold_val)
            return round(gold_val / denom, 4)
        return None
    except Exception:
        return None


def _load_currency_regime(
    usd_thb_rate: float, prior_1yr_high: float, scbgolde_weight: float
) -> dict[str, Any]:
    """
    Score the baht-regime risk and its two-sided effect via
    risk_scorer.currency_regime_flag, so Section 2 can state the FX trade-off
    explicitly: a weak baht CUSHIONS SCBGOLDE's THB NAV while RAISING the FX
    entry cost of any new USD-denominated buy. Tries both import paths; degrades
    to {}. usd_asset_weight is left 0.0 — the book holds no USD-denominated
    positions today, so the entry-cost figure applies only to prospective buys
    (covered qualitatively by the flag's note).
    Added by nightly agent 2026-06-26
    """
    try:
        try:
            from risk_scorer import currency_regime_flag  # type: ignore
        except Exception:
            from ai_engine.risk_scorer import currency_regime_flag  # type: ignore
        return currency_regime_flag(
            usd_thb_rate,
            prior_1yr_high=prior_1yr_high if prior_1yr_high > 0 else None,
            scbgolde_weight=scbgolde_weight,
            usd_asset_weight=0.0,
        )
    except Exception:
        logger.debug("currency regime flag unavailable — skipping")
        return {}


def _load_japan_policy_risk(
    boj_rate: float,
    usd_jpy_rate: float | None = None,
    boj_hike_prob_pct: float | None = None,
) -> dict[str, Any]:
    """
    Compute the BOJ carry-trade-unwind risk via risk_scorer.japan_policy_risk_flag,
    so the brief's Regional Markets section can state Japan's monetary-policy risk
    numerically (risk_level + score + priced hike odds) instead of leaving Japan as
    a free-text afterthought. The yen carry trade is a major driver of EM/Asian
    capital flows, so a forward BOJ-tightening signal is medium-term-relevant to
    Tho's Thai book even with no direct Japan holding. Tries both import paths
    (engine runner adds ai_engine to sys.path); degrades to {}.
    Added by nightly agent 2026-06-29
    `boj_hike_prob_pct` (market-implied next-meeting odds) is optional — None falls
    back to the rate/FX-only read (fully backward compatible).
    """
    try:
        try:
            from risk_scorer import japan_policy_risk_flag  # type: ignore
        except Exception:
            from ai_engine.risk_scorer import japan_policy_risk_flag  # type: ignore
        return japan_policy_risk_flag(
            boj_rate, usd_jpy_rate=usd_jpy_rate, boj_hike_prob_pct=boj_hike_prob_pct
        )
    except Exception:
        logger.debug("japan policy risk unavailable — skipping")
        return {}


def _load_calendar_integrity() -> dict[str, Any]:
    """
    Surface the earnings-date validator (earnings_tracker.validate_earnings_dates)
    so any vendor/calendar date conflict — a stored quarterly-results date that is
    suspiciously_early, implausibly_early, or breaches_deadline, or a third-party
    estimate that disagrees with the internal date — reaches Tho's morning brief as
    a one-line "calendar integrity" note, instead of living only in the DEVLOG.

    Returns a COMPACT dict (issue_count + up to 4 flagged items with the
    reconciliation verdict) so the brief prompt stays small; degrades to
    {"issue_count": 0, "issues": []} on any failure. Confirmed events and
    dates inside the 30-45d SET band are NOT flagged (handled by the validator).
    Added by nightly agent 2026-07-05 (resolves the Jun-30 queued next-priority).
    """
    try:
        v = validate_earnings_dates()
        issues = []
        for r in (v.get("issues") or [])[:4]:
            etype = r.get("event_type", "quarterly_results")
            recon = r.get("reconciliation")
            # Dividend rows carry no vendor `reconciliation`; synthesize a readable
            # verdict from the results-anchored classification so a mis-dated ex-date
            # surfaces with context, not just a bare status.
            # Added by nightly agent 2026-07-15 (resolves the Jul-14 queued item)
            if etype == "interim_dividend_announcement" and not recon:
                ref = r.get("reference_results_date")
                days = r.get("days_after_results")
                if ref is not None and days is not None:
                    recon = (
                        f"REVIEW: interim-dividend ex-date {r.get('expected_date')} falls "
                        f"{days}d after the {ref} results — {r.get('status')}; an ex-date "
                        f"on/before its triggering earnings is implausible, verify on the SET calendar."
                    )
                else:
                    recon = (
                        f"REVIEW: interim-dividend ex-date {r.get('expected_date')} has no "
                        f"anchoring results event ({r.get('status')}); verify on the SET calendar."
                    )
            issues.append(
                {
                    "ticker": r.get("ticker"),
                    "event_type": etype,
                    "expected_date": r.get("expected_date"),
                    "status": r.get("status"),
                    "reconciliation": recon,
                }
            )
        return {"issue_count": len(v.get("issues") or []), "issues": issues}
    except Exception:
        logger.debug("calendar integrity check unavailable — skipping")
        return {"issue_count": 0, "issues": []}


def _load_feed_health_legacy() -> dict[str, Any]:
    """
    Surface data-feed staleness in the morning brief.

    Added by nightly agent 2026-08-08, in direct response to the finding that the
    live market-data collector has been down since 2026-07-15 (23 days) while the
    Aug-05 / Aug-06 / Aug-07 briefs each reported a zero price delta without ever
    saying that the delta was zero because NOBODY ASKED THE MARKET. Three separate
    runs misdiagnosed this as a scraper defect; it is a dead daemon.

    The whole point of this loader is to make that condition impossible to miss:
    if the feed is stale, the brief must say so BEFORE it quotes a single price,
    because a stale mark presented without its age is worse than no mark at all —
    it looks like information and is actually its absence.

    Reads data/feed_health.json (written by data_collector/feed_health.py) rather
    than importing that module, because data_collector and portfolio_engine run in
    separate venvs. Degrades to a benign, explicitly-unknown dict on any failure;
    note that "unknown" is NOT rendered as healthy.
    """
    unknown = {
        "worst_severity": "STALE_UNKNOWN",
        "healthy": False,
        "interpretation": (
            "Feed-health report unavailable — freshness of all prices is UNVERIFIED. "
            "Run data_collector/feed_health.py."
        ),
        "stale_checks": [],
    }
    try:
        path = PROJECT_DIR / "data" / "feed_health.json"
        if not path.exists():
            return unknown
        report = json.loads(path.read_text(encoding="utf-8"))

        # The report itself can go stale. A health check that last ran a week ago
        # tells you the feed was fine a week ago, which is not the question.
        generated = str(report.get("generated_at", ""))[:10]
        try:
            if generated and (date.today() - date.fromisoformat(generated)).days > 2:
                return {
                    **unknown,
                    "interpretation": (
                        f"Feed-health report is itself stale (last run {generated}) — "
                        "price freshness is UNVERIFIED."
                    ),
                }
        except ValueError:
            return unknown

        stale = [
            {
                "name": c.get("name"),
                "severity": c.get("severity"),
                "age_days": c.get("age_days"),
                "detail": c.get("detail") or c.get("error"),
            }
            for c in (report.get("checks") or [])
            if c.get("severity") in ("STALE", "DEAD", "STALE_UNKNOWN")
        ][:4]
        return {
            "worst_severity": report.get("worst_severity", "STALE_UNKNOWN"),
            "healthy": bool(report.get("healthy")),
            "interpretation": report.get("interpretation", ""),
            "stale_checks": stale,
        }
    except Exception:
        logger.debug("feed health unavailable — reporting UNVERIFIED, not healthy")
        return unknown


def _load_feed_health() -> dict[str, Any]:
    """Live feed-health read — Added 2026-10-29 (Phase 2).

    Runs data_collector/feed_health.check_feed_health() in-process (stdlib only)
    so the brief never relies on a days-old report, and separates PRICE feeds
    from the nightly research artifacts: a dead nightly research agent must not
    be reported as stale prices (and vice versa).
    """
    import importlib.util

    try:
        spec = importlib.util.spec_from_file_location(
            "dc_feed_health", PROJECT_DIR / "data_collector" / "feed_health.py"
        )
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)  # type: ignore[union-attr]
        report = module.check_feed_health(write_report=True)
    except Exception:
        logger.exception("live feed-health check failed — falling back to report file")
        return _load_feed_health_legacy()
    checks = report.get("checks") or []
    price_checks = [c for c in checks if c.get("name") != "nightly_artifacts"]
    research = next((c for c in checks if c.get("name") == "nightly_artifacts"), None)
    ok = ("FRESH", "AGING")
    stale = [
        {"name": c.get("name"), "severity": c.get("severity"),
         "age_days": c.get("age_days"), "detail": c.get("detail") or c.get("error")}
        for c in price_checks if c.get("severity") not in ok
    ]
    return {
        "checked_at": report.get("generated_at"),
        "healthy": not stale,
        "worst_severity": "FRESH" if not stale else stale[0]["severity"],
        "interpretation": (
            "Price feeds are fresh." if not stale else
            "Some price inputs are stale or incomplete — see stale_checks; affected figures are not current."
        ),
        "stale_checks": stale,
        "nightly_research": {
            "severity": research.get("severity") if research else "STALE_UNKNOWN",
            "age_days": research.get("age_days") if research else None,
            "legacy_narrative_age_days": research.get("legacy_narrative_age_days") if research else None,
            "note": "Dated snapshots + DB watch lists/market factors (refreshed by the portfolio engine). "
                    "Not a price feed.",
        },
    }


_CRYPTO_MARKERS = ("BTC", "ETH", "CRYPTO", "COIN", "DOGE", "SOL-")


def _fmt_num(value: Any, digits: int = 2) -> str:
    try:
        return f"{float(value):,.{digits}f}"
    except (TypeError, ValueError):
        return "n/a"


def _render_facts(ctx: dict[str, Any], perf_rows: list[dict[str, Any]], snap: dict[str, Any]) -> str:
    """Deterministic, sourced facts block — Added 2026-10-29 (Phase 2).

    Built in Python (never by the LLM) so every number shown is a real, dated
    value from the DB / snapshot. Missing values are shown as n/a.
    """
    kf = ctx.get("key_facts") or {}
    fh = ctx.get("feed_health") or {}
    lines: list[str] = []
    if not fh.get("healthy", False):
        lines.append("🚨 DATA WARNING: " + str(fh.get("interpretation", "price freshness unverified")))
        for c in fh.get("stale_checks") or []:
            lines.append(f"  - {c.get('name')}: {c.get('severity')} ({c.get('detail') or 'no detail'})")
    research = fh.get("nightly_research") or {}
    if research.get("severity") not in (None, "FRESH", "AGING"):
        lines.append(
            f"ℹ️ Watch-list/factor refresh is {research.get('severity')} "
            f"(~{_fmt_num(research.get('age_days'), 1)} days old) — factor readings may be out of date."
        )
    _wl_age = (ctx.get("data_freshness") or {}).get("watchlist_macro_age_days")
    if isinstance(_wl_age, (int, float)) and _wl_age > BRIEF_STALE_DAYS:
        lines.append(
            f"ℹ️ Legacy nightly-research narrative is ~{_wl_age:.0f} days old (agent paused) — its narrative "
            "flags are omitted; live macro levels are in the market-factor list above."
        )
    lines.append("")
    lines.append("**Holdings (latest closes)**")
    snap_h = (snap or {}).get("holdings") or {}
    for r in kf.get("latest_closes") or []:
        t = r.get("ticker")
        if t == "USDTHB=X":
            continue
        h = snap_h.get(t) or {}
        extra = ""
        if h.get("market_value_thb") is not None:
            extra = (f" | value {_fmt_num(h.get('market_value_thb'), 0)} THB, "
                     f"P/L {_fmt_num(h.get('pnl_thb'), 0)} THB ({_fmt_num(h.get('pnl_pct'))}%)")
        elif h.get("error"):
            extra = " | not valued in snapshot"
        lines.append(f"- {t}: {_fmt_num(r.get('close_price'), 4 if t == 'SCBGOLDE' else 2)} "
                     f"(as of {r.get('price_date')}, {r.get('source')}){extra}")
    fx = next((r for r in kf.get("latest_closes") or [] if r.get("ticker") == "USDTHB=X"), None)
    if fx:
        lines.append(f"- USD/THB: {_fmt_num(fx.get('close_price'), 3)} (as of {fx.get('price_date')})")
    ps = kf.get("portfolio_snapshot") or {}
    lines.append(
        f"- Portfolio total: {_fmt_num(ps.get('total_market_value_thb'), 0)} THB, "
        f"P/L {_fmt_num(ps.get('total_pnl_thb'), 0)} THB (snapshot {str(ps.get('generated_at'))[:16]} UTC)"
    )
    if ps.get("valuation_complete") is False:
        lines.append(f"  ⚠️ {ps.get('total_value_caveat') or 'valuation incomplete'}")
    lines.append("")
    lines.append("**Portfolio health**")
    rs = kf.get("latest_risk_score") or {}
    lines.append(f"- Risk score: {_fmt_num(rs.get('risk_score'), 4)} (recorded {rs.get('record_date', 'n/a')})")
    vals = [(r.get("record_date"), r.get("total_value_thb")) for r in perf_rows if r.get("total_value_thb") is not None]
    if len(vals) >= 2:
        newest, oldest = vals[0], vals[-1]
        try:
            chg = (float(newest[1]) / float(oldest[1]) - 1) * 100
            lines.append(f"- Value trend: {_fmt_num(oldest[1], 0)} → {_fmt_num(newest[1], 0)} THB "
                         f"({chg:+.2f}%, {oldest[0]} → {newest[0]}, priced holdings only)")
        except (TypeError, ValueError, ZeroDivisionError):
            pass
    exits = ctx.get("exit_signals") or []
    lines.append(f"- Exit signals: {len(exits)}" + ("" if not exits else " — " + ", ".join(
        str(e.get("ticker")) for e in exits if isinstance(e, dict))))
    ms = kf.get("macro_mood") or {}
    lines.append(f"- News-sentiment mood: {ms.get('market_mood', 'n/a')} (as of {ms.get('snapshot_date', 'n/a')})")
    cat = ctx.get("catalyst_alerts") or {}
    for c in (cat.get("imminent") or [])[:3]:
        if isinstance(c, dict):
            lines.append(f"- Upcoming catalyst {c.get('date')}: {c.get('description')}"
                         f"{'' if c.get('confirmed') else ' (unconfirmed)'}")
    ea = ctx.get("earnings_alerts") or {}
    if ea.get("summary_text"):
        lines.append(f"- Earnings: {ea.get('summary_text')}")
    arts = [a for a in (ctx.get("high_impact_articles") or []) if isinstance(a, dict)
            and not any(m in str(a.get("ticker", "")).upper() or m in str(a.get("source", "")).upper()
                        for m in _CRYPTO_MARKERS)]
    if arts:
        lines.append("")
        lines.append("**Notable headlines (24h)**")
        for a in arts[:4]:
            lines.append(f"- [{a.get('sentiment')}] {a.get('title')} — {a.get('source')}")
    return "\n".join(lines)


def _commentary_prompt(facts_md: str, holdings_line: str) -> str:
    try:
        from holding_meta import owner_hold_tickers
        _holds = ", ".join(sorted(owner_hold_tickers())) or "none"
    except Exception:  # noqa: BLE001
        _holds = "none"
    return f"""You are a careful investment advisor for Tho, a Thai retail investor
(horizon 3 months to 2 years, base currency THB, not interested in crypto).
His holdings: {holdings_line}.

Below are VERIFIED FACTS. Write a short advisor commentary based ONLY on them.
Rules: do not introduce any number, price, level or date that is not in the facts.
If something important is missing, say it is unavailable. Advisory only, no trades.
Do not mention asset classes or holdings that are not listed above (he holds no bonds unless listed).
When you mention a price move, use exactly the direction and sign shown in the facts (e.g. "-4.6%" means it FELL).
Risk-engine figures are provisional until Tho confirms his holdings; say so if you cite them.
Include one point on FOREIGN-CURRENCY risk (USD/THB; up = weaker baht) using only the FX figures in the facts.
OWNER HOLDS ({_holds}): Tho will not sell them until he is satisfied with this project. Never suggest
selling or trimming them; a concentration/limit note about them is INFORMATIONAL only.

Respond ONLY as JSON:
{{"commentary": "3-5 short bullet points (markdown '- '), max 220 words, covering the holdings, portfolio risk/concentration and any data warning",
  "action_items": ["max 3 concrete, cautious next steps"]}}

VERIFIED FACTS:
{facts_md}"""


def _load_reported_actuals(
    tickers: tuple[str, ...] = ("SCB.BK", "PTTEP.BK", "BAFS.BK"),
    max_age_days: int = 45,
) -> list[dict[str, Any]]:
    """
    Surface any RECENTLY-REPORTED earnings actuals + reconciliation for the given
    holdings so the morning brief switches from a stale "preview" read to the
    "reported + reconciled" verdict (e.g. SCB Q2-2026: THB 11.12bn, a ~2% beat on
    Q2 consensus but H1 modestly soft vs the range; yield thesis holds on a lower
    base). Reads via earnings_tracker.load_earnings_actual() and returns a COMPACT,
    prompt-sized item per holding that has a fresh actuals file.

    Each item: {ticker, company, period, reported_date, verdict, dividend_status,
    thesis_read, advisory}. Only actuals whose reported_date is within max_age_days
    of today are returned (so an old print doesn't linger in the brief). Degrades
    to [] on any failure.

    Added by nightly agent 2026-07-25 (resolves the Jul-24 queued next-priority:
    wire load_earnings_actual() into brief_generator).
    """
    from datetime import datetime

    out: list[dict[str, Any]] = []
    today = date.today()
    for ticker in tickers:
        try:
            actual = load_earnings_actual(ticker)
        except Exception:
            actual = None
        if not actual:
            continue
        meta = actual.get("_meta", {}) or {}
        reported_str = meta.get("reported_date")
        # Skip stale prints so only the current-quarter read reaches the brief.
        if reported_str:
            try:
                reported_d = datetime.strptime(reported_str, "%Y-%m-%d").date()
                if (today - reported_d).days > max_age_days:
                    continue
            except ValueError:
                pass
        recon = actual.get("reconciliation_vs_preview", {}) or {}
        div = actual.get("dividend_outcome", {}) or {}
        thesis = actual.get("yield_thesis_assessment", {}) or {}
        out.append(
            {
                "ticker": ticker,
                "company": meta.get("company_name", ticker),
                "period": meta.get("period", ""),
                "reported_date": reported_str,
                "verdict": recon.get("verdict", ""),
                "dividend_status": div.get("interim_2026_status")
                or ("declared" if div.get("declared_with_q2_results") else "not_declared"),
                "thesis_holds": thesis.get("holds"),
                "thesis_read": (thesis.get("read") or "")[:280],
                "advisory": (actual.get("advisory_note_for_tho") or "")[:220],
            }
        )
    return out



def _load_council_reports(
    holdings: tuple[str, ...] = ("SCB.BK", "PTTEP.BK", "BAFS.BK", "SCBGOLDE"),
    max_items: int = 8,
) -> dict[str, Any]:
    """
    Load compact Guru Council report summaries from data/council/reports/.

    Injected into the morning brief so Tho sees chair stance / conviction for
    holdings (and a few high-conviction peers) without re-running the council.
    Degrades to a clear "no council report" payload when the directory is empty
    or unreadable — never raises into brief generation.

    Added 2026-10-07 (improvement #1 — council → daily brief).
    """
    reports_dir = PROJECT_DIR / "data" / "council" / "reports"
    empty = {
        "available": False,
        "status": "no_council_report",
        "message": (
            "No council report on file. Run: "
            "python3 -m guru_council.cli analyze SCB.BK PTTEP.BK BAFS.BK SCBGOLDE"
        ),
        "holdings": [],
        "other_top": [],
        "report_count": 0,
    }
    if not reports_dir.exists():
        return empty
    try:
        files = sorted(reports_dir.glob("*.json"))
        if not files:
            return empty
        holding_set = {h.upper() for h in holdings}
        holdings_out: list[dict[str, Any]] = []
        others: list[dict[str, Any]] = []
        for path in files:
            try:
                report = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            inv = report.get("investment") or {}
            chair = report.get("chair") or {}
            ticker = str(inv.get("ticker") or path.stem).upper()
            item = {
                "ticker": ticker,
                "name": inv.get("name", ticker),
                "asset_class": inv.get("asset_class"),
                "overall_stance": chair.get("overall_stance"),
                "overall_label": chair.get("overall_label"),
                "blended_conviction": chair.get("blended_conviction"),
                "agreement": (chair.get("agreement") or "")[:180],
                "created_at": report.get("created_at"),
                "llm_used": bool(report.get("llm_used")),
                "discovered": bool(report.get("discovered")),
                "advisory_only": True,
            }
            if ticker in holding_set:
                holdings_out.append(item)
            else:
                others.append(item)

        def _conv(row: dict[str, Any]) -> float:
            try:
                return float(row.get("blended_conviction") or 0)
            except (TypeError, ValueError):
                return 0.0

        holdings_out.sort(key=_conv, reverse=True)
        others.sort(key=_conv, reverse=True)
        other_top = others[: max(0, max_items - len(holdings_out))]
        return {
            "available": True,
            "status": "ok",
            "message": f"{len(holdings_out) + len(other_top)} council report(s) loaded from data/council/reports/",
            "holdings": holdings_out,
            "other_top": other_top,
            "report_count": len(files),
        }
    except Exception:
        logger.debug("council reports unavailable — degrading gracefully", exc_info=True)
        return empty


async def ensure_daily_briefs_table() -> None:
    pool = await db_pool.get_pool()
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_briefs (
          id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
          brief_date DATE UNIQUE,
          content TEXT,
          macro_mood VARCHAR(50),
          portfolio_risk_score DECIMAL(5,4),
          top_opportunities JSONB,
          action_items JSONB,
          generated_at TIMESTAMPTZ DEFAULT NOW()
        )
        """
    )


async def generate_daily_brief() -> dict[str, Any]:
    await ensure_daily_briefs_table()
    pool = await db_pool.get_pool()
    macro = await pool.fetchrow("SELECT * FROM macro_sentiment ORDER BY snapshot_date DESC LIMIT 1")
    performance = await pool.fetch(
        "SELECT * FROM portfolio_performance ORDER BY record_date DESC LIMIT 7"
    )
    opportunities = (await scan_opportunities())[:5]
    exits = (await check_exit_signals())[:3]

    # Cross-market tech momentum signals — Added by nightly agent 2026-06-12
    # Fetches top 3 from tech_screener (uses yfinance; degrades gracefully to [])
    try:
        tech_signals = await tech_screener(top_n=3)
    except Exception:
        logger.warning("tech_screener() failed in brief generation — using empty list")
        tech_signals = []

    # 7-day portfolio value trend for Section 5 — Added by nightly agent 2026-06-12
    snapshot_trend_7d = _load_snapshot_trend(days=7)

    # Pre-earnings alert context — Added by nightly agent 2026-06-13
    # Runs nightly check (seeds calendar if empty) and returns 3-day alert window
    try:
        earnings_context = pre_earnings_brief(alert_days=3)
    except Exception:
        logger.warning("earnings pre-brief failed — skipping")
        earnings_context = {"has_upcoming_earnings": False, "alerts": [], "summary_text": ""}
    articles = await pool.fetch(
        """
        SELECT s.ticker, s.sentiment, s.score, s.confidence, s.impact_level,
               a.title, a.source, a.published_at
        FROM sentiment_scores s JOIN news_articles a ON a.id = s.article_id
        WHERE s.analyzed_at >= NOW() - INTERVAL '24 hours'
        ORDER BY CASE s.impact_level WHEN 'high' THEN 3 WHEN 'medium' THEN 2 ELSE 1 END DESC,
                 s.confidence DESC
        LIMIT 5
        """
    )
    recommendations = await pool.fetch(
        """
        SELECT * FROM recommendations
        WHERE validated_by IS NOT NULL AND cardinality(validated_by) > 0
        ORDER BY created_at DESC LIMIT 3
        """
    )
    prices = await pool.fetch(
        """
        SELECT DISTINCT ON (m.ticker) m.ticker, m.price_date, m.close_price
        FROM market_prices m JOIN holdings h ON h.ticker = m.ticker
        WHERE m.price_date <= CURRENT_DATE - 1
        ORDER BY m.ticker, m.price_date DESC
        """
    )
    # Load multi-market intel and watchlist — Added by nightly agent 2026-06-09
    market_intel_text = _load_latest_market_intel()
    watchlist_snapshot = _load_watchlist_snapshot()
    macro_context = watchlist_snapshot.get("macro_context", {})

    # PTTEP oil-price scenario analysis — Added by nightly agent 2026-06-14
    # Reads current Brent from watchlist macro_context; missing stays unknown.
    try:
        _brent_raw = macro_context.get("brent_crude_usd")
        current_brent = float(_brent_raw) if _brent_raw is not None else None
        oil_scenario = (run_oil_scenario_report(current_brent_usd=current_brent) if current_brent is not None
                        else {"status": "unknown", "reason": "Brent price unavailable"})
    except Exception:
        logger.warning("oil scenario report failed — skipping")
        oil_scenario = {"status": "unknown", "reason": "Brent-dependent analysis unavailable"}

    # PTTEP position-level oil risk score — Added by nightly agent 2026-06-17
    # Surfaces the numeric oil_scenario_risk_flag output (risk_level +
    # position_risk_score) in the brief alongside the scenario table, so Tho sees
    # the position RISK LEVEL, not just the scenario narrative. Last run's queued #1.
    try:
        _brent_raw = macro_context.get("brent_crude_usd")
        _brent_now = float(_brent_raw) if _brent_raw is not None else None
        _deal_flag = str(macro_context.get("us_iran_status_flag", "")).lower()
        _deal_confirmed = any(
            k in _deal_flag for k in ("confirmed", "signed", "framework", "complete")
        )
        oil_position_risk = (_load_oil_position_risk(_brent_now, _deal_confirmed) if _brent_now is not None
                             else {"status": "unknown", "reason": "Brent price unavailable"})
    except Exception:
        logger.warning("oil position risk flag failed — skipping")
        oil_position_risk = {"status": "unknown", "reason": "Brent-dependent analysis unavailable"}

    # Probability-weighted oil outlook — Added by nightly agent 2026-06-19
    # Collapses the named Brent scenarios into one expected-value read (expected
    # Brent + expected PTTEP net-income change) so the brief carries a single
    # forward number alongside the scenario table. Last run's queued #1.
    try:
        oil_weighted_outlook = probability_weighted_outlook()
    except Exception:
        logger.warning("oil weighted outlook failed — skipping")
        oil_weighted_outlook = {}

    # Fed-policy risk on gold + baht — Added by nightly agent 2026-06-19
    # Surfaces the numeric fed_policy_risk_flag (risk_level + score) in Section 2,
    # driven by the realised funds rate + dot-plot bias from the watchlist macro
    # context, so the gold/currency read is data-driven. Last run's queued #2.
    try:
        _fed_raw = macro_context.get("us_fed_funds_rate_pct")
        _fed_rate = float(_fed_raw) if _fed_raw is not None else None
        _fed_bias = str(
            macro_context.get("fomc_jun17_dot_plot_bias")
            or macro_context.get("fed_dot_plot_bias")
        )
        # Market-implied next-meeting hike odds (Added by nightly agent 2026-06-27);
        # None when absent → text-only bias (backward compatible).
        _hp_raw = macro_context.get("fed_hike_prob_next_meeting_pct")
        _fed_hike_prob = float(_hp_raw) if _hp_raw is not None else None
        fed_policy_risk = (_load_fed_policy_risk(_fed_rate, _fed_bias, hike_prob_pct=_fed_hike_prob)
                           if _fed_rate is not None else {"status": "unknown", "reason": "Fed funds rate unavailable"})
    except Exception:
        logger.warning("fed policy risk flag failed — skipping")
        fed_policy_risk = {"status": "unknown", "reason": "Fed-dependent analysis unavailable"}

    # Gold-fund drawdown classification — Added by nightly agent 2026-06-20
    # Labels a falling gold NAV as a Fed-driven dip (hold/add) vs a possible
    # trend break (review), by cross-referencing drawdown depth with the Fed
    # flag. Prefers NAV (THB); falls back to gold spot (USD). Last run's queued #1.
    try:
        _nav_cur = macro_context.get("scbgolde_estimated_nav_thb")
        _nav_high = macro_context.get("scbgolde_trailing_high_nav_thb")
        if _nav_cur is not None and _nav_high is not None:
            _g_cur, _g_high = float(_nav_cur), float(_nav_high)
        else:
            _g_cur_raw = macro_context.get("gold_current_usd", macro_context.get("gold_spot_usd"))
            _g_high_raw = macro_context.get("gold_recent_high_usd", macro_context.get("gold_trailing_high_usd"))
            _g_cur = float(_g_cur_raw) if _g_cur_raw is not None else None
            _g_high = float(_g_high_raw) if _g_high_raw is not None else None
        gold_drawdown = (_load_gold_drawdown(_g_cur, _g_high, fed_policy_risk)
                         if _g_cur is not None and _g_high is not None and _g_high > 0
                         else {"status": "unknown", "reason": "gold current/high levels unavailable"})
    except Exception:
        logger.warning("gold drawdown monitor failed — skipping")
        gold_drawdown = {"status": "unknown", "reason": "gold drawdown inputs unavailable"}

    # Baht-regime FX trade-off — Added by nightly agent 2026-06-26
    # Surfaces the two-sided currency_regime_flag in Section 2: a weak baht
    # cushions SCBGOLDE's THB NAV while raising FX entry cost for new USD buys.
    # Reads USD/THB + the prior 1-yr high from the watchlist and the gold-sleeve
    # weight from the live snapshot. Last run's queued #2 (baht-regime watch).
    try:
        _usd_thb = _parse_leading_float(macro_context.get("usd_thb", macro_context.get("usd_thb_rate")))
        _usd_thb_high = _parse_leading_float(macro_context.get("usd_thb_1yr_high"))
        _scbgolde_w = _load_scbgolde_weight()
        currency_regime = (
            _load_currency_regime(_usd_thb, _usd_thb_high, _scbgolde_w)
            if None not in (_usd_thb, _usd_thb_high, _scbgolde_w) and _usd_thb > 0
            else {"status": "unknown", "reason": "USD/THB level, high, or gold weight unavailable"}
        )
    except Exception:
        logger.warning("currency regime flag failed — skipping")
        currency_regime = {"status": "unknown", "reason": "currency-regime inputs unavailable"}

    # BOJ carry-unwind risk for Section 4 (Regional) — Added by nightly agent 2026-06-29
    # Surfaces the numeric japan_policy_risk_flag (risk_level + score + priced BOJ
    # hike odds) so the brief's Japan line states the carry-trade-unwind risk a
    # weak-yen spot read alone hides. Reads the BOJ rate, USD/JPY, and the market-
    # implied next-meeting hike odds from the watchlist macro context. Last run's
    # queued #1 (surface japan_policy_risk_flag in the brief).
    try:
        _boj_raw = macro_context.get("boj_policy_rate_pct")
        _boj_rate = float(_boj_raw) if _boj_raw is not None else None
        _usd_jpy = macro_context.get("usd_jpy", macro_context.get("usd_jpy_rate"))
        _usd_jpy = float(_usd_jpy) if _usd_jpy is not None else None
        _boj_hp_raw = macro_context.get("boj_hike_prob_next_meeting_pct")
        _boj_hike_prob = float(_boj_hp_raw) if _boj_hp_raw is not None else None
        japan_policy_risk = (_load_japan_policy_risk(
            _boj_rate, usd_jpy_rate=_usd_jpy, boj_hike_prob_pct=_boj_hike_prob
        ) if _boj_rate is not None else {"status": "unknown", "reason": "BOJ policy rate unavailable"})
    except Exception:
        logger.warning("japan policy risk flag failed — skipping")
        japan_policy_risk = {"status": "unknown", "reason": "BOJ-dependent analysis unavailable"}

    # Catalyst slippage / this-week watch — Added by nightly agent 2026-06-16
    # Surfaces (a) scheduled catalysts that passed without confirmation and
    # (b) catalysts landing within 5 days, so the brief opens with these facts
    # rather than relying on the LLM to infer them from free-text notes.
    try:
        catalyst_summary = catalyst_alert_summary(horizon_days=5)
    except Exception:
        logger.warning("catalyst alert summary failed — skipping")
        catalyst_summary = {"imminent_count": 0, "slipped_count": 0, "imminent": [], "slipped": []}

    # Earnings calendar-integrity check for the Catalyst Watch header — Added 2026-07-05
    # Surfaces any suspiciously_early / breaches_deadline vendor-vs-internal date
    # conflict (e.g. the PTTEP Aug-11 vs Yahoo Jul-23 case) so Tho sees it directly.
    # Last run's queued #1.
    calendar_integrity = _load_calendar_integrity()

    context = to_jsonable(
        {
            "macro_sentiment": dict(macro) if macro else None,
            "portfolio_performance_7d": [dict(row) for row in performance],
            "top_opportunities": opportunities,
            "exit_signals": exits,
            "high_impact_articles": [dict(row) for row in articles],
            "validated_recommendations": [dict(row) for row in recommendations],
            "holdings_yesterday_close": [dict(row) for row in prices],
            # Added 2026-06-09: multi-market context from nightly agent
            "multi_market_macro": macro_context,
            # Added 2026-06-12: cross-market tech momentum for Section 3
            "tech_screener_top3": tech_signals,
            # Added 2026-06-12: 7-day portfolio value trend for Section 5
            "portfolio_trend_7d": snapshot_trend_7d,
            # Added 2026-06-13: upcoming earnings alerts for Section 5/6
            "earnings_alerts": earnings_context,
            # Added 2026-06-14: PTTEP Brent scenario analysis for Section 1
            "pttep_oil_scenarios": oil_scenario,
            # Added 2026-06-17: PTTEP position-level oil risk score for Section 1
            "pttep_oil_risk_flag": oil_position_risk,
            # Added 2026-06-19: probability-weighted oil expected-value read for Section 1
            "pttep_oil_weighted_outlook": oil_weighted_outlook,
            # Added 2026-06-19: Fed-policy risk on gold + baht for Section 2
            "fed_policy_risk_flag": fed_policy_risk,
            # Added 2026-06-20: gold-fund drawdown classification for Section 2
            "gold_drawdown_flag": gold_drawdown,
            # Added 2026-06-26: baht-regime FX trade-off for Section 2
            "currency_regime_flag": currency_regime,
            # Added 2026-06-29: BOJ carry-unwind risk for Section 4 (Regional)
            "japan_policy_risk_flag": japan_policy_risk,
            # Added 2026-06-16: slipped + this-week catalyst alerts for the brief header
            "catalyst_alerts": catalyst_summary,
            # Added 2026-07-05: earnings calendar-integrity issues for the header
            "calendar_integrity": calendar_integrity,
            # Added 2026-07-25: recently-reported earnings actuals + reconciliation for Section 5
            "reported_earnings_actuals": _load_reported_actuals(),
            # Added 2026-08-08: data-feed staleness — gates every price in the brief
            "feed_health": _load_feed_health(),
            # Added 2026-10-07: Guru Council reports for holdings (+ top peers)
            "council_reports": _load_council_reports(),
        }
    )
    # Phase 2 (2026-10-29): real holdings from DB, stale-input filter, size budget
    from holding_meta import lock_label, load_attrs, is_pending
    _attrs = await load_attrs(pool)
    holdings_rows = await pool.fetch(
        "SELECT ticker, name, asset_class FROM holdings WHERE quantity > 0 OR ticker = ANY($1::text[]) ORDER BY ticker",
        [t for t, a in _attrs.items() if is_pending(a)],
    )
    holdings_line = ", ".join(
        f"{r['ticker']} ({r['name'] or r['asset_class']}"
        + (f"; {lock_label(_attrs.get(r['ticker']))}" if lock_label(_attrs.get(r['ticker'])) else "") + ")"
        for r in holdings_rows
    ) or "no holdings recorded"
    # key_facts: verified, dated numbers computed here so the model need not dig
    latest_px = await pool.fetch(
        """
        SELECT DISTINCT ON (ticker) ticker, price_date, close_price, source
        FROM market_prices WHERE ticker IN (SELECT ticker FROM holdings) OR ticker = 'USDTHB=X'
        ORDER BY ticker, price_date DESC
        """
    )
    try:
        from utils.common import load_snapshot as _load_snap
        snap = _load_snap()
    except Exception:
        snap = {}
    context["key_facts"] = to_jsonable({
        "latest_closes": [dict(r) for r in latest_px],
        "portfolio_snapshot": {
            k: snap.get(k) for k in (
                "generated_at", "total_market_value_thb", "total_pnl_thb",
                "valuation_complete", "unpriced_holdings", "total_value_caveat",
            )
        },
        "latest_risk_score": (
            {"record_date": performance[0]["record_date"], "risk_score": performance[0]["risk_score"]}
            if performance else None
        ),
        "macro_mood": (
            {"snapshot_date": macro["snapshot_date"], "market_mood": macro["market_mood"]}
            if macro else None
        ),
    })
    context = _prepare_brief_context(
        context, (watchlist_snapshot.get("_meta") or {}).get("last_updated")
    )
    intel_age = _age_days(_latest_market_intel_date())
    if intel_age is None or intel_age > BRIEF_STALE_DAYS:
        market_intel_text = ""
    # Enhanced prompt with per-market sections — Added by nightly agent 2026-06-09
    market_intel_section = (
        f"\n\nLatest nightly market intelligence:\n{market_intel_text}"
        if market_intel_text else ""
    )
    prompt = f"""You are a professional investment advisor writing a morning brief for a private
Thai investor (Tho). His current holdings: {holdings_line}. Medium-term horizon (3 months–2 years). Base currency: THB.

Write in clear structured format. FIRST, before anything else including the Catalyst Watch header, check feed_health. If feed_health.healthy is false, open the brief with a **🚨 DATA FEED WARNING** block quoting feed_health.interpretation and, for each entry in feed_health.stale_checks, the check name and its age_days. Then state plainly, in your own words, that because the feed is stale ANY price, weight, P&L or "no change" figure in the rest of this brief is a CARRIED-FORWARD mark of that age and not a current one — a flat reading is absence of data, not absence of movement — and that Tho should not rebalance, size a position, or act on a level off these numbers until the feed is restored. Do NOT soften this and do NOT bury it lower down; it changes how every other number in the brief should be read. If feed_health.healthy is true, omit the block entirely and write nothing about feeds. Then the one-line **⚠️ Catalyst Watch** header BEFORE Section 1, built from catalyst_alerts: if slipped_count > 0, list each slipped entry's date + a short label and say it needs verification before any dependent thesis is treated as resolved; then on the same header list imminent catalysts (date + short label) landing within 5 days. If both counts are 0, write "⚠️ Catalyst Watch: none flagged". Then, if calendar_integrity.issue_count > 0, add a one-line **📅 Calendar integrity** note immediately after the Catalyst Watch header: for each item in calendar_integrity.issues give ticker + expected_date + status, and if reconciliation is present quote its KEEP/REVIEW/AMBIGUOUS verdict verbatim (e.g. "📅 Calendar integrity: PTTEP.BK Aug-11 vs Yahoo Jul-23 — KEEP internal (in 30-45d band); REJECT Jul-23 (suspiciously_early)"). If an item's event_type is "interim_dividend_announcement", label it as a dividend ex-date issue (e.g. "📅 Calendar integrity: SCB.BK interim-dividend ex-date looks mis-dated vs its results date — verify on the SET calendar"), not an earnings-date issue. This tells Tho a vendor/calendar date is unverified so he does not act on a wrong earnings or ex-dividend date. If issue_count is 0, omit this line entirely. Then the SECTIONS:
1. **Thailand / SET** — SET index level, BAFS/PTTEP/SCB news, tourism/economy. For PTTEP, use pttep_oil_scenarios (current_impact + scenarios keyed by Brent regime) to give a concrete oil-sensitivity read: note the deal-signed/Hormuz-open scenario, estimated net-income change vs base, and whether the dividend looks maintained — do NOT just repeat oil headlines. Then state PTTEP's position-level oil risk from pttep_oil_risk_flag in one short phrase (risk_level + position_risk_score), e.g. "oil risk: elevated (0.42)". Also add one line from pttep_oil_weighted_outlook giving the single probability-weighted expectation (expected_brent_usd, expected_net_income_change_pct, expected_yield_base_pct), e.g. "weighted view: Brent ~$83, PTTEP NI -11% vs base, yield ~4.5%"
2. **Gold & Currency** — gold price direction, USD/THB rate impact on gold fund NAV. Use fed_policy_risk_flag to state the US-monetary-policy headwind on gold/baht in one short phrase (risk_level + risk_score), e.g. "Fed policy drag: elevated (0.59)", and if fed_policy_risk_flag.hike_prob_pct is present, cite the market-implied next-meeting hike odds alongside it (e.g. "Fed drag: elevated (0.51); market prices ~80% Dec hike") since the score is now grounded in that priced probability, not just dot-plot text. Connect it to the gold-fund NAV outlook (higher-for-longer = real-yield headwind on the non-yielding gold fund). Then use gold_drawdown_flag to tell Tho what KIND of dip the gold fund is in: state classification + drawdown_pct + the signal in one phrase, e.g. "gold drawdown: fed_driven_dip, -8.0% off the high → hold/add (not a trend break)". This is the key action call — make clear a Fed-driven dip is a hold/add for a medium-term holder, whereas a trend_break_watch warrants reviewing the position. Then state the BAHT-REGIME FX trade-off from currency_regime_flag in one or two phrases: give risk_level + risk_score (e.g. "baht regime: elevated (0.43), regime-break"), and make the TWO-SIDED point explicit for a THB-based holder — the weak baht CUSHIONS SCBGOLDE's THB NAV (use scbgolde_thb_nav_cushion_pct if present) so the gold position can ride, while it RAISES the FX entry cost of any new USD-denominated buy (so stagger, don't convert in size). If a higher threshold (e.g. 33.5) is crossed, flag it
3. **US Technology & AI** — key overnight US tech news; use tech_screener_top3 signals (ticker, market, rsi, price_vs_sma20, signal) for data-driven momentum commentary
4. **Regional Markets** — brief note on Japan, India, Vietnam, China. For Japan, use japan_policy_risk_flag to state the BOJ carry-trade-unwind risk numerically in one short phrase (risk_level + risk_score), e.g. "Japan/BOJ carry risk: low (0.45)", and if japan_policy_risk_flag.boj_hike_prob_pct is present, cite the market-implied next-meeting BOJ hike odds alongside it (e.g. "carry risk: low (0.49); ~20% priced for a late-Jul hike, ~2% terminal path"). Make the medium-term point explicit for Tho: a weak spot yen (USD/JPY ~160) keeps the carry trade intact TODAY, but a priced BOJ tightening path is a FORWARD risk to EM/Asian capital flows (incl. the SET) — so it is a watch item, not a today-action. If carry_threshold_breached is true or the level is elevated/high, flag it more prominently
5. **Portfolio Health** — risk score, any exit signals, rebalancing flags; summarise 7-day portfolio value trend from portfolio_trend_7d (direction, % change, risk_level shift if any); if earnings_alerts.has_upcoming_earnings is true, include a "⚠️ Upcoming Earnings" note with ticker, date, days_until. If reported_earnings_actuals is non-empty, add a "✅ Reported" line for each item using the RECONCILED read (not a stale preview): give ticker + period + verdict + dividend_status, then one clause on whether the thesis holds from thesis_holds/thesis_read (e.g. "✅ Reported: SCB.BK H1-2026 inline_to_slightly_soft, interim div not_yet_declared → yield thesis holds on a lower ~THB 10-11 DPS base (~6.5-7%)"). This ensures Tho sees the confirmed result, not the outdated consensus estimate
6. **Action Items** — exactly 3 specific, actionable items for today
7. **Guru Council** — if council_reports.available is true, add a compact Council block: for each item in council_reports.holdings give ticker + overall_label + blended_conviction (and one short clause from agreement if present); then optionally list up to 3 from council_reports.other_top the same way. Mark the block as ADVISORY ONLY (no auto-trade). If council_reports.available is false, write a one-line section: "Guru Council: no council report on file — run `python3 -m guru_council.cli analyze …`" quoting council_reports.message.

Write in English. Keep under 700 words total. Be direct and data-driven.
STRICT DATA RULE: use only numbers present in the context below. If a field is missing,
null, or listed in data_freshness.omitted_stale_inputs, write "data unavailable" for it.
Never estimate, recall from memory, or invent prices, levels, dates or percentages.
Start from key_facts (verified, dated numbers) and quote the as-of date next to each figure.
Only write "data unavailable" when the value truly is absent from the context.

Respond ONLY as JSON:
{{"content": "full brief with all 6 sections", "action_items": ["item 1", "item 2", "item 3"]}}

Portfolio context: {json_dumps(context)}{market_intel_section}"""
    # Phase 2: deterministic facts + short LLM commentary (the 7k-char template
    # prompt above is kept for reference but is too complex for a local 8B model)
    try:
        from utils.common import load_snapshot as _load_snap2
        _snap_full = _load_snap2()
    except Exception:
        _snap_full = {}
    facts_md = _render_facts(context, [dict(r) for r in performance], _snap_full)
    # Phase 3 (2026-10-29): open with factors past thresholds; add watch list + risk summaries.
    try:
        import watchlists as _wl
        import risk_engine as _re
        _pool3 = await db_pool.get_pool()
        _sec = await _wl.render_brief_sections(_pool3)
        _risk_md = _re.render_brief_section(await _re.latest_risk_report(_pool3))
        facts_md = f"{_sec['opening']}\n\n{facts_md}\n\n{_sec['watchlist']}\n\n{_risk_md}"
        _rr = await _re.latest_risk_report(_pool3)
        _kp = await _wl.key_points(_pool3, (_rr or {}).get("summary"))
    except Exception as _exc:  # noqa: BLE001
        logger.warning("Phase 3 brief sections unavailable: %s", _exc)
        facts_md = f"ℹ️ Watch list / factor / risk sections unavailable ({type(_exc).__name__}).\n\n{facts_md}"
        _kp, _rr = [], None
    # Phase 4 (2026-10-30): signals, regime and PROPOSED trade plans.
    try:
        import signals as _sg
        facts_md = f"{facts_md}\n\n{await _sg.brief_section(await db_pool.get_pool())}"
    except Exception as _exc:  # noqa: BLE001
        logger.warning("Phase 4 signals section unavailable: %s", _exc)
    # 2026-11-01 (P2.2): macro board, policy rates, holding-sector moves, news digest, crypto events (context only)
    try:
        import market_context as _mc
        facts_md = f"{facts_md}\n\n{await _mc.render_brief_section(await db_pool.get_pool())}"
    except Exception as _exc:  # noqa: BLE001
        logger.warning("Market context section unavailable: %s", _exc)
    try:
        import predictions as _pr
        _pp = await db_pool.get_pool()
        facts_md = f"{facts_md}\n\n{_pr.render_brief_section(await _pr.scoreboard(_pp), await _pr.latest_predictions(_pp))}"
    except Exception as _exc:  # noqa: BLE001
        logger.warning("Prediction section unavailable: %s", _exc)
    prompt = _commentary_prompt(facts_md, holdings_line)
    if _kp:
        prompt += "\n\nKEY POINTS (verified - your commentary must agree with every one of these):\n" + "\n".join(f"- {k}" for k in _kp)
    _limits_breached = bool(((_rr or {}).get("summary") or {}).get("limit_breaches"))
    import re as _re_mod
    _contra = _re_mod.compile(r"(limits?\s+(are|is|have)\s+not\s+(been\s+)?exceed|not\s+exceed(ed)?\s+(the\s+)?(risk\s+)?limit|within\s+(the\s+|its\s+|risk\s+)?limits)", _re_mod.I)
    fact_check_note = ""
    content, action_items, failure = "", [], None
    for attempt in range(1, BRIEF_ATTEMPTS + 1):
        try:
            raw = await ollama_chat_stream(
                MODEL, prompt, json_mode=True, num_ctx=BRIEF_NUM_CTX, num_predict=1800
            )
            generated = parse_json_response(raw)
            commentary = generated.get("commentary", "")
            if isinstance(commentary, list):
                commentary = "\n".join(f"- {c}" for c in commentary)
            commentary = str(commentary).strip()
            action_items = [str(a) for a in (generated.get("action_items") or [])][:3]
            if len(commentary) < 120:
                raise ValueError(f"model returned too little commentary ({len(commentary)} chars)")
            fact_check_note = ""
            if _limits_breached and _contra.search(commentary):
                if attempt < BRIEF_ATTEMPTS:
                    raise ValueError("commentary contradicts verified facts (claims limits not exceeded)")
                fact_check_note = ("\n\n⚠️ Fact check: the commentary above wrongly suggests risk limits are not exceeded. "
                                   "They ARE exceeded - see the Risk section. Trust the verified facts.")
            content = (
                f"# Morning brief — {date.today().isoformat()}\n\n{facts_md}\n\n"
                f"**Advisor commentary (AI, local model; opinion)**\n{commentary}{fact_check_note}\n\n"
                "_Advisory only. Not licensed financial advice. No trades are executed._"
            )
            failure = None
            break
        except Exception as exc:  # noqa: BLE001
            failure = f"{type(exc).__name__}: {exc}"[:300]
            logger.exception("Daily brief generation attempt %d/%d failed", attempt, BRIEF_ATTEMPTS)
            content, action_items = "", []
            if attempt < BRIEF_ATTEMPTS:
                import asyncio as _asyncio
                await _asyncio.sleep(30)
    if failure:
        from datetime import datetime as _dt
        content = (
            f"{BRIEF_FAILED_PREFIX} {_dt.now().strftime('%Y-%m-%d %H:%M')} ICT — local AI "
            f"generation failed after {BRIEF_ATTEMPTS} attempts ({failure}). No brief content "
            "was generated and nothing has been filled in. An automatic retry is scheduled."
            f"\n\nVerified facts at time of failure (no AI involved):\n{facts_md}"
        )
        action_items = []
    logger.info(
        "Daily brief %s (prompt %d chars, content %d chars)",
        "FAILED" if failure else "generated", len(prompt), len(content),
    )
    risk_score = float(performance[0]["risk_score"] or 0) if performance else 0.0
    macro_mood = str(macro["market_mood"]) if macro else "unknown"
    await pool.execute(
        """
        INSERT INTO daily_briefs (
          brief_date, content, macro_mood, portfolio_risk_score, top_opportunities, action_items
        ) VALUES (CURRENT_DATE, $1, $2, $3, $4::jsonb, $5::jsonb)
        ON CONFLICT (brief_date) DO UPDATE SET
          content = EXCLUDED.content, macro_mood = EXCLUDED.macro_mood,
          portfolio_risk_score = EXCLUDED.portfolio_risk_score,
          top_opportunities = EXCLUDED.top_opportunities,
          action_items = EXCLUDED.action_items, generated_at = NOW()
        """,
        content,
        macro_mood,
        risk_score,
        json_dumps(opportunities),
        json_dumps(action_items),
    )
    return {
        "brief_date": date.today().isoformat(),
        "status": "failed" if failure else "ok",
        "content": content,
        "action_items": action_items,
    }


async def retry_daily_brief_if_needed() -> dict[str, Any]:
    """Regenerate today's brief only if it is missing, empty or marked failed."""
    pool = await db_pool.get_pool()
    row = await pool.fetchrow("SELECT content FROM daily_briefs WHERE brief_date = CURRENT_DATE")
    if row and not is_failed_brief(row["content"]):
        return {"status": "ok", "skipped": True}
    logger.info("Retrying daily brief (row %s)", "missing" if not row else "failed/empty")
    return await generate_daily_brief()
