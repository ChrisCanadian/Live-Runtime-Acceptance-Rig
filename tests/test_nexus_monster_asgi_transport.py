from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI, Request

from live_runtime_rig_nexus_monster.runtime_adapter import _InProcessASGIClient


def test_monster_asgi_client_executes_real_in_process_http_request() -> None:
    app = FastAPI()

    @app.post("/v1/chat/completions")
    async def chat(request: Request):
        payload = await request.json()
        return {
            "ok": True,
            "principal": request.headers.get("X-Nexus-Rig-Principal"),
            "payload": payload,
        }

    client = _InProcessASGIClient(app)
    response = client.post(
        "/v1/chat/completions",
        headers={"X-Nexus-Rig-Principal": "primary"},
        json={"messages": [{"role": "user", "content": "ping"}]},
    )

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "principal": "primary",
        "payload": {"messages": [{"role": "user", "content": "ping"}]},
    }


def test_monster_asgi_client_does_not_depend_on_httpx_client_app_keyword(monkeypatch) -> None:
    """Reproduce the exact Starlette/HTTPX incompatibility without using TestClient.

    The accepted runtime lock has Starlette 0.35.1 + HTTPX 0.28.1. Old
    Starlette TestClient forwards app= to httpx.Client, but HTTPX 0.28 rejects
    it. Make that path explode explicitly and prove the monster transport never
    touches it.
    """

    original_init = httpx.Client.__init__

    def rejecting_init(self, *args, **kwargs):
        if "app" in kwargs:
            raise TypeError("Client.__init__() got an unexpected keyword argument 'app'")
        return original_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "__init__", rejecting_init)

    app = FastAPI()

    @app.post("/probe")
    async def probe():
        return {"transport": "asgi"}

    client = _InProcessASGIClient(app)
    response = client.post("/probe")
    assert response.status_code == 200
    assert response.json() == {"transport": "asgi"}


def test_monster_asgi_client_fails_closed_after_close() -> None:
    app = FastAPI()
    client = _InProcessASGIClient(app)
    client.close()

    with pytest.raises(RuntimeError, match="client is closed"):
        client.post("/anything")
