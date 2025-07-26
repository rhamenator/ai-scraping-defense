#!/usr/bin/env python3
"""Interactive setup script for AI Scraping Defense.

This helper prompts for key configuration values, writes them to
`.env`, optionally stores secrets in an SQLite database, and then runs
`generate_secrets.sh --update-env` to populate generated values.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
from pathlib import Path


KEY_SETTINGS = [
    "MODEL_URI",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "COHERE_API_KEY",
    "MISTRAL_API_KEY",
    "EXTERNAL_API_KEY",
    "ESCALATION_API_KEY",
    "NGINX_HTTP_PORT",
    "NGINX_HTTPS_PORT",
    "ADMIN_UI_PORT",
    "REAL_BACKEND_HOST",
]


def parse_env(path: Path) -> dict[str, str]:
    """Parse simple KEY=VALUE lines from a .env style file."""
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


def update_env_file(path: Path, values: dict[str, str]) -> None:
    """Update or append KEY=VALUE lines in an env file."""
    lines = []
    seen = set()
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip() and not line.strip().startswith("#") and "=" in line:
                key = line.split("=", 1)[0]
                if key in values:
                    lines.append(f"{key}={values[key]}\n")
                    seen.add(key)
                    continue
            lines.append(line + "\n")
    for key, value in values.items():
        if key not in seen:
            lines.append(f"{key}={value}\n")
    path.write_text("".join(lines))


def store_secrets(root: Path, env: dict[str, str]) -> None:
    """Store secrets in an SQLite database under secrets/ if user agrees."""
    resp = input("Store secrets in local SQLite database? [y/N]: ").strip().lower()
    if resp != "y":
        return
    secrets_dir = root / "secrets"
    secrets_dir.mkdir(exist_ok=True)
    db_path = secrets_dir / "local_secrets.db"
    conn = sqlite3.connect(db_path)
    with conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS secrets (key TEXT PRIMARY KEY, value TEXT)"
        )
        for key, value in env.items():
            if any(s in key for s in ("PASSWORD", "API_KEY", "SECRET")):
                conn.execute(
                    "REPLACE INTO secrets (key, value) VALUES (?, ?)", (key, value)
                )
    print("Secrets have been stored in the local database.")


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    env_file = root / ".env"
    sample_file = root / "sample.env"

    if not env_file.exists() and sample_file.exists():
        env_file.write_text(sample_file.read_text())
        print("Created .env from sample.env")

    env = parse_env(env_file if env_file.exists() else sample_file)

    print("Configure key settings (leave blank to keep defaults):")
    updates: dict[str, str] = {}
    for key in KEY_SETTINGS:
        default = env.get(key, "")
        prompt = f"{key} [{default}]: " if default else f"{key}: "
        val = input(prompt).strip()
        updates[key] = val if val else default

    env.update(updates)
    update_env_file(env_file, updates)
    store_secrets(root, env)

    print("Running generate_secrets.sh --update-env ...")
    subprocess.run(["bash", "generate_secrets.sh", "--update-env"], cwd=root, check=True)
    print("Setup complete. Updated .env and generated secrets.")

    resp = input("Launch the local Docker Compose stack now? [y/N]: ").strip().lower()
    if resp == "y":
        subprocess.run(["bash", "quickstart_dev.sh"], cwd=root, check=True)

    resp = input("Deploy to Kubernetes using quick_deploy.sh now? [y/N]: ").strip().lower()
    if resp == "y":
        subprocess.run(["bash", "quick_deploy.sh"], cwd=root, check=True)


if __name__ == "__main__":  # pragma: no cover - manual usage
    main()
