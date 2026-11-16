from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import Any


class EventBus:
    """Prosty synchroniczny mechanizm publikowania zdarzeń aplikacji."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callable[[Any], None]]] = defaultdict(list)

    def subscribe(self, event_name: str, callback: Callable[[Any], None]) -> None:
        if callback not in self._subscribers[event_name]:
            self._subscribers[event_name].append(callback)

    def unsubscribe(self, event_name: str, callback: Callable[[Any], None]) -> None:
        subscribers = self._subscribers.get(event_name)
        if subscribers is None:
            return
        try:
            subscribers.remove(callback)
        except ValueError:
            return
        if not subscribers:
            del self._subscribers[event_name]

    def publish(self, event_name: str, payload: Any = None) -> None:
        for callback in tuple(self._subscribers.get(event_name, ())):
            callback(payload)