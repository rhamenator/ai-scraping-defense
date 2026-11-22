"""Guards the container supply-chain and Docker-socket hardening (#1913)."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = (ROOT / "docker-compose.yaml").read_text()
DOCKERFILE = (ROOT / "Dockerfile").read_text()
NGINX_K8S = (ROOT / "kubernetes" / "nginx-deployment.yaml").read_text()
SERVICES_BLOCK = COMPOSE[COMPOSE.index("\nservices:"):COMPOSE.index("\nnetworks:")]


def _service(name: str) -> str:
    match = re.search(rf"(?ms)^  {re.escape(name)}:\n(.*?)(?=^  [A-Za-z0-9_]+:\n|^\S)", COMPOSE)
    assert match, f"service {name} not found"
    return match.group(1)


def test_every_compose_image_is_pinned_by_digest():
    images = re.findall(r"(?m)^\s+image: (\S+)\s*$", COMPOSE)
    assert images, "expected image entries"
    for image in images:
        assert re.search(r"@sha256:[0-9a-f]{64}$", image), f"image is not pinned by digest: {image}"


def test_every_dockerfile_base_image_is_pinned_by_digest():
    bases = re.findall(r"(?m)^FROM (\S+)", DOCKERFILE)
    assert bases
    for base in bases:
        assert re.search(r"@sha256:[0-9a-f]{64}$", base), f"base image is not pinned by digest: {base}"


def test_kubernetes_nginx_image_is_pinned_by_digest():
    images = re.findall(r"(?m)^\s+image: (\S*openresty\S*)\s*$", NGINX_K8S)
    assert images
    for image in images:
        assert "@sha256:" in image, image


def test_only_the_socket_proxy_and_opt_in_watchtower_mount_the_docker_socket():
    mounting = {
        name
        for name in re.findall(r"(?m)^  ([A-Za-z0-9_]+):\n", SERVICES_BLOCK)
        if "docker.sock" in _service(name)
    }
    assert mounting == {"docker_socket_proxy", "watchtower"}


def test_traefik_reads_containers_through_the_proxy_only():
    traefik = _service("traefik")
    assert "docker.sock" not in traefik
    assert "--providers.docker.endpoint=tcp://docker_socket_proxy:2375" in traefik


def test_socket_proxy_is_read_only_and_isolated():
    proxy = _service("docker_socket_proxy")
    assert 'POST: "0"' in proxy
    assert 'CONTAINERS: "1"' in proxy
    assert not re.search(r"(?m)^\s+ports:", proxy)
    assert re.search(r"(?ms)^  docker_api:\n(?:    .*\n)*?    internal: true", COMPOSE)


def test_watchtower_is_opt_in_and_limited_to_labelled_containers():
    watchtower = _service("watchtower")
    assert re.search(r'profiles:\s*\["auto-update"\]', watchtower)
    assert "--label-enable" in watchtower
