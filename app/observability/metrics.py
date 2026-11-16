"""Thread-safe, dependency-free Prometheus text metrics with bounded labels."""

from __future__ import annotations

from bisect import bisect_left
from collections import defaultdict
from collections.abc import Callable, Iterable
from threading import Lock

DEFAULT_DURATION_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
KNOWN_METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"})


def safe_method(method: str) -> str:
    normalized = method.upper()
    return normalized if normalized in KNOWN_METHODS else "OTHER"


def status_class(status_code: int) -> str:
    return f"{status_code // 100}xx" if 100 <= status_code <= 599 else "unknown"


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _labels(names: tuple[str, ...], values: tuple[str, ...]) -> str:
    if not names:
        return ""
    rendered = ",".join(f'{name}="{_escape(value)}"' for name, value in zip(names, values))
    return "{" + rendered + "}"


class MetricsRegistry:
    """Application-owned metrics registry; each app instance gets isolated state."""

    def __init__(self, clock: Callable[[], float]) -> None:
        self._clock = clock
        self._lock = Lock()
        self._counters: dict[str, dict[tuple[str, ...], float]] = defaultdict(
            lambda: defaultdict(float)
        )
        self._gauges: dict[str, dict[tuple[str, ...], float]] = defaultdict(
            lambda: defaultdict(float)
        )
        self._histograms: dict[str, dict[tuple[str, ...], tuple[list[int], float, int]]] = (
            defaultdict(dict)
        )
        self._pool_snapshot: Callable[[], dict[str, float]] | None = None

    @property
    def clock(self) -> Callable[[], float]:
        return self._clock

    def increment(self, name: str, labels: tuple[str, ...] = (), amount: float = 1.0) -> None:
        with self._lock:
            self._counters[name][labels] += amount

    def gauge_add(self, name: str, labels: tuple[str, ...] = (), amount: float = 1.0) -> None:
        with self._lock:
            self._gauges[name][labels] += amount

    def gauge_set(self, name: str, value: float, labels: tuple[str, ...] = ()) -> None:
        with self._lock:
            self._gauges[name][labels] = value

    def observe(
        self,
        name: str,
        value: float,
        labels: tuple[str, ...] = (),
        buckets: Iterable[float] = DEFAULT_DURATION_BUCKETS,
    ) -> None:
        bucket_values = tuple(buckets)
        with self._lock:
            counts, total, count = self._histograms[name].get(
                labels, ([0] * len(bucket_values), 0.0, 0)
            )
            bucket_index = bisect_left(bucket_values, value)
            if bucket_index < len(counts):
                counts[bucket_index] += 1
            self._histograms[name][labels] = (counts, total + value, count + 1)

    def set_pool_snapshot_provider(self, provider: Callable[[], dict[str, float]]) -> None:
        self._pool_snapshot = provider

    def render_prometheus(self) -> str:
        pool_snapshot = self._pool_snapshot() if self._pool_snapshot is not None else {}
        with self._lock:
            counters = {name: dict(samples) for name, samples in self._counters.items()}
            gauges = {name: dict(samples) for name, samples in self._gauges.items()}
            histograms = {
                name: {
                    labels: (list(counts), total, count)
                    for labels, (counts, total, count) in samples.items()
                }
                for name, samples in self._histograms.items()
            }

        for name, value in pool_snapshot.items():
            gauges.setdefault(name, {})[()] = value

        lines: list[str] = []
        label_names = {
            "eventhub_http_requests_total": ("method", "route"),
            "eventhub_http_responses_total": ("method", "route", "status_class"),
            "eventhub_http_request_duration_seconds": ("method", "route"),
            "eventhub_http_requests_in_flight": ("method", "route"),
            "eventhub_http_unhandled_exceptions_total": ("method", "route"),
            "eventhub_db_queries_total": ("outcome",),
            "eventhub_db_query_duration_seconds": ("outcome",),
        }
        for name in sorted(counters):
            lines.append(f"# TYPE {name} counter")
            names = label_names.get(name, ())
            for labels, value in sorted(counters[name].items()):
                lines.append(f"{name}{_labels(names, labels)} {value:g}")
        for name in sorted(gauges):
            lines.append(f"# TYPE {name} gauge")
            names = label_names.get(name, ())
            for labels, value in sorted(gauges[name].items()):
                lines.append(f"{name}{_labels(names, labels)} {value:g}")
        for name in sorted(histograms):
            lines.append(f"# TYPE {name} histogram")
            names = label_names.get(name, ())
            for labels, (counts, total, count) in sorted(histograms[name].items()):
                cumulative_count = 0
                for upper_bound, bucket_count in zip(DEFAULT_DURATION_BUCKETS, counts):
                    cumulative_count += bucket_count
                    bucket_names = (*names, "le")
                    bucket_labels = (*labels, f"{upper_bound:g}")
                    lines.append(
                        f"{name}_bucket{_labels(bucket_names, bucket_labels)} {cumulative_count}"
                    )
                lines.append(f"{name}_bucket{_labels((*names, 'le'), (*labels, '+Inf'))} {count}")
                lines.append(f"{name}_sum{_labels(names, labels)} {total:.9f}")
                lines.append(f"{name}_count{_labels(names, labels)} {count}")
        return "\n".join(lines) + "\n"
