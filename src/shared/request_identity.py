"""Trusted proxy and CDN-aware request identity helpers."""

from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass

from starlette.requests import Request

TrustedProxyNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network

_DEFAULT_CLOUDFLARE_HEADERS = (
    "cf-connecting-ip",
    "true-client-ip",
    "x-forwarded-for",
)
_DEFAULT_PROXY_HEADERS = ("x-forwarded-for",)


@dataclass(frozen=True)
class RequestIdentity:
    """Resolved client identity for a request crossing proxy boundaries."""

    client_ip: str
    peer_ip: str | None
    via_trusted_proxy: bool
    via_trusted_cdn: bool
    source_header: str | None = None


def _parse_trusted_proxy_networks(name: str) -> list[TrustedProxyNetwork]:
    raw = os.getenv(name, "")
    networks: list[TrustedProxyNetwork] = []
    for entry in raw.split(","):
        candidate = entry.strip()
        if not candidate:
            continue
        try:
            networks.append(ipaddress.ip_network(candidate, strict=False))
        except ValueError as exc:
            raise ValueError(
                f"Environment variable {name} contains invalid proxy network {candidate!r}"
            ) from exc
    return networks


def _request_from_trusted_network(
    peer_ip: str | None, trusted_networks: list[TrustedProxyNetwork]
) -> bool:
    if not trusted_networks or not peer_ip:
        return False
    try:
        client_ip = ipaddress.ip_address(peer_ip)
    except ValueError:
        return False
    return any(client_ip in network for network in trusted_networks)


def _candidate_client_headers() -> tuple[str, ...]:
    configured = os.getenv("SECURITY_CDN_CLIENT_IP_HEADERS", "")
    if configured.strip():
        names = tuple(
            header.strip().lower() for header in configured.split(",") if header.strip()
        )
        if names:
            return names

    provider = (os.getenv("CLOUD_CDN_PROVIDER") or "").strip().lower()
    if provider == "cloudflare":
        return _DEFAULT_CLOUDFLARE_HEADERS
    return _DEFAULT_PROXY_HEADERS


def _first_valid_ip(value: str | None) -> str | None:
    if not value:
        return None
    for candidate in value.split(","):
        ip_text = candidate.strip()
        if not ip_text:
            continue
        try:
            return str(ipaddress.ip_address(ip_text))
        except ValueError:
            continue
    return None


def resolve_request_identity(request: Request) -> RequestIdentity:
    """Resolve the real client IP through trusted proxies and CDNs only."""

    peer_ip = request.client.host if request.client else None
    trusted_proxy_networks = _parse_trusted_proxy_networks(
        "SECURITY_TRUSTED_PROXY_CIDRS"
    )
    trusted_cdn_networks = _parse_trusted_proxy_networks(
        "SECURITY_CDN_TRUSTED_PROXY_CIDRS"
    )

    via_trusted_cdn = _request_from_trusted_network(peer_ip, trusted_cdn_networks)
    via_trusted_proxy = via_trusted_cdn or _request_from_trusted_network(
        peer_ip, trusted_proxy_networks
    )

    if via_trusted_cdn:
        for header_name in _candidate_client_headers():
            resolved_ip = _first_valid_ip(request.headers.get(header_name))
            if resolved_ip:
                return RequestIdentity(
                    client_ip=resolved_ip,
                    peer_ip=peer_ip,
                    via_trusted_proxy=True,
                    via_trusted_cdn=True,
                    source_header=header_name,
                )

    if via_trusted_proxy:
        forwarded_for = _first_valid_ip(request.headers.get("x-forwarded-for"))
        if forwarded_for:
            return RequestIdentity(
                client_ip=forwarded_for,
                peer_ip=peer_ip,
                via_trusted_proxy=True,
                via_trusted_cdn=via_trusted_cdn,
                source_header="x-forwarded-for",
            )

    return RequestIdentity(
        client_ip=peer_ip or "unknown",
        peer_ip=peer_ip,
        via_trusted_proxy=False,
        via_trusted_cdn=False,
        source_header=None,
    )


def resolve_request_scheme(request: Request) -> str:
    """Resolve the effective request scheme for trusted proxy traffic."""

    identity = resolve_request_identity(request)
    if identity.via_trusted_proxy:
        forwarded = request.headers.get("x-forwarded-proto")
        if forwarded:
            scheme = forwarded.split(",")[0].strip().lower()
            if scheme:
                return scheme
    return request.url.scheme
