"""Acceptance cases for the kernelized Nexus Synapse TEST runtime."""

from __future__ import annotations

import hashlib
import os
from typing import Any, Mapping

from live_runtime_rig.assertions import CheckStatus
from live_runtime_rig.contracts import CaseResult, CheckSpec


def _check(
    name: str,
    condition: bool,
    expected: Any,
    observed: Any,
    *,
    heuristic: bool = False,
) -> CheckSpec:
    return CheckSpec(
        name=name,
        status=CheckStatus.PASS if condition else CheckStatus.FAIL,
        expected=expected,
        observed=observed,
        heuristic=heuristic,
    )


def _skip(name: str, expected: Any, observed: Any) -> CheckSpec:
    return CheckSpec(
        name=name,
        status=CheckStatus.SKIP,
        expected=expected,
        observed=observed,
    )


def _primary_id() -> str | None:
    return os.environ.get("NEXUS_RIG_PRIMARY_DISCORD_ID") or None


def _secondary_id() -> str | None:
    return os.environ.get("NEXUS_RIG_SECONDARY_DISCORD_ID") or None


def _message(
    *,
    external_user_id: str,
    message_id: str,
    text: str,
    channel_id: str = "acceptance-channel",
    guild_id: str = "acceptance-guild",
    thread_id: str = "acceptance-thread",
) -> Mapping[str, Any]:
    return {
        "external_user_id": external_user_id,
        "message_id": message_id,
        "text": text,
        "channel_id": channel_id,
        "guild_id": guild_id,
        "thread_id": thread_id,
    }


class KernelizedReadinessCase:
    name = "kernelized-readiness"
    suite = "KERNELIZED HOST"

    def run(self, runtime, database, context) -> CaseResult:
        del database, context
        health = dict(runtime.health())
        inventory = runtime.request("GET", "/kernel-inventory").json()
        checks = [
            _check(
                "Authoritative registry contains exactly 17 expected kernels",
                health.get("expected_kernel_count") == 17
                and health.get("present_kernel_count") == 17,
                {"expected": 17, "present": 17},
                {
                    "expected": health.get("expected_kernel_count"),
                    "present": health.get("present_kernel_count"),
                },
            ),
            _check(
                "Authoritative registry has no missing kernels",
                tuple(inventory.get("missing", ())) == (),
                (),
                tuple(inventory.get("missing", ())),
            ),
            _check(
                "Authoritative registry has no unexpected kernels",
                tuple(inventory.get("unexpected", ())) == (),
                (),
                tuple(inventory.get("unexpected", ())),
            ),
            _check(
                "No kernel is FAILED for TEST",
                tuple(health.get("failed_kernel_ids", ())) == (),
                (),
                tuple(health.get("failed_kernel_ids", ())),
            ),
            _check(
                "Discord foreground operation gate is ready",
                health.get("discord_foreground_ready") is True
                and not health.get("foreground_missing_operations"),
                {"ready": True, "missing_operations": {}},
                {
                    "ready": health.get("discord_foreground_ready"),
                    "missing_operations": health.get("foreground_missing_operations"),
                },
            ),
        ]
        return CaseResult(checks=checks, evidence={"health": health, "inventory": inventory})


class DiscordFirstContactCase:
    name = "discord-first-contact-isolation"
    suite = "DISCORD AUTHORITY"

    def run(self, runtime, database, context) -> CaseResult:
        del database
        digest = hashlib.sha256(context.run_id.encode("utf-8")).hexdigest()
        guest_id = str(int(digest[:15], 16) % (10**18)).zfill(18)
        response = runtime.request(
            "POST",
            "/discord/chat",
            json=_message(
                external_user_id=guest_id,
                message_id=f"{context.marker}-first-contact",
                text="Hello. This is a first-contact acceptance identity.",
            ),
        )
        body = response.json()
        metadata = body.get("metadata") or {}
        turn = body.get("governed_turn") or {}
        isolated_created = bool(
            metadata.get("auto_provisioned_user")
            or metadata.get("discord_native_account")
        )
        checks = [
            _check(
                "Unknown Discord identity receives isolated Nexus first-contact provisioning",
                body.get("state") == "RELEASED" and isolated_created,
                {"state": "RELEASED", "isolated_identity_created": True},
                {
                    "state": body.get("state"),
                    "isolated_identity_created": isolated_created,
                    "reason": metadata.get("reason"),
                },
            ),
            _check(
                "First-contact identity enters the governed runtime after provisioning",
                turn.get("available") is True,
                True,
                turn.get("available"),
            ),
        ]
        return CaseResult(checks=checks, evidence={"first_contact": body})


class DiscordGovernedTurnCase:
    name = "discord-governed-turn"
    suite = "DISCORD GOVERNED TURN"

    REQUIRED_RECEIPT_KERNELS = frozenset(
        {
            "nexus.analysis",
            "nexus.memory",
            "nexus.identity",
            "nexus.context",
            "nexus.provider",
            "nexus.evidence",
            "nexus.correction",
            "nexus.release",
        }
    )

    def run(self, runtime, database, context) -> CaseResult:
        del database
        user = _primary_id()
        if user is None:
            return CaseResult(
                checks=[
                    _skip(
                        "Linked Discord governed turn",
                        "NEXUS_RIG_PRIMARY_DISCORD_ID configured",
                        "protected primary Discord identity not configured",
                    )
                ]
            )
        response = runtime.request(
            "POST",
            "/discord/chat",
            json=_message(
                external_user_id=user,
                message_id=f"{context.marker}-turn-1",
                text=f"Acceptance marker {context.marker}. Reply briefly and preserve governed execution.",
            ),
        )
        body = response.json()
        turn = dict(body.get("governed_turn") or {})
        receipt_ids = frozenset(turn.get("receipt_kernel_ids") or ())
        missing = tuple(sorted(self.REQUIRED_RECEIPT_KERNELS - receipt_ids))
        receipt_statuses = {
            item.get("kernel_id"): item.get("status")
            for item in turn.get("receipt_chain") or ()
            if item.get("kernel_id")
        }
        bad_statuses = {
            key: value
            for key, value in receipt_statuses.items()
            if value not in {"ok", "degraded"}
        }
        checks = [
            _check("Linked Discord turn is released", body.get("state") == "RELEASED", "RELEASED", body.get("state")),
            _check("Released Discord turn contains response text", bool(str(body.get("text") or "").strip()), "non-empty", bool(str(body.get("text") or "").strip())),
            _check("Governed turn bundle was observed", turn.get("available") is True, True, turn.get("available")),
            _check("Required governed receipt kernels are present", not missing, (), missing),
            _check("Observed governed receipts are non-failed", not bad_statuses, {}, bad_statuses),
            _check("Discord release has a projected surface event", bool(body.get("event_id")), "event id", body.get("event_id")),
        ]
        return CaseResult(
            checks=checks,
            evidence={
                "reply": {
                    "state": body.get("state"),
                    "session_id": body.get("session_id"),
                    "correlation_id": body.get("correlation_id"),
                    "event_id": body.get("event_id"),
                },
                "governed_turn": turn,
                "missing_required_receipts": missing,
            },
            state_updates={"primary_session_id": body.get("session_id")},
        )


class DiscordCommandsCase:
    name = "discord-shared-commands"
    suite = "DISCORD SHARED KERNELS"

    def run(self, runtime, database, context) -> CaseResult:
        del database
        user = _primary_id()
        if user is None:
            return CaseResult(
                checks=[_skip("Shared Discord kernel commands", "linked primary identity", "not configured")]
            )
        base = _message(
            external_user_id=user,
            message_id=f"{context.marker}-commands",
            text="",
        )
        model_mutation = runtime.request(
            "POST", "/discord/command", json={**base, "command": "model", "arguments": ["set", "forbidden-model"]}
        ).json()
        model_status = runtime.request(
            "POST", "/discord/command", json={**base, "message_id": f"{context.marker}-model-status", "command": "model", "arguments": []}
        ).json()
        mode_list = runtime.request(
            "POST", "/discord/command", json={**base, "message_id": f"{context.marker}-mode-list", "command": "mode", "arguments": ["list"]}
        ).json()
        tools = runtime.request(
            "POST", "/discord/command", json={**base, "message_id": f"{context.marker}-tools", "command": "tools", "arguments": []}
        ).json()
        checks = [
            _check("Discord cannot mutate model selection per request", model_mutation.get("state") == "READ_ONLY", "READ_ONLY", model_mutation.get("state")),
            _check("Discord can read installation-managed inference status", model_status.get("state") == "OK", "OK", model_status.get("state")),
            _check("Discord mode listing comes through nexus.modes", mode_list.get("state") == "OK", "OK", mode_list.get("state")),
            _check("Discord tools catalog comes through nexus.tools", tools.get("state") == "OK", "OK", tools.get("state")),
            _check(
                "Discord exposes a non-empty ordinary-callable tool catalog",
                bool(str(tools.get("text") or "").strip()),
                "non-empty ordinary callable catalog",
                bool(str(tools.get("text") or "").strip()),
            ),
        ]
        return CaseResult(
            checks=checks,
            evidence={
                "model_mutation": model_mutation,
                "model_status": model_status,
                "mode_list": mode_list,
                "tools": tools,
            },
        )


class MultiTurnContinuityCase:
    name = "discord-multi-turn-canonical-session"
    suite = "MEMORY CONTINUITY"

    def run(self, runtime, database, context) -> CaseResult:
        del database
        user = _primary_id()
        if user is None:
            return CaseResult(
                checks=[_skip("Multi-turn canonical session continuity", "linked primary identity", "not configured")]
            )
        channel = f"acceptance-continuity-{context.run_id}"
        thread = f"acceptance-thread-{context.run_id}"
        first = runtime.request(
            "POST",
            "/discord/chat",
            json=_message(
                external_user_id=user,
                message_id=f"{context.marker}-continuity-1",
                text=f"Continuity marker is {context.marker}. Acknowledge this turn.",
                channel_id=channel,
                thread_id=thread,
            ),
        ).json()
        second = runtime.request(
            "POST",
            "/discord/chat",
            json=_message(
                external_user_id=user,
                message_id=f"{context.marker}-continuity-2",
                text="Continue this same conversation using the established session context.",
                channel_id=channel,
                thread_id=thread,
            ),
        ).json()
        second_turn = second.get("governed_turn") or {}
        handoffs = tuple(second_turn.get("handoffs") or ())
        artifacts = {
            str(item.get("artifact")): str(item.get("disposition"))
            for item in handoffs
            if item.get("artifact")
        }
        checks = [
            _check("First continuity turn released", first.get("state") == "RELEASED", "RELEASED", first.get("state")),
            _check("Second continuity turn released", second.get("state") == "RELEASED", "RELEASED", second.get("state")),
            _check("Both turns resolve to the same Discord session", first.get("session_id") == second.get("session_id") and bool(first.get("session_id")), first.get("session_id"), second.get("session_id")),
            _check(
                "Second turn consumes canonical session context",
                artifacts.get("memory.session_context") == "consumed",
                "consumed",
                artifacts.get("memory.session_context"),
            ),
            _check(
                "Sessioned turn does not consult legacy CAG",
                "memory.cag_compile" not in artifacts,
                "absent",
                artifacts.get("memory.cag_compile", "absent"),
            ),
        ]
        return CaseResult(
            checks=checks,
            evidence={
                "first": {"state": first.get("state"), "session_id": first.get("session_id")},
                "second": {"state": second.get("state"), "session_id": second.get("session_id")},
                "second_turn": second_turn,
            },
        )


class CrossUserIsolationCase:
    name = "discord-cross-user-isolation"
    suite = "USER ISOLATION"

    def run(self, runtime, database, context) -> CaseResult:
        del database
        primary = _primary_id()
        secondary = _secondary_id()
        if primary is None or secondary is None:
            return CaseResult(
                checks=[
                    _skip(
                        "Two linked users are isolated",
                        "primary and secondary protected Discord identities configured",
                        "secondary protected identity not configured",
                    )
                ]
            )
        secret_marker = f"PRIMARY_ONLY_{context.marker}"
        primary_reply = runtime.request(
            "POST",
            "/discord/chat",
            json=_message(
                external_user_id=primary,
                message_id=f"{context.marker}-isolation-primary",
                text=f"Private acceptance marker {secret_marker}.",
                channel_id="shared-acceptance-channel",
                thread_id="shared-acceptance-thread",
            ),
        ).json()
        secondary_reply = runtime.request(
            "POST",
            "/discord/chat",
            json=_message(
                external_user_id=secondary,
                message_id=f"{context.marker}-isolation-secondary",
                text="Respond using only this identity's authorized context.",
                channel_id="shared-acceptance-channel",
                thread_id="shared-acceptance-thread",
            ),
        ).json()
        checks = [
            _check("Primary user turn released", primary_reply.get("state") == "RELEASED", "RELEASED", primary_reply.get("state")),
            _check("Secondary user turn released", secondary_reply.get("state") == "RELEASED", "RELEASED", secondary_reply.get("state")),
            _check("Discord sessions are user-scoped even in the same channel/thread", primary_reply.get("session_id") != secondary_reply.get("session_id"), "different session ids", {"primary": primary_reply.get("session_id"), "secondary": secondary_reply.get("session_id")}),
            _check("Primary marker is absent from secondary response", secret_marker not in str(secondary_reply.get("text") or ""), "marker absent", "absent" if secret_marker not in str(secondary_reply.get("text") or "") else "present", heuristic=True),
        ]
        return CaseResult(checks=checks, evidence={"primary_session": primary_reply.get("session_id"), "secondary_session": secondary_reply.get("session_id")})


class ToolLoopCase:
    name = "governed-tool-loop"
    suite = "TOOLS EVIDENCE LOOP"

    def run(self, runtime, database, context) -> CaseResult:
        del database
        user = _primary_id()
        enabled = os.environ.get("NEXUS_RIG_EXPECT_TOOL_LOOP", "0") == "1"
        if user is None or not enabled:
            return CaseResult(
                checks=[
                    _skip(
                        "Provider → Tools → Evidence → Provider continuation",
                        "protected identity with explicit read-only tool grant and tool-capable provider",
                        "NEXUS_RIG_EXPECT_TOOL_LOOP is not enabled",
                    )
                ]
            )
        response = runtime.request(
            "POST",
            "/discord/chat",
            json=_message(
                external_user_id=user,
                message_id=f"{context.marker}-tool-loop",
                text="Use an available read-only calculation tool to compute 17 * 19, then answer with the verified result.",
                channel_id=f"acceptance-tools-{context.run_id}",
                thread_id=f"acceptance-tools-{context.run_id}",
            ),
        ).json()
        turn = response.get("governed_turn") or {}
        ids = tuple(turn.get("receipt_kernel_ids") or ())
        tool_receipt_count = sum(1 for value in ids if value == "nexus.tools")
        evidence_receipt_count = sum(1 for value in ids if value == "nexus.evidence")
        checks = [
            _check("Tool-loop turn released", response.get("state") == "RELEASED", "RELEASED", response.get("state")),
            _check("At least one governed tool execution receipt exists", tool_receipt_count >= 2, ">=2 tools receipts (visibility + execution)", tool_receipt_count),
            _check("Evidence re-authenticated tool output before release", evidence_receipt_count >= 2, ">=2 evidence receipts", evidence_receipt_count),
        ]
        return CaseResult(checks=checks, evidence={"governed_turn": turn})


class DeferredEdgesCase:
    name = "explicit-deferred-edges"
    suite = "DEFERRED INTEGRATION"

    def run(self, runtime, database, context) -> CaseResult:
        del runtime, database, context
        return CaseResult(
            checks=[
                _skip(
                    "Post-turn Learning admission is commissioned from released Discord turns",
                    "released turn → Learning evidence/review boundary",
                    "TEST REQUIRED / not part of current foreground coordinator",
                ),
                _skip(
                    "Cognition Senate handoff contributes to Context",
                    "Cognition advisory projection → Context handoff",
                    "TEST REQUIRED / currently background-degraded by design",
                ),
                _skip(
                    "Google Drive/GitHub private connectors run through kernelized Tools",
                    "accepted connector implementation on V5 assembly authority",
                    "DISCONNECTED: connector branch not yet transplanted onto accepted V5 line",
                ),
            ]
        )


def register_cases(_config: Any):
    return [
        KernelizedReadinessCase(),
        DiscordFirstContactCase(),
        DiscordGovernedTurnCase(),
        DiscordCommandsCase(),
        MultiTurnContinuityCase(),
        CrossUserIsolationCase(),
        ToolLoopCase(),
        DeferredEdgesCase(),
    ]
