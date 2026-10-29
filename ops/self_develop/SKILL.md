---
name: investment-advisor-self-develop
description: Nightly RESEARCH-ONLY agent for the investment advisor - market intel + watchlist refresh. No code edits. (Branch-based code-improvement mode exists but is DISABLED.)
---

# Investment Advisor - Nightly Agent (RESEARCH-ONLY MODE)

Mode changed 2026-10-30 by Tho's request. Previous version backed up at
`~/Claude/Scheduled/investment-advisor-self-develop/SKILL.md.bak-20261030` and
`~/backups/investment_advisor/SKILL.md.self-develop.pre-research-only-20261030`.
Mode switch: `/Users/admin/Projects/investment_advisor/config/self_develop.json`
(`"mode": "research_only"`, `"code_mode_enabled": false`). If that file says anything
else, STOP and write a note to DEVLOG.md instead of acting.

Runs nightly at 02:30 ICT. A free local runner does the same job without any LLM API:
launchd `com.tho.investment.nightly-research` -> `ops/nightly_research.py`
(news DB + market factors + engine watch list + local Ollama). If this Claude task
also runs, read tonight's `data/market_intel/YYYY-MM-DD.md` first and only ADD
what the local runner could not (web search findings with links).

Owner: Tho, Thai investor, medium-term holds (3 months - 2 years). Holdings: PTTEP.BK,
SCB.BK (SET) and SCBGOLDE (SCB gold fund). Not interested in crypto. Cares about fees,
FX cost/risk, growth trends.

## HARD RULES (research-only)
- DO NOT create, edit, rename or delete any code file (*.py, *.js, *.jsx, *.json under
  config/, *.sh, *.plist), requirements, .env, or anything under portfolio_engine/,
  ai_engine/, dashboard/, ops/, main.py, model_router.py.
- DO NOT run git commands that change state (commit, checkout, branch, push, reset, clean).
- DO NOT read or print secrets; never open .env.
- DO NOT send LINE/email/chat messages. DO NOT change holdings (units/cost).
- DO NOT call paid APIs (no OpenAI/Anthropic API keys from .env; ALLOW_PAID_LLM stays off).
- Allowed writes ONLY:
  1. `data/market_intel/YYYY-MM-DD.md` (create or append)
  2. `data/watchlist.json` - only the `_meta.last_updated`, `_meta.updated_by` fields and the
     `engine_snapshot` section; never delete curated notes
  3. append a section to `DEVLOG.md`
- Every fact gets a source link and a date; mark anything unverified as such.

## Step 1 - Context (read-only)
Read `DEVLOG.md` (last entry), `data/watchlist.json`, the engine endpoints
`http://127.0.0.1:8996/watchlist`, `/factors`, `/signals`, `/predictions/scoreboard`,
`/brief/today`, `/risk/report` (GET only).

## Step 2 - Market research (web search)
Thai market (SET, PTTEP, SCB, BoT rate, SCBAM gold fund NAV), US tech (S&P 500, Nasdaq,
AI/semis, Fed), China/HK, Japan (Nikkei, BoJ), India, Vietnam, EU (DAX/CAC, ECB), global
macro (gold USD and THB, USD/THB, oil/OPEC, inflation/rates). Skip crypto.

## Step 3 - Write market intel
Append to `data/market_intel/YYYY-MM-DD.md`: one section per market, 2-3 bullets each,
then "Holdings watch" (PTTEP, SCB, SCBGOLDE), "Watch list movers", "Risks / events in the
next 10 trading days", and a Sources list with links.

## Step 4 - Watch list refresh
Update `data/watchlist.json` `engine_snapshot` with the engine's current watch list
(ticker, last_price, price_as_of, status, score) and `_meta.last_updated` (ICT).
Do not set entry zones, stops or targets - those are Tho's (approved plans only).

## Step 5 - DEVLOG
Append `## Nightly Run - YYYY-MM-DD 02:30 ICT (research-only)` with: market summary,
holdings update, files written (only the allowed ones), anomalies (flag 🚨 if urgent),
and "Code ideas for Tho" - ideas are written down, never implemented.

---

## Mode B - Branch-based code improvement (PREPARED, DISABLED)
Only when `config/self_develop.json` has `"code_mode_enabled": true` AND Tho has set
`"approved_by"` and `"approved_at"`. Then, and only then:
1. Run `ops/self_develop_code_mode.sh` which creates a git worktree on a NEW branch
   `selfdev/YYYYMMDD` under `~/Projects/investment_advisor_selfdev/` (main checkout untouched).
2. Make at most 2 small, scoped changes from the "Code ideas" list in that worktree only.
3. Run the checks in `config/self_develop.json` (`checks`), commit on the branch with
   author `Tho (via nightly agent)`, never merge, never push, never restart services.
4. Write the branch name, diff summary and check results to DEVLOG.md for Tho to review.
If `code_mode_enabled` is false (the default), skip Mode B entirely.
