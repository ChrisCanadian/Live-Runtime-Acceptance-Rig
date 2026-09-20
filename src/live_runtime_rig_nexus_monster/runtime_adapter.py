"""Surface-neutral monster acceptance adapter for kernelized Nexus Synapse.

Unlike the Discord surface adapter, this target enters ordinary turns through
the canonical /v1/chat/completions boundary exposed by NDKA. Dedicated
department-boundary acceptance probes may call a registered public kernel
manager, but never a specialist or donor implementation directly. The adapter
records public-safe receipt metadata with the evidence source so the campaign
can distinguish canonical-turn participation from bounded manager exercise.
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

from fastapi import Request

from live_runtime_rig.config import RigConfig
from live_runtime_rig_nexus_monster.takt import TaktRecorder, timed_method


def _configure_operator_console_noise() -> None:
    """Suppress third-party progress bars without muting Nexus initialization."""

    # Model materialization progress is useful when debugging Transformers
    # itself, but it overwhelms acceptance output and is not acceptance evidence.
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    os.environ.setdefault("TQDM_DISABLE", "1")

    try:
        from transformers.utils import logging as transformers_logging

        transformers_logging.disable_progress_bar()
        transformers_logging.set_verbosity_error()
    except Exception:
        pass

    try:
        from huggingface_hub.utils import disable_progress_bars

        disable_progress_bars()
    except Exception:
        pass


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

    @timed_method("runtime.request.total")
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
            "tools:document,artifacts:create,artifacts:read,jobs:create,jobs:read",
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
        self._coverage_sources: dict[str, dict[str, int]] = {
            kernel_id: {"canonical_turn": 0, "boundary_probe": 0}
            for kernel_id in REQUIRED_KERNEL_IDS
        }
        self._turns: list[dict[str, Any]] = []
        self._boundary_events: list[dict[str, Any]] = []
        self._provider_probe: dict[str, Any] = {}
        self._rag_probe: dict[str, Any] = {}
        self._analysis_probe: dict[str, Any] = {}
        self._takt = TaktRecorder()

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

    def _run_real_provider_probe(self, assembled: Any) -> dict[str, Any]:
        from nexus_ndka.kernels.provider.contracts import (
            InferenceRole,
            ProviderOperation,
            ProviderRequest,
        )
        from nexus_ndka.runtime.contracts import KernelStatus, RuntimeContext

        manager = assembled.host.registry.get("nexus.provider")
        context = RuntimeContext(
            request_id="monster-provider-preflight",
            turn_id="monster-provider-preflight",
            actor_id=str(self.primary_user_id),
            scope_id=str(self.primary_user_id),
            session_id="monster-provider-preflight",
            metadata={"acceptance_preflight": True},
        )

        async def execute_probe():
            return await manager.execute(
                ProviderRequest(
                    operation=ProviderOperation.GENERATE,
                    system_prompt=(
                        "You are a transport preflight. Return one brief acknowledgment. "
                        "Do not call tools."
                    ),
                    user_prompt="Reply with a brief acknowledgment.",
                    role=InferenceRole.PRIMARY_RESPONSE,
                    required_capabilities=frozenset({"TEXT"}),
                    available_tools=(),
                ),
                context,
            )

        result = asyncio.run(execute_probe())
        if result.receipt.status is not KernelStatus.OK:
            raise RuntimeError(
                "REAL_PROVIDER_PREFLIGHT_FAILED: "
                + str(result.envelope.diagnostics or result.receipt.details)
            )
        if not str(result.envelope.text or "").strip():
            raise RuntimeError("REAL_PROVIDER_PREFLIGHT_FAILED: empty model response")
        return {
            "status": result.receipt.status.value,
            "provider_id": result.envelope.provider_id,
            "model_id": result.envelope.model_id,
            "response_chars": len(result.envelope.text),
            "route_failures": tuple(result.envelope.route_failures),
        }

    def _run_production_analysis_probe(self, assembled: Any) -> dict[str, Any]:
        from nexus_ndka.kernels.analysis.contracts import AnalysisRequest
        from nexus_ndka.runtime.contracts import KernelStatus, RuntimeContext

        manager = assembled.host.registry.get("nexus.analysis")
        context = RuntimeContext(
            request_id="monster-analysis-preflight",
            turn_id="monster-analysis-preflight",
            actor_id=str(self.primary_user_id),
            scope_id=str(self.primary_user_id),
            session_id="monster-analysis-preflight",
            metadata={"acceptance_preflight": True},
        )

        result = asyncio.run(
            manager.execute(
                AnalysisRequest(
                    user_text=(
                        "I am frustrated that this acceptance test keeps failing, "
                        "but I am curious and determined to fix it."
                    )
                ),
                context,
            )
        )
        if result.receipt.status is not KernelStatus.OK:
            raise RuntimeError(
                "ANALYSIS_PREFLIGHT_FAILED: "
                + str(result.receipt.details or result.receipt.status.value)
            )

        signals = dict(result.state.signals or {})
        donor_analysis = dict(signals.get("donor_analysis") or {})
        intent_data = dict(donor_analysis.get("intent_data") or {})
        latency = dict(donor_analysis.get("latency_breakdown") or {})
        raw_source = str(signals.get("donor_source") or "")
        all_intents = dict(signals.get("all_intents") or {})
        scores = [
            float(value)
            for value in all_intents.values()
            if isinstance(value, (int, float))
        ]
        score_spread = (max(scores) - min(scores)) if scores else 0.0
        sentence_count = int(intent_data.get("sentence_count") or 0)

        # The full local ProductionNLPPipeline returns SentenceLevelAnnotator's
        # intent_data + latency_breakdown shape. The low-memory VM HTTP fallback
        # and the static last-resort path do not. The Monster deliberately tests
        # this full pipeline locally while APIFree.ai remains the response-model
        # inference provider.
        full_local_pipeline = (
            raw_source != "hf_api_lightweight"
            and sentence_count > 0
            and bool(latency)
            and bool(all_intents)
            and score_spread > 1e-6
        )
        if not full_local_pipeline:
            raise RuntimeError(
                "ANALYSIS_PREFLIGHT_FAILED: full local production NLP pipeline "
                "did not execute; lightweight/static analysis is forbidden in "
                "the local Monster lane "
                f"(source={raw_source!r}, sentence_count={sentence_count}, "
                f"latency_keys={tuple(sorted(latency))})"
            )

        return {
            "status": result.receipt.status.value,
            "source": "production_full_nlp_local",
            "donor_source": raw_source,
            "intent": result.state.intent,
            "intent_confidence": result.state.intent_confidence,
            "emotion": result.state.emotion,
            "mood": result.state.mood,
            "topic": result.state.topic,
            "sentence_count": sentence_count,
            "latency_components": tuple(sorted(latency)),
            "latency_breakdown": {
                key: value
                for key, value in latency.items()
                if isinstance(value, (int, float))
            },
            "intent_label_count": len(all_intents),
            "intent_score_spread": score_spread,
            "static_defaults": False,
            "hf_inference_api_used": False,
        }

    def _run_production_rag_probe(self) -> dict[str, Any]:
        import sys

        module = sys.modules.get("memory.memory_manager")
        if module is None:
            raise RuntimeError(
                "RAG_PREFLIGHT_FAILED: production memory.memory_manager donor is not loaded"
            )
        manager = module.MemoryManager(
            user_id=self.primary_user_id,
            session_id="monster-rag-preflight",
        )
        retriever = getattr(manager, "rag_retriever", None)
        if retriever is None:
            raise RuntimeError(
                "RAG_PREFLIGHT_FAILED: production RAGRetriever did not initialize"
            )
        embedding_manager = getattr(retriever, "embedding_manager", None)
        vector_store = getattr(retriever, "vector_store", None)
        if embedding_manager is None or vector_store is None:
            raise RuntimeError(
                "RAG_PREFLIGHT_FAILED: retriever is missing embedding/vector dependencies"
            )

        embedding = embedding_manager.generate_embedding("Nexus RAG acceptance preflight")
        if not embedding:
            raise RuntimeError(
                "RAG_PREFLIGHT_FAILED: nomic-embed-text returned no embedding"
            )
        collection = vector_store.get_or_create_collection("conversations")
        if collection is None:
            raise RuntimeError(
                "RAG_PREFLIGHT_FAILED: Chroma conversations collection is unavailable"
            )
        semantic = vector_store.search_conversations(
            user_id=self.primary_user_id,
            query_embedding=embedding,
            n_results=3,
        )
        return {
            "rag_initialized": True,
            "embedding_dimensions": len(embedding),
            "conversation_vectors": int(collection.count()),
            "user18_semantic_matches": len(semantic),
            "embedding_url": str(getattr(embedding_manager, "ollama_url", "")),
        }

    def start(self) -> None:
        start_total_started = time.perf_counter_ns()
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
        _configure_operator_console_noise()

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
        bootstrap_started = time.perf_counter_ns()
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
        self._takt.record(
            "runtime.bootstrap.build_kernelized_test_runtime",
            (time.perf_counter_ns() - bootstrap_started) / 1_000_000,
            boundary="nexus",
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

        provider_started = time.perf_counter_ns()
        self._provider_probe = self._run_real_provider_probe(assembled)
        self._takt.record(
            "runtime.preflight.provider",
            (time.perf_counter_ns() - provider_started) / 1_000_000,
            boundary="nexus",
        )
        analysis_started = time.perf_counter_ns()
        self._analysis_probe = self._run_production_analysis_probe(assembled)
        self._takt.record(
            "runtime.preflight.analysis",
            (time.perf_counter_ns() - analysis_started) / 1_000_000,
            boundary="nexus",
        )
        rag_started = time.perf_counter_ns()
        self._rag_probe = self._run_production_rag_probe()
        self._takt.record(
            "runtime.preflight.rag",
            (time.perf_counter_ns() - rag_started) / 1_000_000,
            boundary="nexus",
        )

        self._assembled = assembled
        self._app = app
        self._client = _InProcessASGIClient(app)
        self._takt.record(
            "runtime.start.total",
            (time.perf_counter_ns() - start_total_started) / 1_000_000,
            boundary="nexus",
        )

    def close(self) -> None:
        self._takt.write(self.artifact_path)
        client = self._client
        if client is not None:
            close = getattr(client, "close", None)
            if callable(close):
                close()
        self._client = None
        self._app = None
        self._assembled = None
        self._provider_probe = {}
        self._rag_probe = {}
        self._analysis_probe = {}

    @timed_method("runtime.restart.total")
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

    def _record_coverage(
        self,
        *,
        kernel_id: str,
        operation: str,
        source: str,
    ) -> None:
        if kernel_id not in self._coverage:
            return
        self._coverage[kernel_id] += 1
        if operation:
            bucket = self._operation_coverage[kernel_id]
            bucket[operation] = bucket.get(operation, 0) + 1
        sources = self._coverage_sources[kernel_id]
        sources[source] = sources.get(source, 0) + 1

    def _record_receipt_takt(
        self,
        receipt: Any,
        *,
        label: str | None = None,
        source: str = "kernel_receipt",
    ) -> None:
        if isinstance(receipt, Mapping):
            kernel_id = str(receipt.get("kernel_id") or "")
            operation = str(receipt.get("operation") or "")
            duration = receipt.get("duration_ms")
            status = receipt.get("status")
        else:
            kernel_id = str(getattr(receipt, "kernel_id", "") or "")
            operation = str(getattr(receipt, "operation", "") or "")
            duration = getattr(receipt, "duration_ms", None)
            raw_status = getattr(receipt, "status", None)
            status = getattr(raw_status, "value", None) or str(raw_status or "")
        if not isinstance(duration, (int, float)):
            return
        name = label or ".".join(value for value in (kernel_id, operation) if value)
        if not name:
            name = "kernel.receipt"
        self._takt.record(
            name,
            float(duration),
            source=source,
            boundary="nexus",
            metadata={
                "kernel_id": kernel_id,
                "operation": operation,
                "status": status,
            },
        )

    def _observe_payload(self, payload: Mapping[str, Any]) -> None:
        receipts = self._public_receipts(payload)
        for receipt in receipts:
            self._record_receipt_takt(receipt)
            self._record_coverage(
                kernel_id=str(receipt.get("kernel_id") or ""),
                operation=str(receipt.get("operation") or ""),
                source="canonical_turn",
            )
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

    def _observe_boundary_result(self, result: Any, *, label: str) -> None:
        receipt = getattr(result, "receipt", None)
        if receipt is None:
            raise RuntimeError(f"{label} returned no KernelReceipt")
        kernel_id = str(getattr(receipt, "kernel_id", "") or "")
        operation = str(getattr(receipt, "operation", "") or "")
        status = getattr(getattr(receipt, "status", None), "value", None) or str(
            getattr(receipt, "status", "")
        )
        self._record_receipt_takt(
            receipt,
            label=f"{kernel_id}.{operation}.boundary",
        )
        self._record_coverage(
            kernel_id=kernel_id,
            operation=operation,
            source="boundary_probe",
        )
        self._boundary_events.append(
            {
                "label": label,
                "kernel_id": kernel_id,
                "operation": operation,
                "status": status,
                "state_mutated": bool(getattr(receipt, "state_mutated", False)),
            }
        )

    def _boundary_context(self, *, label: str):
        from nexus_ndka.runtime.contracts import RuntimeContext

        return RuntimeContext(
            request_id=f"monster-boundary:{label}",
            turn_id=f"monster-boundary:{label}",
            actor_id=str(self.primary_user_id),
            scope_id=str(self.primary_user_id),
            session_id=f"monster-boundary:{label}",
            metadata={
                "acceptance_boundary_probe": True,
                "owner_key": self.primary_owner_key,
                "trusted_permissions": tuple(sorted(self.permissions)),
            },
        )

    @timed_method("runtime.seed_tool_loop_memory")
    def seed_tool_loop_memory(
        self,
        *,
        lookup_token: str,
        hidden_value: str,
    ) -> Mapping[str, Any]:
        """Seed deterministic tool evidence through the public Memory boundary.

        This prepares evidence only. The acceptance case must still make the
        provider propose memory.retrieve and the ordinary governed runtime must
        execute it. The rig never invokes the Tools kernel for this case.
        """

        from nexus_ndka.kernels.memory import (
            MemoryOperation,
            MemoryRequest,
            MemoryResult,
        )
        from nexus_ndka.runtime.contracts import KernelStatus, RuntimeContext

        assembled, _ = self._require_started()
        manager = assembled.host.registry.get("nexus.memory")
        request_id = f"monster-tool-seed:{lookup_token}"
        context = RuntimeContext(
            request_id=request_id,
            turn_id=request_id,
            actor_id=str(self.primary_user_id),
            scope_id=str(self.primary_user_id),
            session_id=f"monster-tool-seed-{lookup_token}",
            metadata={
                "owner_key": self.primary_owner_key,
                "acceptance_fixture_seed": True,
            },
        )
        result = asyncio.run(
            manager.execute(
                MemoryRequest(
                    operation=MemoryOperation.CANONICAL_ADD,
                    user_id=self.primary_user_id,
                    owner_key=self.primary_owner_key,
                    correlation_id=request_id,
                    source_type="MONSTER_ACCEPTANCE_FIXTURE",
                    source_record_id=lookup_token,
                    text=(
                        f"Acceptance lookup token {lookup_token}. "
                        f"The verified hidden value is {hidden_value}."
                    ),
                    provenance={
                        "source": "monster_acceptance",
                        "purpose": "runtime_initiated_tool_loop",
                        "lookup_token": lookup_token,
                    },
                    confidence=1.0,
                    truth_label="SYSTEM_RECORD",
                    topic="monster_runtime_tool_loop",
                    model_generated=False,
                    user_confirmed=True,
                ),
                context,
            )
        )
        if not isinstance(result, MemoryResult):
            raise TypeError(
                f"memory seed returned {type(result)!r}; expected MemoryResult"
            )
        self._observe_boundary_result(result, label="memory.acceptance_tool_seed")
        value = result.envelope.value if isinstance(result.envelope.value, Mapping) else {}
        return {
            "receipt_status": result.receipt.status.value,
            "source_id": value.get("source_id"),
            "idempotent_replay": bool(value.get("idempotent_replay")),
            "seeded": result.receipt.status is KernelStatus.OK and bool(value.get("source_id")),
        }
    @timed_method("runtime.exercise_kernel_boundary")
    def exercise_kernel_boundary(self, kernel_id: str, *, marker: str) -> Mapping[str, Any]:
        """Exercise a registered public manager at its owning responsibility.

        This is not evidence that the department participates in every chat turn.
        It proves only that the assembled host can execute the kernel's public
        contract against disposable Monster state. Cross-kernel caller wiring is
        reported separately and must not be inferred from this probe.
        """

        assembled, _ = self._require_started()
        manager = assembled.host.registry.get(kernel_id)
        context = self._boundary_context(label=f"{kernel_id}:{marker}")

        if kernel_id == "nexus.cognition":
            from nexus_ndka.kernels.cognition import CognitionOperation, CognitionRequest

            result = asyncio.run(
                manager.execute(
                    CognitionRequest(
                        operation=CognitionOperation.NODE_PROJECTION,
                        user_id=self.primary_user_id,
                        nlp_analysis={
                            "overall": {
                                "primary_intent": "question",
                                "primary_topic": "acceptance",
                            }
                        },
                        mode_node_affinities=(),
                        mood_state={},
                    ),
                    context,
                )
            )
            self._observe_boundary_result(result, label="cognition.node_projection")
            return {
                "kernel_id": kernel_id,
                "receipt_status": result.receipt.status.value,
                "operation": result.receipt.operation,
                "node_count": len(result.envelope.node_activations),
                "advisory_chars": len(result.envelope.node_prompt_text or ""),
                "state_mutated": result.receipt.state_mutated,
            }

        if kernel_id == "nexus.continuity":
            from nexus_ndka.kernels.continuity import (
                ContinuityOperation,
                ContinuityRequest,
            )

            created = asyncio.run(
                manager.execute(
                    ContinuityRequest(
                        operation=ContinuityOperation.CREATE_PIN,
                        content=f"Monster continuity boundary {marker}",
                        pin_type="CONTEXT",
                        source_type="ACCEPTANCE",
                        source_ref=context.turn_id,
                    ),
                    context,
                )
            )
            self._observe_boundary_result(created, label="continuity.create_pin")
            snapshot = asyncio.run(
                manager.execute(
                    ContinuityRequest(operation=ContinuityOperation.SNAPSHOT),
                    context,
                )
            )
            self._observe_boundary_result(snapshot, label="continuity.snapshot")
            pins = tuple((snapshot.envelope.snapshot or {}).get("pins") or ())
            return {
                "kernel_id": kernel_id,
                "receipt_status": created.receipt.status.value,
                "snapshot_status": snapshot.receipt.status.value,
                "pin_id": created.envelope.pin_id,
                "snapshot_pin_count": len(pins),
                "state_mutated": created.receipt.state_mutated,
            }

        if kernel_id == "nexus.learning":
            from nexus_ndka.kernels.learning import LearningOperation, LearningRequest

            result = asyncio.run(
                manager.execute(
                    LearningRequest(
                        operation=LearningOperation.SCAN_DIRECT_FEEDBACK,
                        text="Please stop using emoji and get to the point.",
                    ),
                    context,
                )
            )
            self._observe_boundary_result(result, label="learning.scan_direct_feedback")
            return {
                "kernel_id": kernel_id,
                "receipt_status": result.receipt.status.value,
                "operation": result.receipt.operation,
                "observation_count": len(result.envelope.observations),
                "state_mutated": result.receipt.state_mutated,
            }

        if kernel_id == "nexus.jobs":
            from nexus_ndka.kernels.jobs import JobOperation, JobRequest

            enqueued = asyncio.run(
                manager.execute(
                    JobRequest(
                        operation=JobOperation.ENQUEUE,
                        job_type="THINKER_OBSERVATION",
                        handler_version="1.0.0",
                        payload={"summary": f"bounded Monster job {marker}"},
                        idempotency_key=f"monster:{marker}:jobs",
                        owner_scope_type="USER",
                        owner_scope_id=context.scope_id,
                        max_attempts=3,
                        backoff_base_seconds=2,
                    ),
                    context,
                )
            )
            self._observe_boundary_result(enqueued, label="jobs.enqueue")
            snapshot = asyncio.run(
                manager.execute(
                    JobRequest(
                        operation=JobOperation.SNAPSHOT,
                        job_id=enqueued.envelope.job_id,
                    ),
                    context,
                )
            )
            self._observe_boundary_result(snapshot, label="jobs.snapshot")
            return {
                "kernel_id": kernel_id,
                "receipt_status": enqueued.receipt.status.value,
                "snapshot_status": snapshot.receipt.status.value,
                "job_id": enqueued.envelope.job_id,
                "job_status": enqueued.envelope.status,
                "state_mutated": enqueued.receipt.state_mutated,
            }

        if kernel_id == "nexus.artifacts":
            from nexus_ndka.kernels.artifacts import ArtifactOperation, ArtifactRequest

            created = asyncio.run(
                manager.execute(
                    ArtifactRequest(
                        operation=ArtifactOperation.CREATE,
                        artifact_type="ACCEPTANCE_TEXT",
                        media_type="text/plain",
                        content=f"ACCEPTANCE_ARTIFACT::{marker}".encode("utf-8"),
                        metadata={"source": "monster_boundary_probe"},
                    ),
                    context,
                )
            )
            self._observe_boundary_result(created, label="artifacts.create")
            descriptor = created.envelope.artifact
            if descriptor is None:
                raise RuntimeError("artifacts.create returned no descriptor")
            verified = asyncio.run(
                manager.execute(
                    ArtifactRequest(
                        operation=ArtifactOperation.VERIFY,
                        artifact_id=descriptor.artifact_id,
                        version=descriptor.version,
                    ),
                    context,
                )
            )
            self._observe_boundary_result(verified, label="artifacts.verify")
            return {
                "kernel_id": kernel_id,
                "receipt_status": created.receipt.status.value,
                "verify_status": verified.receipt.status.value,
                "artifact_id": descriptor.artifact_id,
                "artifact_version": descriptor.version,
                "sha256": descriptor.sha256,
                "verified": verified.envelope.verified,
                "state_mutated": created.receipt.state_mutated,
            }

        if kernel_id == "nexus.surfaces":
            from nexus_ndka.kernels.surfaces import SurfaceOperation, SurfaceRequest

            result = asyncio.run(
                manager.execute(
                    SurfaceRequest(
                        operation=SurfaceOperation.PROJECT_EVENT,
                        event_type="acceptance.boundary",
                        payload={"marker": marker, "user_id": self.primary_user_id},
                        sequence=1,
                        release_id=f"acceptance-release:{marker}",
                    ),
                    context,
                )
            )
            self._observe_boundary_result(result, label="surfaces.project_event")
            event = result.envelope.event
            return {
                "kernel_id": kernel_id,
                "receipt_status": result.receipt.status.value,
                "event_id": getattr(event, "event_id", None),
                "replay_token": getattr(event, "replay_token", None),
                "state_mutated": result.receipt.state_mutated,
            }

        raise ValueError(f"unsupported Monster boundary probe kernel: {kernel_id}")

    @timed_method("runtime.exercise_fault_boundary")
    def exercise_fault_boundary(self, fault: str, *, marker: str) -> Mapping[str, Any]:
        """Commission bounded failure controls through real public managers.

        The acceptance harness may swap a department's operation owner only for
        the duration of one tagged probe. The request still crosses the real
        manager policy/normalization/receipt boundary, and the original owner is
        restored in finally. No production source or persistent donor state is
        modified.
        """

        assembled, _ = self._require_started()
        context = self._boundary_context(label=f"fault:{fault}:{marker}")

        if fault == "provider_timeout":
            from nexus_ndka.kernels.provider.contracts import (
                ProviderOperation,
                ProviderRequest,
            )
            from nexus_ndka.runtime.contracts import KernelStatus

            manager = assembled.host.registry.get("nexus.provider")
            original = manager._operation_owner[ProviderOperation.GENERATE]

            class AcceptanceTimeoutSpecialist:
                specialist_id = "acceptance_provider_timeout"
                operations = frozenset({ProviderOperation.GENERATE})

                async def execute(self, request, runtime_context):
                    del request, runtime_context
                    raise TimeoutError("acceptance injected provider timeout")

            manager._operation_owner[ProviderOperation.GENERATE] = AcceptanceTimeoutSpecialist()
            try:
                result = asyncio.run(
                    manager.execute(
                        ProviderRequest(
                            operation=ProviderOperation.GENERATE,
                            system_prompt="Acceptance provider failure control.",
                            user_prompt="Exercise provider timeout handling.",
                        ),
                        context,
                    )
                )
            finally:
                manager._operation_owner[ProviderOperation.GENERATE] = original

            self._observe_boundary_result(result, label="fault.provider_timeout")
            return {
                "fault": fault,
                "receipt_status": result.receipt.status.value,
                "error_type": result.receipt.details.get("error_type"),
                "specialist_failure": result.envelope.diagnostics.get("specialist_failure"),
                "restored": manager._operation_owner[ProviderOperation.GENERATE] is original,
                "bounded": result.receipt.status is KernelStatus.FAILED,
            }

        if fault == "tool_timeout":
            from nexus_ndka.kernels.tools.contracts import ToolOperation, ToolRequest
            from nexus_ndka.runtime.contracts import KernelStatus

            manager = assembled.host.registry.get("nexus.tools")
            original = manager._operation_owner[ToolOperation.EXECUTE]

            class AcceptanceTimedOutToolSpecialist:
                specialist_id = "acceptance_tool_timeout"
                operations = frozenset({ToolOperation.EXECUTE})

                async def execute(self, request, runtime_context):
                    del request, runtime_context
                    return {
                        "execution_id": f"acceptance-timeout:{marker}",
                        "status": "TIMED_OUT",
                        "output": {},
                        "artifact_ids": (),
                        "media_ids": (),
                        "error_code": "ACCEPTANCE_TIMEOUT",
                        "execution_receipt_id": f"acceptance-timeout-receipt:{marker}",
                        "attempt_count": 1,
                        "provenance": {"acceptance_fault_injection": "tool_timeout"},
                    }

            manager._operation_owner[ToolOperation.EXECUTE] = AcceptanceTimedOutToolSpecialist()
            try:
                result = asyncio.run(
                    manager.execute(
                        ToolRequest(
                            operation=ToolOperation.EXECUTE,
                            tool_id="document.read",
                            version="1.0.0",
                            arguments={"segment_ids": ["acceptance-timeout-segment"]},
                            provider_proposal_id=f"acceptance-timeout:{marker}",
                        ),
                        context,
                    )
                )
            finally:
                manager._operation_owner[ToolOperation.EXECUTE] = original

            self._observe_boundary_result(result, label="fault.tool_timeout")
            return {
                "fault": fault,
                "receipt_status": result.receipt.status.value,
                "terminal_status": result.envelope.status,
                "error_code": result.envelope.error_code,
                "restored": manager._operation_owner[ToolOperation.EXECUTE] is original,
                "bounded": (
                    result.envelope.status == "TIMED_OUT"
                    and result.receipt.status is KernelStatus.DEGRADED
                ),
            }

        if fault == "forged_evidence":
            from nexus_ndka.kernels.evidence.contracts import EvidenceRequest
            from nexus_ndka.runtime.contracts import KernelStatus

            manager = assembled.host.registry.get("nexus.evidence")
            result = asyncio.run(
                manager.execute(
                    EvidenceRequest(
                        actor_authenticated=True,
                        authorized=True,
                        authority_reference_ids=(f"acceptance-authority:{marker}",),
                        tool_statuses={
                            f"forged-execution:{marker}": "SUCCEEDED",
                        },
                    ),
                    context,
                )
            )
            self._observe_boundary_result(result, label="fault.forged_evidence")
            return {
                "fault": fault,
                "receipt_status": result.receipt.status.value,
                "reason": result.receipt.details.get("reason"),
                "stage": result.receipt.details.get("stage"),
                "bounded": result.receipt.status is KernelStatus.REJECTED,
            }

        raise ValueError(f"unsupported Monster fault boundary: {fault}")

    def provider_chat_json(
        self,
        system: str,
        user: str,
        *,
        label: str = "provider.attribution_selection",
    ) -> tuple[dict[str, Any], str]:
        """Use the registered Provider manager without creating a full user turn."""

        from nexus_ndka.kernels.provider.contracts import (
            InferenceRole,
            ProviderOperation,
            ProviderRequest,
        )
        from nexus_ndka.runtime.contracts import KernelStatus, RuntimeContext

        assembled, _ = self._require_started()
        manager = assembled.host.registry.get("nexus.provider")
        context = RuntimeContext(
            request_id=f"monster-provider-callback:{label}",
            turn_id=f"monster-provider-callback:{label}",
            actor_id=str(self.primary_user_id),
            scope_id=str(self.primary_user_id),
            session_id=f"monster-provider-callback:{label}",
            metadata={
                "acceptance_provider_callback": True,
                "owner_key": self.primary_owner_key,
            },
        )
        started = time.perf_counter_ns()
        result = asyncio.run(
            manager.execute(
                ProviderRequest(
                    operation=ProviderOperation.GENERATE,
                    system_prompt=system,
                    user_prompt=user,
                    role=InferenceRole.PRIMARY_RESPONSE,
                    required_capabilities=frozenset({"TEXT"}),
                    available_tools=(),
                ),
                context,
            )
        )
        wall_ms = (time.perf_counter_ns() - started) / 1_000_000
        self._takt.record(
            label,
            wall_ms,
            source="observer_wall",
            boundary="nexus",
            metadata={"kernel_id": "nexus.provider"},
        )
        self._observe_boundary_result(result, label=label)
        if result.receipt.status is not KernelStatus.OK:
            raise RuntimeError(
                f"{label} failed: "
                + str(result.envelope.diagnostics or result.receipt.details)
            )
        content = str(result.envelope.text or "")
        if not content.strip():
            raise RuntimeError(f"{label} returned empty provider text")
        raw = {
            "id": f"kernelized-monster:{label}",
            "model": result.envelope.model_id,
            "provider": result.envelope.provider_id,
            "usage": None,
            "receipt_status": result.receipt.status.value,
            "kernel_duration_ms": getattr(result.receipt, "duration_ms", None),
        }
        return raw, content

    def record_nexus_takt(
        self,
        name: str,
        duration_ms: float,
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        self._takt.record(
            name,
            duration_ms,
            source="observer_wall",
            boundary="nexus",
            metadata=metadata,
        )

    def record_external_takt(
        self,
        name: str,
        duration_ms: float,
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        self._takt.record(
            name,
            duration_ms,
            source="external_boundary",
            boundary="external",
            metadata=metadata,
        )

    def takt(self) -> Mapping[str, Any]:
        return self._takt.snapshot()

    @timed_method("runtime.chat.total")
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

    @timed_method("runtime.health.total")
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
            "provider_probe": dict(self._provider_probe),
            "analysis_probe": dict(self._analysis_probe),
            "rag_probe": dict(self._rag_probe),
        }

    def direct_readiness_probe(self) -> Mapping[str, Any]:
        return dict(self.health())

    @timed_method("runtime.coverage.total")
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
            "coverage_sources": {
                kernel_id: dict(values)
                for kernel_id, values in self._coverage_sources.items()
            },
            "turn_count": len(self._turns),
            "turns": tuple(self._turns),
            "boundary_events": tuple(self._boundary_events),
            "wiring_classification": {
                "canonical_chat_active": (
                    "nexus.security",
                    "nexus.analysis",
                    "nexus.memory",
                    "nexus.identity",
                    "nexus.modes",
                    "nexus.context",
                    "nexus.tools",
                    "nexus.provider",
                    "nexus.evidence",
                    "nexus.correction",
                    "nexus.release",
                ),
                "owned_boundary_or_conditional": (
                    "nexus.cognition",
                    "nexus.continuity",
                    "nexus.learning",
                    "nexus.jobs",
                    "nexus.artifacts",
                    "nexus.surfaces",
                ),
                "known_test_required_edges": (
                    "context_to_cognition_to_provider",
                    "continuity_to_jobs_follow_up_enqueue",
                    "tools_to_ndka_continuity_and_artifacts",
                    "learning_post_turn_orchestration",
                    "artifacts_to_surfaces_delivery",
                    "release_outbox_to_surface_ordering",
                ),
            },
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
        if normalized == "GET" and path == "/takt":
            return _MappingResponse(200, dict(self.takt()))
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
            "observer-takt-timing",
            "kernel-receipt-duration-observation",
        )


class _MappingResponse:
    def __init__(self, status_code: int, body: Mapping[str, Any]) -> None:
        self.status_code = status_code
        self._body = body

    def json(self) -> Mapping[str, Any]:
        return self._body


def create_runtime_adapter(config: RigConfig) -> KernelizedMonsterRuntimeAdapter:
    return KernelizedMonsterRuntimeAdapter(config)
