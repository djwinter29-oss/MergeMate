#!/usr/bin/env bash

set -euo pipefail

python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt

echo "Virtual environment ready at .venv"
echo "Activate it with: source .venv/bin/activate"