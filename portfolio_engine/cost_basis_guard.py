"""
Cost-basis integrity guard.
===========================

Added by nightly agent 2026-08-09.

WHY THIS MODULE EXISTS
----------------------
Every row in the `holdings` table carries `avg_cost_price = 0`. The P&L path in
`performance_analytics.get_performance_summary()` does this:

    cost = float(holding["avg_cost_price"] or 0)
    pnl  = quantity * (price - cost)

With `cost == 0` that reduces to `pnl = quantity * price`, i.e. **the entire market
value of the position is reported as profit**. The fingerprint is visible in
`data_collector/portfolio_snapshot.json` right now:

    "BAFS.BK":  {"market_value_thb": 189279.99, "pnl_thb": 189279.99, "pnl_pct": 0.0}
    "PTTEP.BK": {"market_value_thb": 201600.00, "pnl_thb": 201600.00, "pnl_pct": 0.0}
    "SCB.BK":   {"market_value_thb": 217700.00, "pnl_thb": 217700.00, "pnl_pct": 0.0}
    total_market_value_thb == total_pnl_thb == 608579.99

The system is asserting an infinite return on the whole book. It has never once
flagged this, because a missing cost basis is silently coerced to a *valid-looking*
number (zero) instead of being treated as absent. `pnl_pct` is simultaneously 0.0,
which is mutually inconsistent with a non-zero `pnl_thb` — two contradictory claims
in the same record, and neither raised an error.

This is a worse class of defect than the dead price feed. A stale price is wrong in
one direction and eventually looks suspicious. A fabricated cost basis is wrong in a
direction that *flatters the owner*, and flattering errors do not get investigated.

DESIGN PRINCIPLE
----------------
Absent data must propagate as absent — `None`, never `0`. A P&L figure that cannot
be computed is not "zero profit" and it is not "profit equal to market value"; it is
**no answer**, and the correct behaviour is to say so and keep the market value,
which is still perfectly good information.

This module is stdlib-only and has no project imports, so it can be executed
standalone (like `data_collector/feed_health.py`) without the venv or Postgres.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

__all__ = [
    "CostBasisStatus",
    "classify_cost_basis",
    "safe_pnl",
    "audit_holdings",
    "scan_snapshot",
    "format_report",
]

# Sentinel values that a database or CSV may use to mean "unknown" but which
# arithmetic will happily treat as a real price.
_NULLISH = (None, "", "None", "null", "NaN", "nan")

# A cost basis below this is treated as absent rather than real. No SET-listed
# instrument Tho holds trades meaningfully below THB 0.01, and a true zero cost
# basis (a pure gift or a fully-written-down position) is rare enough that it
# should be asserted explicitly rather than inferred from a blank field.
MIN_PLAUSIBLE_COST = 0.01


class CostBasisStatus:
    """Verdicts a single holding's cost basis can receive."""

    OK = "OK"
    MISSING = "MISSING"          # null / blank / absent field
    ZERO = "ZERO"                # present but 0 — the defect this module exists for
    NEGATIVE = "NEGATIVE"        # nonsensical
    IMPLAUSIBLE = "IMPLAUSIBLE"  # positive but below MIN_PLAUSIBLE_COST

    UNUSABLE = {MISSING, ZERO, NEGATIVE, IMPLAUSIBLE}


def _as_float(value: Any) -> float | None:
    """Coerce to float, mapping every flavour of 'unknown' to None (never 0.0)."""
    if value in _NULLISH:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if result != result:  # NaN
        return None
    return result


def classify_cost_basis(avg_cost_price: Any) -> tuple[str, float | None]:
    """
    Classify a single `avg_cost_price` value.

    Returns ``(status, value_or_None)``. The caller must check the status before
    doing arithmetic — that check is the entire point of this module.

    >>> classify_cost_basis(0)
    ('ZERO', None)
    >>> classify_cost_basis(None)
    ('MISSING', None)
    >>> classify_cost_basis(112.5)
    ('OK', 112.5)
    """
    value = _as_float(avg_cost_price)
    if value is None:
        return CostBasisStatus.MISSING, None
    if value == 0:
        return CostBasisStatus.ZERO, None
    if value < 0:
        return CostBasisStatus.NEGATIVE, None
    if value < MIN_PLAUSIBLE_COST:
        return CostBasisStatus.IMPLAUSIBLE, None
    return CostBasisStatus.OK, value


def safe_pnl(
    quantity: Any,
    current_price: Any,
    avg_cost_price: Any,
) -> dict[str, Any]:
    """
    Compute P&L *only* when it is actually computable.

    Unlike the existing inline arithmetic, this NEVER returns a number it cannot
    justify. When the cost basis is unusable the result carries ``pnl_thb=None``
    and ``reliable=False``, plus ``phantom_pnl_thb`` showing what the old
    ``quantity * (price - 0)`` path *would* have reported — which is what makes the
    magnitude of the defect visible instead of invisible.

    Market value is returned regardless, because it does not depend on cost basis
    and is still trustworthy (subject to price freshness, a separate concern
    handled by ``data_collector/feed_health.py``).
    """
    qty = _as_float(quantity)
    price = _as_float(current_price)
    status, cost = classify_cost_basis(avg_cost_price)

    market_value = round(qty * price, 2) if (qty is not None and price is not None) else None

    if status == CostBasisStatus.OK and qty is not None and price is not None:
        pnl = qty * (price - cost)
        invested = qty * cost
        return {
            "reliable": True,
            "cost_basis_status": status,
            "avg_cost_price": cost,
            "market_value_thb": market_value,
            "invested_thb": round(invested, 2),
            "pnl_thb": round(pnl, 2),
            "pnl_pct": round(pnl / invested * 100, 4) if invested else None,
            "phantom_pnl_thb": None,
            "note": None,
        }

    if qty is None or price is None:
        reason = "quantity or price is absent, so neither value nor P&L can be computed"
    else:
        reason = (
            f"cost basis is {status} — P&L is NOT COMPUTABLE. It is not zero and it is "
            f"not equal to market value. Supply a real average cost to obtain P&L."
        )

    return {
        "reliable": False,
        "cost_basis_status": status,
        "avg_cost_price": None,
        "market_value_thb": market_value,
        "invested_thb": None,
        "pnl_thb": None,
        "pnl_pct": None,
        # What the pre-guard code path would have claimed. Kept so the size of the
        # misstatement is reportable rather than merely describable.
        "phantom_pnl_thb": market_value if status in CostBasisStatus.UNUSABLE else None,
        "note": reason,
    }


def audit_holdings(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """
    Audit a set of holdings rows for cost-basis integrity.

    ``rows`` accepts anything mapping-like with ``ticker``, ``quantity``,
    ``avg_cost_price`` and optionally ``current_price`` — asyncpg Records included.

    Returns a report with the count and market-value share of positions whose P&L
    cannot be computed, and the total phantom P&L currently being asserted.
    """
    per_ticker: dict[str, Any] = {}
    unusable: list[str] = []
    total_value = 0.0
    unusable_value = 0.0
    phantom_total = 0.0

    for row in rows:
        ticker = str(row.get("ticker") or "UNKNOWN")
        result = safe_pnl(
            row.get("quantity"),
            row.get("current_price"),
            row.get("avg_cost_price"),
        )
        per_ticker[ticker] = result
        if result["market_value_thb"] is not None:
            total_value += result["market_value_thb"]
            if not result["reliable"]:
                unusable_value += result["market_value_thb"]
        if not result["reliable"]:
            unusable.append(ticker)
        if result["phantom_pnl_thb"]:
            phantom_total += result["phantom_pnl_thb"]

    count = len(per_ticker)
    bad = len(unusable)
    return {
        "holdings_checked": count,
        "holdings_without_usable_cost_basis": bad,
        "unusable_tickers": sorted(unusable),
        "total_market_value_thb": round(total_value, 2),
        "market_value_without_cost_basis_thb": round(unusable_value, 2),
        "share_of_book_without_cost_basis_pct": (
            round(unusable_value / total_value * 100, 2) if total_value else None
        ),
        "phantom_pnl_thb": round(phantom_total, 2),
        "phantom_pnl_explanation": (
            "Sum of P&L the pre-guard arithmetic would report for positions with no "
            "cost basis. Because cost coerces to 0, that arithmetic returns the full "
            "market value as profit. Any figure of this magnitude in a brief or "
            "dashboard is an artefact, not a gain."
        ),
        "portfolio_pnl_reliable": bad == 0,
        "verdict": "CLEAN" if bad == 0 else ("TOTAL" if bad == count else "PARTIAL"),
        "per_ticker": per_ticker,
    }


def scan_snapshot(snapshot_path: str | Path) -> dict[str, Any]:
    """
    Scan a written collector snapshot for the fingerprints of the zero-cost defect,
    without needing the database.

    Two independent fingerprints are checked per holding:

    1. ``pnl_thb == market_value_thb`` — the arithmetic signature of ``cost == 0``.
    2. ``pnl_pct == 0`` while ``pnl_thb != 0`` — mutually contradictory claims that
       cannot both be true and so prove at least one field is fabricated.

    A third check runs at portfolio level: ``total_pnl_thb == total_market_value_thb``.
    """
    path = Path(snapshot_path)
    if not path.exists():
        return {"ok": False, "error": f"snapshot not found: {path}"}

    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": f"could not read snapshot: {exc}"}

    findings: list[dict[str, Any]] = []
    holdings = data.get("holdings") or {}
    for ticker, position in holdings.items():
        if not isinstance(position, Mapping) or position.get("error"):
            continue
        value = _as_float(position.get("market_value_thb"))
        pnl = _as_float(position.get("pnl_thb"))
        pct = _as_float(position.get("pnl_pct"))

        if value is not None and pnl is not None and abs(value - pnl) < 0.01 and value != 0:
            findings.append(
                {
                    "ticker": ticker,
                    "fingerprint": "pnl_equals_market_value",
                    "market_value_thb": value,
                    "pnl_thb": pnl,
                    "meaning": "cost basis was 0; entire position reported as profit",
                }
            )
        if pnl not in (None, 0) and pct == 0:
            findings.append(
                {
                    "ticker": ticker,
                    "fingerprint": "nonzero_pnl_with_zero_pct",
                    "pnl_thb": pnl,
                    "pnl_pct": pct,
                    "meaning": "internally contradictory — at least one field is fabricated",
                }
            )

    total_value = _as_float(data.get("total_market_value_thb"))
    total_pnl = _as_float(data.get("total_pnl_thb"))
    portfolio_level = (
        total_value is not None
        and total_pnl is not None
        and total_value != 0
        and abs(total_value - total_pnl) < 0.01
    )

    return {
        "ok": True,
        "snapshot": str(path),
        "generated_at": data.get("generated_at"),
        "findings": findings,
        "portfolio_level_fingerprint": portfolio_level,
        "total_market_value_thb": total_value,
        "total_pnl_thb": total_pnl,
        "affected_tickers": sorted({f["ticker"] for f in findings}),
        "verdict": "DEFECT_CONFIRMED" if (findings or portfolio_level) else "CLEAN",
    }


def format_report(scan: Mapping[str, Any], audit: Mapping[str, Any] | None = None) -> str:
    """Render a short human-readable report for the nightly log / CLI."""
    lines: list[str] = []
    if not scan.get("ok"):
        return f"COST BASIS SCAN — ERROR: {scan.get('error')}"

    verdict = scan["verdict"]
    icon = "✅" if verdict == "CLEAN" else "🚨"
    lines.append(f"{icon} COST BASIS INTEGRITY — {verdict}")
    lines.append(f"   snapshot: {scan['snapshot']}")
    lines.append(f"   generated_at: {scan.get('generated_at')}")

    if verdict != "CLEAN":
        lines.append(
            "   Every P&L figure derived from these holdings is meaningless. "
            "The cost basis is 0, so P&L collapses to market value."
        )
        if scan.get("portfolio_level_fingerprint"):
            lines.append(
                f"   portfolio level: total_pnl_thb == total_market_value_thb == "
                f"{scan['total_market_value_thb']:,.2f} — an asserted infinite return"
            )
        for finding in scan["findings"]:
            lines.append(f"   • {finding['ticker']}: {finding['fingerprint']} — {finding['meaning']}")
        lines.append(
            "   REMEDY: populate holdings.avg_cost_price with real average costs. "
            "Until then P&L is suppressed (None), not zeroed."
        )

    if audit:
        lines.append("")
        lines.append(
            f"   audit: {audit['holdings_without_usable_cost_basis']}/{audit['holdings_checked']} "
            f"holdings unusable ({audit['verdict']}), "
            f"phantom P&L THB {audit['phantom_pnl_thb']:,.2f}"
        )
    return "\n".join(lines)


def _default_snapshot_path() -> Path:
    return Path(__file__).resolve().parent.parent / "data_collector" / "portfolio_snapshot.json"


def main(argv: Sequence[str] | None = None) -> int:
    """CLI. Exit 0 = clean, 1 = defect found, 2 = could not scan."""
    argv = list(argv if argv is not None else sys.argv[1:])
    target = Path(argv[0]) if argv else _default_snapshot_path()

    scan = scan_snapshot(target)
    if not scan.get("ok"):
        print(format_report(scan))
        return 2

    print(format_report(scan))

    out = Path(__file__).resolve().parent.parent / "data" / "cost_basis_audit.json"
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(scan, indent=2, ensure_ascii=False))
        print(f"\nReport written to {out}")
    except OSError as exc:  # pragma: no cover - best effort
        print(f"\n(could not write report: {exc})")

    return 0 if scan["verdict"] == "CLEAN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
