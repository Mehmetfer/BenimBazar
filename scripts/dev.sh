#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source .venv/bin/activate
PYTHONPATH="$ROOT" exec python -m uvicorn changex.app.main:app --host 0.0.0.0 --port 8000 --reload
