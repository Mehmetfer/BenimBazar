#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! python3 -c "import ensurepip" 2>/dev/null; then
  echo "python3-venv / ensurepip missing; install python3.12-venv" >&2
  exit 1
fi

if [[ ! -x .venv/bin/python || ! -f .venv/bin/activate ]]; then
  rm -rf .venv
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r companion/requirements.txt
python -m pip install -r changex/requirements.txt
python -m pip install pytest
