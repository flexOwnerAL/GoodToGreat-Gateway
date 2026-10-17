from __future__ import annotations

import time
from collections import Counter
from threading import Lock

_lock = Lock()
_requests: Counter[tuple[str, str]] = Counter()
_errors: Counter[tuple[str, str]] = Counter()
_latency_total: Counter[str] = Counter()
_latency_count: Counter[str] = Counter()
_started = time.time()


def record_request(method: str, path: str, status: int, elapsed: float) -> None:
    route = path if path.startswith("/v1/") else path
    with _lock:
        _requests[(method, route)] += 1
        if status >= 400:
            _errors[(method, route)] += 1
        _latency_total[route] += elapsed
        _latency_count[route] += 1


def snapshot() -> dict:
    with _lock:
        return {
            "uptime_seconds": round(time.time() - _started, 3),
            "requests_total": sum(_requests.values()),
            "errors_total": sum(_errors.values()),
            "routes": {
                route: {
                    "requests": sum(v for (method, path), v in _requests.items() if path == route),
                    "errors": sum(v for (method, path), v in _errors.items() if path == route),
                    "average_latency_ms": round(1000 * _latency_total[route] / count, 2)
                    if (count := _latency_count[route]) else 0,
                }
                for route in sorted({path for _, path in _requests})
            },
        }
