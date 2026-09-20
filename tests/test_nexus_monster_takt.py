from __future__ import annotations

from pathlib import Path

from live_runtime_rig_nexus_monster.takt import TaktRecorder


def test_takt_recorder_keeps_wall_and_kernel_sources_distinct(tmp_path: Path) -> None:
    recorder = TaktRecorder()
    recorder.record("runtime.chat", 20.0, source="observer_wall", boundary="nexus")
    recorder.record(
        "nexus.provider.generate",
        12.0,
        source="kernel_receipt",
        boundary="nexus",
        metadata={"kernel_id": "nexus.provider"},
    )
    payload = recorder.snapshot()
    assert payload["sample_count"] == 2
    sources = {item["source"] for item in payload["aggregates"]}
    assert sources == {"observer_wall", "kernel_receipt"}

    json_path, md_path = recorder.write(tmp_path)
    assert json_path.exists()
    assert md_path.exists()
    assert "KernelReceipt.duration_ms" in md_path.read_text(encoding="utf-8")


def test_takt_percentiles_are_stable() -> None:
    recorder = TaktRecorder()
    for value in (10.0, 20.0, 30.0, 40.0):
        recorder.record("runtime.request", value)
    aggregate = recorder.snapshot()["aggregates"][0]
    assert aggregate["mean_ms"] == 25.0
    assert aggregate["p50_ms"] == 25.0
    assert aggregate["max_ms"] == 40.0
