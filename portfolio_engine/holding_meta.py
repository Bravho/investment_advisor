"""Holding attributes: tax wrapper, lock-until date, pending units (2026-10-30).

`holding_attributes` (local investor_db, keyed by ticker) carries what the `holdings` table cannot:
  * tax_wrapper  e.g. 'ThaiESG' (5-year hold counted day-to-day from the purchase/allotment date)
  * lock_until   no sell / switch / trim suggestion may be produced before this date
  * units_status 'pending' = amount invested is known but units/allotment NAV are not confirmed yet
                 (holdings.quantity stays 0 until Tho confirms; units are never guessed into the DB)
Valuation of a pending fund is done in the data collector snapshot (amount invested until the allotment NAV is
known, then amount x NAV_now / NAV_allotment, labelled 'estimated - units pending confirmation').
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

DDL = """
CREATE TABLE IF NOT EXISTS holding_attributes (
    ticker VARCHAR(30) PRIMARY KEY, tax_wrapper VARCHAR(20), order_date DATE, purchase_date DATE, lock_until DATE,
    amount_invested_thb NUMERIC(18,2), units_status VARCHAR(20) NOT NULL DEFAULT 'confirmed', allotment_nav NUMERIC(18,6),
    fund_house VARCHAR(80), look_through VARCHAR(40), risk_proxy VARCHAR(30), notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now())
"""


def _jsonable(d: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for k, v in d.items():
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        elif v.__class__.__name__ == "Decimal":
            out[k] = float(v)
        else:
            out[k] = v
    return out


async def load_attrs(pool: Any) -> dict[str, dict[str, Any]]:
    try:
        async with pool.acquire() as conn:
            await conn.execute(DDL)
            rows = await conn.fetch("SELECT * FROM holding_attributes")
    except Exception:  # noqa: BLE001
        return {}
    return {r["ticker"]: _jsonable(dict(r)) for r in rows}


def is_locked(attr: Optional[dict[str, Any]], today: Optional[date] = None) -> bool:
    if not attr or not attr.get("lock_until"):
        return False
    return (today or date.today()) < date.fromisoformat(str(attr["lock_until"])[:10])


def locked_tickers(attrs: dict[str, dict[str, Any]], today: Optional[date] = None) -> set[str]:
    return {t for t, a in attrs.items() if is_locked(a, today)}


def is_pending(attr: Optional[dict[str, Any]]) -> bool:
    return bool(attr) and attr.get("units_status") == "pending"


def lock_label(attr: Optional[dict[str, Any]]) -> Optional[str]:
    if not attr or not attr.get("tax_wrapper"):
        return None
    s = f"{attr['tax_wrapper']}"
    if attr.get("lock_until"):
        s += f", locked until {attr['lock_until']} (no sell/switch before)"
    if is_pending(attr):
        s += f"; units pending confirmation (invested {float(attr.get('amount_invested_thb') or 0):,.0f} THB, allotment {attr.get('purchase_date')})"
    return s
