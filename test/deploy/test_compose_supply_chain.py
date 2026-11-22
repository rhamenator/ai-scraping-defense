"""Guards the container supply-chain and Docker-socket hardening (#1913)."""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = yaml.safe_load((ROOT / "docker-compose.yaml").read_text())
SERVICES = COMPOSE["services"]
DOCKERFILE = (ROOT / "Dockerfile").read_text()
NGINX_K8S = (ROOT / "kubernetes" / "nginx-deployment.yaml").read_text()
DIGEST = re.compile(r"@sha256:[0-9a-f]{64}$")


def _dockerfile_digest_default(name: str) -> str:
    match = re.search(rf"(?m)^ARG {name}=(sha256:[0-9a-f]{{64}})$", DOCKERFILE)
    assert match, f"{name} default digest not found in the Dockerfile"
    return match.group(1)


def test_every_compose_image_is_pinned_by_digest():
    images = {name: svc["image"] for name, svc in SERVICES.items() if "image" in svc}
    assert images
    for name, image in images.items():
        assert DIGEST.search(image), f"{name}: image is not pinned by digest: {image}"


def test_dockerfile_base_images_use_digest_arguments_with_defaults():
    bases = re.findall(r"(?m)^FROM (\S+)", DOCKERFILE)
    assert len(bases) >= 2
    for base in bases:
        assert re.search(r"@\$\{(PYTHON|RUST)_DIGEST\}$", base), f"base image is not pinned by a digest argument: {base}"
    _dockerfile_digest_default("PYTHON_DIGEST")
    _dockerfile_digest_default("RUST_DIGEST")


def test_a_version_override_that_disagrees_with_its_digest_fails_the_build():
    assert 'rustc --version | grep -F "rustc ${RUST_VERSION}."' in DOCKERFILE
    assert "does not match the pinned" in DOCKERFILE
    assert "sys.version_info[:2]" in DOCKERFILE


def test_compose_build_arguments_carry_the_dockerfile_digests():
    python_digest = _dockerfile_digest_default("PYTHON_DIGEST")
    rust_digest = _dockerfile_digest_default("RUST_DIGEST")
    checked = 0
    for name, svc in SERVICES.items():
        args = (svc.get("build") or {}).get("args") if isinstance(svc.get("build"), dict) else None
        if not args or "PYTHON_VERSION" not in args:
            continue
        checked += 1
        assert python_digest in str(args.get("PYTHON_DIGEST")), name
        if "RUST_VERSION" in args:
            # Services that do not pass a Rust version use the Dockerfile defaults for both.
            assert rust_digest in str(args.get("RUST_DIGEST")), name
    assert checked >= 1


def test_kubernetes_nginx_image_is_pinned_by_digest():
    images = re.findall(r"(?m)^\s+image: (\S*openresty\S*)\s*$", NGINX_K8S)
    assert images
    for image in images:
        assert "@sha256:" in image, image


def test_only_the_socket_proxy_and_opt_in_watchtower_mount_the_docker_socket():
    mounting = {
        name
        for name, svc in SERVICES.items()
        if any("docker.sock" in str(volume) for volume in svc.get("volumes", []))
    }
    assert mounting == {"docker_socket_proxy", "watchtower"}


def test_traefik_reads_containers_through_the_proxy_only():
    traefik = SERVICES["traefik"]
    assert not any("docker.sock" in str(volume) for volume in traefik.get("volumes", []))
    assert "--providers.docker.endpoint=tcp://docker_socket_proxy:2375" in traefik["command"]


def test_socket_proxy_is_read_only_and_isolated():
    proxy = SERVICES["docker_socket_proxy"]
    assert str(proxy["environment"]["POST"]) == "0"
    assert str(proxy["environment"]["CONTAINERS"]) == "1"
    assert "ports" not in proxy
    assert proxy["networks"] == ["docker_api"]
    assert COMPOSE["networks"]["docker_api"]["internal"] is True


def test_watchtower_is_opt_in_and_limited_to_labelled_containers():
    watchtower = SERVICES["watchtower"]
    assert watchtower["profiles"] == ["auto-update"]
    assert "--label-enable" in watchtower["command"]
