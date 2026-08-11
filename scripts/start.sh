#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  bash "$ROOT/scripts/install.sh"
fi

# shellcheck disable=SC1091
source .venv/bin/activate

PID_FILE="$ROOT/companion/data/uvicorn.pid"
mkdir -p "$ROOT/companion/data"

is_healthy() {
  curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1
}

if is_healthy; then
  echo "Borsa already running on :8000"
  exit 0
fi

if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "Waiting for existing process..."
else
  PYTHONPATH="$ROOT" nohup python -m uvicorn companion.app.main:app \
    --host 0.0.0.0 --port 8000 \
    >"$ROOT/companion/data/uvicorn.log" 2>&1 &
  echo $! >"$PID_FILE"
fi

for _ in $(seq 1 30); do
  if is_healthy; then
    echo "Borsa ready on http://127.0.0.1:8000"
    exit 0
  fi
  sleep 0.5
done

echo "Borsa failed to become healthy" >&2
tail -n 50 "$ROOT/companion/data/uvicorn.log" >&2 || true
exit 1
