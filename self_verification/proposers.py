"""Build ChangeProposal objects — never apply to production."""

from __future__ import annotations

from .models import ChangeProposal, FilePatch, new_proposal_id
from .probes import Diagnosis, Observation


FIXED_MODULE = '''\
"""Self-verification target module (sandbox fixture)."""

MARKER = "VERIFIED_OK"


def self_check() -> bool:
    """Return True when the controlled defect has been repaired."""
    return MARKER == "VERIFIED_OK"


def answer() -> str:
    return "READY_FOR_REVIEW"
'''


def propose_self_verification_fix(obs: Observation, diagnosis: Diagnosis) -> ChangeProposal:
    old = obs.files.get("module.py", "")
    return ChangeProposal(
        proposal_id=new_proposal_id(),
        title="Repair self-verification target defect",
        rationale=f"{diagnosis.root_cause} → {diagnosis.suggested_fix}",
        patches=[
            FilePatch(
                path="module.py",
                old_content=old,
                new_content=FIXED_MODULE,
                description="Flip BROKEN self_check to VERIFIED_OK",
            )
        ],
        target="self-verification",
        applies_to_production=False,
        deployment_allowed=False,
    )


def propose_bad_fix(obs: Observation) -> ChangeProposal:
    """Failure-injection proposal that keeps the defect (for rollback tests)."""
    old = obs.files.get("module.py", "")
    bad = old.replace("intentional defect", "still broken on purpose")
    if bad == old:
        bad = old + "\n# still broken\n"
    return ChangeProposal(
        proposal_id=new_proposal_id(),
        title="Injected bad fix (failure injection)",
        rationale="Deliberately incorrect patch to exercise ROLLBACK",
        patches=[
            FilePatch(
                path="module.py",
                old_content=old,
                new_content=bad,
                description="Keep failing self_check",
            )
        ],
        target="self-verification",
        applies_to_production=False,
        deployment_allowed=False,
    )
