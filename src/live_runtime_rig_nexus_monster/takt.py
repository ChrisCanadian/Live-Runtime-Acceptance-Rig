"""Observer-side takt timing for the Nexus Monster acceptance rig.

This module deliberately does not change Nexus contracts. It measures wall time
around acceptance-owned call boundaries and records existing KernelReceipt
duration_ms values when they are already exposed by the runtime.
"""

from __future__ import annotations

import json
import statistics
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from functools import wraps
from pathlib import Path
from typing import Any, Iterator, Mapping


@dataclass(frozen=True)
class TaktSample:
    name: str
    duration_ms: float
    source: str
    boundary: str
    metadata: Mapping[str, Any]


class TaktRecorder:
    def __init__(self) -> None:
        self._samples: list[TaktSample] = []

    def record(
        self,
        name: str,
        duration_ms: float,
        *,
        source: str = "observer_wall",
        boundary: str = "nexus",
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        self._samples.append(
            TaktSample(
                name=str(name),
                duration_ms=round(float(duration_ms), 6),
                source=str(source),
                boundary=str(boundary),
                metadata=dict(metadata or {}),
            )
        )

    @contextmanager
    def measure(
        self,
        name: str,
        *,
        source: str = "observer_wall",
        boundary: str = "nexus",
        metadata: Mapping[str, Any] | None = None,
    ) -> Iterator[None]:
        started = time.perf_counter_ns()
        try:
            yield
        finally:
            elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
            self.record(
                name,
                elapsed_ms,
                source=source,
                boundary=boundary,
                metadata=metadata,
            )

    @staticmethod
    def _percentile(values: list[float], fraction: float) -> float:
        if not values:
            return 0.0
        ordered = sorted(values)
        if len(ordered) == 1:
            return ordered[0]
        index = (len(ordered) - 1) * fraction
        low = int(index)
        high = min(low + 1, len(ordered) - 1)
        weight = index - low
        return ordered[low] * (1.0 - weight) + ordered[high] * weight

    def snapshot(self) -> dict[str, Any]:
        groups: dict[tuple[str, str, str], list[float]] = {}
        for sample in self._samples:
            key = (sample.name, sample.source, sample.boundary)
            groups.setdefault(key, []).append(sample.duration_ms)

        aggregates = []
        for (name, source, boundary), values in sorted(groups.items()):
            aggregates.append(
                {
                    "name": name,
                    "source": source,
                    "boundary": boundary,
                    "count": len(values),
                    "total_ms": round(sum(values), 6),
                    "mean_ms": round(statistics.fmean(values), 6),
                    "min_ms": round(min(values), 6),
                    "p50_ms": round(self._percentile(values, 0.50), 6),
                    "p95_ms": round(self._percentile(values, 0.95), 6),
                    "max_ms": round(max(values), 6),
                }
            )

        return {
            "schema_version": "1.0",
            "measurement_contract": {
                "observer_wall": (
                    "Wall-clock time measured by the acceptance rig around a Nexus-owned "
                    "or explicitly crossed external boundary."
                ),
                "kernel_receipt": (
                    "KernelReceipt.duration_ms emitted by the existing Nexus kernel contract; "
                    "not independently instrumented by the rig."
                ),
                "external_boundary": (
                    "Wall-clock time observed from Nexus/Business-Brain caller side only. "
                    "No internal external-system timing is inferred."
                ),
            },
            "sample_count": len(self._samples),
            "aggregates": aggregates,
            "samples": [asdict(sample) for sample in self._samples],
        }

    def write(self, root: Path) -> tuple[Path, Path]:
        root.mkdir(parents=True, exist_ok=True)
        payload = self.snapshot()
        json_path = root / "takt-timings.json"
        md_path = root / "TAKT_TIMINGS.md"
        json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

        rows = [
            "# Monster Takt Timing",
            "",
            "Observer timings are acceptance-rig wall clock measurements. "
            "Kernel timings are existing KernelReceipt.duration_ms values only.",
            "",
            "| Function / operation | Source | Boundary | Count | Mean ms | P50 ms | P95 ms | Max ms |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
        for item in payload["aggregates"]:
            rows.append(
                "| {name} | {source} | {boundary} | {count} | {mean_ms:.3f} | "
                "{p50_ms:.3f} | {p95_ms:.3f} | {max_ms:.3f} |".format(**item)
            )
        md_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
        return json_path, md_path


def timed_method(name: str, *, boundary: str = "nexus"):
    """Measure a synchronous acceptance adapter method without changing its result."""

    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            recorder = getattr(self, "_takt", None)
            if recorder is None:
                return func(self, *args, **kwargs)
            with recorder.measure(name, boundary=boundary):
                return func(self, *args, **kwargs)

        return wrapper

    return decorator
