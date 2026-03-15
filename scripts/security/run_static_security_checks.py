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


def _fail(message: str) -> None:
    print(f"[security-check] {message}", file=sys.stderr)
    raise SystemExit(1)


DEFAULT_HARDENING_BASELINE: Dict[str, Any] = {
    "compose": {
        "required_services": [
            "nginx_proxy",
            "ai_service",
            "escalation_engine",
            "tarpit_api",
            "admin_ui",
            "captcha_service",
            "cloud_dashboard",
            "cloud_proxy",
            "config_recommender",
            "prompt_router",
            "blocklist_sync",
        ],
        "service_requirements": {
            "security_opt": ["no-new-privileges:true"],
            "cap_drop": ["ALL"],
            "read_only": True,
            "tmpfs_prefixes": ["/tmp"],  # nosec B108 - tmpfs mount requirement
            "require_readonly_volume": True,
        },
        "secret_volume_prefixes": ["./secrets:/run/secrets"],
        "secret_volume_readonly": True,
        "documented_exceptions": {},
    },
    "kubernetes": {
        "restricted_workloads": {
            "admin-ui-deployment.yaml": ["admin-ui"],
            "ai-service-deployment.yaml": ["ai-service"],
            "archive-rotator-deployment.yaml": ["archive-rotator"],
            "corpus-updater-cronjob.yaml": ["corpus-updater"],
            "escalation-engine-deployment.yaml": ["escalation-engine"],
            "markov-model-trainer.yaml": ["markov-trainer"],
            "robots-fetcher-cronjob.yaml": ["robots-fetcher"],
            "tarpit-api-deployment.yaml": ["tarpit-api"],
            "waf-rules-fetcher-cronjob.yaml": ["owasp-crs-fetcher"],
        },
        "documented_exceptions": {},
    },
    "installers": {
        "required_call_tokens": {},
    },
}
WORKLOAD_KINDS = {"Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob"}


def _load_hardening_baseline() -> Dict[str, Any]:
    baseline_path = PROJECT_ROOT / "config/security_hardening.yaml"
    if not baseline_path.exists():
        _fail("Missing config/security_hardening.yaml baseline configuration.")
    baseline = yaml.safe_load(baseline_path.read_text()) or {}
    merged = dict(DEFAULT_HARDENING_BASELINE)
    merged_compose = dict(DEFAULT_HARDENING_BASELINE.get("compose", {}))
    merged_compose.update(baseline.get("compose", {}))
    merged["compose"] = merged_compose
    merged_kubernetes = dict(DEFAULT_HARDENING_BASELINE.get("kubernetes", {}))
    merged_kubernetes.update(baseline.get("kubernetes", {}))
    merged["kubernetes"] = merged_kubernetes
    merged_installers = dict(DEFAULT_HARDENING_BASELINE.get("installers", {}))
    merged_installers.update(baseline.get("installers", {}))
    merged["installers"] = merged_installers
    return merged


def _matches_required_value(actual: Any, expected: str) -> bool:
    """Allow compose hardening tokens to use env expansion with safe defaults."""
    actual_value = str(actual)
    if actual_value == expected:
        return True
    if expected == "no-new-privileges:true":
        return bool(
            re.fullmatch(
                r"no-new-privileges:\$\{[A-Z0-9_]+(?::-[Tt][Rr][Uu][Ee])?\}",
                actual_value,
            )
        )
    return False


def _extract_pod_spec(document: Dict[str, Any]) -> Dict[str, Any]:
    kind = document.get("kind")
    spec = document.get("spec") or {}
    if kind in {"Deployment", "StatefulSet", "DaemonSet", "Job"}:
        return ((spec.get("template") or {}).get("spec")) or {}
    if kind == "CronJob":
        return (
            (
                (((spec.get("jobTemplate") or {}).get("spec") or {}).get("template"))
                or {}
            )
        ).get("spec", {})
    return {}


def _iter_kubernetes_workloads() -> (
    Iterable[tuple[Path, Dict[str, Any], Dict[str, Any]]]
):
    for manifest_path in sorted((PROJECT_ROOT / "kubernetes").glob("*.y*ml")):
        for document in yaml.safe_load_all(manifest_path.read_text()):
            if not isinstance(document, dict):
                continue
            if document.get("kind") not in WORKLOAD_KINDS:
                continue
            yield manifest_path, document, _extract_pod_spec(document)


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
    tmpfs_prefixes = service_requirements.get(
        "tmpfs_prefixes", ["/tmp"]  # nosec B108 - tmpfs mount requirement
    )
    require_readonly_volume = service_requirements.get("require_readonly_volume", True)
    secret_prefixes = compose_baseline.get(
        "secret_volume_prefixes", ["./secrets:/run/secrets"]
    )
    require_secret_ro = compose_baseline.get("secret_volume_readonly", True)

    compose = yaml.safe_load((PROJECT_ROOT / "docker-compose.yaml").read_text())
    services = compose.get("services", {})
    documented_exceptions = compose_baseline.get("documented_exceptions", {})
    covered_services = set(required_services) | set(documented_exceptions)
    missing_coverage = sorted(set(services) - covered_services)
    if missing_coverage:
        _fail(
            "docker-compose services missing hardening coverage: "
            + ", ".join(missing_coverage)
        )
    stale_exceptions = sorted(set(documented_exceptions) - set(services))
    if stale_exceptions:
        _fail(
            "security_hardening.yaml lists stale compose exceptions: "
            + ", ".join(stale_exceptions)
        )

    for service_name in required_services:
        service = services.get(service_name)
        if not service:
            _fail(f"docker-compose missing service definition for {service_name}")
        security_opt = service.get("security_opt", [])
        for token in required_security_opt:
            if not any(_matches_required_value(opt, token) for opt in security_opt):
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


def ensure_kubernetes_runtime_security() -> None:
    baseline = _load_hardening_baseline()
    kubernetes_baseline = baseline.get("kubernetes", {})
    restricted_workloads = kubernetes_baseline.get("restricted_workloads", {})
    documented_exceptions = kubernetes_baseline.get("documented_exceptions", {})

    discovered_workloads = {
        path.name: (document, pod_spec)
        for path, document, pod_spec in _iter_kubernetes_workloads()
    }
    covered_workloads = set(restricted_workloads) | set(documented_exceptions)
    missing_coverage = sorted(set(discovered_workloads) - covered_workloads)
    if missing_coverage:
        _fail(
            "Kubernetes workloads missing hardening coverage: "
            + ", ".join(missing_coverage)
        )
    stale_coverage = sorted(covered_workloads - set(discovered_workloads))
    if stale_coverage:
        _fail(
            "security_hardening.yaml lists stale Kubernetes entries: "
            + ", ".join(stale_coverage)
        )

    for manifest_name, required_containers in restricted_workloads.items():
        _, pod_spec = discovered_workloads[manifest_name]
        pod_security_context = pod_spec.get("securityContext") or {}
        if pod_security_context.get("runAsNonRoot") is not True:
            _fail(f"{manifest_name} must set pod securityContext.runAsNonRoot=true")
        if pod_security_context.get("runAsUser") != 1000:
            _fail(f"{manifest_name} must set pod securityContext.runAsUser=1000")
        if pod_security_context.get("runAsGroup") != 1000:
            _fail(f"{manifest_name} must set pod securityContext.runAsGroup=1000")
        if pod_security_context.get("fsGroup") != 1000:
            _fail(f"{manifest_name} must set pod securityContext.fsGroup=1000")
        if (
            pod_security_context.get("seccompProfile", {}).get("type")
            != "RuntimeDefault"
        ):
            _fail(
                f"{manifest_name} must set pod securityContext.seccompProfile.type=RuntimeDefault"
            )

        volumes = {
            volume.get("name"): volume for volume in (pod_spec.get("volumes") or [])
        }
        if "tmp" not in volumes or "emptyDir" not in volumes["tmp"]:
            _fail(f"{manifest_name} must define an emptyDir tmp volume")

        containers = {
            container.get("name"): container
            for container in (pod_spec.get("containers") or [])
        }
        for container_name in required_containers:
            container = containers.get(container_name)
            if not container:
                _fail(f"{manifest_name} missing container {container_name}")
            security_context = container.get("securityContext") or {}
            if security_context.get("allowPrivilegeEscalation") is not False:
                _fail(
                    f"{manifest_name}:{container_name} must set allowPrivilegeEscalation=false"
                )
            if security_context.get("readOnlyRootFilesystem") is not True:
                _fail(
                    f"{manifest_name}:{container_name} must set readOnlyRootFilesystem=true"
                )
            if security_context.get("capabilities", {}).get("drop") != ["ALL"]:
                _fail(f"{manifest_name}:{container_name} must drop all capabilities")
            volume_mounts = {
                mount.get("name"): mount
                for mount in (container.get("volumeMounts") or [])
            }
            if volume_mounts.get("tmp", {}).get("mountPath") != "/tmp":
                _fail(f"{manifest_name}:{container_name} must mount tmp at /tmp")


def ensure_installer_hardening_hooks() -> None:
    baseline = _load_hardening_baseline()
    required_call_tokens = baseline.get("installers", {}).get(
        "required_call_tokens", {}
    )
    for relative_path, tokens in required_call_tokens.items():
        file_path = PROJECT_ROOT / relative_path
        if not file_path.exists():
            _fail(
                f"Missing installer path referenced by hardening baseline: {relative_path}"
            )
        contents = file_path.read_text()
        for token in tokens:
            if token not in contents:
                _fail(f"{relative_path} missing required hardening call: {token}")


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
    ensure_nginx_headers_and_limits,
    ensure_compose_security,
    ensure_kubernetes_runtime_security,
    ensure_installer_hardening_hooks,
    ensure_no_plaintext_secrets,
)


def main() -> None:
    for check in CHECKS:
        check()
    print("All static security checks passed.")


if __name__ == "__main__":
    main()
