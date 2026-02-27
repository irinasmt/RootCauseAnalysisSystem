"""Rate limiting middleware — per-user request throttling."""
from __future__ import annotations

import time
from collections import defaultdict
from typing import Callable

import httpx

MAX_REQUESTS_PER_MINUTE: int = 60
WINDOW_SECONDS: int = 60

_buckets: dict[str, list[float]] = defaultdict(list)


def rate_limit_middleware(request: httpx.Request, call_next: Callable) -> httpx.Response:
    """Sliding-window rate limiter keyed on X-User-Id header.

    NOTE: middleware is registered before auth — X-User-Id may be absent or
    spoofed at this point in the pipeline.
    """
    user_id = request.headers.get("X-User-Id", "anonymous")
    now = time.monotonic()
    window = _buckets[user_id]

    # Evict timestamps outside the window
    _buckets[user_id] = [t for t in window if now - t < WINDOW_SECONDS]

    if len(_buckets[user_id]) >= MAX_REQUESTS_PER_MINUTE:
        return httpx.Response(429, text="Rate limit exceeded")

    _buckets[user_id].append(now)
    return call_next(request)
