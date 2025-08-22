#!/usr/bin/env python3
"""Validate required settings in the .env file."""
from __future__ import annotations

import argparse
import json  # noqa: F401
import logging  # noqa: F401
import os  # noqa: F401
from pathlib import Path


def parse_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key] = value
    return env


# Keys that must be present in the environment configuration
REQUIRED_KEYS = [
    "MODEL_URI",
    "NGINX_HTTP_PORT",
    "NGINX_HTTPS_PORT",
    "ADMIN_UI_PORT",
    # Internal service ports
    "PROMPT_ROUTER_PORT",
    "PROMETHEUS_PORT",
    "GRAFANA_PORT",
    "PROMPT_ROUTER_HOST",
]

PROVIDER_KEYS = {
    "openai://": "OPENAI_API_KEY",
    "mistral://": "MISTRAL_API_KEY",
    "anthropic://": "ANTHROPIC_API_KEY",
    "google://": "GOOGLE_API_KEY",
    "cohere://": "COHERE_API_KEY",
}


def validate_env(env: dict[str, str]) -> list[str]:
    errors: list[str] = []

    for key in REQUIRED_KEYS:
        if not env.get(key):
            errors.append(f"{key} is missing or empty")

    model_uri = env.get("MODEL_URI", "")
    for prefix, key in PROVIDER_KEYS.items():
        if model_uri.startswith(prefix) and not env.get(key):
            errors.append(f"{key} required for MODEL_URI {model_uri}")

    for key in (
        "NGINX_HTTP_PORT",
        "NGINX_HTTPS_PORT",
        "ADMIN_UI_PORT",
        "PROMPT_ROUTER_PORT",
        "PROMETHEUS_PORT",
        "GRAFANA_PORT",
    ):
        value = env.get(key)
        try:
            port = int(value)
            if not 1 <= port <= 65535:
                raise ValueError
        except Exception:
            errors.append(f"{key} has invalid port value: {value}")

    if not env.get("REAL_BACKEND_HOST") and not env.get("REAL_BACKEND_HOSTS"):
        errors.append("REAL_BACKEND_HOST or REAL_BACKEND_HOSTS must be set")
    if not env.get("PROMPT_ROUTER_HOST"):
        errors.append("PROMPT_ROUTER_HOST is missing or empty")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate .env configuration")
    parser.add_argument(
        "env_path",
        nargs="?",
        default=".env",
        help="Path to the env file (default: .env)",
    )
    args = parser.parse_args()
    env_file = Path(args.env_path)

    env = parse_env(env_file)
    errors = validate_env(env)

    if errors:
        for err in errors:
            print(f"ERROR: {err}")
        return 1

    print("Environment looks valid.")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI execution
    raise SystemExit(main())
