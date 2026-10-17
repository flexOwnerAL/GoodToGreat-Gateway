"""A minimal in-process token-bucket rate limiter.

Scope and limitations (documented honestly, not hidden):
  - State lives in process memory. If you run multiple gateway workers/processes,
    each one enforces its own independent limit — use a single worker, or move
    this to a shared store (e.g. Redis) for multi-process deployments.
  - Keyed per client identity (the bearer token if auth is enabled, else the
    client IP). This bounds abuse per caller without needing a database.
"""

from __future__ import annotations

import time
from threading import Lock

from app.core.config import get_settings

_lock = Lock()
# identity -> (tokens_remaining, last_refill_monotonic)
_buckets: dict[str, tuple[float, float]] = {}
_PRUNE_EVERY = 500
_calls_since_prune = 0


def _prune(now: float, window: float) -> None:
    """Drop buckets that have been idle long enough to be back at full capacity."""
    stale_before = now - (window * 2)
    stale_keys = [key for key, (_, last) in _buckets.items() if last < stale_before]
    for key in stale_keys:
        _buckets.pop(key, None)


def check_rate_limit(identity: str) -> tuple[bool, float]:
    """Returns (allowed, retry_after_seconds).

    retry_after_seconds is 0.0 when allowed is True.
    """
    global _calls_since_prune
    settings = get_settings()
    if not settings.rate_limit_enabled:
        return True, 0.0

    capacity = max(1, settings.rate_limit_requests)
    window = max(0.001, settings.rate_limit_window_seconds)
    refill_rate = capacity / window
    now = time.monotonic()

    with _lock:
        _calls_since_prune += 1
        if _calls_since_prune >= _PRUNE_EVERY:
            _calls_since_prune = 0
            _prune(now, window)

        tokens, last = _buckets.get(identity, (float(capacity), now))
        elapsed = max(0.0, now - last)
        tokens = min(float(capacity), tokens + elapsed * refill_rate)

        if tokens < 1.0:
            _buckets[identity] = (tokens, now)
            retry_after = (1.0 - tokens) / refill_rate
            return False, round(retry_after, 3)

        tokens -= 1.0
        _buckets[identity] = (tokens, now)
        return True, 0.0


def reset_rate_limits() -> None:
    """Test helper: clear all bucket state."""
    with _lock:
        _buckets.clear()
