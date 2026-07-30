"""A deliberately small work-order service used only as a public example."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from .database import connect, initialize_database


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CreateWorkOrder(BaseModel):
    marker: str = Field(min_length=8, max_length=80)
    title: str = Field(min_length=3, max_length=200)


class UpdateWorkOrder(BaseModel):
    marker: str = Field(min_length=8, max_length=80)
    title: str = Field(min_length=3, max_length=200)
    status: Literal["open", "in_progress"]


class ArchiveWorkOrder(BaseModel):
    marker: str = Field(min_length=8, max_length=80)


def _row_payload(row) -> dict:
    return {
        "id": row["id"],
        "marker": row["marker"],
        "title": row["title"],
        "status": row["status"],
        "archived": bool(row["archived"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def create_app(database_path: Path) -> FastAPI:
    initialize_database(database_path)
    app = FastAPI(title="Work Order Example", version="1.0")

    @app.get("/health")
    def health() -> dict:
        with connect(database_path) as connection:
            connection.execute("SELECT 1").fetchone()
        return {"ready": True}

    @app.post("/work-orders", status_code=status.HTTP_201_CREATED)
    def create_work_order(payload: CreateWorkOrder) -> dict:
        work_order_id = str(uuid4())
        event_id = str(uuid4())
        receipt_id = str(uuid4())
        timestamp = utc_now()
        with connect(database_path) as connection:
            connection.execute(
                """
                INSERT INTO work_orders
                    (id, marker, title, status, archived, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    work_order_id,
                    payload.marker,
                    payload.title,
                    "open",
                    0,
                    timestamp,
                    timestamp,
                ),
            )
            connection.execute(
                """
                INSERT INTO work_order_events
                    (id, work_order_id, marker, event_type, detail, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    work_order_id,
                    payload.marker,
                    "created",
                    "Work order created",
                    timestamp,
                ),
            )
            connection.execute(
                """
                INSERT INTO audit_receipts
                    (id, work_order_id, marker, action, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    receipt_id,
                    work_order_id,
                    payload.marker,
                    "created",
                    timestamp,
                ),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM work_orders WHERE id = ?", (work_order_id,)
            ).fetchone()
        return _row_payload(row)

    @app.get("/work-orders/{work_order_id}")
    def get_work_order(work_order_id: str) -> dict:
        with connect(database_path) as connection:
            row = connection.execute(
                "SELECT * FROM work_orders WHERE id = ?", (work_order_id,)
            ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Work order not found")
        return _row_payload(row)

    @app.patch("/work-orders/{work_order_id}")
    def update_work_order(work_order_id: str, payload: UpdateWorkOrder) -> dict:
        timestamp = utc_now()
        with connect(database_path) as connection:
            current = connection.execute(
                "SELECT * FROM work_orders WHERE id = ? AND marker = ?",
                (work_order_id, payload.marker),
            ).fetchone()
            if current is None:
                raise HTTPException(
                    status_code=404, detail="Tagged work order not found"
                )
            connection.execute(
                """
                UPDATE work_orders
                SET title = ?, status = ?, updated_at = ?
                WHERE id = ? AND marker = ?
                """,
                (
                    payload.title,
                    payload.status,
                    timestamp,
                    work_order_id,
                    payload.marker,
                ),
            )
            connection.execute(
                """
                INSERT INTO work_order_events
                    (id, work_order_id, marker, event_type, detail, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    work_order_id,
                    payload.marker,
                    "updated",
                    "Work order updated",
                    timestamp,
                ),
            )
            connection.execute(
                """
                INSERT INTO audit_receipts
                    (id, work_order_id, marker, action, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    work_order_id,
                    payload.marker,
                    "updated",
                    timestamp,
                ),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM work_orders WHERE id = ? AND marker = ?",
                (work_order_id, payload.marker),
            ).fetchone()
        return _row_payload(row)

    @app.post("/work-orders/{work_order_id}/archive")
    def archive_work_order(
        work_order_id: str, payload: ArchiveWorkOrder
    ) -> dict:
        timestamp = utc_now()
        with connect(database_path) as connection:
            current = connection.execute(
                "SELECT * FROM work_orders WHERE id = ? AND marker = ?",
                (work_order_id, payload.marker),
            ).fetchone()
            if current is None:
                raise HTTPException(
                    status_code=404, detail="Tagged work order not found"
                )
            connection.execute(
                """
                UPDATE work_orders
                SET archived = ?, status = ?, updated_at = ?
                WHERE id = ? AND marker = ?
                """,
                (1, "in_progress", timestamp, work_order_id, payload.marker),
            )
            connection.execute(
                """
                INSERT INTO work_order_events
                    (id, work_order_id, marker, event_type, detail, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    work_order_id,
                    payload.marker,
                    "archived",
                    "Work order archived",
                    timestamp,
                ),
            )
            connection.execute(
                """
                INSERT INTO audit_receipts
                    (id, work_order_id, marker, action, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    work_order_id,
                    payload.marker,
                    "archived",
                    timestamp,
                ),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM work_orders WHERE id = ? AND marker = ?",
                (work_order_id, payload.marker),
            ).fetchone()
        return _row_payload(row)

    return app
