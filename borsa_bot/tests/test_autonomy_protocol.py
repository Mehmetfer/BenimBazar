"""Autonomy protocol — measurable proof tests (research/paper only; LIVE locked)."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from autonomy.completeness import bist_crypto_isolation_check, scan_symbol
from autonomy.failure import begin_failure_analysis, protocol_steps, record_hypothesis, record_retest
from autonomy.lessons import Lesson, list_lessons, load_lesson, required_regression_tests, save_lesson, seed_known_lessons
from autonomy.loop import LOOP_STEPS, loop_complete
from autonomy.self_review import check_live_broker_not_unlocked, check_syntax, self_review
from config.settings import settings


def test_live_broker_remains_locked():
    assert bool(getattr(settings, "live_broker_enabled", False)) is False
    assert bool(getattr(settings, "live_confirmed", False)) is False


def test_failure_protocol_steps():
    steps = protocol_steps()
    assert len(steps) >= 8
    assert any("hypothesis" in s.lower() for s in steps)
    case = begin_failure_analysis("tests/x.py::test_y", "AssertionError: boom")
    record_hypothesis(case, "env pollution")
    record_retest(case, True, regression_nodes=["tests/x.py::test_y"])
    assert case.hypothesis == "env pollution"
    assert case.retest_ok is True


def test_lesson_store_roundtrip(tmp_path: Path, monkeypatch):
    import autonomy.lessons as lessons_mod

    monkeypatch.setattr(lessons_mod, "LESSONS_DIR", tmp_path)
    path = save_lesson(
        Lesson(
            id="unit-demo",
            title="demo",
            error_class="AssertionError",
            root_cause="test",
            fix_summary="fix",
            regression_test="tests/test_autonomy_protocol.py::test_lesson_store_roundtrip",
            architectural_decision="lessons are data",
        )
    )
    assert path.is_file()
    loaded = load_lesson("unit-demo")
    assert loaded is not None
    assert loaded.id == "unit-demo"
    assert "test_lesson_store_roundtrip" in required_regression_tests()[0]


def test_lessons_seed_and_regression_list():
    paths = seed_known_lessons()
    assert len(paths) >= 5
    lessons = list_lessons()
    assert any(l.id == "live-broker-never-auto-unlock" for l in lessons)
    regs = required_regression_tests()
    assert any("test_live_broker_remains_locked" in r for r in regs)


def test_self_review_catches_syntax(tmp_path: Path):
    bad = tmp_path / "bad.py"
    bad.write_text("def broken(\n", encoding="utf-8")
    findings = check_syntax([bad])
    assert any(f.severity == "error" for f in findings)
    report = self_review([bad], run_tests=False)
    assert report.ok is False


def test_self_review_blocks_live_unlock(tmp_path: Path):
    evil = tmp_path / "evil.py"
    evil.write_text('live_broker_enabled = True\n', encoding="utf-8")
    findings = check_live_broker_not_unlocked([evil])
    assert any(f.code == "LIVE_LOCK" for f in findings)


def test_completeness_scan_symbol():
    rep = scan_symbol("create_crypto_provider")
    assert rep.ok is True
    assert rep.call_sites or rep.definition_files
    assert any("factory" in c or "providers" in c for c in (rep.call_sites + rep.definition_files))
    iso = bist_crypto_isolation_check()
    assert "ok" in iso


def test_loop_requires_all_steps():
    assert loop_complete(LOOP_STEPS) is True
    assert loop_complete(["PLAN", "IMPLEMENT"]) is False


def test_level8_not_claimed_without_evidence():
    """Folder presence ≠ Level 8 success."""
    from level8.engine import ContinuousLearningEngine
    from level8.store import Level8Store
    from strategy.service import TradingService

    eng = ContinuousLearningEngine(TradingService(), store=Level8Store(path=Path("/tmp/a8_proto.db")))
    out = eng.run_acceptance_chain()
    assert out["auto_promoted"] is False
    assert out["scorecard"]["full_level8_claimed"] is False
    # Protocol must not flip LIVE
    assert bool(settings.live_broker_enabled) is False


def test_gates_module_import_and_g1():
    from autonomy.gates import run_gates

    # Narrow unit-only style: changed autonomy lessons file, skip heavy regression for speed
    suite = run_gates(
        changed_files=["autonomy/lessons.py"],
        unit_nodes=["tests/test_autonomy_protocol.py::test_live_broker_remains_locked"],
        integration_nodes=["tests/test_level_gates.py::test_l6_live_broker_locked"],
        smoke_nodes=["tests/test_level_gates.py::test_l1_app_imports_and_settings"],
        run_full_regression=False,
    )
    g1 = next(g for g in suite.gates if g.name == "G1_syntax_import")
    assert g1.ok is True


def test_scorecard_does_not_claim_8_without_levels():
    from autonomy.levels import LevelResult, LevelStatus
    from autonomy.scorecard import score_autonomy

    levels = [
        LevelResult(1, "x", LevelStatus.PASS, "e"),
        LevelResult(2, "x", LevelStatus.FAIL, "e"),
    ]
    card = score_autonomy(
        level_results=levels,
        gates_ok=True,
        lesson_count=5,
        self_review_ok=True,
        baseline_pass=297,
        baseline_fail=0,
        live_locked=True,
    )
    assert card.overall < 8.0
    assert card.verdict == "AUTONOMY 8+ NOT VERIFIED"


def test_crypto_chart_fail_closed_unknown_symbol():
    """Regression: unknown venue symbol must not 500."""
    from crypto.providers.public_exchanges import OkxPublicProvider
    from crypto.service import CryptoFoundationService

    svc = CryptoFoundationService()
    # Force a public provider path if crypto disabled — still must not raise
    if not settings.crypto_enabled:
        chart = svc.chart("BTC_TL", timeframe="15m")
        assert "candles" in chart or "bars" in chart or isinstance(chart, dict)
    else:
        svc.provider = OkxPublicProvider()
        svc.provider.tick()
        chart = svc.chart("BTC_TL", timeframe="15m")
        assert isinstance(chart, dict)
