"""Shared post-install smoke test contract for Docker-based installs."""

from __future__ import annotations

import argparse
import re
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass(frozen=True)
class SmokeConfig:
    platform: str
    proxy: str
    docker_context: str = "default"


class SmokeFailure(RuntimeError):
    """Raised when a smoke-test contract assertion fails."""


CORE_SERVICES = (
    "postgres_markov_db",
    "redis_store",
    "admin_ui",
    "escalation_engine",
    "tarpit_api",
)
PROXY_CONTAINERS = {
    "nginx": "nginx_proxy",
    "apache": "apache_proxy",
}


def docker_prefix(docker_context: str) -> list[str]:
    return ["docker", "--context", docker_context]


def run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )


def run_docker(config: SmokeConfig, *args: str) -> subprocess.CompletedProcess[str]:
    return run_command(docker_prefix(config.docker_context) + list(args))


def fail(message: str) -> None:
    raise SmokeFailure(message)


def assert_running_and_healthy(config: SmokeConfig, container: str) -> None:
    status = run_docker(
        config, "inspect", "-f", "{{.State.Status}}", container
    ).stdout.strip()
    if status != "running":
        fail(f"{container} is not running (status={status or 'missing'})")

    health = run_docker(
        config,
        "inspect",
        "-f",
        "{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}",
        container,
    ).stdout.strip()
    if health not in {"none", "healthy"}:
        fail(f"{container} health is not healthy (health={health})")

    print(f"[OK] {container} is running (health={health})")


def host_port_for_container(config: SmokeConfig, container: str, port: str) -> str:
    result = run_docker(
        config,
        "inspect",
        "-f",
        f'{{{{(index (index .NetworkSettings.Ports "{port}") 0).HostPort}}}}',
        container,
    )
    host_port = result.stdout.strip()
    if not host_port:
        fail(f"{container} does not expose {port}")
    return host_port


def assert_http(url: str, *, insecure: bool = False) -> None:
    context = ssl._create_unverified_context() if insecure else None
    try:
        with urllib.request.urlopen(url, timeout=10, context=context) as response:
            if response.status >= 400:
                fail(f"{url} returned HTTP {response.status}")
    except urllib.error.URLError as exc:
        fail(f"{url} is not reachable ({exc})")


def assert_container_http(
    config: SmokeConfig, container: str, url: str, expected_pattern: str | None = None
) -> None:
    result = run_docker(config, "exec", container, "curl", "-fsS", url)
    if result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip()
        fail(f"{container} could not reach {url} ({stderr})")
    if expected_pattern and not re.search(expected_pattern, result.stdout):
        fail(
            f"{container} returned unexpected payload for {url}: {result.stdout.strip()}"
        )


def run_smoke_test(config: SmokeConfig) -> None:
    if config.proxy not in PROXY_CONTAINERS:
        raise ValueError(f"Unsupported proxy: {config.proxy}")

    print(f"=== Stack Smoke Test ({config.platform} / {config.proxy}) ===")

    proxy_container = PROXY_CONTAINERS[config.proxy]
    for container in (*CORE_SERVICES, proxy_container):
        assert_running_and_healthy(config, container)

    http_port = host_port_for_container(config, proxy_container, "80/tcp")
    assert_http(f"http://127.0.0.1:{http_port}/")
    print(f"[OK] {proxy_container} HTTP is reachable on port {http_port}")

    if config.proxy == "nginx":
        https_port = host_port_for_container(config, proxy_container, "443/tcp")
        assert_http(f"https://127.0.0.1:{https_port}/", insecure=True)
        print(f"[OK] nginx_proxy HTTPS is reachable on port {https_port}")

    assert_container_http(
        config, "admin_ui", "http://127.0.0.1:5002/observability/health"
    )
    print("[OK] admin_ui health endpoint is reachable")

    assert_container_http(config, "tarpit_api", "http://127.0.0.1:8001/health")
    print("[OK] tarpit_api health endpoint is reachable")

    assert_container_http(
        config,
        "escalation_engine",
        "http://127.0.0.1:8003/health",
        expected_pattern=r'"status":"(healthy|degraded)"',
    )
    print("[OK] escalation_engine health payload is acceptable")
    print("Smoke test passed.")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--platform",
        default="linux",
        choices=("linux", "windows", "macos"),
        help="Platform label for the smoke-test banner",
    )
    parser.add_argument(
        "--proxy",
        default="nginx",
        choices=tuple(PROXY_CONTAINERS),
        help="Reverse proxy under test",
    )
    parser.add_argument(
        "--docker-context",
        default="default",
        help="Docker context to target",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = SmokeConfig(
        platform=args.platform,
        proxy=args.proxy,
        docker_context=args.docker_context,
    )
    try:
        run_smoke_test(config)
    except SmokeFailure as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
