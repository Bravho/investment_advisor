"""Official-NAV anchoring for proxied funds (2026-11-01, P2.3).

SCBGOLDE used a pure GC=F x THB=X proxy although fund_nav_daily holds ~1y of official NAVs.
* nav_anchored_series(): official NAV where it exists; proxy RETURNS chained before the first NAV
  (long look-backs) and after the last NAV (days not yet published). Marked in the data note.
* tracking(): daily / weekly / 3-day correlation, beta and annualised tracking error of proxy vs NAV.
  Daily correlation is low (~0.5) because the Thai NAV cut-off is not synchronous with the COMEX close;
  multi-day figures are the relevant ones for a swing/position investor.
"""
from __future__ import annotations

from typing import Any, Optional

import numpy as np
import pandas as pd

MIN_NAV_POINTS = 120
MAX_NAV_AGE_DAYS = 7


async def load_navs(pool: Any, codes: list[str]) -> dict[str, pd.Series]:
    out: dict[str, pd.Series] = {}
    for code in codes:
        try:
            rows = await pool.fetch("SELECT nav_date, nav FROM fund_nav_daily WHERE code = $1 AND nav > 0 ORDER BY nav_date", code)
        except Exception:  # noqa: BLE001
            continue
        if rows:
            out[code] = pd.Series({pd.Timestamp(r["nav_date"]): float(r["nav"]) for r in rows}).sort_index()
    return out


def usable(nav: Optional[pd.Series]) -> bool:
    if nav is None or len(nav) < MIN_NAV_POINTS:
        return False
    return (pd.Timestamp.today().normalize() - nav.index[-1]).days <= MAX_NAV_AGE_DAYS


def nav_anchored_series(proxy: pd.Series, nav: pd.Series) -> pd.Series:
    """Index = proxy index. Official NAV on NAV dates; proxy returns chained outside the NAV window."""
    proxy = proxy.dropna()
    idx = proxy.index.tz_localize(None) if getattr(proxy.index, "tz", None) is not None else proxy.index
    proxy = pd.Series(proxy.values, index=idx)
    nav = nav[(nav.index >= proxy.index[0])]
    out = pd.Series(np.nan, index=proxy.index.union(nav.index))
    out.loc[nav.index] = nav.values
    first, last = nav.index[0], nav.index[-1]
    p = proxy.reindex(out.index).ffill()
    before = out.index < first
    if before.any():
        out.loc[before] = (p[before] / p.loc[first]) * nav.loc[first]
    after = out.index > last
    if after.any():
        out.loc[after] = (p[after] / p.loc[last]) * nav.loc[last]
    return out.ffill().reindex(proxy.index).ffill()


def tracking(proxy: pd.Series, nav: pd.Series) -> dict[str, Any]:
    idx = proxy.index.tz_localize(None) if getattr(proxy.index, "tz", None) is not None else proxy.index
    proxy = pd.Series(proxy.values, index=idx)
    j = pd.concat([nav, proxy.ffill()], axis=1, keys=["nav", "proxy"]).dropna()
    if len(j) < 30:
        return {"status": "insufficient", "n": len(j)}

    def stats(r: pd.DataFrame, ann: float) -> dict[str, Any]:
        r = r.dropna()
        return {"n": int(len(r)), "corr": round(float(r.corr().iloc[0, 1]), 3),
                "beta": round(float(np.cov(r.nav, r.proxy)[0, 1] / r.proxy.var()), 3),
                "tracking_error_ann_pct": round(float((r.nav - r.proxy).std() * np.sqrt(ann) * 100), 2)}
    lg = np.log(j)
    return {"status": "ok", "from": str(j.index[0].date()), "to": str(j.index[-1].date()),
            "daily": stats(lg.diff(), 252), "three_day": stats(lg.diff(3).iloc[::3], 252 / 3),
            "weekly": stats(np.log(j.resample("W").last()).diff(), 52),
            "period_return_pct": {"nav": round(float((j.nav.iloc[-1] / j.nav.iloc[0] - 1) * 100), 2),
                                  "proxy": round(float((j.proxy.iloc[-1] / j.proxy.iloc[0] - 1) * 100), 2)},
            "note": "daily corr is low because the Thai NAV cut-off is not synchronous with the COMEX close; use multi-day figures"}
