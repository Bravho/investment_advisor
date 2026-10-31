"""Pure, point-in-time signal component and composite scoring.

This module is deliberately limited to pandas/numpy calculations.  It owns the
live signal weights and price transformations so a historical runner can call
the exact same implementation without a database or network dependency.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Mapping, Optional, Set

import numpy as np
import pandas as pd


BASE_WEIGHTS: Dict[str, float] = {
    "value": .15,
    "quality": .15,
    "momentum": .15,
    "low_vol": .10,
    "dividend": .10,
    "technical": .15,
    "flows": .05,
    "fundamentals": .10,
    "sentiment": .05,
}
REGIME_TILT: Dict[str, Dict[str, float]] = {
    "risk_on": {"momentum": +.05, "technical": +.05, "low_vol": -.05, "dividend": -.05},
    "risk_off": {
        "low_vol": +.05,
        "quality": +.05,
        "dividend": +.05,
        "momentum": -.05,
        "technical": -.05,
        "value": -.05,
    },
    "neutral": {},
}

# metric -> (component, higher_is_better).  These are the price-backed rows of
# signals.METRIC_MAP and intentionally retain the live rank/average semantics.
PRICE_METRIC_MAP = {
    "mom_12_1": ("momentum", True),
    "mom_6m": ("momentum", True),
    "vol_1y": ("low_vol", False),
    "beta": ("low_vol", False),
    "trend": ("technical", True),
    "rs_3m": ("technical", True),
    "rsi_score": ("technical", True),
    "macd_hist_pct": ("technical", True),
    "volume_confirm": ("technical", True),
}


def _finite(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _through_asof(series: Optional[pd.Series], asof: Any) -> Optional[pd.Series]:
    if series is None:
        return None
    result = series.copy()
    result.index = pd.to_datetime(result.index)
    stamp = pd.Timestamp(asof)
    if result.index.tz is not None:
        if stamp.tzinfo is None:
            stamp = stamp.tz_localize(result.index.tz)
        else:
            stamp = stamp.tz_convert(result.index.tz)
    elif stamp.tzinfo is not None:
        stamp = stamp.tz_localize(None)
    return result.sort_index().loc[:stamp]


def _rsi(close: pd.Series, n: int = 14) -> Optional[float]:
    delta = close.diff().dropna()
    if len(delta) < n + 1:
        return None
    up = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    down = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    relative = up.iloc[-1] / down.iloc[-1] if down.iloc[-1] > 0 else np.inf
    return float(100 - 100 / (1 + relative))


def rsi_score(value: Optional[float]) -> Optional[float]:
    """Live RSI transformation: reward the healthy-trend band around 55."""
    number = _finite(value)
    return -abs(number - 55) if number is not None else None


def _macd_hist(close: pd.Series) -> Optional[float]:
    if len(close) < 40:
        return None
    macd = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
    hist = macd - macd.ewm(span=9, adjust=False).mean()
    return float(hist.iloc[-1] / close.iloc[-1] * 100)


def price_components(
    close: pd.Series,
    volume: Optional[pd.Series],
    bench: Optional[pd.Series],
    asof: Any,
) -> Dict[str, Any]:
    """Return the live raw price metrics using observations no later than ``asof``.

    Despite the public name, the result contains the raw metrics which are
    cross-sectionally ranked into the high-level momentum/low_vol/technical
    components.  Names and transformations match ``signals.py``.
    """
    close_asof = _through_asof(close, asof)
    c = close_asof.dropna() if close_asof is not None else pd.Series(dtype=float)
    if c.empty:
        return {}
    metrics: Dict[str, Any] = {"as_of": str(c.index[-1].date()), "price": float(c.iloc[-1])}
    returns = c.pct_change().dropna()
    if len(c) >= 252:
        metrics["mom_12_1"] = float(c.iloc[-22] / c.iloc[-252] - 1)
    if len(c) >= 126:
        metrics["mom_6m"] = float(c.iloc[-1] / c.iloc[-126] - 1)
    if len(returns) >= 120:
        metrics["vol_1y"] = float(returns.iloc[-252:].std() * np.sqrt(252))

    bench_asof = _through_asof(bench, asof)
    if bench_asof is not None:
        b = bench_asof.dropna()
        joined_returns = pd.concat([returns, b.pct_change()], axis=1, join="inner").dropna().iloc[-252:]
        if len(joined_returns) > 60 and joined_returns.iloc[:, 1].var() > 0:
            metrics["beta"] = float(
                joined_returns.iloc[:, 0].cov(joined_returns.iloc[:, 1]) / joined_returns.iloc[:, 1].var()
            )
        joined_closes = pd.concat([c, b], axis=1, join="inner").dropna()
        if len(joined_closes) > 63:
            metrics["rs_3m"] = float(
                (joined_closes.iloc[-1, 0] / joined_closes.iloc[-63, 0])
                / (joined_closes.iloc[-1, 1] / joined_closes.iloc[-63, 1])
                - 1
            )

    sma50 = c.iloc[-50:].mean() if len(c) >= 50 else None
    sma200 = c.iloc[-200:].mean() if len(c) >= 200 else None
    if sma50 is not None and sma200 is not None:
        metrics["trend"] = (
            (1 if c.iloc[-1] > sma50 else -1)
            + (1 if sma50 > sma200 else -1)
            + (1 if c.iloc[-1] > sma200 else -1)
        )
    metrics["rsi14"] = _rsi(c)
    metrics["rsi_score"] = rsi_score(metrics.get("rsi14"))
    metrics["macd_hist_pct"] = _macd_hist(c)

    volume_asof = _through_asof(volume, asof)
    if volume_asof is not None and volume_asof.dropna().size > 60:
        v = volume_asof.dropna()
        mean60 = v.iloc[-60:].mean()
        ratio = float(v.iloc[-20:].mean() / mean60) if mean60 > 0 else None
        up = float(c.iloc[-1] / c.iloc[-21] - 1) if len(c) > 21 else 0
        metrics["volume_ratio_20_60"] = ratio
        metrics["volume_confirm"] = (ratio - 1) * (1 if up >= 0 else -1) if ratio else None
    return metrics


def _tilted_weights(
    regime: Optional[str],
    weights: Mapping[str, float],
    tilt: Mapping[str, Mapping[str, float]],
) -> Dict[str, float]:
    adjusted = {key: float(value) for key, value in weights.items()}
    for key, delta in tilt.get(regime or "neutral", {}).items():
        if key in adjusted:
            adjusted[key] = max(0.0, adjusted[key] + float(delta))
    total = sum(adjusted.values())
    return {key: value / total for key, value in adjusted.items()} if total else adjusted


def composite_score(
    components: Mapping[str, Any],
    regime: Optional[str],
    components_allowed: Set[str],
    weights: Mapping[str, float] = BASE_WEIGHTS,
    tilt: Mapping[str, Mapping[str, float]] = REGIME_TILT,
) -> Optional[float]:
    """Regime-tilted weighted mean, renormalized over allowed available data."""
    adjusted = _tilted_weights(regime, weights, tilt)
    available = {
        key: number
        for key in components_allowed
        if key in adjusted and (number := _finite(components.get(key))) is not None
    }
    denominator = sum(adjusted[key] for key in available)
    if not denominator:
        return None
    return sum(adjusted[key] * value for key, value in available.items()) / denominator


def cross_section_scores(
    closes: pd.DataFrame,
    volumes: Optional[pd.DataFrame],
    bench: Optional[pd.Series],
    asof: Any,
    regime: Optional[str],
    components_allowed: Set[str],
) -> pd.Series:
    """Score a universe exactly like live using data available at one as-of date."""
    raw: Dict[str, Dict[str, Any]] = {}
    for ticker in closes.columns:
        volume = volumes[ticker] if volumes is not None and ticker in volumes.columns else None
        raw[ticker] = price_components(closes[ticker], volume, bench, asof)

    metric_percentiles: Dict[str, Dict[str, float]] = {ticker: {} for ticker in closes.columns}
    for metric, (_, higher_is_better) in PRICE_METRIC_MAP.items():
        values = {
            ticker: number
            for ticker, metrics in raw.items()
            if (number := _finite(metrics.get(metric))) is not None
        }
        if len(values) < 3:
            continue
        ranked = pd.Series(values, dtype=float).rank(pct=True, ascending=higher_is_better) * 100
        for ticker, percentile in ranked.items():
            metric_percentiles[ticker][metric] = float(percentile)

    scores: Dict[str, float] = {}
    for ticker in closes.columns:
        components: Dict[str, Optional[float]] = {}
        for component in set(value[0] for value in PRICE_METRIC_MAP.values()):
            percentiles = [
                metric_percentiles[ticker][metric]
                for metric, (owner, _) in PRICE_METRIC_MAP.items()
                if owner == component and metric in metric_percentiles[ticker]
            ]
            components[component] = round(float(np.mean(percentiles)), 1) if percentiles else None
        score = composite_score(components, regime, components_allowed)
        if score is not None:
            scores[ticker] = score
    return pd.Series(scores, dtype=float).reindex(closes.columns)
