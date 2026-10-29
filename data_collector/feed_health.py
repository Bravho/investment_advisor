"""
Feed health / data-staleness monitor.
=====================================

Added by nightly agent 2026-08-08.

WHY THIS MODULE EXISTS
----------------------
On 2026-08-08 the nightly agent established that the live market-data collector
process has not written anything since **2026-07-15 23:53 ICT** — 23 days. The
evidence, all mutually corroborating:

  * ``data_collector/portfolio_snapshot.json`` carries
    ``generated_at = 2026-07-15T11:30:14Z`` and has not moved since.
  * ``data_collector/logs/market_data_process.log`` last written 2026-07-15 23:53,
    ending in ``Shutdown requested by signal 15`` (SIGTERM) — a clean stop, never
    restarted.
  * ``data_collector/logs/market_data.log.<date>`` rotation stops at 2026-07-14.
  * ``data_collector/heartbeat.json`` is stamped 2026-06-06 — older still.

The three preceding nightly runs (Aug-05, Aug-06, Aug-07) each reported "no
confirmed SET close" and each diagnosed it as a *retrieval* defect — a scraper or
vendor problem. That diagnosis was wrong. There is no retrieval defect to fix:
**the collector is not running at all.** A dead daemon and a broken parser look
identical from downstream, because in both cases the last-known price simply
stops advancing, and nothing in this codebase distinguished the two.

That is the actual defect this module addresses. The failure was not that a feed
broke — feeds break constantly and that is survivable. The failure was that it
broke **silently**, and every downstream consumer kept treating a 23-day-old mark
as if it were today's, because a price with no attached age is indistinguishable
from a fresh one. Portfolio weights, concentration flags and P&L deltas were all
computed off that stale mark and reported without qualification.

DESIGN PRINCIPLE
----------------
Absence of data must be loud, and must be **distinguishable from data showing no
change**. A zero delta because the market did not move and a zero delta because
nobody asked the market are completely different facts and must never render the
same way. Every check below therefore returns an explicit age in days plus a
severity, and the aggregate refuses to report ``OK`` when it cannot prove
freshness.

This module is deliberately:
  * **stdlib-only** — no pandas, no psycopg2, no yfinance. A health check that
    depends on the stack it is checking is worthless: if the venv or the DB is
    the thing that is broken, the checker must still run and still tell you.
  * **read-only** — it inspects mtimes and parses JSON. It never repairs,
    restarts or writes to any monitored file. Its one write is its own report.
  * **non-throwing** — every individual check is wrapped; a check that itself
    fails degrades to severity STALE_UNKNOWN with the exception recorded, and
    never takes down the caller. An exception inside a health check must not
    look like health.

USAGE
-----
    from feed_health import check_feed_health, format_health_banner

    report = check_feed_health()
    if report["worst_severity"] in ("STALE", "DEAD"):
        print(format_health_banner(report))

Or standalone, which is the intended operator entry point::

    python3 data_collector/feed_health.py

Exit code is 0 when everything is FRESH/AGING, 1 when anything is STALE, and
2 when anything is DEAD — so it can be dropped straight into cron or a
launchd ``KeepAlive`` wrapper without any glue.
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
UTC = timezone.utc

# Report destination. Written next to the other nightly data artefacts so the
# brief generator and the dashboard can both pick it up without importing this
# module (and therefore without depending on data_collector being importable).
HEALTH_REPORT_PATH = PROJECT_DIR / "data" / "feed_health.json"

# ---------------------------------------------------------------------------
# Severity ladder.
# ---------------------------------------------------------------------------
# Thresholds are expressed in CALENDAR days, not trading days, and that is a
# deliberate simplification with a known cost: a Friday-evening snapshot read on
# Monday morning is 3 calendar days old but 0 trading days old, and will show as
# AGING. That false-positive direction is the correct one to accept. The failure
# mode this module exists to prevent is a stale feed reading as healthy; an
# occasional weekend nag is a trivial price for never repeating the 23-day
# silence. Do NOT "fix" this by widening the thresholds — if trading-day
# precision is wanted, add a SET/NYSE holiday calendar and count properly.
SEVERITY_ORDER = ("FRESH", "AGING", "STALE", "DEAD", "STALE_UNKNOWN")

FRESH_MAX_DAYS = 2      # within tolerance including a normal weekend
AGING_MAX_DAYS = 4      # a long weekend / public holiday; watch but do not alarm
STALE_MAX_DAYS = 10     # beyond any plausible market closure — something is wrong
# > STALE_MAX_DAYS  ->  DEAD


def _severity_for_age(age_days: Optional[float]) -> str:
    """Map an age in days onto the severity ladder."""
    if age_days is None:
        return "STALE_UNKNOWN"
    if age_days <= FRESH_MAX_DAYS:
        return "FRESH"
    if age_days <= AGING_MAX_DAYS:
        return "AGING"
    if age_days <= STALE_MAX_DAYS:
        return "STALE"
    return "DEAD"


def _worst(severities: list[str]) -> str:
    """Return the most severe entry. STALE_UNKNOWN outranks everything.

    An unknown age is treated as worse than a known-dead feed on purpose: a feed
    we know is dead is a scheduling problem, but a feed whose age we cannot even
    determine means the monitoring itself is compromised, which is the condition
    that produced the original 23-day blind spot.
    """
    if not severities:
        return "STALE_UNKNOWN"
    return max(severities, key=lambda s: SEVERITY_ORDER.index(s))


def _age_days(moment: Optional[datetime], now: Optional[datetime] = None) -> Optional[float]:
    """Age of `moment` in fractional days. Naive datetimes are assumed UTC."""
    if moment is None:
        return None
    now = now or datetime.now(UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return (now - moment).total_seconds() / 86400.0


def _parse_iso(value: Any) -> Optional[datetime]:
    """Best-effort ISO-8601 parse that tolerates a trailing 'Z' and bare dates."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass
    try:
        return datetime.combine(date.fromisoformat(text[:10]), datetime.min.time(), tzinfo=UTC)
    except (ValueError, TypeError):
        return None


def _check(name: str, description: str) -> dict[str, Any]:
    """Skeleton result so every check returns the same shape."""
    return {
        "name": name,
        "description": description,
        "as_of": None,
        "age_days": None,
        "severity": "STALE_UNKNOWN",
        "detail": "",
        "error": None,
    }


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def check_portfolio_snapshot() -> dict[str, Any]:
    """Age of the live valuation snapshot written by market_data.py.

    This is the single most important check in the module: it is the file whose
    staleness directly corrupts portfolio weights and P&L. Its own
    ``generated_at`` field is trusted over the file mtime, because a file can be
    touched by a backup or a sync without its contents being refreshed — mtime
    measures the filesystem, ``generated_at`` measures the data.
    """
    result = _check(
        "portfolio_snapshot",
        "data_collector/portfolio_snapshot.json — live holdings valuation",
    )
    path = BASE_DIR / "portfolio_snapshot.json"
    try:
        if not path.exists():
            result["detail"] = f"{path} does not exist — collector has never written a snapshot"
            result["severity"] = "DEAD"
            return result
        payload = json.loads(path.read_text(encoding="utf-8"))
        generated = _parse_iso(payload.get("generated_at"))
        age = _age_days(generated)
        result["as_of"] = payload.get("generated_at")
        result["age_days"] = round(age, 2) if age is not None else None
        result["severity"] = _severity_for_age(age)

        # Surface per-holding errors too. A snapshot can be FRESH in age while
        # still carrying a holding that failed to price — that is a partial
        # outage and must not be masked by an overall-green timestamp.
        holdings = payload.get("holdings") or {}
        errored = sorted(k for k, v in holdings.items() if isinstance(v, dict) and v.get("error"))
        priced = [k for k in holdings if k not in errored]
        bits = [f"{len(priced)} holding(s) priced"]
        if errored:
            bits.append(f"{len(errored)} FAILED: {', '.join(errored)}")
            if result["severity"] in ("FRESH", "AGING"):
                result["severity"] = "STALE"
        result["detail"] = "; ".join(bits)
        return result
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["detail"] = "snapshot unreadable — treat all portfolio marks as unverified"
        return result


def check_collector_process_log() -> dict[str, Any]:
    """Age of the collector's own process log — proves the daemon is alive.

    This is the check that would have caught the July outage on 2026-07-16
    instead of 2026-08-08. It also reads the log tail for a clean-shutdown
    signature, because "stopped deliberately and never restarted" needs a
    different remedy (fix the supervisor) than "crashed mid-run" (fix the code).
    """
    result = _check(
        "collector_process",
        "data_collector/logs/market_data_process.log — collector daemon liveness",
    )
    try:
        logs_dir = BASE_DIR / "logs"
        candidates = [
            logs_dir / "market_data_process.log",
            logs_dir / "market_data.log",
        ]
        existing = [p for p in candidates if p.exists()]
        if not existing:
            result["detail"] = "no collector log found at all — daemon has never run from this checkout"
            result["severity"] = "DEAD"
            return result

        newest = max(existing, key=lambda p: p.stat().st_mtime)
        moment = datetime.fromtimestamp(newest.stat().st_mtime, tz=UTC)
        age = _age_days(moment)
        result["as_of"] = moment.isoformat()
        result["age_days"] = round(age, 2) if age is not None else None
        result["severity"] = _severity_for_age(age)

        tail = ""
        try:
            with newest.open("rb") as handle:
                handle.seek(0, 2)
                handle.seek(max(0, handle.tell() - 4096))
                tail = handle.read().decode("utf-8", errors="replace")
        except Exception:
            tail = ""

        # 2026-10-30: judge by the LAST event in the tail, not mere presence - a
        # restart after a clean shutdown (or a handled traceback) is healthy.
        def _last(*needles: str) -> int:
            return max((tail.rfind(n) for n in needles), default=-1)

        _stop = _last("Market collector stopped", "Shutdown requested by signal")
        _start = _last("Market collector started", "Collecting current prices", "Portfolio snapshot saved",
                       "NAV SCBGOLDE", "Collecting end-of-day")
        _tb = _last("Traceback")
        if _start > max(_stop, _tb):
            result["detail"] = f"{newest.name}: running — last event at {moment.astimezone().strftime('%Y-%m-%d %H:%M')} local"
        elif _stop > _tb:
            result["detail"] = (
                f"{newest.name}: last entry is a CLEAN SHUTDOWN — the daemon was stopped "
                "deliberately and never restarted. Remedy is the supervisor/launchd job, "
                "NOT the fetch code."
            )
        elif _tb >= 0:
            result["detail"] = f"{newest.name}: last entry contains a traceback — daemon likely crashed"
        else:
            result["detail"] = f"{newest.name}: last written {moment.date().isoformat()}"
        return result
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result


def check_heartbeat() -> dict[str, Any]:
    """Age of the orchestrator heartbeat covering all three worker processes."""
    result = _check(
        "orchestrator_heartbeat",
        "data_collector/heartbeat.json — news/market/ai worker heartbeat",
    )
    path = BASE_DIR / "heartbeat.json"
    try:
        if not path.exists():
            result["detail"] = "heartbeat.json absent — orchestrator not running"
            result["severity"] = "DEAD"
            return result
        payload = json.loads(path.read_text(encoding="utf-8"))
        moment = _parse_iso(payload.get("timestamp"))
        age = _age_days(moment)
        result["as_of"] = payload.get("timestamp")
        result["age_days"] = round(age, 2) if age is not None else None
        result["severity"] = _severity_for_age(age)
        workers = payload.get("workers") or {}
        running = [n for n, w in workers.items() if isinstance(w, dict) and w.get("status") == "running"]
        result["detail"] = (
            f"{len(running)}/{len(workers)} workers last reported running "
            f"({', '.join(running) if running else 'none'}); "
            "NOTE a stale heartbeat means these statuses are historical, not current"
        )
        return result
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result


def check_nightly_artifacts() -> dict[str, Any]:
    """Age of the nightly agent's own outputs (snapshots / watchlist / intel).

    Deliberately separated from the live-feed checks. The nightly agent and the
    live collector are independent subsystems and it is entirely possible — in
    fact it is exactly what happened through late July — for the nightly agent to
    be running perfectly while the live collector is dead. Merging these two into
    one number would let a healthy agent mask a dead feed, which is the precise
    error this module exists to make impossible.
    """
    result = _check(
        "nightly_artifacts",
        "dated snapshots + DB watch lists/factors (legacy watchlist.json narrative = info only)",
    )
    try:
        ages: list[float] = []
        bits: list[str] = []

        snap_dir = PROJECT_DIR / "data" / "snapshots"
        if snap_dir.is_dir():
            snaps = sorted(p for p in snap_dir.glob("20[0-9][0-9]-[0-9][0-9]-[0-9][0-9].json"))  # dated only (fund_nav_history.json sorted last)
            if snaps:
                latest = snaps[-1]
                moment = _parse_iso(latest.stem)
                age = _age_days(moment)
                if age is not None:
                    ages.append(age)
                bits.append(f"latest snapshot {latest.stem}")

        # 2026-10-30 (Phase 3): the live watch lists now live in investor_db and are
        # refreshed by the portfolio engine; their freshness is what counts. The
        # legacy data/watchlist.json narrative (paused nightly agent) is reported
        # for information only and no longer drives this check's severity.
        status_file = PROJECT_DIR / "data" / "watchlists_status.json"
        if status_file.exists():
            status = json.loads(status_file.read_text(encoding="utf-8"))
            for key, label in (("investment_watchlist_refreshed_at", "watch-list prices"),
                               ("market_factors_refreshed_at", "market factors")):
                moment = _parse_iso(status.get(key))
                age = _age_days(moment)
                if age is not None:
                    ages.append(age)
                    bits.append(f"{label} {age * 24:.1f}h ago")
                else:
                    bits.append(f"{label} never refreshed")
                    ages.append(999.0)
        else:
            bits.append("DB watch lists never refreshed (no data/watchlists_status.json)")
            ages.append(999.0)

        watchlist = PROJECT_DIR / "data" / "watchlist.json"
        if watchlist.exists():
            payload = json.loads(watchlist.read_text(encoding="utf-8"))
            stamp = (payload.get("_meta") or {}).get("last_updated") or payload.get("last_updated")
            live = (payload.get("_meta") or {}).get("live_levels_updated_at")
            n_age = _age_days(_parse_iso(stamp))
            bits.append(f"legacy narrative {stamp} (~{n_age:.0f}d, info only)" if n_age is not None else f"legacy narrative {stamp}")
            if live:
                bits.append(f"legacy levels synced {live[:16]}Z")
            result["legacy_narrative_age_days"] = round(n_age, 1) if n_age is not None else None

        if not ages:
            result["detail"] = "no nightly artefacts found"
            return result

        worst_age = max(ages)
        result["age_days"] = round(worst_age, 2)
        result["severity"] = _severity_for_age(worst_age)
        result["detail"] = "; ".join(bits)
        return result
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------

CHECKS = (
    check_portfolio_snapshot,
    check_collector_process_log,
    check_heartbeat,
    check_nightly_artifacts,
)


def check_feed_health(write_report: bool = True) -> dict[str, Any]:
    """Run every check and return an aggregate report.

    Never raises. A check that blows up is recorded as STALE_UNKNOWN with its
    exception text, because a monitor that can be silenced by an exception is
    not a monitor.
    """
    checks: list[dict[str, Any]] = []
    for check in CHECKS:
        try:
            checks.append(check())
        except Exception as exc:  # defensive; individual checks already guard
            broken = _check(getattr(check, "__name__", "unknown"), "check raised")
            broken["error"] = f"{type(exc).__name__}: {exc}"
            checks.append(broken)

    worst = _worst([c["severity"] for c in checks])
    report: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "worst_severity": worst,
        "healthy": worst in ("FRESH", "AGING"),
        "thresholds_days": {
            "fresh_max": FRESH_MAX_DAYS,
            "aging_max": AGING_MAX_DAYS,
            "stale_max": STALE_MAX_DAYS,
            "note": "calendar days, not trading days — see module docstring",
        },
        "checks": checks,
        "interpretation": _interpret(checks, worst),
    }
    if write_report:
        try:
            HEALTH_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
            temporary = HEALTH_REPORT_PATH.with_suffix(".json.tmp")
            temporary.write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            temporary.replace(HEALTH_REPORT_PATH)
        except Exception:
            # Failing to persist the report must not fail the check itself.
            pass
    return report


def _interpret(checks: list[dict[str, Any]], worst: str) -> str:
    """Plain-language verdict — what the caller should actually DO."""
    by_name = {c["name"]: c for c in checks}
    live_dead = by_name.get("collector_process", {}).get("severity") in ("STALE", "DEAD")
    snapshot_dead = by_name.get("portfolio_snapshot", {}).get("severity") in ("STALE", "DEAD")
    nightly_ok = by_name.get("nightly_artifacts", {}).get("severity") in ("FRESH", "AGING")

    if live_dead and snapshot_dead and nightly_ok:
        return (
            "LIVE COLLECTOR IS DOWN while the nightly agent is still running. Portfolio "
            "marks are frozen at the last collector run: any 'no change' in price, weight "
            "or P&L is ABSENCE OF DATA, not absence of movement, and must not be read as a "
            "flat market. Restart the market_data collector; do not spend time debugging "
            "the fetch path until the process is confirmed alive."
        )
    if worst in ("STALE", "DEAD", "STALE_UNKNOWN"):
        return (
            "One or more data feeds are stale or of unknown age. Treat every downstream "
            "price, weight and delta as UNVERIFIED until the flagged checks are green."
        )
    return "All monitored feeds are within freshness tolerance."


def format_health_banner(report: Optional[dict[str, Any]] = None) -> str:
    """One-block human-readable banner for the morning brief or the console."""
    report = report or check_feed_health(write_report=False)
    icon = {"FRESH": "✅", "AGING": "🟡", "STALE": "⚠️", "DEAD": "🚨", "STALE_UNKNOWN": "❓"}
    lines = [
        f"{icon.get(report['worst_severity'], '❓')} DATA FEED HEALTH — {report['worst_severity']}",
        f"   {report['interpretation']}",
    ]
    for check in report["checks"]:
        age = check["age_days"]
        age_text = f"{age:.1f}d old" if isinstance(age, (int, float)) else "age UNKNOWN"
        lines.append(
            f"   {icon.get(check['severity'], '❓')} {check['name']}: {age_text} — {check['detail'] or check['error'] or ''}"
        )
    return "\n".join(lines)


def stale_price_warning(as_of: Any, label: str = "price") -> Optional[str]:
    """Return a warning string if `as_of` is too old to be quoted as current.

    Intended for use at the point a mark is *rendered*, so that a stale number
    can never be printed without its age attached. Returns None when fresh,
    which makes the call site read naturally::

        warning = stale_price_warning(row["last_price_date"], "BAFS.BK close")
        if warning:
            print(warning)
    """
    moment = _parse_iso(as_of)
    age = _age_days(moment)
    severity = _severity_for_age(age)
    if severity in ("FRESH", "AGING"):
        return None
    if age is None:
        return f"❓ {label}: as-of date is missing or unparseable — freshness cannot be established"
    return (
        f"⚠️ {label}: mark is {age:.0f} days old (as of {moment.date().isoformat()}). "
        "Any zero change against it is absence of data, not absence of movement."
    )


def main() -> int:
    report = check_feed_health()
    print(format_health_banner(report))
    print(f"\nReport written to {HEALTH_REPORT_PATH}")
    if report["worst_severity"] in ("DEAD", "STALE_UNKNOWN"):
        return 2
    if report["worst_severity"] == "STALE":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
