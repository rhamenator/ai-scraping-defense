from __future__ import annotations

import os
import secrets
from urllib.parse import urljoin, urlparse

import httpx
from fastapi import HTTPException, Request, Response
from pydantic import BaseModel

from src.shared.middleware import create_app
from src.shared.observability import (
    HealthCheckResult,
    register_health_check,
    trace_span,
)
from src.shared.ssrf_protection import is_private_ip

from .db import add_credit, charge, get_crawler, init_db, register_crawler
from .pricing import PricingEngine, load_pricing

PRICING_PATH = os.getenv("PRICING_CONFIG", "config/pricing.yaml")
UPSTREAM_URL = os.getenv("UPSTREAM_URL", "http://localhost:8080")
DEFAULT_PRICE = float(os.getenv("DEFAULT_PRICE", "0.0"))
HTTPX_TIMEOUT = float(os.getenv("HTTPX_TIMEOUT", "10.0"))

pricing_engine = PricingEngine(load_pricing(PRICING_PATH), DEFAULT_PRICE)
init_db()

app = create_app()


@register_health_check(app, "pay_per_crawl", critical=True)
async def _service_health() -> HealthCheckResult:
    try:
        conn = init_db()
        conn.execute("SELECT 1")
    except Exception as exc:  # pragma: no cover - database IO
        return HealthCheckResult.unhealthy({"error": str(exc)})
    rule_count = len(pricing_engine.mapping)
    detail = {"pricing_rules": rule_count, "default_price": DEFAULT_PRICE}
    if rule_count == 0:
        return HealthCheckResult.degraded(detail)
    return HealthCheckResult.healthy(detail)


class RegisterPayload(BaseModel):
    name: str
    purpose: str
    token: str | None = None


@app.post("/register-crawler")
def register(payload: RegisterPayload):
    token = payload.token or secrets.token_hex(16)
    register_crawler(payload.name, token, payload.purpose)
    return {"token": token}


class PayPayload(BaseModel):
    token: str
    amount: float


@app.post("/pay")
def pay(payload: PayPayload):
    add_credit(payload.token, payload.amount)
    return {"status": "ok"}


@app.api_route(
    "/{full_path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
)
async def proxy(full_path: str, request: Request):
    # Basic validation to prevent path traversal or absolute URLs
    parsed = urlparse(full_path)
    if parsed.scheme or parsed.netloc or ".." in full_path.split("/"):
        raise HTTPException(status_code=400, detail="Invalid path")

    token = request.headers.get("X-API-Key")
    if not token:
        raise HTTPException(status_code=403, detail="Missing crawler token")

    info = get_crawler(token)
    if not info:
        raise HTTPException(status_code=403, detail="Crawler not registered")

    price = pricing_engine.price_for_path(full_path)
    if price > 0 and not charge(token, price):
        raise HTTPException(status_code=402, detail="Payment required")

    upstream = urljoin(UPSTREAM_URL.rstrip("/") + "/", full_path.lstrip("/"))
    # Ensure the upstream URL stays within the intended host and scheme
    parsed_upstream = urlparse(upstream)
    parsed_base = urlparse(UPSTREAM_URL)
    if (
        parsed_upstream.scheme != parsed_base.scheme
        or parsed_upstream.netloc != parsed_base.netloc
    ):
        raise HTTPException(status_code=400, detail="Invalid upstream URL")

    # Additional SSRF protection: check for private IPs in the upstream hostname
    upstream_hostname = parsed_upstream.hostname
    if upstream_hostname and is_private_ip(upstream_hostname):
        raise HTTPException(status_code=400, detail="Access to private IPs not allowed")
    headers = {k: v for k, v in request.headers.items() if k.lower() != "host"}
    body_chunks: list[bytes] = []

    async def stream_with_buffer():
        async for chunk in request.stream():
            body_chunks.append(chunk)
            yield chunk

    async with httpx.AsyncClient(timeout=HTTPX_TIMEOUT) as client:
        try:
            with trace_span(
                "pay_per_crawl.forward_request",
                attributes={"upstream": upstream, "price": price},
            ):
                resp = await client.request(
                    request.method,
                    upstream,
                    params=request.query_params,
                    content=stream_with_buffer(),
                    headers=headers,
                    timeout=HTTPX_TIMEOUT,
                )
        except httpx.RequestError:
            with trace_span(
                "pay_per_crawl.retry_forward",
                attributes={"upstream": upstream, "price": price},
            ):
                resp = await client.request(
                    request.method,
                    upstream,
                    params=request.query_params,
                    content=b"".join(body_chunks),
                    headers=headers,
                    timeout=HTTPX_TIMEOUT,
                )
    return Response(
        content=resp.content, status_code=resp.status_code, headers=resp.headers
    )
