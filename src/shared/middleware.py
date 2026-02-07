"""Shared middleware for API services with secure defaults."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import deque
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from cachetools import TTLCache
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse

from .errors import register_error_handlers
from .observability import ObservabilitySettings, configure_observability

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
        raise ValueError(
            f"Environment variable {name} must be a positive integer, got {value!r}"
        )
    if parsed <= 0:
        raise ValueError(
            f"Environment variable {name} must be a positive integer, got {parsed!r}"
        )
    return parsed


def _load_security_settings() -> SecuritySettings:
    """Load security middleware settings from environment variables."""

    return SecuritySettings(
        rate_limit_requests=_parse_int("RATE_LIMIT_REQUESTS", 100),
        rate_limit_window=_parse_int("RATE_LIMIT_WINDOW", 60),
        max_body_size=_parse_int("MAX_BODY_SIZE", 1 * 1024 * 1024),
        enable_https=os.getenv("ENABLE_HTTPS", "false").lower() == "true",
    )


def _header_override(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value else default


def _parse_non_negative_int(name: str, default: int) -> int:
    """Parse an integer env var allowing 0 to disable a check."""

    value = os.getenv(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        raise ValueError(
            f"Environment variable {name} must be an integer, got {value!r}"
        )
    if parsed < 0:
        raise ValueError(
            f"Environment variable {name} must be a non-negative integer, got {parsed!r}"
        )
    return parsed


def _parse_host_list(name: str) -> list[str]:
    """Parse a comma-separated list of hosts or host:port values."""

    raw = os.getenv(name, "")
    hosts = [entry.strip().lower() for entry in raw.split(",") if entry.strip()]
    seen: set[str] = set()
    unique: list[str] = []
    for host in hosts:
        if host not in seen:
            seen.add(host)
            unique.append(host)
    return unique


class RequestTargetLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests with unusually large request targets or headers."""

    def __init__(
        self,
        app: FastAPI,
        *,
        max_path_length: int,
        max_query_string_length: int,
        max_header_count: int,
        max_header_value_length: int,
    ) -> None:
        super().__init__(app)
        self.max_path_length = max_path_length
        self.max_query_string_length = max_query_string_length
        self.max_header_count = max_header_count
        self.max_header_value_length = max_header_value_length

    async def dispatch(self, request: Request, call_next):
        if self.max_path_length:
            raw_path = request.scope.get("raw_path") or request.url.path.encode()
            if len(raw_path) > self.max_path_length:
                return JSONResponse(
                    status_code=414, content={"detail": "Request-URI too long"}
                )

        if self.max_query_string_length:
            query = request.scope.get("query_string", b"")
            if len(query) > self.max_query_string_length:
                return JSONResponse(
                    status_code=414, content={"detail": "Request-URI too long"}
                )

        headers = request.scope.get("headers", [])
        if self.max_header_count and len(headers) > self.max_header_count:
            return JSONResponse(
                status_code=431, content={"detail": "Request header fields too large"}
            )

        if self.max_header_value_length:
            for _, value in headers:
                if len(value) > self.max_header_value_length:
                    return JSONResponse(
                        status_code=431,
                        content={"detail": "Request header fields too large"},
                    )

        return await call_next(request)


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


class GDPRComplianceMiddleware(BaseHTTPMiddleware):
    """Middleware to apply GDPR data minimization and privacy controls."""

    async def dispatch(self, request: Request, call_next):
        # Import here to avoid circular dependency
        try:
            from .gdpr import get_gdpr_manager

            gdpr = get_gdpr_manager()

            # Extract request data
            import datetime

            request_data = {
                "ip_address": request.client.host if request.client else "unknown",
                "user_agent": request.headers.get("user-agent", ""),
                "path": request.url.path,
                "method": request.method,
                "timestamp": datetime.datetime.now(datetime.timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
            }

            # Apply data minimization
            minimized_data = gdpr.minimize_data(request_data)

            # Store minimized data in request state for downstream use
            request.state.gdpr_minimized_data = minimized_data

        except Exception as e:
            # Don't block requests if GDPR processing fails
            logger.warning(f"GDPR middleware error: {e}")

        return await call_next(request)


def add_security_middleware(
    app: FastAPI, security_settings: SecuritySettings | None = None
) -> SecuritySettings:
    settings = security_settings or _load_security_settings()

    # Add GDPR compliance middleware first (innermost)
    gdpr_enabled = os.getenv("GDPR_ENABLED", "true").lower() == "true"
    if gdpr_enabled:
        app.add_middleware(GDPRComplianceMiddleware)

    app.add_middleware(
        RequestTargetLimitMiddleware,
        max_path_length=_parse_non_negative_int("SECURITY_MAX_PATH_LENGTH", 2048),
        max_query_string_length=_parse_non_negative_int(
            "SECURITY_MAX_QUERY_STRING_LENGTH", 4096
        ),
        max_header_count=_parse_non_negative_int("SECURITY_MAX_HEADER_COUNT", 100),
        max_header_value_length=_parse_non_negative_int(
            "SECURITY_MAX_HEADER_VALUE_LENGTH", 8192
        ),
    )

    app.add_middleware(BodySizeLimitMiddleware, max_body_size=settings.max_body_size)
    app.add_middleware(
        RateLimitMiddleware,
        max_requests=settings.rate_limit_requests,
        window_seconds=settings.rate_limit_window,
    )
    if settings.enable_https:
        canonical = os.getenv("SECURITY_HTTPS_REDIRECT_CANONICAL_HOST", "").strip()
        allowed_hosts = _parse_host_list("SECURITY_HTTPS_REDIRECT_ALLOWED_HOSTS")

        @app.middleware("http")
        async def _enforce_https(request, call_next):
            forwarded = request.headers.get("x-forwarded-proto")
            scheme = (
                forwarded.split(",")[0].strip() if forwarded else request.url.scheme
            )
            if scheme != "https":
                current_netloc = (request.url.netloc or "").lower()
                target_netloc = current_netloc
                if canonical:
                    target_netloc = canonical
                elif allowed_hosts:
                    if current_netloc not in allowed_hosts:
                        target_netloc = allowed_hosts[0]
                        logger.warning(
                            "HTTPS redirect host %r not in allowlist; redirecting to %r",
                            current_netloc,
                            target_netloc,
                        )

                safe_path = quote(request.url.path, safe="/%")
                return RedirectResponse(
                    url=str(
                        request.url.replace(
                            scheme="https",
                            netloc=target_netloc,
                            path=safe_path,
                            query=request.url.query,
                        )
                    ),
                    status_code=307,
                )
            return await call_next(request)

    # Add standard security headers to all responses
    @app.middleware("http")
    async def _security_headers(request, call_next):
        response = await call_next(request)
        header_defaults = {
            "X-Frame-Options": _header_override(
                "SECURITY_HEADER_X_FRAME_OPTIONS", "DENY"
            ),
            "X-Content-Type-Options": _header_override(
                "SECURITY_HEADER_X_CONTENT_TYPE_OPTIONS", "nosniff"
            ),
            "Referrer-Policy": _header_override(
                "SECURITY_HEADER_REFERRER_POLICY", "no-referrer"
            ),
            "Permissions-Policy": _header_override(
                "SECURITY_HEADER_PERMISSIONS_POLICY",
                "geolocation=(), microphone=(), camera=()",
            ),
            "X-Permitted-Cross-Domain-Policies": _header_override(
                "SECURITY_HEADER_X_PERMITTED_CROSS_DOMAIN_POLICIES", "none"
            ),
            "X-XSS-Protection": _header_override(
                "SECURITY_HEADER_X_XSS_PROTECTION", "1; mode=block"
            ),
            "Content-Security-Policy": _header_override(
                "SECURITY_HEADER_CSP", "default-src 'self'"
            ),
        }
        # Clickjacking and MIME sniffing protections
        for header, value in header_defaults.items():
            response.headers.setdefault(header, value)
        # Enable HSTS when HTTPS is enabled. Header is ignored over plain HTTP.
        if settings.enable_https:
            hsts_value = _header_override(
                "SECURITY_HEADER_HSTS",
                "max-age=31536000; includeSubDomains; preload",
            )
            response.headers.setdefault("Strict-Transport-Security", hsts_value)
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
    register_error_handlers(app)
    configure_observability(app, settings=observability_settings)
    return app
