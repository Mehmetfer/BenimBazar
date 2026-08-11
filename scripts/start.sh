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
LOG_FILE="$ROOT/companion/data/uvicorn.log"
mkdir -p "$ROOT/companion/data"

is_healthy() {
  curl -fsS --max-time 1 http://127.0.0.1:8000/api/health >/dev/null 2>&1
}

if is_healthy; then
  echo "Borsa already running on :8000"
  exit 0
fi

# Clear stale pid
rm -f "$PID_FILE"

PYTHONPATH="$ROOT" nohup python -m uvicorn companion.app.main:app \
  --host 0.0.0.0 --port 8000 \
  >"$LOG_FILE" 2>&1 &
echo $! >"$PID_FILE"

for _ in $(seq 1 20); do
  if is_healthy; then
    echo "Borsa ready on http://127.0.0.1:8000"
    exit 0
  fi
  sleep 0.2
done

echo "Borsa failed to become healthy" >&2
tail -n 50 "$LOG_FILE" >&2 || true
exit 1
