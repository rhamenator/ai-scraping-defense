#!/usr/bin/env python3
"""Validate hardened security configuration for local development deployments."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

import yaml  # noqa: E402

from src.security_audit.inventory import generate_inventory_markdown  # noqa: E402


def _fail(message: str) -> None:
    print(f"[security-check] {message}", file=sys.stderr)
    raise SystemExit(1)


DEFAULT_HARDENING_BASELINE: Dict[str, Any] = {
    "compose": {
        "required_services": [
            "ai_service",
            "escalation_engine",
            "tarpit_api",
            "cloud_proxy",
            "config_recommender",
        ],
        "service_requirements": {
            "security_opt": ["no-new-privileges:true"],
            "cap_drop": ["ALL"],
            "read_only": True,
            "tmpfs_prefixes": ["/tmp"],
            "require_readonly_volume": True,
        },
        "secret_volume_prefixes": ["./secrets:/run/secrets"],
        "secret_volume_readonly": True,
    }
}


def _load_hardening_baseline() -> Dict[str, Any]:
    baseline_path = PROJECT_ROOT / "config/security_hardening.yaml"
    if not baseline_path.exists():
        _fail("Missing config/security_hardening.yaml baseline configuration.")
    baseline = yaml.safe_load(baseline_path.read_text()) or {}
    merged = dict(DEFAULT_HARDENING_BASELINE)
    merged_compose = dict(DEFAULT_HARDENING_BASELINE.get("compose", {}))
    merged_compose.update(baseline.get("compose", {}))
    merged["compose"] = merged_compose
    return merged


def ensure_inventory_is_current() -> None:
    json_path = PROJECT_ROOT / "security_problems_batch1.json"
    markdown_path = PROJECT_ROOT / "docs/security/security_inventory_batch1.md"
    expected = generate_inventory_markdown(json_path)
    recorded = markdown_path.read_text()
    if expected != recorded:
        _fail("Security inventory markdown is stale. Re-run the generator.")


def ensure_nginx_headers_and_limits() -> None:
    config = (PROJECT_ROOT / "nginx/nginx.conf").read_text()
    required_tokens = [
        "Strict-Transport-Security",
        "limit_req_zone",
        "limit_req zone=global_limit",
        "add_header X-Frame-Options",
        "add_header X-Content-Type-Options",
        "add_header Content-Security-Policy",
    ]
    for token in required_tokens:
        if token not in config:
            _fail(f"nginx.conf missing required directive: {token}")


def ensure_compose_security() -> None:
    baseline = _load_hardening_baseline()
    compose_baseline = baseline.get("compose", {})
    required_services: List[str] = compose_baseline.get(
        "required_services", DEFAULT_HARDENING_BASELINE["compose"]["required_services"]
    )
    service_requirements = compose_baseline.get(
        "service_requirements",
        DEFAULT_HARDENING_BASELINE["compose"]["service_requirements"],
    )
    required_security_opt = service_requirements.get(
        "security_opt", ["no-new-privileges:true"]
    )
    required_cap_drop = service_requirements.get("cap_drop", ["ALL"])
    require_read_only = service_requirements.get("read_only", True)
    tmpfs_prefixes = service_requirements.get("tmpfs_prefixes", ["/tmp"])
    require_readonly_volume = service_requirements.get("require_readonly_volume", True)
    secret_prefixes = compose_baseline.get(
        "secret_volume_prefixes", ["./secrets:/run/secrets"]
    )
    require_secret_ro = compose_baseline.get("secret_volume_readonly", True)

    compose = yaml.safe_load((PROJECT_ROOT / "docker-compose.yaml").read_text())
    services = compose.get("services", {})
    for service_name in required_services:
        service = services.get(service_name)
        if not service:
            _fail(f"docker-compose missing service definition for {service_name}")
        security_opt = service.get("security_opt", [])
        for token in required_security_opt:
            if token not in security_opt:
                _fail(f"{service_name} missing security_opt entry: {token}")
        cap_drop = service.get("cap_drop", [])
        for cap in required_cap_drop:
            if cap not in cap_drop:
                _fail(f"{service_name} missing cap_drop entry: {cap}")
        if require_read_only and not service.get("read_only", False):
            _fail(f"{service_name} must run with a read-only root filesystem")
        tmpfs = service.get("tmpfs", [])
        if not any(
            str(entry).startswith(prefix)
            for entry in tmpfs
            for prefix in tmpfs_prefixes
        ):
            _fail(f"{service_name} must mount tmpfs for /tmp")
        volumes = service.get("volumes", [])
        if require_readonly_volume and not any(
            str(volume).endswith(":ro") for volume in volumes
        ):
            _fail(f"{service_name} must mount at least one read-only volume")

    for service in services.values():
        for volume in service.get("volumes", []):
            if isinstance(volume, str) and any(
                volume.startswith(prefix) for prefix in secret_prefixes
            ):
                if require_secret_ro and not volume.endswith(":ro"):
                    _fail("Secret volumes must be read-only")


SECRET_PATTERN = re.compile(r"=(?:sk-|AIza|mistral-|coh-|key-for-)")


def ensure_no_plaintext_secrets() -> None:
    sample_env_path = PROJECT_ROOT / "sample.env"
    if not sample_env_path.exists():
        _fail(
            "sample.env does not exist; please provide the file for secret validation."
        )
    sample_env = sample_env_path.read_text()
    for line in sample_env.splitlines():
        if SECRET_PATTERN.search(line):
            _fail("Potential plaintext secret detected in sample.env")


CHECKS: Iterable[Callable[[], None]] = (
    ensure_inventory_is_current,
    ensure_nginx_headers_and_limits,
    ensure_compose_security,
    ensure_no_plaintext_secrets,
)


def main() -> None:
    for check in CHECKS:
        check()
    print("All static security checks passed.")


if __name__ == "__main__":
    main()
