def test_health_endpoint(client) -> None:
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_redirects_to_dashboard(client) -> None:
    response = client.get("/")

    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"
