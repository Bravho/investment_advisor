"""Configuration, paths, and capability detection (network / LLM)."""
from __future__ import annotations

import os
import urllib.error
import urllib.request
from pathlib import Path

try:  # optional: load a .env if python-dotenv is installed
    from dotenv import load_dotenv

    load_dotenv()
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:  # pragma: no cover - dotenv is optional
    pass

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data" / "council"
REPORTS_DIR = DATA_DIR / "reports"
SOURCESETS_DIR = DATA_DIR / "source_sets"
SITE_DIR = DATA_DIR / "site"  # rendered HTML output

for _d in (REPORTS_DIR, SOURCESETS_DIR, SITE_DIR):
    _d.mkdir(parents=True, exist_ok=True)

BASE_CURRENCY = os.getenv("BASE_CURRENCY", "THB")
USD_THB = float(os.getenv("USD_THB_RATE", "32.9"))


def configured(name: str) -> bool:
    """True if an env var is set to a real (non-placeholder) value."""
    value = os.getenv(name, "")
    return bool(value and not value.startswith("your_"))


_network: bool | None = None


def network_available() -> bool:
    """Probe outbound network once; cached for the process."""
    global _network
    if _network is None:
        if os.getenv("GURU_OFFLINE") == "1":
            _network = False
            return _network
        # Any HTTP response (even an error status) means the network is up.
        probes = (
            "https://query1.finance.yahoo.com/v8/finance/chart/AAPL?range=1d&interval=1d",
            "https://www.google.com",
        )
        _network = False
        for url in probes:
            try:
                urllib.request.urlopen(url, timeout=5)
                _network = True
                break
            except urllib.error.HTTPError:
                _network = True  # reached a server -> network works
                break
            except Exception:
                continue
    return _network


def llm_provider() -> str | None:
    """Pick an LLM provider from env, in preference order. None => no-LLM mode.

    All providers are called over plain HTTP (see core/llm.py), so only an API key
    (or, for Ollama, a URL) is needed — no SDK install required. Set
    GURU_LLM_PROVIDER to force one of: anthropic | openai | ollama.
    """
    if os.getenv("GURU_NO_LLM") == "1":
        return None
    forced = os.getenv("GURU_LLM_PROVIDER")
    if forced:
        return forced
    if configured("ANTHROPIC_API_KEY"):
        return "anthropic"
    if configured("OPENAI_API_KEY"):
        return "openai"
    if os.getenv("OLLAMA_URL") or os.getenv("OLLAMA_ADVISORY_MODEL"):
        return "ollama"
    return None
