import asyncio
import json
import os
from typing import Any

from utils.common import configure_logging, ollama_chat, parse_json_response

logger = configure_logging("ai_engine.validator")
CLAUDE_MODEL = "claude-sonnet-4-5-20251022"
OPENAI_MODEL = "gpt-4o-mini"
OLLAMA_MODEL = os.getenv("OLLAMA_ADVISORY_MODEL", "hermes3:8b")


def configured(name: str) -> bool:
    value = os.getenv(name, "")
    return bool(value and not value.startswith("your_"))


def normalize(response: dict[str, Any]) -> dict[str, Any]:
    action = str(response.get("suggested_action", "hold")).lower()
    if action not in {"buy", "sell", "hold"}:
        action = "hold"
    return {
        "agree": bool(response.get("agree", False)),
        "confidence": max(0.0, min(1.0, float(response.get("confidence", 0)))),
        "reasoning": str(response.get("reasoning", "")),
        "suggested_action": action,
    }


async def claude_validate(prompt: str) -> dict:
    from anthropic import AsyncAnthropic
    response = await AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY")).messages.create(
        model=CLAUDE_MODEL, max_tokens=500, temperature=0, messages=[{"role": "user", "content": prompt}]
    )
    return normalize(parse_json_response("".join(block.text for block in response.content if hasattr(block, "text"))))


async def openai_validate(prompt: str) -> dict:
    from openai import AsyncOpenAI
    response = await AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY")).chat.completions.create(
        model=OPENAI_MODEL, temperature=0, max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    return normalize(parse_json_response(response.choices[0].message.content or "{}"))


async def ollama_validate(prompt: str) -> dict:
    return normalize(parse_json_response(await ollama_chat(OLLAMA_MODEL, prompt, 90)))


async def validate_recommendation(
    ticker: str,
    proposed_action: str,
    rationale: str,
    sentiment_context: dict,
    confidence_threshold: float = 0.7,
) -> dict:
    primary_confidence = float(sentiment_context.get("confidence", 1.0))
    if primary_confidence < confidence_threshold:
        return {"validated": False, "reason": "low_confidence"}
    prompt = f"""You are a senior investment analyst. Review this recommendation:
Ticker: {ticker}
Proposed Action: {proposed_action}
Primary Rationale: {rationale}
Sentiment Data: {json.dumps(sentiment_context, ensure_ascii=False)}

Respond ONLY with JSON:
{{
  "agree": true,
  "confidence": 0.0,
  "reasoning": "brief explanation",
  "suggested_action": "buy"
}}"""
    validators = []
    if configured("ANTHROPIC_API_KEY"):
        validators.append((CLAUDE_MODEL, claude_validate))
    if configured("OPENAI_API_KEY"):
        validators.append((OPENAI_MODEL, openai_validate))
    validators.append((OLLAMA_MODEL, ollama_validate))
    results = await asyncio.gather(
        *(function(prompt) for _, function in validators), return_exceptions=True
    )
    details = {}
    for (model, _), result in zip(validators, results):
        if isinstance(result, Exception):
            logger.error("Validator %s failed: %s", model, result)
            details[model] = {"error": str(result)}
        else:
            details[model] = result
    actions: dict[str, list[tuple[str, dict]]] = {}
    for model, result in details.items():
        if "error" not in result:
            actions.setdefault(result["suggested_action"], []).append((model, result))
    consensus_action, agreeing = max(actions.items(), key=lambda item: len(item[1]), default=(None, []))
    validated = len(agreeing) >= 2
    agreed_models = [model for model, _ in agreeing] if validated else []
    final_confidence = (
        sum(result["confidence"] for _, result in agreeing) / len(agreeing)
        if validated else 0.0
    )
    return {
        "validated": validated,
        "consensus_action": consensus_action if validated else None,
        "final_confidence": round(final_confidence, 4),
        "validated_by": agreed_models,
        "dissenting": [model for model in details if model not in agreed_models],
        "validation_detail": details,
    }
