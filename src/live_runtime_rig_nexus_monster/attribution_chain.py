"""Nexus-conducted attribution acceptance for the full Monster.

The rig supplies only a natural user problem. Nexus must independently select
Business Brain through its ordinary governed tool loop. Business Brain then
owns the Moon Source -> HZK -> disposable Business Brain composition and returns
a bounded result. No hidden required_tool_id, routing prompt, retry bumper or
prebuilt chain packet is supplied by the harness.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from contextlib import contextmanager
from typing import Any, Mapping


ATTRIBUTION_SCENARIO = """An AI-assisted collaboration has blurred several attribution and lineage questions.

An external collaborator's public framework materially informed some later local design work, while the local implementation itself was still authored and built locally. Current cross-system integration is now being treated as proof that the external framework was part of the local system's historical architecture. Conceptual influence is also being treated as automatic coauthorship. Older references, current authority, compatibility material, and implementation evidence may be getting treated as if they all carry the same weight.

Please resolve the dispute from the governed project evidence available to you. Separate what the evidence supports from what it does not support, preserve relevant provenance and authorship distinctions, distinguish current integration from historical lineage, and leave genuine unknowns unresolved."""


FORBIDDEN_ROUTING_BUMPERS = (
    "business brain",
    "moon source",
    "hzk",
    "business_brain.resolve_attribution",
    "use a tool",
    "call the tool",
    "call business",
    "required_tool_id",
)


def _emit_live(message: str) -> None:
    stream = getattr(sys, "__stdout__", None) or sys.stdout
    stream.write(message.rstrip() + "\n")
    stream.flush()


@contextmanager
def _observe_live_nexus_turn(runtime: Any, turn_id: str):
    stop = threading.Event()
    started = time.monotonic()
    _emit_live("[10A] Nexus-conducted attribution turn START")

    def heartbeat() -> None:
        while not stop.wait(30):
            rounds = list(runtime.provider_telemetry_for_turn(turn_id))
            elapsed = time.monotonic() - started
            if not rounds:
                _emit_live(
                    f"[10A] Nexus pre/provider routing alive... {elapsed:.0f}s | "
                    "no provider round observed yet"
                )
                continue
            current = rounds[-1]
            chunks = int(current.get("stream_chunks_observed") or 0)
            bytes_out = int(current.get("stream_bytes_observed") or 0)
            phase = "streaming content" if chunks else "waiting for first visible output"
            _emit_live(
                f"[10A] Nexus alive... {elapsed:.0f}s | "
                f"provider_round={current.get('round')} | {phase} | "
                f"chunks={chunks} output={bytes_out}B"
            )

    thread = threading.Thread(
        target=heartbeat,
        name="monster-nexus-attribution-heartbeat",
        daemon=True,
    )
    thread.start()
    try:
        yield
    finally:
        stop.set()
        _emit_live(
            f"[10A] Nexus-conducted attribution turn END | "
            f"{time.monotonic() - started:.1f}s"
        )


def _receipt_trace(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    trace: list[dict[str, Any]] = []
    for raw in payload.get("receipts") or ():
        if not isinstance(raw, Mapping):
            continue
        trace.append(
            {
                "kernel_id": raw.get("kernel_id"),
                "operation": raw.get("operation"),
                "status": raw.get("status"),
                "duration_ms": raw.get("duration_ms"),
                "state_mutated": raw.get("state_mutated"),
                "output_hash": raw.get("output_hash"),
            }
        )
    return trace


def run_attribution_chain(runtime: Any, *, marker: str) -> dict[str, Any]:
    scenario = ATTRIBUTION_SCENARIO.strip()
    lowered = scenario.casefold()
    routing_bumpers = tuple(
        marker for marker in FORBIDDEN_ROUTING_BUMPERS if marker in lowered
    )

    turn_id = f"monster-attribution-route:{marker}"
    session_id = f"monster-attribution-route:{marker}"

    started = time.perf_counter_ns()
    with _observe_live_nexus_turn(runtime, turn_id):
        response = runtime.request(
            "POST",
            "/v1/chat/completions",
            principal="primary",
            json={
                "messages": [{"role": "user", "content": scenario}],
                "session_id": session_id,
                "request_id": turn_id,
                "turn_id": turn_id,
                "include_tools": True,
            },
        )
    wall_ms = (time.perf_counter_ns() - started) / 1_000_000
    runtime.record_nexus_takt(
        "attribution.nexus_conducted_turn",
        wall_ms,
        metadata={"boundary": "canonical_v1_chat_completions"},
    )

    try:
        body = dict(response.json())
    except Exception:
        body = {}

    tool_executions = list(runtime.tool_execution_trace(turn_id))
    provider_telemetry = list(runtime.provider_telemetry_for_turn(turn_id))
    business_brain_trace = runtime.business_brain_trace_for_turn(turn_id)
    final_text = str(body.get("text") or "").strip()
    receipts = _receipt_trace(body)

    bb_executions = [
        item
        for item in tool_executions
        if str(item.get("tool_id") or "") == "business_brain.resolve_attribution"
    ]
    bb_execution = bb_executions[0] if len(bb_executions) == 1 else None
    bounded_result = (
        dict(bb_execution.get("result") or {})
        if isinstance(bb_execution, Mapping)
        and isinstance(bb_execution.get("result"), Mapping)
        else {}
    )
    bounded_serialized = json.dumps(
        bounded_result,
        sort_keys=True,
        ensure_ascii=False,
    )

    first_round = provider_telemetry[0] if provider_telemetry else {}
    final_round = provider_telemetry[-1] if provider_telemetry else {}

    return {
        "scenario": scenario,
        "scenario_bytes": len(scenario.encode("utf-8")),
        "routing_bumpers": routing_bumpers,
        "turn_id": turn_id,
        "session_id": session_id,
        "status_code": getattr(response, "status_code", None),
        "body": body,
        "state": body.get("state"),
        "blocking_reason": body.get("blocking_reason"),
        "final_text": final_text,
        "wall_ms": round(wall_ms, 6),
        "receipts": receipts,
        "tool_executions": tool_executions,
        "business_brain_executions": bb_executions,
        "business_brain_execution": bb_execution,
        "business_brain_trace": business_brain_trace,
        "bounded_result": bounded_result,
        "bounded_result_bytes": len(bounded_serialized.encode("utf-8")),
        "bounded_result_leaks_raw_hzk": (
            "payload_text" in bounded_serialized
            or "treaty_grant" in bounded_serialized
        ),
        "provider_telemetry": provider_telemetry,
        "provider_round_count": len(provider_telemetry),
        "first_round": first_round,
        "final_round": final_round,
    }
