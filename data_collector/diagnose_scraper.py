"""Sequential diagnostics for the financial news scraper."""

from __future__ import annotations

import json
import os
import sys
import traceback
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import quote
from uuid import uuid4

import feedparser
import psycopg2
from dotenv import load_dotenv

import news_scraper

BASE_DIR = Path(__file__).resolve().parent
PARENT_ENV = BASE_DIR.parent / ".env"
LOCAL_ENV = BASE_DIR / ".env"
TEST_URL_PREFIX = "https://diagnostic.local/news-scraper/"
results: dict[str, tuple[bool, str]] = {}
feeds: dict[str, Any] = {}
settings: Optional[news_scraper.Settings] = None


def heading(text: str) -> None:
    print(f"\n{'=' * 72}\n{text}\n{'=' * 72}")


def record(name: str, passed: bool, detail: str) -> bool:
    results[name] = (passed, detail)
    print(f"{'PASS' if passed else 'FAIL'} — {name}: {detail}")
    return passed


def exact_error(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"


def connect():
    assert settings is not None
    return psycopg2.connect(
        host=settings.db_host,
        port=settings.db_port,
        dbname=settings.db_name,
        user=settings.db_user,
        password=settings.db_password,
        connect_timeout=10,
        application_name="news_scraper_diagnostic",
    )


def check_environment() -> bool:
    global settings
    heading("CHECK 1 — Environment")
    load_dotenv(LOCAL_ENV)
    load_dotenv(PARENT_ENV)
    print(f"Local .env:  {LOCAL_ENV} ({'exists' if LOCAL_ENV.exists() else 'not present'})")
    print(f"Shared .env: {PARENT_ENV} ({'exists' if PARENT_ENV.exists() else 'not present'})")
    try:
        settings = news_scraper.Settings.from_env()
        values = {
            "DB_HOST": settings.db_host,
            "DB_PORT": settings.db_port,
            "DB_NAME": settings.db_name,
            "DB_USER": settings.db_user,
            "DB_PASSWORD": "********" if settings.db_password else "<missing>",
            "WATCHLIST_TICKERS": ",".join(settings.watchlist_tickers),
            "REQUEST_TIMEOUT_SECONDS": settings.request_timeout,
        }
        for key, value in values.items():
            print(f"{key}={value}")
        placeholder = settings.db_host.upper() in {
            "YOUR_MAC_MINI_IP", "[YOUR_MAC_MINI_IP]", "192.168.1.100"
        }
        if placeholder or not settings.watchlist_tickers:
            return record("Environment", False, "DB_HOST is a placeholder or watchlist is empty")
        return record("Environment", True, "shared configuration loaded correctly")
    except Exception as exc:
        return record("Environment", False, exact_error(exc))


def check_database_connection() -> bool:
    heading("CHECK 2 — Database Connection")
    if settings is None:
        return record("Database Connection", False, "environment check did not produce settings")
    test_url = TEST_URL_PREFIX + str(uuid4())
    try:
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_database(), current_user")
                print(f"Connected to database/user: {cursor.fetchone()}")
                cursor.execute(
                    """
                    INSERT INTO news_articles (
                        source, title, content, url, author, published_at,
                        fetched_at, language, is_processed
                    ) VALUES (%s, %s, %s, %s, %s, NOW(), NOW(), %s, FALSE)
                    RETURNING id
                    """,
                    ("Diagnostic", "Connection test", "Temporary test row", test_url, "diagnostic", "en"),
                )
                article_id = cursor.fetchone()[0]
                cursor.execute("DELETE FROM news_articles WHERE id = %s", (article_id,))
        return record("Database Connection", True, "connected; INSERT and DELETE succeeded")
    except Exception as exc:
        return record("Database Connection", False, exact_error(exc))


def fetch_feed(name: str, url: str) -> Any:
    assert settings is not None
    rotator = news_scraper.UserAgentRotator()
    import httpx

    with httpx.Client(
        timeout=settings.request_timeout,
        follow_redirects=True,
        headers={"User-Agent": rotator.get()},
    ) as client:
        response = client.get(url)
        response.raise_for_status()
    feed = feedparser.parse(response.content)
    feeds[name] = feed
    return feed


def check_rss_feeds() -> bool:
    heading("CHECK 3 — RSS Feeds")
    if settings is None:
        return record("RSS Feeds", False, "environment check did not produce settings")
    sources = {"Bangkok Post": [news_scraper.BANGKOK_POST_RSS]}
    sources["Reuters"] = [news_scraper.REUTERS_RSS, news_scraper.REUTERS_RSS_FALLBACK]
    failures = []
    for name, urls in sources.items():
        source_errors = []
        for index, url in enumerate(urls):
            try:
                feed = fetch_feed(name, url)
                title = feed.feed.get("title", "<no title>")
                count = len(feed.entries)
                first = feed.entries[0].get("title", "<no title>") if count else "<none>"
                label = "fallback" if index else "primary"
                print(f"{name} ({label}): title={title!r}, entries={count}, first={first!r}")
                if count:
                    break
                source_errors.append(f"{label}: zero entries")
            except Exception as exc:
                source_errors.append(exact_error(exc))
                print(f"{name} URL {index + 1}: FAIL — {exact_error(exc)}")
        else:
            failures.append(f"{name}: {'; '.join(source_errors)}")
    return record(
        "RSS Feeds",
        not failures,
        "all RSS feeds returned entries" if not failures else "; ".join(failures),
    )


def first_entry() -> tuple[str, Any]:
    preferred = feeds.get("Reuters")
    if preferred and preferred.entries:
        return "Reuters", preferred.entries[0]
    for name, feed in feeds.items():
        if feed.entries:
            return name, feed.entries[0]
    assert settings is not None
    for ticker in settings.watchlist_tickers:
        feed = fetch_feed(
            f"Yahoo Finance ({ticker})",
            news_scraper.YAHOO_RSS.format(ticker=quote(ticker, safe=".-")),
        )
        if feed.entries:
            return f"Yahoo Finance ({ticker})", feed.entries[0]
    raise RuntimeError("No RSS entry is available for diagnostics")


def diagnostic_scraper() -> tuple[news_scraper.NewsScraper, news_scraper.NewsDatabase]:
    assert settings is not None
    database = news_scraper.NewsDatabase(settings)
    return news_scraper.NewsScraper(settings, database), database


def check_article_extraction() -> bool:
    heading("CHECK 4 — Article Extraction")
    if settings is None:
        return record("Article Extraction", False, "environment check did not produce settings")
    database = None
    try:
        source, entry = first_entry()
        url = entry.get("link", "")
        scraper, database = diagnostic_scraper()
        extracted = {}
        extraction_error = None
        try:
            extracted = scraper.extract_full_article(url)
        except Exception as exc:
            extraction_error = exact_error(exc)
        summary = scraper._plain_text(entry.get("summary", ""))
        print(f"Source/URL: {source} / {url}")
        print(f"newspaper3k title length: {len(extracted.get('title', ''))}")
        print(f"newspaper3k content length: {len(extracted.get('content', ''))}")
        print(f"RSS fallback summary length: {len(summary)}")
        if extraction_error:
            print(f"newspaper3k error: {extraction_error}")
        passed = bool(extracted.get("content") or summary)
        return record("Article Extraction", passed, "full text or RSS fallback is usable" if passed else "both extraction paths are empty")
    except Exception as exc:
        return record("Article Extraction", False, exact_error(exc))
    finally:
        if database:
            database.close()


def check_yahoo_finance() -> bool:
    heading("CHECK 5 — Yahoo Finance per ticker")
    if settings is None:
        return record("Yahoo Finance", False, "environment check did not produce settings")
    total = 0
    errors = []
    for ticker in settings.watchlist_tickers:
        try:
            url = news_scraper.YAHOO_RSS.format(ticker=quote(ticker, safe=".-"))
            feed = fetch_feed(f"Yahoo Finance ({ticker})", url)
            count = len(feed.entries)
            total += count
            print(f"{ticker}: {count} articles")
        except Exception as exc:
            errors.append(f"{ticker}: {exact_error(exc)}")
            print(f"{ticker}: FAIL — {exact_error(exc)}")
        time.sleep(float(os.getenv("YAHOO_REQUEST_DELAY_SECONDS", "3")))
    detail = f"{total} total articles across watchlist"
    if errors:
        detail += f"; source errors: {len(errors)}"
    return record("Yahoo Finance", total > 0, detail)


def check_actual_database_insert() -> bool:
    heading("CHECK 6 — Database INSERT")
    if settings is None:
        return record("Database INSERT", False, "environment check did not produce settings")
    database = None
    inserted_url = TEST_URL_PREFIX + "actual-" + str(uuid4())
    try:
        source, entry = first_entry()
        scraper, database = diagnostic_scraper()
        summary = scraper._plain_text(entry.get("summary", "")) or "Diagnostic RSS fallback content"
        article = {
            "source": source,
            "title": entry.get("title", "Diagnostic article"),
            "content": summary,
            "url": inserted_url,
            "author": entry.get("author") or None,
            "published_at": scraper._feed_datetime(entry),
            "language": scraper.detect_language(f"{entry.get('title', '')}\n{summary}"),
        }
        inserted = database.insert_article(article)
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id, title FROM news_articles WHERE url = %s", (inserted_url,))
                row = cursor.fetchone()
                cursor.execute("DELETE FROM news_articles WHERE url = %s", (inserted_url,))
        print(f"Actual insert returned: {inserted}; verified row: {row}")
        return record("Database INSERT", bool(inserted and row), "actual NewsDatabase.insert_article logic succeeded")
    except Exception as exc:
        return record("Database INSERT", False, exact_error(exc))
    finally:
        if database:
            database.close()


class SchedulerProbe:
    def scrape_reuters(self): pass
    def scrape_investing(self): pass
    def scrape_yahoo_watchlist(self): pass
    def scrape_bangkok_post(self): pass


def check_scheduler_jobs() -> bool:
    heading("CHECK 7 — Scheduler Jobs")
    scheduler = None
    try:
        scheduler = news_scraper.build_scheduler(SchedulerProbe())
        scheduler.start(paused=True)
        jobs = scheduler.get_jobs()
        for job in jobs:
            print(f"{job.id}: trigger={job.trigger}, next_run_time={job.next_run_time}")
        return record("Scheduler Jobs", bool(jobs), f"{len(jobs)} jobs registered")
    except Exception as exc:
        return record("Scheduler Jobs", False, exact_error(exc))
    finally:
        if scheduler and scheduler.running:
            scheduler.shutdown(wait=False)


def print_summary() -> None:
    heading("SUMMARY")
    for name, (passed, detail) in results.items():
        print(f"{'✅ PASS' if passed else '❌ FAIL'} — {name}: {detail}")
    heading("DIAGNOSIS")
    failures = {name: detail for name, (passed, detail) in results.items() if not passed}
    if not failures:
        print("All diagnostics passed. The scraper can fetch and insert articles.")
        print("A normal run may report 0 new articles when every feed URL already exists in the database.")
        return
    explanations = {
        "Environment": "Fix investment_advisor/.env values, especially DB_HOST and WATCHLIST_TICKERS.",
        "Database Connection": "PostgreSQL credentials, network access, table permissions, or schema are preventing writes.",
        "RSS Feeds": "One or more source URLs are unavailable, retired, blocked, or returning no entries.",
        "Article Extraction": "Publishers block full-text extraction and the RSS source provides no summary fallback.",
        "Yahoo Finance": "Yahoo RSS is blocked/rate-limited or the watchlist symbols have no feed articles.",
        "Database INSERT": "The scraper's real INSERT does not match the news_articles schema or lacks permission.",
        "Scheduler Jobs": "The scraper scheduler is not registering source jobs.",
    }
    for name, detail in failures.items():
        print(f"- {name}: {explanations.get(name, detail)}")
        print(f"  Exact failure: {detail}")


def main() -> int:
    checks: list[Callable[[], bool]] = [
        check_environment,
        check_database_connection,
        check_rss_feeds,
        check_article_extraction,
        check_yahoo_finance,
        check_actual_database_insert,
        check_scheduler_jobs,
    ]
    for check in checks:
        try:
            check()
        except Exception as exc:
            record(check.__name__, False, exact_error(exc))
            traceback.print_exc()
    print_summary()
    return 0 if all(passed for passed, _ in results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
