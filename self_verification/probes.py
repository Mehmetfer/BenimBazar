"""OBSERVE / DETECT / DIAGNOSE helpers for the self-verification target."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class Observation:
    target: str
    files: dict[str, str]
    markers: dict[str, bool]


@dataclass
class Detection:
    defect_found: bool
    code: str
    message: str
    evidence: dict


@dataclass
class Diagnosis:
    root_cause: str
    suggested_fix: str
    confidence: float


def observe_target(root: Path) -> Observation:
    """Read sandbox/source target files for the self-verification fixture."""
    files: dict[str, str] = {}
    for name in ("module.py", "EXPECTED.txt"):
        path = root / name
        if path.is_file():
            files[name] = path.read_text(encoding="utf-8")
    markers = {
        "has_module": "module.py" in files,
        "has_expected": "EXPECTED.txt" in files,
        "broken_marker": "BROKEN" in files.get("module.py", ""),
        "fixed_marker": "VERIFIED_OK" in files.get("module.py", ""),
    }
    return Observation(target="self-verification", files=files, markers=markers)


def detect_defect(obs: Observation) -> Detection:
    if not obs.markers.get("has_module"):
        return Detection(True, "MISSING_MODULE", "module.py absent", {"markers": obs.markers})
    body = obs.files.get("module.py", "")
    if "BROKEN" in body or "return False  # intentional defect" in body:
        return Detection(
            True,
            "SELF_CHECK_FAILING",
            "Self-verification target reports intentional defect",
            {"snippet": body[:200]},
        )
    if "def self_check" not in body:
        return Detection(True, "MISSING_SELF_CHECK", "self_check() missing", {})
    return Detection(False, "OK", "No defect detected", {})


def diagnose(detection: Detection) -> Diagnosis:
    if not detection.defect_found:
        return Diagnosis("none", "no_change", 1.0)
    if detection.code == "SELF_CHECK_FAILING":
        return Diagnosis(
            root_cause="Intentional BROKEN marker / failing self_check for F7 demo",
            suggested_fix="Replace BROKEN path with VERIFIED_OK returning True",
            confidence=0.95,
        )
    return Diagnosis(
        root_cause=detection.message,
        suggested_fix="Restore self_check contract",
        confidence=0.7,
    )
