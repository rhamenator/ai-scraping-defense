#!/usr/bin/env python3
"""Deterministic and guarded HTTP attack-regression probes."""

from __future__ import annotations

import argparse
import json
import ssl
import sys
import urllib.parse
from dataclasses import dataclass
from http.client import HTTPConnection, HTTPSConnection

REDIRECT_STATUSES = {301, 302, 307, 308}
SECURITY_HEADERS = {
    "content-security-policy",
    "permissions-policy",
    "referrer-policy",
    "x-content-type-options",
    "x-frame-options",
}
WAF_BLOCK_STATUSES = {403, 406, 429, 431}
WEBSOCKET_REJECTION_STATUSES = {400, 401, 403, 426}


class RequestCapExceeded(RuntimeError):
    """Raised when a profile exceeds its allowed outbound request budget."""


@dataclass(frozen=True)
class AttackProfile:
    name: str
    mode: str
    version: int
    checks: tuple[str, ...]
    default_max_requests: int


PROFILES = {
    profile.name: profile
    for profile in (
        AttackProfile(
            name="compose-v1",
            mode="compose",
            version=1,
            checks=(
                "nginx_https_redirect",
                "nginx_security_headers",
                "admin_ui_spoofed_forwarded_proto_redirect",
                "admin_ui_missing_auth_rejected",
                "admin_ui_websocket_missing_auth_rejected",
                "admin_ui_large_header_rejected",
                "admin_ui_large_body_rejected",
                "prompt_router_rate_limit",
            ),
            default_max_requests=13,
        ),
        AttackProfile(
            name="staging-v1",
            mode="staging",
            version=1,
            checks=(
                "nginx_https_redirect",
                "nginx_security_headers",
                "admin_ui_spoofed_forwarded_proto_redirect",
                "admin_ui_missing_auth_rejected",
                "admin_ui_websocket_missing_auth_rejected",
                "admin_ui_large_header_rejected",
                "admin_ui_large_body_rejected",
                "edge_waf_payload_rejected",
            ),
            default_max_requests=10,
        ),
        AttackProfile(
            name="kali-v1",
            mode="kali",
            version=1,
            checks=(
                "nginx_https_redirect",
                "nginx_security_headers",
                "admin_ui_spoofed_forwarded_proto_redirect",
                "admin_ui_missing_auth_rejected",
                "admin_ui_websocket_missing_auth_rejected",
                "admin_ui_large_header_rejected",
                "admin_ui_large_body_rejected",
                "edge_waf_payload_rejected",
            ),
            default_max_requests=10,
        ),
    )
}


def _validate_base_url(base_url: str) -> str:
    parsed = urllib.parse.urlparse(base_url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("base URL must use http:// or https://")
    if not parsed.netloc:
        raise ValueError("base URL must include a host")
    return urllib.parse.urlunparse(parsed._replace(fragment=""))


def _normalize_host(host: str) -> str:
    return host.strip().lower()


def _validate_allowed_hosts(urls: list[str], allowed_hosts: list[str]) -> list[str]:
    if not allowed_hosts:
        raise ValueError("at least one --allow-host entry is required")
    allowed = {_normalize_host(host) for host in allowed_hosts}
    denied = []
    for url in urls:
        parsed = urllib.parse.urlparse(url)
        host = _normalize_host(parsed.hostname or "")
        if host not in allowed:
            denied.append(host)
    return sorted(set(denied))


def _request(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    data: bytes | None = None,
    timeout: float = 10.0,
    verify_tls: bool = True,
) -> tuple[int, dict[str, str], bytes]:
    parsed = urllib.parse.urlparse(url)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"

    kwargs: dict[str, object] = {"timeout": timeout}
    if parsed.scheme == "https" and not verify_tls:
        kwargs["context"] = ssl._create_unverified_context()
    conn_cls = HTTPSConnection if parsed.scheme == "https" else HTTPConnection
    conn = conn_cls(parsed.hostname, port, **kwargs)
    try:
        conn.request(method, path, body=data, headers=headers or {})
        response = conn.getresponse()
        body = response.read(1024 * 1024)
        response_headers = {k.lower(): v for k, v in response.getheaders()}
        return response.status, response_headers, body
    finally:
        conn.close()


def _websocket_handshake_status(
    url: str, *, timeout: float = 10.0, verify_tls: bool = True
) -> int:
    headers = {
        "Connection": "Upgrade",
        "Upgrade": "websocket",
        "Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ==",
        "Sec-WebSocket-Version": "13",
    }
    status, _, _ = _request(
        url,
        method="GET",
        headers=headers,
        timeout=timeout,
        verify_tls=verify_tls,
    )
    return status


def _join(base_url: str, path: str) -> str:
    return base_url.rstrip("/") + (path if path.startswith("/") else f"/{path}")


def _missing_security_headers(headers: dict[str, str]) -> list[str]:
    return sorted(header for header in SECURITY_HEADERS if header not in headers)


def _is_https_redirect(status: int, headers: dict[str, str]) -> bool:
    location = headers.get("location", "")
    parsed = urllib.parse.urlparse(location)
    return status in REDIRECT_STATUSES and parsed.scheme == "https"


def _prompt_rate_limit_ok(statuses: list[int]) -> bool:
    if not statuses or 429 not in statuses:
        return False
    limit_index = statuses.index(429)
    prior_statuses = statuses[:limit_index]
    if not prior_statuses:
        return False
    if any(status >= 500 or status in {0, 401} for status in prior_statuses):
        return False
    return True


def _waf_payload_rejected(status: int) -> bool:
    return status in WAF_BLOCK_STATUSES


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--profile",
        choices=sorted(PROFILES),
        default="compose-v1",
        help="Bounded attack profile to execute.",
    )
    parser.add_argument("--nginx-http-base", required=True)
    parser.add_argument("--nginx-https-base", required=True)
    parser.add_argument("--admin-ui-base", required=True)
    parser.add_argument("--prompt-router-base")
    parser.add_argument("--prompt-shared-secret")
    parser.add_argument("--prompt-rate-limit-count", type=int, default=6)
    parser.add_argument(
        "--allow-host",
        action="append",
        default=[],
        help="Explicitly allow a target host for bounded attack simulation.",
    )
    parser.add_argument(
        "--max-requests",
        type=int,
        help="Maximum number of outbound requests permitted for this run.",
    )
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--json", dest="json_output", action="store_true")
    parser.add_argument(
        "--output-path",
        help="Optional file path for writing the structured JSON report.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    profile = PROFILES[args.profile]

    try:
        nginx_http_base = _validate_base_url(args.nginx_http_base)
        nginx_https_base = _validate_base_url(args.nginx_https_base)
        admin_ui_base = _validate_base_url(args.admin_ui_base)
        prompt_router_base = (
            _validate_base_url(args.prompt_router_base)
            if args.prompt_router_base
            else None
        )
        denied_hosts = _validate_allowed_hosts(
            [
                nginx_http_base,
                nginx_https_base,
                admin_ui_base,
                *([prompt_router_base] if prompt_router_base else []),
            ],
            args.allow_host,
        )
        if denied_hosts:
            raise ValueError(
                "target hosts are not allowlisted: " + ", ".join(denied_hosts)
            )
    except ValueError as exc:
        print(f"[attack-regression] invalid input: {exc}", file=sys.stderr)
        return 2

    max_requests = args.max_requests or profile.default_max_requests
    if max_requests <= 0:
        print(
            "[attack-regression] invalid input: --max-requests must be positive",
            file=sys.stderr,
        )
        return 2

    request_budget = {"used": 0, "limit": max_requests}
    results: dict[str, object] = {
        "profile": {
            "name": profile.name,
            "mode": profile.mode,
            "version": profile.version,
        },
        "targets": {
            "nginx_http_base": nginx_http_base,
            "nginx_https_base": nginx_https_base,
            "admin_ui_base": admin_ui_base,
            "prompt_router_base": prompt_router_base,
            "allow_hosts": sorted({_normalize_host(host) for host in args.allow_host}),
        },
        "request_budget": {"limit": max_requests, "used": 0},
        "checks": [],
    }
    failures: list[str] = []

    def record(name: str, ok: bool, detail: dict[str, object]) -> None:
        payload = {"name": name, "ok": ok, **detail}
        results["checks"].append(payload)
        if not ok:
            failures.append(name)

    def perform_request(*request_args, **request_kwargs):
        if request_budget["used"] >= request_budget["limit"]:
            raise RequestCapExceeded("request cap exceeded")
        request_budget["used"] += 1
        results["request_budget"]["used"] = request_budget["used"]
        return _request(*request_args, **request_kwargs)

    def perform_websocket_probe(url: str, *, timeout: float, verify_tls: bool) -> int:
        if request_budget["used"] >= request_budget["limit"]:
            raise RequestCapExceeded("request cap exceeded")
        request_budget["used"] += 1
        results["request_budget"]["used"] = request_budget["used"]
        return _websocket_handshake_status(
            url,
            timeout=timeout,
            verify_tls=verify_tls,
        )

    if "nginx_https_redirect" in profile.checks:
        try:
            status, headers, _ = perform_request(
                _join(nginx_http_base, "/"),
                headers={"X-Enable-Https": "true"},
                timeout=args.timeout,
            )
            record(
                "nginx_https_redirect",
                _is_https_redirect(status, headers),
                {"status": status, "location": headers.get("location", "")},
            )
        except Exception as exc:
            record("nginx_https_redirect", False, {"error": str(exc)})

    if "nginx_security_headers" in profile.checks:
        try:
            status, headers, _ = perform_request(
                _join(nginx_https_base, "/"),
                timeout=args.timeout,
                verify_tls=False,
            )
            missing = _missing_security_headers(headers)
            record(
                "nginx_security_headers",
                status < 500 and not missing,
                {"status": status, "missing_security_headers": missing},
            )
        except Exception as exc:
            record("nginx_security_headers", False, {"error": str(exc)})

    if "admin_ui_spoofed_forwarded_proto_redirect" in profile.checks:
        try:
            status, headers, _ = perform_request(
                _join(admin_ui_base, "/observability/health"),
                headers={"X-Forwarded-Proto": "https"},
                timeout=args.timeout,
            )
            record(
                "admin_ui_spoofed_forwarded_proto_redirect",
                _is_https_redirect(status, headers),
                {"status": status, "location": headers.get("location", "")},
            )
        except Exception as exc:
            record(
                "admin_ui_spoofed_forwarded_proto_redirect",
                False,
                {"error": str(exc)},
            )

    if "admin_ui_missing_auth_rejected" in profile.checks:
        try:
            status, _, _ = perform_request(
                _join(admin_ui_base, "/"),
                timeout=args.timeout,
            )
            record(
                "admin_ui_missing_auth_rejected",
                status == 401,
                {"status": status},
            )
        except Exception as exc:
            record("admin_ui_missing_auth_rejected", False, {"error": str(exc)})

    if "admin_ui_websocket_missing_auth_rejected" in profile.checks:
        try:
            status = perform_websocket_probe(
                _join(admin_ui_base, "/ws/metrics"),
                timeout=args.timeout,
                verify_tls=False,
            )
            record(
                "admin_ui_websocket_missing_auth_rejected",
                status in WEBSOCKET_REJECTION_STATUSES,
                {"status": status},
            )
        except Exception as exc:
            record(
                "admin_ui_websocket_missing_auth_rejected",
                False,
                {"error": str(exc)},
            )

    if "admin_ui_large_header_rejected" in profile.checks:
        try:
            status, _, _ = perform_request(
                _join(admin_ui_base, "/observability/health"),
                headers={"X-Probe": "a" * 9000},
                timeout=args.timeout,
            )
            record("admin_ui_large_header_rejected", status == 431, {"status": status})
        except Exception as exc:
            record("admin_ui_large_header_rejected", False, {"error": str(exc)})

    if "admin_ui_large_body_rejected" in profile.checks:
        try:
            status, _, _ = perform_request(
                _join(admin_ui_base, "/"),
                method="POST",
                headers={
                    "Content-Type": "application/octet-stream",
                    "Content-Length": str(1024 * 1024 + 1),
                },
                data=b"a" * (1024 * 1024 + 1),
                timeout=args.timeout,
            )
            record("admin_ui_large_body_rejected", status == 413, {"status": status})
        except Exception as exc:
            record("admin_ui_large_body_rejected", False, {"error": str(exc)})

    if "prompt_router_rate_limit" in profile.checks:
        if prompt_router_base and args.prompt_shared_secret:
            statuses: list[int] = []
            for _ in range(max(args.prompt_rate_limit_count, 2)):
                try:
                    status, _, _ = perform_request(
                        _join(prompt_router_base, "/route"),
                        method="POST",
                        headers={
                            "Authorization": f"Bearer {args.prompt_shared_secret}",
                            "Content-Type": "application/json",
                        },
                        data=json.dumps({"prompt": "hi", "input": "hi"}).encode(),
                        timeout=args.timeout,
                    )
                except RequestCapExceeded as exc:
                    record(
                        "prompt_router_rate_limit",
                        False,
                        {
                            "error": str(exc),
                            "statuses": statuses,
                        },
                    )
                    break
                except Exception:
                    status = 0
                else:
                    statuses.append(status)
            else:
                record(
                    "prompt_router_rate_limit",
                    _prompt_rate_limit_ok(statuses),
                    {"statuses": statuses},
                )
        else:
            record(
                "prompt_router_rate_limit",
                False,
                {"error": "prompt router base and shared secret are required"},
            )

    if "edge_waf_payload_rejected" in profile.checks:
        try:
            status, _, _ = perform_request(
                _join(
                    nginx_https_base,
                    "/?probe=%3Cscript%3Ealert%281%29%3C%2Fscript%3E",
                ),
                timeout=args.timeout,
                verify_tls=False,
            )
            record(
                "edge_waf_payload_rejected",
                _waf_payload_rejected(status),
                {"status": status},
            )
        except Exception as exc:
            record("edge_waf_payload_rejected", False, {"error": str(exc)})

    results["failures"] = failures
    results["summary"] = {
        "total_checks": len(results["checks"]),
        "failed_checks": len(failures),
        "passed_checks": len(results["checks"]) - len(failures),
    }

    rendered_json = json.dumps(results, indent=2, sort_keys=True)
    if args.output_path:
        try:
            with open(args.output_path, "w", encoding="utf-8") as output_file:
                output_file.write(rendered_json)
                output_file.write("\n")
        except OSError as exc:
            print(
                f"[attack-regression] failed to write output: {exc}",
                file=sys.stderr,
            )
            return 2
    if args.json_output:
        print(rendered_json)
    else:
        for check in results["checks"]:
            status = "OK" if check["ok"] else "FAIL"
            extra = {k: v for k, v in check.items() if k not in {"name", "ok"}}
            print(f"- {status}: {check['name']} {extra}")
        if failures:
            print(
                f"[attack-regression] failures: {', '.join(failures)}",
                file=sys.stderr,
            )

    return 2 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
