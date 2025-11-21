"""Shared middleware for API services with secure defaults."""

from __future__ import annotations

import asyncio
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

from src.security.mobile_security import (
    MobileAppAttestationValidator,
    MobilePlatformDetector,
    MobileThreatDetector,
)

from .observability import (
    ObservabilitySettings,
    configure_observability,
)


@dataclass(frozen=True)
class SecuritySettings:
    """Runtime configuration for security middleware."""

    rate_limit_requests: int
    rate_limit_window: int
    max_body_size: int
    enable_https: bool
    mobile_rate_limit_requests: int = 50
    mobile_rate_limit_window: int = 60
    enable_mobile_attestation: bool = False
    block_emulators: bool = False
    block_rooted_devices: bool = False


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
        mobile_rate_limit_requests=_parse_int("MOBILE_RATE_LIMIT_REQUESTS", 50),
        mobile_rate_limit_window=_parse_int("MOBILE_RATE_LIMIT_WINDOW", 60),
        enable_mobile_attestation=os.getenv("ENABLE_MOBILE_ATTESTATION", "false").lower() == "true",
        block_emulators=os.getenv("BLOCK_EMULATORS", "false").lower() == "true",
        block_rooted_devices=os.getenv("BLOCK_ROOTED_DEVICES", "false").lower() == "true",
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


class MobileRateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiter specifically for mobile API endpoints."""

    def __init__(
        self,
        app: FastAPI,
        max_requests: int,
        window_seconds: int,
        mobile_paths: list[str] | None = None,
    ) -> None:
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.mobile_paths = mobile_paths or ["/api/mobile/", "/mobile/"]
        self._requests: TTLCache[str, deque[float]] = TTLCache(
            maxsize=10000, ttl=window_seconds * 2
        )
        self._lock = asyncio.Lock()

    def _is_mobile_endpoint(self, path: str) -> bool:
        """Check if the request path is for a mobile endpoint."""
        return any(path.startswith(mobile_path) for mobile_path in self.mobile_paths)

    async def dispatch(self, request: Request, call_next):
        if self.max_requests <= 0 or not self._is_mobile_endpoint(request.url.path):
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
                    status_code=429,
                    content={"detail": "Mobile API rate limit exceeded"},
                )
            bucket.append(now)
            self._requests[ip] = bucket
        return await call_next(request)


class MobileSecurityMiddleware(BaseHTTPMiddleware):
    """Mobile-specific security checks including attestation and threat detection."""

    def __init__(
        self,
        app: FastAPI,
        enable_attestation: bool = False,
        block_emulators: bool = False,
        block_rooted_devices: bool = False,
    ) -> None:
        super().__init__(app)
        self.enable_attestation = enable_attestation
        self.block_emulators = block_emulators
        self.block_rooted_devices = block_rooted_devices

    async def dispatch(self, request: Request, call_next):
        user_agent = request.headers.get("user-agent", "")
        headers = dict(request.headers)

        # Extract mobile device information
        device_info = MobilePlatformDetector.extract_device_info(user_agent, headers)

        # Store device info in request state for downstream handlers
        request.state.mobile_device_info = device_info

        # Check for emulators if blocking is enabled
        if self.block_emulators and device_info.is_emulator:
            return JSONResponse(
                status_code=403,
                content={"detail": "Emulator access not permitted"},
            )

        # Check for rooted devices if blocking is enabled
        if self.block_rooted_devices and device_info.is_rooted:
            return JSONResponse(
                status_code=403,
                content={"detail": "Rooted/jailbroken device access not permitted"},
            )

        # Validate attestation if enabled
        if self.enable_attestation:
            attestation_token = headers.get("x-app-attestation")
            challenge = headers.get("x-attestation-challenge")

            if attestation_token and challenge:
                is_valid = MobileAppAttestationValidator.validate_attestation(
                    device_info.platform, attestation_token, challenge
                )
                if not is_valid:
                    return JSONResponse(
                        status_code=401,
                        content={"detail": "Invalid app attestation"},
                    )
            else:
                # If attestation is enabled but not provided, reject
                return JSONResponse(
                    status_code=401,
                    content={"detail": "App attestation required"},
                )

        # Check if request appears to be from a mobile bot
        if MobileThreatDetector.is_mobile_bot(user_agent, device_info):
            return JSONResponse(
                status_code=403,
                content={"detail": "Automated mobile access detected"},
            )

        return await call_next(request)


def add_security_middleware(
    app: FastAPI, security_settings: SecuritySettings | None = None
) -> SecuritySettings:
    settings = security_settings or _load_security_settings()

    # Add mobile-specific security middleware first
    app.add_middleware(
        MobileSecurityMiddleware,
        enable_attestation=settings.enable_mobile_attestation,
        block_emulators=settings.block_emulators,
        block_rooted_devices=settings.block_rooted_devices,
    )
    app.add_middleware(
        MobileRateLimitMiddleware,
        max_requests=settings.mobile_rate_limit_requests,
        window_seconds=settings.mobile_rate_limit_window,
    )
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
