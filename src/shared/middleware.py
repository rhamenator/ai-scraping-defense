import asyncio
import os
import time
from collections import deque

from cachetools import TTLCache
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "100"))
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))
MAX_BODY_SIZE = int(os.getenv("MAX_BODY_SIZE", str(1 * 1024 * 1024)))


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


def add_security_middleware(app: FastAPI) -> None:
    app.add_middleware(BodySizeLimitMiddleware, max_body_size=MAX_BODY_SIZE)
    app.add_middleware(
        RateLimitMiddleware,
        max_requests=RATE_LIMIT_REQUESTS,
        window_seconds=RATE_LIMIT_WINDOW,
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
        if os.getenv("ENABLE_HTTPS", "false").lower() == "true":
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains; preload",
            )
        return response


def create_app(**kwargs) -> FastAPI:
    app = FastAPI(**kwargs)
    add_security_middleware(app)
    return app
