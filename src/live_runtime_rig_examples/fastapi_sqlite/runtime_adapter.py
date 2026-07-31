"""Runtime adapter for the in-process work-order API."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from fastapi.testclient import TestClient

from live_runtime_rig.config import RigConfig

from .app import create_app


class WorkOrderRuntimeAdapter:
    def __init__(self, config: RigConfig) -> None:
        self._app = create_app(config.database_path)
        self._client: TestClient | None = None

    def start(self) -> None:
        if self._client is not None:
            raise RuntimeError("Runtime adapter is already started")
        self._client = TestClient(self._app)
        self._client.__enter__()

    def close(self) -> None:
        if self._client is not None:
            self._client.__exit__(None, None, None)
            self._client = None

    def health(self) -> Mapping[str, Any]:
        response = self.request("GET", "/health")
        return {
            "ready": response.status_code == 200
            and response.json().get("ready") is True,
            "status_code": response.status_code,
        }

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        if self._client is None:
            raise RuntimeError("Runtime adapter has not been started")
        return self._client.request(method, path, **kwargs)

    def direct_readiness_probe(self) -> Mapping[str, Any]:
        route_paths = {route.path for route in self._app.routes}
        required = {
            "/health",
            "/work-orders",
            "/work-orders/{work_order_id}",
            "/work-orders/{work_order_id}/archive",
        }
        return {
            "ready": required.issubset(route_paths),
            "required_route_count": len(required),
        }

    def list_capabilities(self) -> Sequence[str]:
        return (
            "health",
            "create-work-order",
            "read-work-order",
            "update-work-order",
            "archive-work-order",
        )


def create_runtime_adapter(config: RigConfig) -> WorkOrderRuntimeAdapter:
    return WorkOrderRuntimeAdapter(config)
