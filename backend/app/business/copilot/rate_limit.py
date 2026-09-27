"""Conservative process-local request bound for synthetic demo Copilot."""

from __future__ import annotations

import threading
import time
from collections import deque

from app.core.exceptions import CopilotRateLimitedError


class LocalCopilotRateLimiter:
    """Per-subject rolling minute; fail closed when the local table is full.

    Only used in local synthetic demo. Production needs a distributed limiter
    before enabling the feature across multiple backend replicas.
    """

    def __init__(self, *, limit: int) -> None:
        self._limit = limit
        self._times: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, subject: str) -> None:
        now = time.monotonic()
        with self._lock:
            if len(self._times) >= 1024:
                self._times = {
                    key: stamps
                    for key, stamps in self._times.items()
                    if stamps and stamps[-1] > now - 60
                }
            if subject not in self._times and len(self._times) >= 1024:
                raise CopilotRateLimitedError()
            stamps = self._times.setdefault(subject, deque())
            while stamps and stamps[0] <= now - 60:
                stamps.popleft()
            if len(stamps) >= self._limit:
                raise CopilotRateLimitedError()
            stamps.append(now)
