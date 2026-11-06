"""Simple in-process sliding-window rate limiter.

Suitable for the single-process deployment GuessTheFrame targets. The interface
is intentionally small so it can be replaced by a Redis-backed limiter later.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque

from app.core.errors import AppError


class SlidingWindowLimiter:
    def __init__(self, max_attempts: int, window_seconds: int) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def hit(self, key: str) -> None:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        async with self._lock:
            events = self._events[key]
            while events and events[0] < cutoff:
                events.popleft()
            if len(events) >= self.max_attempts:
                retry_after = max(1, int(self.window_seconds - (now - events[0])))
                raise AppError(
                    "RATE_LIMITED",
                    f"Trop de tentatives. Réessayez dans {retry_after} secondes.",
                    status_code=429,
                    details={"retry_after": retry_after},
                )
            events.append(now)
            # Opportunistic cleanup of idle keys.
            if len(self._events) > 5000:
                for stale in [k for k, v in self._events.items() if not v]:
                    self._events.pop(stale, None)

    async def reset(self, key: str) -> None:
        async with self._lock:
            self._events.pop(key, None)


login_limiter = SlidingWindowLimiter(max_attempts=6, window_seconds=15 * 60)
setup_limiter = SlidingWindowLimiter(max_attempts=8, window_seconds=15 * 60)
frame_limiter = SlidingWindowLimiter(max_attempts=120, window_seconds=60)
