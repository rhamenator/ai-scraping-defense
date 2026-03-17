from __future__ import annotations

import os
from enum import Enum
from typing import Mapping


class InternalAuthMode(str, Enum):
    SHARED_KEY = "shared_key"


def load_internal_auth_mode(
    env: Mapping[str, str] | None = None,
) -> InternalAuthMode:
    source = env or os.environ
    raw_value = source.get("INTERNAL_AUTH_MODE", InternalAuthMode.SHARED_KEY.value)
    normalized = raw_value.strip().lower()
    try:
        return InternalAuthMode(normalized)
    except ValueError as exc:
        raise ValueError(
            "INTERNAL_AUTH_MODE must be one of: "
            + ", ".join(mode.value for mode in InternalAuthMode)
        ) from exc


def build_cloud_proxy_headers(
    env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    source = env or os.environ
    auth_mode = load_internal_auth_mode(source)
    if auth_mode is InternalAuthMode.SHARED_KEY:
        proxy_key = source.get("PROXY_KEY", "").strip()
        if not proxy_key:
            raise RuntimeError(
                "PROXY_KEY is required when INTERNAL_AUTH_MODE=shared_key"
            )
        return {"X-Proxy-Key": proxy_key}
    return {}
