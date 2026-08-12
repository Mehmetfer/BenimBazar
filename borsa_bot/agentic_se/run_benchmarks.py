"""Run ASE benchmarks and write SOFTWARE_ENGINEERING_AUTONOMY_REPORT.md."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from agentic_se.benchmarks import run_all_benchmarks
from agentic_se.scorecard import score_software_engineering_autonomy
from self_improvement.verify import save_baseline

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "autonomy" / "reports"
EVIDENCE = ROOT / "autonomy" / "evidence" / "agentic_se"


def main() -> int:
    save_baseline(passed=412, failed=0, note="pre-ASE baseline")
    payload = run_all_benchmarks()
    by_name = {r["name"]: r["success"] for r in payload["results"]}
    sc = score_software_engineering_autonomy(
        bench=by_name,
        benchmark_passed=payload["passed"],
        benchmark_total=payload["total"],
    )
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "scorecard.json").write_text(json.dumps(sc.to_dict(), indent=2), encoding="utf-8")

    lines = [
        "# Software Engineering Autonomy Report",
        "",
        f"- Generated: `{datetime.now(timezone.utc).isoformat()}`",
        f"- Previous engineering autonomy: **{sc.previous_engineering}/10**",
        f"- Previous self-improvement: **{sc.previous_si}/10**",
        f"- Software engineering autonomy: **{sc.software_engineering_autonomy}/10**",
        f"- Live-money autonomy: **{sc.live_money_autonomy}**",
        f"- full_level8_claimed: **{sc.full_level8_claimed}**",
        f"- Verdict: **{sc.verdict}**",
        "",
        "## Benchmark results",
        "",
        f"- Passed: **{sc.benchmark_passed}/{sc.benchmark_total}**",
        "",
        "| Benchmark | Category | Success | Seconds | Detail |",
        "|-----------|----------|---------|--------:|--------|",
    ]
    for r in payload["results"]:
        lines.append(
            f"| {r['name']} | {r['category']} | {'PASS' if r['success'] else 'FAIL'} | {r['seconds']:.3f} | {r.get('detail','')[:60]} |"
        )
    lines.extend(["", "## Criteria", "", "| Criterion | Weight | Status | Score |", "|-----------|-------:|--------|------:|"])
    for c in sc.criteria:
        lines.append(f"| {c.name} | {int(c.weight*100)}% | {c.status} | {c.score} |")
    lines.extend(
        [
            "",
            "## Roadmap",
            "",
            *[f"- {x}" for x in sc.roadmap],
            "",
            "## Notes",
            "",
            *[f"- {n}" for n in sc.notes],
            "",
            "## Remaining limitations",
            "",
            "- No LLM planner — heuristic decomposition/discovery",
            "- Parallel sub-agents not yet scheduled",
            "- Long multi-hour soak not run → 9.6+ not claimed",
            "- LIVE-MONEY AUTONOMY NOT VERIFIED",
            "",
        ]
    )
    (REPORTS / "SOFTWARE_ENGINEERING_AUTONOMY_REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(sc.to_dict(), indent=2))
    return 0 if payload["passed"] == payload["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
