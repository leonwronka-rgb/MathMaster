from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException, Request


class InMemoryRateLimiter:
    """Single-process sliding-window limiter; deploy one worker per instance."""

    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()
        self._checks = 0

    def check(self, key: str, *, limit: int, window_seconds: int) -> None:
        now = time.monotonic()
        with self._lock:
            self._checks += 1
            if self._checks % 1_000 == 0:
                cutoff = now - window_seconds
                for existing_key in tuple(self._events):
                    events_for_key = self._events[existing_key]
                    while events_for_key and events_for_key[0] <= cutoff:
                        events_for_key.popleft()
                    if not events_for_key:
                        self._events.pop(existing_key, None)
            events = self._events[key]
            while events and events[0] <= now - window_seconds:
                events.popleft()
            if len(events) >= limit:
                raise HTTPException(status_code=429, detail="Rate limit exceeded.")
            events.append(now)


def client_key(request: Request, suffix: str) -> str:
    client = request.client.host if request.client else "unknown"
    return f"{client}:{suffix}"

