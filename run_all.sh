#!/bin/bash
# ══════════════════════════════════════════════════════════════════
# Portfolio Analyzer V2 — Startup Script (FastAPI, no Celery/Redis)
# ══════════════════════════════════════════════════════════════════
set -e
cd "$(dirname "$0")"

# Use conda/miniconda python if available
PYTHON=$(which python 2>/dev/null || which python3 2>/dev/null)
if [ -d "$HOME/miniconda3/bin" ]; then
    export PATH="$HOME/miniconda3/bin:$PATH"
    PYTHON="$HOME/miniconda3/bin/python"
elif [ -d "$HOME/anaconda3/bin" ]; then
    export PATH="$HOME/anaconda3/bin:$PATH"
    PYTHON="$HOME/anaconda3/bin/python"
fi
echo "🐍 Using Python: $PYTHON"

# ── Kill any leftover processes ───────────────────────────────────
echo "🧹 Cleaning up old processes..."
pkill -f "uvicorn api_gateway" 2>/dev/null || true
pkill -f "streamlit run app_v2" 2>/dev/null || true
sleep 1

# ── Install missing deps silently ────────────────────────────────
echo "📦 Checking dependencies..."
pip install -q fastapi uvicorn[standard] python-multipart slowapi 2>/dev/null || true

# ── Start FastAPI backend ─────────────────────────────────────────
echo "🚀 Starting FastAPI backend on :8000 ..."
$PYTHON -m uvicorn api_gateway:app --host 0.0.0.0 --port 8000 --reload --log-level info &
UVICORN_PID=$!

# Wait for FastAPI to be ready
echo "⏳ Waiting for API to be ready..."
for i in $(seq 1 20); do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo "✅ API ready!"
        break
    fi
    sleep 1
done

# ── Print API key ─────────────────────────────────────────────────
API_KEY=$(grep PORTFOLIO_API_KEY .env 2>/dev/null | cut -d= -f2 | tr -d '[:space:]')
if [ -n "$API_KEY" ]; then
    echo ""
    echo "🔑 API Key: $API_KEY"
    echo "📖 Swagger: http://localhost:8000/docs"
    echo ""
fi

# ── Start Streamlit frontend ──────────────────────────────────────
echo "🌐 Starting Streamlit on :8501 ..."
$PYTHON -m streamlit run app_v2.py \
    --server.port 8501 \
    --server.address localhost \
    --server.headless true \
    --browser.gatherUsageStats false &
STREAMLIT_PID=$!

echo ""
echo "══════════════════════════════════════════════"
echo " Portfolio Analyzer V2"
echo " Frontend: http://localhost:8501"
echo " API Docs: http://localhost:8000/docs"
echo " Press Ctrl+C to stop both services"
echo "══════════════════════════════════════════════"

# ── Wait / handle Ctrl+C ─────────────────────────────────────────
trap "echo '🛑 Shutting down...'; kill $UVICORN_PID $STREAMLIT_PID 2>/dev/null; exit 0" INT TERM
wait
