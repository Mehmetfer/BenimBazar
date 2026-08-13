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
from .f7_loop import F7ControlledLoop
from .learning import LearningMemory
from .models import ChangeProposal, LoopStage, RunStatus
from .planner import ImprovementProposal, plan_improvement
from .system_observe import diagnose_observation, observe_system

__all__ = [
    "SelfVerificationEngine",
    "run_self_verification",
    "F7ControlledLoop",
    "LearningMemory",
    "ImprovementProposal",
    "plan_improvement",
    "observe_system",
    "diagnose_observation",
    "LoopStage",
    "RunStatus",
    "ChangeProposal",
]
