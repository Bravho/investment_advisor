# Investment Advisor — Command Reference

## ⚡ Start Everything (One Command)

```bash
cd ~/Projects/investment_advisor
bash start_all.sh
```

## 🛑 Stop Everything

```bash
bash start_all.sh --stop
```

---

## Services & Ports

| Service | Port | What it does |
|---|---|---|
| Main Advisor API | **8991** | FastAPI chat & advisory backend |
| Data Orchestrator | **8090** | News scraper, market data collector |
| AI Engine | **8997** | Sentiment, embeddings, risk scorer |
| Portfolio Engine | **8996** | Opportunities, rebalancing, briefs |
| Guru Council | **8993** | Discover/Explore API — scout + 4-analyst council |
| React Dashboard | **3999** | Web UI — open in browser |

---

## Individual Service Commands

### Prerequisites (start once, keep running)

```bash
# PostgreSQL database
brew services start postgresql        # macOS
sudo systemctl start postgresql       # Linux

# Ollama local LLM (optional — falls back to OpenAI/Anthropic API)
ollama serve
ollama pull hermes3:8b                # advisory model
ollama pull nomic-embed-text          # embeddings
ollama pull scb10x/typhoon2.5-qwen3-4b:latest  # Thai sentiment
```

### Service 1 — Main Advisor API (port 8991)
```bash
cd ~/Projects/investment_advisor
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8991
# OR background:
bash start_advisor.sh
```

### Service 2 — Data Collector & Orchestrator (port 8090)
```bash
cd ~/Projects/investment_advisor/data_collector
source venv/bin/activate
python orchestrator.py
# Runs: news_scraper.py + market_data.py on schedule
```

### Service 3 — AI Engine (port 8997)
```bash
cd ~/Projects/investment_advisor/ai_engine
source venv/bin/activate
python engine_runner.py
# Runs internally on schedule:
#   sentiment_pipeline.py  — scores news articles
#   embedding_pipeline.py  — builds vector embeddings
#   macro_aggregator.py    — aggregates macro indicators
#   risk_scorer.py         — calculates portfolio risk
```

### Service 4 — Portfolio Engine (port 8996)
```bash
cd ~/Projects/investment_advisor/portfolio_engine
source ../venv/bin/activate
python api.py
# Runs internally on schedule:
#   opportunity_scanner.py — scans watchlist every 30 min
#   check_exit_signals     — checks exit conditions every 15 min
#   brief_generator.py     — generates daily brief at 07:00 ICT
#   performance_analytics  — saves daily snapshot at 17:30 ICT
#   backtesting.py         — records outcomes at 08:00 ICT
```

### Service 5 — React Dashboard (port 3999)
```bash
cd ~/Projects/investment_advisor/dashboard
npm run dev
# Open: http://localhost:3999
```

### Service 6 — Guru Council / Discover API (port 8993)
Powers the dashboard's **Explore / Discover** page (sidebar: "ค้นหาโอกาส").
`start_all.sh` launches this automatically; to run it on its own:
```bash
cd ~/Projects/investment_advisor
source venv/bin/activate
python3 -m guru_council.cli serve --port 8993   # needs: pip install fastapi uvicorn
# Open the dashboard at http://localhost:3999 → Explore / Discover → Run
# Or the standalone ranked scorecard at http://localhost:8993/
```

Command-line use (no browser, writes to `data/council/`):
```bash
source venv/bin/activate
python3 -m guru_council.cli discover                       # AI scouts new ideas (excludes holdings)
python3 -m guru_council.cli discover --scope "US equities" "gold" -n 6
python3 -m guru_council.cli analyze MSFT SCB.BK PTTEP.BK SCBGOLDE BAFS.BK
python3 -m guru_council.cli compare                        # rebuild the ranked scorecard HTML
python3 -m guru_council.cli sources MSFT                   # show a ticker's data sources
```

API endpoints (also reachable through the dashboard proxy at `/api/council`):
```bash
curl http://localhost:8993/api/llm                         # which model is active
curl -X POST http://localhost:8993/api/discover \
  -H 'Content-Type: application/json' \
  -d '{"scope":["US equities","gold"],"n":6}'              # run discovery, get findings
```
> Discovery requires an LLM key (OpenAI/Anthropic) in `.env`. Without one the scout returns "unavailable".

---

## Useful Endpoints

```bash
# Check if Advisor API is alive
curl http://localhost:8991/

# AI Engine status (pipelines, last run times)
curl http://localhost:8997/status

# Portfolio Engine — latest opportunities
curl http://localhost:8996/opportunities

# Portfolio Engine — exit signals
curl http://localhost:8996/exit-signals

# Portfolio Engine — rebalancing plan
curl http://localhost:8996/rebalance

# Portfolio Engine — today's brief
curl http://localhost:8996/brief

# Portfolio Engine — performance summary
curl http://localhost:8996/performance

# Portfolio Engine — backtesting accuracy
curl http://localhost:8996/accuracy

# Orchestrator status (data collectors)
curl http://localhost:8090/status
```

---

## Run Individual AI Functions Manually

```bash
cd ~/Projects/investment_advisor
source venv/bin/activate

# Run sentiment pipeline once (score today's news)
cd ai_engine && python -c "
import asyncio
from sentiment_pipeline import run_sentiment_pipeline
asyncio.run(run_sentiment_pipeline())
"

# Run embedding pipeline once
cd ai_engine && python -c "
import asyncio
from embedding_pipeline import run_embedding_pipeline
asyncio.run(run_embedding_pipeline())
"

# Aggregate macro indicators
cd ai_engine && python -c "
import asyncio
from macro_aggregator import aggregate_macro_sentiment
asyncio.run(aggregate_macro_sentiment())
"

# Calculate portfolio risk score
cd ai_engine && python -c "
import asyncio
from risk_scorer import calculate_portfolio_risk
import json
result = asyncio.run(calculate_portfolio_risk())
print(json.dumps(result, indent=2))
"

# Scan for opportunities (portfolio engine)
cd portfolio_engine && python -c "
import asyncio
from opportunity_scanner import scan_opportunities
asyncio.run(scan_opportunities())
"

# Generate today's brief manually
cd portfolio_engine && python -c "
import asyncio
from brief_generator import generate_daily_brief
asyncio.run(generate_daily_brief())
"

# Scrape news now
cd data_collector && python news_scraper.py

# Fetch market data now
cd data_collector && python market_data.py
```

---

## Log Files

```bash
# Tail all logs at once
tail -f ~/Projects/investment_advisor/logs/*.log

# Individual logs
tail -f ~/Projects/investment_advisor/advisor.log          # Main API
tail -f ~/Projects/investment_advisor/logs/orchestrator.log
tail -f ~/Projects/investment_advisor/logs/ai_engine.log
tail -f ~/Projects/investment_advisor/logs/portfolio_engine.log
tail -f ~/Projects/investment_advisor/logs/guru_council.log
tail -f ~/Projects/investment_advisor/logs/dashboard.log
tail -f ~/Projects/investment_advisor/ai_engine/logs/sentiment.log
tail -f ~/Projects/investment_advisor/ai_engine/logs/embedding.log
tail -f ~/Projects/investment_advisor/ai_engine/logs/macro.log
tail -f ~/Projects/investment_advisor/ai_engine/logs/runner.log
```

---

## Watchlist Configuration

Edit `WATCHLIST_TICKERS` in `.env` to control what assets are tracked:

```bash
# Current default tickers (Yahoo Finance format):
WATCHLIST_TICKERS=BAFS.BK,PTTEP.BK,SCB.BK,ADVANC.BK,AOT.BK,AAPL,SPY,USDTHB=X

# Add more markets (examples):
# US Tech:    NVDA,MSFT,GOOGL,META,AMZN,TSM
# Japan:      7203.T,6758.T,9984.T       (Toyota, Sony, SoftBank)
# India:      RELIANCE.NS,TCS.NS,INFY.NS
# Vietnam:    VNM (ETF via NYSE)
# China/HK:   FXI,BABA,0700.HK
# EU:         EWG,EWQ,ASML.AS
# Gold:       GLD,GOLD
# Currencies: USDTHB=X,USDJPY=X,EURUSD=X
```

---

## Nightly Self-Development Agent

The project auto-improves itself every night at **2:30 AM**.  
To see what it did last night:

```bash
cat ~/Projects/investment_advisor/DEVLOG.md
```

To see today's market intelligence data:

```bash
ls ~/Projects/investment_advisor/data/market_intel/
cat ~/Projects/investment_advisor/data/market_intel/$(date +%Y-%m-%d).md
```
