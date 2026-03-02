#!/bin/bash
# Run Kinly Lead Distribution (dashboard on port 5001)
cd "$(dirname "$0")"
export PORT=5001
echo "Starting server at http://127.0.0.1:$PORT"
echo "Open that URL in your browser for the dashboard."
exec .venv/bin/python app.py
