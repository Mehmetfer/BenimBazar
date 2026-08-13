"""GÖREV 21–22 — System self-observation + evidence-based root cause."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class ObservationKind(str, Enum):
    TEST_FAILURE = "TEST_FAILURE"
    API_ERROR = "API_ERROR"
    DECISION_ANOMALY = "DECISION_ANOMALY"
    PERFORMANCE_DEGRADATION = "PERFORMANCE_DEGRADATION"
    UNUSUAL_TRADE_PATTERN = "UNUSUAL_TRADE_PATTERN"
    REPEATED_FAILURE = "REPEATED_FAILURE"
    STALE_DATA = "STALE_DATA"
    BROKEN_DEPENDENCY = "BROKEN_DEPENDENCY"
    MISSING_CONFIGURATION = "MISSING_CONFIGURATION"
    HEALTHY = "HEALTHY"


@dataclass
class SystemObservation:
    kind: ObservationKind
    source: str
    message: str
    evidence: Dict[str, Any] = field(default_factory=dict)
    severity: str = "medium"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind.value,
            "source": self.source,
            "message": self.message,
            "evidence": dict(self.evidence),
            "severity": self.severity,
            "timestamp": self.timestamp,
        }


@dataclass
class RootCauseDiagnosis:
    category: str
    root_cause: str
    suggested_fix: str
    confidence: float
    evidence: List[str] = field(default_factory=list)
    llm_trusted: bool = False  # never accept LLM alone

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category,
            "root_cause": self.root_cause,
            "suggested_fix": self.suggested_fix,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
            "llm_trusted": False,
            "evidence_required": True,
        }


def observe_system(
    *,
    test_failures: Optional[List[str]] = None,
    api_errors: Optional[List[str]] = None,
    decision_stats: Optional[Dict[str, Any]] = None,
    dependency_ok: bool = True,
    config_present: bool = True,
    stale_symbols: Optional[List[str]] = None,
) -> List[SystemObservation]:
    """Normalize heterogeneous health signals into Observation objects."""
    out: List[SystemObservation] = []
    for msg in test_failures or []:
        out.append(
            SystemObservation(
                kind=ObservationKind.TEST_FAILURE,
                source="test_runner",
                message=msg,
                evidence={"failure": msg},
                severity="high",
            )
        )
    for msg in api_errors or []:
        out.append(
            SystemObservation(
                kind=ObservationKind.API_ERROR,
                source="api",
                message=msg,
                evidence={"error": msg},
                severity="high",
            )
        )
    if stale_symbols:
        out.append(
            SystemObservation(
                kind=ObservationKind.STALE_DATA,
                source="market_provider",
                message=f"stale_symbols={stale_symbols}",
                evidence={"symbols": list(stale_symbols)},
                severity="medium",
            )
        )
    if not dependency_ok:
        out.append(
            SystemObservation(
                kind=ObservationKind.BROKEN_DEPENDENCY,
                source="deps",
                message="dependency_check_failed",
                evidence={"dependency_ok": False},
                severity="critical",
            )
        )
    if not config_present:
        out.append(
            SystemObservation(
                kind=ObservationKind.MISSING_CONFIGURATION,
                source="config",
                message="required_config_missing",
                evidence={"config_present": False},
                severity="high",
            )
        )
    stats = decision_stats or {}
    if stats.get("no_trade_ratio", 0) > 0.95 and stats.get("cycles", 0) >= 10:
        out.append(
            SystemObservation(
                kind=ObservationKind.DECISION_ANOMALY,
                source="f6_decision",
                message="almost_all_no_trade",
                evidence=dict(stats),
                severity="medium",
            )
        )
    if stats.get("win_rate") is not None and stats.get("trades", 0) >= 8:
        if float(stats["win_rate"]) < 0.3:
            out.append(
                SystemObservation(
                    kind=ObservationKind.PERFORMANCE_DEGRADATION,
                    source="paper_trading",
                    message="win_rate_below_30pct",
                    evidence=dict(stats),
                    severity="high",
                )
            )
    if stats.get("consecutive_losses", 0) >= 5:
        out.append(
            SystemObservation(
                kind=ObservationKind.UNUSUAL_TRADE_PATTERN,
                source="paper_trading",
                message="consecutive_losses>=5",
                evidence=dict(stats),
                severity="high",
            )
        )
    if stats.get("repeat_failure_count", 0) >= 3:
        out.append(
            SystemObservation(
                kind=ObservationKind.REPEATED_FAILURE,
                source="self_verification",
                message="same_failure_repeated",
                evidence=dict(stats),
                severity="high",
            )
        )
    if not out:
        out.append(
            SystemObservation(
                kind=ObservationKind.HEALTHY,
                source="system",
                message="no_issues_detected",
                evidence={},
                severity="low",
            )
        )
    return out


def diagnose_observation(obs: SystemObservation) -> RootCauseDiagnosis:
    """CLASSIFY → DIAGNOSE with mandatory evidence (LLM not trusted alone)."""
    evidence = [f"kind={obs.kind.value}", f"source={obs.source}", obs.message]
    for k, v in obs.evidence.items():
        evidence.append(f"{k}={v}")

    if obs.kind == ObservationKind.TEST_FAILURE:
        msg = obs.message.lower()
        if "ui" in msg or "flutter" in msg or "widget" in msg:
            return RootCauseDiagnosis(
                category="UI",
                root_cause="UI initialization or widget test failure",
                suggested_fix="Fix missing dependency / init binding; add regression test",
                confidence=0.75,
                evidence=evidence,
            )
        return RootCauseDiagnosis(
            category="TEST",
            root_cause="Automated test failure",
            suggested_fix="Reproduce locally, fix assertion or code, keep regression",
            confidence=0.7,
            evidence=evidence,
        )
    if obs.kind == ObservationKind.PERFORMANCE_DEGRADATION:
        return RootCauseDiagnosis(
            category="STRATEGY",
            root_cause="Trading performance degraded — possible regime/strategy mismatch",
            suggested_fix="Propose defensive sizing / NO_TRADE in mismatched regimes (paper)",
            confidence=0.65,
            evidence=evidence,
        )
    if obs.kind == ObservationKind.STALE_DATA:
        return RootCauseDiagnosis(
            category="DATA",
            root_cause="Market data freshness below threshold",
            suggested_fix="Block trading on STALE; refresh provider / widen NO_TRADE",
            confidence=0.85,
            evidence=evidence,
        )
    if obs.kind == ObservationKind.BROKEN_DEPENDENCY:
        return RootCauseDiagnosis(
            category="DEPENDENCY",
            root_cause="Broken or missing dependency",
            suggested_fix="Restore dependency pin; fail closed until resolved",
            confidence=0.9,
            evidence=evidence,
        )
    if obs.kind == ObservationKind.MISSING_CONFIGURATION:
        return RootCauseDiagnosis(
            category="CONFIG",
            root_cause="Required configuration missing",
            suggested_fix="Add config validation gate; refuse unsafe defaults",
            confidence=0.9,
            evidence=evidence,
        )
    if obs.kind == ObservationKind.HEALTHY:
        return RootCauseDiagnosis(
            category="NONE",
            root_cause="none",
            suggested_fix="no_change",
            confidence=1.0,
            evidence=evidence,
        )
    return RootCauseDiagnosis(
        category="GENERAL",
        root_cause=obs.message,
        suggested_fix="Create ImprovementProposal with evidence; sandbox only",
        confidence=0.55,
        evidence=evidence,
    )
