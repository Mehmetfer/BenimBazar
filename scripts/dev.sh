#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  bash "$ROOT/scripts/install.sh"
fi

# shellcheck disable=SC1091
source .venv/bin/activate
export PYTHONPATH="$ROOT"
exec python -m uvicorn companion.app.main:app --host 0.0.0.0 --port 8000
