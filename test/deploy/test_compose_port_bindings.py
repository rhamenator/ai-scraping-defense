"""Only the public edge may publish ports on every interface (#1914)."""

from pathlib import Path

import yaml

COMPOSE = yaml.safe_load((Path(__file__).resolve().parents[2] / "docker-compose.yaml").read_text())
PUBLIC_EDGE = {"nginx_proxy"}
LOOPBACK_DEFAULT = "${PUBLISH_ADDRESS:-127.0.0.1}:"


def _published():
    for name, service in COMPOSE["services"].items():
        for port in service.get("ports", []) or []:
            yield name, str(port)


def test_only_the_public_edge_publishes_on_all_interfaces():
    seen = set()
    for name, port in _published():
        seen.add(name)
        if name in PUBLIC_EDGE:
            assert not port.startswith(LOOPBACK_DEFAULT), f"{name} is the public edge and should stay public"
        else:
            assert port.startswith(LOOPBACK_DEFAULT), f"{name} publishes {port} on every interface"
    assert PUBLIC_EDGE <= seen


def test_data_stores_and_model_servers_are_never_public_by_default():
    for name in ("postgres", "redis", "llama3", "mixtral", "admin_ui", "traefik", "prometheus", "grafana"):
        ports = [port for owner, port in _published() if owner == name]
        assert ports, f"{name} no longer publishes a port; update this test if that is intended"
        assert all(port.startswith(LOOPBACK_DEFAULT) for port in ports), name
