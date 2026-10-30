"""Scheduled market-data collector and portfolio valuation snapshot service."""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from functools import wraps
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar

import pandas as pd
import psycopg2
import requests
import yfinance as yf
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
from fredapi import Fred
from psycopg2.extras import execute_values
from psycopg2.pool import ThreadedConnectionPool
from zoneinfo import ZoneInfo

BASE_DIR = Path(__file__).resolve().parent
LOGS_DIR = BASE_DIR / "logs"
SNAPSHOT_PATH = BASE_DIR / "portfolio_snapshot.json"
BACKFILL_MARKER = BASE_DIR / ".market_data_backfill_complete"
ICT = ZoneInfo("Asia/Bangkok")
UTC = timezone.utc
MACRO_INDICATORS = ("DFF", "CPIAUCSL", "VIXCLS")
COINGECKO_IDS = {"BTC-USD": "bitcoin", "ETH-USD": "ethereum"}
LOGGER = logging.getLogger("market_data")
T = TypeVar("T")

load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR.parent / ".env")


@dataclass(frozen=True)
class Settings:
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str
    alpha_vantage_api_key: str
    fred_api_key: str
    watchlist_tickers: tuple[str, ...]
    base_currency: str
    request_timeout: float = 30.0

    @classmethod
    def from_env(cls) -> "Settings":
        required = {
            "DB_HOST": os.getenv("DB_HOST", "").strip(),
            "DB_PASSWORD": os.getenv("DB_PASSWORD", "").strip(),
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
        tickers = tuple(
            dict.fromkeys(
                ticker.strip().upper()
                for ticker in os.getenv(
                    "WATCHLIST_TICKERS",
                    "ADVANC.BK,AOT.BK,BTC-USD,ETH-USD,AAPL,SPY,USDTHB=X",
                ).split(",")
                if ticker.strip()
            )
        )
        # 2026-10-30 (Phase 3 #3): crypto is excluded from the advisor; skip it so the
        # two-year backfill can complete instead of re-running (and failing) on every
        # restart. Set INCLUDE_CRYPTO=1 to collect it again.
        if os.getenv("INCLUDE_CRYPTO", "0") != "1":
            skipped = [t for t in tickers if t in COINGECKO_IDS or t.endswith(("-USD", "-USDT"))]
            if skipped:
                LOGGER.info("Skipping crypto tickers (excluded from advisor): %s", ", ".join(skipped))
            tickers = tuple(t for t in tickers if t not in skipped)
        return cls(
            db_host=required["DB_HOST"],
            db_port=int(os.getenv("DB_PORT", "5432")),
            db_name=os.getenv("DB_NAME", "investor_db"),
            db_user=os.getenv("DB_USER", "investor_app"),
            db_password=required["DB_PASSWORD"],
            alpha_vantage_api_key=os.getenv("ALPHA_VANTAGE_API_KEY", "").strip(),
            fred_api_key=os.getenv("FRED_API_KEY", "").strip(),
            watchlist_tickers=tickers,
            base_currency=os.getenv("BASE_CURRENCY", "THB").strip().upper(),
            request_timeout=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "30")),
        )


def configure_logging() -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(threadName)s | %(message)s"
    )
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    file_handler = TimedRotatingFileHandler(
        LOGS_DIR / "market_data.log",
        when="midnight",
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    LOGGER.setLevel(logging.INFO)
    LOGGER.handlers.clear()
    LOGGER.addHandler(console)
    LOGGER.addHandler(file_handler)
    LOGGER.propagate = False


def retry(attempts: int = 3, base_delay: float = 2.0) -> Callable:
    def decorator(function: Callable[..., T]) -> Callable[..., T]:
        @wraps(function)
        def wrapped(*args: Any, **kwargs: Any) -> T:
            last_error: Optional[Exception] = None
            for attempt in range(attempts):
                try:
                    return function(*args, **kwargs)
                except Exception as exc:
                    last_error = exc
                    if attempt == attempts - 1:
                        break
                    delay = base_delay * (2**attempt)
                    # 2026-10-29: rate limited (HTTP 429) -> back off much harder.
                    if "429" in str(exc) or "too many requests" in str(exc).lower() or "rate limit" in str(exc).lower():
                        delay = min(30.0 * (2**attempt), 240.0)
                    LOGGER.warning(
                        "%s failed (attempt %s/%s): %s; retrying in %.1fs",
                        function.__name__,
                        attempt + 1,
                        attempts,
                        exc,
                        delay,
                    )
                    time.sleep(delay)
            assert last_error is not None
            raise last_error

        return wrapped

    return decorator


class MarketDatabase:
    def __init__(self, settings: Settings) -> None:
        self.pool = ThreadedConnectionPool(
            minconn=1,
            maxconn=6,
            host=settings.db_host,
            port=settings.db_port,
            dbname=settings.db_name,
            user=settings.db_user,
            password=settings.db_password,
            connect_timeout=10,
            application_name="market_data_collector",
        )

    def close(self) -> None:
        self.pool.closeall()

    @retry()
    def upsert_prices(self, rows: list[tuple[Any, ...]]) -> int:
        if not rows:
            return 0
        connection = self.pool.getconn()
        try:
            with connection:
                with connection.cursor() as cursor:
                    execute_values(
                        cursor,
                        """
                        INSERT INTO market_prices (
                            ticker, price_date, open_price, high_price,
                            low_price, close_price, volume, source
                        ) VALUES %s
                        ON CONFLICT (ticker, price_date) DO UPDATE SET
                            open_price = EXCLUDED.open_price,
                            high_price = EXCLUDED.high_price,
                            low_price = EXCLUDED.low_price,
                            close_price = EXCLUDED.close_price,
                            volume = EXCLUDED.volume,
                            source = EXCLUDED.source,
                            fetched_at = NOW()
                        """,
                        rows,
                    )
            return len(rows)
        except Exception:
            connection.rollback()
            raise
        finally:
            self.pool.putconn(connection)

    def get_connection(self):
        return self.pool.getconn()

    def put_connection(self, connection: Any) -> None:
        self.pool.putconn(connection)


@retry()
def connect_database(settings: Settings) -> MarketDatabase:
    return MarketDatabase(settings)


class MarketDataCollector:
    def __init__(self, settings: Settings, database: MarketDatabase) -> None:
        self.settings = settings
        self.database = database
        self.http = requests.Session()
        self.http.headers.update(
            {"User-Agent": "InvestorAdvisorMarketCollector/1.0"}
        )
        # FRED keys are 32 lower-case alphanumerics; an invalid key only produces
        # a traceback per indicator, so treat it as "not configured" (2026-10-30).
        import re as _re
        _valid = bool(_re.fullmatch(r"[a-z0-9]{32}", settings.fred_api_key or ""))
        if settings.fred_api_key and not _valid:
            LOGGER.warning("FRED_API_KEY is set but not a valid 32-char key; macro indicators skipped until replaced")
        self.fred = Fred(api_key=settings.fred_api_key) if _valid else None

    def collect_current_prices(self) -> None:
        LOGGER.info("Collecting current prices")
        for ticker in self.settings.watchlist_tickers:
            try:
                rows = self.fetch_ticker(ticker, period="5d", current_only=True)
                self.database.upsert_prices(rows)
            except Exception:
                LOGGER.exception("Current-price collection failed for %s", ticker)
        self.save_portfolio_snapshot()

    def refresh_fund_navs(self) -> None:
        """Fetch published NAVs (SCBAM issuer page / SETTRADE) for non-exchange funds.

        Added 2026-10-29 (Phase 2 #5). Writes NAV to fund_nav_history.json and
        market_prices only -- never touches holdings units or cost.
        """
        try:
            from fund_nav_fetch import fetch_official_nav, record_nav
        except Exception:
            from data_collector.fund_nav_fetch import fetch_official_nav, record_nav
        for fund_code in sorted({i["fund_code"] for i in NON_EXCHANGE_INSTRUMENTS.values()}):
            try:
                nav = fetch_official_nav(fund_code)
                if nav is None:
                    LOGGER.warning("No published NAV found for %s (SCBAM/SETTRADE)", fund_code)
                    continue
                record_nav(fund_code, nav)
                value = float(nav["nav_thb"])
                self.database.upsert_prices([(
                    fund_code, date.fromisoformat(nav["date"]), value, value, value, value, None, nav["source"],
                )])
                LOGGER.info("NAV %s = %.4f THB as of %s (%s; cross-check %s)",
                            fund_code, value, nav["date"], nav["source"], nav.get("cross_check"))
            except Exception:
                LOGGER.exception("NAV refresh failed for %s", fund_code)

    def collect_end_of_day(self) -> None:
        LOGGER.info("Collecting end-of-day prices and macro indicators")
        self.refresh_fund_navs()
        for ticker in self.settings.watchlist_tickers:
            try:
                rows = self.fetch_ticker(ticker, period="10d")
                self.database.upsert_prices(rows)
            except Exception:
                LOGGER.exception("End-of-day collection failed for %s", ticker)
        self.collect_macro(start_date=date.today() - timedelta(days=10))
        self.save_portfolio_snapshot()

    def backfill_history(self) -> None:
        if BACKFILL_MARKER.exists():
            LOGGER.info("Historical backfill already completed")
            return
        start_date = date.today() - timedelta(days=730)
        LOGGER.info("Starting two-year historical backfill from %s", start_date)
        failures: list[str] = []
        for ticker in self.settings.watchlist_tickers:
            try:
                rows = self.fetch_ticker(ticker, start_date=start_date)
                count = self.database.upsert_prices(rows)
                LOGGER.info("Backfilled %s rows for %s", count, ticker)
            except Exception:
                failures.append(ticker)
                LOGGER.exception("Historical backfill failed for %s", ticker)
        try:
            self.collect_macro(start_date=start_date)
        except Exception:
            failures.extend(MACRO_INDICATORS)
            LOGGER.exception("Macro historical backfill failed")
        if failures:
            LOGGER.warning("Backfill incomplete; will retry next startup: %s", failures)
            return
        BACKFILL_MARKER.write_text(datetime.now(UTC).isoformat(), encoding="utf-8")
        LOGGER.info("Historical backfill complete")

    def fetch_ticker(
        self,
        ticker: str,
        period: Optional[str] = None,
        start_date: Optional[date] = None,
        current_only: bool = False,
    ) -> list[tuple[Any, ...]]:
        if ticker in COINGECKO_IDS:
            rows = self.fetch_coingecko(ticker, start_date=start_date, days=period)
        else:
            try:
                rows = self.fetch_yfinance(ticker, period=period, start_date=start_date)
            except Exception:
                if self._is_us_equity(ticker) and self.settings.alpha_vantage_api_key:
                    rows = self.fetch_alpha_vantage(ticker, start_date=start_date)
                else:
                    raise
        return rows[-1:] if current_only and rows else rows

    @retry()
    def fetch_yfinance(
        self, ticker: str, period: Optional[str], start_date: Optional[date]
    ) -> list[tuple[Any, ...]]:
        kwargs: dict[str, Any] = {
            "tickers": ticker,
            "interval": "1d",
            "auto_adjust": False,
            "progress": False,
            "threads": False,
        }
        if start_date:
            kwargs["start"] = start_date.isoformat()
        else:
            kwargs["period"] = period or "5d"
        frame = yf.download(**kwargs)
        if frame.empty:
            raise RuntimeError(f"yfinance returned no data for {ticker}")
        frame = self._flatten_yfinance_frame(frame)
        return self._frame_to_rows(ticker, frame, "yfinance")

    @retry()
    def fetch_alpha_vantage(
        self, ticker: str, start_date: Optional[date]
    ) -> list[tuple[Any, ...]]:
        response = self.http.get(
            "https://www.alphavantage.co/query",
            params={
                "function": "TIME_SERIES_DAILY",
                "symbol": ticker,
                "outputsize": "full" if start_date else "compact",
                "apikey": self.settings.alpha_vantage_api_key,
            },
            timeout=self.settings.request_timeout,
        )
        response.raise_for_status()
        payload = response.json()
        series = payload.get("Time Series (Daily)")
        if not series:
            raise RuntimeError(payload.get("Note") or payload.get("Error Message") or "No Alpha Vantage data")
        rows = []
        for day, values in sorted(series.items()):
            price_date = date.fromisoformat(day)
            if start_date and price_date < start_date:
                continue
            rows.append(
                (
                    ticker,
                    price_date,
                    values["1. open"],
                    values["2. high"],
                    values["3. low"],
                    values["4. close"],
                    int(values.get("5. volume", 0)),
                    "alpha_vantage",
                )
            )
        return rows

    @retry()
    def fetch_coingecko(
        self, ticker: str, start_date: Optional[date], days: Optional[str]
    ) -> list[tuple[Any, ...]]:
        coin_id = COINGECKO_IDS[ticker]
        if start_date:
            endpoint = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart/range"
            params = {
                "vs_currency": "usd",
                "from": int(datetime.combine(start_date, datetime.min.time(), tzinfo=UTC).timestamp()),
                "to": int(datetime.now(UTC).timestamp()),
            }
        else:
            endpoint = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
            requested_days = 5 if not days else max(1, int(days.rstrip("d")))
            params = {"vs_currency": "usd", "days": requested_days, "interval": "daily"}
        response = self.http.get(endpoint, params=params, timeout=self.settings.request_timeout)
        response.raise_for_status()
        payload = response.json()
        prices = pd.DataFrame(payload.get("prices", []), columns=["timestamp", "price"])
        volumes = pd.DataFrame(
            payload.get("total_volumes", []), columns=["timestamp", "volume"]
        )
        if prices.empty:
            raise RuntimeError(f"CoinGecko returned no data for {ticker}")
        prices["datetime"] = pd.to_datetime(prices["timestamp"], unit="ms", utc=True)
        prices["price_date"] = prices["datetime"].dt.date
        daily = prices.groupby("price_date")["price"].agg(
            open_price="first", high_price="max", low_price="min", close_price="last"
        )
        if not volumes.empty:
            volumes["datetime"] = pd.to_datetime(volumes["timestamp"], unit="ms", utc=True)
            volumes["price_date"] = volumes["datetime"].dt.date
            daily["volume"] = volumes.groupby("price_date")["volume"].last()
        else:
            daily["volume"] = 0
        return [
            (
                ticker,
                index,
                row.open_price,
                row.high_price,
                row.low_price,
                row.close_price,
                int(row.volume or 0),
                "coingecko",
            )
            for index, row in daily.iterrows()
        ]

    def collect_macro(self, start_date: date) -> None:
        if not self.fred:
            LOGGER.warning("FRED_API_KEY is not configured; skipping macro indicators")
            return
        for indicator in MACRO_INDICATORS:
            try:
                series = self.fred.get_series(indicator, observation_start=start_date)
                rows = [
                    (
                        indicator,
                        index.date(),
                        float(value),
                        float(value),
                        float(value),
                        float(value),
                        None,
                        "fred",
                    )
                    for index, value in series.dropna().items()
                ]
                self.database.upsert_prices(rows)
                LOGGER.info("Stored %s FRED observations for %s", len(rows), indicator)
            except Exception:
                LOGGER.exception("FRED collection failed for %s", indicator)

    def save_portfolio_snapshot(self) -> None:
        connection = self.database.get_connection()
        try:
            snapshot = get_current_portfolio_value(connection)
        finally:
            self.database.put_connection(connection)
        temporary_path = SNAPSHOT_PATH.with_suffix(".json.tmp")
        temporary_path.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary_path.replace(SNAPSHOT_PATH)
        LOGGER.info("Portfolio snapshot saved to %s", SNAPSHOT_PATH)

    @staticmethod
    def _is_us_equity(ticker: str) -> bool:
        return not ticker.endswith(".BK") and not ticker.endswith("=X") and "-" not in ticker

    @staticmethod
    def _flatten_yfinance_frame(frame: pd.DataFrame) -> pd.DataFrame:
        if isinstance(frame.columns, pd.MultiIndex):
            frame.columns = frame.columns.get_level_values(0)
        return frame

    @staticmethod
    def _frame_to_rows(
        ticker: str, frame: pd.DataFrame, source: str
    ) -> list[tuple[Any, ...]]:
        rows = []
        for index, row in frame.dropna(subset=["Close"]).iterrows():
            rows.append(
                (
                    ticker,
                    index.date(),
                    MarketDataCollector._number(row.get("Open")),
                    MarketDataCollector._number(row.get("High")),
                    MarketDataCollector._number(row.get("Low")),
                    MarketDataCollector._number(row.get("Close")),
                    int(MarketDataCollector._number(row.get("Volume")) or 0),
                    source,
                )
            )
        return rows

    @staticmethod
    def _number(value: Any) -> Optional[float]:
        if value is None or pd.isna(value):
            return None
        return float(value)


@retry()
def current_yfinance_price(ticker: str) -> float:
    instrument = yf.Ticker(ticker)
    try:
        last_price = instrument.fast_info.get("last_price")
        if last_price is not None and not pd.isna(last_price):
            return float(last_price)
    except Exception:
        LOGGER.debug("yfinance fast_info unavailable for %s", ticker, exc_info=True)
    history = instrument.history(period="5d", interval="1d", auto_adjust=False)
    if history.empty or history["Close"].dropna().empty:
        raise RuntimeError(f"No current price available for {ticker}")
    return float(history["Close"].dropna().iloc[-1])


# ---------------------------------------------------------------------------
# Non-exchange instrument pricing — Added by nightly agent 2026-08-08
# ---------------------------------------------------------------------------
# The holdings table contains SCB_GOLD_FUND, which is a Thai open-end mutual
# fund. It has no exchange listing and therefore no yfinance symbol, so every
# valuation cycle since the fund was added has driven it through
# current_yfinance_price(), burned all three retry attempts (2s + 4s backoff),
# logged a full traceback and then written {"error": ...} into the snapshot.
# That is ~6 seconds of guaranteed-futile work and one spurious ERROR every
# 15 minutes during market hours, which is worse than useless: it trains the
# reader to ignore ERROR lines in this log, which is precisely how the
# 2026-07-15 collector outage went unnoticed for 23 days.
#
# A fund NAV is a different KIND of quantity from an exchange price. It is
# struck once daily after close, published on a lag, and is not tradeable
# intraday. Routing it through an equity quote API was a category error, not a
# missing symbol. This resolver makes the distinction explicit and, critically,
# labels the provenance of whatever it returns so a modelled NAV can never be
# mistaken for a published one downstream.

NON_EXCHANGE_INSTRUMENTS: dict[str, dict[str, str]] = {
    # Canonical ticker (matches council / fund_nav_tracker / watchlist).
    "SCBGOLDE": {
        "fund_code": "SCBGOLDE",
        "kind": "thai_open_end_fund",
        "note": "SCB Gold Open End Fund (E-channel) — unhedged, tracks USD gold; NAV struck daily post-close.",
    },
    # ThaiESG funds bought 2026-10-30 (allotment 2026-11-02, 100,000 THB each; units pending). NAV from SETTRADE.
    "K-TNZ-ThaiESG": {
        "fund_code": "K-TNZ-ThaiESG",
        "kind": "thai_open_end_fund",
        "note": "K Thai Net Zero ThaiESG Fund (KAsset) - Thai ESG equity; ThaiESG tax wrapper, locked to 2031-11-02.",
    },
    "ES-SETESG-ThaiESG-A": {
        "fund_code": "ES-SETESG-ThaiESG-A",
        "kind": "thai_open_end_fund",
        "note": "Eastspring SET ESG Index ThaiESG Fund class A - SETESG index; ThaiESG, locked to 2031-11-02.",
    },
    "TDSThaiESG-A": {
        "fund_code": "TDSThaiESG-A",
        "kind": "thai_open_end_fund",
        "note": "TISCO Dividend Select Equity Thailand ESG Fund class A - Thai ESG equity; ThaiESG, locked to 2031-11-02.",
    },
    # Legacy alias kept so old DB rows / snapshots still resolve during migration.
    "SCB_GOLD_FUND": {
        "fund_code": "SCBGOLDE",
        "kind": "thai_open_end_fund",
        "note": "Legacy alias for SCBGOLDE — prefer SCBGOLDE in holdings.",
    },
}

# Written by portfolio_engine/fund_nav_tracker.py. Read as a plain file rather
# than imported: portfolio_engine and data_collector run in separate venvs, so a
# cross-package import would fail at runtime even though it type-checks fine.
FUND_NAV_HISTORY_PATH = BASE_DIR.parent / "data" / "snapshots" / "fund_nav_history.json"


def latest_fund_nav(fund_code: str, max_age_days: int = 7) -> Optional[dict[str, Any]]:
    """Most recent stored NAV for `fund_code`, or None if absent/too old.

    Returns a dict carrying the NAV *and its as-of date and provenance*, never a
    bare float. A NAV without its strike date is unusable: gold moves several
    percent a week and a week-old NAV quoted as current would silently misprice
    the largest non-equity sleeve in the book.
    """
    try:
        if not FUND_NAV_HISTORY_PATH.exists():
            return None
        history = json.loads(FUND_NAV_HISTORY_PATH.read_text(encoding="utf-8"))
        entries = history.get(fund_code) or []
        if not entries:
            return None
        # Accept both schemas: fund_nav_tracker writes date/nav_thb;
        # older notes used nav_date/nav_per_unit/nav.
        def _nav_date_str(e: dict) -> str:
            return str(e.get("nav_date") or e.get("date") or "")[:10]

        dated = [e for e in entries if isinstance(e, dict) and _nav_date_str(e)]
        if not dated:
            return None
        latest = max(dated, key=_nav_date_str)
        nav_date = date.fromisoformat(_nav_date_str(latest))
        age = (date.today() - nav_date).days
        if age > max_age_days:
            LOGGER.warning(
                "Stored NAV for %s is %s days old (%s) — exceeds max_age_days=%s; refusing to quote it as current",
                fund_code, age, nav_date, max_age_days,
            )
            return None
        nav = latest.get("nav_per_unit") or latest.get("nav") or latest.get("nav_thb")
        if nav is None:
            return None
        return {
            "price": float(nav),
            "as_of": nav_date.isoformat(),
            "age_days": age,
            "source": latest.get("source", "fund_nav_history"),
            "is_modelled": bool(latest.get("estimated") or latest.get("is_modelled") or str(latest.get("source","")).lower()=="estimated"),
        }
    except Exception:
        LOGGER.exception("Failed to read stored NAV for %s", fund_code)
        return None


def _observed_mark_price(ticker: str, max_age_days: int = 5) -> Optional[dict[str, Any]]:
    """Agent-observed mark for ``ticker``, shaped like a resolve_current_price result.

    Added by nightly agent 2026-08-12.

    Returns None when there is no usable mark -- including when one exists but
    is older than ``max_age_days``, because ``observed_marks.get_mark()``
    refuses stale marks outright rather than returning them with a caveat. A
    caveat in a returned dict does not get read; an absent price does.

    The returned dict carries ``observed_as_of`` (the trading session), the
    source chain, and the corroboration count, so the brief can tell Tho not
    just the number but how well attested it is and how old it is.
    """
    try:
        from observed_marks import get_mark  # local import: optional dependency
    except Exception:
        try:
            from data_collector.observed_marks import get_mark
        except Exception as exc:
            LOGGER.debug("observed_marks unavailable (%s); no fallback mark.", exc)
            return None

    try:
        mark = get_mark(ticker, max_age_days=max_age_days)
    except Exception as exc:
        LOGGER.warning("observed_marks.get_mark(%s) failed: %s", ticker, exc)
        return None
    if mark is None:
        return None

    corroboration = getattr(mark, "corroboration", None)
    return {
        "price": mark.close,
        "as_of": mark.observed_as_of,
        "as_of_basis": "session_date",
        "source": f"observed_mark[{mark.source_name}]",
        "source_url": getattr(mark, "source_url", None),
        "corroboration": corroboration,
        # is_modelled stays False: this is a published exchange print that the
        # agent read, not a number this system derived. It is stale-able, which
        # is a different failure mode from modelled, and the two must not be
        # collapsed into one flag.
        "is_modelled": False,
        "is_fallback": True,
        "error": None,
    }


def resolve_current_price(ticker: str) -> dict[str, Any]:
    """Price any holding, exchange-listed or not, WITH provenance attached.

    Always returns a dict; never raises. Shape:
        {"price": float|None, "as_of": str|None, "source": str,
         "is_modelled": bool, "error": str|None}

    `is_modelled` is the field that matters. True means the number was derived
    (e.g. a NAV inferred from spot gold) rather than published by the fund or the
    exchange, and downstream consumers must not present it to Tho as a mark
    without saying so. Silently blending modelled and published prices into one
    "current_price" column is how a portfolio ends up with a precise-looking
    valuation that nobody can trace.
    """
    instrument = NON_EXCHANGE_INSTRUMENTS.get(ticker)
    if instrument is None:
        yf_error: Optional[str] = None
        try:
            live = current_yfinance_price(ticker)
        except Exception as exc:
            live, yf_error = None, f"{type(exc).__name__}: {exc}"
        if live is not None:
            return {
                "price": live,
                "as_of": date.today().isoformat(),
                # Added by nightly agent 2026-08-12.
                # This `as_of` is the date the price was RETRIEVED, not the
                # session it belongs to -- a quote pulled on a Sunday gets
                # stamped Sunday. That conflation is the exact defect that let a
                # February BAFS price wear an August date for five runs, so it
                # is now labelled rather than silently carried. Consumers that
                # need a true session date must not trust `as_of` when
                # `as_of_basis` is "retrieval_date".
                "as_of_basis": "retrieval_date",
                "source": "yfinance",
                "is_modelled": False,
                "error": None,
            }

        # Added by nightly agent 2026-08-12.
        # yfinance gave nothing. Before reporting the holding as unpriced, fall
        # through to the agent-observed mark store. Ranked deliberately BELOW
        # the live feed and ABOVE nothing: a dated, provenanced mark from the
        # exchange beats no price at all, but must never silently outrank a live
        # quote. The mark carries its own session date, so unlike the branch
        # above its `as_of` is real.
        observed = _observed_mark_price(ticker)
        if observed is not None:
            observed["error"] = yf_error
            return observed

        return {
            "price": None, "as_of": None, "as_of_basis": None, "source": "yfinance",
            "is_modelled": False,
            "error": yf_error or f"yfinance returned no price for {ticker}.",
        }

    fund_code = instrument["fund_code"]
    stored = latest_fund_nav(fund_code)
    if stored is not None:
        return {
            "price": stored["price"],
            "as_of": stored["as_of"],
            "source": stored["source"],
            "is_modelled": stored["is_modelled"],
            "error": None,
        }

    # No usable stored NAV. Do NOT fall through to an equity quote API — that is
    # the original category error. Return an explicit, typed miss so the snapshot
    # records WHY the sleeve is unpriced rather than an opaque RuntimeError.
    return {
        "price": None,
        "as_of": None,
        "source": f"fund_nav_history[{fund_code}]",
        "is_modelled": False,
        "error": (
            f"No NAV within tolerance for {fund_code}. This instrument has no exchange "
            "listing and is intentionally NOT routed to yfinance. Populate it by running "
            "portfolio_engine/fund_nav_tracker.run_nightly_nav_snapshot()."
        ),
    }


def usdthb_with_fallback(conn: Any = None) -> tuple[Optional[float], str]:
    """USD/THB: Yahoo first, then free no-key APIs (ECB via frankfurter, open.er-api),
    then the latest stored USDTHB=X row if <= 3 days old. Added 2026-10-29 (Phase 2 #6).
    Returns (rate, source); rate None only if every source failed.
    """
    try:
        return current_yfinance_price("USDTHB=X"), "yfinance"
    except Exception as exc:
        LOGGER.warning("USD/THB from yfinance failed (%s); trying free fallbacks", exc)
    try:
        try:
            from fund_nav_fetch import fetch_usdthb_fallback
        except Exception:
            from data_collector.fund_nav_fetch import fetch_usdthb_fallback
        fb = fetch_usdthb_fallback()
        if fb:
            return fb["rate"], f"{fb['source']} (as of {fb['as_of']})"
    except Exception:
        LOGGER.exception("USD/THB free fallback failed")
    if conn is not None:
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT close_price, price_date FROM market_prices WHERE ticker = 'USDTHB=X' "
                    "AND price_date >= CURRENT_DATE - 3 ORDER BY price_date DESC LIMIT 1"
                )
                row = cursor.fetchone()
            if row:
                return float(row[0]), f"db_last_close ({row[1]})"
        except Exception:
            LOGGER.exception("USD/THB DB fallback failed")
    LOGGER.error("USD/THB unavailable from every source")
    return None, "unavailable"


def _fund_nav_on(fund_code: str, day: date) -> Optional[dict[str, Any]]:
    """Stored published NAV struck exactly on `day` (fund_nav_history.json), else None."""
    try:
        history = json.loads(FUND_NAV_HISTORY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None
    for e in history.get(fund_code) or []:
        if str(e.get("date")) == day.isoformat():
            return e
    return None


def _value_pending_fund(ticker: str, attr: dict[str, Any]) -> dict[str, Any]:
    """Value a fund whose units are not confirmed yet (added 2026-10-30).

    Never guesses units into the DB. Until a NAV struck on the allotment date is known
    (attr.allotment_nav, or the published NAV for purchase_date) the position is carried at the
    amount invested. Afterwards: amount x NAV_now / NAV_allotment (fees ignored), labelled estimated.
    """
    amount = float(attr.get("amount_invested_thb") or 0)
    purchase = attr.get("purchase_date")
    nav_now = latest_fund_nav(ticker)
    alloc_nav = float(attr["allotment_nav"]) if attr.get("allotment_nav") else None
    alloc_src = "holding_attributes.allotment_nav" if alloc_nav else None
    if alloc_nav is None and purchase is not None:
        e = _fund_nav_on(ticker, purchase)
        if e:
            alloc_nav, alloc_src = float(e["nav_thb"]), f"published NAV {e['date']} ({e.get('source')})"
    if alloc_nav and nav_now:
        est_units = amount / alloc_nav
        value = est_units * float(nav_now["price"])
        basis = (f"estimated: {amount:,.0f} THB x NAV {float(nav_now['price']):.4f} / allotment NAV {alloc_nav:.4f} "
                 f"({alloc_src}); units pending confirmation")
    else:
        est_units = None
        value = amount
        basis = (f"carried at amount invested {amount:,.0f} THB - allotment {purchase} NAV not known yet; "
                 "units pending confirmation")
    return {
        "current_price": round(float(nav_now["price"]), 6) if nav_now else None,
        "market_value_thb": round(value, 2),
        "cost_value_thb": round(amount, 2),
        "pnl_thb": round(value - amount, 2),
        "pnl_pct": round((value - amount) / amount * 100, 2) if amount else 0.0,
        "price_as_of": nav_now.get("as_of") if nav_now else None,
        "price_source": nav_now.get("source") if nav_now else None,
        "is_modelled": True,
        "is_estimated": True,
        "estimated_units": round(est_units, 4) if est_units else None,
        "allotment_nav": alloc_nav,
        "valuation_basis": basis,
        "units_status": "pending",
        "tax_wrapper": attr.get("tax_wrapper"),
        "purchase_date": str(purchase) if purchase else None,
        "lock_until": str(attr["lock_until"]) if attr.get("lock_until") else None,
        "amount_invested_thb": amount,
    }


def get_current_portfolio_value(conn: Any) -> dict[str, Any]:
    """Return holdings valuation in THB using current yfinance prices."""
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT ticker, name, asset_class, exchange, quantity,
                   avg_cost_price, currency
            FROM holdings
            ORDER BY ticker
            """
        )
        columns = [description.name for description in cursor.description]
        holdings = [dict(zip(columns, row)) for row in cursor.fetchall()]

    usdthb, usdthb_source = usdthb_with_fallback(conn)
    result: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "base_currency": "THB",
        "usdthb_rate": usdthb,
        "usdthb_source": usdthb_source,
        "holdings": {},
        "total_market_value_thb": 0.0,
        "total_pnl_thb": 0.0,
    }
    # Added by nightly agent 2026-08-08: track sleeves that could NOT be priced.
    # Previously an unpriced holding was written as {"error": ...} and then simply
    # omitted from total_market_value_thb, so the total silently described a
    # SMALLER portfolio than Tho actually owns — and every weight and
    # concentration flag derived from that total was correspondingly overstated
    # for the sleeves that did price. A partial valuation must announce itself.
    result["unpriced_holdings"] = []
    result["valuation_complete"] = True

    # Added 2026-10-30: tax wrapper / lock / pending-units attributes (holding_attributes, local investor_db).
    attrs: dict[str, dict[str, Any]] = {}
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT ticker, tax_wrapper, purchase_date, lock_until, amount_invested_thb, units_status, allotment_nav "
                "FROM holding_attributes"
            )
            cols = [d.name for d in cursor.description]
            attrs = {r[0]: dict(zip(cols, r)) for r in cursor.fetchall()}
    except Exception:  # table absent -> behave as before
        conn.rollback()
        attrs = {}

    for holding in holdings:
        ticker = holding["ticker"]
        attr = attrs.get(ticker)
        if attr and attr.get("units_status") == "pending":
            try:
                result["holdings"][ticker] = _value_pending_fund(ticker, attr)
                result["total_market_value_thb"] += result["holdings"][ticker]["market_value_thb"]
                result["total_pnl_thb"] += result["holdings"][ticker]["pnl_thb"]
            except Exception as exc:
                LOGGER.exception("Pending-fund valuation failed for %s", ticker)
                result["holdings"][ticker] = {"error": str(exc)}
                result["unpriced_holdings"].append(ticker)
                result["valuation_complete"] = False
            continue
        try:
            resolved = resolve_current_price(ticker)
            if resolved["price"] is None:
                raise RuntimeError(resolved["error"] or f"No price available for {ticker}")
            current_price = float(resolved["price"])
            quantity = float(holding["quantity"] or Decimal("0"))
            avg_cost = float(holding["avg_cost_price"] or Decimal("0"))
            is_usd = str(holding.get("currency", "")).upper() == "USD"
            if is_usd and usdthb is None:
                raise RuntimeError("USD/THB unavailable from all sources; cannot value USD holding")
            conversion = usdthb if is_usd else 1.0
            market_value_thb = current_price * quantity * conversion
            cost_value_thb = avg_cost * quantity * conversion
            pnl_thb = market_value_thb - cost_value_thb
            pnl_pct = (pnl_thb / cost_value_thb * 100) if cost_value_thb else 0.0
            result["holdings"][ticker] = {
                "current_price": round(current_price, 6),
                "market_value_thb": round(market_value_thb, 2),
                "pnl_thb": round(pnl_thb, 2),
                "pnl_pct": round(pnl_pct, 2),
                # Provenance — added 2026-08-08. A modelled NAV and a published
                # exchange close must never be indistinguishable in the output.
                "price_as_of": resolved.get("as_of"),
                "price_source": resolved.get("source"),
                "is_modelled": resolved.get("is_modelled", False),
            }
            result["total_market_value_thb"] += market_value_thb
            result["total_pnl_thb"] += pnl_thb
        except Exception as exc:
            LOGGER.exception("Portfolio valuation failed for %s", ticker)
            result["holdings"][ticker] = {"error": str(exc)}
            # Added by nightly agent 2026-08-08 — see note above the loop.
            result["unpriced_holdings"].append(ticker)
            result["valuation_complete"] = False
    result["total_market_value_thb"] = round(result["total_market_value_thb"], 2)
    result["total_pnl_thb"] = round(result["total_pnl_thb"], 2)
    # Added by nightly agent 2026-08-08: make a partial valuation self-describing,
    # so no consumer can compute a weight off an incomplete total without seeing why.
    if not result["valuation_complete"]:
        result["total_value_caveat"] = (
            f"PARTIAL VALUATION — {len(result['unpriced_holdings'])} holding(s) could not be "
            f"priced ({', '.join(result['unpriced_holdings'])}). total_market_value_thb "
            "EXCLUDES them and therefore understates the portfolio; any weight or "
            "concentration figure derived from this total is overstated for the priced "
            "sleeves. Do not use for rebalancing until complete."
        )
        LOGGER.warning(result["total_value_caveat"])
    return result


def guarded_job(name: str, function: Callable[[], None]) -> Callable[[], None]:
    def run() -> None:
        try:
            function()
        except Exception:
            LOGGER.exception("Scheduled job failed: %s", name)

    return run


def build_scheduler(collector: MarketDataCollector) -> BackgroundScheduler:
    scheduler = BackgroundScheduler(
        timezone=ICT,
        job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 300},
    )
    scheduler.add_job(
        guarded_job("intraday prices", collector.collect_current_prices),
        "cron",
        day_of_week="mon-fri",
        hour="9-16",
        minute="*/15",
        id="intraday_prices",
    )
    scheduler.add_job(
        guarded_job("17:00 prices", collector.collect_current_prices),
        "cron",
        day_of_week="mon-fri",
        hour=17,
        minute=0,
        id="market_close_prices",
    )
    scheduler.add_job(
        guarded_job("fund NAV refresh", collector.refresh_fund_navs),
        "cron",
        hour="8,12,20",
        minute=10,
        id="fund_nav_refresh",
    )
    scheduler.add_job(
        guarded_job("end-of-day prices", collector.collect_end_of_day),
        "cron",
        hour=18,
        minute=30,
        id="end_of_day",
    )
    return scheduler


def main() -> int:
    configure_logging()
    try:
        settings = Settings.from_env()
        database = connect_database(settings)
    except Exception:
        LOGGER.exception("Market collector initialization failed")
        return 1

    collector = MarketDataCollector(settings, database)
    scheduler = build_scheduler(collector)
    shutdown_event = threading.Event()

    def request_shutdown(signum: int, frame: Any) -> None:
        del frame
        LOGGER.info("Shutdown requested by signal %s", signum)
        shutdown_event.set()

    signal.signal(signal.SIGINT, request_shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, request_shutdown)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, request_shutdown)

    try:
        collector.backfill_history()
        guarded_job("startup fund NAV refresh", collector.refresh_fund_navs)()
        scheduler.start()
        LOGGER.info(
            "Market collector started in ICT timezone; watching %s",
            ", ".join(settings.watchlist_tickers),
        )
        shutdown_event.wait()
    except KeyboardInterrupt:
        LOGGER.info("Shutdown requested by keyboard interrupt")
    finally:
        LOGGER.info("Stopping market collector")
        if scheduler.running:
            scheduler.shutdown(wait=True)
        database.close()
        LOGGER.info("Market collector stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
