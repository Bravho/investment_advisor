import json
import logging
import logging.handlers
import os
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
from dotenv import load_dotenv

ENGINE_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = ENGINE_DIR.parent
load_dotenv(ENGINE_DIR / ".env")
load_dotenv(PROJECT_DIR / ".env")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")


def configure_logging(name: str) -> logging.Logger:
    logs_dir = ENGINE_DIR / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    file_handler = logging.handlers.TimedRotatingFileHandler(
        logs_dir / f"{name.rsplit('.', 1)[-1]}.log",
        when="midnight",
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.setLevel(logging.INFO)
    logger.addHandler(stream)
    logger.addHandler(file_handler)
    logger.propagate = False
    return logger


def strip_json_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    return re.sub(r"\s*```$", "", text).strip()


def parse_json_response(text: str) -> dict[str, Any]:
    return json.loads(strip_json_fences(text))


def json_default(value: Any) -> Any:
    if isinstance(value, (datetime, date, UUID, Decimal)):
        return str(value)
    raise TypeError(f"Cannot JSON serialize {type(value).__name__}")


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=json_default)


def to_jsonable(value: Any) -> Any:
    return json.loads(json_dumps(value))


async def ollama_chat(model: str, prompt: str, timeout: float = 120, json_mode: bool = False) -> str:
    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0.1},
    }
    if json_mode:
        payload["format"] = "json"
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(f"{OLLAMA_URL}/api/chat", json=payload)
        response.raise_for_status()
        return response.json()["message"]["content"].strip()


def snapshot_path() -> Path:
    configured = Path(
        os.getenv("PORTFOLIO_SNAPSHOT_PATH", "data_collector/portfolio_snapshot.json")
    )
    return configured if configured.is_absolute() else PROJECT_DIR / configured


def load_snapshot() -> dict[str, Any]:
    path = snapshot_path()
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


async def latest_price(pool: Any, ticker: str) -> float:
    price = await pool.fetchval(
        "SELECT close_price FROM market_prices WHERE ticker = $1 ORDER BY price_date DESC LIMIT 1",
        ticker,
    )
    if price is not None and float(price) != 0:
        return float(price)
    # Fall back to portfolio snapshot (covers mutual-fund NAVs not in market_prices).
    snap = load_snapshot().get("holdings", {}).get(ticker) or {}
    snap_price = snap.get("current_price")
    if snap_price is not None and float(snap_price) != 0:
        return float(snap_price)
    return 0.0


async def save_recommendation(
    pool: Any,
    *,
    ticker: str,
    action: str,
    confidence: float,
    rationale: str,
    sentiment_snapshot: Any,
    price: float,
    llm_model: str,
    validated_by: Any = None,
) -> str:
    existing = await pool.fetchval(
        """
        SELECT id FROM recommendations
        WHERE ticker = $1 AND action = $2 AND rationale = $3
          AND created_at >= NOW() - INTERVAL '30 minutes'
        ORDER BY created_at DESC LIMIT 1
        """,
        ticker,
        action,
        rationale,
    )
    if existing:
        return str(existing)
    recommendation_id = await pool.fetchval(
        """
        INSERT INTO recommendations (
            ticker, action, confidence, rationale, sentiment_snapshot,
            price_at_recommendation, llm_model, validated_by
        ) VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8::text[])
        RETURNING id
        """,
        ticker,
        action,
        confidence,
        rationale,
        json_dumps(sentiment_snapshot),
        price or None,
        llm_model,
        list(validated_by or []),
    )
    return str(recommendation_id)
