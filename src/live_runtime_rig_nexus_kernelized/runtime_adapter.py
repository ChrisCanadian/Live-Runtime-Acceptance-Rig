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
import sqlite3
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


class _RecordingTurnRunner:
    """Transparent recorder around the real governed coordinator."""

    def __init__(self, delegate: Any) -> None:
        self.delegate = delegate
        self.last_bundle: Any | None = None

    async def run(self, request: Any, context: Any) -> Any:
        bundle = await self.delegate.run(request, context)
        self.last_bundle = bundle
        return bundle


class _CanonicalIdentityOwnerResolver:
    """Resolve owner authority from V5 state, with explicit fixture fallback only."""

    def __init__(self, v5_runtime: Any, fixture_owners: Mapping[str, str]) -> None:
        self._v5 = v5_runtime
        self._fixture_owners = dict(fixture_owners)

    async def resolve_owner_key(self, *, user_id: int, external_scope_id: str) -> str:
        del external_scope_id
        rows: list[Any] = []
        try:
            with self._v5.database.read() as connection:
                rows = connection.execute(
                    """
                    SELECT DISTINCT owner_key
                    FROM canonical_principal_mappings
                    WHERE nexus_user_id = ? AND status IN ('OWNER_APPROVED','ACTIVE')
                    ORDER BY owner_key
                    """,
                    (str(user_id),),
                ).fetchall()
        except sqlite3.OperationalError:
            rows = []
        owners = tuple(str(row["owner_key"]) for row in rows)
        if len(owners) == 1:
            return owners[0]
        if len(owners) > 1:
            raise PermissionError("AMBIGUOUS_CANONICAL_IDENTITY_OWNER")
        return self._fixture_owners.get(str(user_id), "")


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
        self.legacy_db = Path(os.environ["NEXUS_RIG_LEGACY_DB_PATH"]).resolve()
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
        raw_owners = os.environ.get("NEXUS_RIG_IDENTITY_OWNERS_JSON", "{}")
        parsed = json.loads(raw_owners)
        if not isinstance(parsed, dict):
            raise ValueError("NEXUS_RIG_IDENTITY_OWNERS_JSON must be an object")
        self.fixture_owners = {str(key): str(value) for key, value in parsed.items()}
        self._assembled: Any | None = None
        self._discord: Any | None = None
        self._recorder: _RecordingTurnRunner | None = None

    def _configure_v5_environment(self) -> None:
        self.artifact_path.mkdir(parents=True, exist_ok=True)
        os.environ["NEXUS_DB_PATH"] = str(self.config.database_path)
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

    @staticmethod
    def _legacy_connection_factory(path: Path):
        def factory() -> sqlite3.Connection:
            return sqlite3.connect(path)

        return factory

    def start(self) -> None:
        if self._assembled is not None:
            raise RuntimeError("kernelized Nexus runtime adapter already started")
        if not self.production_checkout.is_dir():
            raise FileNotFoundError(
                f"production donor source not found: {self.production_checkout}"
            )
        if self.v5_checkout is not None and not self.v5_checkout.is_dir():
            raise FileNotFoundError(f"V5 assembly source not found: {self.v5_checkout}")
        if self.v5_checkout is None and self.v5_source_authority is not None:
            raise ValueError(
                "staged V5 mode cannot use NEXUS_RIG_V5_SOURCE_AUTHORITY"
            )
        if self.production_source_manifest is not None and not self.production_source_manifest.is_file():
            raise FileNotFoundError(
                f"production source manifest not found: {self.production_source_manifest}"
            )
        if self.v5_source_authority is not None and not self.v5_source_authority.is_file():
            raise FileNotFoundError(
                f"V5 source authority record not found: {self.v5_source_authority}"
            )
        if not self.legacy_db.is_file():
            raise FileNotFoundError(f"legacy TEST database not found: {self.legacy_db}")

        self._configure_v5_environment()

        from nexus_ndka.host.bootstrap import build_discord_host_adapter
        from nexus_ndka.host.runtime_bootstrap import (
            KernelizedTestRuntimeConfig,
            build_kernelized_test_runtime,
        )

        assembled = build_kernelized_test_runtime(
            KernelizedTestRuntimeConfig(
                production_checkout=self.production_checkout,
                legacy_state_db_path=self.legacy_db,
                v5_checkout=self.v5_checkout,
                production_source_manifest_path=self.production_source_manifest,
                v5_source_authority_path=self.v5_source_authority,
                allow_mode_lifecycle_writes=True,
                allow_legacy_memory_writes=False,
                allow_canonical_memory_writes=False,
            )
        )
        owner_resolver = _CanonicalIdentityOwnerResolver(
            assembled.v5_runtime, self.fixture_owners
        )
        discord = build_discord_host_adapter(
            assembled.host.registry,
            connection_factory=self._legacy_connection_factory(self.legacy_db),
            identity_owner_resolver=owner_resolver,
            user_tz_name=self.user_tz_name,
        )
        recorder = _RecordingTurnRunner(assembled.host.turn_runner)
        discord.turn_runner = recorder
        self._assembled = assembled
        self._discord = discord
        self._recorder = recorder

    def close(self) -> None:
        self._discord = None
        self._recorder = None
        self._assembled = None

    def _require_started(self) -> tuple[Any, Any, _RecordingTurnRunner]:
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
            "discord-guest-bare-inference",
            "discord-mode-command",
            "discord-model-read-only",
            "discord-tools-read-only-catalog",
            "governed-receipt-chain",
            "cag-context-observation",
            "multi-user-scope",
        )


def create_runtime_adapter(config: RigConfig) -> KernelizedNexusRuntimeAdapter:
    return KernelizedNexusRuntimeAdapter(config)
