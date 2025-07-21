# src/tarpit/bad_api_generator.py
"""Generate deceptive API endpoints for the tarpit honeypot."""

from __future__ import annotations

import logging
import random
import string
from typing import List

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

try:
    from src.shared.honeypot_logger import log_honeypot_hit

    HONEYPOT_LOGGING_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    HONEYPOT_LOGGING_AVAILABLE = False

    def log_honeypot_hit(details: dict) -> None:  # type: ignore[empty-body]
        return


logger = logging.getLogger(__name__)

COMMON_PREFIXES = ["v1", "v2", "internal", "private"]
RESOURCE_NAMES = [
    "config",
    "data",
    "auth",
    "report",
    "metrics",
    "status",
    "secrets",
]

GENERATED_BAD_API_ENDPOINTS: List[str] = []


def _rand_str(length: int = 6) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


def generate_bad_endpoints(count: int = 5) -> List[str]:
    """Return a list of fake API endpoint paths."""
    endpoints: List[str] = []
    for _ in range(count):
        prefix = random.choice(COMMON_PREFIXES)
        resource = random.choice(RESOURCE_NAMES)
        unique = _rand_str()
        endpoints.append(f"/{prefix}/{resource}/{unique}")
    return endpoints


def register_bad_endpoints(app: FastAPI, count: int = 5) -> List[str]:
    """Register fake API endpoints on the provided FastAPI app."""
    endpoints = generate_bad_endpoints(count)
    global GENERATED_BAD_API_ENDPOINTS
    GENERATED_BAD_API_ENDPOINTS = endpoints

    for path in endpoints:

        async def handler(request: Request, path: str = path):
            client_ip = request.client.host if request.client else "unknown"
            ua = request.headers.get("user-agent", "unknown")
            details = {
                "ip": client_ip,
                "user_agent": ua,
                "path": f"/api{path}",
                "method": request.method,
            }
            if HONEYPOT_LOGGING_AVAILABLE:
                try:
                    log_honeypot_hit(details)
                except Exception as exc:  # pragma: no cover - log unexpected error
                    logger.error(f"Error logging honeypot hit: {exc}", exc_info=True)
            logger.info(f"BAD API HIT: /api{path} from {client_ip}")
            return JSONResponse({"detail": "Invalid API endpoint"}, status_code=404)

        app.add_api_route(
            f"/api{path}",
            handler,
            methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
        )
    return endpoints
