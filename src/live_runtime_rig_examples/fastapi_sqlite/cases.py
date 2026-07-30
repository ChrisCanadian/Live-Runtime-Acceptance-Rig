"""Acceptance cases for the unrelated work-order example."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from live_runtime_rig.assertions import CheckStatus
from live_runtime_rig.contracts import (
    CaseContext,
    CaseResult,
    CheckSpec,
    DatabaseAdapter,
    RuntimeAdapter,
)


def _status(condition: bool) -> CheckStatus:
    return CheckStatus.PASS if condition is True else CheckStatus.FAIL


@dataclass(frozen=True)
class WorkOrderLifecycleCase:
    name: str = "work_order_lifecycle"
    suite: str = "work order lifecycle"

    def run(
        self,
        runtime: RuntimeAdapter,
        database: DatabaseAdapter,
        context: CaseContext,
    ) -> CaseResult:
        marker = context.marker
        initial_title = "Inspect example circulation pump"
        updated_title = "Inspect and label example circulation pump"
        context.tracer.emit(
            "case.input.metadata",
            suite=self.suite,
            case=self.name,
            title=context.tracer.protected_text_metadata(initial_title),
        )

        create_response = runtime.request(
            "POST",
            "/work-orders",
            json={"marker": marker, "title": initial_title},
        )
        create_body = create_response.json()
        work_order_id = str(create_body.get("id", ""))
        durable_created = (
            database.verify_created_record("work_order", work_order_id)
            if work_order_id
            else None
        )

        read_response = runtime.request(
            "GET", f"/work-orders/{work_order_id}"
        )
        update_response = runtime.request(
            "PATCH",
            f"/work-orders/{work_order_id}",
            json={
                "marker": marker,
                "title": updated_title,
                "status": "in_progress",
            },
        )
        durable_updated = database.verify_created_record(
            "work_order", work_order_id
        )
        archive_response = runtime.request(
            "POST",
            f"/work-orders/{work_order_id}/archive",
            json={"marker": marker},
        )
        durable_archived = database.verify_created_record(
            "work_order", work_order_id
        )
        resources = database.resources_for_work_order(work_order_id, marker)
        audit_actions = sorted(
            receipt["action"] for receipt in resources["audit_receipts"]
        )
        event_types = sorted(event["event_type"] for event in resources["events"])

        checks = [
            CheckSpec(
                "Create endpoint returned 201",
                _status(create_response.status_code == 201),
                201,
                create_response.status_code,
            ),
            CheckSpec(
                "Create response contains current run marker",
                _status(create_body.get("marker") == marker),
                marker,
                create_body.get("marker"),
            ),
            CheckSpec(
                "Created work order passed durable readback",
                _status(
                    durable_created is not None
                    and durable_created.get("marker") == marker
                    and durable_created.get("title") == initial_title
                ),
                {"marker": marker, "title": initial_title},
                durable_created,
            ),
            CheckSpec(
                "Read endpoint returned the tagged work order",
                _status(
                    read_response.status_code == 200
                    and read_response.json().get("id") == work_order_id
                ),
                {"status": 200, "id": work_order_id},
                {
                    "status": read_response.status_code,
                    "id": read_response.json().get("id"),
                },
            ),
            CheckSpec(
                "Update endpoint changed only the tagged work order",
                _status(
                    update_response.status_code == 200
                    and durable_updated is not None
                    and durable_updated.get("marker") == marker
                    and durable_updated.get("title") == updated_title
                    and durable_updated.get("status") == "in_progress"
                ),
                {
                    "status": 200,
                    "marker": marker,
                    "title": updated_title,
                    "work_order_status": "in_progress",
                },
                {
                    "status": update_response.status_code,
                    "row": durable_updated,
                },
            ),
            CheckSpec(
                "Archive endpoint archived only the tagged work order",
                _status(
                    archive_response.status_code == 200
                    and durable_archived is not None
                    and durable_archived.get("marker") == marker
                    and durable_archived.get("archived") == 1
                ),
                {"status": 200, "marker": marker, "archived": 1},
                {
                    "status": archive_response.status_code,
                    "row": durable_archived,
                },
            ),
            CheckSpec(
                "Audit receipts verify create, update, and archive",
                _status(audit_actions == ["archived", "created", "updated"]),
                ["archived", "created", "updated"],
                audit_actions,
            ),
            CheckSpec(
                "Durable event history matches the lifecycle",
                _status(event_types == ["archived", "created", "updated"]),
                ["archived", "created", "updated"],
                event_types,
            ),
        ]
        cleanup_entries = [
            database.cleanup_manifest_entry(
                "work_order",
                work_order_id,
                marker,
                notes="Archived work order created by this acceptance run.",
            )
        ]
        cleanup_entries.extend(
            database.cleanup_manifest_entry(
                "event",
                str(event["id"]),
                marker,
                notes=f"Lifecycle event for work order {work_order_id}.",
            )
            for event in resources["events"]
        )
        cleanup_entries.extend(
            database.cleanup_manifest_entry(
                "audit_receipt",
                str(receipt["id"]),
                marker,
                notes=f"Audit receipt for work order {work_order_id}.",
            )
            for receipt in resources["audit_receipts"]
        )
        return CaseResult(
            checks=checks,
            evidence={
                "request_statuses": {
                    "create": create_response.status_code,
                    "read": read_response.status_code,
                    "update": update_response.status_code,
                    "archive": archive_response.status_code,
                },
                "work_order_id": work_order_id,
                "marker": marker,
                "durable_row": durable_archived,
                "audit_actions": audit_actions,
                "event_types": event_types,
            },
            cleanup_entries=cleanup_entries,
            state_updates={"work_order_id": work_order_id},
        )


@dataclass(frozen=True)
class InvalidInputCase:
    name: str = "invalid_input"
    suite: str = "validation"

    def run(
        self,
        runtime: RuntimeAdapter,
        database: DatabaseAdapter,
        context: CaseContext,
    ) -> CaseResult:
        response = runtime.request(
            "POST",
            "/work-orders",
            json={"marker": context.marker, "title": ""},
        )
        body = response.json()
        detail = body.get("detail")
        return CaseResult(
            checks=[
                CheckSpec(
                    "Invalid input is rejected with 422",
                    _status(response.status_code == 422),
                    422,
                    response.status_code,
                ),
                CheckSpec(
                    "Validation response contains structured detail",
                    _status(isinstance(detail, list) and len(detail) > 0),
                    "non-empty detail list",
                    type(detail).__name__,
                ),
            ],
            evidence={
                "status_code": response.status_code,
                "detail_type": type(detail).__name__,
            },
        )


@dataclass(frozen=True)
class IntentionalFailureCase:
    name: str = "intentional_acceptance_failure"
    suite: str = "demonstration"

    def run(
        self,
        runtime: RuntimeAdapter,
        database: DatabaseAdapter,
        context: CaseContext,
    ) -> CaseResult:
        enabled = context.settings.get("intentional_failure") is True
        if not enabled:
            return CaseResult(
                checks=[
                    CheckSpec(
                        "Intentional failure demonstration",
                        CheckStatus.SKIP,
                        "enabled by the intentional-failure example config",
                        "disabled for the passing campaign",
                    )
                ],
                evidence={"intentional_failure_enabled": False},
            )
        return CaseResult(
            checks=[
                CheckSpec(
                    "Intentional service-level expectation",
                    CheckStatus.FAIL,
                    "urgent",
                    "normal",
                    heuristic=False,
                )
            ],
            evidence={
                "intentional_failure_enabled": True,
                "purpose": (
                    "Demonstrate a completed framework campaign that exits nonzero "
                    "because an acceptance check failed."
                ),
            },
        )


def register_cases(config: Any):
    return [
        WorkOrderLifecycleCase(),
        InvalidInputCase(),
        IntentionalFailureCase(),
    ]
