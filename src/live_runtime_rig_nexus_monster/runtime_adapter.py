"""Surface-neutral monster acceptance adapter for kernelized Nexus Synapse.

Unlike the Discord surface adapter, this target enters the runtime through the
canonical /v1/chat/completions boundary exposed by NDKA. It never calls a
kernel specialist directly. The adapter records public-safe receipt metadata
from every turn so the campaign can prove which flight controls actually ran.
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
from pathlib import Path
from typing import Any, Mapping, Sequence

from fastapi import Request

from live_runtime_rig.config import RigConfig


REQUIRED_KERNEL_IDS = (
    "nexus.analysis",
    "nexus.artifacts",
    "nexus.cognition",
    "nexus.context",
    "nexus.continuity",
    "nexus.correction",
    "nexus.evidence",
    "nexus.identity",
    "nexus.jobs",
    "nexus.learning",
    "nexus.memory",
    "nexus.modes",
    "nexus.provider",
    "nexus.release",
    "nexus.security",
    "nexus.surfaces",
    "nexus.tools",
)


def _inventory_payload(inventory: Any) -> dict[str, tuple[str, ...]]:
    """Project NDKA's authoritative KernelInventoryView without inventing fields.

    NDKA names the live registry membership ``registered``. ``present`` remains
    only as a rig compatibility alias for older monster-case code; both are
    sourced from the same authoritative ``registered`` tuple.
    """

    registered = tuple(inventory.registered)
    return {
        "expected": tuple(inventory.expected),
        "registered": registered,
        "present": registered,
        "missing": tuple(inventory.missing),
        "unexpected": tuple(inventory.unexpected),
    }


class _InProcessASGIClient:
    """Tiny synchronous facade over HTTPX's supported ASGI transport.

    The monster image intentionally installs the exact accepted V2 dependency
    lock. That lock contains Starlette 0.35.1 and HTTPX 0.28.1. Starlette's
    TestClient from that generation still forwards ``app=`` into
    ``httpx.Client``, while HTTPX 0.28 removed that constructor argument.

    Do not mutate the accepted runtime dependency lock merely to make the rig's
    test harness happy. This client keeps the acceptance boundary at real ASGI
    HTTP semantics, stays fully in-process/no-network, and uses HTTPX's current
    supported ``ASGITransport`` API instead.
    """

    def __init__(self, app: Any) -> None:
        self._app = app
        self._closed = False

    async def _request_async(self, method: str, path: str, **kwargs: Any):
        import httpx

        transport = httpx.ASGITransport(app=self._app, raise_app_exceptions=True)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://nexus-rig.invalid",
        ) as client:
            return await client.request(method, path, **kwargs)

    def request(self, method: str, path: str, **kwargs: Any):
        if self._closed:
            raise RuntimeError("monster ASGI client is closed")
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise RuntimeError(
                "monster ASGI client synchronous facade cannot run inside an active event loop"
            )
        return asyncio.run(self._request_async(method, path, **kwargs))

    def post(self, path: str, **kwargs: Any):
        return self.request("POST", path, **kwargs)

    def close(self) -> None:
        self._closed = True


class KernelizedMonsterRuntimeAdapter:
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
        self.artifact_path = Path(
            os.environ.get("NEXUS_RIG_ARTIFACT_PATH", str(config.evidence_dir / "nexus-artifacts"))
        ).resolve()
        self.runtime_profile = os.environ.get("NEXUS_RIG_RUNTIME_PROFILE", "development_fixture")
        self.provider_kind = os.environ.get("NEXUS_RIG_PROVIDER_KIND", "fake")
        if self.provider_kind == "fake":
            raise RuntimeError(
                "REAL_PROVIDER_REQUIRED: the real-LLM Monster lane forbids the deterministic fake provider"
            )
        self.primary_user_id = int(os.environ.get("NEXUS_RIG_PRIMARY_USER_ID", "18"))
        self.secondary_user_id = int(os.environ.get("NEXUS_RIG_SECONDARY_USER_ID", "19"))
        self.primary_owner_key = os.environ.get("NEXUS_RIG_PRIMARY_OWNER_KEY", "fixture-owner-18")
        self.secondary_owner_key = os.environ.get("NEXUS_RIG_SECONDARY_OWNER_KEY", "fixture-owner-19")
        raw_permissions = os.environ.get(
            "NEXUS_RIG_MONSTER_PERMISSIONS",
            "tools:calculate,tools:read,artifacts:create,artifacts:read,jobs:create,jobs:read",
        )
        self.permissions = frozenset(
            value.strip() for value in raw_permissions.split(",") if value.strip()
        )
        self._assembled: Any | None = None
        self._app: Any | None = None
        self._client: Any | None = None
        self._coverage: dict[str, int] = {kernel_id: 0 for kernel_id in REQUIRED_KERNEL_IDS}
        self._operation_coverage: dict[str, dict[str, int]] = {
            kernel_id: {} for kernel_id in REQUIRED_KERNEL_IDS
        }
        self._turns: list[dict[str, Any]] = []

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

    def _principal(self, label: str):
        from nexus_ndka.host.runtime_ingress import RuntimePrincipal

        if label == "secondary":
            user_id = self.secondary_user_id
            owner_key = self.secondary_owner_key
        else:
            user_id = self.primary_user_id
            owner_key = self.primary_owner_key
        authenticated = label != "unauthenticated"
        return RuntimePrincipal(
            user_id=user_id,
            owner_key=owner_key,
            actor_id=str(user_id),
            scope_id=str(user_id),
            authenticated=authenticated,
            authority_reference_ids=(f"monster-authority:{label}:{user_id}",) if authenticated else (),
            permissions=self.permissions if authenticated else frozenset(),
            metadata={"acceptance_principal": label, "fixture": True},
        )

    def start(self) -> None:
        if self._assembled is not None:
            raise RuntimeError("monster runtime adapter already started")
        if not self.production_checkout.is_dir():
            raise FileNotFoundError(
                f"production donor source not found: {self.production_checkout}"
            )
        if self.v5_checkout is not None and not self.v5_checkout.is_dir():
            raise FileNotFoundError(f"V5 assembly source not found: {self.v5_checkout}")
        if not self.legacy_db.is_file():
            raise FileNotFoundError(f"legacy fixture database not found: {self.legacy_db}")

        self._configure_v5_environment()

        from fastapi import FastAPI
        from nexus_ndka.host.runtime_bootstrap import (
            KernelizedTestRuntimeConfig,
            build_kernelized_test_runtime,
        )
        from nexus_ndka.host.runtime_ingress import (
            CanonicalRuntimeIngress,
            build_fastapi_runtime_router,
        )

        # The monster lane owns disposable state, so all runtime write paths are
        # enabled. Source databases remain untouched because the launcher mounts
        # only isolated copies into /run/state.
        assembled = build_kernelized_test_runtime(
            KernelizedTestRuntimeConfig(
                production_checkout=self.production_checkout,
                legacy_state_db_path=self.legacy_db,
                v5_checkout=self.v5_checkout,
                allow_mode_lifecycle_writes=True,
                allow_legacy_memory_writes=True,
                allow_canonical_memory_writes=True,
            )
        )
        service = CanonicalRuntimeIngress(assembled.host.turn_runner)

        async def require_principal(request: Request):
            label = request.headers.get("X-Nexus-Rig-Principal", "primary")
            if label not in {"primary", "secondary", "unauthenticated"}:
                label = "primary"
            return self._principal(label)

        app = FastAPI()
        app.include_router(
            build_fastapi_runtime_router(service, require_principal=require_principal)
        )
        provider = getattr(assembled.v5_runtime, "provider", None)
        provider_class = type(provider).__name__ if provider is not None else ""
        provider_id = str(getattr(provider, "provider_id", "") or "")
        model_id = str(getattr(provider, "model_id", "") or "")
        if (
            not provider_class
            or "fake" in provider_class.casefold()
            or "fake" in provider_id.casefold()
            or "fake" in model_id.casefold()
        ):
            raise RuntimeError(
                "REAL_PROVIDER_REQUIRED: assembled runtime resolved a fake provider"
            )
        self._assembled = assembled
        self._app = app
        self._client = _InProcessASGIClient(app)

    def close(self) -> None:
        client = self._client
        if client is not None:
            close = getattr(client, "close", None)
            if callable(close):
                close()
        self._client = None
        self._app = None
        self._assembled = None

    def restart(self) -> None:
        self.close()
        self.start()

    def _require_started(self) -> tuple[Any, Any]:
        if self._assembled is None or self._client is None:
            raise RuntimeError("monster runtime adapter has not been started")
        return self._assembled, self._client

    @staticmethod
    def _public_receipts(payload: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
        raw = payload.get("receipts") or ()
        return tuple(item for item in raw if isinstance(item, Mapping))

    def _observe_payload(self, payload: Mapping[str, Any]) -> None:
        receipts = self._public_receipts(payload)
        for receipt in receipts:
            kernel_id = str(receipt.get("kernel_id") or "")
            operation = str(receipt.get("operation") or "")
            if kernel_id not in self._coverage:
                continue
            self._coverage[kernel_id] += 1
            if operation:
                bucket = self._operation_coverage[kernel_id]
                bucket[operation] = bucket.get(operation, 0) + 1
        self._turns.append(
            {
                "state": payload.get("state"),
                "request_id": payload.get("request_id"),
                "turn_id": payload.get("turn_id"),
                "session_id": payload.get("session_id"),
                "blocking_reason": payload.get("blocking_reason"),
                "receipt_kernel_ids": tuple(
                    str(item.get("kernel_id")) for item in receipts if item.get("kernel_id")
                ),
            }
        )

    def chat(
        self,
        text: str,
        *,
        session_id: str,
        principal: str = "primary",
        include_tools: bool = True,
        extra: Mapping[str, Any] | None = None,
    ):
        _, client = self._require_started()
        body: dict[str, Any] = {
            "messages": [{"role": "user", "content": text}],
            "session_id": session_id,
            "include_tools": include_tools,
        }
        body.update(dict(extra or {}))
        response = client.post(
            "/v1/chat/completions",
            headers={"X-Nexus-Rig-Principal": principal},
            json=body,
        )
        try:
            payload = response.json()
        except Exception:
            payload = {}
        if isinstance(payload, Mapping):
            self._observe_payload(payload)
        return response

    def health(self) -> Mapping[str, Any]:
        assembled, _ = self._require_started()
        readiness = asyncio.run(assembled.host.test_readiness())
        inventory = assembled.host.observability.inventory()
        provider = getattr(assembled.v5_runtime, "provider", None)
        return {
            "ready_for_test": readiness.ready_for_test,
            **_inventory_payload(inventory),
            "degraded_kernel_ids": tuple(readiness.degraded_kernel_ids),
            "failed_kernel_ids": tuple(readiness.failed_kernel_ids),
            "primary_user_id": self.primary_user_id,
            "primary_owner_key": self.primary_owner_key,
            "provider_kind": self.provider_kind,
            "provider_class": type(provider).__name__ if provider is not None else None,
            "provider_id": getattr(provider, "provider_id", None),
            "model_id": getattr(provider, "model_id", None),
            "real_provider": (
                provider is not None
                and "fake" not in type(provider).__name__.casefold()
                and "fake" not in str(getattr(provider, "provider_id", "")).casefold()
                and "fake" not in str(getattr(provider, "model_id", "")).casefold()
            ),
        }

    def direct_readiness_probe(self) -> Mapping[str, Any]:
        return dict(self.health())

    def coverage(self) -> Mapping[str, Any]:
        missing = tuple(kernel_id for kernel_id in REQUIRED_KERNEL_IDS if self._coverage[kernel_id] == 0)
        return {
            "required_kernel_ids": REQUIRED_KERNEL_IDS,
            "receipt_counts": dict(self._coverage),
            "operation_counts": {
                kernel_id: dict(sorted(values.items()))
                for kernel_id, values in self._operation_coverage.items()
            },
            "missing_kernel_receipts": missing,
            "turn_count": len(self._turns),
            "turns": tuple(self._turns),
        }

    def request(self, method: str, path: str, **kwargs: Any):
        assembled, client = self._require_started()
        normalized = method.upper()
        if normalized == "GET" and path in {"/health", "/readiness"}:
            body = dict(self.health())
            status = 200 if body["ready_for_test"] else 503
            return _MappingResponse(status, body)
        if normalized == "GET" and path == "/kernel-inventory":
            inventory = assembled.host.observability.inventory()
            return _MappingResponse(200, _inventory_payload(inventory))
        if normalized == "GET" and path == "/coverage":
            return _MappingResponse(200, dict(self.coverage()))
        if normalized == "POST" and path == "/__rig/restart":
            self.restart()
            return _MappingResponse(200, {"restarted": True})
        if normalized == "POST" and path == "/v1/chat/completions":
            payload = kwargs.get("json") or {}
            principal = str(kwargs.get("principal") or "primary")
            response = client.post(
                path,
                headers={"X-Nexus-Rig-Principal": principal},
                json=payload,
            )
            try:
                body = response.json()
            except Exception:
                body = {}
            if isinstance(body, Mapping):
                self._observe_payload(body)
            return response
        raise ValueError(f"unsupported monster acceptance route: {method} {path}")

    def list_capabilities(self) -> Sequence[str]:
        return (
            "canonical-v1-chat-completions",
            "authoritative-17-kernel-inventory",
            "receipt-coverage-matrix",
            "runtime-initiated-tool-loop",
            "continuity-and-restart",
            "cross-user-isolation",
            "negative-security-path",
            "all-required-flight-controls",
        )


class _MappingResponse:
    def __init__(self, status_code: int, body: Mapping[str, Any]) -> None:
        self.status_code = status_code
        self._body = body

    def json(self) -> Mapping[str, Any]:
        return self._body


def create_runtime_adapter(config: RigConfig) -> KernelizedMonsterRuntimeAdapter:
    return KernelizedMonsterRuntimeAdapter(config)
