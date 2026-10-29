"""Live + offline extractors, registered by method name.

Strategy: when the network and `yfinance` are available, the quote extractor
pulls a live price; fundamentals and history come from the curated dataset
unless overridden. When offline, everything falls back to the sample dataset
and is flagged so provenance stays honest.
"""
from __future__ import annotations

import logging
from typing import Any

from ..config import USD_THB, network_available
from ..core.provenance import Fact, Investment
from .base import register
from .sample_data import get_sample

# Thai funds / some tickers aren't on Yahoo; we handle that gracefully, so keep
# yfinance's own "possibly delisted" noise out of the CLI output.
logging.getLogger("yfinance").setLevel(logging.CRITICAL)


def _apply_meta(inv: Investment, meta: dict[str, Any]) -> None:
    inv.name = inv.name or meta.get("name", inv.ticker)
    # specific class from the data source (e.g. "SET Bank") refines the coarse
    # classifier ("SET Equity") so the right analyst branch + valuation fire.
    if meta.get("asset_class"):
        inv.asset_class = meta["asset_class"]
    inv.currency = inv.currency or meta.get("currency", "")
    if inv.price is None:
        inv.price = meta.get("price")
        inv.price_display = meta.get("price_display", "")
        inv.change_pct = meta.get("change_pct")


def _facts_for(ticker: str, category: str, source: dict, offline: bool) -> list[Fact]:
    data = get_sample(ticker)
    if not data:
        return []
    facts: list[Fact] = []
    for metric, info in data["facts"].items():
        if info.get("category") != category:
            continue
        note = info.get("note", "")
        if offline:
            note = (note + " · offline sample").strip(" ·")
        facts.append(
            Fact(
                metric=metric,
                value=info.get("value"),
                unit=info.get("unit", ""),
                source_name=source.get("name", category),
                source_url=source.get("url", ""),
                period=info.get("period", "TTM"),
                confidence=info.get("confidence", 1.0),
                note=note,
                history=info.get("history"),
            )
        )
    return facts


def _try_live_quote(ticker: str) -> dict[str, Any] | None:
    """Best-effort live price via yfinance; returns meta overrides or None."""
    if not network_available():
        return None
    import contextlib
    import io

    try:
        import yfinance as yf  # type: ignore

        # yfinance prints "possibly delisted / 404" straight to stderr for
        # unlisted symbols (e.g. Thai funds); capture it — we handle the None.
        with contextlib.redirect_stderr(io.StringIO()):
            t = yf.Ticker(ticker)
            fast = getattr(t, "fast_info", {}) or {}
            price = fast.get("last_price") or fast.get("lastPrice")
            prev = fast.get("previous_close") or fast.get("previousClose")
        if price:
            change = round((price - prev) / prev * 100, 2) if prev else None
            cur = fast.get("currency", "")
            disp = f"{price:,.2f}"
            return {"price": float(price), "price_display": disp, "change_pct": change,
                    "currency": cur}
    except Exception:
        return None
    return None


@register("yahoo_quote")
def yahoo_quote(source: dict, inv: Investment) -> list[Fact]:
    data = get_sample(inv.ticker)
    meta = dict(data["meta"]) if data else {"name": inv.ticker}
    live = _try_live_quote(inv.ticker)
    offline = live is None
    if live:
        meta.update({k: v for k, v in live.items() if v is not None})
    _apply_meta(inv, meta)
    facts = _facts_for(inv.ticker, "price", source, offline)
    if not data and not live:
        inv.flag(f"No data available for {inv.ticker} (no sample, no live source)")
    elif offline:
        inv.flag("Live quote unavailable — using curated sample prices")
    return facts


def _human_cap(market_cap: float, currency: str) -> str:
    sym = "฿" if currency == "THB" else "$" if currency in ("USD", "") else currency + " "
    for div, suf in ((1e12, "T"), (1e9, "B"), (1e6, "M")):
        if market_cap >= div:
            return f"{sym}{market_cap / div:.2f}{suf}"
    return f"{sym}{market_cap:.0f}"


def _live_history(t: Any) -> dict[str, list[list[Any]]]:
    """Best-effort multi-year history from yfinance annual financials (~4yr)."""
    import contextlib
    import io

    out: dict[str, list[list[Any]]] = {}
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            fin = t.financials
            bs = t.balance_sheet
        if fin is not None and not fin.empty and "Total Revenue" in fin.index:
            rev = fin.loc["Total Revenue"].dropna()
            pairs = sorted((c.year, float(v)) for c, v in rev.items())
            growth = [[pairs[i][0], round((pairs[i][1] - pairs[i - 1][1]) / abs(pairs[i - 1][1]) * 100, 1)]
                      for i in range(1, len(pairs)) if pairs[i - 1][1]]
            if growth:
                out["Revenue growth"] = growth
        if fin is not None and bs is not None and not fin.empty and not bs.empty:
            ni_key = next((k for k in ("Net Income", "Net Income Common Stockholders") if k in fin.index), None)
            eq_key = next((k for k in ("Stockholders Equity", "Total Stockholder Equity", "Common Stock Equity") if k in bs.index), None)
            if ni_key and eq_key:
                ni, eq = fin.loc[ni_key], bs.loc[eq_key]
                roe = [[c.year, round(float(ni[c]) / float(eq[c]) * 100, 1)]
                       for c in ni.index if c in eq.index and eq[c]]
                roe = sorted(roe)
                if roe:
                    out["ROE"] = roe
    except Exception:
        return {}
    return out


def _try_live_fundamentals(ticker: str) -> dict[str, dict[str, Any]] | None:
    """Live ratios via yfinance .info (+ short history). Per-metric best-effort."""
    if not network_available():
        return None
    import contextlib
    import io

    try:
        import yfinance as yf  # type: ignore

        with contextlib.redirect_stderr(io.StringIO()):
            t = yf.Ticker(ticker)
            info = dict(getattr(t, "info", {}) or {})
        if not info or info.get("trailingPE") is None and info.get("marketCap") is None:
            return None
        out: dict[str, dict[str, Any]] = {}

        def put(metric: str, val: Any, unit: str, period: str = "TTM") -> None:
            if val is not None:
                try:
                    out[metric] = {"value": round(float(val), 2), "unit": unit, "period": period}
                except (TypeError, ValueError):
                    pass

        put("P/E", info.get("trailingPE"), "×")
        roe = info.get("returnOnEquity")
        if roe is not None:
            put("ROE", roe * 100 if abs(roe) <= 2 else roe, "%")
        dy = info.get("dividendYield")
        if dy is not None:
            put("Dividend yield", dy * 100 if dy <= 1 else dy, "%")
        de = info.get("debtToEquity")
        if de is not None:
            put("Debt/Equity", de / 100 if de > 3 else de, "")
        rg = info.get("revenueGrowth")
        if rg is not None:
            put("Revenue growth", rg * 100 if abs(rg) <= 2 else rg, "%")
        mc = info.get("marketCap")
        cur = info.get("currency", "")
        if mc:
            usd_bn = (mc / USD_THB if cur == "THB" else mc) / 1e9
            out["Market cap"] = {"value": round(usd_bn, 2), "unit": "USD bn",
                                 "period": "spot", "note": _human_cap(mc, cur)}
        fcf = info.get("freeCashflow")
        if fcf and mc:
            put("FCF yield", fcf / mc * 100, "%")

        for metric, hist in _live_history(t).items():
            out.setdefault(metric, {"value": hist[-1][1], "unit": "%", "period": "FY"})
            out[metric]["history"] = hist
        return out or None
    except Exception:
        return None


@register("fundamentals")
def fundamentals(source: dict, inv: Investment) -> list[Fact]:
    """Live ratios where Yahoo provides them; curated values/history otherwise.
    Provenance is tagged per metric so the report shows what is live vs curated.
    """
    data = get_sample(inv.ticker)
    if data:
        _apply_meta(inv, data["meta"])
    curated = _facts_for(inv.ticker, "ratios", source, offline=False) if data else []
    cur_map: dict[str, Fact] = {f.metric: f for f in curated}

    live = _try_live_fundamentals(inv.ticker)
    if live:
        for metric, info in live.items():
            hist = info.get("history") or (cur_map[metric].history if metric in cur_map else None)
            note = "Yahoo (live)" if info.get("history") else "Yahoo (live) · curated history"
            cur_map[metric] = Fact(
                metric=metric,
                value=info.get("value"),
                unit=info.get("unit", ""),
                source_name=source.get("name", "Fundamentals"),
                source_url=source.get("url", ""),
                period=info.get("period", "TTM"),
                note=info.get("note", note),
                history=hist,
            )
        for metric, fact in cur_map.items():
            if metric not in live and not fact.note:
                fact.note = "curated"
        inv.flag(f"Fundamentals: {len(live)} live (Yahoo), remainder curated")
    elif data:
        inv.flag("Fundamentals: curated dataset (live unavailable)")

    if not data and not live:
        inv.flag(f"No fundamentals for {inv.ticker}")
    return list(cur_map.values())


@register("news_rss")
def news_rss(source: dict, inv: Investment) -> list[Fact]:
    offline = not network_available()
    facts = _facts_for(inv.ticker, "news", source, offline)
    return facts


@register("sample")
def sample_all(source: dict, inv: Investment) -> list[Fact]:
    data = get_sample(inv.ticker)
    if not data:
        inv.flag(f"No sample data for {inv.ticker}")
        return []
    _apply_meta(inv, data["meta"])
    out: list[Fact] = []
    for cat in ("price", "ratios", "news"):
        out.extend(_facts_for(inv.ticker, cat, source, offline=True))
    return out
