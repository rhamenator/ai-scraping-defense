#!/usr/bin/env python3
"""Deterministic HTTP attack-regression probes for CI."""

from __future__ import annotations

import argparse
import json
import ssl
import sys
import urllib.parse
from http.client import HTTPConnection, HTTPSConnection

REDIRECT_STATUSES = {301, 302, 307, 308}
SECURITY_HEADERS = {
    "content-security-policy",
    "permissions-policy",
    "referrer-policy",
    "x-content-type-options",
    "x-frame-options",
}


def _validate_base_url(base_url: str) -> str:
    parsed = urllib.parse.urlparse(base_url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("base URL must use http:// or https://")
    if not parsed.netloc:
        raise ValueError("base URL must include a host")
    return urllib.parse.urlunparse(parsed._replace(fragment=""))


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nginx-http-base", required=True)
    parser.add_argument("--nginx-https-base", required=True)
    parser.add_argument("--admin-ui-base", required=True)
    parser.add_argument("--prompt-router-base")
    parser.add_argument("--prompt-shared-secret")
    parser.add_argument("--prompt-rate-limit-count", type=int, default=6)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--json", dest="json_output", action="store_true")
    args = parser.parse_args(argv)

    try:
        nginx_http_base = _validate_base_url(args.nginx_http_base)
        nginx_https_base = _validate_base_url(args.nginx_https_base)
        admin_ui_base = _validate_base_url(args.admin_ui_base)
        prompt_router_base = (
            _validate_base_url(args.prompt_router_base)
            if args.prompt_router_base
            else None
        )
    except ValueError as exc:
        print(f"[attack-regression] invalid input: {exc}", file=sys.stderr)
        return 2

    results: dict[str, object] = {"checks": []}
    failures: list[str] = []

    def record(name: str, ok: bool, detail: dict[str, object]) -> None:
        payload = {"name": name, "ok": ok, **detail}
        results["checks"].append(payload)
        if not ok:
            failures.append(name)

    try:
        status, headers, _ = _request(
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

    try:
        status, headers, _ = _request(
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

    try:
        status, headers, _ = _request(
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

    try:
        status, _, _ = _request(
            _join(admin_ui_base, "/observability/health"),
            headers={"X-Probe": "a" * 9000},
            timeout=args.timeout,
        )
        record("admin_ui_large_header_rejected", status == 431, {"status": status})
    except Exception as exc:
        record("admin_ui_large_header_rejected", False, {"error": str(exc)})

    try:
        status, _, _ = _request(
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

    if prompt_router_base and args.prompt_shared_secret:
        statuses: list[int] = []
        for _ in range(max(args.prompt_rate_limit_count, 2)):
            try:
                status, _, _ = _request(
                    _join(prompt_router_base, "/route"),
                    method="POST",
                    headers={
                        "Authorization": f"Bearer {args.prompt_shared_secret}",
                        "Content-Type": "application/json",
                    },
                    data=json.dumps({"prompt": "hi", "input": "hi"}).encode(),
                    timeout=args.timeout,
                )
            except Exception:
                status = 0
            statuses.append(status)
        record(
            "prompt_router_rate_limit",
            _prompt_rate_limit_ok(statuses),
            {"statuses": statuses},
        )

    results["failures"] = failures
    if args.json_output:
        print(json.dumps(results, indent=2, sort_keys=True))
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
