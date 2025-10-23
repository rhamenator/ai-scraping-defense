#!/usr/bin/env python3
"""Validate hardened security configuration for local development deployments."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Callable, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

import yaml

from src.security_audit.inventory import generate_inventory_markdown

def _fail(message: str) -> None:
    print(f"[security-check] {message}", file=sys.stderr)
    raise SystemExit(1)

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
    ]
    for token in required_tokens:
        if token not in config:
            _fail(f"nginx.conf missing required directive: {token}")

def ensure_compose_security() -> None:
    compose = yaml.safe_load((PROJECT_ROOT / "docker-compose.yaml").read_text())
    services = compose.get("services", {})
    required_services = {
        "ai_service",
        "escalation_engine",
        "tarpit_api",
        "cloud_proxy",
        "config_recommender",
    }
    for service_name in required_services:
        service = services.get(service_name)
        if not service:
            _fail(f"docker-compose missing service definition for {service_name}")
        if "no-new-privileges:true" not in service.get("security_opt", []):
            _fail(f"{service_name} must drop privilege escalation")
        if "ALL" not in service.get("cap_drop", []):
            _fail(f"{service_name} must drop all Linux capabilities")
        if not service.get("read_only", False):
            _fail(f"{service_name} must run with a read-only root filesystem")
        tmpfs = service.get("tmpfs", [])
        if not any(str(entry).startswith("/tmp") for entry in tmpfs):
            _fail(f"{service_name} must mount tmpfs for /tmp")
        volumes = service.get("volumes", [])
        if not any(str(volume).endswith(":ro") for volume in volumes):
            _fail(f"{service_name} must mount at least one read-only volume")

    for service in services.values():
        for volume in service.get("volumes", []):
            if isinstance(volume, str) and volume.startswith("./secrets:/run/secrets"):
                if not volume.endswith(":ro"):
                    _fail("Secret volumes must be read-only")

SECRET_PATTERN = re.compile(r"=(?:sk-|AIza|mistral-|coh-|key-for-)")

def ensure_no_plaintext_secrets() -> None:
    sample_env_path = PROJECT_ROOT / "sample.env"
    if not sample_env_path.exists():
        _fail("sample.env does not exist; please provide the file for secret validation.")
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