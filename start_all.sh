#!/bin/bash
# ============================================================
#  Investment Advisor — Start All Services
#  Usage: bash start_all.sh [--stop]
# ============================================================

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'; BOLD='\033[1m'
ok()   { echo -e "${GREEN}✔ $1${NC}"; }
warn() { echo -e "${YELLOW}⚠ $1${NC}"; }
err()  { echo -e "${RED}✘ $1${NC}"; }
hdr()  { echo -e "\n${BOLD}$1${NC}"; }

# ── Stop mode ────────────────────────────────────────────────
if [[ "$1" == "--stop" ]]; then
  hdr "Stopping all Investment Advisor services..."
  for PORT in 8991 8090 8996 8997 8993 3999; do
    PID=$(lsof -t -i:$PORT 2>/dev/null)
    if [ -n "$PID" ]; then
      kill -9 $PID 2>/dev/null
      ok "Stopped process on port $PORT (PID $PID)"
    fi
  done
  echo "All services stopped."
  exit 0
fi

hdr "=== Investment Advisor — Starting All Services ==="
echo "Project: $PROJECT_DIR"
echo "Time:    $(date)"

# ── Check prerequisites ──────────────────────────────────────
hdr "1. Checking prerequisites..."

# PostgreSQL
if pg_isready -q 2>/dev/null; then
  ok "PostgreSQL is running"
else
  warn "PostgreSQL not detected — DB-dependent features may fail"
  warn "Start with: brew services start postgresql  (macOS)"
fi

# Ollama (local LLM)
if curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
  ok "Ollama is running"
else
  warn "Ollama not running — AI features will fall back to OpenAI/Anthropic API"
  warn "Start with: ollama serve  (in a separate terminal)"
fi

# .env file
if [ -f "$PROJECT_DIR/.env" ]; then
  ok ".env file found"
else
  err ".env file missing — copy .env.example to .env and fill in your keys"
  exit 1
fi

# ── Kill any existing processes on our ports ─────────────────
hdr "2. Clearing ports..."
for PORT in 8991 8090 8996 8997 8993 3999; do
  PID=$(lsof -t -i:$PORT 2>/dev/null)
  if [ -n "$PID" ]; then
    kill -9 $PID 2>/dev/null
    warn "Cleared port $PORT (PID $PID)"
  fi
done

# ── Set up Python venv ───────────────────────────────────────
hdr "3. Setting up Python virtual environment..."
cd "$PROJECT_DIR"
if [ ! -d "venv" ]; then
  python3 -m venv venv
  ok "Created venv"
fi
source venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt
ok "Main dependencies installed"

# ── Service 1: Data Collector / Orchestrator (port 8090) ─────
hdr "4. Starting Data Collector & Orchestrator (port 8090)..."
cd "$PROJECT_DIR/data_collector"
if [ ! -d "venv" ]; then
  python3 -m venv venv
  pip install -q -r requirements.txt
fi
source venv/bin/activate
pip install -q -r requirements.txt
nohup python orchestrator.py start > "$LOG_DIR/orchestrator.log" 2>&1 &
echo $! > "$LOG_DIR/orchestrator.pid"
ok "Data Collector started (PID $!) → log: logs/orchestrator.log"

# ── Service 2: AI Engine (port 8997) ─────────────────────────
hdr "5. Starting AI Engine (port 8997)..."
cd "$PROJECT_DIR/ai_engine"
if [ ! -d "venv" ]; then
  python3 -m venv venv
fi
source venv/bin/activate
pip install -q -r requirements.txt
nohup python engine_runner.py > "$LOG_DIR/ai_engine.log" 2>&1 &
echo $! > "$LOG_DIR/ai_engine.pid"
ok "AI Engine started (PID $!) → log: logs/ai_engine.log"

# ── Service 3: Portfolio Engine (port 8996) ───────────────────
hdr "6. Starting Portfolio Engine (port 8996)..."
cd "$PROJECT_DIR/portfolio_engine"
source "$PROJECT_DIR/venv/bin/activate"
pip install -q -r requirements.txt
nohup python api.py > "$LOG_DIR/portfolio_engine.log" 2>&1 &
echo $! > "$LOG_DIR/portfolio_engine.pid"
ok "Portfolio Engine started (PID $!) → log: logs/portfolio_engine.log"

# ── Service 4: Main FastAPI Advisor (port 8991) ───────────────
hdr "7. Starting Main Advisor API (port 8991)..."
cd "$PROJECT_DIR"
source venv/bin/activate
nohup uvicorn main:app --host 0.0.0.0 --port 8991 > "$LOG_DIR/advisor.log" 2>&1 &
echo $! > "$LOG_DIR/advisor.pid"
ok "Main Advisor started (PID $!) → log: logs/advisor.log"

# ── Service 6: Guru Council (port 8993) ──────────────────────
hdr "8. Starting Guru Council — Discover/Explore API (port 8993)..."
cd "$PROJECT_DIR"
source venv/bin/activate
nohup python3 -m guru_council.cli serve --port 8993 > "$LOG_DIR/guru_council.log" 2>&1 &
echo $! > "$LOG_DIR/guru_council.pid"
ok "Guru Council started (PID $!) → log: logs/guru_council.log"

# ── Service 5: Dashboard (port 3999) ─────────────────────────
hdr "9. Starting React Dashboard (port 3999)..."
cd "$PROJECT_DIR/dashboard"
if [ ! -d "node_modules" ]; then
  npm install --silent
fi
nohup npm run dev > "$LOG_DIR/dashboard.log" 2>&1 &
echo $! > "$LOG_DIR/dashboard.pid"
ok "Dashboard started (PID $!) → log: logs/dashboard.log"

# ── Wait and show status ──────────────────────────────────────
hdr "10. Waiting for services to become ready..."
sleep 4

echo ""
echo -e "${BOLD}══════════════════════════════════════════════════${NC}"
echo -e "${BOLD}  SERVICE STATUS${NC}"
echo -e "${BOLD}══════════════════════════════════════════════════${NC}"
check_port() {
  local NAME=$1; local PORT=$2; local URL=$3
  if lsof -i:$PORT >/dev/null 2>&1; then
    ok "$NAME → http://localhost:$PORT$URL"
  else
    err "$NAME (port $PORT) — not responding yet, check log"
  fi
}
check_port "Main Advisor API  " 8991 "/"
check_port "Orchestrator      " 8090 "/status"
check_port "AI Engine         " 8997 "/status"
check_port "Portfolio Engine  " 8996 "/opportunities"
check_port "Guru Council      " 8993 "/api/llm"
check_port "Dashboard UI      " 3999 "/"
echo -e "${BOLD}══════════════════════════════════════════════════${NC}"
echo ""
echo "To stop all services: bash start_all.sh --stop"
echo "To tail all logs:     tail -f $LOG_DIR/*.log"
