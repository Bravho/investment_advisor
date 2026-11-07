"""XD (ex-dividend) timing analysis for the Thai watch list.

Reads the raw yfinance files written by pull_stocks.py / pull_funds.py and returns, per item:
  - next XD date: estimated from last year's XD date (same calendar date + 365 days) unless a
    confirmed date is supplied; a note is raised when it falls within 60 days.
  - per past XD event: dividend payout (% of the prior close), short-term price moves before and
    after the XD date, and the total return of two entry choices (buy before XD vs buy after XD).
  - summary: averages, share of events recovering the pre-XD close within 20 trading days,
    after-tax yield (default 10% withholding), and a plain entry-timing note.

Research only. Not backtested. Prices are raw (unadjusted) closes, so the ex-day drop is visible.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

import numpy as np
import pandas as pd

WITHHOLDING = 0.10   # usual Thai withholding on dividends paid to individuals; user to confirm
ALERT_DAYS = 60      # show a note when the next XD is within two months
LOOKBACK_YEARS = 3


def _series(pairs):
    return pd.Series([v for _, v in pairs], index=pd.to_datetime([d for d, _ in pairs]))


def analyze(ticker: str, raw: dict[str, Any], today: dt.date | None = None,
            confirmed_next_xd: dict[str, str] | None = None) -> dict[str, Any]:
    today = today or dt.date.today()
    confirmed_next_xd = confirmed_next_xd or {}
    c = _series(raw["closes"]).dropna()
    end = c.index[-1]
    last = float(c.iloc[-1])
    divs = _series(raw["dividends"]) if raw["dividends"] else pd.Series(dtype=float)
    divs = divs[divs.index >= c.index[0]]

    # --- next XD estimate ---------------------------------------------------
    next_xd = None
    basis = None
    if ticker in confirmed_next_xd:
        next_xd = dt.date.fromisoformat(confirmed_next_xd[ticker])
        basis = "confirmed (news source, see sources)"
    elif len(divs):
        candidates = [(d + pd.Timedelta(days=365)).date() for d in divs.index]
        candidates = [x for x in candidates if x >= today]
        if candidates:
            next_xd = min(candidates)
            basis = "estimated from last year's XD date"
    days_to = (next_xd - today).days if next_xd else None
    alert = days_to is not None and 0 <= days_to <= ALERT_DAYS

    # --- past XD events ------------------------------------------------------
    events = []
    for d, dv in divs.items():
        if d < c.index[0] + pd.Timedelta(days=20):
            continue
        idx = c.index.searchsorted(d)
        if idx < 11 or idx + 21 >= len(c):
            continue
        prev = float(c.iloc[idx - 1])
        payout = dv / prev * 100 if prev else np.nan
        pre5 = (c.iloc[idx - 1] / c.iloc[idx - 6] - 1) * 100
        pre10 = (c.iloc[idx - 1] / c.iloc[idx - 11] - 1) * 100
        post5 = (c.iloc[idx + 5] / c.iloc[idx] - 1) * 100
        post10 = (c.iloc[idx + 10] / c.iloc[idx] - 1) * 100
        post20 = (c.iloc[idx + 20] / c.iloc[idx] - 1) * 100
        recovered = bool(c.iloc[idx:idx + 21].max() >= prev)
        # Entry A: buy 10 days before XD, hold through XD, sell 10 days after. Dividend included.
        before_total = ((c.iloc[idx + 10] + dv) / c.iloc[idx - 10] - 1) * 100
        before_net = ((c.iloc[idx + 10] + dv * (1 - WITHHOLDING)) / c.iloc[idx - 10] - 1) * 100
        # Entry B: buy the day after XD, sell 10 trading days later. No dividend.
        after_total = (c.iloc[idx + 11] / c.iloc[idx + 1] - 1) * 100
        events.append(dict(date=str(d.date()), dividend=round(float(dv), 4), payout_pct=round(float(payout), 2),
                           pre5=round(float(pre5), 2), pre10=round(float(pre10), 2), post5=round(float(post5), 2),
                           post10=round(float(post10), 2), post20=round(float(post20), 2), recovered20=recovered,
                           before_total_net=round(float(before_net), 2), before_total=round(float(before_total), 2),
                           after_total=round(float(after_total), 2)))

    n = len(events)
    def avg(key):
        vals = [e[key] for e in events if e[key] is not None and not (isinstance(e[key], float) and np.isnan(e[key]))]
        return round(float(np.mean(vals)), 2) if vals else None

    summary = dict(events=n, avg_payout_pct=avg("payout_pct"), avg_pre5=avg("pre5"), avg_pre10=avg("pre10"),
                   avg_post5=avg("post5"), avg_post10=avg("post10"), avg_post20=avg("post20"),
                   recover20_pct=round(sum(e["recovered20"] for e in events) / n * 100, 0) if n else None,
                   avg_before_total_net=avg("before_total_net"), avg_after_total=avg("after_total"))
    # Entry timing: compare Entry A (before, net of tax) with Entry B (after).
    if n < 3:
        timing = "not enough past XD events (fewer than 3) - no timing view"
    else:
        gap = summary["avg_after_total"] - summary["avg_before_total_net"]
        if gap > 0.5:
            timing = f"waiting until after XD looked better on average (about {gap:.1f} points better over 10 days)"
        elif gap < -0.5:
            timing = f"buying before XD looked better on average (about {-gap:.1f} points better over 10 days)"
        else:
            timing = "no clear XD effect on average - the dividend is not the deciding factor"

    # Dividend payout vs short-term trend, in one line
    if n >= 3 and summary["avg_payout_pct"] is not None:
        ratio = (summary["avg_post10"] or 0) - summary["avg_payout_pct"]
        trend_line = (f"average payout {summary['avg_payout_pct']:.2f}% vs price {summary['avg_post10']:+.2f}% "
                      f"in the 10 days after XD (net {ratio:+.2f} points)")
    else:
        trend_line = "not enough events for payout vs trend"

    yld_hist = float(divs[divs.index > end - pd.Timedelta(days=365)].sum()) / last * 100 if len(divs) else 0.0
    return dict(
        next_xd=dict(date=str(next_xd) if next_xd else None, basis=basis, days_to_xd=days_to, alert_within_60d=alert,
                     note=(f"XD in {days_to} days ({basis}) - check timing" if alert else None)),
        summary=summary, timing_note=timing, payout_vs_trend=trend_line,
        after_tax_yield_hist_pct=round(yld_hist * (1 - WITHHOLDING), 2),
        withholding_assumed_pct=WITHHOLDING * 100,
        events=events[-8:],  # keep the latest 8 events for display
        history_events_total=n,
    )
