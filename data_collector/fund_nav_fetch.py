"""Official NAV + USD/THB fallbacks from free public sources (stdlib only).

Added 2026-10-29 (Phase 2 #5/#6). Used by market_data.py (data_collector venv)
and loadable by file path from portfolio_engine. No API keys, no paid sources.

NAV sources (published figures only, never modelled):
  1. SCBAM issuer fund page  -> "NAV/Unit 22.8146 at 29 Oct 2026"
  2. SETTRADE mutual-fund overview (embedded navPerUnit history)
The most recent dated value wins. Writes only NAV/price data; never holdings.
"""
from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

LOGGER = logging.getLogger("market_data.fund_nav")
PROJECT_DIR = Path(__file__).resolve().parent.parent
NAV_STORE_PATH = PROJECT_DIR / "data" / "snapshots" / "fund_nav_history.json"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

SCBAM_URLS = {
    "SCBGOLDE": "https://www.scbam.com/en/fund/foreign-investment-fund-commodity/fund-information/scbgolde",
}
SETTRADE_URL = "https://www.settrade.com/th/mutualfund/quote/{code}/overview"
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def http_get(url: str, timeout: float = 20, attempts: int = 3, base_delay: float = 5.0) -> str:
    """GET with exponential backoff on 429/5xx (honours Retry-After up to 120s)."""
    last: Optional[Exception] = None
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en;q=0.9,th;q=0.8"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code != 429 and exc.code < 500:
                raise
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            delay = min(float(retry_after), 120.0) if (retry_after or "").isdigit() else base_delay * (2 ** attempt)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = exc
            delay = base_delay * (2 ** attempt)
        if attempt < attempts - 1:
            LOGGER.warning("GET %s failed (%s); retry in %.0fs", url, last, delay)
            time.sleep(delay)
    assert last is not None
    raise last


def _text(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def fetch_scbam_nav(fund_code: str) -> Optional[dict[str, Any]]:
    url = SCBAM_URLS.get(fund_code)
    if not url:
        return None
    text = _text(http_get(url))
    m = re.search(r"NAV/Unit\s+([0-9]{1,4}\.[0-9]{2,6})\s+at\s+(\d{1,2})\s+([A-Za-z]{3})[a-z]*\s+(\d{4})", text)
    if not m:
        LOGGER.warning("SCBAM page for %s: NAV pattern not found", fund_code)
        return None
    nav = float(m.group(1))
    nav_date = date(int(m.group(4)), _MONTHS[m.group(3).lower()], int(m.group(2)))
    return {"date": nav_date.isoformat(), "nav_thb": nav, "source": "scbam_official", "source_url": url}


def fetch_settrade_nav(fund_code: str) -> Optional[dict[str, Any]]:
    url = SETTRADE_URL.format(code=fund_code)
    pts = re.findall(r'date:"([^"]+)",navPerUnit:([0-9]+\.[0-9]+)', http_get(url))
    if not pts:
        return None
    d, nav = max(((x[:10], float(y)) for x, y in pts), key=lambda t: t[0])
    return {"date": d, "nav_thb": nav, "source": "settrade_official", "source_url": url}


def fetch_official_nav(fund_code: str) -> Optional[dict[str, Any]]:
    """Most recent published NAV across sources, with date + source; None if all fail."""
    found = []
    for fn in (fetch_scbam_nav, fetch_settrade_nav):
        try:
            r = fn(fund_code)
            if r:
                found.append(r)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("%s(%s) failed: %s", fn.__name__, fund_code, exc)
    if not found:
        return None
    best = max(found, key=lambda r: r["date"])
    if date.fromisoformat(best["date"]) > date.today():
        LOGGER.warning("Ignoring future-dated NAV %s for %s", best, fund_code)
        return None
    best["cross_check"] = [{k: r[k] for k in ("source", "date", "nav_thb")} for r in found]
    return best


def record_nav(fund_code: str, entry: dict[str, Any], path: Path = NAV_STORE_PATH) -> dict[str, Any]:
    """Append/overwrite the NAV for entry['date'] in fund_nav_history.json (atomic write)."""
    history: dict[str, list] = {}
    if path.exists():
        try:
            history = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            LOGGER.warning("fund_nav_history.json unreadable; refusing to overwrite it")
            raise
    rec = {
        "date": entry["date"], "nav_thb": float(entry["nav_thb"]), "source": entry["source"],
        "source_url": entry.get("source_url"), "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    records = [r for r in history.get(fund_code, []) if r.get("date") != rec["date"]]
    records.append(rec)
    history[fund_code] = sorted(records, key=lambda r: r["date"])[-365:]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    return rec


# ---------------------------------------------------------------- USD/THB ---
def fetch_usdthb_fallback() -> Optional[dict[str, Any]]:
    """USD/THB from free no-key sources when Yahoo fails. Returns {rate, as_of, source}."""
    sources = (
        ("frankfurter_ecb", "https://api.frankfurter.app/latest?from=USD&to=THB",
         lambda d: (d["rates"]["THB"], d.get("date"))),
        ("open_er_api", "https://open.er-api.com/v6/latest/USD",
         lambda d: (d["rates"]["THB"], (d.get("time_last_update_utc") or "")[:16])),
    )
    for name, url, parse in sources:
        try:
            rate, as_of = parse(json.loads(http_get(url, timeout=15, attempts=2)))
            rate = float(rate)
            if 20.0 < rate < 60.0:  # sanity band
                return {"rate": rate, "as_of": as_of, "source": name}
            LOGGER.warning("USD/THB from %s out of sanity band: %s", name, rate)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("USD/THB fallback %s failed: %s", name, exc)
    return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(fetch_official_nav("SCBGOLDE"))
    print(fetch_usdthb_fallback())
