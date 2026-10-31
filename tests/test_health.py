def test_health_endpoint(client) -> None:
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "script-src 'none'" in response.headers["content-security-policy"]
    assert "style-src 'self'" in response.headers["content-security-policy"]
    assert "'unsafe-inline'" not in response.headers["content-security-policy"]
    assert "strict-transport-security" not in response.headers


def test_secure_cookie_configuration_enables_hsts(client, monkeypatch) -> None:
    from app.config import Settings
    import app.main as main

    monkeypatch.setattr(
        main,
        "get_settings",
        lambda: Settings(session_cookie_secure=True),
    )

    response = client.get("/healthz")

    assert response.headers["strict-transport-security"] == "max-age=31536000; includeSubDomains"


def test_root_redirects_to_dashboard(client) -> None:
    response = client.get("/")

    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"


def test_shared_stylesheet_is_served_with_css_content_type(client) -> None:
    response = client.get("/static/app.css")

    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]
    assert "prefers-reduced-motion" in response.text
