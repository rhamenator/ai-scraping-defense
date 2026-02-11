from pathlib import Path

import yaml

HARDENED_SERVICES = {
    "ai_service",
    "escalation_engine",
    "tarpit_api",
    "cloud_proxy",
    "config_recommender",
}
WORKLOAD_KINDS = {"Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob"}


def _load_compose() -> dict:
    compose_path = Path("docker-compose.yaml")
    return yaml.safe_load(compose_path.read_text())


def _iter_kubernetes_workload_containers():
    for manifest_path in Path("kubernetes").glob("*.y*ml"):
        for document in yaml.safe_load_all(manifest_path.read_text()):
            if not isinstance(document, dict):
                continue
            kind = document.get("kind")
            if kind not in WORKLOAD_KINDS:
                continue

            spec = document.get("spec") or {}
            containers = []
            if kind in {"Deployment", "StatefulSet", "DaemonSet", "Job"}:
                containers = ((spec.get("template") or {}).get("spec") or {}).get(
                    "containers"
                ) or []
            elif kind == "CronJob":
                containers = (
                    (
                        ((spec.get("jobTemplate") or {}).get("spec") or {}).get(
                            "template"
                        )
                        or {}
                    )
                    .get("spec", {})
                    .get("containers")
                ) or []

            for container in containers:
                yield manifest_path, kind, container


def test_nginx_enforces_https_and_headers():
    config = Path("nginx/nginx.conf").read_text()
    assert "Strict-Transport-Security" in config
    assert "add_header X-Frame-Options" in config
    assert "return 301 https://$host$request_uri;" in config
    assert "limit_req_zone" in config


def test_compose_services_drop_privileges():
    compose = _load_compose()
    services = compose.get("services", {})
    for service_name in HARDENED_SERVICES:
        assert service_name in services, f"{service_name} missing from compose"
        service = services[service_name]
        security_opt = service.get("security_opt", [])
        assert any(
            str(opt).startswith("no-new-privileges:") for opt in security_opt
        ), f"{service_name} must set no-new-privileges"
        assert "cap_drop" in service and "ALL" in service["cap_drop"]
        assert service.get("read_only", False) is True
        tmpfs = service.get("tmpfs", [])
        assert any(str(entry).startswith("/tmp") for entry in tmpfs)  # nosec B108
        volumes = service.get("volumes", [])
        assert any(str(volume).endswith(":ro") for volume in volumes)


def test_compose_mounts_secret_directory_read_only():
    compose = _load_compose()
    services = compose.get("services", {})
    for service in services.values():
        volumes = service.get("volumes", [])
        for volume in volumes:
            if isinstance(volume, str) and volume.startswith("./secrets:/run/secrets"):
                assert volume.endswith(":ro"), "Secrets volume must be read-only"


def test_kubernetes_workloads_define_resource_limits():
    missing = []
    for manifest_path, kind, container in _iter_kubernetes_workload_containers():
        name = container.get("name", "<unnamed>")
        resources = container.get("resources") or {}
        requests = resources.get("requests") or {}
        limits = resources.get("limits") or {}
        if not requests or not limits:
            missing.append(f"{manifest_path.name}:{kind}:{name}")

    assert not missing, (
        "All Kubernetes workload containers must define resources.requests and "
        "resources.limits: " + ", ".join(sorted(missing))
    )
