"""In-process acceptance adapter for the assembled kernelized Nexus TEST host.

This adapter does not construct individual kernels. It invokes the NDKA-supported
whole-runtime bootstrap, attaches the real transport-neutral Discord host to the
resulting authoritative registry, and records only public-safe receipt metadata
from completed governed turns.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from live_runtime_rig.config import RigConfig


@dataclass(frozen=True)
class AdapterResponse:
    status_code: int
    body: Mapping[str, Any]

    def json(self) -> Mapping[str, Any]:
        return self.body


class _RecordingRuntimeIngress:
    """Transparent recorder around the canonical surface-neutral ingress."""

    def __init__(self, delegate: Any) -> None:
        self.delegate = delegate
        self.last_bundle: Any | None = None

    async def run_chat(self, *args: Any, **kwargs: Any) -> Any:
        result = await self.delegate.run_chat(*args, **kwargs)
        self.last_bundle = getattr(result, "bundle", None)
        return result


class KernelizedNexusRuntimeAdapter:
    def __init__(self, config: RigConfig) -> None:
        self.config = config
        self.production_checkout = Path(os.environ["NEXUS_RIG_PRODUCTION_CHECKOUT"]).resolve()
        raw_v5_checkout = os.environ.get("NEXUS_RIG_V5_CHECKOUT", "").strip()
        self.v5_checkout = (
            None
            if not raw_v5_checkout or raw_v5_checkout.upper() == "STAGED"
            else Path(raw_v5_checkout).resolve()
        )
        self.v5_expected_sha = os.environ.get("NEXUS_RIG_V5_EXPECTED_SHA", "").strip() or None
        self.canonical_db = Path(config.database_path).resolve()
        production_manifest = os.environ.get("NEXUS_RIG_PRODUCTION_SOURCE_MANIFEST")
        v5_authority = os.environ.get("NEXUS_RIG_V5_SOURCE_AUTHORITY")
        self.production_source_manifest = (
            Path(production_manifest).resolve() if production_manifest else None
        )
        self.v5_source_authority = Path(v5_authority).resolve() if v5_authority else None
        self.artifact_path = Path(
            os.environ.get(
                "NEXUS_RIG_ARTIFACT_PATH",
                str(config.evidence_dir / "nexus-artifacts"),
            )
        ).resolve()
        self.runtime_profile = os.environ.get(
            "NEXUS_RIG_RUNTIME_PROFILE", "development_fixture"
        )
        self.provider_kind = os.environ.get("NEXUS_RIG_PROVIDER_KIND", "fake")
        self.user_tz_name = os.environ.get("NEXUS_RIG_USER_TZ", "America/Toronto")
        self._assembled: Any | None = None
        self._discord: Any | None = None
        self._recorder: _RecordingRuntimeIngress | None = None

    def _configure_v5_environment(self) -> None:
        self.artifact_path.mkdir(parents=True, exist_ok=True)
        os.environ["NEXUS_DB_PATH"] = str(self.canonical_db)
        if self.v5_checkout is not None:
            migrations = self.v5_checkout / "migrations"
            if not migrations.is_dir():
                raise FileNotFoundError(f"V5 migrations directory not found: {migrations}")
            os.environ["NEXUS_MIGRATIONS_PATH"] = str(migrations)
        else:
            os.environ.pop("NEXUS_MIGRATIONS_PATH", None)
        os.environ["NEXUS_ARTIFACT_PATH"] = str(self.artifact_path)
        os.environ["NEXUS_RUNTIME_PROFILE"] = self.runtime_profile
        os.environ["NEXUS_PROVIDER_KIND"] = self.provider_kind
        os.environ.setdefault("NEXUS_V2_PRODUCT_MODE", "structural_fixture")

    def start(self) -> None:
        if self._assembled is not None:
            raise RuntimeError("kernelized Nexus runtime adapter already started")
        if not self.production_checkout.is_dir():
            raise FileNotFoundError(
                f"production donor source not found: {self.production_checkout}"
            )
        if self.v5_checkout is not None and not self.v5_checkout.is_dir():
            raise FileNotFoundError(f"V5 assembly source not found: {self.v5_checkout}")
        if self.production_source_manifest is not None and not self.production_source_manifest.is_file():
            raise FileNotFoundError(
                f"production source manifest not found: {self.production_source_manifest}"
            )
        if self.v5_source_authority is not None and not self.v5_source_authority.is_file():
            raise FileNotFoundError(
                f"V5 source authority record not found: {self.v5_source_authority}"
            )
        if not self.canonical_db.is_file():
            raise FileNotFoundError(
                f"canonical TEST database not found: {self.canonical_db}"
            )

        self._configure_v5_environment()

        from nexus_ndka.host.kernelized_compat import KernelizedV5CompatibilityRuntime
        from nexus_ndka.host.runtime_bootstrap import (
            KernelizedTestRuntimeConfig,
            build_kernelized_test_runtime,
        )

        assembled = build_kernelized_test_runtime(
            KernelizedTestRuntimeConfig(
                production_checkout=self.production_checkout,
                legacy_state_db_path=self.canonical_db,
                v5_checkout=self.v5_checkout,
                v5_expected_sha=self.v5_expected_sha,
                production_source_manifest_path=self.production_source_manifest,
                v5_source_authority_path=self.v5_source_authority,
                allow_mode_lifecycle_writes=True,
                allow_legacy_memory_writes=False,
                allow_canonical_memory_writes=True,
            )
        )
        compatibility = KernelizedV5CompatibilityRuntime(assembled)
        discord = compatibility.discord_adapter
        discord.user_tz_name = self.user_tz_name
        recorder = _RecordingRuntimeIngress(assembled.host.runtime_ingress)
        discord.runtime_ingress = recorder
        self._assembled = assembled
        self._discord = discord
        self._recorder = recorder

    def close(self) -> None:
        self._discord = None
        self._recorder = None
        self._assembled = None

    def _require_started(self) -> tuple[Any, Any, _RecordingRuntimeIngress]:
        if self._assembled is None or self._discord is None or self._recorder is None:
            raise RuntimeError("kernelized Nexus runtime adapter has not been started")
        return self._assembled, self._discord, self._recorder

    @staticmethod
    def _bundle_evidence(bundle: Any | None) -> Mapping[str, Any]:
        if bundle is None:
            return {"available": False}
        receipts = []
        for receipt in tuple(getattr(bundle, "receipts", ()) or ()):
            status = getattr(getattr(receipt, "status", None), "value", None)
            receipts.append(
                {
                    "kernel_id": getattr(receipt, "kernel_id", None),
                    "operation": getattr(receipt, "operation", None),
                    "status": status,
                    "output_hash": getattr(receipt, "output_hash", None),
                }
            )
        inference = getattr(bundle, "inference", None)
        provider = getattr(getattr(inference, "provider", None), "envelope", None)
        pre = getattr(inference, "pre_inference", None)
        context_result = getattr(pre, "context", None)
        context_envelope = getattr(context_result, "envelope", None)
        sections = tuple(getattr(context_envelope, "sections", ()) or ())
        section_ids = tuple(
            str(getattr(section, "section_id", ""))
            for section in sections
            if getattr(section, "section_id", None)
        )
        state = getattr(getattr(bundle, "state", None), "value", None)
        return {
            "available": True,
            "state": state,
            "receipt_chain": tuple(receipts),
            "receipt_kernel_ids": tuple(
                item["kernel_id"] for item in receipts if item["kernel_id"]
            ),
            "context_section_ids": section_ids,
            "cag_section_present": "memory.cag" in section_ids,
            "visible_tool_count": len(tuple(getattr(inference, "visible_tools", ()) or ())),
            "provider_id": getattr(provider, "provider_id", None),
            "model_id": getattr(provider, "model_id", None),
            "route_id": getattr(provider, "route_id", None),
            "blocking_reason": getattr(bundle, "blocking_reason", None),
        }

    def health(self) -> Mapping[str, Any]:
        assembled, _, _ = self._require_started()
        host_ready = asyncio.run(assembled.host.test_readiness())
        foreground = asyncio.run(assembled.discord_foreground_readiness())
        inventory = assembled.host.observability.inventory()
        return {
            "ready": host_ready.ready_for_test and foreground.ready,
            "host_ready_for_test": host_ready.ready_for_test,
            "discord_foreground_ready": foreground.ready,
            "expected_kernel_count": len(tuple(inventory.expected)),
            "present_kernel_count": len(tuple(inventory.present)),
            "missing_kernel_ids": tuple(inventory.missing),
            "unexpected_kernel_ids": tuple(inventory.unexpected),
            "degraded_kernel_ids": tuple(host_ready.degraded_kernel_ids),
            "failed_kernel_ids": tuple(host_ready.failed_kernel_ids),
            "foreground_missing_operations": dict(foreground.missing_operations),
        }

    def direct_readiness_probe(self) -> Mapping[str, Any]:
        return dict(self.health())

    @staticmethod
    def _message(payload: Mapping[str, Any]) -> Any:
        from nexus_ndka.host.discord import DiscordInboundMessage

        return DiscordInboundMessage(
            external_user_id=str(payload["external_user_id"]),
            channel_id=str(payload.get("channel_id", "acceptance-channel")),
            message_id=str(payload["message_id"]),
            text=str(payload.get("text", "")),
            guild_id=(str(payload["guild_id"]) if payload.get("guild_id") else None),
            thread_id=(str(payload["thread_id"]) if payload.get("thread_id") else None),
            attachments=tuple(str(value) for value in payload.get("attachments", ())),
        )

    @staticmethod
    def _reply_body(reply: Any) -> dict[str, Any]:
        value = asdict(reply)
        value["metadata"] = dict(value.get("metadata") or {})
        return value

    def request(self, method: str, path: str, **kwargs: Any) -> AdapterResponse:
        assembled, discord, recorder = self._require_started()
        normalized_method = method.upper()
        if normalized_method == "GET" and path in {"/health", "/readiness"}:
            body = dict(self.health())
            return AdapterResponse(200 if body["ready"] else 503, body)
        if normalized_method == "GET" and path == "/last-turn":
            return AdapterResponse(200, dict(self._bundle_evidence(recorder.last_bundle)))

        payload = kwargs.get("json") or {}
        if not isinstance(payload, Mapping):
            raise TypeError("Nexus acceptance requests require a JSON object")
        message = self._message(payload)

        if normalized_method == "POST" and path == "/discord/chat":
            recorder.last_bundle = None
            reply = asyncio.run(discord.handle_chat(message))
            body = self._reply_body(reply)
            body["governed_turn"] = dict(self._bundle_evidence(recorder.last_bundle))
            status = 200
            if reply.state == "DENIED":
                status = 403
            elif reply.state in {"BLOCKED", "GUEST_RUNTIME_NOT_WIRED"}:
                status = 409
            return AdapterResponse(status, body)

        if normalized_method == "POST" and path == "/discord/command":
            command = str(payload.get("command", ""))
            arguments = tuple(str(value) for value in payload.get("arguments", ()))
            reply = asyncio.run(
                discord.handle_command(message, command=command, arguments=arguments)
            )
            body = self._reply_body(reply)
            return AdapterResponse(403 if reply.state == "DENIED" else 200, body)

        if normalized_method == "GET" and path == "/kernel-inventory":
            inventory = assembled.host.observability.inventory()
            return AdapterResponse(
                200,
                {
                    "expected": tuple(inventory.expected),
                    "present": tuple(inventory.present),
                    "missing": tuple(inventory.missing),
                    "unexpected": tuple(inventory.unexpected),
                },
            )

        raise ValueError(f"unsupported kernelized Nexus acceptance route: {method} {path}")

    def list_capabilities(self) -> Sequence[str]:
        return (
            "authoritative-17-kernel-readiness",
            "discord-linked-governed-turn",
            "discord-guest-fail-closed",
            "discord-mode-command",
            "discord-model-read-only",
            "discord-tools-read-only-catalog",
            "governed-receipt-chain",
            "canonical-session-context-observation",
            "multi-user-scope",
        )


def create_runtime_adapter(config: RigConfig) -> KernelizedNexusRuntimeAdapter:
    return KernelizedNexusRuntimeAdapter(config)
