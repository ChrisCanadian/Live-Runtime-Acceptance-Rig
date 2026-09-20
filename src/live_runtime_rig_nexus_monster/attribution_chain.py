"""Attribution-chain acceptance composition for the full Nexus Monster.

Moon Source discovers relevant public evidence, HZK admits it as read-only
knowledge, Business Brain preserves it as a governed draft artifact, and the
canonical kernelized Nexus runtime synthesizes the bounded packet.

Attribution is proven by receipts/provenance, not by forcing the user-facing
Nexus answer to narrate internal plumbing.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Mapping


def _clean_json(value: str) -> dict[str, Any]:
    text = str(value or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("attribution synthesis must be a JSON object")
    return parsed


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _timed(runtime: Any, name: str, fn, *, metadata: Mapping[str, Any] | None = None):
    started = time.perf_counter_ns()
    result = fn()
    elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
    runtime.record_external_takt(name, elapsed_ms, metadata=metadata)
    return result, elapsed_ms


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
            }
        )
    return trace


def run_attribution_chain(runtime: Any, *, marker: str) -> dict[str, Any]:
    bb_root = Path(os.environ["NEXUS_RIG_BUSINESS_BRAIN_CHECKOUT"]).resolve()
    moon_root = Path(os.environ["NEXUS_RIG_MOON_SOURCE_DIR"]).resolve()
    bb_db = Path(
        os.environ.get(
            "NEXUS_RIG_BUSINESS_BRAIN_DB_PATH",
            "/run/state/business-brain-attribution.db",
        )
    ).resolve()

    if not (bb_root / "integration_lab" / "business_brain_moon_source.py").is_file():
        raise FileNotFoundError(f"Business Brain attribution integration missing: {bb_root}")
    if not (moon_root / "registry" / "public-capabilities.json").is_file():
        raise FileNotFoundError(f"Moon Source corpus missing: {moon_root}")

    for module_path in (bb_root, bb_root / "src"):
        value = str(module_path)
        if value not in sys.path:
            sys.path.insert(0, value)

    from integration_lab.attribution_chain_score import score_discovery
    from integration_lab.business_brain_moon_source import MoonSourceEmbedded
    from integration_lab.hzk_business_brain_knowledge import govern_selected_sources
    from business_brain.models import ActorContext
    from business_brain.service import BusinessBrainService

    incident_path = bb_root / "tests" / "fixtures" / "attribution_incident_v1.txt"
    incident = incident_path.read_text(encoding="utf-8")

    moon = MoonSourceEmbedded(
        moon_root,
        chat_callable=lambda system, user: runtime.provider_chat_json(
            system,
            user,
            label="attribution.moon_source.provider_selection",
        ),
    )
    moon_pair, moon_wall_ms = _timed(
        runtime,
        "external.moon_source.discovery_total",
        lambda: moon.discover(incident),
        metadata={"boundary": "moon_source"},
    )
    moon_result, moon_provider = moon_pair
    moon_score = score_discovery(moon_result)

    hzk, hzk_wall_ms = _timed(
        runtime,
        "external.hzk.knowledge_governance_total",
        lambda: govern_selected_sources(
            moon_root,
            list(moon_result["selected_sources"]),
            query=incident,
            correlation_id=f"monster-attribution:{marker}",
        ),
        metadata={"boundary": "hzk"},
    )

    bb_db.parent.mkdir(parents=True, exist_ok=True)
    if bb_db.exists():
        bb_db.unlink()

    service_started = time.perf_counter_ns()
    service = BusinessBrainService(bb_db)
    service.create_workspace("attribution_chain_test", "Attribution Knowledge Chain")
    service.put_member(
        "attribution_chain_test",
        "service:nexus",
        actor_type="service",
        roles=("client_adapter",),
        permissions=("capture", "distill", "read", "export"),
    )
    runtime.record_external_takt(
        "external.business_brain.initialize",
        (time.perf_counter_ns() - service_started) / 1_000_000,
        metadata={"boundary": "business_brain"},
    )
    actor = ActorContext(
        actor_id="service:nexus",
        actor_type="service",
        workspace_id="attribution_chain_test",
        channel_scope_id="monster:attribution-chain",
        visibility_scope="team",
        verified_roles=("client_adapter",),
        verified_permissions=("capture", "distill", "read", "export"),
        request_source="nexus_monster",
        session_id=f"monster-attribution-{marker}",
    )

    normalized_incident = incident.replace("\r\n", "\n").replace("\r", "\n").strip()
    artifact_id = "BB-ATTR-" + hashlib.sha256(marker.encode("utf-8")).hexdigest()[:20]

    capture, capture_ms = _timed(
        runtime,
        "external.business_brain.capture",
        lambda: service.execute(
            "capture",
            {
                "artifact_id": artifact_id,
                "artifact_type": "attribution_resolution",
                "content": incident,
                "external_source_id": "fixture:attribution_incident_v1",
                "source_type": "owner_acceptance_fixture",
                "source_checksum": "sha256:" + _sha256_text(normalized_incident),
                "visibility": "team",
                "origin_owner": "ChrisCanadian/business-brain",
                "source_steward": "owner_acceptance_rig",
                "source_metadata": {
                    "fixture": "tests/fixtures/attribution_incident_v1.txt",
                    "purpose": "source->knowledge->business attribution acceptance",
                },
            },
            actor,
        ),
        metadata={"boundary": "business_brain"},
    )

    moon_projection = {
        "source_revision": moon_result.get("source_revision"),
        "selected_sources": moon_result.get("selected_sources"),
        "ownership_boundaries": moon_result.get("ownership_boundaries"),
        "claim_dispositions": moon_result.get("claim_dispositions"),
        "attribution_findings": moon_result.get("attribution_findings"),
        "claim_ceiling": moon_result.get("claim_ceiling"),
        "acceptance_score": moon_score,
    }
    hzk_projection = {
        key: hzk.get(key)
        for key in (
            "source_revision",
            "packet_id",
            "payload_sha256",
            "manifest_sha256",
            "selection_id",
            "constitutional_status",
            "evidence_status",
            "state_hash_before",
            "state_hash_after",
            "state_unchanged",
            "authority_clean",
            "historical_distinction_preserved",
            "entries",
            "instruction_authority",
            "mutation_authority",
        )
    }
    resolution_projection = {
        "ownership_boundaries": moon_result.get("ownership_boundaries"),
        "claim_dispositions": moon_result.get("claim_dispositions"),
        "attribution_findings": moon_result.get("attribution_findings"),
        "warnings": moon_result.get("warnings"),
        "status": "candidate_resolution_only",
        "promotion_authority": False,
    }

    distill, distill_ms = _timed(
        runtime,
        "external.business_brain.distill",
        lambda: service.execute(
            "distill",
            {
                "artifact_id": artifact_id,
                "expected_version": 1,
                "sections": {
                    "moon_source_discovery": json.dumps(
                        moon_projection, sort_keys=True, ensure_ascii=False
                    ),
                    "hzk_knowledge": json.dumps(
                        hzk_projection, sort_keys=True, ensure_ascii=False
                    ),
                    "attribution_resolution": json.dumps(
                        resolution_projection, sort_keys=True, ensure_ascii=False
                    ),
                },
                "change_summary": (
                    "Embedded Moon Source discovery plus HZK-verified attribution evidence"
                ),
                "reason": "Monster owner acceptance; no canonical promotion",
            },
            actor,
        ),
        metadata={"boundary": "business_brain"},
    )

    status, status_ms = _timed(
        runtime,
        "external.business_brain.status_readback",
        lambda: service.execute("status", {"artifact_id": artifact_id}, actor),
        metadata={"boundary": "business_brain"},
    )
    integrity, integrity_ms = _timed(
        runtime,
        "external.business_brain.integrity",
        service.verify_integrity,
        metadata={"boundary": "business_brain"},
    )

    sections = status.get("document", {}).get("sections", {})
    stored_source = str(sections.get("source") or "")
    source_immutable = _sha256_text(stored_source) == _sha256_text(normalized_incident)
    expected_sections = {
        "source",
        "moon_source_discovery",
        "hzk_knowledge",
        "attribution_resolution",
    }
    readback_complete = expected_sections <= set(sections)

    moon_entries = [
        item for item in moon_result.get("selected_sources", [])
        if isinstance(item, dict)
    ]
    hzk_entries = [
        item for item in hzk.get("entries", [])
        if isinstance(item, dict)
    ]
    moon_paths = {str(item.get("path")) for item in moon_entries}
    hzk_paths = {str(item.get("source_path")) for item in hzk_entries}

    stored_hzk = (
        json.loads(str(sections.get("hzk_knowledge") or "{}"))
        if readback_complete
        else {}
    )
    stored_hzk_entries = [
        item for item in stored_hzk.get("entries", [])
        if isinstance(item, dict)
    ]
    stored_hzk_paths = {str(item.get("source_path")) for item in stored_hzk_entries}

    moon_hashes = {
        str(item.get("path")): str(item.get("source_sha256") or "")
        for item in moon_entries
    }
    hzk_hashes = {
        str(item.get("source_path")): str(item.get("source_sha256") or "")
        for item in hzk_entries
    }
    stored_hzk_hashes = {
        str(item.get("source_path")): str(item.get("source_sha256") or "")
        for item in stored_hzk_entries
    }

    nested_provenance = moon_paths == hzk_paths == stored_hzk_paths and bool(moon_paths)
    nested_hash_provenance = (
        moon_hashes == hzk_hashes == stored_hzk_hashes
        and bool(moon_hashes)
        and all(moon_hashes.values())
    )

    hzk_concepts = sorted(
        {
            str(concept)
            for item in hzk_entries
            for concept in (item.get("concepts") or [])
            if str(concept)
        }
    )
    hzk_relevance_ok = {
        "attribution",
        "lineage",
        "provenance",
        "authority",
    } <= set(hzk_concepts)

    chain_packet = {
        "business_brain": {
            "artifact_id": artifact_id,
            "artifact_version": status.get("artifact_version"),
            "state": status.get("state"),
            "capture_receipt_id": capture.get("receipt_id"),
            "distill_receipt_id": distill.get("receipt_id"),
            "status_receipt_id": status.get("receipt_id"),
            "source_immutable": source_immutable,
            "readback_complete": readback_complete,
            "integrity_status": integrity.get("status"),
        },
        "moon_source_receipt": moon_projection,
        "hzk_receipt": hzk_projection,
        "provenance_checks": {
            "nested_provenance": nested_provenance,
            "nested_hash_provenance": nested_hash_provenance,
            "moon_paths": sorted(moon_paths),
            "hzk_paths": sorted(hzk_paths),
            "hzk_relevance_concepts": hzk_concepts,
        },
    }

    synthesis_prompt = (
        "Synthesize the bounded evidence packet below into a concise user-facing answer. "
        "The answer should focus on the substantive attribution/lineage resolution and "
        "evidence, not narrate internal pipeline mechanics merely for attribution. "
        "The application exposes source/system provenance separately through receipts. "
        "Do not claim that current integration topology proves historical lineage. "
        "Do not claim that conceptual influence automatically creates coauthorship. "
        "Return ONLY one JSON object with fields status, answer, "
        "guardrail_acknowledgements, unresolved, claim_ceiling. "
        "status must be PASS. answer must be natural prose suitable to show directly "
        "to a user. guardrail_acknowledgements must contain exactly these two values: "
        "current_topology_not_historical_lineage and "
        "conceptual_influence_not_automatic_coauthorship.\n\nCHAIN_PACKET:\n"
        + json.dumps(chain_packet, sort_keys=True, ensure_ascii=False)
    )

    nexus_started = time.perf_counter_ns()
    nexus_response = runtime.request(
        "POST",
        "/v1/chat/completions",
        principal="primary",
        json={
            "messages": [{"role": "user", "content": synthesis_prompt}],
            "session_id": f"monster-attribution-final-{marker}",
            "include_tools": False,
        },
    )
    nexus_wall_ms = (time.perf_counter_ns() - nexus_started) / 1_000_000
    runtime.record_nexus_takt(
        "attribution.nexus_final_canonical_synthesis",
        nexus_wall_ms,
        metadata={"boundary": "canonical_v1_chat_completions"},
    )

    try:
        nexus_body = nexus_response.json()
    except Exception:
        nexus_body = {}
    nexus_text = str(nexus_body.get("text") or "")
    try:
        nexus_json = _clean_json(nexus_text)
        nexus_json_error = None
    except Exception as exc:
        nexus_json = {}
        nexus_json_error = f"{type(exc).__name__}: {exc}"

    answer = str(nexus_json.get("answer") or "").strip()
    acknowledgements = {
        str(value)
        for value in (nexus_json.get("guardrail_acknowledgements") or [])
    }
    guardrails_ok = acknowledgements == {
        "current_topology_not_historical_lineage",
        "conceptual_influence_not_automatic_coauthorship",
    }
    substantive_terms = {
        "attribution",
        "lineage",
        "provenance",
        "authorship",
        "coauthorship",
        "authority",
        "evidence",
        "source",
    }
    answer_terms = {
        term for term in substantive_terms if term in answer.lower()
    }

    nexus_function_trace = _receipt_trace(nexus_body)
    nexus_kernel_ids = sorted(
        {
            str(item.get("kernel_id"))
            for item in nexus_function_trace
            if item.get("kernel_id")
        }
    )

    provenance_trace = {
        "moon_source": {
            "source_revision": moon_result.get("source_revision"),
            "selected_evidence": moon_entries,
            "relevance": moon_score,
        },
        "hzk": {
            "source_revision": hzk.get("source_revision"),
            "packet_id": hzk.get("packet_id"),
            "constitutional_status": hzk.get("constitutional_status"),
            "evidence_status": hzk.get("evidence_status"),
            "entries": hzk_entries,
            "concepts": hzk_concepts,
            "authority_clean": hzk.get("authority_clean"),
            "state_unchanged": hzk.get("state_unchanged"),
        },
        "business_brain": {
            "artifact_id": artifact_id,
            "artifact_version": status.get("artifact_version"),
            "state": status.get("state"),
            "capture_receipt_id": capture.get("receipt_id"),
            "distill_receipt_id": distill.get("receipt_id"),
            "status_receipt_id": status.get("receipt_id"),
            "integrity_status": integrity.get("status"),
        },
        "nexus": {
            "ingress": "/v1/chat/completions",
            "functions": nexus_function_trace,
            "kernel_ids": nexus_kernel_ids,
        },
        "alignment": {
            "path_identity_preserved": nested_provenance,
            "hash_identity_preserved": nested_hash_provenance,
        },
    }

    return {
        "moon_result": moon_result,
        "moon_provider": moon_provider,
        "moon_score": moon_score,
        "hzk": hzk,
        "hzk_relevance_ok": hzk_relevance_ok,
        "hzk_concepts": hzk_concepts,
        "business_brain": {
            "capture": capture,
            "distill": distill,
            "status": status,
            "integrity": integrity,
            "source_immutable": source_immutable,
            "readback_complete": readback_complete,
        },
        "chain_packet": chain_packet,
        "provenance_trace": provenance_trace,
        "nested_provenance": nested_provenance,
        "nested_hash_provenance": nested_hash_provenance,
        "nexus": {
            "status_code": getattr(nexus_response, "status_code", None),
            "body_state": nexus_body.get("state"),
            "text": nexus_text,
            "parsed": nexus_json,
            "parse_error": nexus_json_error,
            "answer": answer,
            "answer_terms": sorted(answer_terms),
            "guardrails_ok": guardrails_ok,
            "function_trace": nexus_function_trace,
            "kernel_ids": nexus_kernel_ids,
        },
        "timings_ms": {
            "moon_source_total": round(moon_wall_ms, 6),
            "hzk_total": round(hzk_wall_ms, 6),
            "bb_capture": round(capture_ms, 6),
            "bb_distill": round(distill_ms, 6),
            "bb_status": round(status_ms, 6),
            "bb_integrity": round(integrity_ms, 6),
            "nexus_final_canonical": round(nexus_wall_ms, 6),
        },
        "final_input_contains_original_incident": incident in synthesis_prompt,
    }
