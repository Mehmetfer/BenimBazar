"""Resource / iteration budgets — prevent runaway autonomy."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


class BudgetExceeded(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass
class AutonomyBudget:
    max_iterations: int = 5
    max_files_changed: int = 8
    max_test_runtime_sec: float = 120.0
    max_failed_attempts: int = 3
    max_cpu_hint: float = 0.85  # soft advisory
    max_memory_mb: int = 1024  # soft advisory
    started_at: float = field(default_factory=time.time)
    iterations: int = 0
    files_changed: int = 0
    failed_attempts: int = 0
    test_runtime_sec: float = 0.0

    def check(self) -> None:
        if self.files_changed > self.max_files_changed:
            raise BudgetExceeded("max_files_changed")
        if self.failed_attempts >= self.max_failed_attempts:
            raise BudgetExceeded("max_failed_attempts")
        if self.test_runtime_sec > self.max_test_runtime_sec:
            raise BudgetExceeded("max_test_runtime")

    def begin_iteration(self) -> None:
        if self.iterations >= self.max_iterations:
            raise BudgetExceeded("max_iterations")
        self.iterations += 1
        self.check()

    def record_files(self, n: int) -> None:
        self.files_changed += max(0, n)
        self.check()

    def record_test_runtime(self, seconds: float) -> None:
        self.test_runtime_sec += max(0.0, seconds)
        self.check()

    def record_failure(self) -> None:
        self.failed_attempts += 1
        self.check()

    def remaining_iterations(self) -> int:
        return max(0, self.max_iterations - self.iterations)
