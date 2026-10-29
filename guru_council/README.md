# Investment Guru Council

A model-agnostic, multi-agent investment-analysis pipeline — the redesign described in
`../REDESIGN_PLAN.md`, built as a clean package alongside the existing system.

It analyzes an investment through a **council of four field specialists**, scores their
verdicts, synthesizes a Chair view, and renders a per-investment report + a ranked
comparison scorecard with clickable multi-year ratio charts.

> The council informs; **you decide**. No auto-trading. Medium-term horizon (3m–2y).

## Why it runs anywhere
The **core pipeline depends only on the Python standard library**. With no network and
no LLM it uses a curated sample dataset and deterministic heuristic analysts, so you can
run and inspect the whole thing immediately. It automatically upgrades when extras are present:

| Capability | Without extras | With extras |
|---|---|---|
| Market data | curated sample (flagged) | live quote via `yfinance` |
| Fundamentals + history | curated sample (flagged) | live ratios + ~4yr history via `yfinance` (per-metric fallback) |
| **Scoring** | **Unscored** (marked "score unavailable") | **AI scores** (`anthropic` / `openai` / Ollama) |
| Interaction | CLI + static HTML | web app (source review + re-run) |

**Scoring is AI-owned and peer-relative.** Each specialist scores the investment
*mostly by how it ranks against same-industry competitors* (curated peer groups in
`data/council/peers.json`), ~70% relative / 30% absolute, at temperature 0. By design
there is **no offline scoring fallback** — with no LLM the verdicts are marked
`Unscored`.

**Peer advisory.** A deterministic composite ranking flags when a competitor beats
your target on specific fields or overall, and the report suggests it
("🏅 Consider: AAPL, GOOGL"). This part works without an LLM as long as peer data loads.

**Candidate discovery (funnel).** `run_batch` analyzes the names you ask for, then
auto-discovers peers that are **overall better-or-equal**, analyzes those too
(tagged `discovered`), and keeps — per investment — only the candidates whose
council conviction ≥ the target's. They appear in the scorecard's **Candidates**
column; click one for a popup with its analysis and an **Add to watchlist** button
(persists via the web app's `/api/watchlist`, or `localStorage` for the static file).
The watchlist lives in `data/council/watchlist.json`.

**Idea discovery (AI scout).** `discover` finds *brand-new* investments — not based on
what you hold. A scout agent reads a live macro snapshot (10Y yield, USD, gold, oil,
indices) and proposes new tickers across the chosen scope (US / Thai SET / ETFs / gold),
**excluding your holdings** (`data/council/holdings.json`). Each proposal is validated
against live data (hallucinated/untradeable symbols dropped), then the council analyzes
it. Ideas in the same theme peer-compare against each other, so relative scoring still
works for fresh names. Requires an LLM. Holdings to exclude are editable in
`data/council/holdings.json` (defaults: SCB.BK, PTTEP.BK, SCBGOLDE, BAFS.BK).

**Repatriation & cross-border tax (cost factor).** `tools/repatriation.py` estimates the
annual drag of getting returns back to Thailand and shows it per investment (scorecard
column, report strip + a 🇹🇭 note) and feeds it to the Cross-Asset and Risk analysts so it
influences the score (never an auto-drop). It models: source-country dividend withholding
(US 15% treaty), Thai tax on **remitted** foreign income (PIT with a foreign-tax credit;
a not-yet-enacted same/next-year exemption is toggleable), ETF domicile (flags that an
Irish-domiciled UCITS is usually more efficient than a US-domiciled ETF for a Thai holder),
and FX round-trip cost. **All rates are estimates — confirm with a tax professional.**
Tune via env: `THAI_MARGINAL_PIT` (your bracket, default 0.20), `US_TH_DIV_WHT` (0.15),
`TH_DIV_WHT` (0.10), `FX_ROUNDTRIP` (0.01), `MEDIUM_TERM_YEARS` (1.5),
`THAI_REMIT_EXEMPT=1` (assume same/next-year exemption).

Nothing hard-depends on any single model — that is the whole point of the redesign.

## Quick start
```bash
# from the investment_advisor/ project root

# DISCOVER brand-new ideas (AI scout; excludes your holdings) — needs an LLM:
python3 -m guru_council.cli discover --scope "US equities" "Thai SET" "Global ETFs" gold -n 8

# Or analyze specific names you name yourself:
python3 -m guru_council.cli analyze MSFT NVDA INDA
# -> writes data/council/site/council_site.html  (open it in a browser)

python3 -m guru_council.cli compare        # rebuild the scorecard from saved reports
python3 -m guru_council.cli sources MSFT   # show the data-source set for a ticker
python3 -m guru_council.cli serve          # web app (needs: pip install fastapi uvicorn)
```

Force modes for testing: `GURU_OFFLINE=1` (no network), `GURU_NO_LLM=1` (heuristics only).

## Pipeline (stages)
```
source set ─▶ extract ─▶ clean ─▶ tools(valuation/fees/fx) ─▶ verify(provenance)
          ─▶ council(value · macro/trends · cross-asset · risk) ─▶ chair ─▶ report
```
- **Provenance-first:** every number is a `Fact{value, source, period, retrieved_at}`. Missing data is *flagged*, never invented (`stages/verify.py`).
- **Field specialists** (`council/`): Value (Buffett-style), Macro & Tech-Trends, Cross-Asset / Commodity-Linkage, Risk & Control (Taleb-style). Each returns a scored verdict so options are rankable.
- **Chair** (`council/chair.py`): blends conviction and surfaces agreement vs disagreement — it never forces consensus.

## Layout
```
guru_council/
  config.py            # paths + capability detection (network / LLM)
  core/                # provenance, registry, store, llm, workflow
  extractors/          # base registry + live/offline (sample) extractors
  stages/              # clean, verify (QC + provenance)
  tools/               # valuation (DCF/multiple), fees, fx  (deterministic)
  council/             # 4 analysts + chair
  report/render.py     # self-contained HTML site (report + scorecard + charts)
  cli.py · app.py      # CLI and optional FastAPI web app
```

## Extending
- **New data source:** add an extractor in `extractors/`, decorate with `@register("method")`, and reference that method in a Source Set. (Methods are kept in the registry for reuse — per the design goal.)
- **Live fundamentals / history:** implement the hook in `extractors/live.py::fundamentals` to pull a real 5–10yr time series (Macrotrends / stockanalysis / Yahoo); the report/scorecard charts pick it up automatically.
- **New persona:** subclass `council/base.CouncilAnalyst` (set `lens`, `relevant`, `peer_metrics`, `guidance`) and add it to `council/__init__.COUNCIL`.
- **Edit competitor sets:** edit `data/council/peers.json` (ticker → list of peers). Used for both AI relative scoring and the peer advisory.
- **Postgres instead of JSON:** reimplement `core/store.py`.

## Status
Working: AI idea **discovery** (scout, excludes holdings), live prices, live
fundamentals (best-effort via yfinance, ~4yr history, per-metric fallback to
curated), AI **peer-relative scoring**, a **peer advisory** that flags better
competitors, a **candidate funnel** (auto-analyze better-or-equal alternatives
→ scorecard column → popup → add to watchlist), and a **repatriation/tax cost factor**
for a Thai investor (dividend WHT + Thai remittance PIT + ETF domicile + FX). Analyzed
data is stored locally under `data/council/` for comparison over time.

Not yet wired:
- A dedicated **Thai SET/AMC fundamentals + fund-NAV source** (Yahoo is sparse for `.BK`
  and absent for funds → those fall back to curated, flagged, which also limits peer
  comparison and candidate discovery for Thai names).
- The interactive **source-review front-end JS** (web API endpoints exist in `app.py`).
- The **nightly-brief hook**.
