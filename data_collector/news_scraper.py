"""Cross-platform continuous financial-news collector for PostgreSQL."""

from __future__ import annotations

import logging
import os
import random
import signal
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import wraps
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, TypeVar
from urllib.parse import quote, urljoin, urlparse

import feedparser
import httpx
import psycopg2
from apscheduler.schedulers.background import BackgroundScheduler
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from fake_useragent import UserAgent
from newspaper import Article
from psycopg2.pool import ThreadedConnectionPool

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR.parent / ".env")

REUTERS_RSS = "https://feeds.reuters.com/reuters/businessNews"
REUTERS_RSS_FALLBACK = (
    "https://news.google.com/rss/search"
    "?q=site%3Areuters.com%2Fbusiness&hl=en-US&gl=US&ceid=US:en"
)
BANGKOK_POST_RSS = "https://www.bangkokpost.com/rss/data/business.xml"
YAHOO_RSS = (
    "https://feeds.finance.yahoo.com/rss/2.0/headline"
    "?s={ticker}&region=US&lang=en-US"
)
INVESTING_NEWS_URL = "https://www.investing.com/news/stock-market-news"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) "
    "Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) "
    "AppleWebKit/605.1.15 Version/17.4 Mobile/15E148 Safari/604.1",
]

LOGGER = logging.getLogger("news_scraper")
T = TypeVar("T")


@dataclass(frozen=True)
class Settings:
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str
    watchlist_tickers: tuple[str, ...]
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
            ticker.strip()
            for ticker in os.getenv(
                "WATCHLIST_TICKERS",
                "ADVANC.BK,AOT.BK,BTC-USD,ETH-USD,AAPL,SPY",
            ).split(",")
            if ticker.strip()
        )
        if not tickers:
            raise ValueError("WATCHLIST_TICKERS is empty")
        if required["DB_HOST"].upper() in {"YOUR_MAC_MINI_IP", "[YOUR_MAC_MINI_IP]"}:
            raise ValueError("DB_HOST still contains a placeholder value")
        return cls(
            db_host=required["DB_HOST"],
            db_port=int(os.getenv("DB_PORT", "5432")),
            db_name=os.getenv("DB_NAME", "investor_db"),
            db_user=os.getenv("DB_USER", "investor_app"),
            db_password=required["DB_PASSWORD"],
            watchlist_tickers=tickers,
            request_timeout=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "30")),
        )


def configure_logging() -> None:
    logs_dir = BASE_DIR / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(threadName)s | %(message)s"
    )

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    file_handler = TimedRotatingFileHandler(
        logs_dir / "scraper.log",
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    LOGGER.setLevel(logging.INFO)
    LOGGER.handlers.clear()
    LOGGER.addHandler(console)
    LOGGER.addHandler(file_handler)
    LOGGER.propagate = False


def retry(
    attempts: int = 3, base_delay: float = 2.0
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Retry a synchronous operation using 2^n-second backoff."""

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


class UserAgentRotator:
    def __init__(self) -> None:
        try:
            self.fake_user_agent: Optional[UserAgent] = UserAgent()
        except Exception as exc:
            LOGGER.warning("fake-useragent initialization failed: %s", exc)
            self.fake_user_agent = None

    def get(self) -> str:
        if self.fake_user_agent:
            try:
                return self.fake_user_agent.random
            except Exception:
                pass
        return random.choice(USER_AGENTS)


class NewsDatabase:
    def __init__(self, settings: Settings) -> None:
        self.pool = ThreadedConnectionPool(
            minconn=1,
            maxconn=8,
            host=settings.db_host,
            port=settings.db_port,
            dbname=settings.db_name,
            user=settings.db_user,
            password=settings.db_password,
            connect_timeout=10,
            application_name="financial_news_scraper",
        )

    def close(self) -> None:
        self.pool.closeall()

    @retry()
    def url_exists(self, url: str) -> bool:
        connection = self.pool.getconn()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 FROM news_articles WHERE url = %s LIMIT 1", (url,))
                return cursor.fetchone() is not None
        except Exception:
            connection.rollback()
            raise
        finally:
            self.pool.putconn(connection)

    @retry()
    def insert_article(self, article: dict[str, Any]) -> bool:
        connection = self.pool.getconn()
        try:
            with connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO news_articles (
                            source, title, content, url, author,
                            published_at, language, is_processed
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, FALSE)
                        ON CONFLICT (url) DO NOTHING
                        RETURNING id
                        """,
                        (
                            article["source"],
                            article["title"],
                            article["content"],
                            article["url"],
                            article["author"],
                            article["published_at"],
                            article["language"],
                        ),
                    )
                    return cursor.fetchone() is not None
        except Exception:
            connection.rollback()
            raise
        finally:
            self.pool.putconn(connection)


@retry()
def connect_database(settings: Settings) -> NewsDatabase:
    return NewsDatabase(settings)


class NewsScraper:
    def __init__(self, settings: Settings, database: NewsDatabase) -> None:
        self.settings = settings
        self.database = database
        self.user_agents = UserAgentRotator()

    def headers(self) -> dict[str, str]:
        return {
            "User-Agent": self.user_agents.get(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,th;q=0.7",
            "Cache-Control": "no-cache",
        }

    @retry()
    def fetch(self, url: str) -> httpx.Response:
        with httpx.Client(
            timeout=self.settings.request_timeout,
            follow_redirects=True,
            headers=self.headers(),
        ) as client:
            response = client.get(url)
            if response.status_code == 429:
                delay = float(response.headers.get("Retry-After", "5"))
                LOGGER.warning("Rate limited by %s; waiting %.1fs", urlparse(url).netloc, delay)
                time.sleep(delay)
            response.raise_for_status()
            return response

    def scrape_reuters(self) -> None:
        try:
            self.scrape_rss(REUTERS_RSS, "Reuters")
        except Exception as exc:
            LOGGER.warning("Legacy Reuters RSS unavailable; using fallback feed: %s", exc)
            self.scrape_rss(REUTERS_RSS_FALLBACK, "Reuters")

    def scrape_bangkok_post(self) -> None:
        self.scrape_rss(BANGKOK_POST_RSS, "Bangkok Post")

    def scrape_yahoo_watchlist(self) -> None:
        delay = float(os.getenv("YAHOO_REQUEST_DELAY_SECONDS", "3"))
        for index, ticker in enumerate(self.settings.watchlist_tickers):
            try:
                url = YAHOO_RSS.format(ticker=quote(ticker, safe=".-"))
                self.scrape_rss(url, f"Yahoo Finance ({ticker})")
            except Exception:
                LOGGER.exception("Yahoo Finance scrape failed for %s", ticker)
            if index < len(self.settings.watchlist_tickers) - 1:
                time.sleep(delay)

    def scrape_rss(self, feed_url: str, source: str) -> None:
        LOGGER.info("Scraping RSS source: %s", source)
        response = self.fetch(feed_url)
        feed = feedparser.parse(response.content)
        if feed.bozo and not feed.entries:
            raise RuntimeError(f"Could not parse {source} RSS: {feed.bozo_exception}")
        LOGGER.info("%s feed returned %s entries", source, len(feed.entries))

        inserted = 0
        for entry in feed.entries:
            url = self._normalize_url(entry.get("link", ""))
            if not url:
                continue
            candidate = {
                "source": source,
                "title": entry.get("title", "").strip(),
                "url": url,
                "author": entry.get("author", ""),
                "published_at": self._feed_datetime(entry),
                "fallback_content": entry.get("summary", ""),
            }
            inserted += int(self.process_candidate(candidate))
        LOGGER.info("%s complete: %s new article(s)", source, inserted)

    def scrape_investing(self) -> None:
        LOGGER.info("Scraping Investing.com stock-market news")
        response = self.fetch(INVESTING_NEWS_URL)
        soup = BeautifulSoup(response.text, "html.parser")
        candidates: list[dict[str, Any]] = []
        seen: set[str] = set()

        for link in soup.select('a[href*="/news/stock-market-news/"]'):
            url = self._normalize_url(urljoin(INVESTING_NEWS_URL, link.get("href", "")))
            title = link.get_text(" ", strip=True)
            if not url or url in seen or len(title) < 15:
                continue
            seen.add(url)
            candidates.append(
                {
                    "source": "Investing.com",
                    "title": title,
                    "url": url,
                    "author": "",
                    "published_at": None,
                    "fallback_content": "",
                }
            )

        inserted = sum(int(self.process_candidate(candidate)) for candidate in candidates)
        LOGGER.info("Investing.com complete: %s new article(s)", inserted)

    def process_candidate(self, candidate: dict[str, Any]) -> bool:
        url = candidate["url"]
        try:
            if self.database.url_exists(url):
                LOGGER.debug("Skipping existing URL: %s", url)
                return False

            try:
                extracted = self.extract_full_article(url)
            except Exception as exc:
                LOGGER.warning("Full-text extraction failed for %s: %s", url, exc)
                extracted = {
                    "title": "",
                    "content": "",
                    "author": "",
                    "published_at": None,
                }
            extracted_title = extracted["title"]
            if extracted_title.lower() in {"google news", "news"}:
                extracted_title = ""
            title = extracted_title or candidate["title"]
            content = extracted["content"] or self._plain_text(
                candidate.get("fallback_content", "")
            )
            if not title or not content:
                LOGGER.warning("Skipping article without title/content: %s", url)
                return False

            article = {
                "source": candidate["source"],
                "title": title,
                "content": content,
                "url": url,
                "author": (extracted["author"] or candidate.get("author") or "")[:200]
                or None,
                "published_at": extracted["published_at"]
                or candidate.get("published_at"),
                "language": self.detect_language(f"{title}\n{content}"),
            }
            inserted = self.database.insert_article(article)
            if inserted:
                LOGGER.info("Inserted [%s] %s", article["source"], article["title"])
            return inserted
        except Exception:
            LOGGER.exception("Failed processing article: %s", url)
            return False

    @retry()
    def extract_full_article(self, url: str) -> dict[str, Any]:
        response = self.fetch(url)
        article = Article(url=url)
        article.set_html(response.text)
        article.parse()
        authors = ", ".join(article.authors) if article.authors else ""
        return {
            "title": (article.title or "").strip(),
            "content": (article.text or "").strip(),
            "author": authors[:200],
            "published_at": self._ensure_timezone(article.publish_date),
        }

    @staticmethod
    def detect_language(text: str) -> str:
        thai_characters = sum("\u0e00" <= character <= "\u0e7f" for character in text)
        non_space_characters = max(1, sum(not character.isspace() for character in text))
        return "th" if thai_characters / non_space_characters >= 0.10 else "en"

    @staticmethod
    def _plain_text(value: str) -> str:
        return BeautifulSoup(value or "", "html.parser").get_text(" ", strip=True)

    @staticmethod
    def _normalize_url(url: str) -> str:
        url = (url or "").strip()
        if not url:
            return ""
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return ""
        return parsed._replace(fragment="").geturl()

    @staticmethod
    def _feed_datetime(entry: Any) -> Optional[datetime]:
        value = entry.get("published_parsed") or entry.get("updated_parsed")
        if not value:
            return None
        try:
            return datetime(*value[:6], tzinfo=timezone.utc)
        except (TypeError, ValueError):
            LOGGER.warning("Could not parse RSS published date: %r", value)
            return None

    @staticmethod
    def _ensure_timezone(value: Optional[datetime]) -> Optional[datetime]:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


def guarded_job(name: str, function: Callable[[], None]) -> Callable[[], None]:
    def run() -> None:
        try:
            function()
        except Exception:
            LOGGER.exception("Scheduled job failed: %s", name)

    return run


def build_scheduler(scraper: NewsScraper) -> BackgroundScheduler:
    scheduler = BackgroundScheduler(
        timezone="UTC",
        job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 300},
    )
    now = datetime.now(timezone.utc)
    scheduler.add_job(
        guarded_job("Reuters", scraper.scrape_reuters),
        "interval",
        minutes=30,
        next_run_time=now,
        id="reuters",
    )
    scheduler.add_job(
        guarded_job("Investing.com", scraper.scrape_investing),
        "interval",
        minutes=30,
        next_run_time=now,
        id="investing",
    )
    scheduler.add_job(
        guarded_job("Yahoo Finance watchlist", scraper.scrape_yahoo_watchlist),
        "interval",
        minutes=15,
        next_run_time=now,
        id="yahoo_watchlist",
    )
    scheduler.add_job(
        guarded_job("Bangkok Post", scraper.scrape_bangkok_post),
        "interval",
        minutes=60,
        next_run_time=now,
        id="bangkok_post",
    )
    return scheduler


def register_shutdown_handlers(shutdown_event: threading.Event) -> None:
    """Register the shutdown signals available on the current operating system."""

    def request_shutdown(signum: int, frame: Any) -> None:
        del frame
        LOGGER.info("Shutdown requested by signal %s", signum)
        shutdown_event.set()

    signal_names = ("SIGINT", "SIGTERM", "SIGHUP", "SIGBREAK")
    for signal_name in signal_names:
        shutdown_signal = getattr(signal, signal_name, None)
        if shutdown_signal is not None:
            signal.signal(shutdown_signal, request_shutdown)


def main() -> int:
    configure_logging()
    try:
        settings = Settings.from_env()
        database = connect_database(settings)
    except Exception:
        LOGGER.exception("Scraper initialization failed")
        return 1

    scraper = NewsScraper(settings, database)
    scheduler = build_scheduler(scraper)
    shutdown_event = threading.Event()
    register_shutdown_handlers(shutdown_event)

    try:
        scheduler.start()
        LOGGER.info(
            "News scraper started; watching %s",
            ", ".join(settings.watchlist_tickers),
        )
        shutdown_event.wait()
    except KeyboardInterrupt:
        LOGGER.info("Shutdown requested by keyboard interrupt")
    finally:
        LOGGER.info("Stopping scheduler and database pool")
        if scheduler.running:
            scheduler.shutdown(wait=True)
        database.close()
        LOGGER.info("News scraper stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
