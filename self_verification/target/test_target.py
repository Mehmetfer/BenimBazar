"""Pytest suite that runs INSIDE the sandbox against the target module."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module():
    # Prefer sandbox-local module.py next to this test file's parent target
    candidates = [
        Path.cwd() / "module.py",
        Path(__file__).resolve().parent / "module.py",
    ]
    for path in candidates:
        if path.is_file():
            spec = importlib.util.spec_from_file_location("sv_target_module", path)
            assert spec and spec.loader
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
    raise AssertionError("module.py not found in sandbox")


def test_self_check_passes():
    mod = _load_module()
    assert mod.self_check() is True
    assert mod.MARKER == "VERIFIED_OK"


def test_answer_ready_for_review():
    mod = _load_module()
    assert mod.answer() == "READY_FOR_REVIEW"
