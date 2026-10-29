# Plan: unify the Python virtual environments (NOT migrated yet)

_Written 2026-10-30 (ICT). Status: proposal only. Nothing has been changed._

## Today
| venv | Used by | Size | Packages |
|---|---|---|---|
| `investment_advisor/venv` | portfolio engine 8996, advisor 8991, guru council 8993, nightly research | 203 MB | 83 |
| `investment_advisor/ai_engine/venv` | AI engine 8997 (`engine_runner.py`) | 106 MB | 39 |
| `investment_advisor/data_collector/venv` | orchestrator 8090, news_scraper, market_data | 177 MB | 67 |
| `ai_secretary_brain/venv` | secretary 8999, health monitor | 180 MB | 70 |

- All four use CPython 3.9.6 from Xcode. 3.9 has been end-of-life since Oct 2025, so it gets no security fixes.
- There are 111 distinct packages across the four venvs. Only 4 have version differences, all minor: anthropic 0.106.0 vs 0.105.2, openai 2.41.0 vs 2.40.0, tqdm, pip. So conflicts are low.
- Problems this causes:
  - The same code imported across packages (e.g. `ai_engine` from the portfolio engine via PYTHONPATH) runs under a different venv than it was installed into.
  - There are 4 places to patch for each security update.
  - `start_all.sh` runs `pip install` on every start.

## Target
1. Use **one venv for investment_advisor**: `investment_advisor/.venv`. Then, when ready, upgrade to Homebrew Python 3.12. It serves the engine, advisor, council, AI engine and data collector.
2. **Keep `ai_secretary_brain/venv` separate.** It is a different repo with its own release cycle, and it talks to the advisor over HTTP only. Align versions where they overlap.
3. Manage everything from one `pyproject.toml` with lock files (`uv` or `pip-tools`): a `requirements.lock` per repo, with hashes.

## Steps (each one reversible; old venvs kept until the end)
1. **Inventory:** `pip freeze` of each venv into `docs/venv-freeze/<name>.txt`. Merge into a `requirements.in` with the top-level packages only.
2. **Build the new venv side by side:** `python3.9 -m venv .venv-new` (still 3.9 first, so only one variable changes), then install from the lock file.
3. **Smoke test with the new venv on spare ports:**
   - Engine on 18996, advisor on 18991, AI engine on 18997.
   - Run `py_compile`, `/health`, `/brief/today`, `/risk/report` and `/predictions/scoreboard`, and diff the JSON against production.
   - Run the walk-forward backtest once and compare it with the last stored run.
4. **Cut over one service at a time:**
   - Edit that one plist's ProgramArguments to `.venv-new` (backup first), kickstart it, and watch the health monitor for 24 h.
   - Order: AI engine, data collector, guru council, advisor, portfolio engine.
5. **Fix `start_all.sh`:**
   - Point it at the single venv.
   - Remove the per-start `pip install`.
   - Stop it starting services that launchd already runs.
   - Later, add launchd agents for the orchestrator, AI engine and council, so all services restart on reboot.
6. **Python upgrade (separate change):** repeat steps 2–4 with Python 3.12. Watch for:
   - asyncpg/numpy/pandas wheels.
   - The `zoneinfo` data.
   - yfinance behaviour.
7. **Retire the old venvs** only after 2 weeks with no errors, and only with Tho's OK. Archive them (tar to `~/backups`) rather than delete them.

## Risks and mitigations
- **yfinance or pandas behaviour changes alter numbers.** Pin the current versions for step 2, and diff the API outputs.
- **The AI engine's heavy packages (embeddings) bloat the shared venv.** If a conflict appears, keep the AI engine as the one exception.
- **Rollback:** each plist keeps its previous ProgramArguments in `~/backups/investment_advisor/`. A rollback is one kickstart.

## Effort
About half a day for steps 1–5, plus one day of soak time per batch of services. The Python 3.12 upgrade is about half a day plus soak.
