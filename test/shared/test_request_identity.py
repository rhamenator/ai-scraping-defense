from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from src.shared.request_identity import resolve_request_identity, resolve_request_scheme


def _build_identity_app() -> FastAPI:
    app = FastAPI()

    @app.get("/identity")
    async def identity(request: Request) -> dict[str, str | bool | None]:
        resolved = resolve_request_identity(request)
        return {
            "client_ip": resolved.client_ip,
            "peer_ip": resolved.peer_ip,
            "via_trusted_proxy": resolved.via_trusted_proxy,
            "via_trusted_cdn": resolved.via_trusted_cdn,
            "source_header": resolved.source_header,
            "scheme": resolve_request_scheme(request),
        }

    return app


def test_resolve_request_identity_uses_cloudflare_header_for_trusted_cdn(monkeypatch):
    monkeypatch.setenv("CLOUD_CDN_PROVIDER", "cloudflare")
    monkeypatch.setenv("SECURITY_CDN_TRUSTED_PROXY_CIDRS", "127.0.0.0/8")

    client = TestClient(_build_identity_app(), client=("127.0.0.1", 45000))

    response = client.get(
        "/identity",
        headers={
            "CF-Connecting-IP": "203.0.113.24",
            "X-Forwarded-Proto": "https",
            "X-Forwarded-For": "198.51.100.50",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "client_ip": "203.0.113.24",
        "peer_ip": "127.0.0.1",
        "via_trusted_proxy": True,
        "via_trusted_cdn": True,
        "source_header": "cf-connecting-ip",
        "scheme": "https",
    }


def test_resolve_request_identity_ignores_spoofed_cdn_headers(monkeypatch):
    monkeypatch.delenv("SECURITY_CDN_TRUSTED_PROXY_CIDRS", raising=False)
    monkeypatch.delenv("SECURITY_TRUSTED_PROXY_CIDRS", raising=False)

    client = TestClient(_build_identity_app(), client=("198.51.100.10", 45000))

    response = client.get(
        "/identity",
        headers={
            "CF-Connecting-IP": "203.0.113.24",
            "X-Forwarded-Proto": "https",
            "X-Forwarded-For": "198.51.100.50",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "client_ip": "198.51.100.10",
        "peer_ip": "198.51.100.10",
        "via_trusted_proxy": False,
        "via_trusted_cdn": False,
        "source_header": None,
        "scheme": "http",
    }


def test_resolve_request_identity_uses_forwarded_for_for_trusted_proxy(monkeypatch):
    monkeypatch.setenv("SECURITY_TRUSTED_PROXY_CIDRS", "127.0.0.0/8")

    client = TestClient(_build_identity_app(), client=("127.0.0.1", 45000))

    response = client.get(
        "/identity",
        headers={
            "X-Forwarded-For": "198.51.100.50, 127.0.0.1",
            "X-Forwarded-Proto": "https",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "client_ip": "198.51.100.50",
        "peer_ip": "127.0.0.1",
        "via_trusted_proxy": True,
        "via_trusted_cdn": False,
        "source_header": "x-forwarded-for",
        "scheme": "https",
    }
