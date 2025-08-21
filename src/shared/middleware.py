import asyncio
import os
import time

from fastapi import FastAPI, HTTPException
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
        self._requests: dict[str, list[float]] = {}
        self._lock = asyncio.Lock()

    async def dispatch(self, request: Request, call_next):
        if self.max_requests <= 0:
            return await call_next(request)
        ip = request.client.host if request.client else "unknown"
        now = time.time()
        async with self._lock:
            bucket = self._requests.setdefault(ip, [])
            cutoff = now - self.window_seconds
            while bucket and bucket[0] <= cutoff:
                bucket.pop(0)
            if len(bucket) >= self.max_requests:
                raise HTTPException(status_code=429, detail="Too Many Requests")
            bucket.append(now)
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
            raise HTTPException(status_code=413, detail="Request body too large")
        body = await request.body()
        if len(body) > self.max_body_size:
            raise HTTPException(status_code=413, detail="Request body too large")
        return await call_next(request)


def add_security_middleware(app: FastAPI) -> None:
    app.add_middleware(BodySizeLimitMiddleware, max_body_size=MAX_BODY_SIZE)
    app.add_middleware(
        RateLimitMiddleware,
        max_requests=RATE_LIMIT_REQUESTS,
        window_seconds=RATE_LIMIT_WINDOW,
    )


def create_app(**kwargs) -> FastAPI:
    app = FastAPI(**kwargs)
    add_security_middleware(app)
    return app
