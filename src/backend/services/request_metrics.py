from __future__ import annotations

from collections import defaultdict, deque
from threading import Lock
from time import perf_counter
from typing import Any


def percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    index = max(
        0, min(len(sorted_values) - 1, int((len(sorted_values) * ratio) + 0.999999) - 1)
    )
    return float(sorted_values[index])


class RequestMetricsService:
    def __init__(self, max_samples: int = 200):
        self.max_samples = max_samples
        self._durations: dict[str, deque[float]] = defaultdict(
            lambda: deque(maxlen=max_samples)
        )
        self._lock = Lock()

    def record(self, route_key: str, duration_ms: float) -> None:
        with self._lock:
            self._durations[route_key].append(duration_ms)

    def summarize(self) -> dict[str, dict[str, float | int]]:
        with self._lock:
            return {
                route: {
                    "sample_count": len(samples),
                    "min_ms": round(min(samples), 3) if samples else 0.0,
                    "max_ms": round(max(samples), 3) if samples else 0.0,
                    "median_ms": round(percentile(list(samples), 0.5), 3),
                    "p95_ms": round(percentile(list(samples), 0.95), 3),
                }
                for route, samples in self._durations.items()
            }


_request_metrics_service: RequestMetricsService | None = None


def get_request_metrics_service() -> RequestMetricsService:
    global _request_metrics_service
    if _request_metrics_service is None:
        _request_metrics_service = RequestMetricsService()
    return _request_metrics_service


class RequestTimer:
    def __init__(self):
        self.started = perf_counter()

    def elapsed_ms(self) -> float:
        return (perf_counter() - self.started) * 1000
