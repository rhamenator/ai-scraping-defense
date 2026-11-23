#!/usr/bin/env python3
"""Render a least-privilege Redis ACL file from ``redis/users.acl.template``."""

from __future__ import annotations

import os
import secrets
from pathlib import Path

PLACEHOLDERS = (
    "__DEFAULT_PASSWORD__",
    "__NGINX_PASSWORD__",
    "__CAPTCHA_PASSWORD__",
    "__TARPIT_PASSWORD__",
    "__ESCALATION_PASSWORD__",
    "__ADMIN_UI_PASSWORD__",
)


def render_acl(template_path: Path, output_path: Path, passwords: dict[str, str] | None = None) -> dict[str, str]:
    """Write ``output_path`` (mode 0600) with distinct per-service Redis ACL passwords."""
    template = template_path.read_text(encoding="utf-8")
    resolved = dict(passwords or {})
    rendered = template
    for placeholder in PLACEHOLDERS:
        secret = resolved.setdefault(placeholder, secrets.token_urlsafe(24))
        rendered = rendered.replace(placeholder, secret)
    output_path.parent.mkdir(mode=0o700, exist_ok=True)
    fd = os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.chmod(output_path, 0o600)
        os.write(fd, rendered.encode("utf-8"))
    finally:
        os.close(fd)
    return resolved
