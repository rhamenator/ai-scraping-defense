#!/usr/bin/env python3
"""Interactive setup script for AI Scraping Defense.

This helper prompts for key configuration values, writes them to
`.env`, and then runs `scripts/linux/generate_secrets.sh --update-env`
to populate generated values.

It also supports pause/resume using a local state file, so users can
return later if required credentials are not available.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import platform
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
    "ENABLE_MCP_MODEL": {
        "prompt": "Use an MCP model server (the bundled Rust server or your own)?",
        "extras": [
            {
                "key": "MCP_SERVER_PRIMARY_TRANSPORT",
                "label": "MCP transport (ws or http)",
                "default": "ws",
                "required": True,
            },
            {
                "key": "MCP_SERVER_PRIMARY_URL",
                "label": "MCP server URL",
                "default": "ws://127.0.0.1:8085/mcp",
                "required": True,
            },
            {
                "key": "MCP_SERVER_PRIMARY_AUTH_TOKEN",
                "label": "MCP bearer token (type 'pause' to resume later)",
                "default": "",
                "required": True,
            },
        ],
    },
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
            {
                "key": "SECURITY_CDN_TRUSTED_PROXY_CIDRS",
                "label": "Trusted Cloudflare proxy CIDRs",
                "default": "",
                "required": True,
            },
            {
                "key": "SECURITY_CDN_ORIGIN_LOCKDOWN",
                "label": "Restrict origin to trusted CDN proxies only",
                "default": "true",
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
    write_private_text(path, "".join(lines))


def write_private_text(path: Path, text: str) -> None:
    """Write ``text`` so that only the owner can read it, from the first byte (#1912).

    The file is created with mode 0600 instead of being created with the default umask and tightened afterwards, and an
    existing file with wider permissions is tightened before anything is written. Windows ignores the mode bits.
    """
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
    except (AttributeError, OSError):  # not available on Windows
        pass
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(text)


def create_private_file(path: Path) -> None:
    """Create ``path`` empty with mode 0600 if it does not exist, and tighten it if it does."""
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
    except (AttributeError, OSError):  # not available on Windows
        pass
    os.close(descriptor)


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
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return {}


def save_setup_state(path: Path, completed_keys: set[str]) -> None:
    """Persist setup progress so users can resume later."""
    payload = {"completed_keys": sorted(completed_keys)}
    write_private_text(path, json.dumps(payload, indent=2, sort_keys=True))


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


def run_secrets_generator(root: Path, env: dict[str, str]) -> None:
    """Run the platform-appropriate secrets generator script."""
    is_windows = platform.system() == "Windows"
    generator_env = {**os.environ, **env}
    if is_windows:
        secrets_script = root / "scripts" / "windows" / "Generate-Secrets.ps1"
        # Controlled script call (repo-local path, fixed argv).
        subprocess.run(  # nosec B603
            ["powershell", "-File", str(secrets_script), "-UpdateEnv"],
            cwd=str(root),
            check=True,
            env=generator_env,
        )
        return
    secrets_script = root / "scripts" / "linux" / "generate_secrets.sh"
    # Controlled script call (repo-local path, fixed argv).
    subprocess.run(  # nosec B603
        ["bash", str(secrets_script), "--update-env"],
        cwd=str(root),
        check=True,
        env=generator_env,
    )


def _apply_web_updates(root: Path, env_file: Path, state_file: Path, updates: dict[str, str]) -> None:
    update_env_file(env_file, updates)
    clear_setup_state(state_file)
    run_secrets_generator(root, parse_env(env_file))


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Interactive setup for AI Scraping Defense.")
    parser.add_argument(
        "--web",
        action="store_true",
        help="Launch a temporary localhost-only pre-boot setup Web UI instead of CLI prompts.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind host for --web (default: 127.0.0.1).")
    parser.add_argument("--port", type=int, default=8765, help="Bind port for --web (default: 8765).")
    parser.add_argument("--no-browser", action="store_true", help="Do not auto-open browser in --web mode.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    root = Path(__file__).resolve().parent.parent
    is_windows = platform.system() == "Windows"
    env_file = root / ".env"
    sample_file = root / "sample.env"
    state_file = root / SETUP_STATE_FILENAME

    if not env_file.exists() and sample_file.exists():
        write_private_text(env_file, sample_file.read_text())
        print("Created .env from sample.env")

    if args.web:
        try:
            from scripts.interactive_setup_web import run_setup_web_server
        except ModuleNotFoundError:
            from interactive_setup_web import run_setup_web_server

        run_setup_web_server(
            root,
            {
                "parse_env_fn": parse_env,
                "apply_updates_fn": lambda updates: _apply_web_updates(root, env_file, state_file, updates),
                "key_settings": KEY_SETTINGS,
                "optional_features": OPTIONAL_FEATURES,
                "is_secret_fn": is_secret_key,
            },
            host=args.host,
            port=args.port,
            open_browser=not args.no_browser,
        )
        return

    _run_cli_setup(root, env_file, sample_file, state_file, is_windows)


def _load_resumable_keys(state_file: Path) -> set[str]:
    state = load_setup_state(state_file)
    completed_keys = set(state.get("completed_keys", []))
    if not completed_keys:
        return completed_keys
    if prompt_yes_no("Found unfinished setup progress. Resume where you left off?", default=True):
        print("Resuming setup using saved progress.")
        return completed_keys
    completed_keys.clear()
    clear_setup_state(state_file)
    print("Starting setup from the beginning.")
    return completed_keys


def _apply_cli_feature_rules(feature: str, env: dict[str, str], record_value) -> None:
    if feature == "ENABLE_GLOBAL_CDN":
        if env.get("CLOUD_CDN_PROVIDER", "").strip().lower() != "cloudflare":
            print("Only Cloudflare is currently supported for ENABLE_GLOBAL_CDN. Setting CLOUD_CDN_PROVIDER=cloudflare.")
            record_value("CLOUD_CDN_PROVIDER", "cloudflare")
        record_value("REQUIRE_CLOUDFLARE_ACCOUNT", "true")
    elif feature == "ENABLE_MCP_MODEL":
        record_value("MODEL_URI", "mcp://primary/classify")


def _prompt_optional_feature(
    feature: str,
    info: dict[str, Any],
    env: dict[str, str],
    completed_keys: set[str],
    record_value,
) -> None:
    if feature in completed_keys:
        enabled = env.get(feature, "false").lower() == "true"
    else:
        default_enabled = env.get(feature, "false").lower() == "true"
        enabled = prompt_yes_no(info["prompt"], default=default_enabled)
        record_value(feature, "true" if enabled else "false")
    if not enabled:
        return
    for extra in info.get("extras", []):
        key = extra["key"]
        if key not in completed_keys:
            default = env.get(key, extra.get("default", ""))
            value = prompt_value(
                key,
                f"  {extra.get('label', key)}",
                default,
                required=bool(extra.get("required", False)),
            )
            record_value(key, value)
    _apply_cli_feature_rules(feature, env, record_value)


def _run_platform_script(root: Path, is_windows: bool, win_name: str, linux_name: str) -> None:
    if is_windows:
        script_path = root / "scripts" / "windows" / win_name
        subprocess.run(["powershell", "-File", str(script_path)], cwd=str(root), check=True)  # nosec B603 B607
        return
    script_path = root / "scripts" / "linux" / linux_name
    subprocess.run(["bash", str(script_path)], cwd=str(root), check=True)  # nosec B603 B607


def _prompt_post_setup_actions(root: Path, is_windows: bool) -> None:
    resp = input("Launch the local Docker Compose stack now? [y/N]: ").strip().lower()  # nosec B322
    if resp == "y":
        _run_platform_script(root, is_windows, "quickstart_dev.ps1", "quickstart_dev.sh")
    resp = input("Deploy to Kubernetes using quick_deploy.sh now? [y/N]: ").strip().lower()  # nosec B322
    if resp == "y":
        _run_platform_script(root, is_windows, "quick_deploy.ps1", "quick_deploy.sh")


def _run_cli_setup(
    root: Path, env_file: Path, sample_file: Path, state_file: Path, is_windows: bool
) -> None:
    env = parse_env(env_file if env_file.exists() else sample_file)
    completed_keys = _load_resumable_keys(state_file)

    def record_value(key: str, value: str) -> None:
        env[key] = value
        update_env_file(env_file, {key: value})
        completed_keys.add(key)
        save_setup_state(state_file, completed_keys)

    try:
        print("Configure key settings (type 'pause' to save and exit):")
        for key in KEY_SETTINGS:
            if key not in completed_keys:
                record_value(key, prompt_value(key, key, env.get(key, ""), required=False))
        print("\nConfigure optional features:")
        for feature, info in OPTIONAL_FEATURES.items():
            _prompt_optional_feature(feature, info, env, completed_keys, record_value)
        if "REQUIRE_CLOUDFLARE_ACCOUNT" not in env:
            record_value("REQUIRE_CLOUDFLARE_ACCOUNT", "false")
        clear_setup_state(state_file)
    except (SetupPaused, KeyboardInterrupt) as exc:
        save_setup_state(state_file, completed_keys)
        print(f"\n{exc or 'Setup interrupted'}. Progress saved in {state_file.name}. Re-run this script to continue.")
        return

    print("Generating secrets...")
    run_secrets_generator(root, env)
    print("Setup complete. Updated .env and generated secrets.")
    _prompt_post_setup_actions(root, is_windows)


if __name__ == "__main__":  # pragma: no cover - manual usage
    main()
