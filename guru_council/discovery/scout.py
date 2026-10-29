"""AI discovery scout — proposes brand-new investment ideas.

Reads a live macro snapshot, asks the specialist AI to propose new tickers that
fit the current macro/trend backdrop and a Thailand-based medium-term investor,
then validates each proposal against real market data. Excludes the user's
current holdings. Requires an LLM (returns unavailable otherwise).
"""
from __future__ import annotations

from typing import Any

from ..config import network_available
from ..core import llm
from ..core.store import get_holdings

SYSTEM = (
    "You are an investment scout for a Thailand-based, medium-term (3 months to 2 years) "
    "investor. You propose NEW ideas to research — never financial advice. Prefer liquid, "
    "accessible instruments with real data."
)


def macro_snapshot() -> dict[str, float]:
    """Small live macro snapshot to ground the scout (best-effort)."""
    if not network_available():
        return {}
    try:
        import contextlib
        import io

        import yfinance as yf  # type: ignore

        symbols = {
            "US 10Y yield": "^TNX", "US Dollar idx": "DX-Y.NYB", "Gold": "GC=F",
            "Brent": "BZ=F", "S&P 500": "^GSPC", "Nasdaq": "^IXIC",
        }
        out: dict[str, float] = {}
        with contextlib.redirect_stderr(io.StringIO()):
            for name, sym in symbols.items():
                try:
                    price = yf.Ticker(sym).fast_info.get("last_price")
                    if price:
                        out[name] = round(float(price), 2)
                except Exception:
                    pass
        return out
    except Exception:
        return {}


def _valid(ticker: str) -> bool:
    """Validate a proposed ticker has real market data (drops hallucinations)."""
    from ..extractors.live import _try_live_quote

    return _try_live_quote(ticker) is not None


def propose_ideas(scope: list[str], n: int = 8, exclude: list[str] | None = None) -> dict[str, Any]:
    if not llm.available():
        return {"available": False, "reason": "no LLM reachable (scout requires AI)", "ideas": []}

    excluded = {t.upper() for t in (exclude or [])} | {t.upper() for t in get_holdings()}
    macro = macro_snapshot()
    macro_txt = "; ".join(f"{k}: {v}" for k, v in macro.items()) or "(macro snapshot unavailable)"
    scope_txt = ", ".join(scope)

    prompt = (
        f"Current macro snapshot: {macro_txt}.\n"
        f"Search scope: {scope_txt}.\n"
        f"Already held — EXCLUDE these and avoid close substitutes: {', '.join(sorted(excluded)) or '(none)'}.\n\n"
        f"Propose {n} DIVERSE, currently-attractive NEW investment ideas that fit the macro/trend "
        "backdrop and a THB-based medium-term investor. Spread across the scope. Use valid Yahoo "
        "Finance tickers: US stocks plain (e.g. NVDA), Thai add .BK (e.g. AOT.BK), ETFs (e.g. SMH, "
        "INDA, VNM), gold (e.g. GLD). Group with a short theme. JSON only:\n"
        '{"ideas":[{"ticker":"...","theme":"...","reason":"<=20 words"}]}'
    )
    data = llm.parse_json(llm.complete(prompt, SYSTEM, max_tokens=800, temperature=0.4))
    raw = (data or {}).get("ideas", []) if isinstance(data, dict) else []

    ideas: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw:
        tk = str(item.get("ticker", "")).upper().strip()
        if not tk or tk in excluded or tk in seen:
            continue
        seen.add(tk)
        ideas.append({"ticker": tk, "theme": str(item.get("theme", "")).strip(),
                      "reason": str(item.get("reason", "")).strip()})

    valid = [i for i in ideas if _valid(i["ticker"])]
    return {"available": True, "macro": macro, "ideas": valid[:n],
            "proposed": len(ideas), "validated": len(valid)}
