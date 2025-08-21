from __future__ import annotations

import time

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from src.shared.middleware import BodySizeLimitMiddleware, RateLimitMiddleware


def create_app(
    max_body_size: int = 1024,
    max_requests: int = 2,
    window_seconds: int = 60,
) -> FastAPI:
    app = FastAPI()
    app.add_middleware(BodySizeLimitMiddleware, max_body_size=max_body_size)
    app.add_middleware(
        RateLimitMiddleware,
        max_requests=max_requests,
        window_seconds=window_seconds,
    )

    @app.post("/echo")
    async def echo(request: Request) -> dict[str, int]:
        data = await request.body()
        return {"len": len(data)}

    @app.get("/ping")
    async def ping() -> dict[str, bool]:
        return {"ok": True}

    return app


def get_rate_limiter(app: FastAPI) -> RateLimitMiddleware:
    stack = app.middleware_stack
    while True:
        if isinstance(stack, RateLimitMiddleware):
            return stack
        if not hasattr(stack, "app"):
            break
        stack = stack.app  # type: ignore[assignment]
    raise RuntimeError("RateLimitMiddleware not found")


def test_content_length_exceeds_limit() -> None:
    app = create_app(max_body_size=10)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post("/echo", data="x" * 11)
    assert resp.status_code == 413


def test_streaming_body_exceeds_limit() -> None:
    app = create_app(max_body_size=10)
    client = TestClient(app, raise_server_exceptions=False)

    def gen():
        for _ in range(3):
            yield b"a" * 5

    resp = client.post("/echo", data=gen())
    assert resp.status_code == 413


def test_body_under_limit_and_readable() -> None:
    app = create_app(max_body_size=10)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post("/echo", data="hello")
    assert resp.status_code == 200
    assert resp.json() == {"len": 5}


def test_rate_limit_exceeded() -> None:
    app = create_app(max_requests=2, window_seconds=60)
    client = TestClient(app, raise_server_exceptions=False)
    assert client.get("/ping").status_code == 200
    assert client.get("/ping").status_code == 200
    assert client.get("/ping").status_code == 429


def test_rate_limiter_prunes_stale_ips() -> None:
    app = create_app(max_requests=1, window_seconds=1)
    client = TestClient(app, raise_server_exceptions=False)
    assert client.get("/ping").status_code == 200
    rate = get_rate_limiter(app)
    assert len(rate._requests) == 1
    time.sleep(2.1)
    # access cache to trigger expiry
    assert len(rate._requests) == 0
