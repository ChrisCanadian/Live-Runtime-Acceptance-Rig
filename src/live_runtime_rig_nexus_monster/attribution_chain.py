"""Attribution-chain acceptance composition for the full Nexus Monster.

The case composes sovereign components without changing their contracts:
Moon Source discovery -> HZK read-only knowledge governance -> Business Brain
artifact lifecycle -> canonical kernelized Nexus synthesis.
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

    for path in (bb_root, bb_root / "src"):
        value = str(path)
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
    (moon_pair, moon_wall_ms) = _timed(
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

    moon_paths = {
        str(item.get("path"))
        for item in moon_result.get("selected_sources", [])
        if isinstance(item, dict)
    }
    hzk_paths = {
        str(item.get("source_path"))
        for item in hzk.get("entries", [])
        if isinstance(item, dict)
    }
    stored_hzk = (
        json.loads(str(sections.get("hzk_knowledge") or "{}"))
        if readback_complete
        else {}
    )
    stored_hzk_paths = {
        str(item.get("source_path"))
        for item in stored_hzk.get("entries", [])
        if isinstance(item, dict)
    }
    nested_provenance = moon_paths == hzk_paths == stored_hzk_paths and bool(moon_paths)

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
            "moon_paths": sorted(moon_paths),
            "hzk_paths": sorted(hzk_paths),
        },
    }

    synthesis_prompt = (
        "You are the final Nexus synthesis boundary for an attribution acceptance test. "
        "You receive ONLY a bounded Business Brain packet plus nested Moon Source and HZK "
        "receipts. Preserve authority boundaries. Current integration topology is not proof "
        "of historical lineage. Conceptual influence is not automatically coauthorship. "
        "Return ONLY one JSON object with fields status, synthesis, authority_map, "
        "rejected_overclaims, unresolved, claim_ceiling. status must be PASS. "
        "authority_map must keep Moon Source, HZK, Business Brain, and Nexus distinct. "
        "rejected_overclaims must explicitly reject topology-implies-lineage and "
        "influence-implies-coauthorship.\n\nCHAIN_PACKET:\n"
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

    authority_text = json.dumps(nexus_json.get("authority_map") or []).lower()
    rejected_text = json.dumps(nexus_json.get("rejected_overclaims") or []).lower()

    return {
        "moon_result": moon_result,
        "moon_provider": moon_provider,
        "moon_score": moon_score,
        "hzk": hzk,
        "business_brain": {
            "capture": capture,
            "distill": distill,
            "status": status,
            "integrity": integrity,
            "source_immutable": source_immutable,
            "readback_complete": readback_complete,
        },
        "chain_packet": chain_packet,
        "nested_provenance": nested_provenance,
        "nexus": {
            "status_code": getattr(nexus_response, "status_code", None),
            "body_state": nexus_body.get("state"),
            "text": nexus_text,
            "parsed": nexus_json,
            "parse_error": nexus_json_error,
            "authority_distinct": all(
                value in authority_text
                for value in ("moon source", "hzk", "business brain", "nexus")
            ),
            "topology_lineage_rejected": (
                "topology" in rejected_text and "lineage" in rejected_text
            ),
            "influence_coauthorship_rejected": (
                "influence" in rejected_text and "coauthor" in rejected_text
            ),
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
