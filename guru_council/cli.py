"""Command-line interface for the Guru Council.

Examples:
    python -m guru_council.cli analyze MSFT SCB.BK PTTEP.BK SCBGOLDE BAFS.BK
    python -m guru_council.cli compare            # rebuild the HTML site
    python -m guru_council.cli sources MSFT       # show the source set
    python -m guru_council.cli serve              # run the web app (needs fastapi)
"""
from __future__ import annotations

import argparse
import json
import sys

from .core import llm, store
from .core.registry import default_source_set
from .core.workflow import discover, run_analysis, run_batch
from .extractors.sample_data import sample_tickers
from .report.render import write_site


def _print_llm() -> None:
    prov, model = llm.active_model()
    print(f"  LLM: {prov} ({model})" if prov else "  LLM: none configured → verdicts will be Unscored")


def _summary(report: dict) -> str:
    inv = report["investment"]
    c = report["chair"]
    flags = len(inv.get("flags", []))
    mode = "LLM" if report.get("llm_used") else "no-LLM"
    unscored = c.get("overall_stance") == "Unscored"
    conv = "  —  " if unscored else f"{c['blended_conviction']:>3}/100"
    advice = ""
    pa = report.get("peer_advice") or {}
    if pa.get("available") and pa.get("better_overall"):
        advice = "  🏅 consider " + ", ".join(x["ticker"] for x in pa["better_overall"])
    return (f"  {inv['ticker']:<10} {c['overall_label']:<36} conv {conv}  [{mode}]"
            + (f"  ⚠{flags}" if flags else "") + advice)


def cmd_analyze(args: argparse.Namespace) -> None:
    tickers = args.tickers or sample_tickers()
    print(f"Analyzing {len(tickers)} investment(s) + discovering better-or-equal candidates...")
    _print_llm()
    reports = run_batch(tickers)
    for t in tickers:
        r = reports.get(t.upper())
        if r:
            print(_summary(r))
    discovered = [k for k, r in reports.items() if r.get("discovered")]
    if discovered:
        print("  ── discovered alternatives ──")
        for k in discovered:
            print(_summary(reports[k]))
    path = write_site(store.all_reports())
    print(f"\nSite written: {path}")


DEFAULT_SCOPE = ["US equities", "Thai SET", "Global ETFs / funds", "gold"]


def cmd_discover(args: argparse.Namespace) -> None:
    scope = args.scope or DEFAULT_SCOPE
    print(f"AI scout searching for new ideas across: {', '.join(scope)} (excluding your holdings)...")
    _print_llm()
    res = discover(scope, n=args.n)
    if not res.get("available"):
        print(f"Scout unavailable: {res.get('reason')}. Configure an LLM (OpenAI/Anthropic/Ollama) and retry.")
        return
    ideas = res.get("ideas", [])
    print(f"Proposed {len(ideas)} validated new ideas:\n")
    for r in res["reports"].values():
        print(_summary(r) + f"  [{r.get('idea_theme', '')}]")
    path = write_site(store.all_reports())
    print(f"\nSite written: {path}")


def cmd_compare(args: argparse.Namespace) -> None:
    reports = store.all_reports()
    if not reports:
        print("No analyzed reports yet. Run: analyze <ticker> ...")
        return
    path = write_site(reports)
    print(f"Scorecard ({len(reports)} investments) written: {path}")


def cmd_sources(args: argparse.Namespace) -> None:
    t = args.ticker.upper()
    sources = store.load_source_set(t) or default_source_set(t)
    print(json.dumps(sources, indent=2, ensure_ascii=False))


def cmd_serve(args: argparse.Namespace) -> None:
    try:
        import uvicorn
    except ImportError:
        print("fastapi/uvicorn not installed. pip install fastapi uvicorn")
        sys.exit(1)
    uvicorn.run("guru_council.app:app", host="0.0.0.0", port=args.port, reload=False)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="guru_council", description="Investment Guru Council")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("analyze", help="analyze one or more tickers")
    a.add_argument("tickers", nargs="*", help="tickers (default: sample set)")
    a.set_defaults(func=cmd_analyze)

    d = sub.add_parser("discover", help="AI-scout brand-new investment ideas (excludes holdings)")
    d.add_argument("--scope", nargs="*", help="markets/themes to search (default: US, Thai SET, ETFs, gold)")
    d.add_argument("-n", type=int, default=8, help="number of ideas")
    d.set_defaults(func=cmd_discover)

    c = sub.add_parser("compare", help="rebuild the comparison site from saved reports")
    c.set_defaults(func=cmd_compare)

    s = sub.add_parser("sources", help="show the source set for a ticker")
    s.add_argument("ticker")
    s.set_defaults(func=cmd_sources)

    sv = sub.add_parser("serve", help="run the web app")
    sv.add_argument("--port", type=int, default=8993)
    sv.set_defaults(func=cmd_serve)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
