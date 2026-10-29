"""Model-agnostic LLM client (pure HTTP, no SDKs required).

Picks an available provider (Anthropic / OpenAI / Ollama) from env. All providers
are called over plain HTTP via urllib, so no `openai`/`anthropic` package needs to
be installed — an API key is enough. If none is configured, callers fall back to
their non-LLM behavior.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request

from ..config import llm_provider

_notified = False


def _notice(msg: str) -> None:
    global _notified
    if not _notified:
        print(f"[guru_council] LLM note: {msg}", file=sys.stderr)
        _notified = True


def available() -> bool:
    return llm_provider() is not None


def active_model() -> tuple[str | None, str | None]:
    p = llm_provider()
    if p == "anthropic":
        return p, os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-latest")
    if p == "openai":
        return p, os.getenv("OPENAI_ADVISORY_MODEL", "gpt-4o-mini")
    if p == "ollama":
        return p, os.getenv("OLLAMA_ADVISORY_MODEL", "hermes3:8b")
    return None, None


def _post(url: str, headers: dict, payload: dict, timeout: int) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={**headers, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _openai(prompt: str, system: str, max_tokens: int, temperature: float) -> str | None:
    key = os.getenv("OPENAI_API_KEY")
    msgs = ([{"role": "system", "content": system}] if system else []) + [
        {"role": "user", "content": prompt}
    ]
    data = _post(
        os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1") + "/chat/completions",
        {"Authorization": f"Bearer {key}"},
        {"model": os.getenv("OPENAI_ADVISORY_MODEL", "gpt-4o-mini"),
         "messages": msgs, "temperature": temperature, "max_tokens": max_tokens},
        60,
    )
    return (data["choices"][0]["message"]["content"] or "").strip() or None


def _anthropic(prompt: str, system: str, max_tokens: int, temperature: float) -> str | None:
    key = os.getenv("ANTHROPIC_API_KEY")
    payload = {
        "model": os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-latest"),
        "max_tokens": max_tokens, "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        payload["system"] = system
    data = _post(
        "https://api.anthropic.com/v1/messages",
        {"x-api-key": key, "anthropic-version": "2023-06-01"},
        payload, 60,
    )
    return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip() or None


def _ollama(prompt: str, system: str, max_tokens: int, temperature: float) -> str | None:
    url = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
    model = os.getenv("OLLAMA_ADVISORY_MODEL", "hermes3:8b")
    msgs = ([{"role": "system", "content": system}] if system else []) + [
        {"role": "user", "content": prompt}
    ]
    data = _post(
        f"{url}/api/chat",
        {},
        {"model": model, "messages": msgs, "stream": False,
         "options": {"temperature": temperature, "num_predict": max_tokens}},
        int(os.getenv("OLLAMA_TIMEOUT", "60")),
    )
    return (data.get("message", {}) or {}).get("content", "").strip() or None


def complete(prompt: str, system: str = "", max_tokens: int = 600, temperature: float = 0.2) -> str | None:
    provider = llm_provider()
    try:
        if provider == "anthropic":
            return _anthropic(prompt, system, max_tokens, temperature)
        if provider == "openai":
            return _openai(prompt, system, max_tokens, temperature)
        if provider == "ollama":
            return _ollama(prompt, system, max_tokens, temperature)
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode()[:200]
        except Exception:
            pass
        _notice(f"{provider} HTTP {exc.code}: {body}")
    except Exception as exc:
        _notice(f"{provider} call failed: {exc}")
    return None


def parse_json(text: str | None) -> dict | None:
    if not text:
        return None
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
