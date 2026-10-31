from __future__ import annotations
import asyncio
import time
from typing import Any

import numpy as np

from utils.common import configure_logging, latest_price, load_snapshot
from utils.db_pool import db_pool

logger = configure_logging("portfolio_engine.performance")

# --- Cost-basis integrity guard — Added by nightly agent 2026-08-09 ------------
# `holdings.avg_cost_price` is 0 for every row, which made the old inline
# `quantity * (price - cost)` collapse to `quantity * price` — the whole position
# reported as profit. Import is defensive so this module still loads if the guard
# is ever moved; the fallback degrades to "unreliable", never to a fabricated number.
try:  # pragma: no cover - import shim
    from cost_basis_guard import audit_holdings as _audit_holdings, safe_pnl as _safe_pnl
except ImportError:  # pragma: no cover
    try:
        from portfolio_engine.cost_basis_guard import (  # type: ignore
            audit_holdings as _audit_holdings,
            safe_pnl as _safe_pnl,
        )
    except ImportError:
        _audit_holdings = None  # type: ignore[assignment]
        _safe_pnl = None  # type: ignore[assignment]
# ------------------------------------------------------------------------------

_cache: dict[int, tuple[float, dict[str, Any]]] = {}
_cache_lock = asyncio.Lock()
CACHE_TTL = 300


def _metrics(values: list[float], returns: list[float]) -> dict[str, float]:
    total_return = ((values[-1] - values[0]) / values[0] * 100) if len(values) > 1 and values[0] else 0.0
    array = np.array(returns, dtype=float)
    std = float(np.std(array, ddof=1)) if len(array) > 1 else 0.0
    sharpe = float(np.mean(array) / std * np.sqrt(252)) if std else 0.0
    peaks = np.maximum.accumulate(np.array(values, dtype=float)) if values else np.array([])
    drawdowns = (np.array(values, dtype=float) - peaks) / peaks * 100 if len(peaks) and np.all(peaks != 0) else np.array([0])
    return {
        "return": round(total_return, 4),
        "sharpe_ratio": round(sharpe, 4),
        "max_drawdown": round(float(np.min(drawdowns)), 4),
        "win_rate": round(float(np.mean(array > 0)), 4) if len(array) else 0.0,
        "best_day": round(float(np.max(array)), 4) if len(array) else 0.0,
        "worst_day": round(float(np.min(array)), 4) if len(array) else 0.0,
    }


async def _benchmark(pool: Any, ticker: str, days: int) -> dict[str, float]:
    rows = await pool.fetch(
        "SELECT close_price FROM market_prices WHERE ticker = $1 ORDER BY price_date DESC LIMIT $2",
        ticker,
        days + 1,
    )
    values = list(reversed([float(row["close_price"]) for row in rows]))
    returns = [(values[index] / values[index - 1] - 1) * 100 for index in range(1, len(values)) if values[index - 1]]
    return _metrics(values, returns)


async def get_performance_summary(days: int = 30, force_refresh: bool = False) -> dict[str, Any]:
    days = max(1, min(days, 3650))
    cached = _cache.get(days)
    if cached and not force_refresh and time.monotonic() - cached[0] < CACHE_TTL:
        return cached[1]
    async with _cache_lock:
        pool = await db_pool.get_pool()
        records = await pool.fetch(
            """
            SELECT record_date, total_value_thb, daily_pnl_pct
            FROM portfolio_performance
            WHERE record_date >= CURRENT_DATE - $1::int
            ORDER BY record_date
            """,
            days,
        )
        # 2026-10-31: the recorded totals mix purchases (e.g. +300k ThaiESG on 30 Oct) and unpriced days with
        # performance, daily_pnl_pct is always 0 and ^SET.BK/^GSPC are not in market_prices - so the old
        # first-vs-last-total "return" (63.8%), Sharpe 0 and flat benchmarks were wrong. Use the time-weighted,
        # flow-neutral series (perf_series) instead; legacy recorded totals stay available as recorded_totals.
        import perf_series
        twr = await perf_series.build(pool, days)
        tp = twr.get("portfolio") or {}
        portfolio = {"return": tp.get("return_pct"), "sharpe_ratio": tp.get("sharpe"), "max_drawdown": tp.get("max_drawdown_pct"),
                     "win_rate": tp.get("win_rate"), "best_day": tp.get("best_day_pct"), "worst_day": tp.get("worst_day_pct")}

        def _bm(key: str) -> dict[str, Any]:
            b = (twr.get("benchmarks") or {}).get(key)
            if not b:
                return {"return": None, "error": (twr.get("benchmark_errors") or {}).get(key, "unavailable")}
            return {"ticker": b.get("ticker"), "label": (twr.get("benchmark_labels") or {}).get(key), "return": b.get("return_pct"),
                    "sharpe_ratio": b.get("sharpe"), "max_drawdown": b.get("max_drawdown_pct"), "win_rate": b.get("win_rate"),
                    "best_day": b.get("best_day_pct"), "worst_day": b.get("worst_day_pct")}
        set_metrics, sp_metrics = _bm("SET"), _bm("SP500")
        holdings = await pool.fetch("SELECT ticker, quantity, avg_cost_price FROM holdings ORDER BY ticker")
        snapshot = load_snapshot()
        total_value = float(snapshot.get("total_market_value_thb") or 0)
        breakdown = []
        audit_rows = []  # Added by nightly agent 2026-08-09
        for holding in holdings:
            price = await latest_price(pool, holding["ticker"])
            quantity = float(holding["quantity"] or 0)
            cost = float(holding["avg_cost_price"] or 0)
            snapshot_position = snapshot.get("holdings", {}).get(holding["ticker"], {})
            value = float(snapshot_position.get("market_value_thb") or quantity * price)
            pnl = float(snapshot_position.get("pnl_thb") or quantity * (price - cost))

            # --- Added by nightly agent 2026-08-09 --------------------------
            # Route P&L through the guard. When the cost basis is unusable the
            # guard returns None, and None is what gets published: an
            # uncomputable P&L is NOT zero and NOT equal to market value. The
            # figure the old path would have claimed is retained as
            # `phantom_pnl_thb` so the size of the misstatement stays visible.
            # `current_weight` and market value are unaffected — they do not
            # depend on cost basis and remain trustworthy.
            guard = (
                _safe_pnl(quantity, price, holding["avg_cost_price"])
                if _safe_pnl is not None
                else {"reliable": False, "pnl_thb": None, "cost_basis_status": "GUARD_UNAVAILABLE",
                      "phantom_pnl_thb": round(pnl, 2), "note": "cost_basis_guard could not be imported"}
            )
            reliable = bool(guard["reliable"])
            published_pnl = guard["pnl_thb"] if reliable else None
            audit_rows.append(
                {
                    "ticker": holding["ticker"],
                    "quantity": quantity,
                    "current_price": price,
                    "avg_cost_price": holding["avg_cost_price"],
                }
            )
            if not reliable:
                logger.warning(
                    "P&L suppressed for %s: cost basis %s. Legacy path would have "
                    "reported THB %s as profit.",
                    holding["ticker"],
                    guard.get("cost_basis_status"),
                    guard.get("phantom_pnl_thb"),
                )
            # ----------------------------------------------------------------

            breakdown.append(
                {
                    "ticker": holding["ticker"],
                    "current_weight": round(value / total_value, 4) if total_value else 0.0,
                    "market_value_thb": round(value, 2),
                    "pnl_thb": published_pnl,
                    "pnl_reliable": reliable,
                    "cost_basis_status": guard.get("cost_basis_status"),
                    "phantom_pnl_thb": guard.get("phantom_pnl_thb"),
                    "pnl_caveat": guard.get("note"),
                    "contribution_to_return": (
                        round(published_pnl / total_value * 100, 4)
                        if (reliable and total_value and published_pnl is not None)
                        else None
                    ),
                }
            )
        result = {
            "period_days": days,
            "total_return_pct": portfolio["return"],
            "sharpe_ratio": portfolio["sharpe_ratio"],
            "max_drawdown": portfolio["max_drawdown"],
            "win_rate": portfolio["win_rate"],
            "benchmark_comparison": {
                "SET": {**set_metrics, "alpha": round(portfolio["return"] - set_metrics["return"], 2) if None not in (portfolio["return"], set_metrics.get("return")) else None},
                "SP500": {**sp_metrics, "alpha": round(portfolio["return"] - sp_metrics["return"], 2) if None not in (portfolio["return"], sp_metrics.get("return")) else None},
            },
            "method": twr.get("method"), "window": twr.get("window"), "series": twr.get("series", []),
            "sharpe_note": tp.get("sharpe_note"), "mdd_note": tp.get("mdd_note"), "n_returns": tp.get("n_returns"),
            "vol_pct": tp.get("vol_pct"), "risk_free": twr.get("risk_free"), "notes": twr.get("notes", []),
            "provisional_note_th": twr.get("provisional_note_th"), "pending_contributions": twr.get("pending_contributions"),
            "error": twr.get("error"),
            "recorded_totals": [{"date": str(r["record_date"]), "total_value_thb": float(r["total_value_thb"] or 0)} for r in records],
            "recorded_totals_note": "raw recorded totals include purchases and unpriced days - NOT a return series",
            "holdings_breakdown": breakdown,
            "best_day": portfolio["best_day"],
            "worst_day": portfolio["worst_day"],
        }
        # --- Added by nightly agent 2026-08-09 ------------------------------
        # Attach a portfolio-level cost-basis audit so any consumer (brief,
        # dashboard, API) can see at a glance whether P&L means anything before
        # rendering it. `pnl_reliable` is deliberately top-level and boolean.
        if _audit_holdings is not None:
            audit = _audit_holdings(audit_rows)
            result["cost_basis_audit"] = audit
            result["pnl_reliable"] = audit["portfolio_pnl_reliable"]
            if not audit["portfolio_pnl_reliable"]:
                result["pnl_caveat"] = (
                    f"{audit['holdings_without_usable_cost_basis']} of "
                    f"{audit['holdings_checked']} holdings have no usable cost basis "
                    f"({audit['share_of_book_without_cost_basis_pct']}% of book by value). "
                    f"Per-holding and total P&L are SUPPRESSED, not zero. Populate "
                    f"holdings.avg_cost_price to restore them."
                )
        else:
            result["pnl_reliable"] = False
            result["pnl_caveat"] = "cost_basis_guard unavailable; treat all P&L as unverified."
        # --------------------------------------------------------------------
        _cache[days] = (time.monotonic(), result)
        return result


# ---------------------------------------------------------------------------
# Daily portfolio snapshot saver — Added by nightly agent 2026-06-10
# ---------------------------------------------------------------------------

import json as _json
from datetime import date as _date
from pathlib import Path as _Path


def save_daily_snapshot(snapshot_data: dict[str, Any], output_dir: _Path | None = None) -> _Path:
    """
    Persist a daily JSON snapshot of portfolio values to
    data/snapshots/YYYY-MM-DD.json.

    Designed to be called nightly after calculate_portfolio_risk() or after
    the data_collector's portfolio_snapshot.json is updated. Pass the full
    snapshot dict (or a subset) and this function will stamp it with today's
    date and write it to the archive.

    Args:
        snapshot_data: Portfolio state dict — at minimum include
            total_market_value_thb, holdings (per-ticker breakdown), and
            any risk/performance metrics available at call time.
        output_dir: Override output directory (default: data/snapshots/).

    Returns:
        Path to the written file.

    Added by nightly agent 2026-06-10
    """
    from utils.common import PROJECT_DIR as _PROJECT_DIR  # local import to avoid circular
    base = output_dir or (_PROJECT_DIR / "data" / "snapshots")
    base.mkdir(parents=True, exist_ok=True)

    today_str = _date.today().isoformat()
    out_path = base / f"{today_str}.json"

    payload: dict[str, Any] = {
        "snapshot_date": today_str,
        **snapshot_data,
    }
    out_path.write_text(
        _json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    logger.info("Daily portfolio snapshot saved to %s", out_path)
    return out_path


def load_snapshot_history(days: int = 30, snapshots_dir: _Path | None = None) -> list[dict[str, Any]]:
    """
    Load the last `days` daily snapshot files from data/snapshots/.

    Useful for trend analysis, drawdown charts, and performance comparisons
    in the morning brief.

    Returns a list of snapshot dicts sorted oldest-first.

    Added by nightly agent 2026-06-10
    """
    from utils.common import PROJECT_DIR as _PROJECT_DIR
    base = snapshots_dir or (_PROJECT_DIR / "data" / "snapshots")
    if not base.exists():
        return []
    files = sorted(base.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].json"), reverse=True)
    results: list[dict[str, Any]] = []
    for f in files[:days]:
        try:
            results.append(_json.loads(f.read_text(encoding="utf-8")))
        except (_json.JSONDecodeError, OSError):
            # Fixed by nightly agent 2026-06-15: was `json.JSONDecodeError`
            # (NameError — module imported as `_json`), which would mask a
            # corrupt snapshot file with an unhandled exception.
            logger.warning("Could not read snapshot %s", f)
    return list(reversed(results))  # oldest first
