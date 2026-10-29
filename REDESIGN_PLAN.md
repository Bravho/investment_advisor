# Investment Guru Council — Redesign Plan (rev. 2)

**Status:** Plan only (no code yet). Revised 2026-06-20.
**Decision inputs:**
- Full redesign · model-agnostic (reuse `model_router` + pgvector; not tied to Gemini/Opal/NotebookLM).
- **Council = four field-specialist analyst agents** (see §5.1), not famous-person personas. Personas are pluggable so they can be added/swapped later.
- **Interactive data-source review** in a web display: user sees current raw-data sources, can edit/add/remove them, and clicks **Run again** to re-analyze. Each source's extraction method is kept and reusable.
- **Scored verdicts** (0–100 conviction) so investments are rankable.
- Output = on-demand per-investment report **and** a nightly-brief section, plus a **ranked scorecard** comparison view.

---

## 1. The lesson's core idea (what we are imitating)

The video's real message is *not* "use Opal/Gemini." It is a coding/architecture discipline:

> A good answer = **Data + Context + Workflow + Human judgment** — not a clever prompt.

Principles: (1) data quality before intelligence, (2) context engineering not prompt-stuffing, (3) workflow over one long prompt, (4) **multiple specialist perspectives that may disagree**, (5) **the human decides**.

The current project already embodies #1–#3 partially. The redesign's big moves are: a **council of field specialists** (#4) replacing the consensus validator, and a **human-in-the-loop web display** for both the *inputs* (data sources) and the *outputs* (per-investment report + comparison).

---

## 2. What exists today and what each piece becomes

Full redesign does **not** mean rewrite-from-zero. Most modules survive as **tools** or **extractors** in the new pipeline.

| Today | Role in redesign | Action |
|---|---|---|
| `data_collector/` (news_scraper, market_data, orchestrator) | Stage 1 extractors, registered by source type | **Port** behind a common extractor interface |
| `ai_engine/sentiment_pipeline`, `macro_aggregator` | Stage 1/2 enrichment + Macro analyst inputs | **Port** as tools |
| `ai_engine/embedding_pipeline` + pgvector | Knowledge Base (RAG) | **Repurpose** — this *is* your NotebookLM |
| `ai_engine/risk_scorer` (currency/fed/gold flags) | Risk analyst tools | **Port** as deterministic tools |
| `portfolio_engine/oil_scenario`, `fund_nav_tracker`, `dividend_tracker`, `earnings_tracker` | Cross-asset & valuation tools | **Port** as deterministic tools |
| `portfolio_engine/fee_analyzer` | Fee/FX cost tool (a scorecard column) | **Port** |
| `ai_engine/multi_llm_validator` (consensus) | Replaced concept | **Retire as gatekeeper**, reuse plumbing for the Council |
| `model_router` | Model-agnostic LLM access | **Keep** — central to "not Gemini-specific" |
| `context_builder` | Context assembly | **Absorb** into context/provenance layer |
| `main.py` (FastAPI chat + dashboard) | Web app entry | **Rebuild** into the 3-screen web display (§6) |
| `db.py` + schema | Persistence | **Extend** with provenance, source-sets, council verdicts |
| Nightly agent + `brief_generator` + DEVLOG | Stage 6 report + scheduler | **Keep**, add a Council section |

---

## 3. Target architecture (with human-in-the-loop on both ends)

```
            ┌──────────────────────────────────────────────────────────────┐
 INPUT      │  user picks an investment (ticker / fund / crypto)            │
            └───────────────────────────┬──────────────────────────────────┘
                                        ▼
 SOURCE     ╔══════════════ WEB DISPLAY: DATA-SOURCE REVIEW ════════════════╗
 REVIEW     ║ system proposes a Source Set for the investment:              ║
 (human)    ║   [✓] Yahoo Finance quote   url…   method: yahoo_quote        ║
            ║   [✓] SET company page      url…   method: set_scrape         ║
            ║   [✓] FRED macro series     url…   method: fred_api           ║
            ║   [✓] News RSS              url…   method: rss                ║
            ║   [ ] (add your own URL → pick/auto-detect extractor method)  ║
            ║   user edits / adds / removes / toggles  →  [ RUN ANALYSIS ]  ║
            ╚═══════════════════════════════╤══════════════════════════════╝
                                        ▼   (re-runnable: change sources, run again)
 STAGE 1   EXTRACTION   ── run ONLY approved sources, via their registered
                            extractor method; each datum → Fact{value, source_url,
                            method, period, retrieved_at}
                                        ▼
 STAGE 2   CLEANING     ── validate · normalize units/currency · reconcile · dedupe
                                        ▼
 STAGE 3   VERIFICATION ── QC rules + provenance: every number traceable;
                            missing data flagged, never invented
                                        ▼
            ┌──────── shared services (called by analyst agents) ───────────┐
            │ KNOWLEDGE BASE (pgvector RAG): valuation, macro, cross-asset, │
            │   risk frameworks, Thai fee/tax                               │
            │ QUANT TOOLS (deterministic): DCF/FCF, fees, FX, oil/sensitivity│
            │   correlations, dividend yield, risk flags                    │
            │ WEB SEARCH (live confirmation)                                │
            └───────────────────────────┬──────────────────────────────────┘
                                        ▼
 STAGE 4   COUNCIL  ── four FIELD SPECIALISTS in parallel (§5.1), each on the
                       SAME verified Facts; each returns a SCORED verdict
                       {stance, conviction 0–100, confidence, thesis, metrics, sources}
                                        ▼
 STAGE 5   SYNTHESIS ── "Chair": blend scores (optionally weighted), surface
                        agreement vs disagreement, frame for a human decision
                                        ▼
 STAGE 6   WEB DISPLAY: OUTPUTS
              (a) PER-INVESTMENT REPORT  — analyst cards + chair verdict + sources
              (b) RANKED SCORECARD       — compare all analyzed investments
              (c) NIGHTLY-BRIEF section   — council block for watchlist holdings
            persisted to DB + data/ for historical comparison
```

---

## 4. Proposed module layout

```
investment_advisor/
├── core/
│   ├── workflow.py          # NEW: stage runner (re-runnable per source-set change)
│   ├── provenance.py        # NEW: Fact{value, source_url, method, period, retrieved_at}
│   ├── source_registry.py   # NEW: investment → Source Set; extractor-method registry
│   ├── model_router.py      # KEEP
│   └── db.py                # EXTEND: provenance · source_sets · council_verdicts
├── stage1_extract/          # pluggable extractors, registered by method name
│   ├── base.py              # Extractor protocol → List[Fact]; self-registers
│   ├── yahoo_quote.py · set_scrape.py · fred_api.py · rss.py · generic_url.py
│   └── fundamentals.py      # NEW: SBC, capex split, buybacks
├── stage2_clean/  ·  stage3_verify/   # clean + QC/provenance (qc_rules.py)
├── knowledge/               # the "NotebookLM": curated corpus + pgvector retrieve
├── tools/                   # deterministic, agent-callable
│   ├── valuation.py (DCF/FCF) · fees.py · fx.py · oil.py · correlations.py · risk.py
├── council/                 # NEW heart of the redesign (pluggable specialists)
│   ├── analyst.py           # base agent: prompt + KB + tools + verified Facts + score
│   ├── value.py · macro_trends.py · cross_asset.py · risk_control.py
│   └── chair.py             # Stage 5 synthesis / debate summary
├── report/
│   ├── per_investment.py    # report model → HTML
│   └── scorecard.py · brief_section.py
├── app/                     # the web display (3 screens, §6)
│   ├── api.py               # endpoints: source review, run, report, compare
│   └── views/               # source_review · report · comparison templates
└── data/                    # snapshots · market_intel · reports · source_sets
```

---

## 5. The council, revised

### 5.1 Four field-specialist analyst agents
All four read the **same verified Fact set** and call the **same quant tools** — they differ in *lens*, not data. Each returns a **scored** structured verdict.

1. **Value Analyst** *(Buffett-style)* — business quality, moat, ROE/ROIC, free cash flow, intrinsic value via `valuation.py` (DCF/FCF), margin of safety. Core question: *is price below conservative intrinsic value?*
2. **Macro & Technology-Trends Analyst** — rates/Fed/BOT, inflation, growth cycle, and the sector/technology backdrop (e.g. AI-capex/semis cycle, tourism for SET, structural EM themes). Core question: *does the macro and trend backdrop push this asset up or down over 3m–2y?*
3. **Cross-Asset / Commodity-Linkage Analyst** — inter-market relationships and pricing linkages: oil↔PTTEP, gold↔real yields/USD, USD/THB FX, rates↔banks (SCB), correlations and hedges. Uses `oil.py`, `fx.py`, `correlations.py`. Core question: *which external prices/economic factors actually drive this asset, and where do they point now?*
4. **Risk & Control Analyst** *(Taleb-style)* — tail risk, fragility, hidden/black-swan exposure, drawdown, concentration, currency risk, and medium-term position sizing. Uses `risk.py`. Core question: *what can go badly wrong, how fragile is the thesis, and how should size be controlled?*

**Verdict schema (each analyst):**
```
{ stance: Buy | Accumulate | Wait | Pass | Caution,
  conviction: 0–100,          # enables ranking on the scorecard
  confidence: 0–100,          # how solid the underlying data was
  thesis: short text,
  metrics_used: [Fact refs],  # only verified Facts
  sources: [urls],
  key_risks: [text] }
```

DCF/valuation stays a **shared deterministic tool** (mainly the Value Analyst) rather than a separate persona — easy to promote a Damodaran-style valuation persona later since personas are pluggable.

### 5.4 Historical ratio trends (clickable charts)
Every financial ratio/metric on the report and scorecard is clickable and opens a **5–10 year trend chart**. This needs:
- A **historical time-series extractor** (Macrotrends / stockanalysis.com / Yahoo fundamentals) registered like any other source, returning annual (or quarterly) ratio history with provenance.
- A small **`metric_history` time-series table** (ticker · metric · period · value · source) so charts load instantly and stay reproducible — not re-scraped on every view.
- Reused across screens: snapshot tiles, scorecard cells, and the nightly brief can all render the same cached series (a sparkline inline, the full chart on click).

### 5.2 The Chair (Stage 5 synthesis)
The Chair tabulates the four scored verdicts, computes a **blended conviction** (equal-weight by default; weights configurable later, e.g. risk-averse → Risk analyst heavier), and writes a short synthesis that **explicitly states where the analysts agree and disagree** and **what new evidence would flip the call**. It never averages disagreement into mush and never auto-trades.

---

## 6. The web display — three screens

### Screen A — Data-Source Review (input, human-in-the-loop)
For a chosen investment, the system resolves a **Source Set** from `source_registry.py` and shows a reviewable list. Each row: source name, URL (editable), **extraction method** (the registered extractor, kept for reuse), data type, on/off toggle, last-fetched status. The user can **edit a URL, add a new source** (choose an extractor method or auto-detect from the URL), remove, or toggle a source, then click **Run analysis**. Changing sources and clicking **Run again** re-executes the whole pipeline on the new set. Source Sets are **saved per investment** so they persist and improve over time; extractor methods live in the registry so each "how to fetch this source" is retained and reusable for future investments.

### Screen B — Per-Investment Report (output)
One page per analyzed investment:
- **Header:** investment, asset class, current price/NAV, currency, as-of timestamp, medium-term (3m–2y) framing.
- **Selectable options list:** a left-hand list of analyzed investments (verdict chip + conviction) to switch the report.
- **Verified data snapshot:** key Facts, each with a clickable source link (provenance). **Each ratio is itself clickable → opens a 5–10yr trend chart** of that metric (see §5.4).
- **Four analyst cards:** stance label + **conviction bar (0–100)** + confidence + thesis + metrics used + sources + key risks — one card per specialist.
- **Chair synthesis:** overall verdict, blended conviction, agreement/disagreement map, "what would change the call."
- **Cost & risk strip:** total fee/cost drag, FX cost/risk, top risk flag.
- Footer: human-decides note + Thai risk disclaimer. Saved to `data/reports/` + DB for history.

### Screen C — Ranked Scorecard (comparison)
A sortable table comparing every analyzed investment so options can be ranked side by side:

| Investment | Asset class | Overall verdict | **Conviction** | Value | Macro/Trend | Cross-asset | Risk | Div yield | Fee/cost | FX risk | Top risk flag |
|---|---|---|---|---|---|---|---|---|---|---|---|
| (row per investment, sortable by any column; default sort = Conviction desc) | | | | | | | | | | | |

Rows are built from the saved per-investment reports (so the comparison is reproducible and consistent), each cell links back to that investment's report, and per-analyst columns let the user see at a glance where the specialists agree or split across options. Filterable by asset class; re-running any investment updates its row.

### Nightly-brief section
The nightly agent runs the council for each watchlist holding (medium-term lens) and injects a compact Council block + the holding's scorecard row into the brief and DEVLOG, alongside your existing fee/FX/oil context.

---

## 7. Build sequence (phased; each phase ends with a verification gate)

- **Phase 0 — Scaffold.** `core/workflow.py`, `provenance.py`, `source_registry.py`, DB migrations (provenance · source_sets · council_verdicts). *Gate:* empty pipeline runs end-to-end on a stub.
- **Phase 1 — Data spine + extractor registry.** Port collectors into self-registering extractors; Source Set resolution; Stage 2 clean + Stage 3 verify with QC rules. *Gate:* pull one SET + one US name; every figure has provenance + method; QC flags fire on bad input.
- **Phase 2 — Source-review screen.** Web Screen A: list/edit/add/remove sources, save Source Set, **Run / Re-run**. *Gate:* edit a URL, add a source, re-run, confirm only approved sources are used and methods are reused.
- **Phase 3 — Knowledge + tools.** Curate KB corpus (value/macro/cross-asset/risk/Thai-fees); port fee/FX/oil/risk/correlations; build `valuation.py`. *Gate:* unit-test DCF & fee math; KB retrieval returns relevant chunks.
- **Phase 4 — Council + Chair.** Build `analyst.py` base + four specialists + Chair with scored verdicts. *Gate:* run on MSFT + one SET holding; verdicts cite only verified Facts/tools; scores populate.
- **Phase 5 — Output screens.** Screen B (per-investment report) + Screen C (ranked scorecard) + nightly-brief section. *Gate:* generate all three; every number links to a source; scorecard sorts/ranks correctly.
- **Phase 6 — Hardening.** Backtest hookup (do council calls age well?), regression tests, model-router fallback across providers. *Gate:* full nightly run green; provenance spot-checked on 3 reports.

---

## 8. Risks / decisions to watch

- **Don't lose working logic.** Port the subtle, already-verified math (fee breakeven, oil elasticity, Fed/gold flags) — treat porting as part of the redesign, not optional.
- **Fundamentals data source.** SBC, capex split, and buybacks aren't in your current collectors. Decide the source (Yahoo fundamentals vs SEC/Macrotrends vs a data API) early — it drives council quality and is the first new extractor.
- **Conviction scoring needs an anchor.** Define what 0–100 means per analyst (rubric) so scores are comparable across investments and over time; otherwise the scorecard ranking is noise.
- **KB makes or breaks the specialists.** A "Value analyst" with a thin knowledge base is a costume. Budget real effort on `knowledge/corpus/`.
- **Cost/latency.** Four analysts + tools + RAG per investment is many calls. Route specialists to cheaper local models via `model_router`; reserve a stronger model for the Chair.
- **Source review must be safe.** User-added URLs are arbitrary; validate/allowlist and fetch through the controlled extractor layer, not raw.

---

## 9. Out of scope (explicit)

No auto-trading, no order placement, no moving money — the system advises; you decide. Stays medium-term (3m–2y), not a trading bot.
