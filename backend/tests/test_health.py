from httpx import AsyncClient


async def test_health_reports_api_is_ready(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "api"}
