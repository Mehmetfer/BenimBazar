"""Run trading-safety scorecard after challenge suites."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from config.settings import settings
from trading_safety.scorecard import score_trading_autonomy

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "autonomy" / "reports"
EVIDENCE = ROOT / "autonomy" / "evidence"


def _ok(nodes: list[str]) -> bool:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--tb=line", *nodes],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
    )
    return proc.returncode == 0


def main() -> dict:
    REPORTS.mkdir(parents=True, exist_ok=True)
    safety = _ok(["tests/test_trading_safety.py"])
    e2e = _ok(["tests/test_trading_safety_e2e.py"])
    required_reg = _ok(
        ["tests/test_trading_safety.py::test_required_provider_still_blocked_in_production"]
    )
    live_locked = bool(getattr(settings, "live_broker_enabled", False)) is False
    all_ok = safety and e2e and required_reg and live_locked
    card = score_trading_autonomy(
        engineering_score=8.45,
        safety_gates_ok=safety,
        fail_closed_ok=safety,
        idempotency_ok=safety,
        unknown_order_ok=safety and e2e,
        reconciliation_ok=safety and e2e,
        restart_recovery_ok=e2e,
        risk_controls_ok=safety,
        kill_circuit_ok=safety and e2e,
        observability_audit_ok=safety,
        adversarial_e2e_ok=e2e,
        live_broker_locked=live_locked,
        critical_findings=0 if all_ok else 1,
        all_mandatory_pass=all_ok,
    )
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "previous_engineering_autonomy": 8.45,
        "suites": {"trading_safety": safety, "e2e": e2e, "required_regression": required_reg},
        "scorecard": card.to_dict(),
    }
    (REPORTS / "trading_autonomy_score.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    md = f"""# Trading Autonomy Report

- Generated: `{payload['generated_at']}`
- Previous engineering autonomy: **8.45/10** (VERIFIED — coding/validation)
- Trading safety score: **{card.trading_safety_score}/10**
- Live-money readiness: **{card.live_money_readiness}**
- full_level8_claimed: **{card.full_level8_claimed}**
- Verdict: **{card.verdict}**

## Suite results

- trading_safety: `{'PASS' if safety else 'FAIL'}`
- adversarial/e2e: `{'PASS' if e2e else 'FAIL'}`
- REQUIRED provider regression: `{'PASS' if required_reg else 'FAIL'}`
- LIVE broker locked: `{live_locked}`

## Criteria

| Criterion | Status | Weight | Score |
|-----------|--------|--------|------:|
"""
    for c in card.criteria:
        md += f"| {c.name} | {c.status} | {int(c.weight*100)}% | {c.score} |\n"
    md += "\n## Notes\n\n"
    for n in card.notes:
        md += f"- {n}\n"
    md += """
## Meaning

Trading safety ≥9 means fail-closed execution controls are verified in paper/shadow/simulated adversarial tests.
It does **not** authorize real-money LIVE trading.
"""
    (REPORTS / "TRADING_AUTONOMY_REPORT.md").write_text(md, encoding="utf-8")
    print(json.dumps({"trading_safety_score": card.trading_safety_score, "verdict": card.verdict, "live_money_readiness": card.live_money_readiness}, indent=2))
    return payload


if __name__ == "__main__":
    main()
