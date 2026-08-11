from __future__ import annotations

from collections.abc import Callable
from typing import Any

from alerts.events import TradingAlertEvent

Listener = Callable[[TradingAlertEvent], Any]


class EventBus:
    """In-process pub/sub. Trading code publishes; AlertManager subscribes.

    Failures in listeners must never raise into trading callers when wrapped.
    """

    def __init__(self) -> None:
        self._listeners: list[Listener] = []

    def subscribe(self, listener: Listener) -> None:
        if listener not in self._listeners:
            self._listeners.append(listener)

    def unsubscribe(self, listener: Listener) -> None:
        self._listeners = [x for x in self._listeners if x is not listener]

    def publish(self, event: TradingAlertEvent) -> list[Exception]:
        errors: list[Exception] = []
        for listener in list(self._listeners):
            try:
                listener(event)
            except Exception as exc:  # noqa: BLE001 — isolation from trading
                errors.append(exc)
        return errors
