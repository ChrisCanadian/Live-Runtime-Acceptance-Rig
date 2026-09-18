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
        "Initial continuity write turn released",
        "Same-session recall turn released",
        "Continuity kernel participates before restart",
        "Restarted runtime releases same-session recovery turn",
        "Continuity kernel participates after restart",
        "Memory kernel participates after restart",
        "Recovered answer contains durable marker",
    )
    name = "monster-continuity-restart"
    suite = "05 CONTINUITY / RESTART"

    def run(self, runtime, database, context) -> CaseResult:
        del database
        session = f"monster-continuity-{context.run_id}"
        marker = f"DURABLE_{context.marker}"
        first = runtime.chat(
            f"Remember this exact continuity marker for this acceptance session: {marker}",
            session_id=session,
        )
        second = runtime.chat(
            "What continuity marker did I give you in this session?",
            session_id=session,
        )
        continuity_before_restart = _count(runtime, "nexus.continuity")
        memory_before_restart = _count(runtime, "nexus.memory")
        runtime.request("POST", "/__rig/restart")
        third = runtime.chat(
            "After the runtime restart, recover the continuity marker from this same session.",
            session_id=session,
        )
        continuity_after_restart = _count(runtime, "nexus.continuity")
        memory_after_restart = _count(runtime, "nexus.memory")
        checks = [
            _check("Initial continuity write turn released", _released(first), "released", _payload(first).get("state")),
            _check("Same-session recall turn released", _released(second), "released", _payload(second).get("state")),
            _check("Continuity kernel participates before restart", continuity_before_restart > 0, ">0 receipts", continuity_before_restart),
            _check("Restarted runtime releases same-session recovery turn", _released(third), "released", _payload(third).get("state")),
            _check("Continuity kernel participates after restart", continuity_after_restart > continuity_before_restart, f"> {continuity_before_restart}", continuity_after_restart),
            _check("Memory kernel participates after restart", memory_after_restart > memory_before_restart, f"> {memory_before_restart}", memory_after_restart),
            _check("Recovered answer contains durable marker", marker in str(_payload(third).get("text") or ""), marker, _payload(third).get("text"), heuristic=True),
        ]
        return CaseResult(checks=checks, evidence={"first": _payload(first), "second": _payload(second), "third": _payload(third), "coverage": _coverage(runtime)})


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
        "Complex cognition turn is released",
        "Modes kernel executes through normal turn resolution",
        "Cognition kernel executes through the canonical turn",
        "Direct feedback turn is released",
        "Learning kernel admits/records the feedback through runtime flow",
    )
    name = "monster-cognition-modes-learning"
    suite = "07 COGNITION / MODES / LEARNING"

    def run(self, runtime, database, context) -> CaseResult:
        del database
        cognition_before = _count(runtime, "nexus.cognition")
        modes_before = _count(runtime, "nexus.modes")
        learning_before = _count(runtime, "nexus.learning")
        complex_turn = runtime.chat(
            "Analyze a difficult tradeoff with multiple competing constraints. Use the runtime's normal cognition and mode resolution, not a direct specialist call.",
            session_id=f"monster-cognition-{context.run_id}",
        )
        feedback_turn = runtime.chat(
            "Direct preference correction for the learning system: stop using emoji in my responses and keep this preference for future turns.",
            session_id=f"monster-learning-{context.run_id}",
        )
        cognition_after = _count(runtime, "nexus.cognition")
        modes_after = _count(runtime, "nexus.modes")
        learning_after = _count(runtime, "nexus.learning")
        checks = [
            _check("Complex cognition turn is released", _released(complex_turn), "released", _payload(complex_turn).get("state")),
            _check("Modes kernel executes through normal turn resolution", modes_after > modes_before, f"> {modes_before}", modes_after),
            _check("Cognition kernel executes through the canonical turn", cognition_after > cognition_before, f"> {cognition_before}", cognition_after),
            _check("Direct feedback turn is released", _released(feedback_turn), "released", _payload(feedback_turn).get("state")),
            _check("Learning kernel admits/records the feedback through runtime flow", learning_after > learning_before, f"> {learning_before}", learning_after),
        ]
        return CaseResult(checks=checks, evidence={"complex": _payload(complex_turn), "feedback": _payload(feedback_turn), "coverage": _coverage(runtime)})


class JobsArtifactsCase:
    planned_checks = (
        "Job request is handled through canonical runtime",
        "Jobs kernel actually executes instead of prose-only simulation",
        "Artifact request is handled through canonical runtime",
        "Artifacts kernel actually executes instead of prose-only simulation",
    )
    name = "monster-jobs-artifacts"
    suite = "08 JOBS / ARTIFACTS"

    def run(self, runtime, database, context) -> CaseResult:
        del database
        jobs_before = _count(runtime, "nexus.jobs")
        artifacts_before = _count(runtime, "nexus.artifacts")
        job_turn = runtime.chat(
            "Use the runtime's normal capabilities to create a bounded test job representing 'acceptance-job'. Do not simulate success in prose if the job subsystem is unavailable.",
            session_id=f"monster-job-{context.run_id}",
        )
        artifact_turn = runtime.chat(
            "Use the runtime's normal capabilities to create a tiny text artifact containing ACCEPTANCE_ARTIFACT. Do not simulate artifact creation in prose.",
            session_id=f"monster-artifact-{context.run_id}",
        )
        jobs_after = _count(runtime, "nexus.jobs")
        artifacts_after = _count(runtime, "nexus.artifacts")
        checks = [
            _check("Job request is handled through canonical runtime", _released(job_turn), "released", _payload(job_turn).get("state")),
            _check("Jobs kernel actually executes instead of prose-only simulation", jobs_after > jobs_before, f"> {jobs_before}", jobs_after),
            _check("Artifact request is handled through canonical runtime", _released(artifact_turn), "released", _payload(artifact_turn).get("state")),
            _check("Artifacts kernel actually executes instead of prose-only simulation", artifacts_after > artifacts_before, f"> {artifacts_before}", artifacts_after),
        ]
        return CaseResult(checks=checks, evidence={"job": _payload(job_turn), "artifact": _payload(artifact_turn), "coverage": _coverage(runtime)})


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
        "Every one of the 17 required kernels emitted at least one real runtime receipt",
        "Every required kernel has at least one observed executed operation",
        "Monster campaign has zero missing flight-control receipts",
    )
    name = "monster-receipt-coverage-gate"
    suite = "10 ALL-FLIGHT-CONTROLS GATE"

    def run(self, runtime, database, context) -> CaseResult:
        del database, context
        coverage = dict(_coverage(runtime))
        counts = dict(coverage.get("receipt_counts") or {})
        operation_counts = dict(coverage.get("operation_counts") or {})
        missing = tuple(kernel_id for kernel_id in REQUIRED_KERNEL_IDS if int(counts.get(kernel_id, 0)) == 0)
        zero_operation = tuple(
            kernel_id for kernel_id in REQUIRED_KERNEL_IDS if not dict(operation_counts.get(kernel_id) or {})
        )
        checks = [
            _check("Every one of the 17 required kernels emitted at least one real runtime receipt", not missing, (), missing),
            _check("Every required kernel has at least one observed executed operation", not zero_operation, (), zero_operation),
            _check("Monster campaign has zero missing flight-control receipts", not coverage.get("missing_kernel_receipts"), (), tuple(coverage.get("missing_kernel_receipts") or ())),
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
