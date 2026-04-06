"""Minimal in-memory counter store with Prometheus text export."""

from __future__ import annotations

from collections import defaultdict
import math
from threading import Lock


class MetricsStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._counters: dict[str, float] = defaultdict(float)
        self._observations: dict[str, list[float]] = defaultdict(list)

    def inc(self, name: str, value: float = 1.0) -> None:
        with self._lock:
            self._counters[name] += value

    def snapshot(self) -> dict[str, float]:
        with self._lock:
            return dict(self._counters)

    def observe(self, name: str, value: float) -> None:
        with self._lock:
            if math.isfinite(value):
                self._observations[name].append(float(value))

    def _observation_summary(self) -> dict[str, dict[str, float]]:
        with self._lock:
            copied = {k: list(v) for k, v in self._observations.items()}
        summary: dict[str, dict[str, float]] = {}
        for key, values in copied.items():
            if not values:
                continue
            values.sort()
            count = len(values)
            p50_idx = min(count - 1, int(round((count - 1) * 0.50)))
            p95_idx = min(count - 1, int(round((count - 1) * 0.95)))
            summary[key] = {
                "count": float(count),
                "sum": float(sum(values)),
                "p50": float(values[p50_idx]),
                "p95": float(values[p95_idx]),
            }
        return summary

    def to_prometheus(self) -> str:
        lines: list[str] = []
        snapshot = self.snapshot()
        for key, value in sorted(snapshot.items()):
            metric_name = key.replace("-", "_").replace(".", "_")
            lines.append(f"# TYPE {metric_name} counter")
            lines.append(f"{metric_name} {value}")

        # Derived metric: cache hit ratio.
        hit = float(snapshot.get("cache_hit_total", 0.0))
        miss = float(snapshot.get("cache_miss_total", 0.0))
        total = hit + miss
        if total > 0:
            lines.append("# TYPE pipeline_cache_hit_ratio gauge")
            lines.append(f"pipeline_cache_hit_ratio {hit / total:.6f}")

        for key, stats in sorted(self._observation_summary().items()):
            metric_name = key.replace("-", "_").replace(".", "_")
            lines.append(f"# TYPE {metric_name}_count gauge")
            lines.append(f"{metric_name}_count {stats['count']}")
            lines.append(f"# TYPE {metric_name}_sum gauge")
            lines.append(f"{metric_name}_sum {stats['sum']:.6f}")
            lines.append(f"# TYPE {metric_name}_p50 gauge")
            lines.append(f"{metric_name}_p50 {stats['p50']:.6f}")
            lines.append(f"# TYPE {metric_name}_p95 gauge")
            lines.append(f"{metric_name}_p95 {stats['p95']:.6f}")
        return "\n".join(lines) + "\n"
