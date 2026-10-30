# Investment Advisor (Tho)

Personal investment-advisory stack on the Mac Mini: data collection, AI engine, portfolio/risk
engine, chat advisor, guru council and a React dashboard. Everything is advisory: no broker
connection, no automatic orders. See `COMMANDS.md` for the older command reference and
`DEVLOG.md` for history.

## Ops

_Last verified 2026-10-30 (ICT)._

### Services and ports

| Service | Port / bind | Started by | Python / runtime | Logs |
|---|---|---|---|---|
| Portfolio engine (FastAPI + APScheduler: risk, signals, trade plans, predictions, construction, attribution, briefs) | 8996 on 127.0.0.1 | launchd `com.tho.investment.portfolio-engine` (KeepAlive) | `venv/` (3.9) | `portfolio_engine/logs/api.log` |
| Main advisor / chat (`main.py`, `/advisors/message` for the secretary) | 8991 on 0.0.0.0 | launchd `com.tho.investment.advisor` | `venv/` | `advisor.log`, `logs/` |
| Dashboard (Vite preview of `dashboard/dist`; `/api/*` same-origin proxies) | 3999 on 127.0.0.1 | launchd `com.tho.investment.dashboard` | node (Homebrew) | launchd log |
| Data orchestrator (news_scraper, market_data workers) | 8090 | `start_all.sh` (nohup) | `data_collector/venv/` | `logs/orchestrator.log` |
| AI engine (`engine_runner.py`: sentiment, embeddings) | 8997 | orchestrator / `start_all.sh` | `ai_engine/venv/` | `logs/ai_engine.log` |
| Guru council (`guru_council.cli serve`) | 8993 | `start_all.sh` | `venv/` | `logs/guru_council.log` |
| AI secretary (other repo, `~/Projects/ai_secretary_brain`) + ngrok static domain | 8999 | launchd `com.ai_secretary` (`scripts/start.sh`) | `ai_secretary_brain/venv/` | its `logs/` |
| Remote access auth proxy (password) + Cloudflare quick tunnel | 19091 on 127.0.0.1 | manual, config in `~/.config/investment_advisor/` | Homebrew Python 3.14 | - |
| Second cloudflared (token from /Library) | - | system | - | - |
| PostgreSQL `investor_db` | 5432 on localhost | Homebrew service | - | - |
| Ollama (local LLM, hermes3:8b) | 11434 on 127.0.0.1 | Ollama app | - | - |

**Do not touch** the auth proxy / Cloudflare tunnel processes (Tho's public link).

### launchd agents (`~/Library/LaunchAgents`, copies in `ops/launchd/`)

| Label | Schedule | What |
|---|---|---|
| `com.tho.investment.portfolio-engine` | always (KeepAlive) | engine on 8996 |
| `com.tho.investment.advisor` | always | advisor on 8991 |
| `com.tho.investment.dashboard` | always | dashboard on 3999 |
| `com.tho.investment.healthmonitor` | every 300 s | `ops/health_monitor.py` (12 checks; LINE alert unless `HEALTH_MONITOR_DRY_RUN=1`) |
| `com.tho.logrotate` | 03:15 daily | `ops/rotate_logs.py` |
| `com.tho.investment.nightly-research` | 02:30 daily | `ops/nightly_research.py`: research-only nightly agent (local, free) |
| `com.ai_secretary` | always | secretary 8999 + ngrok |

Restart one service: `launchctl kickstart -k gui/$(id -u)/<label>`.
Status: `launchctl print gui/$(id -u)/<label> | grep state`.
Dashboard change: `cd dashboard && npm run build`, then kickstart the dashboard.
Health: `ai_secretary_brain/venv/bin/python ops/health_monitor.py --dry-run` (should print 12/12 OK).

Warning: `start_all.sh` also starts a portfolio engine, an advisor and a dashboard. Those are now run
by launchd, so starting them again would cause port clashes. Use `start_all.sh` only for the
orchestrator, AI engine and guru council, or stop the launchd agents first.

### Engine schedule (ICT, APScheduler in `portfolio_engine/api.py`)
06:30 risk report · 06:40 factors · 06:45 trade-plan proposals · 06:50 signals · 06:55 predictions ·
07:00 brief (retries after) · 07:10 portfolio construction · 08:00 outcome scoring · 08:05 prediction
validation · 17:30 performance snapshot · 18:00 paper ledger · 18:15 attribution · Sun 05:00
walk-forward backtest · day 1 09:00 monthly forecast summary (LINE; dry-run unless enabled) ·
every 30 min watch-list prices/alerts · every 60 min market factors.

### Key endpoints (8996; via dashboard `/api/portfolio/...`)
`/health`, `/brief/today`, `/risk/report`, `/factors`, `/watchlist`, `/signals`, `/trade-plans`
(PATCH `/trade-plans/{id}` to approve or reject), `/journal`, `/backtest/latest`, `/paper-trades`,
`/predictions`, `/predictions/scoreboard`, `/portfolio/construction`, `/performance/attribution`.
Dashboard: `/` (overview) and `/desk` (one-screen trading desk).

### Safety switches
- `ALLOW_PAID_LLM` (unset or 0 means local Ollama only). `WATCH_ALERTS_DRY_RUN=1` and `HEALTH_MONITOR_DRY_RUN=1` stop LINE sends.
- `config/investment_policy.json` is a **DRAFT** policy. `config/risk_limits.json` holds the caps. `config/self_develop.json` sets the nightly-agent mode (research_only; code mode disabled).
- Secrets live in `.env` (untracked). Never commit it.

### Backups
DB: `~/backups/investor_db/investor_db.full.<stamp>.dump` (`pg_dump -Fc`). File backups before edits: `~/backups/investment_advisor/`.

### Python environments
There are four venvs (`venv/`, `ai_engine/venv/`, `data_collector/venv/`, `ai_secretary_brain/venv/`), all CPython 3.9.6 (Xcode).
For the unification plan (not migrated yet), see `docs/VENV_UNIFICATION_PLAN.md`.

## Setups (2026-10-30)
- `momentum_base_swing`: a swing/position adaptation of Tho's momentum + base lesson. Docs: `docs/lessons/momentum_base_setup.md`. Config: `config/setups.json`.
- Jobs (8996): `setup_screen_evening` 17:45 ICT Mon–Fri, `setup_screen_prebrief` 06:47 ICT, `setup_backtest` Sunday 05:30 ICT.
- API: `GET /setups/momentum-base`, `POST /setups/momentum-base/run`, `GET|POST /setups/momentum-base/backtest[/run]`, `GET /setups/momentum-base/advisor-context`.
- **No order execution exists anywhere in this project.** Plans are `proposed`. Approving one only logs the decision and copies its levels to the watch list for alerts. Tho places every trade himself.
