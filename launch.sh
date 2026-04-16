#!/bin/bash
# STS2 Advisor Overlay — Linux Launcher

cd "$(dirname "$0")"

# Create venv if it doesn't exist
if [ ! -f ".venv/bin/python" ]; then
    echo "Setting up virtual environment for first run..."
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt
    echo "Setup complete."
fi

# Launch overlay (auto-detects save directory)
.venv/bin/python main.py "$@"
