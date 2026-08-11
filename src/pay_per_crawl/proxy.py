from __future__ import annotations

import os
import secrets
from urllib.parse import urljoin, urlparse

import httpx
from fastapi import Header, HTTPException, Request, Response
from pydantic import BaseModel, Field

from src.shared.api_key_auth import is_api_key_valid, load_api_key
from src.shared.middleware import create_app
from src.shared.observability import (
    HealthCheckResult,
    register_health_check,
    trace_span,
)
from src.shared.ssrf_protection import SSRFProtectionError, validate_url

from .db import add_credit, charge, get_crawler, init_db, register_crawler
from .pricing import PricingEngine, load_pricing

PRICING_PATH = os.getenv("PRICING_CONFIG", "config/pricing.yaml")
UPSTREAM_URL = os.getenv("UPSTREAM_URL") or (
    f"{os.getenv('UPSTREAM_SCHEME', 'http')}://localhost:8080"
)
DEFAULT_PRICE = float(os.getenv("DEFAULT_PRICE", "0.0"))
HTTPX_TIMEOUT = float(os.getenv("HTTPX_TIMEOUT", "10.0"))
MAX_PROXY_PATH_LENGTH = int(os.getenv("PROXY_MAX_PATH_LENGTH", "2048"))
MAX_PROXY_BODY_BYTES = int(os.getenv("PROXY_MAX_BODY_BYTES", str(10 * 1024 * 1024)))
BLOCK_PRIVATE_UPSTREAMS = os.getenv("UPSTREAM_BLOCK_PRIVATE_IPS", "false").lower() in {
    "1",
    "true",
    "yes",
    "on",
}

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
    name: str = Field(max_length=128)
    purpose: str = Field(max_length=256)
    token: str | None = Field(default=None, max_length=128)


@app.post("/register-crawler")
def register(payload: RegisterPayload):
    if payload.token and os.getenv(
        "ALLOW_CLIENT_SUPPLIED_CRAWLER_TOKEN", "false"
    ).lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        raise HTTPException(
            status_code=400, detail="Client-supplied tokens are disabled"
        )
    token = payload.token or secrets.token_hex(16)
    register_crawler(payload.name, token, payload.purpose)
    return {"token": token}


class PayPayload(BaseModel):
    token: str = Field(max_length=128)
    amount: float = Field(gt=0.0, allow_inf_nan=False)


@app.post("/pay")
def pay(
    payload: PayPayload,
    payment_api_key: str | None = Header(default=None, alias="X-Payment-API-Key"),
):
    expected = load_api_key("PAYMENT_API_KEY")
    if not expected:
        raise HTTPException(
            status_code=503, detail="Payment crediting is not configured"
        )
    if not is_api_key_valid(payment_api_key, expected):
        raise HTTPException(status_code=401, detail="Invalid payment API key")
    if not add_credit(payload.token, payload.amount):
        raise HTTPException(status_code=404, detail="Crawler not registered")
    return {"status": "ok"}


@app.api_route(
    "/{full_path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
)
async def proxy(full_path: str, request: Request):
    # Basic validation to prevent path traversal or absolute URLs
    parsed = urlparse(full_path)
    if (
        parsed.scheme
        or parsed.netloc
        or ".." in full_path.split("/")
        or len(full_path) > MAX_PROXY_PATH_LENGTH
    ):
        raise HTTPException(status_code=400, detail="Invalid path")

    token = request.headers.get("X-API-Key")
    if not token:
        raise HTTPException(status_code=403, detail="Missing crawler token")

    info = get_crawler(token)
    if not info:
        raise HTTPException(status_code=403, detail="Crawler not registered")

    price = pricing_engine.price_for_path(full_path)
    upstream = urljoin(UPSTREAM_URL.rstrip("/") + "/", full_path.lstrip("/"))
    # Ensure the upstream URL stays within the intended host and scheme
    parsed_upstream = urlparse(upstream)
    parsed_base = urlparse(UPSTREAM_URL)
    if (
        parsed_upstream.scheme != parsed_base.scheme
        or parsed_upstream.netloc != parsed_base.netloc
    ):
        raise HTTPException(status_code=400, detail="Invalid upstream URL")

    try:
        validate_url(
            upstream,
            allowed_schemes=[parsed_base.scheme],
            allowed_domains=[parsed_base.hostname] if parsed_base.hostname else None,
            block_private_ips=BLOCK_PRIVATE_UPSTREAMS,
            resolve_dns=BLOCK_PRIVATE_UPSTREAMS,
        )
    except SSRFProtectionError as exc:
        raise HTTPException(status_code=400, detail="Invalid upstream URL") from exc
    blocked_request_headers = {
        "host",
        "x-api-key",
        "connection",
        "content-length",
        "transfer-encoding",
    }
    headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower() not in blocked_request_headers
    }
    body_parts: list[bytes] = []
    body_size = 0
    async for chunk in request.stream():
        body_size += len(chunk)
        if body_size > MAX_PROXY_BODY_BYTES:
            raise HTTPException(status_code=413, detail="Request body too large")
        body_parts.append(chunk)
    body = b"".join(body_parts)

    if price > 0 and not charge(token, price):
        raise HTTPException(status_code=402, detail="Payment required")

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
                    content=body,
                    headers=headers,
                    timeout=HTTPX_TIMEOUT,
                )
        except httpx.RequestError as first_error:
            if request.method not in {"GET", "HEAD", "OPTIONS"}:
                if price > 0:
                    add_credit(token, price)
                raise HTTPException(
                    status_code=502, detail="Upstream unavailable"
                ) from first_error
            try:
                with trace_span(
                    "pay_per_crawl.retry_forward",
                    attributes={"upstream": upstream, "price": price},
                ):
                    resp = await client.request(
                        request.method,
                        upstream,
                        params=request.query_params,
                        content=body,
                        headers=headers,
                        timeout=HTTPX_TIMEOUT,
                    )
            except httpx.RequestError as retry_error:
                if price > 0:
                    add_credit(token, price)
                raise HTTPException(
                    status_code=502, detail="Upstream unavailable"
                ) from retry_error
    blocked_response_headers = {
        "connection",
        "content-encoding",
        "content-length",
        "transfer-encoding",
    }
    response_headers = {
        k: v
        for k, v in resp.headers.items()
        if k.lower() not in blocked_response_headers
    }
    return Response(
        content=resp.content, status_code=resp.status_code, headers=response_headers
    )
