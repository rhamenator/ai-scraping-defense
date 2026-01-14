"""Central configuration dataclass and helpers for environment settings."""

import logging
import os
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


def _fetch_vault_secret(secret_path: str, key: str = "value") -> Optional[str]:
    """
    Retrieve a secret from HashiCorp Vault using the enhanced vault_client.

    Args:
        secret_path: Path to the secret in Vault (e.g., 'myapp/database')
        key: Key within the secret data (default: 'value')

    Returns:
        Secret value as string or None if not found
    """
    try:
        # Use the enhanced vault client if available
        from src.shared.vault_client import get_vault_client

        vault_client = get_vault_client()
        if vault_client:
            secret = vault_client.get_secret_value(secret_path, key)
            if secret is not None:
                return secret

        # Fallback to legacy HTTP method for backward compatibility
        vault_addr = os.getenv("VAULT_ADDR")
        token = os.getenv("VAULT_TOKEN")
        if not (vault_addr and token):
            return None

        # Parse path to determine mount point and secret path
        # Format: <mount_point>/data/<path> for KV v2
        parts = secret_path.lstrip("/").split("/", 1)
        if len(parts) == 2 and parts[0]:
            mount_point = parts[0]
            path = parts[1]
            # Remove 'data/' prefix if present (KV v2 API)
            if path.startswith("data/"):
                path = path[5:]
            url = f"{vault_addr.rstrip('/')}/v1/{mount_point}/data/{path}"
        else:
            url = f"{vault_addr.rstrip('/')}/v1/{secret_path.lstrip('/')}"

        with requests.get(url, headers={"X-Vault-Token": token}, timeout=5) as resp:
            if resp.ok:
                data = resp.json().get("data", {}).get("data", {})
                secret = data.get(key)
            else:
                secret = None
    except ImportError:
        logger.warning("vault_client not available, using legacy HTTP method")
        vault_addr = os.getenv("VAULT_ADDR")
        token = os.getenv("VAULT_TOKEN")
        if not (vault_addr and token):
            return None
        url = f"{vault_addr.rstrip('/')}/v1/{secret_path.lstrip('/')}"
        try:
            with requests.get(url, headers={"X-Vault-Token": token}, timeout=5) as resp:
                if resp.ok:
                    data = resp.json().get("data", {}).get("data", {})
                    secret = data.get(key)
                else:
                    secret = None
        except requests.RequestException as exc:
            logger.warning("Could not read secret from Vault at %s: %s", secret_path, exc)
            return None
    except requests.RequestException as exc:
        logger.warning("Could not read secret from Vault at %s: %s", secret_path, exc)
        return None
    except Exception as exc:
        logger.warning("Error fetching secret from Vault at %s: %s", secret_path, exc)
        return None

    try:
        return secret
    finally:
        if secret is not None:
            del secret


def get_secret(file_variable_name: str) -> Optional[str]:
    """Read a secret from a file or Vault and clear variables after use."""
    vault_path = os.environ.get(f"{file_variable_name}_VAULT_PATH")
    if vault_path:
        secret = _fetch_vault_secret(vault_path)
        if secret is not None:
            try:
                return secret
            finally:
                del secret

    file_path = os.environ.get(file_variable_name)
    if file_path and os.path.exists(file_path):
        try:
            with open(file_path, "r") as f:
                secret = f.read().strip()
            try:
                return secret
            finally:
                del secret
        except IOError as exc:
            logger.warning("Could not read secret file at %s: %s", file_path, exc)
    return None


@dataclass(frozen=True)
class Config:
    """Configuration loaded from environment variables once on import."""

    # Internal service hosts
    AI_SERVICE_HOST: str = field(
        default_factory=lambda: os.getenv("AI_SERVICE_HOST", "ai_service")
    )
    ESCALATION_ENGINE_HOST: str = field(
        default_factory=lambda: os.getenv("ESCALATION_ENGINE_HOST", "escalation_engine")
    )
    TARPIT_API_HOST: str = field(
        default_factory=lambda: os.getenv("TARPIT_API_HOST", "tarpit_api")
    )
    ADMIN_UI_HOST: str = field(
        default_factory=lambda: os.getenv("ADMIN_UI_HOST", "admin_ui")
    )
    CLOUD_DASHBOARD_HOST: str = field(
        default_factory=lambda: os.getenv("CLOUD_DASHBOARD_HOST", "cloud_dashboard")
    )
    CONFIG_RECOMMENDER_HOST: str = field(
        default_factory=lambda: os.getenv(
            "CONFIG_RECOMMENDER_HOST", "config_recommender"
        )
    )
    PROMPT_ROUTER_HOST: str = field(
        default_factory=lambda: os.getenv("PROMPT_ROUTER_HOST", "prompt_router")
    )

    # Service ports
    AI_SERVICE_PORT: int = field(
        default_factory=lambda: int(os.getenv("AI_SERVICE_PORT", 8000))
    )
    ESCALATION_ENGINE_PORT: int = field(
        default_factory=lambda: int(os.getenv("ESCALATION_ENGINE_PORT", 8003))
    )
    TARPIT_API_PORT: int = field(
        default_factory=lambda: int(os.getenv("TARPIT_API_PORT", 8001))
    )
    ADMIN_UI_PORT: int = field(
        default_factory=lambda: int(os.getenv("ADMIN_UI_PORT", 5002))
    )
    CLOUD_DASHBOARD_PORT: int = field(
        default_factory=lambda: int(os.getenv("CLOUD_DASHBOARD_PORT", 5006))
    )
    CONFIG_RECOMMENDER_PORT: int = field(
        default_factory=lambda: int(os.getenv("CONFIG_RECOMMENDER_PORT", 8010))
    )
    PROMPT_ROUTER_PORT: int = field(
        default_factory=lambda: int(os.getenv("PROMPT_ROUTER_PORT", 8009))
    )

    # Redis
    REDIS_HOST: str = field(default_factory=lambda: os.getenv("REDIS_HOST", "redis"))
