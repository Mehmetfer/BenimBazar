"""Autonomy observation hooks for messaging health (no production mutate)."""

from __future__ import annotations

from typing import Any

from autonomy.concepts import Observation


def observe_messaging_health(*, stats: dict[str, Any] | None = None, api_errors: list[str] | None = None) -> list[Observation]:
    """Convert messaging metrics / errors into autonomy Observations."""
    out: list[Observation] = []
    for err in api_errors or []:
        out.append(
            Observation(
                source="messaging",
                kind="API_ERROR",
                message=err,
                evidence=[err],
            )
        )
    s = stats or {}
    open_reports = int(s.get("reported_messages") or 0)
    if open_reports >= 5:
        out.append(
            Observation(
                source="messaging",
                kind="MODERATION_BACKLOG",
                message=f"open_message_reports={open_reports}",
                evidence=[f"reported_messages={open_reports}"],
            )
        )
    open_tickets = int(s.get("open_support_tickets") or 0)
    if open_tickets >= 10:
        out.append(
            Observation(
                source="messaging",
                kind="SUPPORT_BACKLOG",
                message=f"open_support_tickets={open_tickets}",
                evidence=[f"open_support_tickets={open_tickets}"],
            )
        )
    if not out:
        out.append(
            Observation(
                source="messaging",
                kind="HEALTHY",
                message="messaging_ok",
                evidence=[],
            )
        )
    return out
