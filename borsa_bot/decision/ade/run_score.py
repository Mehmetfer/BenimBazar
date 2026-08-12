"""Generate ADE autonomy evidence + report from test outcomes."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from decision.ade.scorecard import score_decision_autonomy

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "autonomy" / "evidence" / "ade"
REPORTS = ROOT / "autonomy" / "reports"


def _run_pytest(args: list[str]) -> tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *args, "-q", "--tb=line"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode == 0, out


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)

    unit_ok, unit_out = _run_pytest(["tests/test_ade_decision.py"])
    e2e_ok, e2e_out = _run_pytest(["tests/test_ade_humanless_e2e.py"])
    safety_ok, safety_out = _run_pytest(["tests/test_trading_safety.py", "tests/test_trading_safety_e2e.py"])

    (EVIDENCE / "unit.txt").write_text(unit_out, encoding="utf-8")
    (EVIDENCE / "humanless_e2e.txt").write_text(e2e_out, encoding="utf-8")
    (EVIDENCE / "trading_safety.txt").write_text(safety_out, encoding="utf-8")

    sc = score_decision_autonomy(
        engineering_score=8.45,
        trading_safety_score=10.0 if safety_ok else 0.0,
        decision_states_ok=unit_ok,
        chain_complete_ok=unit_ok,
        no_trade_ok=unit_ok,
        position_sizing_hard_cap_ok=unit_ok,
        immutable_limits_ok=unit_ok,
        adaptive_no_bypass_ok=unit_ok,
        self_correction_ok=unit_ok,
        decision_validator_ok=unit_ok,
        confidence_gate_ok=unit_ok,
        humanless_e2e_ok=e2e_ok,
        failure_acceptance_ok=unit_ok and e2e_ok,
    )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "unit_ok": unit_ok,
        "e2e_ok": e2e_ok,
        "safety_ok": safety_ok,
        "scorecard": sc.to_dict(),
    }
    (EVIDENCE / "scorecard.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = [
        "# Autonomous Decision Engine Report",
        "",
        f"- Generated: `{payload['generated_at']}`",
        f"- Engineering autonomy (prior): **{sc.engineering_autonomy_score}/10**",
        f"- Decision autonomy: **{sc.decision_autonomy_score}/10**",
        f"- Trading safety (prior): **{sc.trading_safety_score}/10**",
        f"- Live-money autonomy: **{sc.live_money_autonomy}**",
        f"- full_level8_claimed: **{sc.full_level8_claimed}**",
        f"- Verdict: **{sc.verdict}**",
        "",
        "## Suite results",
        "",
        f"- ADE unit: `{'PASS' if unit_ok else 'FAIL'}`",
        f"- Humanless E2E: `{'PASS' if e2e_ok else 'FAIL'}`",
        f"- Trading safety regression: `{'PASS' if safety_ok else 'FAIL'}`",
        "",
        "## Criteria",
        "",
        "| Criterion | Status | Weight | Score |",
        "|-----------|--------|--------|------:|",
    ]
    for c in sc.criteria:
        lines.append(f"| {c.name} | {c.status} | {int(c.weight * 100)}% | {c.score} |")
    lines.extend(
        [
            "",
            "## Roadmap",
            "",
            *[f"- {r}" for r in sc.roadmap],
            "",
            "## Notes",
            "",
            *[f"- {n}" for n in sc.notes],
            "",
            "## Meaning",
            "",
            "8.5 means the bot can independently observe, decide (including NO_TRADE),",
            "size within immutable hard caps, validate, and execute **paper/shadow** orders",
            "without human approval — while refusing to trade when safety cannot be established.",
            "It does **not** mean LIVE-MONEY AUTONOMY = VERIFIED.",
            "",
        ]
    )
    (REPORTS / "ADE_AUTONOMY_REPORT.md").write_text("\n".join(lines), encoding="utf-8")

    # Keep trading report pointer honest (idempotent replace of follow-on block)
    ptr = REPORTS / "AUTONOMY_REPORT.md"
    if ptr.exists():
        text = ptr.read_text(encoding="utf-8")
        marker = "## Autonomous Decision Engine (follow-on)"
        block = (
            f"{marker}\n\n"
            f"- Decision autonomy level: **{sc.decision_autonomy_score}/10**\n"
            f"- Verdict: {sc.verdict}\n"
            "- Details: `ADE_AUTONOMY_REPORT.md`\n"
            "- LIVE-MONEY AUTONOMY: NOT VERIFIED\n"
        )
        if marker in text:
            pre = text.split(marker)[0].rstrip()
            text = pre + "\n\n" + block
        else:
            text = text.rstrip() + "\n\n" + block
        ptr.write_text(text + "\n", encoding="utf-8")

    print(json.dumps(sc.to_dict(), indent=2))
    return 0 if (unit_ok and e2e_ok and safety_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
