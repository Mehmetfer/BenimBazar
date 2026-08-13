"""CHANGE X observability helpers — no secrets/tokens/passwords."""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Iterator


def safe_log_fields(
    *,
    actor_id: int | None,
    action: str,
    entity: str | None = None,
    entity_id: int | None = None,
    result: str = "ok",
    error_code: str | None = None,
    duration_ms: float | None = None,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    return {
        "actor_id": actor_id,
        "action": action,
        "entity": entity,
        "entity_id": entity_id,
        "result": result,
        "error_code": error_code,
        "duration_ms": duration_ms,
        "correlation_id": correlation_id,
    }


@contextmanager
def timed() -> Iterator[dict[str, float]]:
    box: dict[str, float] = {"duration_ms": 0.0}
    start = time.perf_counter()
    try:
        yield box
    finally:
        box["duration_ms"] = (time.perf_counter() - start) * 1000.0
