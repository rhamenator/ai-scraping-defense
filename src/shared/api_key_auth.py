from __future__ import annotations

import os
import secrets
from typing import Optional

from src.shared.config import get_secret


def load_api_key(env_var_name: str) -> Optional[str]:
    """Load an API key from an env var or an accompanying *_FILE secret.

    Example:
      - `FOO_API_KEY` (raw value)
      - `FOO_API_KEY_FILE` (path to file, or *_VAULT_PATH per get_secret)
    """

    return os.getenv(env_var_name) or get_secret(f"{env_var_name}_FILE")


def is_api_key_valid(provided: Optional[str], expected: str) -> bool:
    if not provided:
        return False
    return secrets.compare_digest(provided, expected)
