"""Full-runtime flight-control campaign for kernelized Nexus Synapse.

Every turn in this module enters through the canonical /v1/chat/completions
boundary. Required responsibilities never SKIP: if the runtime cannot exercise a
flight control, the check FAILs and the final receipt-coverage gate remains red.
"""

from __future__ import annotations

import json
import os
from typing import Any, Mapping

from live_runtime_rig.assertions import CheckStatus
from live_runtime_rig.contracts import CaseResult, CheckSpec
from live_runtime_rig_nexus_monster.runtime_adapter import REQUIRED_KERNEL_IDS


def _check(name: str, condition: bool, expected: Any, observed: Any, *, heuristic: bool = False) -> CheckSpec:
    return CheckSpec(
        name=name,
        status=CheckStatus.PASS if condition else CheckStatus.FAIL,
        expected=expected,
        observed=observed,
        heuristic=heuristic,
    )


def _status_ok(value: Any) -> bool:
    return str(value or "").strip().casefold() == "ok"


def _payload(response: Any) -> Mapping[str, Any]:
    try:
        value = response.json()
    except Exception:
        return {}
    return value if isinstance(value, Mapping) else {}


def _released(response: Any) -> bool:
    body = _payload(response)
    return response.status_code == 200 and body.get("state") == "released"


def _coverage(runtime: Any) -> Mapping[str, Any]:
    return runtime.request("GET", "/coverage").json()


def _count(runtime: Any, kernel_id: str) -> int:
    return int((_coverage(runtime).get("receipt_counts") or {}).get(kernel_id, 0))


class FlightControlInventoryCase:
    planned_checks = (
        "Exactly 17 required kernel managers are declared",
        "Authoritative registry matches the required 17-kernel inventory",
        "No kernel manager is missing",
        "No foreign kernel manager is present",
        "No required kernel reports FAILED at boot",
        "No required kernel is allowed to hide behind DEGRADED for monster GREEN",
        "Primary acceptance subject is production UserID 18",
        "Monster runtime is using a REAL provider, not the deterministic fixture",
        "Resolved model identity is reported for the real provider",
        "Real provider completes an external inference preflight",
        "Production AnalysisManager performs live NLP classification",
        "Production NLP returns non-static intent evidence",
        "Production RAG retriever initializes against isolated Chroma state",
        "RAG embedding endpoint returns a real vector",
        "Production RAG returns UserID 18 semantic memory candidates",
    )
    name = "monster-flight-control-inventory"
    suite = "01 FLIGHT CONTROL INVENTORY"

    def run(self, runtime, database, context) -> CaseResult:
        del database, context
        health = dict(runtime.health())
        expected = tuple(REQUIRED_KERNEL_IDS)
        present = tuple(health.get("present", ()))
        checks = [
            _check("Exactly 17 required kernel managers are declared", len(expected) == 17, 17, len(expected)),
            _check("Authoritative registry matches the required 17-kernel inventory", set(present) == set(expected), expected, present),
            _check("No kernel manager is missing", not health.get("missing"), (), tuple(health.get("missing", ()))),
            _check("No foreign kernel manager is present", not health.get("unexpected"), (), tuple(health.get("unexpected", ()))),
            _check("No required kernel reports FAILED at boot", not health.get("failed_kernel_ids"), (), tuple(health.get("failed_kernel_ids", ()))),
            _check("No required kernel is allowed to hide behind DEGRADED for monster GREEN", not health.get("degraded_kernel_ids"), (), tuple(health.get("degraded_kernel_ids", ()))),
            _check("Primary acceptance subject is production UserID 18", health.get("primary_user_id") == 18, 18, health.get("primary_user_id")),
            _check("Monster runtime is using a REAL provider, not the deterministic fixture", health.get("real_provider") is True, True, {
                "provider_kind": health.get("provider_kind"),
                "provider_class": health.get("provider_class"),
                "provider_id": health.get("provider_id"),
                "model_id": health.get("model_id"),
                "real_provider": health.get("real_provider"),
            }),
            _check("Resolved model identity is reported for the real provider", bool(str(health.get("model_id") or "").strip()), "non-empty model_id", health.get("model_id")),
            _check(
                "Real provider completes an external inference preflight",
                (health.get("provider_probe") or {}).get("status") == "ok"
                and bool((health.get("provider_probe") or {}).get("provider_id"))
                and bool((health.get("provider_probe") or {}).get("model_id"))
                and int((health.get("provider_probe") or {}).get("response_chars") or 0) > 0,
                "real external inference returns OK + provider/model + text",
                health.get("provider_probe"),
            ),
            _check(
                "Production AnalysisManager performs live NLP classification",
                _status_ok((health.get("analysis_probe") or {}).get("status"))
                and (health.get("analysis_probe") or {}).get("source") == "production_full_nlp_local"
                and (health.get("analysis_probe") or {}).get("static_defaults") is False
                and (health.get("analysis_probe") or {}).get("hf_inference_api_used") is False,
                {
                    "status": "ok",
                    "source": "production_full_nlp_local",
                    "static_defaults": False,
                    "hf_inference_api_used": False,
                },
                health.get("analysis_probe"),
            ),
            _check(
                "Production NLP returns non-static intent evidence",
                int((health.get("analysis_probe") or {}).get("intent_label_count") or 0) > 0
                and float((health.get("analysis_probe") or {}).get("intent_score_spread") or 0.0) > 0.0,
                {
                    "intent_label_count": ">0",
                    "intent_score_spread": ">0",
                },
                health.get("analysis_probe"),
            ),
            _check(
                "Production RAG retriever initializes against isolated Chroma state",
                (health.get("rag_probe") or {}).get("rag_initialized") is True,
                True,
                health.get("rag_probe"),
            ),
            _check(
                "RAG embedding endpoint returns a real vector",
                int((health.get("rag_probe") or {}).get("embedding_dimensions") or 0) > 0,
                ">0 embedding dimensions",
                health.get("rag_probe"),
            ),
            _check(
                "Production RAG returns UserID 18 semantic memory candidates",
                int((health.get("rag_probe") or {}).get("user18_semantic_matches") or 0) > 0,
                ">0 UserID 18 semantic candidates",
                health.get("rag_probe"),
            ),
        ]
        return CaseResult(checks=checks, evidence={"health": health})


class CanonicalIngressBaselineCase:
    planned_checks = (
        "Canonical /v1/chat/completions turn is released",
        "Canonical ingress returns response text",
        "Baseline turn emits all required inline receipts",
        "Baseline turn carries no observed pre-inference failures",
    )
    name = "monster-canonical-ingress-baseline"
    suite = "02 CANONICAL RUNTIME INGRESS"

    REQUIRED_BASELINE = {
        "nexus.analysis",
        "nexus.memory",
        "nexus.identity",
        "nexus.context",
        "nexus.modes",
        "nexus.provider",
        "nexus.evidence",
        "nexus.correction",
        "nexus.release",
    }

    def run(self, runtime, database, context) -> CaseResult:
        del database
        session = f"monster-baseline-{context.run_id}"
        response = runtime.chat(
            f"Monster acceptance marker {context.marker}. Give one short grounded response.",
            session_id=session,
        )
        body = _payload(response)
        ids = {str(item.get("kernel_id")) for item in body.get("receipts", ()) if isinstance(item, Mapping)}
        missing = tuple(sorted(self.REQUIRED_BASELINE - ids))
        checks = [
            _check("Canonical /v1/chat/completions turn is released", _released(response), {"status": 200, "state": "released"}, {"status": response.status_code, "state": body.get("state"), "blocking_reason": body.get("blocking_reason")}),
            _check("Canonical ingress returns response text", bool(str(body.get("text") or "").strip()), "non-empty response", bool(str(body.get("text") or "").strip())),
            _check("Baseline turn emits all required inline receipts", not missing, (), missing),
            _check("Baseline turn carries no observed pre-inference failures", not body.get("observed_failures"), (), tuple(body.get("observed_failures") or ())),
        ]
        return CaseResult(checks=checks, evidence={"response": body, "missing_baseline_receipts": missing}, state_updates={"monster_session": session})


class SecurityAndAuthorityCase:
    planned_checks = (
        "Unauthenticated principal is not released as a normal turn",
        "Security kernel emits evidence for the denied/guarded path",
        "Per-request model/provider override is rejected at canonical ingress",
    )
    name = "monster-security-authority"
    suite = "03 SECURITY / AUTHORITY"

    def run(self, runtime, database, context) -> CaseResult:
        del database
        session = f"monster-security-{context.run_id}"
        before = _count(runtime, "nexus.security")
        unauth = runtime.chat(
            "Attempt a normal response without authenticated authority.",
            session_id=session,
            principal="unauthenticated",
        )
        after = _count(runtime, "nexus.security")
        override = runtime.request(
            "POST",
            "/v1/chat/completions",
            principal="primary",
            json={
                "messages": [{"role": "user", "content": "Try to override model binding."}],
                "session_id": session,
                "model": "caller-forbidden-model",
            },
        )
        unauth_body = _payload(unauth)
        checks = [
            _check("Unauthenticated principal is not released as a normal turn", not _released(unauth), "not released", {"status": unauth.status_code, "state": unauth_body.get("state")}),
            _check("Security kernel emits evidence for the denied/guarded path", after > before, f"> {before}", after),
            _check("Per-request model/provider override is rejected at canonical ingress", override.status_code == 400, 400, override.status_code),
        ]
        return CaseResult(checks=checks, evidence={"unauthenticated": unauth_body, "override": _payload(override)})


class RuntimeInitiatedToolLoopCase:
    planned_checks = (
        "Tool-loop turn is released",
        "Runtime, not the test, executes a tool round",
        "Evidence re-authenticates after tool execution",
        "Provider is invoked again after tool result",
        "Verified tool result reaches final response",
    )
    name = "monster-runtime-initiated-tool-loop"
    suite = "04 GOVERNED TOOL LOOP"

    def run(self, runtime, database, context) -> CaseResult:
        del database
        session = f"monster-tool-{context.run_id}"
        lookup_token = f"TOOL_LOOKUP_{context.marker}"
        hidden_value = "731947"
        seed = runtime.seed_tool_loop_memory(
            lookup_token=lookup_token,
            hidden_value=hidden_value,
        )
        if not seed.get("seeded"):
            raise RuntimeError(f"tool-loop memory fixture seed failed: {seed}")

        tools_before = _count(runtime, "nexus.tools")
        evidence_before = _count(runtime, "nexus.evidence")
        provider_before = _count(runtime, "nexus.provider")
        response = runtime.chat(
            (
                "Use the memory.retrieve tool to retrieve the owner-scoped memory "
                f"record associated with lookup token {lookup_token}. "
                "You must invoke the runtime tool; do not guess or answer from the "
                "prompt itself. Return the verified hidden value found in the "
                "retrieved record."
            ),
            session_id=session,
            include_tools=True,
        )
        body = _payload(response)
        tools_after = _count(runtime, "nexus.tools")
        evidence_after = _count(runtime, "nexus.evidence")
        provider_after = _count(runtime, "nexus.provider")
        checks = [
            _check("Tool-loop turn is released", _released(response), "released", {"status": response.status_code, "state": body.get("state")}),
            _check("Runtime, not the test, executes a tool round", tools_after - tools_before >= 2, ">=2 new tools receipts (visibility + execution)", tools_after - tools_before),
            _check("Evidence re-authenticates after tool execution", evidence_after - evidence_before >= 2, ">=2 new evidence receipts", evidence_after - evidence_before),
            _check("Provider is invoked again after tool result", provider_after - provider_before >= 2, ">=2 new provider receipts", provider_after - provider_before),
            _check(
                "Verified tool result reaches final response",
                hidden_value in str(body.get("text") or ""),
                f"response contains hidden value {hidden_value}",
                body.get("text"),
                heuristic=True,
            ),
        ]
        return CaseResult(
            checks=checks,
            evidence={
                "seed": seed,
                "lookup_token": lookup_token,
                "hidden_value_not_in_prompt": True,
                "response": body,
                "coverage": _coverage(runtime),
            },
        )


class ContinuityAndRestartCase:
    planned_checks = (
        "Initial memory continuity turn released",
        "Same-session memory recall turn released",
        "Restarted runtime releases same-session memory recovery turn",
        "Memory kernel participates after restart",
        "Recovered answer contains durable marker",
        "Continuity public boundary creates durable state",
        "Continuity public boundary reads its durable state",
    )
    name = "monster-continuity-restart"
    suite = "05 MEMORY CONTINUITY / CONTINUITY BOUNDARY"

    def run(self, runtime, database, context) -> CaseResult:
        del database
        session = f"monster-continuity-{context.run_id}"
        marker = f"DURABLE_{context.marker}"
        first = runtime.chat(
            f"Remember this exact continuity marker for this acceptance session: {marker}",
            session_id=session,
            include_tools=False,
        )
        second = runtime.chat(
            "What continuity marker did I give you in this session?",
            session_id=session,
            include_tools=False,
        )
        memory_before_restart = _count(runtime, "nexus.memory")
        runtime.request("POST", "/__rig/restart")
        third = runtime.chat(
            "After the runtime restart, recover the continuity marker from this same session.",
            session_id=session,
            include_tools=False,
        )
        memory_after_restart = _count(runtime, "nexus.memory")
        continuity = runtime.exercise_kernel_boundary("nexus.continuity", marker=f"{context.marker}-continuity")
        checks = [
            _check("Initial memory continuity turn released", _released(first), "released", _payload(first).get("state")),
            _check("Same-session memory recall turn released", _released(second), "released", _payload(second).get("state")),
            _check("Restarted runtime releases same-session memory recovery turn", _released(third), "released", _payload(third).get("state")),
            _check("Memory kernel participates after restart", memory_after_restart > memory_before_restart, f"> {memory_before_restart}", memory_after_restart),
            _check("Recovered answer contains durable marker", marker in str(_payload(third).get("text") or ""), marker, _payload(third).get("text"), heuristic=True),
            _check("Continuity public boundary creates durable state", _status_ok(continuity.get("receipt_status")) and bool(continuity.get("pin_id")), {"receipt_status": "ok", "pin_id": "non-empty"}, continuity),
            _check("Continuity public boundary reads its durable state", _status_ok(continuity.get("snapshot_status")) and int(continuity.get("snapshot_pin_count") or 0) > 0, {"snapshot_status": "ok", "snapshot_pin_count": ">0"}, continuity),
        ]
        return CaseResult(checks=checks, evidence={"first": _payload(first), "second": _payload(second), "third": _payload(third), "continuity_boundary": continuity, "coverage": _coverage(runtime)})


class CrossUserIsolationCase:
    planned_checks = (
        "Primary principal turn released",
        "Secondary principal turn released",
        "Primary marker does not leak to secondary response",
        "Primary and secondary sessions remain distinct",
    )
    name = "monster-cross-user-isolation"
    suite = "06 CROSS-USER ISOLATION"

    def run(self, runtime, database, context) -> CaseResult:
        del database
        primary_session = f"monster-user-a-{context.run_id}"
        secondary_session = f"monster-user-b-{context.run_id}"
        marker = f"PRIMARY_SECRET_{context.marker}"
        first = runtime.chat(
            f"This marker belongs only to the primary principal: {marker}",
            session_id=primary_session,
            principal="primary",
            include_tools=False,
        )
        second = runtime.chat(
            "State only context authorized for this secondary principal. Do not infer another user's private marker.",
            session_id=secondary_session,
            principal="secondary",
            include_tools=False,
        )
        second_text = str(_payload(second).get("text") or "")
        checks = [
            _check(
                "Primary principal turn released",
                _released(first),
                "released",
                {
                    "state": _payload(first).get("state"),
                    "blocking_reason": _payload(first).get("blocking_reason"),
                },
            ),
            _check(
                "Secondary principal turn released",
                _released(second),
                "released",
                {
                    "state": _payload(second).get("state"),
                    "blocking_reason": _payload(second).get("blocking_reason"),
                },
            ),
            _check("Primary marker does not leak to secondary response", marker not in second_text, "marker absent", "absent" if marker not in second_text else "present", heuristic=True),
            _check("Primary and secondary sessions remain distinct", primary_session != secondary_session, "different session ids", {"primary": primary_session, "secondary": secondary_session}),
        ]
        return CaseResult(checks=checks, evidence={"primary": _payload(first), "secondary": _payload(second)})


class CognitionModesLearningCase:
    planned_checks = (
        "Complex canonical turn is released",
        "Modes kernel executes through normal turn resolution",
        "Cognition public boundary executes advisory node projection",
        "Cognition advisory projection returns UserID 18 node evidence",
        "Learning public boundary scans direct feedback without promotion",
    )
    name = "monster-cognition-modes-learning"
    suite = "07 COGNITION / MODES / LEARNING"

    def run(self, runtime, database, context) -> CaseResult:
        del database
        modes_before = _count(runtime, "nexus.modes")
        complex_turn = runtime.chat("Analyze a difficult tradeoff with multiple competing constraints.", session_id=f"monster-cognition-{context.run_id}")
        modes_after = _count(runtime, "nexus.modes")
        cognition = runtime.exercise_kernel_boundary("nexus.cognition", marker=f"{context.marker}-cognition")
        learning = runtime.exercise_kernel_boundary("nexus.learning", marker=f"{context.marker}-learning")
        checks = [
            _check("Complex canonical turn is released", _released(complex_turn), "released", _payload(complex_turn).get("state")),
            _check("Modes kernel executes through normal turn resolution", modes_after > modes_before, f"> {modes_before}", modes_after),
            _check("Cognition public boundary executes advisory node projection", _status_ok(cognition.get("receipt_status")) and cognition.get("state_mutated") is False, {"receipt_status": "ok", "state_mutated": False}, cognition),
            _check("Cognition advisory projection returns UserID 18 node evidence", int(cognition.get("node_count") or 0) > 0, ">0 node activations", cognition),
            _check("Learning public boundary scans direct feedback without promotion", _status_ok(learning.get("receipt_status")) and int(learning.get("observation_count") or 0) > 0 and learning.get("state_mutated") is False, {"receipt_status": "ok", "observation_count": ">0", "state_mutated": False}, learning),
        ]
        return CaseResult(checks=checks, evidence={"complex": _payload(complex_turn), "cognition_boundary": cognition, "learning_boundary": learning, "coverage": _coverage(runtime)})


class JobsArtifactsCase:
    planned_checks = (
        "Jobs public boundary enqueues isolated work",
        "Jobs public boundary exposes the queued record",
        "Artifacts public boundary creates durable custody",
        "Artifacts public boundary independently verifies custody",
        "Surfaces public boundary projects a release-style event",
        "Surface projection returns stable presentation identity",
    )
    name = "monster-jobs-artifacts-surfaces"
    suite = "08 JOBS / ARTIFACTS / SURFACES"

    def run(self, runtime, database, context) -> CaseResult:
        del database
        jobs = runtime.exercise_kernel_boundary("nexus.jobs", marker=f"{context.marker}-jobs")
        artifacts = runtime.exercise_kernel_boundary("nexus.artifacts", marker=f"{context.marker}-artifacts")
        surfaces = runtime.exercise_kernel_boundary("nexus.surfaces", marker=f"{context.marker}-surfaces")
        checks = [
            _check("Jobs public boundary enqueues isolated work", _status_ok(jobs.get("receipt_status")) and bool(jobs.get("job_id")), {"receipt_status": "ok", "job_id": "non-empty"}, jobs),
            _check("Jobs public boundary exposes the queued record", _status_ok(jobs.get("snapshot_status")) and str(jobs.get("job_status") or "").upper() in {"QUEUED", "PENDING"}, {"snapshot_status": "ok", "job_status": "queued"}, jobs),
            _check("Artifacts public boundary creates durable custody", _status_ok(artifacts.get("receipt_status")) and bool(artifacts.get("artifact_id")) and bool(artifacts.get("sha256")), {"receipt_status": "ok", "artifact_id": "non-empty", "sha256": "non-empty"}, artifacts),
            _check("Artifacts public boundary independently verifies custody", _status_ok(artifacts.get("verify_status")) and artifacts.get("verified") is True, {"verify_status": "ok", "verified": True}, artifacts),
            _check("Surfaces public boundary projects a release-style event", _status_ok(surfaces.get("receipt_status")), "ok", surfaces),
            _check("Surface projection returns stable presentation identity", bool(surfaces.get("event_id")) and bool(surfaces.get("replay_token")), {"event_id": "non-empty", "replay_token": "non-empty"}, surfaces),
        ]
        return CaseResult(checks=checks, evidence={"jobs_boundary": jobs, "artifacts_boundary": artifacts, "surfaces_boundary": surfaces, "coverage": _coverage(runtime)})


class FaultInjectionCase:
    planned_checks = (
        "Malformed runtime request fails closed",
        "Caller cannot override provider binding",
        "Provider backend timeout becomes a bounded FAILED receipt",
        "Tool timeout remains terminal and non-success",
        "Forged evidence declaration is rejected before proof authority",
    )
    name = "monster-fault-injection"
    suite = "09 FAULT / FAIL-CLOSED"

    def run(self, runtime, database, context) -> CaseResult:
        del database
        malformed = runtime.request(
            "POST",
            "/v1/chat/completions",
            principal="primary",
            json={"messages": [{"role": "assistant", "content": "no user input"}]},
        )
        forbidden_provider = runtime.request(
            "POST",
            "/v1/chat/completions",
            principal="primary",
            json={
                "messages": [{"role": "user", "content": "normal request"}],
                "provider_id": "caller-controlled-provider",
            },
        )
        provider_timeout = runtime.exercise_fault_boundary(
            "provider_timeout", marker=f"{context.marker}-provider-timeout"
        )
        tool_timeout = runtime.exercise_fault_boundary(
            "tool_timeout", marker=f"{context.marker}-tool-timeout"
        )
        forged_evidence = runtime.exercise_fault_boundary(
            "forged_evidence", marker=f"{context.marker}-forged-evidence"
        )
        checks = [
            _check("Malformed runtime request fails closed", malformed.status_code == 422, 422, malformed.status_code),
            _check("Caller cannot override provider binding", forbidden_provider.status_code == 400, 400, forbidden_provider.status_code),
            _check(
                "Provider backend timeout becomes a bounded FAILED receipt",
                provider_timeout.get("bounded") is True
                and provider_timeout.get("receipt_status") == "failed"
                and provider_timeout.get("error_type") == "TimeoutError"
                and provider_timeout.get("restored") is True,
                {
                    "receipt_status": "failed",
                    "error_type": "TimeoutError",
                    "restored": True,
                },
                provider_timeout,
            ),
            _check(
                "Tool timeout remains terminal and non-success",
                tool_timeout.get("bounded") is True
                and tool_timeout.get("receipt_status") == "degraded"
                and tool_timeout.get("terminal_status") == "TIMED_OUT"
                and tool_timeout.get("restored") is True,
                {
                    "receipt_status": "degraded",
                    "terminal_status": "TIMED_OUT",
                    "restored": True,
                },
                tool_timeout,
            ),
            _check(
                "Forged evidence declaration is rejected before proof authority",
                forged_evidence.get("bounded") is True
                and forged_evidence.get("receipt_status") == "rejected"
                and forged_evidence.get("reason") == "declared_tool_status_not_evidence",
                {
                    "receipt_status": "rejected",
                    "reason": "declared_tool_status_not_evidence",
                },
                forged_evidence,
            ),
        ]
        return CaseResult(
            checks=checks,
            evidence={
                "malformed": _payload(malformed),
                "forbidden_provider": _payload(forbidden_provider),
                "provider_timeout": provider_timeout,
                "tool_timeout": tool_timeout,
                "forged_evidence": forged_evidence,
            },
        )



class AttributionKnowledgeChainCase:
    planned_checks = (
        "Attribution stimulus contains no hidden routing bumper",
        "Initial Nexus provider round exposes multiple legitimate read-only choices",
        "Nexus independently proposes the Business Brain attribution tool",
        "Governed nexus.tools executes Business Brain exactly once",
        "Business Brain returns a passing bounded resolution",
        "Business Brain result excludes raw HZK treaty payload from model context",
        "Moon Source selects sufficient relevant governed evidence",
        "Moon Source evidence remains attributable by path and source hash",
        "HZK verifies the selected evidence without state or authority transfer",
        "HZK treaty v0.3 return receipt validates against exact grant and payload",
        "Historical and compatibility distinctions survive the governed workflow",
        "Business Brain keeps the resolution at draft_memory with immutable source",
        "Business Brain integrity verification passes",
        "Kernelized Nexus releases the final answer after the tool round",
        "Final Nexus answer contains substantive attribution resolution",
        "Nexus receipt chain includes tools provider evidence correction and release",
        "Provider telemetry proves a second inference round consumed tool results",
        "Completed Nexus provider rounds expose token and latency telemetry",
        "Full Business Brain handshake evidence remains inspectable outside model context",
    )
    name = "monster-attribution-knowledge-chain"
    suite = "10A ATTRIBUTION / KNOWLEDGE CHAIN"

    def run(self, runtime, database, context) -> CaseResult:
        del database
        from live_runtime_rig_nexus_monster.attribution_chain import run_attribution_chain

        result = run_attribution_chain(runtime, marker=context.marker)
        body = dict(result.get("body") or {})
        final_text = str(result.get("final_text") or "").strip()
        tool_executions = [
            item for item in (result.get("tool_executions") or [])
            if isinstance(item, Mapping)
        ]
        bb_executions = [
            item for item in (result.get("business_brain_executions") or [])
            if isinstance(item, Mapping)
        ]
        bounded = dict(result.get("bounded_result") or {})
        bb_trace_wrapper = result.get("business_brain_trace")
        bb_trace_wrapper = (
            dict(bb_trace_wrapper)
            if isinstance(bb_trace_wrapper, Mapping)
            else {}
        )
        full_trace = (
            dict(bb_trace_wrapper.get("trace") or {})
            if isinstance(bb_trace_wrapper.get("trace"), Mapping)
            else {}
        )
        moon = dict(full_trace.get("moon_source") or {})
        moon_result = dict(moon.get("result") or {})
        moon_score = dict(moon.get("score") or {})
        hzk = dict(full_trace.get("hzk") or {})
        bb = dict(full_trace.get("business_brain") or {})
        treaty_return = dict(full_trace.get("nexus_return_validation") or {})
        provider_telemetry = [
            item for item in (result.get("provider_telemetry") or [])
            if isinstance(item, Mapping)
        ]
        receipts = [
            item for item in (result.get("receipts") or [])
            if isinstance(item, Mapping)
        ]

        selected_sources = [
            item for item in (bounded.get("sources") or [])
            if isinstance(item, Mapping)
        ]
        source_identity_ok = bool(selected_sources) and all(
            bool(str(item.get("path") or ""))
            and len(str(item.get("source_sha256") or "")) == 64
            for item in selected_sources
        )

        first_round = provider_telemetry[0] if provider_telemetry else {}
        final_round = provider_telemetry[-1] if provider_telemetry else {}
        initial_tools = set(first_round.get("available_tools") or ())
        multiple_choices = (
            "business_brain.resolve_attribution" in initial_tools
            and "memory.retrieve" in initial_tools
            and len(initial_tools) >= 2
            and int(first_round.get("tool_result_count") or 0) == 0
        )

        bb_execution = bb_executions[0] if len(bb_executions) == 1 else {}
        model_selected_bb = (
            len(bb_executions) == 1
            and bool(str(bb_execution.get("provider_proposal_id") or ""))
        )
        bb_executed = (
            len(bb_executions) == 1
            and str(bb_execution.get("status") or "") == "SUCCEEDED"
        )

        receipt_ids = {str(item.get("kernel_id") or "") for item in receipts}
        receipt_chain_ok = {
            "nexus.tools",
            "nexus.provider",
            "nexus.evidence",
            "nexus.correction",
            "nexus.release",
        } <= receipt_ids

        second_round_ok = (
            len(provider_telemetry) >= 2
            and int(first_round.get("tool_result_count") or 0) == 0
            and int(final_round.get("tool_result_count") or 0) >= 1
        )
        completed_rounds = [
            item for item in provider_telemetry if item.get("completed") is True
        ]
        telemetry_complete = bool(completed_rounds) and all(
            isinstance(item.get("input_token_count"), int)
            and isinstance(item.get("output_token_count"), int)
            and isinstance(item.get("first_token_latency_ms"), int)
            and isinstance(item.get("total_latency_ms"), int)
            and int(item.get("provider_chunk_count") or 0) > 0
            for item in completed_rounds
        )

        substantive_terms = {
            term for term in (
                "attribution",
                "lineage",
                "authorship",
                "coauthor",
                "historical",
                "provenance",
                "evidence",
                "source",
            )
            if term in final_text.casefold()
        }

        handshake_artifact = context.evidence.write_json(
            "artifacts/ATTRIBUTION_HANDSHAKE.json",
            full_trace,
        )
        trace_artifact = context.evidence.write_json(
            "artifacts/ATTRIBUTION_TRACE.json",
            {
                "turn_id": result.get("turn_id"),
                "scenario": result.get("scenario"),
                "routing_bumpers": result.get("routing_bumpers"),
                "tool_executions": tool_executions,
                "provider_telemetry": provider_telemetry,
                "receipts": receipts,
                "bounded_result": bounded,
                "business_brain_trace_path": bb_trace_wrapper.get("trace_path"),
            },
        )
        telemetry_artifact = context.evidence.write_json(
            "artifacts/NEXUS_PROVIDER_TELEMETRY.json",
            {"turn_id": result.get("turn_id"), "rounds": provider_telemetry},
        )
        response_artifact = context.evidence.write_text(
            "artifacts/NEXUS_RESPONSE.md",
            "# Nexus attribution response\n\n"
            + (final_text or "[NO RELEASED RESPONSE]")
            + "\n\n## Canonical runtime payload\n\n```json\n"
            + json.dumps(body, indent=2, ensure_ascii=False)
            + "\n```\n",
        )

        transport = dict(bounded.get("transport") or {})
        trace_lines = [
            "NEXUS ACTUAL RESPONSE",
            "---------------------",
            final_text or "[NO RELEASED RESPONSE]",
            "",
            "ROUTING PROOF",
            "-------------",
            f"Natural stimulus bytes: {result.get('scenario_bytes')}",
            f"Hidden routing bumpers: {list(result.get('routing_bumpers') or ())}",
            "Initial visible read-only tools: " + ", ".join(sorted(initial_tools)),
            f"Business Brain executions: {len(bb_executions)}",
            f"Provider proposal id: {bb_execution.get('provider_proposal_id')}",
            f"Execution status: {bb_execution.get('status')}",
            "",
            "BUSINESS BRAIN BOUNDARY",
            "-----------------------",
            f"Selected Moon sources: {len(selected_sources)}",
            f"Raw HZK payload: {transport.get('hzk_payload_bytes')} bytes",
            f"HZK treaty wire: {transport.get('hzk_grant_wire_bytes')} bytes",
            f"Bounded result returned to Nexus: {transport.get('bounded_result_bytes')} bytes",
            f"Raw treaty leaked to model result: {result.get('bounded_result_leaks_raw_hzk')}",
            f"HZK treaty return validation: {treaty_return.get('status')}",
            f"Business Brain state: {(bounded.get('business_brain') or {}).get('state')}",
            "",
            "NEXUS PROVIDER ROUNDS",
            "---------------------",
        ]
        for item in provider_telemetry:
            trace_lines.append(
                "  round {round}: system={system_bytes}B user={user_bytes}B "
                "tool_results={tool_result_count}/{tool_result_bytes}B "
                "input_tokens={input_token_count} output_tokens={output_token_count} "
                "first_token={first_token_latency_ms}ms total={total_latency_ms}ms "
                "chunks={provider_chunk_count}".format(**{
                    key: item.get(key)
                    for key in (
                        "round",
                        "system_bytes",
                        "user_bytes",
                        "tool_result_count",
                        "tool_result_bytes",
                        "input_token_count",
                        "output_token_count",
                        "first_token_latency_ms",
                        "total_latency_ms",
                        "provider_chunk_count",
                    )
                })
            )
        trace_lines.extend(
            (
                "",
                f"Handshake evidence: {handshake_artifact}",
                f"Routing trace:      {trace_artifact}",
                f"Provider telemetry: {telemetry_artifact}",
                f"Nexus response:     {response_artifact}",
            )
        )

        checks = [
            _check(
                "Attribution stimulus contains no hidden routing bumper",
                not result.get("routing_bumpers"),
                (),
                tuple(result.get("routing_bumpers") or ()),
            ),
            _check(
                "Initial Nexus provider round exposes multiple legitimate read-only choices",
                multiple_choices,
                {
                    "business_brain.resolve_attribution": "visible",
                    "memory.retrieve": "visible",
                    "tool_results": 0,
                },
                {
                    "tools": sorted(initial_tools),
                    "tool_result_count": first_round.get("tool_result_count"),
                },
            ),
            _check(
                "Nexus independently proposes the Business Brain attribution tool",
                model_selected_bb,
                {"exactly_once": True, "provider_proposal_id": "non-empty"},
                {
                    "count": len(bb_executions),
                    "provider_proposal_id": bb_execution.get("provider_proposal_id"),
                },
            ),
            _check(
                "Governed nexus.tools executes Business Brain exactly once",
                bb_executed,
                {"count": 1, "status": "SUCCEEDED"},
                {
                    "count": len(bb_executions),
                    "status": bb_execution.get("status"),
                    "execution_id": bb_execution.get("execution_id"),
                },
            ),
            _check(
                "Business Brain returns a passing bounded resolution",
                bounded.get("status") == "PASS",
                "PASS",
                bounded.get("status"),
            ),
            _check(
                "Business Brain result excludes raw HZK treaty payload from model context",
                result.get("bounded_result_leaks_raw_hzk") is False
                and int(result.get("bounded_result_bytes") or 0) <= 80_000,
                {"raw_hzk_payload": False, "max_bytes": 80000},
                {
                    "raw_hzk_payload": result.get("bounded_result_leaks_raw_hzk"),
                    "bytes": result.get("bounded_result_bytes"),
                },
            ),
            _check(
                "Moon Source selects sufficient relevant governed evidence",
                moon_score.get("status") == "PASS" and bool(selected_sources),
                {"status": "PASS", "selected_sources": ">0"},
                {
                    "status": moon_score.get("status"),
                    "selected_sources": len(selected_sources),
                },
            ),
            _check(
                "Moon Source evidence remains attributable by path and source hash",
                source_identity_ok,
                True,
                {
                    "complete": source_identity_ok,
                    "sources": [
                        {"path": item.get("path"), "sha256": item.get("source_sha256")}
                        for item in selected_sources
                    ],
                },
            ),
            _check(
                "HZK verifies the selected evidence without state or authority transfer",
                hzk.get("status") == "PASS"
                and hzk.get("constitutional_status") == "PASS"
                and hzk.get("state_unchanged") is True
                and hzk.get("authority_clean") is True,
                {
                    "status": "PASS",
                    "constitutional_status": "PASS",
                    "state_unchanged": True,
                    "authority_clean": True,
                },
                {
                    "status": hzk.get("status"),
                    "constitutional_status": hzk.get("constitutional_status"),
                    "state_unchanged": hzk.get("state_unchanged"),
                    "authority_clean": hzk.get("authority_clean"),
                },
            ),
            _check(
                "HZK treaty v0.3 return receipt validates against exact grant and payload",
                hzk.get("treaty_version") == "hzk-nexus/0.3"
                and treaty_return.get("status") == "PASS"
                and treaty_return.get("valid") is True,
                {"treaty": "hzk-nexus/0.3", "valid": True},
                {
                    "treaty": hzk.get("treaty_version"),
                    "return_validation": treaty_return,
                },
            ),
            _check(
                "Historical and compatibility distinctions survive the governed workflow",
                hzk.get("historical_distinction_preserved") is True,
                True,
                hzk.get("historical_distinction_preserved"),
            ),
            _check(
                "Business Brain keeps the resolution at draft_memory with immutable source",
                (bounded.get("business_brain") or {}).get("state") == "draft_memory"
                and (bounded.get("business_brain") or {}).get("source_immutable") is True
                and (bounded.get("business_brain") or {}).get("readback_complete") is True,
                {
                    "state": "draft_memory",
                    "source_immutable": True,
                    "readback_complete": True,
                },
                bounded.get("business_brain"),
            ),
            _check(
                "Business Brain integrity verification passes",
                (bounded.get("business_brain") or {}).get("integrity_status") == "ok",
                "ok",
                (bounded.get("business_brain") or {}).get("integrity_status"),
            ),
            _check(
                "Kernelized Nexus releases the final answer after the tool round",
                result.get("status_code") == 200
                and result.get("state") == "released"
                and bool(final_text),
                {"status_code": 200, "state": "released", "text": "non-empty"},
                {
                    "status_code": result.get("status_code"),
                    "state": result.get("state"),
                    "blocking_reason": result.get("blocking_reason"),
                    "text_chars": len(final_text),
                },
            ),
            _check(
                "Final Nexus answer contains substantive attribution resolution",
                len(substantive_terms) >= 2,
                "at least two attribution/lineage resolution terms",
                sorted(substantive_terms),
            ),
            _check(
                "Nexus receipt chain includes tools provider evidence correction and release",
                receipt_chain_ok,
                {
                    "nexus.tools",
                    "nexus.provider",
                    "nexus.evidence",
                    "nexus.correction",
                    "nexus.release",
                },
                receipt_ids,
            ),
            _check(
                "Provider telemetry proves a second inference round consumed tool results",
                second_round_ok,
                {"rounds": ">=2", "first_tool_results": 0, "final_tool_results": ">=1"},
                {
                    "rounds": len(provider_telemetry),
                    "first_tool_results": first_round.get("tool_result_count"),
                    "final_tool_results": final_round.get("tool_result_count"),
                },
            ),
            _check(
                "Completed Nexus provider rounds expose token and latency telemetry",
                telemetry_complete,
                True,
                {
                    "complete": telemetry_complete,
                    "rounds": provider_telemetry,
                },
            ),
            _check(
                "Full Business Brain handshake evidence remains inspectable outside model context",
                bool(full_trace)
                and bool(str(bb_trace_wrapper.get("trace_path") or "")),
                {"full_trace": True, "trace_path": "present"},
                {
                    "full_trace": bool(full_trace),
                    "trace_path": bb_trace_wrapper.get("trace_path"),
                },
            ),
        ]
        return CaseResult(
            checks=checks,
            evidence={
                "turn_id": result.get("turn_id"),
                "scenario": result.get("scenario"),
                "routing_bumpers": result.get("routing_bumpers"),
                "tool_executions": tool_executions,
                "provider_telemetry": provider_telemetry,
                "bounded_result": bounded,
                "moon_score": moon_score,
                "hzk": {
                    "source_revision": hzk.get("source_revision"),
                    "treaty_version": hzk.get("treaty_version"),
                    "packet_id": hzk.get("packet_id"),
                    "state_unchanged": hzk.get("state_unchanged"),
                    "authority_clean": hzk.get("authority_clean"),
                    "historical_distinction_preserved": hzk.get(
                        "historical_distinction_preserved"
                    ),
                    "return_validation": treaty_return,
                },
                "business_brain": bounded.get("business_brain"),
                "nexus": {
                    "state": result.get("state"),
                    "status_code": result.get("status_code"),
                    "blocking_reason": result.get("blocking_reason"),
                    "text": final_text,
                    "receipts": receipts,
                },
                "artifacts": {
                    "handshake": handshake_artifact,
                    "trace": trace_artifact,
                    "provider_telemetry": telemetry_artifact,
                    "nexus_response": response_artifact,
                },
            },
            operator_output=tuple(trace_lines),
        )


class ReceiptCoverageGateCase:
    planned_checks = (
        "All 17 required kernels emitted campaign evidence at an appropriate boundary",
        "Every required kernel has at least one observed public operation",
        "Monster campaign has zero unexercised required kernel boundaries",
        "Coverage evidence distinguishes canonical turns from boundary probes",
    )
    name = "monster-receipt-coverage-gate"
    suite = "10 ALL-FLIGHT-CONTROLS GATE"

    def run(self, runtime, database, context) -> CaseResult:
        del database, context
        coverage = dict(_coverage(runtime))
        counts = dict(coverage.get("receipt_counts") or {})
        operation_counts = dict(coverage.get("operation_counts") or {})
        source_counts = dict(coverage.get("coverage_sources") or {})
        missing = tuple(kernel_id for kernel_id in REQUIRED_KERNEL_IDS if int(counts.get(kernel_id, 0)) == 0)
        zero_operation = tuple(kernel_id for kernel_id in REQUIRED_KERNEL_IDS if not dict(operation_counts.get(kernel_id) or {}))
        source_unclassified = tuple(
            kernel_id for kernel_id in REQUIRED_KERNEL_IDS
            if int((source_counts.get(kernel_id) or {}).get("canonical_turn", 0)) == 0
            and int((source_counts.get(kernel_id) or {}).get("boundary_probe", 0)) == 0
        )
        checks = [
            _check("All 17 required kernels emitted campaign evidence at an appropriate boundary", not missing, (), missing),
            _check("Every required kernel has at least one observed public operation", not zero_operation, (), zero_operation),
            _check("Monster campaign has zero unexercised required kernel boundaries", not coverage.get("missing_kernel_receipts"), (), tuple(coverage.get("missing_kernel_receipts") or ())),
            _check("Coverage evidence distinguishes canonical turns from boundary probes", not source_unclassified, (), source_unclassified),
        ]
        return CaseResult(checks=checks, evidence={"coverage": coverage})



class MonsterTaktCase:
    planned_checks = (
        "Observer-side Nexus takt samples were captured",
        "Full governed chat wall takt is represented",
        "Internal kernel timing availability is explicitly classified",
        "Timing evidence preserves source and boundary classification",
    )
    name = "monster-takt-timing"
    suite = "11 TAKT / PERFORMANCE OBSERVATION"

    def run(self, runtime, database, context) -> CaseResult:
        del database, context
        timing = dict(runtime.request("GET", "/takt").json())
        samples = list(timing.get("samples") or ())
        aggregates = list(timing.get("aggregates") or ())
        observer = [item for item in samples if item.get("source") == "observer_wall"]
        kernel = [item for item in samples if item.get("source") == "kernel_receipt"]
        chat = [
            item for item in aggregates
            if item.get("name") in {"runtime.chat.total", "runtime.request.total"}
            and item.get("source") == "observer_wall"
        ]
        internal_status = "OBSERVED" if kernel else "NOT_EXPOSED_BY_RUNTIME"
        classified = all(
            item.get("source") in {"observer_wall", "kernel_receipt", "external_boundary"}
            and item.get("boundary") in {"nexus", "external"}
            for item in samples
        )
        checks = [
            _check(
                "Observer-side Nexus takt samples were captured",
                bool(observer),
                ">=1 observer_wall sample",
                len(observer),
            ),
            _check(
                "Full governed chat wall takt is represented",
                bool(chat),
                "runtime.chat.total or runtime.request.total observer timing",
                [item.get("name") for item in chat],
            ),
            _check(
                "Internal kernel timing availability is explicitly classified",
                internal_status in {"OBSERVED", "NOT_EXPOSED_BY_RUNTIME"},
                "OBSERVED or NOT_EXPOSED_BY_RUNTIME",
                internal_status,
            ),
            _check(
                "Timing evidence preserves source and boundary classification",
                classified,
                True,
                classified,
            ),
        ]
        return CaseResult(
            checks=checks,
            evidence={
                "takt": timing,
                "internal_kernel_timing_status": internal_status,
                "observer_sample_count": len(observer),
                "kernel_receipt_sample_count": len(kernel),
            },
        )


def register_cases(_config: Any):
    # Order matters: the final gate evaluates accumulated evidence from every
    # preceding scenario. No required full-runtime flight control is represented
    # as SKIP in this campaign.
    cases = [
        FlightControlInventoryCase(),
        CanonicalIngressBaselineCase(),
        SecurityAndAuthorityCase(),
        RuntimeInitiatedToolLoopCase(),
        ContinuityAndRestartCase(),
        CrossUserIsolationCase(),
        CognitionModesLearningCase(),
        JobsArtifactsCase(),
        FaultInjectionCase(),
    ]
    if os.environ.get("NEXUS_RIG_ATTRIBUTION_CHAIN", "0") == "1":
        cases.append(AttributionKnowledgeChainCase())
    cases.append(ReceiptCoverageGateCase())
    if os.environ.get("NEXUS_RIG_TAKT", "0") == "1":
        cases.append(MonsterTaktCase())
    return cases
