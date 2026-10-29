import json
import logging
import logging.handlers
import os
import re
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

ENGINE_DIR = Path(__file__).resolve().parents[1]
ADVISOR_DIR = ENGINE_DIR.parent
PROJECT_DIR = ADVISOR_DIR
load_dotenv(ENGINE_DIR / ".env")
load_dotenv(ADVISOR_DIR / ".env")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")


def strip_json_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def parse_json_response(text: str) -> dict[str, Any]:
    return json.loads(strip_json_fences(text))


async def ollama_chat(model: str, prompt: str, timeout: float = 90) -> str:
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.1},
            },
        )
        response.raise_for_status()
        return response.json()["message"]["content"]


async def ollama_embedding(text: str) -> list[float]:
    model = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{OLLAMA_URL}/api/embeddings",
            json={"model": model, "prompt": text},
        )
        response.raise_for_status()
        embedding = response.json()["embedding"]
        if len(embedding) != 768:
            raise ValueError(f"Expected 768 embedding dimensions, received {len(embedding)}")
        return embedding


def vector_literal(values: list[float]) -> str:
    return "[" + ",".join(str(float(value)) for value in values) + "]"


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
