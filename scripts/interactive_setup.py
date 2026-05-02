#!/usr/bin/env python3
"""Interactive setup script for AI Scraping Defense.

This helper prompts for key configuration values, writes them to
`.env`, optionally stores secrets in an SQLite database, and then runs
`scripts/linux/generate_secrets.sh --update-env` to populate generated values.

It also supports pause/resume using a local state file, so users can
return later if required credentials are not available.
"""

from __future__ import annotations

import getpass
import json
import platform
import sqlite3
import subprocess  # nosec B404 - required for controlled script calls
from pathlib import Path
from typing import Any

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

OPTIONAL_FEATURES = {
    "ENABLE_GLOBAL_CDN": {
        "prompt": "Enable Cloudflare CDN integration?",
        "extras": [
            {
                "key": "CLOUD_CDN_PROVIDER",
                "label": "CDN provider",
                "default": "cloudflare",
                "required": True,
            },
            {
                "key": "CLOUD_CDN_ZONE_ID",
                "label": "Cloudflare zone ID",
                "default": "",
                "required": True,
            },
            {
                "key": "CLOUD_CDN_API_TOKEN",
                "label": "Cloudflare API token (type 'pause' to resume later)",
                "default": "",
                "required": True,
            },
        ],
    },
    "ENABLE_DDOS_PROTECTION": {
        "prompt": "Enable DDoS mitigation service?",
        "extras": [
            {
                "key": "DDOS_PROTECTION_PROVIDER_URL",
                "label": "External provider URL",
                "default": "",
                "required": False,
            },
            {
                "key": "DDOS_PROTECTION_API_KEY",
                "label": "API key",
                "default": "",
                "required": False,
            },
        ],
    },
    "ENABLE_MANAGED_TLS": {
        "prompt": "Enable managed TLS certificates?",
        "extras": [
            {
                "key": "TLS_PROVIDER",
                "label": "TLS provider",
                "default": "certbot",
                "required": False,
            },
            {
                "key": "TLS_EMAIL",
                "label": "Contact email",
                "default": "",
                "required": False,
            },
        ],
    },
    "ENABLE_WAF": {
        "prompt": "Enable web application firewall?",
        "extras": [
            {
                "key": "WAF_RULES_PATH",
                "label": "Rules file path",
                "default": "/etc/nginx/waf_rules.conf",
                "required": False,
            },
        ],
    },
}

SETUP_STATE_FILENAME = ".interactive_setup_state.json"
SECRET_KEY_MARKERS = ("PASSWORD", "API_KEY", "SECRET", "TOKEN")


class SetupPaused(RuntimeError):
    """Raised when the user requests a resumable pause."""


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


def is_secret_key(key: str) -> bool:
    """Return True if the setting key should be treated as sensitive input."""
    upper = key.upper()
    return any(marker in upper for marker in SECRET_KEY_MARKERS)


def load_setup_state(path: Path) -> dict[str, Any]:
    """Load setup progress state from disk."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def save_setup_state(path: Path, completed_keys: set[str]) -> None:
    """Persist setup progress so users can resume later."""
    payload = {"completed_keys": sorted(completed_keys)}
    path.write_text(json.dumps(payload, indent=2, sort_keys=True))


def clear_setup_state(path: Path) -> None:
    """Remove setup progress marker after successful completion/reset."""
    if path.exists():
        path.unlink()


def prompt_yes_no(prompt: str, default: bool = False) -> bool:
    """Prompt for yes/no with a default."""
    suffix = "[Y/n]" if default else "[y/N]"
    raw = input(f"{prompt} {suffix}: ").strip().lower()  # nosec B322
    if not raw:
        return default
    return raw in {"y", "yes"}


def prompt_value(
    key: str,
    label: str,
    default: str,
    *,
    required: bool = False,
) -> str:
    """Prompt for a value with optional masking and required validation."""
    while True:
        if is_secret_key(key):
            hint = " [saved]" if default else ""
            raw = getpass.getpass(f"{label}{hint}: ").strip()
        else:
            prompt = f"{label} [{default}]: " if default else f"{label}: "
            raw = input(prompt).strip()  # nosec B322

        if raw.lower() == "pause":
            raise SetupPaused(f"Paused while prompting for {key}")

        value = raw if raw else default
        if required and not value:
            print(
                "This value is required. Enter it now, or type 'pause' to save progress and exit."
            )
            continue
        return value


def store_secrets(root: Path, env: dict[str, str]) -> None:
    """Store secrets in an SQLite database under secrets/ if user agrees."""
    resp = (
        input(  # nosec B322 - interactive prompt
            "Store secrets in local SQLite database? [y/N]: "
        )
        .strip()
        .lower()
    )
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
            if any(s in key for s in ("PASSWORD", "API_KEY", "SECRET", "TOKEN")):
                conn.execute(
                    "REPLACE INTO secrets (key, value) VALUES (?, ?)", (key, value)
                )
    print("Secrets have been stored in the local database.")


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    is_windows = platform.system() == "Windows"
    env_file = root / ".env"
    sample_file = root / "sample.env"
    state_file = root / SETUP_STATE_FILENAME

    if not env_file.exists() and sample_file.exists():
        env_file.write_text(sample_file.read_text())
        print("Created .env from sample.env")

    env = parse_env(env_file if env_file.exists() else sample_file)
    state = load_setup_state(state_file)
    completed_keys = set(state.get("completed_keys", []))

    if completed_keys:
        resume = prompt_yes_no(
            "Found unfinished setup progress. Resume where you left off?",
            default=True,
        )
        if not resume:
            completed_keys.clear()
            clear_setup_state(state_file)
            print("Starting setup from the beginning.")
        else:
            print("Resuming setup using saved progress.")

    def record_value(key: str, value: str) -> None:
        env[key] = value
        update_env_file(env_file, {key: value})
        completed_keys.add(key)
        save_setup_state(state_file, completed_keys)

    try:
        print("Configure key settings (type 'pause' to save and exit):")
        for key in KEY_SETTINGS:
            if key in completed_keys:
                continue
            default = env.get(key, "")
            value = prompt_value(key, key, default, required=False)
            record_value(key, value)

        print("\nConfigure optional features:")
        for feature, info in OPTIONAL_FEATURES.items():
            if feature in completed_keys:
                enabled = env.get(feature, "false").lower() == "true"
            else:
                default_enabled = env.get(feature, "false").lower() == "true"
                enabled = prompt_yes_no(info["prompt"], default=default_enabled)
                record_value(feature, "true" if enabled else "false")

            if not enabled:
                continue

            for extra in info.get("extras", []):
                key = extra["key"]
                if key in completed_keys:
                    continue
                default = env.get(key, extra.get("default", ""))
                value = prompt_value(
                    key,
                    f"  {extra.get('label', key)}",
                    default,
                    required=bool(extra.get("required", False)),
                )
                record_value(key, value)

            if feature == "ENABLE_GLOBAL_CDN":
                provider = env.get("CLOUD_CDN_PROVIDER", "").strip().lower()
                if provider != "cloudflare":
                    print(
                        "Only Cloudflare is currently supported for ENABLE_GLOBAL_CDN. "
                        "Setting CLOUD_CDN_PROVIDER=cloudflare."
                    )
                    record_value("CLOUD_CDN_PROVIDER", "cloudflare")
                record_value("REQUIRE_CLOUDFLARE_ACCOUNT", "true")

        if "REQUIRE_CLOUDFLARE_ACCOUNT" not in env:
            record_value("REQUIRE_CLOUDFLARE_ACCOUNT", "false")

        clear_setup_state(state_file)
    except SetupPaused as exc:
        save_setup_state(state_file, completed_keys)
        print(f"{exc}.")
        print(
            f"Setup paused and progress saved in {state_file.name}. Re-run this script to continue."
        )
        return
    except KeyboardInterrupt:
        save_setup_state(state_file, completed_keys)
        print(
            f"\nSetup interrupted. Progress saved in {state_file.name}. Re-run this script to continue."
        )
        return

    store_secrets(root, env)

    print("Generating secrets...")
    if is_windows:
        secrets_script = root / "scripts" / "windows" / "Generate-Secrets.ps1"
        # Controlled script call (repo-local path, fixed argv).
        subprocess.run(  # nosec B603
            ["powershell", "-File", str(secrets_script)],
            cwd=str(root),
            check=True,
        )
    else:
        secrets_script = root / "scripts" / "linux" / "generate_secrets.sh"
        # Controlled script call (repo-local path, fixed argv).
        subprocess.run(  # nosec B603
            ["bash", str(secrets_script), "--update-env"],
            cwd=str(root),
            check=True,
        )
    print("Setup complete. Updated .env and generated secrets.")

    resp = (
        input(  # nosec B322 - interactive prompt
            "Launch the local Docker Compose stack now? [y/N]: "
        )
        .strip()
        .lower()
    )
    if resp == "y":
        if is_windows:
            quickstart_script = root / "scripts" / "windows" / "quickstart_dev.ps1"
            # Controlled script call (repo-local path, fixed argv).
            subprocess.run(  # nosec B603
                ["powershell", "-File", str(quickstart_script)],
                cwd=str(root),
                check=True,
            )
        else:
            quickstart_script = root / "scripts" / "linux" / "quickstart_dev.sh"
            # Controlled script call (repo-local path, fixed argv).
            subprocess.run(  # nosec B603
                ["bash", str(quickstart_script)], cwd=str(root), check=True
            )

    resp = (
        input(  # nosec B322 - interactive prompt
            "Deploy to Kubernetes using quick_deploy.sh now? [y/N]: "
        )
        .strip()
        .lower()
    )
    if resp == "y":
        if is_windows:
            deploy_script = root / "scripts" / "windows" / "quick_deploy.ps1"
            # Controlled script call (repo-local path, fixed argv).
            subprocess.run(  # nosec B603
                ["powershell", "-File", str(deploy_script)],
                cwd=str(root),
                check=True,
            )
        else:
            deploy_script = root / "scripts" / "linux" / "quick_deploy.sh"
            # Controlled script call (repo-local path, fixed argv).
            subprocess.run(  # nosec B603
                ["bash", str(deploy_script)], cwd=str(root), check=True
            )


if __name__ == "__main__":  # pragma: no cover - manual usage
    main()
