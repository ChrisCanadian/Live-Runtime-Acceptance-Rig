"""Full-runtime flight-control campaign for kernelized Nexus Synapse.

Every turn in this module enters through the canonical /v1/chat/completions
boundary. Required responsibilities never SKIP: if the runtime cannot exercise a
flight control, the check FAILs and the final receipt-coverage gate remains red.
"""

from __future__ import annotations

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
                and (health.get("analysis_probe") or {}).get("source") == "hf_api_lightweight"
                and (health.get("analysis_probe") or {}).get("static_defaults") is False,
                {
                    "status": "ok",
                    "source": "hf_api_lightweight",
                    "static_defaults": False,
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
        tools_before = _count(runtime, "nexus.tools")
        evidence_before = _count(runtime, "nexus.evidence")
        provider_before = _count(runtime, "nexus.provider")
        response = runtime.chat(
            "Use the available calculation tool to compute 17 * 19. Do not answer from mental arithmetic; invoke the runtime tool and then synthesize the verified result.",
            session_id=session,
            include_tools=True,
        )
        body = _payload(response)
        tools_after = _count(runtime, "nexus.tools")
        evidence_after = _count(runtime, "nexus.evidence")
        provider_after = _count(runtime, "nexus.provider")
        checks = [
            _check("Tool-loop turn is released", _released(response), "released", {"status": response.status_code, "state": body.get("state")}),
            _check("Runtime, not the test, executes a tool round", tools_after - tools_before >= 2, ">=2 new tools receipts (visibility/proposal + execution)", tools_after - tools_before),
            _check("Evidence re-authenticates after tool execution", evidence_after - evidence_before >= 2, ">=2 new evidence receipts", evidence_after - evidence_before),
            _check("Provider is invoked again after tool result", provider_after - provider_before >= 2, ">=2 new provider receipts", provider_after - provider_before),
            _check("Verified tool result reaches final response", "323" in str(body.get("text") or ""), "response contains 323", body.get("text"), heuristic=True),
        ]
        return CaseResult(checks=checks, evidence={"response": body, "coverage": _coverage(runtime)})


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
        first = runtime.chat(f"Remember this exact continuity marker for this acceptance session: {marker}", session_id=session)
        second = runtime.chat("What continuity marker did I give you in this session?", session_id=session)
        memory_before_restart = _count(runtime, "nexus.memory")
        runtime.request("POST", "/__rig/restart")
        third = runtime.chat("After the runtime restart, recover the continuity marker from this same session.", session_id=session)
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
        )
        second = runtime.chat(
            "State only context authorized for this secondary principal. Do not infer another user's private marker.",
            session_id=secondary_session,
            principal="secondary",
        )
        second_text = str(_payload(second).get("text") or "")
        checks = [
            _check("Primary principal turn released", _released(first), "released", _payload(first).get("state")),
            _check("Secondary principal turn released", _released(second), "released", _payload(second).get("state")),
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
        "Provider failure injection flight control is commissioned",
        "Tool timeout injection flight control is commissioned",
        "Evidence failure injection flight control is commissioned",
    )
    name = "monster-fault-injection"
    suite = "09 FAULT / FAIL-CLOSED"

    def run(self, runtime, database, context) -> CaseResult:
        del database, context
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
        checks = [
            _check("Malformed runtime request fails closed", malformed.status_code == 422, 422, malformed.status_code),
            _check("Caller cannot override provider binding", forbidden_provider.status_code == 400, 400, forbidden_provider.status_code),
            _check("Provider failure injection flight control is commissioned", False, "real provider failure injected and bounded receipt observed", "TEST REQUIRED: no runtime fault-injection control exposed"),
            _check("Tool timeout injection flight control is commissioned", False, "tool timeout injected and bounded receipt observed", "TEST REQUIRED: no runtime fault-injection control exposed"),
            _check("Evidence failure injection flight control is commissioned", False, "evidence failure injected and release blocked", "TEST REQUIRED: no runtime fault-injection control exposed"),
        ]
        return CaseResult(checks=checks, evidence={"malformed": _payload(malformed), "forbidden_provider": _payload(forbidden_provider)})


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


def register_cases(_config: Any):
    # Order matters: the final gate evaluates accumulated evidence from every
    # preceding scenario. No required full-runtime flight control is represented
    # as SKIP in this campaign.
    return [
        FlightControlInventoryCase(),
        CanonicalIngressBaselineCase(),
        SecurityAndAuthorityCase(),
        RuntimeInitiatedToolLoopCase(),
        ContinuityAndRestartCase(),
        CrossUserIsolationCase(),
        CognitionModesLearningCase(),
        JobsArtifactsCase(),
        FaultInjectionCase(),
        ReceiptCoverageGateCase(),
    ]
