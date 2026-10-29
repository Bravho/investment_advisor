"""Shared free market-data helpers (yfinance + no-key public APIs).

Added 2026-10-29 (Phase 3). Every value returned carries a source and an
as-of timestamp. No paid APIs. Rate limits (HTTP 429) get exponential backoff.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd

LOGGER = logging.getLogger("portfolio_engine.market_history")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
_CACHE: dict[tuple, tuple[float, Any]] = {}
_LOCK = threading.Lock()

# yfinance has no history for ^SET.BK; TDEX.BK (SET50 ETF) is the return proxy.
SET_PROXY = "TDEX.BK"


def _is_rate_limited(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "429" in text or "too many requests" in text or "rate limit" in text


def download_closes(tickers: list[str], start: Optional[str] = None, period: Optional[str] = None,
                    ttl: int = 900, attempts: int = 3) -> pd.DataFrame:
    """Daily closes (auto-adjusted) as a DataFrame[date x ticker]. Cached for `ttl` seconds."""
    import yfinance as yf

    tickers = sorted(set(t for t in tickers if t))
    key = (tuple(tickers), start, period)
    with _LOCK:
        hit = _CACHE.get(key)
        if hit and time.time() - hit[0] < ttl:
            return hit[1]
    last: Optional[Exception] = None
    for attempt in range(attempts):
        try:
            kwargs: dict[str, Any] = dict(tickers=tickers, interval="1d", auto_adjust=True,
                                          progress=False, threads=False)
            if start:
                kwargs["start"] = start
            else:
                kwargs["period"] = period or "1y"
            frame = yf.download(**kwargs)
            if frame is None or frame.empty:
                raise RuntimeError("yfinance returned no data")
            close = frame["Close"]
            if isinstance(close, pd.Series):
                close = close.to_frame(tickers[0])
            close.index = pd.to_datetime(close.index).tz_localize(None)
            with _LOCK:
                _CACHE[key] = (time.time(), close)
            return close
        except Exception as exc:  # noqa: BLE001
            last = exc
            delay = min(30 * 2 ** attempt, 240) if _is_rate_limited(exc) else 3 * 2 ** attempt
            LOGGER.warning("download_closes failed (%s); retry in %ss", exc, delay)
            if attempt < attempts - 1:
                time.sleep(delay)
    raise RuntimeError(f"download_closes failed for {len(tickers)} tickers: {last}")


def last_valid(series: pd.Series) -> tuple[Optional[float], Optional[pd.Timestamp]]:
    s = series.dropna()
    if s.empty:
        return None, None
    return float(s.iloc[-1]), s.index[-1]


def pct_change_over(series: pd.Series, sessions: int) -> Optional[float]:
    s = series.dropna()
    if len(s) <= sessions:
        return None
    prev = float(s.iloc[-1 - sessions])
    return (float(s.iloc[-1]) / prev - 1.0) * 100 if prev else None


def http_json(url: str, timeout: float = 20, attempts: int = 3, headers: Optional[dict] = None,
              opener: Any = None) -> Any:
    last: Optional[Exception] = None
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json", **(headers or {})})
            with (opener.open(req, timeout=timeout) if opener else urllib.request.urlopen(req, timeout=timeout)) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code != 429 and exc.code < 500:
                raise
            delay = min(30 * 2 ** attempt, 240) if exc.code == 429 else 3 * 2 ** attempt
        except Exception as exc:  # noqa: BLE001
            last = exc
            delay = 3 * 2 ** attempt
        if attempt < attempts - 1:
            LOGGER.warning("GET %s failed (%s); retry in %ss", url, last, delay)
            time.sleep(delay)
    raise RuntimeError(f"GET {url} failed: {last}")


def http_bytes(url: str, timeout: float = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
