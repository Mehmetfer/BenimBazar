"""Persistent lesson store — Hata → Root Cause → Lesson → Regression Test → CI Gate.

Never self-modifies production trading code. Lessons are data + required tests.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LESSONS_DIR = Path(__file__).resolve().parent / "lessons"


@dataclass
class Lesson:
    id: str
    title: str
    error_class: str
    root_cause: str
    fix_summary: str
    regression_test: str  # pytest node id or path::name
    architectural_decision: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    prevents: list[str] = field(default_factory=list)
    live_trading_impact: str = "NONE — lessons never unlock LIVE broker"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def lessons_dir() -> Path:
    LESSONS_DIR.mkdir(parents=True, exist_ok=True)
    return LESSONS_DIR


def lesson_path(lesson_id: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9_\-]", "_", lesson_id.strip())
    return lessons_dir() / f"{safe}.json"


def save_lesson(lesson: Lesson) -> Path:
    path = lesson_path(lesson.id)
    path.write_text(json.dumps(lesson.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def load_lesson(lesson_id: str) -> Lesson | None:
    path = lesson_path(lesson_id)
    if not path.is_file():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    return Lesson(**{k: raw[k] for k in Lesson.__dataclass_fields__ if k in raw})


def list_lessons() -> list[Lesson]:
    out: list[Lesson] = []
    for p in sorted(lessons_dir().glob("*.json")):
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            out.append(Lesson(**{k: raw[k] for k in Lesson.__dataclass_fields__ if k in raw}))
        except Exception:  # noqa: BLE001
            continue
    return out


def required_regression_tests() -> list[str]:
    """All regression tests referenced by lessons — CI gate input."""
    tests: list[str] = []
    for lesson in list_lessons():
        t = (lesson.regression_test or "").strip()
        if t and t not in tests:
            tests.append(t)
    return tests


def seed_known_lessons() -> list[Path]:
    """Seed lessons from proven failures in this repo (idempotent overwrite of seeds)."""
    seeds = [
        Lesson(
            id="stamp-kwargs-drift",
            title="stamp_quote_defaults / stamp_bar_defaults kind= kwargs drift",
            error_class="TypeError",
            root_cause=(
                "Caller passed kind= but stamp_* signatures only accept provider/origin "
                "(http_live had the same stale call). Crypto public providers copied the bug."
            ),
            fix_summary="Remove kind=; set data_source_kind on the model before stamp.",
            regression_test="tests/test_crypto_public_md.py::test_okx_provider_live_smoke",
            architectural_decision="Contract helpers must stay the single source of stamp kwargs; callers match signatures.",
            prevents=["unexpected keyword argument 'kind'", "quote stamp TypeError"],
        ),
        Lesson(
            id="env-pollution-crypto-enabled",
            title="Local .env CRYPTO_ENABLED=true breaks default-off tests",
            error_class="AssertionError",
            root_cause="Runtime enablement was written into .env; settings load at import; tests expected default false.",
            fix_summary="Keep .env default CRYPTO_ENABLED=false; enable via process env at server start only.",
            regression_test="tests/test_crypto_foundation.py::test_default_crypto_disabled",
            architectural_decision="Dev toggles for demos must not mutate committed defaults or permanent .env test assumptions.",
            prevents=["crypto_enabled True while tests expect False"],
        ),
        Lesson(
            id="crypto-unknown-symbol-fail-closed",
            title="Crypto detail/chart raised 500 on unknown venue symbol",
            error_class="RuntimeError",
            root_cause="OKX has no BTC_TL; get_bars raised; chart fallback also raised → API 500.",
            fix_summary="chart() catches both get_bars_tf and get_bars; returns empty chart with note.",
            regression_test="tests/test_crypto_ui.py::test_crypto_detail_and_chart_api",
            architectural_decision="NO_MARKET_DATA must fail closed to empty payload, never uncaught 500 on detail UI.",
            prevents=["NO_MARKET_DATA uncaught in /api/crypto/detail"],
        ),
        Lesson(
            id="governor-halt-is-valid",
            title="Governor TRADING_HALT treated as test failure",
            error_class="AssertionError",
            root_cause="Paper ledger weekly loss tripped halt; test required NORMAL only.",
            fix_summary="Accept NORMAL|CAUTION|REDUCED_RISK|TRADING_HALT as valid governor states.",
            regression_test="tests/test_master_v2.py::test_engine_status_exposes_level_and_governor",
            architectural_decision="Fail-closed governor states are success for safety tests.",
            prevents=["assert state == NORMAL while halt is correct"],
        ),
        Lesson(
            id="live-broker-never-auto-unlock",
            title="LIVE broker must stay locked under autonomy protocol",
            error_class="SafetyViolation",
            root_cause="Autonomy improvements must not flip LIVE_BROKER_ENABLED or bypass RiskEngine.",
            fix_summary="Hard assert live_broker_enabled is False in autonomy acceptance.",
            regression_test="tests/test_autonomy_protocol.py::test_live_broker_remains_locked",
            architectural_decision="research → test → paper → shadow only; LIVE requires human.",
            prevents=["LIVE_BROKER_ENABLED auto true", "broker safety bypass"],
        ),
    ]
    return [save_lesson(s) for s in seeds]
