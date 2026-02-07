from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from src.shared.middleware import SecuritySettings, create_app


def _build_app(settings: SecuritySettings) -> FastAPI:
    app = create_app(security_settings=settings)

    @app.get("/ping")
    async def ping() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/debug/headers")
    async def header_debug(request: Request) -> dict[str, int]:
        return {"count": len(request.scope.get("headers", []))}

    @app.post("/echo")
    async def echo(request: Request) -> JSONResponse:
        payload = await request.body()
        return JSONResponse({"size": len(payload)})

    return app


def test_security_headers_include_hsts_when_enabled():
    settings = SecuritySettings(
        rate_limit_requests=5,
        rate_limit_window=60,
        max_body_size=1024,
        enable_https=True,
    )
    client = TestClient(_build_app(settings))

    response = client.get("/ping")

    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Content-Security-Policy"] == "default-src 'self'"
    assert "Strict-Transport-Security" in response.headers


def test_security_headers_skip_hsts_when_disabled():
    settings = SecuritySettings(
        rate_limit_requests=5,
        rate_limit_window=60,
        max_body_size=1024,
        enable_https=False,
    )
    client = TestClient(_build_app(settings))

    response = client.get("/ping")

    assert "Strict-Transport-Security" not in response.headers


def test_rate_limiting_blocks_after_threshold():
    settings = SecuritySettings(
        rate_limit_requests=2,
        rate_limit_window=60,
        max_body_size=1024,
        enable_https=False,
    )
    client = TestClient(_build_app(settings))

    assert client.get("/ping").status_code == 200
    assert client.get("/ping").status_code == 200
    third = client.get("/ping")
    assert third.status_code == 429
    assert third.json()["detail"] == "Too Many Requests"


def test_body_size_limit_enforced():
    settings = SecuritySettings(
        rate_limit_requests=5,
        rate_limit_window=60,
        max_body_size=10,
        enable_https=False,
    )
    client = TestClient(_build_app(settings))

    small_payload = b"12345"
    assert client.post("/echo", data=small_payload).json()["size"] == len(small_payload)

    large_payload = b"x" * 64
    response = client.post("/echo", data=large_payload)
    assert response.status_code == 413
    assert response.json()["detail"] == "Request body too large"


def test_https_redirect_uses_canonical_host_when_configured(monkeypatch):
    monkeypatch.setenv("SECURITY_HTTPS_REDIRECT_CANONICAL_HOST", "example.com")
    settings = SecuritySettings(
        rate_limit_requests=5,
        rate_limit_window=60,
        max_body_size=1024,
        enable_https=True,
    )
    client = TestClient(_build_app(settings))

    response = client.get(
        "/ping", headers={"host": "evil.test"}, follow_redirects=False
    )

    assert response.status_code == 307
    assert response.headers["location"].startswith("https://example.com/ping")


def test_https_redirect_uses_allowlist_when_configured(monkeypatch):
    monkeypatch.setenv("SECURITY_HTTPS_REDIRECT_ALLOWED_HOSTS", "good.test")
    settings = SecuritySettings(
        rate_limit_requests=5,
        rate_limit_window=60,
        max_body_size=1024,
        enable_https=True,
    )
    client = TestClient(_build_app(settings))

    response = client.get(
        "/ping", headers={"host": "evil.test"}, follow_redirects=False
    )

    assert response.status_code == 307
    assert response.headers["location"].startswith("https://good.test/ping")


def test_request_target_limit_rejects_long_paths(monkeypatch):
    monkeypatch.setenv("SECURITY_MAX_PATH_LENGTH", "10")
    settings = SecuritySettings(
        rate_limit_requests=5,
        rate_limit_window=60,
        max_body_size=1024,
        enable_https=False,
    )
    client = TestClient(_build_app(settings))

    response = client.get("/" + ("a" * 64))
    assert response.status_code == 414
    assert response.json()["detail"] == "Request-URI too long"


def test_request_target_limit_rejects_long_query_strings(monkeypatch):
    monkeypatch.setenv("SECURITY_MAX_QUERY_STRING_LENGTH", "10")
    settings = SecuritySettings(
        rate_limit_requests=5,
        rate_limit_window=60,
        max_body_size=1024,
        enable_https=False,
    )
    client = TestClient(_build_app(settings))

    response = client.get("/ping?x=" + ("a" * 64))
    assert response.status_code == 414
    assert response.json()["detail"] == "Request-URI too long"


def test_request_target_limit_rejects_many_headers(monkeypatch):
    # Establish the baseline header count with a permissive configuration.
    monkeypatch.setenv("SECURITY_MAX_HEADER_COUNT", "1000")
    settings = SecuritySettings(
        rate_limit_requests=5,
        rate_limit_window=60,
        max_body_size=1024,
        enable_https=False,
    )
    baseline_client = TestClient(_build_app(settings))
    baseline = baseline_client.get("/debug/headers").json()["count"]

    monkeypatch.setenv("SECURITY_MAX_HEADER_COUNT", str(baseline + 1))
    limited_client = TestClient(_build_app(settings))
    response = limited_client.get(
        "/ping",
        headers={"x-a": "1", "x-b": "2", "x-c": "3"},
    )
    assert response.status_code == 431
    assert response.json()["detail"] == "Request header fields too large"


def test_request_target_limit_rejects_large_header_values(monkeypatch):
    monkeypatch.setenv("SECURITY_MAX_HEADER_VALUE_LENGTH", "64")
    settings = SecuritySettings(
        rate_limit_requests=5,
        rate_limit_window=60,
        max_body_size=1024,
        enable_https=False,
    )
    client = TestClient(_build_app(settings))

    response = client.get("/ping", headers={"x-test": "a" * 256})
    assert response.status_code == 431
    assert response.json()["detail"] == "Request header fields too large"
