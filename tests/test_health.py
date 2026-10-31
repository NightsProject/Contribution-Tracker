import asyncio

import httpx

from app.main import app


def request(path: str) -> httpx.Response:
    async def get_response() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            return await client.get(path)

    return asyncio.run(get_response())


def test_health_endpoint() -> None:
    response = request("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_reports_foundation_status() -> None:
    response = request("/")

    assert response.status_code == 200
    assert response.json() == {
        "name": "Contribution & Expense Tracker",
        "status": "foundation",
    }
