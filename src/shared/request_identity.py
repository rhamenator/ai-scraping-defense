"""Trusted proxy and CDN-aware request identity helpers."""

from __future__ import annotations

import ipaddress
import os
import re
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

    @property
    def activity_key(self) -> str:
        """Return a non-actionable key for rate limits and audit correlation."""

        if self.client_ip != "unknown":
            return self.client_ip
        if self.peer_ip:
            return f"unknown-via-{self.peer_ip}"
        return "unknown"


@dataclass(frozen=True)
class TlsFingerprint:
    """Validated TLS client fingerprints supplied by trusted infrastructure."""

    ja3: str | None = None
    ja4: str | None = None
    source: str | None = None


_JA3_PATTERN = re.compile(r"^[0-9a-f]{32}$")
_JA4_PATTERN = re.compile(r"^[a-z0-9]{10}_[0-9a-f]{12}_[0-9a-f]{12}$")


def normalize_ja3(value: str | None) -> str | None:
    """Normalize a standard JA3 MD5 digest, rejecting malformed input."""

    candidate = (value or "").strip().lower()
    return candidate if _JA3_PATTERN.fullmatch(candidate) else None


def normalize_ja4(value: str | None) -> str | None:
    """Normalize the canonical JA4 ``a_b_c`` value, rejecting raw variants."""

    candidate = (value or "").strip().lower()
    return candidate if _JA4_PATTERN.fullmatch(candidate) else None


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


def is_trusted_infrastructure_ip(candidate: str) -> bool:
    """Return whether an address belongs to a configured proxy/CDN trust range."""

    networks = [
        *_parse_trusted_proxy_networks("SECURITY_TRUSTED_PROXY_CIDRS"),
        *_parse_trusted_proxy_networks("SECURITY_CDN_TRUSTED_PROXY_CIDRS"),
    ]
    return _request_from_trusted_network(candidate, networks)


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


def _resolve_forwarded_chain(
    value: str | None,
    trusted_networks: list[TrustedProxyNetwork],
) -> str | None:
    if not value:
        return None
    parsed: list[str] = []
    for candidate in value.split(","):
        try:
            parsed.append(str(ipaddress.ip_address(candidate.strip())))
        except ValueError:
            continue
    for candidate in reversed(parsed):
        if not _request_from_trusted_network(candidate, trusted_networks):
            return candidate
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
            if header_name == "x-forwarded-for":
                resolved_ip = _resolve_forwarded_chain(
                    request.headers.get(header_name),
                    [*trusted_proxy_networks, *trusted_cdn_networks],
                )
            else:
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
        forwarded_for = _resolve_forwarded_chain(
            request.headers.get("x-forwarded-for"),
            [*trusted_proxy_networks, *trusted_cdn_networks],
        )
        if forwarded_for:
            return RequestIdentity(
                client_ip=forwarded_for,
                peer_ip=peer_ip,
                via_trusted_proxy=True,
                via_trusted_cdn=via_trusted_cdn,
                source_header="x-forwarded-for",
            )

        # Never reinterpret an infrastructure peer as the originating client
        # merely because its forwarded identity header is absent or malformed.
        return RequestIdentity(
            client_ip="unknown",
            peer_ip=peer_ip,
            via_trusted_proxy=True,
            via_trusted_cdn=via_trusted_cdn,
            source_header=None,
        )

    return RequestIdentity(
        client_ip=peer_ip or "unknown",
        peer_ip=peer_ip,
        via_trusted_proxy=False,
        via_trusted_cdn=False,
        source_header=None,
    )


def resolve_tls_fingerprint(
    request: Request, identity: RequestIdentity | None = None
) -> TlsFingerprint:
    """Read TLS fingerprints only from the infrastructure that observed TLS."""

    resolved_identity = identity or resolve_request_identity(request)
    if resolved_identity.via_trusted_cdn:
        ja3 = normalize_ja3(request.headers.get("cf-ja3-hash"))
        ja4 = normalize_ja4(request.headers.get("cf-ja4"))
        return TlsFingerprint(
            ja3=ja3,
            ja4=ja4,
            source="cloudflare" if ja3 or ja4 else None,
        )
    if resolved_identity.via_trusted_proxy:
        ja3 = normalize_ja3(request.headers.get("x-asd-tls-ja3"))
        ja4 = normalize_ja4(request.headers.get("x-asd-tls-ja4"))
        return TlsFingerprint(
            ja3=ja3,
            ja4=ja4,
            source="envoy" if ja3 or ja4 else None,
        )
    return TlsFingerprint()


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
