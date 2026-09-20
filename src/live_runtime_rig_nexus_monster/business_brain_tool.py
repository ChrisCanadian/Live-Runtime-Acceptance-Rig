"""Acceptance-only governed Business Brain tool registration.

The capability is registered into the real V5 ToolRegistry that NDKA wraps.
Nexus may choose it through the ordinary model-driven tool loop. The rig never
forces required_tool_id, rewrites the user's request, or retries until the model
selects this tool.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Mapping


TOOL_ID = "business_brain.resolve_attribution"
TOOL_VERSION = "1.0.0"
TOOL_PERMISSION = "tools:business_brain"


def _emit(message: str) -> None:
    stream = getattr(sys, "__stdout__", None) or sys.stdout
    stream.write(message.rstrip() + "\n")
    stream.flush()


class BusinessBrainAttributionTool:
    def __init__(
        self,
        *,
        moon_root: Path,
        artifact_dir: Path,
        tool_result_factory: Any,
    ) -> None:
        self.moon_root = moon_root.resolve()
        self.artifact_dir = artifact_dir.resolve()
        self.tool_result_factory = tool_result_factory
        self._traces: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _stage_label(stage: str) -> str:
        return {
            "moon.start": "Moon Source discovery",
            "moon.complete": "Moon Source discovery",
            "hzk.start": "HZK treaty governance",
            "hzk.complete": "HZK treaty governance",
            "business_brain.start": "Business Brain custody",
            "business_brain.complete": "Business Brain custody",
        }.get(stage, stage)

    def _progress(self, stage: str, facts: Mapping[str, Any]) -> None:
        label = self._stage_label(stage)
        if stage.endswith(".start"):
            _emit(f"[BB TOOL] {label} START")
            return
        values = []
        for key in (
            "elapsed_ms",
            "selected_count",
            "candidate_count",
            "entry_count",
            "payload_bytes",
            "grant_wire_bytes",
            "state",
            "integrity",
        ):
            value = facts.get(key)
            if value is not None:
                values.append(f"{key}={value}")
        suffix = " | " + " ".join(values) if values else ""
        _emit(f"[BB TOOL] {label} COMPLETE{suffix}")

    def __call__(self, arguments: Mapping[str, Any], context: Any):
        from integration_lab.nexus_business_brain_attribution import (
            resolve_attribution_for_nexus,
        )

        query = str(arguments.get("query") or "").strip()
        execution_id = str(context.execution_id or "")
        if not execution_id:
            raise RuntimeError("Business Brain tool requires execution_id")

        started = time.perf_counter()
        _emit(
            f"[BB TOOL] governed execution START | turn={context.turn_id} "
            f"proposal={context.provider_proposal_id or 'NONE'}"
        )
        compact, trace = resolve_attribution_for_nexus(
            query,
            moon_root=self.moon_root,
            correlation_id=context.correlation_id,
            nexus_turn_id=context.turn_id,
            nexus_execution_id=execution_id,
            progress=self._progress,
        )
        elapsed_ms = (time.perf_counter() - started) * 1000

        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        trace_path = self.artifact_dir / (
            "BB_TOOL_TRACE_" + execution_id.replace(":", "_").replace("/", "_") + ".json"
        )
        trace_path.write_text(
            json.dumps(trace, indent=2, sort_keys=True, ensure_ascii=False),
            encoding="utf-8",
        )
        self._traces[context.turn_id] = {
            "execution_id": execution_id,
            "provider_proposal_id": context.provider_proposal_id,
            "trace_path": str(trace_path),
            "trace": trace,
            "bounded_result": compact,
        }

        transport = compact.get("transport") or {}
        _emit(
            "[BB TOOL] governed execution COMPLETE | "
            f"elapsed={elapsed_ms / 1000:.1f}s "
            f"raw_hzk={transport.get('hzk_payload_bytes')}B "
            f"grant={transport.get('hzk_grant_wire_bytes')}B "
            f"returned={transport.get('bounded_result_bytes')}B"
        )
        return self.tool_result_factory("SUCCEEDED", compact)

    def trace_for_turn(self, turn_id: str) -> Mapping[str, Any] | None:
        value = self._traces.get(turn_id)
        return dict(value) if value is not None else None


def register_business_brain_tool(
    runtime: Any,
    *,
    moon_root: Path,
    artifact_dir: Path,
) -> BusinessBrainAttributionTool:
    """Register the acceptance capability into the real V5 registry."""

    modules = runtime.v5_modules
    tool_service = modules.tools_service
    handler = BusinessBrainAttributionTool(
        moon_root=moon_root,
        artifact_dir=artifact_dir,
        tool_result_factory=tool_service.ToolResult,
    )
    manifest = tool_service.ToolManifest(
        tool_id=TOOL_ID,
        version=TOOL_VERSION,
        description=(
            "Resolve evidence-backed questions about attribution, provenance, "
            "authorship, lineage, current-versus-historical authority, and "
            "cross-system responsibility boundaries using governed Business Brain evidence."
        ),
        input_schema={
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string", "minLength": 1, "maxLength": 20000},
            },
            "additionalProperties": False,
        },
        required_permissions=frozenset({TOOL_PERMISSION}),
        risk_class="READ_ONLY",
        execution_class="IN_PROCESS",
        handler_key="business_brain.resolve_attribution.v1",
        result_schema={
            "type": "object",
            "required": [
                "status",
                "resolution",
                "sources",
                "hzk",
                "business_brain",
                "provenance",
                "transport",
            ],
            "properties": {
                "status": {"type": "string"},
                "resolution": {"type": "object"},
                "sources": {"type": "array", "maxItems": 20},
                "hzk": {"type": "object"},
                "business_brain": {"type": "object"},
                "provenance": {"type": "object"},
                "transport": {"type": "object"},
            },
            "additionalProperties": False,
        },
        authorization_policy={
            "acceptance_scope": "isolated_disposable_state",
            "canonical_write_authority": False,
            "upstream_mutation_authority": False,
        },
        timeout_ms=300_000,
        retry_policy={"max_attempts": 1, "retryable_error_codes": []},
        idempotency_policy={"required": True, "max_invocations_per_turn": 1},
        destructive_action_class="NON_DESTRUCTIVE",
        artifact_behavior={
            "canonical_artifact_write": False,
            "acceptance_evidence_trace": True,
        },
    )
    runtime.v5_runtime.tools.register(manifest, handler)
    return handler
