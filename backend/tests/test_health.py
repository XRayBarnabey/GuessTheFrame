from __future__ import annotations

from httpx import AsyncClient


async def test_health_returns_ok(client: AsyncClient) -> None:
    response = await client.get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["database"] == "ok"
    assert payload["app"] == "GuessTheFrame"
    assert "api_key" not in response.text.lower()
    assert "token" not in response.text.lower()


async def test_unknown_api_route_is_not_spa(client: AsyncClient) -> None:
    response = await client.get("/api/does-not-exist")

    assert response.status_code == 404
    assert response.json()["error"]["code"] in {"HTTP_ERROR", "NOT_FOUND"}
