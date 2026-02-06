#!/usr/bin/env python3
"""Lightweight HTTP-level probes for common security regressions.

This script is intentionally dependency-free (stdlib only) so it can run on
security test hosts (e.g. Kali) without a Python package bootstrap.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


def _now() -> float:
    return time.time()


def _validate_base_url(base_url: str) -> str:
    parsed = urllib.parse.urlparse(base_url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("base URL must use http:// or https://")
    if not parsed.netloc:
        raise ValueError("base URL must include a host")
    # Normalize away fragments to avoid confusing output.
    return urllib.parse.urlunparse(parsed._replace(fragment=""))


def _request(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    data: bytes | None = None,
    timeout: float = 10.0,
) -> tuple[int, dict[str, str], bytes]:
    req = urllib.request.Request(url, method=method)
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, data=data, timeout=timeout) as resp:
            body = resp.read(1024 * 1024)
            resp_headers = {k.lower(): v for k, v in resp.headers.items()}
            return resp.getcode(), resp_headers, body
    except urllib.error.HTTPError as exc:
        body = exc.read(1024 * 1024) if exc.fp else b""
        resp_headers = {k.lower(): v for k, v in exc.headers.items()}
        return int(exc.code), resp_headers, body


def _join(base_url: str, path: str) -> str:
    base = base_url.rstrip("/")
    if not path.startswith("/"):
        path = "/" + path
    return base + path


def _check_headers(headers: dict[str, str]) -> list[str]:
    missing: list[str] = []
    required = [
        "x-frame-options",
        "x-content-type-options",
        "referrer-policy",
        "permissions-policy",
        "content-security-policy",
    ]
    for header in required:
        if header not in headers:
            missing.append(header)
    return missing


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--rate-limit-count", type=int, default=25)
    parser.add_argument("--json", dest="json_output", action="store_true")
    args = parser.parse_args(argv)

    try:
        base_url = _validate_base_url(args.base_url)
    except ValueError as exc:
        print(f"[stack-probe] invalid base_url: {exc}", file=sys.stderr)
        return 2
    timeout = args.timeout
    results: dict[str, object] = {"base_url": base_url, "checks": []}
    failures: list[str] = []

    def record(name: str, ok: bool, detail: dict[str, object]) -> None:
        detail["name"] = name
        detail["ok"] = ok
        results["checks"].append(detail)
        if not ok:
            failures.append(name)

    # 1) Baseline GET
    start = _now()
    try:
        status, headers, _ = _request(base_url, timeout=timeout)
    except Exception as exc:
        record("baseline_get", False, {"error": str(exc)})
    else:
        missing = _check_headers(headers)
        record(
            "baseline_get",
            status < 500,
            {
                "status": status,
                "duration_ms": int((_now() - start) * 1000),
                "missing_security_headers": missing,
            },
        )

    # 2) Long path should not 500
    long_path_url = _join(base_url, "/" + ("a" * 4096))
    try:
        status, _, _ = _request(long_path_url, timeout=timeout)
    except Exception as exc:
        record("long_path", False, {"error": str(exc)})
    else:
        record("long_path", status < 500, {"status": status})

    # 3) Long query should not 500
    long_query = "q=" + ("a" * 8192)
    long_query_url = base_url.rstrip("/") + "/?" + long_query
    try:
        status, _, _ = _request(long_query_url, timeout=timeout)
    except Exception as exc:
        record("long_query", False, {"error": str(exc)})
    else:
        record("long_query", status < 500, {"status": status})

    # 4) Large header value should not 500
    large_header_url = _join(base_url, "/")
    try:
        status, _, _ = _request(
            large_header_url,
            headers={"X-Probe": "a" * 16384},
            timeout=timeout,
        )
    except Exception as exc:
        record("large_header_value", False, {"error": str(exc)})
    else:
        record("large_header_value", status < 500, {"status": status})

    # 5) Rate limiting (best-effort): note whether any 429 observed
    count = max(1, args.rate_limit_count)
    statuses: list[int] = []
    for _ in range(count):
        try:
            status, _, _ = _request(base_url, timeout=timeout)
        except Exception:
            statuses.append(0)
        else:
            statuses.append(status)
    record(
        "rate_limit_probe",
        True,
        {
            "count": count,
            "any_429": any(s == 429 for s in statuses),
            "any_5xx": any(s >= 500 for s in statuses),
        },
    )
    if any(s >= 500 for s in statuses):
        failures.append("rate_limit_probe_5xx")

    results["failures"] = failures
    if args.json_output:
        print(json.dumps(results, indent=2, sort_keys=True))
    else:
        print(f"[stack-probe] base_url={base_url}")
        for check in results["checks"]:
            name = check["name"]
            ok = check["ok"]
            extra = {k: v for k, v in check.items() if k not in {"name", "ok"}}
            status = "OK" if ok else "FAIL"
            print(f"- {status}: {name} {extra}")
        if failures:
            print(f"[stack-probe] failures: {', '.join(failures)}", file=sys.stderr)

    # Exit non-zero only on hard failures (exceptions / 5xx responses).
    hard_fail = any(
        check.get("name")
        in {"baseline_get", "long_path", "long_query", "large_header_value"}
        and not check.get("ok")
        for check in results["checks"]
        if isinstance(check, dict)
    ) or ("rate_limit_probe_5xx" in failures)
    return 2 if hard_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
