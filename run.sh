#!/bin/bash
# Nifty Option Trading - Startup Script
# No virtual environment - uses system Python

echo "================================================"
echo "     Nifty Option Trading - Starting...         "
echo "================================================"

# Change to backend directory
cd "$(dirname "$0")/backend"

# Create required directories
mkdir -p cache data logs

# Install dependencies (system-wide)
echo "Installing dependencies..."
pip3 install -r requirements.txt -q

# Start the server
echo ""
echo "================================================"
echo "  Server starting at http://localhost:8000      "
echo "  Login: http://localhost:8000/login            "
echo "  Credentials: admin / admin                    "
echo "================================================"
echo ""

python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
