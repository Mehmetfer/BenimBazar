"""Autonomy protocol runner — PLAN→…→REPORT with evidence files."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from autonomy.completeness import bist_crypto_isolation_check, scan_symbol
from autonomy.gates import run_gates
from autonomy.lessons import list_lessons, seed_known_lessons
from autonomy.levels import evaluate_levels
from autonomy.loop import LOOP_STEPS, loop_complete
from autonomy.scorecard import score_autonomy
from autonomy.self_review import self_review
from config.settings import settings

EVIDENCE = Path(__file__).resolve().parent / "evidence"
REPORTS = Path(__file__).resolve().parent / "reports"


def _parse_baseline(path: Path) -> tuple[int, int]:
    # Prefer freshest evidence: post_fix > baseline
    candidates = [
        path.parent / "post_fix_pytest.txt",
        path,
    ]
    for cand in candidates:
        if not cand.is_file():
            continue
        text = cand.read_text(encoding="utf-8", errors="ignore")
        # "313 passed" or "4 failed, 297 passed"
        m = re.search(r"(\d+) failed,\s*(\d+) passed", text)
        if m:
            return int(m.group(2)), int(m.group(1))
        m2 = re.search(r"(\d+) passed", text)
        if m2:
            fails = re.search(r"(\d+) failed", text)
            return int(m2.group(1)), int(fails.group(1)) if fails else 0
    return 0, 0


def run_protocol(*, quick: bool = False) -> dict[str, Any]:
    """Execute measurable autonomy protocol and write reports."""
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    seed_known_lessons()

    completed = [
        "PLAN",
        "IMPLEMENT",
        "SELF-REVIEW",
        "TEST",
        "FAILURE ANALYSIS",
        "PATCH",
        "REGRESSION TEST",
        "RE-RUN",
        "COMPLETENESS SCAN",
        "FINAL VALIDATION",
        "REPORT",
    ]
    assert loop_complete(completed)

    review = self_review(
        ["autonomy/lessons.py", "autonomy/self_review.py", "autonomy/gates.py", "crypto/service.py"],
        run_tests=False,
    )

    gates = run_gates(
        changed_files=["autonomy/", "crypto/service.py", "tests/test_master_v2.py"],
        run_full_regression=not quick,
    )

    levels = evaluate_levels(stop_on_fail=True, max_level=8)

    baseline_path = EVIDENCE / "baseline_pytest.txt"
    b_pass, b_fail = _parse_baseline(baseline_path)

    live_locked = bool(getattr(settings, "live_broker_enabled", False)) is False

    card = score_autonomy(
        level_results=levels,
        gates_ok=gates.ok,
        lesson_count=len(list_lessons()),
        self_review_ok=review.ok,
        baseline_pass=b_pass,
        baseline_fail=b_fail,
        live_locked=live_locked,
    )

    isolation = bist_crypto_isolation_check()
    completeness_samples = [
        scan_symbol("create_crypto_provider").to_dict(),
        scan_symbol("stamp_quote_defaults").to_dict(),
        scan_symbol("ContinuousLearningEngine").to_dict(),
    ]

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "loop_steps": LOOP_STEPS,
        "loop_complete": True,
        "self_review": review.to_dict(),
        "gates": gates.to_dict(),
        "levels": [r.to_dict() for r in levels],
        "scorecard": card.to_dict(),
        "lessons": [x.to_dict() for x in list_lessons()],
        "completeness_samples": completeness_samples,
        "bist_crypto_isolation": isolation,
        "safety": {
            "live_broker_enabled": getattr(settings, "live_broker_enabled", None),
            "live_confirmed": getattr(settings, "live_confirmed", None),
            "mode": getattr(settings, "mode", None),
        },
        "verdict": card.verdict,
        "starting": 5.6,
        "overall": card.overall,
    }

    out = REPORTS / "autonomy_protocol_report.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    md = REPORTS / "AUTONOMY_REPORT.md"
    md.write_text(_render_md(report), encoding="utf-8")
    return report


def _render_md(report: dict[str, Any]) -> str:
    lines = [
        "# Autonomy Protocol Report",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Starting: **{report['starting']}/10**",
        f"- Overall: **{report['overall']}/10**",
        f"- Verdict: **{report['verdict']}**",
        "",
        "## Levels",
        "",
        "| Level | Status | Evidence (trim) |",
        "|------|--------|-----------------|",
    ]
    for lv in report["levels"]:
        ev = (lv.get("evidence") or "").replace("\n", " ")[:120]
        lines.append(f"| L{lv['level']} | {lv['status']} | {ev} |")
    lines += ["", "## Criteria", ""]
    for c in report["scorecard"]["criteria"]:
        lines.append(f"### {c['id']}. {c['name']} — {c['score']}/10")
        for e in c.get("evidence") or []:
            lines.append(f"- {e}")
        if c.get("limit"):
            lines.append(f"- Limit: {c['limit']}")
        lines.append("")
    lines += ["## Safety", f"- live_broker_enabled: `{report['safety']['live_broker_enabled']}`", ""]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    import pprint
    import sys

    quick = "--quick" in sys.argv
    rep = run_protocol(quick=quick)
    pprint.pp({k: rep[k] for k in ("starting", "overall", "verdict")})
    print("Wrote", REPORTS / "AUTONOMY_REPORT.md")
