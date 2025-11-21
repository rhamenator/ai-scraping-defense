"""Shared middleware for API services with secure defaults."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import deque
from dataclasses import dataclass
from typing import Any

from cachetools import TTLCache
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from .observability import (
    ObservabilitySettings,
    configure_observability,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SecuritySettings:
    """Runtime configuration for security middleware."""

    rate_limit_requests: int
    rate_limit_window: int
    max_body_size: int
    enable_https: bool


def _parse_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        raise ValueError(f"Environment variable {name} must be a positive integer, got {value!r}")
    if parsed <= 0:
        raise ValueError(f"Environment variable {name} must be a positive integer, got {parsed!r}")
    return parsed
def _load_security_settings() -> SecuritySettings:
    """Load security middleware settings from environment variables."""

    return SecuritySettings(
        rate_limit_requests=_parse_int("RATE_LIMIT_REQUESTS", 100),
        rate_limit_window=_parse_int("RATE_LIMIT_WINDOW", 60),
        max_body_size=_parse_int("MAX_BODY_SIZE", 1 * 1024 * 1024),
        enable_https=os.getenv("ENABLE_HTTPS", "false").lower() == "true",
    )


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory IP-based rate limiter."""

    def __init__(self, app: FastAPI, max_requests: int, window_seconds: int) -> None:
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: TTLCache[str, deque[float]] = TTLCache(
            maxsize=10000, ttl=window_seconds * 2
        )
        self._lock = asyncio.Lock()

    async def dispatch(self, request: Request, call_next):
        if self.max_requests <= 0:
            return await call_next(request)
        ip = request.client.host if request.client else "unknown"
        now = time.time()
        async with self._lock:
            bucket = self._requests.get(ip)
            if bucket is None:
                bucket = deque()
            else:
                cutoff = now - self.window_seconds
                while bucket and bucket[0] <= cutoff:
                    bucket.popleft()
                if not bucket:
                    self._requests.pop(ip, None)
                    bucket = deque()
            if len(bucket) >= self.max_requests:
                return JSONResponse(
                    status_code=429, content={"detail": "Too Many Requests"}
                )
            bucket.append(now)
            self._requests[ip] = bucket
        return await call_next(request)


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests with bodies exceeding the configured limit."""

    def __init__(self, app: FastAPI, max_body_size: int) -> None:
        super().__init__(app)
        self.max_body_size = max_body_size

    async def dispatch(self, request: Request, call_next):
        if self.max_body_size <= 0:
            return await call_next(request)
        length = request.headers.get("content-length")
        if length and int(length) > self.max_body_size:
            return JSONResponse(
                status_code=413, content={"detail": "Request body too large"}
            )

        size = 0
        body = bytearray()
        async for chunk in request.stream():
            size += len(chunk)
            if size > self.max_body_size:
                return JSONResponse(
                    status_code=413, content={"detail": "Request body too large"}
                )
            body.extend(chunk)

        if body:
            body_bytes = bytes(body)
            received = False

            async def receive() -> dict:
                nonlocal received
                if received:
                    return {"type": "http.request", "body": b"", "more_body": False}
                received = True
                return {
                    "type": "http.request",
                    "body": body_bytes,
                    "more_body": False,
                }

            request._receive = receive  # type: ignore[attr-defined]
            request._body = body_bytes  # type: ignore[attr-defined]
            request._stream_consumed = False  # type: ignore[attr-defined]
        return await call_next(request)


class InsiderThreatMiddleware(BaseHTTPMiddleware):
    """Monitor user behavior for insider threat detection."""

    def __init__(self, app: FastAPI) -> None:
        super().__init__(app)
        self._enabled = os.getenv("INSIDER_THREAT_DETECTION_ENABLED", "true").lower() == "true"
        self._sensitive_paths = [
            "/admin",
            "/api/secrets",
            "/api/config",
            "/api/users",
            "/api/audit",
        ]

    async def dispatch(self, request: Request, call_next):
        if not self._enabled:
            return await call_next(request)

        # Extract user information from request state or headers
        user_id = getattr(request.state, "user_id", None)
        if not user_id:
            # Try to extract from Authorization header or other auth mechanism
            auth_header = request.headers.get("authorization", "")
            if auth_header.startswith("Bearer "):
                # In a real implementation, decode the JWT token
                user_id = "authenticated_user"

        if user_id:
            try:
                from src.security.insider_threat import get_insider_threat_detector

                detector = get_insider_threat_detector()
                client_ip = request.client.host if request.client else "unknown"
                user_agent = request.headers.get("user-agent", "")
                endpoint = str(request.url.path)

                # Check if accessing sensitive resource
                is_sensitive = any(endpoint.startswith(path) for path in self._sensitive_paths)

                # Record the access
                detector.record_access(
                    user_id=user_id,
                    endpoint=endpoint,
                    client_ip=client_ip,
                    user_agent=user_agent,
                    is_sensitive=is_sensitive,
                )

                # Analyze for threats
                threat = detector.analyze_user(user_id)
                if threat and threat.risk_score >= 0.8:
                    # High-risk threat detected - could block or flag
                    logger.warning(
                        f"High-risk insider threat detected for user {user_id}: "
                        f"{threat.threat_type} (score: {threat.risk_score:.2f})"
                    )
            except Exception as e:
                # Don't block requests if monitoring fails
                logger.error(f"Error in insider threat monitoring: {e}")

        return await call_next(request)


def add_security_middleware(
    app: FastAPI, security_settings: SecuritySettings | None = None
) -> SecuritySettings:
    settings = security_settings or _load_security_settings()

    app.add_middleware(InsiderThreatMiddleware)
    app.add_middleware(BodySizeLimitMiddleware, max_body_size=settings.max_body_size)
    app.add_middleware(
        RateLimitMiddleware,
        max_requests=settings.rate_limit_requests,
        window_seconds=settings.rate_limit_window,
    )
    # Add standard security headers to all responses
    @app.middleware("http")
    async def _security_headers(request, call_next):
        response = await call_next(request)
        # Clickjacking and MIME sniffing protections
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        # Legacy XSS header (modern browsers rely on CSP); included per security baseline
        response.headers.setdefault("X-XSS-Protection", "1; mode=block")
        # Provide a conservative default CSP if not already set upstream
        response.headers.setdefault("Content-Security-Policy", "default-src 'self'")
        # Enable HSTS when HTTPS is enabled. Header is ignored over plain HTTP.
        if settings.enable_https:
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains; preload",
            )
        return response

    return settings


def create_app(
    *,
    security_settings: SecuritySettings | None = None,
    observability_settings: ObservabilitySettings | None = None,
    **kwargs: Any,
) -> FastAPI:
    app = FastAPI(**kwargs)
    add_security_middleware(app, security_settings=security_settings)
    configure_observability(app, settings=observability_settings)
    return app
