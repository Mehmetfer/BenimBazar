#!/usr/bin/env bash
# F7 controlled self-verification — sandbox only (no deploy / no LIVE).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [[ -x .venv/bin/python ]]; then
  PY=.venv/bin/python
else
  PY=python3
fi
exec "$PY" - <<'PY'
from self_verification import run_self_verification
from pathlib import Path
import json

out = Path("self_verification/.last_run")
out.mkdir(parents=True, exist_ok=True)
sandbox = out / "sandbox"
audit = out / "audit.jsonl"
report = run_self_verification(sandbox_root=sandbox, audit_path=audit)
print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False)[:4000])
print("STATUS:", report.status.value)
raise SystemExit(0 if report.ready_for_review else 1)
PY
