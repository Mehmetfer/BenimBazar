"""FAZ 6 — Level 1→8 acceptance. Names ≠ success; only evidence."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


class LevelStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"


@dataclass
class LevelResult:
    level: int
    name: str
    status: LevelStatus
    evidence: str
    criteria: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d


LEVEL_DEFS: dict[int, dict[str, Any]] = {
    1: {
        "name": "Basic task execution",
        "criteria": ["app imports", "settings load", "TradingService boots"],
        "tests": [
            "tests/test_level_gates.py::test_l1_app_imports_and_settings",
            "tests/test_core.py",
        ],
    },
    2: {
        "name": "Test-and-fix",
        "criteria": ["HTTP MD fail-closed", "parse_ts no invented now", "failure protocol module"],
        "tests": [
            "tests/test_level_gates.py::test_l2_http_source_meta_accepts_datetime",
            "tests/test_level_gates.py::test_l2_parse_ts_never_invents_now",
            "tests/test_level_gates.py::test_l2_http_bars_fail_closed_no_stale_cache",
            "tests/test_autonomy_protocol.py::test_failure_protocol_steps",
        ],
    },
    3: {
        "name": "Multi-module coordination",
        "criteria": ["MTF no lookahead", "BIST/CRYPTO isolation"],
        "tests": [
            "tests/test_level_gates.py::test_l3_mtf_drops_incomplete_bucket_no_lookahead",
            "tests/test_level_gates.py::test_l3_same_input_same_mtf",
            "tests/test_data_source_isolation.py",
            "tests/test_crypto_foundation.py::test_bist_trading_service_unaffected_by_crypto_package",
        ],
    },
    4: {
        "name": "Failure → diagnosis → recovery",
        "criteria": ["provider offline safe", "kill switch blocks", "confidence ≠ calibrated p"],
        "tests": [
            "tests/test_level_gates.py::test_failure_matrix_safe",
            "tests/test_level_gates.py::test_l4_confidence_not_calibrated_probability",
            "tests/test_level_gates.py::test_l5_kill_switch_blocks",
        ],
    },
    5: {
        "name": "Systematic gap detection",
        "criteria": ["self-review engine", "completeness scanner", "risk empty fail-closed"],
        "tests": [
            "tests/test_autonomy_protocol.py::test_self_review_catches_syntax",
            "tests/test_autonomy_protocol.py::test_completeness_scan_symbol",
            "tests/test_level_gates.py::test_l5_risk_empty_verdict_fail_closed",
        ],
    },
    6: {
        "name": "Persistent lesson / regression system",
        "criteria": ["lesson store", "regression gate list", "LIVE locked"],
        "tests": [
            "tests/test_autonomy_protocol.py::test_lesson_store_roundtrip",
            "tests/test_autonomy_protocol.py::test_lessons_seed_and_regression_list",
            "tests/test_level_gates.py::test_l6_live_broker_locked",
            "tests/test_autonomy_protocol.py::test_live_broker_remains_locked",
        ],
    },
    7: {
        "name": "Shadow/paper closed-loop verification",
        "criteria": ["Level7 engine paper-only", "AI before entries", "no LIVE unlock"],
        "tests": [
            "tests/test_level7.py",
            "tests/test_level_gates.py::test_l7_ai_before_entries_in_source_file",
        ],
    },
    8: {
        "name": "All prior levels measurable + safe together",
        "criteria": [
            "ContinuousLearningEngine acceptance chain",
            "auto_promoted is False",
            "full_level8_claimed is False unless all gates prove otherwise",
            "protocol gates G1–G8",
        ],
        "tests": [
            "tests/test_level_gates.py::test_l8_acceptance_no_auto_promote",
            "tests/test_level8.py",
            "tests/test_autonomy_protocol.py::test_level8_not_claimed_without_evidence",
        ],
    },
}


def _run_tests(nodes: list[str], timeout: int = 180) -> tuple[bool, str]:
    existing = []
    for n in nodes:
        path = n.split("::")[0]
        if (ROOT / path).exists():
            existing.append(n)
    if not existing:
        return False, "no test files found"
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--tb=line", *existing],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
        env={**__import__("os").environ, "PYTHONPATH": str(ROOT)},
    )
    return proc.returncode == 0, ((proc.stdout or "") + (proc.stderr or ""))[-2000:]


def evaluate_levels(*, stop_on_fail: bool = True, max_level: int = 8) -> list[LevelResult]:
    """Evaluate L1→L8 in order. If stop_on_fail, do not advance after FAIL."""
    results: list[LevelResult] = []
    for lvl in range(1, max_level + 1):
        meta = LEVEL_DEFS[lvl]
        if stop_on_fail and results and results[-1].status == LevelStatus.FAIL:
            results.append(
                LevelResult(
                    level=lvl,
                    name=meta["name"],
                    status=LevelStatus.SKIP,
                    evidence="skipped: previous level FAILED",
                    criteria=list(meta["criteria"]),
                )
            )
            continue
        ok, log = _run_tests(list(meta["tests"]))
        results.append(
            LevelResult(
                level=lvl,
                name=meta["name"],
                status=LevelStatus.PASS if ok else LevelStatus.FAIL,
                evidence=log if not ok else f"pytest PASS: {', '.join(meta['tests'][:3])}…",
                criteria=list(meta["criteria"]),
            )
        )
    return results
