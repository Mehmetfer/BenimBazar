"""F7 Controlled Self-Verification — sandbox only.

Does NOT:
- mutate production tree in-place
- self-deploy
- enable LIVE / high autonomy (F8)

Does:
- OBSERVE → DETECT → DIAGNOSE → PLAN → PROPOSE → TEST → VERIFY → ROLLBACK → REPORT
- write every step to an append-only audit log
- reach READY_FOR_REVIEW only after sandbox tests pass
"""

from .engine import SelfVerificationEngine, run_self_verification
from .models import LoopStage, RunStatus, ChangeProposal

__all__ = [
    "SelfVerificationEngine",
    "run_self_verification",
    "LoopStage",
    "RunStatus",
    "ChangeProposal",
]
