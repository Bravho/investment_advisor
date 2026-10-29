"""Optional FastAPI web app: interactive source review, run, report, compare.

Run:  python -m guru_council.cli serve   (or: uvicorn guru_council.app:app)
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from .core import llm, store
from .core.registry import default_source_set
from .core.workflow import discover, run_analysis
from .report.render import render_site

app = FastAPI(title="Investment Guru Council", version="0.1.0")

# Allow the React dashboard (Vite dev server on :3999) to call this API directly
# in addition to going through the Vite proxy. Model-agnostic, read-only API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3999",
        "http://127.0.0.1:3999",
        "http://0.0.0.0:3999",
    ],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1|0\.0\.0\.0|192\.168\.\d+\.\d+):\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)

DEFAULT_SCOPE = ["US equities", "Thai SET", "Global ETFs / funds", "gold"]


def _llm_info() -> dict[str, Any]:
    provider, model = llm.active_model()
    return {"provider": provider, "model": model, "available": llm.available()}


def _findings_summary(reports: dict[str, Any]) -> dict[str, Any]:
    """Distill raw council reports into a review-friendly findings summary:
    top ideas (ranked by conviction), peer advisories, and repatriation drag.
    """
    top_ideas: list[dict[str, Any]] = []
    peer_advisories: list[dict[str, Any]] = []
    repatriation: list[dict[str, Any]] = []

    for r in reports.values():
        inv = r.get("investment", {})
        chair = r.get("chair", {})
        ticker = inv.get("ticker", "")
        name = inv.get("name") or ticker
        unscored = chair.get("overall_stance") == "Unscored"

        top_ideas.append({
            "ticker": ticker,
            "name": name,
            "theme": r.get("idea_theme", ""),
            "reason": r.get("idea_reason", ""),
            "stance": chair.get("overall_stance", "Unscored"),
            "label": chair.get("overall_label", ""),
            "conviction": 0 if unscored else chair.get("blended_conviction", 0),
            "unscored": unscored,
            "net": chair.get("net", ""),
            "llm_used": bool(r.get("llm_used")),
            "flags": inv.get("flags", []),
            "price_display": inv.get("price_display", ""),
            "change_pct": inv.get("change_pct"),
        })

        pa = r.get("peer_advice") or {}
        for b in pa.get("better_overall", []):
            peer_advisories.append({
                "from": ticker,
                "from_name": name,
                "consider": b.get("ticker", ""),
                "score": b.get("score"),
            })

        repat = (r.get("tools") or {}).get("repatriation") or {}
        drag = repat.get("total_drag_pct")
        if isinstance(drag, (int, float)) and drag > 0:
            repatriation.append({
                "ticker": ticker,
                "name": name,
                "origin": repat.get("origin", ""),
                "total_drag_pct": drag,
                "fx_drag_pct": repat.get("fx_drag_pct"),
                "dividend_drag_pct": repat.get("dividend_drag_pct"),
                "high": drag >= 2.0,
                "suggestion": repat.get("suggestion", ""),
            })

    top_ideas.sort(key=lambda x: (x["unscored"], -x["conviction"]))
    repatriation.sort(key=lambda x: -(x["total_drag_pct"] or 0))

    scored = [t["conviction"] for t in top_ideas if not t["unscored"]]
    stats = {
        "ideas_found": len(top_ideas),
        "scored": len(scored),
        "top_conviction": max(scored) if scored else 0,
        "avg_conviction": round(sum(scored) / len(scored)) if scored else 0,
        "high_drag_count": sum(1 for x in repatriation if x["high"]),
    }
    return {
        "stats": stats,
        "top_ideas": top_ideas,
        "peer_advisories": peer_advisories,
        "repatriation": repatriation,
    }


@app.get("/", response_class=HTMLResponse)
def home() -> HTMLResponse:
    return HTMLResponse(render_site(store.all_reports()))


@app.get("/api/llm")
def llm_status() -> JSONResponse:
    """Which model is active (model-agnostic). Used by the dashboard badge."""
    return JSONResponse(_llm_info())


@app.post("/api/discover")
def discover_endpoint(payload: dict[str, Any] = Body(default={})) -> JSONResponse:
    """Run the guru_council discovery pipeline from data sources (excludes holdings).

    Body: {"scope": ["US equities", ...], "n": 8}
    Returns: {available, llm, macro, ideas, findings, reports}
    """
    scope = payload.get("scope") or DEFAULT_SCOPE
    n = int(payload.get("n") or 8)
    res = discover(scope, n=n)
    reports = res.get("reports", {})
    return JSONResponse({
        "available": res.get("available", False),
        "reason": res.get("reason", ""),
        "llm": _llm_info(),
        "macro": res.get("macro", {}),
        "ideas": res.get("ideas", []),
        "findings": _findings_summary(reports),
        "reports": reports,
    })


@app.get("/api/sources/{ticker}")
def get_sources(ticker: str) -> JSONResponse:
    sources = store.load_source_set(ticker) or default_source_set(ticker)
    return JSONResponse(sources)


@app.post("/api/run/{ticker}")
def run(ticker: str, payload: dict[str, Any] = Body(default={})) -> JSONResponse:
    """Run (or re-run) analysis. Optional body: {"sources": [...]} to override."""
    sources = payload.get("sources")
    report = run_analysis(ticker, sources=sources)
    return JSONResponse(report)


@app.get("/api/report/{ticker}")
def get_report(ticker: str, refresh: bool = False) -> JSONResponse:
    report = None if refresh else store.load_report(ticker)
    if report is None:
        report = run_analysis(ticker)
    return JSONResponse(report)


@app.get("/api/reports")
def list_reports() -> JSONResponse:
    return JSONResponse(store.all_reports())


@app.get("/api/watchlist")
def watchlist() -> JSONResponse:
    return JSONResponse(store.get_watchlist())


@app.post("/api/watchlist/add/{ticker}")
def watchlist_add(ticker: str) -> JSONResponse:
    return JSONResponse({"watchlist": store.add_watchlist(ticker)})
