from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from src.shared.request_identity import (
    is_trusted_infrastructure_ip,
    resolve_request_identity,
    resolve_request_scheme,
    resolve_tls_fingerprint,
)

JA3 = "72a589da586844d7f0818ce684948eea"
JA4 = "t13d1516h2_8daaf6152771_e5627efa2ab1"


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


def test_resolve_request_identity_ignores_spoofed_leftmost_forwarded_entry(monkeypatch):
    monkeypatch.setenv("SECURITY_TRUSTED_PROXY_CIDRS", "127.0.0.0/8")
    client = TestClient(_build_identity_app(), client=("127.0.0.1", 45000))

    response = client.get(
        "/identity",
        headers={"X-Forwarded-For": "192.0.2.99, 198.51.100.50, 127.0.0.2"},
    )

    assert response.status_code == 200
    assert response.json()["client_ip"] == "198.51.100.50"


def test_trusted_cloudflare_edge_is_never_a_block_target(monkeypatch):
    monkeypatch.setenv("SECURITY_CDN_TRUSTED_PROXY_CIDRS", "173.245.48.0/20")
    assert is_trusted_infrastructure_ip("173.245.48.10")
    assert not is_trusted_infrastructure_ip("198.51.100.10")


def test_tls_fingerprint_accepts_cloudflare_headers_only_from_trusted_cdn(monkeypatch):
    monkeypatch.setenv("SECURITY_CDN_TRUSTED_PROXY_CIDRS", "173.245.48.0/20")
    request = Request(
        {
            "type": "http",
            "scheme": "https",
            "server": ("example.test", 443),
            "client": ("173.245.48.10", 45000),
            "headers": [
                (b"cf-connecting-ip", b"198.51.100.7"),
                (b"cf-ja3-hash", JA3.upper().encode()),
                (b"cf-ja4", JA4.upper().encode()),
            ],
        }
    )
    fingerprint = resolve_tls_fingerprint(request)

    assert fingerprint.ja3 == JA3
    assert fingerprint.ja4 == JA4
    assert fingerprint.source == "cloudflare"


def test_tls_fingerprint_ignores_direct_client_spoofing(monkeypatch):
    monkeypatch.delenv("SECURITY_CDN_TRUSTED_PROXY_CIDRS", raising=False)
    monkeypatch.delenv("SECURITY_TRUSTED_PROXY_CIDRS", raising=False)
    request = Request(
        {
            "type": "http",
            "scheme": "https",
            "server": ("example.test", 443),
            "client": ("198.51.100.7", 44321),
            "headers": [
                (b"cf-ja3-hash", JA3.encode()),
                (b"x-asd-tls-ja4", JA4.encode()),
            ],
        }
    )

    assert resolve_tls_fingerprint(request).source is None


def test_tls_fingerprint_rejects_malformed_collector_values(monkeypatch):
    monkeypatch.setenv("SECURITY_TRUSTED_PROXY_CIDRS", "10.0.0.0/8")
    request = Request(
        {
            "type": "http",
            "scheme": "https",
            "server": ("example.test", 443),
            "client": ("10.0.0.2", 44321),
            "headers": [
                (b"x-asd-tls-ja3", b"not-a-ja3"),
                (b"x-asd-tls-ja4", b"not-a-ja4"),
            ],
        }
    )

    fingerprint = resolve_tls_fingerprint(request)
    assert fingerprint.ja3 is None
    assert fingerprint.ja4 is None
    assert fingerprint.source is None
