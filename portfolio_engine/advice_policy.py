"""Central, non-negotiable advice policies.

This module changes advice labels only.  It never places, schedules, or routes
orders.
"""
from __future__ import annotations

from typing import Any, Dict, Tuple

try:
    from holding_meta import owner_hold_tickers
except ImportError:  # package import in tests/tools
    from portfolio_engine.holding_meta import owner_hold_tickers


PROHIBITED_OWNER_HOLD_ACTIONS = {
    "sell",
    "reduce",
    "review_reduce",
    "stop_loss",
    "trim",
}
OWNER_HOLD_NOTE = "owner hold - informational only, no sell/trim suggested"


def _ticker_key(ticker: Any) -> str:
    value = str(ticker or "").strip().upper()
    return value[:-3] if value.endswith(".BK") else value


def apply_owner_hold_policy(
    ticker: str,
    action: str,
    payload: Dict[str, Any],
) -> Tuple[str, Dict[str, Any]]:
    """Return an owner-hold-safe ``(action, payload)`` pair.

    Both bare SET symbols (``PTTEP``) and Yahoo-style symbols
    (``PTTEP.BK``) match the configured owner holds.  Non-owner holds and
    non-prohibited actions are returned unchanged.
    """
    holds = {_ticker_key(value) for value in owner_hold_tickers()}
    if _ticker_key(ticker) not in holds or str(action or "").lower() not in PROHIBITED_OWNER_HOLD_ACTIONS:
        return action, payload
    safe_payload = dict(payload or {})
    safe_payload["actionable"] = False
    safe_payload["note"] = OWNER_HOLD_NOTE
    return "info_risk_alert", safe_payload
