"""Verify-8 challenges: E2E, completeness, failure recovery, lesson replay."""

from __future__ import annotations

from pathlib import Path

from autonomy.completeness import scan_symbol
from autonomy.failure import begin_failure_analysis, record_hypothesis, record_patch, record_retest, record_root_cause
from autonomy.gates import run_g3_typecheck
from autonomy.lessons import Lesson, list_lessons, required_regression_tests, save_lesson, seed_known_lessons
from autonomy.self_review import self_review
from config.settings import settings
from crypto.reliability import crypto_signals_permitted
from data.integrity import DataSourceKind


# --- G3 HARD ---


def test_g3_typecheck_is_hard_pass():
    g = run_g3_typecheck()
    assert g.ok is True, g.detail
    assert "soft-pass" not in g.detail.lower()
    assert "HARD FAIL" not in g.detail


# --- E2E humanless acceptance (feature already implemented under acceptance-only brief) ---


def test_e2e_reliability_gate_blocks_unreliable_md():
    """Acceptance: unreliable crypto MD must not permit signals; LIVE stays locked."""
    assert settings.live_broker_enabled is False

    class Stale:
        def has_market_data(self):
            return True

        def is_fresh(self, max_age_sec: float = 30.0):
            return False

        kind = DataSourceKind.LIVE

    ok, reason = crypto_signals_permitted(Stale(), crypto_enabled=True, signals_enabled=True)
    assert ok is False
    assert "STALE" in reason


def test_e2e_service_scan_empty_when_unreliable():
    from crypto.service import CryptoFoundationService

    svc = CryptoFoundationService()

    class Bad:
        is_stub = False
        is_real_provider = True
        kind = DataSourceKind.UNAVAILABLE
        provider_id = "bad"

        def has_market_data(self):
            return False

        def is_fresh(self, max_age_sec: float = 30.0):
            return False

        def list_symbols(self):
            return ["BTC_USDT"]

    svc.provider = Bad()
    # Even if signals were conceptually desired, unreliable MD → empty
    assert crypto_signals_permitted(svc.provider, crypto_enabled=True, signals_enabled=True)[0] is False
    assert svc.scan() == []


# --- Completeness challenge ---


def test_completeness_reliability_surfaces():
    rep = scan_symbol("crypto_signals_permitted")
    assert rep.ok
    assert any("reliability" in d for d in rep.definition_files + rep.call_sites)
    assert any("test_" in t for t in rep.test_files)
    # factory / service wiring
    svc = scan_symbol("CryptoFoundationService")
    assert svc.call_sites or svc.definition_files


def test_completeness_env_example_documents_crypto_provider():
    text = (Path(__file__).resolve().parents[1] / ".env.example").read_text(encoding="utf-8")
    assert "CRYPTO_PROVIDER" in text
    assert "LIVE_BROKER_ENABLED=false" in text


# --- Failure recovery challenge ---


def test_failure_recovery_loop_records_minimal_patch():
    case = begin_failure_analysis(
        "tests/test_verify8_challenges.py::test_e2e_reliability_gate_blocks_unreliable_md",
        "AssertionError: expected STALE block",
    )
    record_hypothesis(case, "is_fresh ignored in gate")
    record_root_cause(case, "crypto_signals_permitted must check is_fresh before permitting")
    record_patch(case, "gate returns STALE_OR_DISCONNECTED when is_fresh False")
    record_retest(case, True, regression_nodes=["tests/test_domain_invariants.py::test_inv_unreliable_crypto_blocks_signal_emission"])
    assert case.retest_ok is True
    assert case.root_cause
    assert len(case.patch_summary) < 200  # minimal patch narrative


def test_failure_recovery_injected_bug_caught_by_regression(tmp_path: Path):
    """Simulate broken gate → regression test fails → restore → pass."""
    # Broken behavior
    def broken_gate(provider, *, crypto_enabled, signals_enabled, max_age_sec=30.0):
        return True, "OK"  # wrongly permits

    class Bad:
        def has_market_data(self):
            return False

        def is_fresh(self, max_age_sec: float = 30.0):
            return False

        kind = DataSourceKind.UNAVAILABLE

    ok_bad, _ = broken_gate(Bad(), crypto_enabled=True, signals_enabled=True)
    assert ok_bad is True  # injected failure class
    # Real gate must catch
    ok_good, reason = crypto_signals_permitted(Bad(), crypto_enabled=True, signals_enabled=True)
    assert ok_good is False
    assert reason != "OK"


# --- Lesson store replay ---


def test_lesson_store_catches_repeated_error_class():
    seed_known_lessons()
    save_lesson(
        Lesson(
            id="unreliable-crypto-signals",
            title="Unreliable crypto MD must not emit signals",
            error_class="SilentDomainError",
            root_cause="Signals emitted without freshness/kind checks",
            fix_summary="crypto_signals_permitted gate in service.scan/_signal_engine",
            regression_test="tests/test_domain_invariants.py::test_inv_unreliable_crypto_blocks_signal_emission",
            architectural_decision="Fail-closed reliability before CryptoSignalEngine",
            prevents=["signal emission on UNAVAILABLE/STALE crypto MD"],
        )
    )
    regs = required_regression_tests()
    assert any("test_inv_unreliable_crypto_blocks_signal_emission" in r for r in regs)
    assert any(l.id == "unreliable-crypto-signals" for l in list_lessons())


def test_self_review_on_reliability_change():
    report = self_review(
        ["crypto/reliability.py", "crypto/service.py", "tests/test_domain_invariants.py"],
        run_tests=False,
    )
    assert report.ok is True


def test_live_still_locked_after_verify8():
    assert settings.live_broker_enabled is False
