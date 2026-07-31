from __future__ import annotations

from fastapi.testclient import TestClient

from live_runtime_rig_examples.fastapi_sqlite.app import create_app
from live_runtime_rig_examples.fastapi_sqlite.database import initialize_database
from live_runtime_rig_examples.fastapi_sqlite.database_adapter import (
    WorkOrderDatabaseAdapter,
)


def test_work_order_create_update_archive_and_durable_readback(tmp_path) -> None:
    database_path = tmp_path / "work_orders.sqlite"
    initialize_database(database_path)
    database = WorkOrderDatabaseAdapter(database_path)
    protected_before = database.protected_state_snapshot()
    marker = "ACCEPTANCE_EXAMPLE"

    with TestClient(create_app(database_path)) as client:
        created = client.post(
            "/work-orders",
            json={"marker": marker, "title": "Inspect example valve"},
        )
        assert created.status_code == 201
        work_order_id = created.json()["id"]

        durable_created = database.verify_created_record(
            "work_order", work_order_id
        )
        assert durable_created["marker"] == marker
        assert durable_created["title"] == "Inspect example valve"

        updated = client.patch(
            f"/work-orders/{work_order_id}",
            json={
                "marker": marker,
                "title": "Inspect and label example valve",
                "status": "in_progress",
            },
        )
        assert updated.status_code == 200

        archived = client.post(
            f"/work-orders/{work_order_id}/archive",
            json={"marker": marker},
        )
        assert archived.status_code == 200
        assert archived.json()["archived"] is True

    durable_archived = database.verify_created_record(
        "work_order", work_order_id
    )
    assert durable_archived["archived"] == 1
    resources = database.resources_for_work_order(work_order_id, marker)
    assert sorted(item["action"] for item in resources["audit_receipts"]) == [
        "archived",
        "created",
        "updated",
    ]
    assert database.protected_state_snapshot() == protected_before


def test_invalid_input_returns_structured_422(tmp_path) -> None:
    database_path = tmp_path / "work_orders.sqlite"
    initialize_database(database_path)
    with TestClient(create_app(database_path)) as client:
        response = client.post(
            "/work-orders",
            json={"marker": "ACCEPTANCE_EXAMPLE", "title": ""},
        )
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)
