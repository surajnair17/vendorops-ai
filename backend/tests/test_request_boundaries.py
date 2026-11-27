import asyncio

from backend.config import settings
from backend.middleware import RequestBoundaryMiddleware


def test_host_and_origin_protection(client):
    assert client.get("/health", headers={"Host": "attacker.example"}).status_code == 400
    response = client.post("/api/v1/documents", headers={"Origin": "https://attacker.example"})
    assert response.status_code == 403
    assert client.get("/health", headers={"Origin": "http://testserver"}).status_code == 200
    assert client.get("/health").headers["cache-control"] == "no-store"


def test_unknown_routes_and_methods_use_the_error_contract(client):
    assert client.get("/api/v1/missing").json()["error"]["code"] == "not_found"
    response = client.post("/health")
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"


def test_declared_and_streamed_body_limits_precede_parsing(client, monkeypatch):
    monkeypatch.setattr(settings, "max_json_bytes", 20)
    for content in (b"x" * 21, iter([b"x" * 10, b"y" * 11])):
        response = client.post(
            "/api/v1/policies", content=content, headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "request_too_large"
    assert client.get("/api/v1/policies").json() == []


def test_slow_body_returns_timeout_without_entering_app(monkeypatch):
    monkeypatch.setattr(settings, "upload_timeout_seconds", 0.01)
    messages = []

    async def unreachable(*args):
        raise AssertionError("Request must be rejected before parsing")

    async def receive():
        await asyncio.sleep(10)

    async def send(message):
        messages.append(message)

    asyncio.run(
        RequestBoundaryMiddleware(unreachable)(
            {"type": "http", "scheme": "http", "headers": [(b"host", b"localhost")]}, receive, send
        )
    )
    assert messages[0]["status"] == 408
