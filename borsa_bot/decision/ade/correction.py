"""Self-correction: DETECT → CLASSIFY → RECOVER → VERIFY."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

from decision.ade.states import DecisionAction


class FailureClass(str, Enum):
    KNOWN_SAFE = "KNOWN_SAFE"
    KNOWN_UNSAFE = "KNOWN_UNSAFE"
    UNKNOWN = "UNKNOWN"
    RECOVERABLE = "RECOVERABLE"
    UNRECOVERABLE = "UNRECOVERABLE"


class CorrectionStage(str, Enum):
    DETECT = "DETECT"
    CLASSIFY = "CLASSIFY"
    RECOVER = "RECOVER"
    VERIFY = "VERIFY"


@dataclass
class CorrectionResult:
    stage: str
    failure_class: str
    recovered: bool
    verified: bool
    action: str
    details: dict[str, Any] = field(default_factory=dict)
    trail: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


ProviderProbe = Callable[[], dict[str, Any]]


def classify_failure(
    *,
    provider_ok: bool,
    data_valid: bool,
    data_fresh: bool,
    alternate_available: bool,
    kill_switch: bool,
    unknown_broker_state: bool,
) -> FailureClass:
    if kill_switch or unknown_broker_state:
        return FailureClass.UNRECOVERABLE if unknown_broker_state else FailureClass.KNOWN_UNSAFE
    if not provider_ok or not data_valid or not data_fresh:
        if alternate_available:
            return FailureClass.RECOVERABLE
        return FailureClass.KNOWN_UNSAFE
    if provider_ok and data_valid and data_fresh:
        return FailureClass.KNOWN_SAFE
    return FailureClass.UNKNOWN


def run_self_correction(
    *,
    primary_probe: ProviderProbe,
    alternate_probe: Optional[ProviderProbe] = None,
    kill_switch: bool = False,
    unknown_broker_state: bool = False,
) -> CorrectionResult:
    """DETECT → CLASSIFY → RECOVER → VERIFY. Unverified alternate → NO_TRADE."""
    trail = [CorrectionStage.DETECT.value]
    primary = primary_probe()
    provider_ok = bool(primary.get("ok"))
    data_valid = bool(primary.get("data_valid", provider_ok))
    data_fresh = bool(primary.get("data_fresh", provider_ok))
    alt_available = alternate_probe is not None

    trail.append(CorrectionStage.CLASSIFY.value)
    klass = classify_failure(
        provider_ok=provider_ok,
        data_valid=data_valid,
        data_fresh=data_fresh,
        alternate_available=alt_available,
        kill_switch=kill_switch,
        unknown_broker_state=unknown_broker_state,
    )

    if klass is FailureClass.KNOWN_SAFE:
        trail.append(CorrectionStage.VERIFY.value)
        return CorrectionResult(
            stage=CorrectionStage.VERIFY.value,
            failure_class=klass.value,
            recovered=False,
            verified=True,
            action=DecisionAction.BUY.value,  # placeholder — engine re-decides
            details={"primary": primary},
            trail=trail,
        )

    if klass in {FailureClass.KNOWN_UNSAFE, FailureClass.UNRECOVERABLE, FailureClass.UNKNOWN}:
        trail.append(CorrectionStage.VERIFY.value)
        return CorrectionResult(
            stage=CorrectionStage.VERIFY.value,
            failure_class=klass.value,
            recovered=False,
            verified=False,
            action=DecisionAction.NO_TRADE.value,
            details={"primary": primary, "halt": klass is FailureClass.UNRECOVERABLE},
            trail=trail,
        )

    # RECOVERABLE
    trail.append(CorrectionStage.RECOVER.value)
    assert alternate_probe is not None
    alt = alternate_probe()
    alt_ok = bool(alt.get("ok")) and bool(alt.get("data_valid")) and bool(alt.get("data_fresh"))
    trail.append(CorrectionStage.VERIFY.value)
    if not alt_ok:
        return CorrectionResult(
            stage=CorrectionStage.VERIFY.value,
            failure_class=klass.value,
            recovered=False,
            verified=False,
            action=DecisionAction.NO_TRADE.value,
            details={"primary": primary, "alternate": alt},
            trail=trail,
        )
    return CorrectionResult(
        stage=CorrectionStage.VERIFY.value,
        failure_class=klass.value,
        recovered=True,
        verified=True,
        action="CONTINUE",
        details={"primary": primary, "alternate": alt, "provider": alt.get("provider")},
        trail=trail,
    )
