#!/bin/bash
# Start Investment Advisor AI server on port 8991

PORT=${PORT:-8991}
echo "Starting Investment Advisor on port $PORT..."

# Find any process using port $PORT and kill it
PID=$(lsof -t -i:$PORT)
if [ ! -z "$PID" ]; then
    echo "Killing existing process on port $PORT (PID: $PID)"
    kill -9 $PID
    sleep 1
fi

# Ensure we are in the script's directory
cd "$(dirname "$0")"

# Create a virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Run server in the background
echo "Starting FastAPI server in background..."
nohup uvicorn main:app --host 0.0.0.0 --port $PORT > advisor.log 2>&1 &

echo "Investment Advisor AI started successfully on port $PORT."
echo "Logs are written to advisor.log."
echo "Visit the dashboard at http://localhost:$PORT/"
