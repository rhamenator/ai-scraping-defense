from pathlib import Path

import yaml

WORKLOAD_KINDS = {"Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob"}
BASELINE = yaml.safe_load(Path("config/security_hardening.yaml").read_text())
HARDENED_SERVICES = set(BASELINE["compose"]["required_services"])
COMPOSE_EXCEPTIONS = set(BASELINE["compose"]["documented_exceptions"])
RESTRICTED_WORKLOADS = BASELINE["kubernetes"]["restricted_workloads"]
KUBERNETES_EXCEPTIONS = set(BASELINE["kubernetes"]["documented_exceptions"])
INSTALLER_CALL_TOKENS = BASELINE["installers"]["required_call_tokens"]
NETWORK_EXPOSURE = BASELINE["network_exposure"]
HTTPS_REDIRECTED_HEALTHCHECK_SERVICES = {
    "ai_service",
    "admin_ui",
    "captcha_service",
    "cloud_dashboard",
    "cloud_proxy",
    "config_recommender",
    "escalation_engine",
    "prompt_router",
    "tarpit_api",
}


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


def _iter_kubernetes_workload_specs():
    for manifest_path in Path("kubernetes").glob("*.y*ml"):
        for document in yaml.safe_load_all(manifest_path.read_text()):
            if not isinstance(document, dict):
                continue
            kind = document.get("kind")
            if kind not in WORKLOAD_KINDS:
                continue

            spec = document.get("spec") or {}
            if kind in {"Deployment", "StatefulSet", "DaemonSet", "Job"}:
                pod_spec = ((spec.get("template") or {}).get("spec")) or {}
            else:
                pod_spec = (
                    (
                        ((spec.get("jobTemplate") or {}).get("spec") or {}).get(
                            "template"
                        )
                    )
                    or {}
                ).get("spec", {})
            yield manifest_path, kind, pod_spec


def test_nginx_enforces_https_and_headers():
    config = Path("nginx/nginx.conf").read_text()
    assert "Strict-Transport-Security" in config
    assert "add_header X-Frame-Options" in config
    assert "return 301 https://$host$request_uri;" in config
    assert "include /etc/nginx/conf.d/*.conf;" in config
    assert "limit_req_zone" in config
    assert "location = /healthz" in config
    assert "client_body_temp_path /var/run/openresty/nginx-client-body;" in config
    assert "proxy_temp_path /var/cache/nginx/proxy_temp;" in config
    assert "fastcgi_temp_path /var/cache/nginx/fastcgi_temp;" in config
    assert "uwsgi_temp_path /var/cache/nginx/uwsgi_temp;" in config
    assert "scgi_temp_path /var/cache/nginx/scgi_temp;" in config


def test_nginx_compose_service_renders_cdn_origin_lockdown():
    compose = _load_compose()
    nginx_service = compose["services"]["nginx_proxy"]

    assert any(
        str(volume).startswith(
            "./nginx/render_cdn_origin_lockdown.sh:/usr/local/bin/render_cdn_origin_lockdown.sh"
        )
        for volume in nginx_service.get("volumes", [])
    )
    command = " ".join(nginx_service.get("command", []))
    assert "render_cdn_origin_lockdown.sh" in command
    assert "openresty -g 'daemon off;'" in command


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


def test_compose_services_have_full_hardening_coverage():
    compose = _load_compose()
    services = set(compose.get("services", {}))

    assert services == HARDENED_SERVICES | COMPOSE_EXCEPTIONS


def test_compose_mounts_secret_directory_read_only():
    compose = _load_compose()
    services = compose.get("services", {})
    for service in services.values():
        volumes = service.get("volumes", [])
        for volume in volumes:
            if isinstance(volume, str) and volume.startswith("./secrets:/run/secrets"):
                assert volume.endswith(":ro"), "Secrets volume must be read-only"


def test_python_edge_services_use_builtin_health_probes():
    compose = _load_compose()
    services = compose.get("services", {})
    for service_name in ("cloud_proxy", "prompt_router"):
        healthcheck = services[service_name]["healthcheck"]["test"]
        assert healthcheck[:2] == ["CMD", "python"]
        command = " ".join(healthcheck)
        assert "urllib.request" in command


def test_https_redirected_services_have_proxy_aware_healthchecks():
    compose = _load_compose()
    services = compose.get("services", {})
    for service_name in HTTPS_REDIRECTED_HEALTHCHECK_SERVICES:
        healthcheck = services[service_name]["healthcheck"]["test"]
        command = (
            " ".join(healthcheck) if isinstance(healthcheck, list) else str(healthcheck)
        )
        assert (
            "X-Forwarded-Proto" in command and "https" in command
        ), f"{service_name} healthcheck must bypass HTTPS redirect loops"

    escalation_command = " ".join(services["escalation_engine"]["healthcheck"]["test"])
    assert "curl -sS" in escalation_command
    assert "curl -fsS" not in escalation_command


def test_compose_network_exposure_is_fully_documented():
    compose = _load_compose()
    services = compose.get("services", {})
    published = {name for name, svc in services.items() if svc.get("ports")}
    compose_baseline = NETWORK_EXPOSURE["compose"]
    documented = (
        set(compose_baseline["public_edge_services"])
        | set(compose_baseline["operator_access_services"])
        | set(compose_baseline["development_only_services"])
    )

    assert published == documented
    assert not (published & set(compose_baseline["internal_only_services"]))


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


def test_kubernetes_workloads_have_full_hardening_coverage():
    discovered = {
        manifest_path.name for manifest_path, _, _ in _iter_kubernetes_workload_specs()
    }

    assert discovered == set(RESTRICTED_WORKLOADS) | KUBERNETES_EXCEPTIONS


def test_kubernetes_service_exposure_matches_baseline():
    expected = dict(NETWORK_EXPOSURE["kubernetes"]["public_services"]) | dict(
        NETWORK_EXPOSURE["kubernetes"]["internal_services"]
    )
    discovered = {}
    for manifest_path in Path("kubernetes").glob("*.y*ml"):
        for document in yaml.safe_load_all(manifest_path.read_text()):
            if not isinstance(document, dict) or document.get("kind") != "Service":
                continue
            name = (document.get("metadata") or {}).get("name")
            discovered[name] = (document.get("spec") or {}).get("type", "ClusterIP")

    assert discovered == expected


def test_helm_service_defaults_preserve_internal_clusterip_boundaries():
    values = yaml.safe_load(Path("helm/ai-scraping-defense-v9/values.yaml").read_text())
    services = values["services"]
    for service_name in NETWORK_EXPOSURE["helm"]["v9_services_requiring_clusterip"]:
        assert services[service_name]["service"]["type"] == "ClusterIP"

    legacy_public = Path(
        "helm/ai-scraping-defense/templates/nginx-deployment.yaml"
    ).read_text()
    assert "type: LoadBalancer" in legacy_public


def test_selected_kubernetes_workloads_define_restricted_security_contexts():
    seen = {name: set() for name in RESTRICTED_WORKLOADS}

    for manifest_path, _, pod_spec in _iter_kubernetes_workload_specs():
        required_containers = RESTRICTED_WORKLOADS.get(manifest_path.name)
        if not required_containers:
            continue

        pod_security_context = pod_spec.get("securityContext") or {}
        assert pod_security_context.get("runAsNonRoot") is True
        assert pod_security_context.get("runAsUser") == 1000
        assert pod_security_context.get("runAsGroup") == 1000
        assert pod_security_context.get("fsGroup") == 1000
        assert pod_security_context.get("seccompProfile", {}).get("type") == (
            "RuntimeDefault"
        )

        containers = pod_spec.get("containers") or []
        volumes = {volume.get("name"): volume for volume in pod_spec.get("volumes", [])}
        assert "tmp" in volumes and "emptyDir" in volumes["tmp"]

        for container in containers:
            name = container.get("name")
            if name not in required_containers:
                continue
            seen[manifest_path.name].add(name)
            security_context = container.get("securityContext") or {}
            assert security_context.get("allowPrivilegeEscalation") is False
            assert security_context.get("readOnlyRootFilesystem") is True
            assert security_context.get("capabilities", {}).get("drop") == ["ALL"]
            volume_mounts = {
                mount.get("name"): mount for mount in container.get("volumeMounts", [])
            }
            assert volume_mounts.get("tmp", {}).get("mountPath") == "/tmp"

    for manifest_name, container_names in RESTRICTED_WORKLOADS.items():
        assert seen[manifest_name] == set(container_names)


def test_installer_scripts_preserve_no_new_privileges_detection():
    for relative_path, tokens in INSTALLER_CALL_TOKENS.items():
        contents = Path(relative_path).read_text()
        for token in tokens:
            assert token in contents
