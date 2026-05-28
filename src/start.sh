#!/bin/bash

# RAG Pipeline startup script

set -e

echo "=========================================="
echo "RAG Pipeline Startup Script"
echo "=========================================="

# Change to src directory
cd "$(dirname "$0")"

# Step 1: Install dependencies
echo ""
echo "[1] Installing dependencies..."
pip install -r requirements.txt 2>&1 | tail -5

# Step 2: Create sample documents
echo ""
echo "[2] Creating sample documents..."
export PYTHONPATH="$(pwd)"
python -m core.crawler --mode sample --output ./sample_docs 2>&1 | tail -3

# Step 3: Start FastAPI server
echo ""
echo "[3] Starting FastAPI server..."
echo "    Swagger UI: http://localhost:8000/docs"
echo "    API: http://localhost:8000"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

export PYTHONPATH="$(pwd)"
python -m uvicorn core.api:app --reload --host 0.0.0.0 --port 8000
