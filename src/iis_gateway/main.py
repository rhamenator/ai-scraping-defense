"""Simple gateway service to replicate Nginx Lua logic on Windows.

Checks requests against a Redis blocklist and applies basic bot heuristics
before forwarding to the configured backend. Intended for use with IIS
when a custom HttpModule is not desired.
"""

import json
import logging
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx
from cachetools import TTLCache
from fastapi import Request, Response
from fastapi.responses import PlainTextResponse
from redis.exceptions import RedisError

from src.shared.containment import THROTTLE_KEY_PREFIX
from src.shared.middleware import create_app
from src.shared.observability import (
    HealthCheckResult,
    register_health_check,
    trace_span,
)
from src.shared.redis_client import get_redis_connection


@dataclass
class Settings:
    BACKEND_URL: str = os.getenv("BACKEND_URL") or (
        f"{os.getenv('BACKEND_SCHEME', 'http')}://localhost:8080"
    )
    ESCALATION_ENDPOINT: str | None = os.getenv("ESCALATION_ENDPOINT")
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", 6379))
    REDIS_DB_BLOCKLIST: int = int(os.getenv("REDIS_DB_BLOCKLIST", 2))
    TENANT_ID: str = os.getenv("TENANT_ID", "default")
    RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", 0))


settings = Settings()

BAD_BOTS = [
    "GPTBot",
    "CCBot",
    "ClaudeBot",
    "Scrapy",
    "python-requests",
    "curl",
    "wget",
]

logger = logging.getLogger("iis_gateway")

redis_client = get_redis_connection(db_number=settings.REDIS_DB_BLOCKLIST)
_http_client: httpx.AsyncClient | None = None


@asynccontextmanager
async def _lifespan(_app):
    try:
        yield
    finally:
        global _http_client
        if _http_client is not None:
            await _http_client.aclose()
            _http_client = None


app = create_app(lifespan=_lifespan)

BLOCK_CACHE = TTLCache(maxsize=10000, ttl=60)
HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}
FORWARDED_HEADER_NAMES = {
    "host",
    "x-forwarded-for",
    "x-forwarded-host",
    "x-forwarded-port",
    "x-forwarded-proto",
    "x-real-ip",
}


@register_health_check(app, "iis_gateway_redis", critical=True)
async def _redis_health() -> HealthCheckResult:
    if redis_client is None:
        return HealthCheckResult.unhealthy({"error": "Redis unavailable"})
    try:
        redis_client.ping()
    except RedisError as exc:  # pragma: no cover - external dependency
        return HealthCheckResult.unhealthy({"error": str(exc)})
    return HealthCheckResult.healthy()


async def get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=10.0)
    return _http_client


def ip_blocked(ip: str) -> bool:
    if redis_client is None:
        raise RedisError("Redis unavailable")
    if ip in BLOCK_CACHE:
        return BLOCK_CACHE[ip]
    key = f"{settings.TENANT_ID}:blocklist:ip:{ip}"
    try:
        with trace_span("iis_gateway.block_lookup", attributes={"ip": ip}):
            blocked = bool(redis_client.exists(key))
    except RedisError:
        logger.exception("Redis blocklist lookup failed")
        raise
    BLOCK_CACHE[ip] = blocked
    return blocked


def get_ip_throttle_state(ip: str) -> dict | None:
    if redis_client is None:
        raise RedisError("Redis unavailable")
    key = f"{THROTTLE_KEY_PREFIX}{ip}"
    try:
        payload = redis_client.get(key)
        if not payload:
            return None
        ttl_seconds = redis_client.ttl(key)
    except RedisError:
        logger.exception("Redis throttle lookup failed")
        raise

    metadata = json.loads(payload)
    if not isinstance(metadata, dict):
        logger.warning("Unexpected throttle metadata type for %s", ip)
        return None
    metadata["ttl_seconds"] = ttl_seconds
    return metadata


def _effective_rate_limit(limit_override: int | None) -> int:
    base_limit = settings.RATE_LIMIT_PER_MINUTE
    if limit_override is None or limit_override <= 0:
        return base_limit
    if base_limit <= 0:
        return limit_override
    return min(base_limit, limit_override)


async def rate_limited(
    ip: str, *, limit_override: int | None = None
) -> tuple[bool, int | None]:
    limit = _effective_rate_limit(limit_override)
    if limit <= 0:
        return False, None
    if redis_client is None:
        raise RedisError("Redis unavailable")
    key = f"{settings.TENANT_ID}:ratelimit:{ip}"
    try:
        with trace_span(
            "iis_gateway.rate_limit", attributes={"ip": ip, "limit": limit}
        ):
            count = redis_client.incr(key)
            if count == 1:
                redis_client.expire(key, 60)
            if count > limit:
                await escalate(ip, "RateLimit")
                retry_after = redis_client.ttl(key)
                if not isinstance(retry_after, int) or retry_after < 0:
                    retry_after = 60
                elif retry_after == 0:
                    retry_after = 1
                return True, retry_after
    except RedisError:
        logger.exception("Redis rate limit update failed")
        raise
    return False, None


async def escalate(ip: str, reason: str) -> None:
    if not settings.ESCALATION_ENDPOINT:
        return
    client = await get_http_client()
    try:
        with trace_span(
            "iis_gateway.escalate", attributes={"ip": ip, "reason": reason}
        ):
            await client.post(
                settings.ESCALATION_ENDPOINT,
                json={"ip": ip, "reason": reason},
            )
            logger.info("Escalated %s for %s", ip, reason)
    except httpx.TimeoutException:
        logger.exception("Escalation request timed out")
    except httpx.HTTPError:
        logger.exception("Escalation failed")


def _build_forward_headers(request: Request) -> dict[str, str]:
    """Build canonical proxy headers and drop spoofable client-supplied values."""

    forwarded_headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in HOP_BY_HOP_HEADERS | FORWARDED_HEADER_NAMES
    }

    client_ip = request.client.host if request.client else "unknown"
    forwarded_headers["Host"] = request.headers.get("host", request.url.netloc)
    forwarded_headers["X-Forwarded-For"] = client_ip
    forwarded_headers["X-Forwarded-Host"] = request.headers.get(
        "host", request.url.netloc
    )
    scheme = request.url.scheme
    default_port = 443 if scheme == "https" else 80
    forwarded_headers["X-Forwarded-Port"] = str(request.url.port or default_port)
    forwarded_headers["X-Forwarded-Proto"] = scheme
    forwarded_headers["X-Real-IP"] = client_ip
    return forwarded_headers


@app.api_route(
    "/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]
)
async def proxy(path: str, request: Request) -> Response:
    client_ip = request.client.host
    try:
        if ip_blocked(client_ip):
            return PlainTextResponse("Forbidden", status_code=403)
        throttle_state = get_ip_throttle_state(client_ip)
        throttle_limit = None
        if throttle_state:
            raw_limit = throttle_state.get("rate_limit_per_minute")
            throttle_limit = raw_limit if isinstance(raw_limit, int) else None
        limited, retry_after = await rate_limited(
            client_ip, limit_override=throttle_limit
        )
        if limited:
            return PlainTextResponse(
                "Too Many Requests",
                status_code=429,
                headers={"Retry-After": str(retry_after)},
            )
    except RedisError:
        return PlainTextResponse("Service Unavailable", status_code=503)

    ua = request.headers.get("user-agent", "")
    if not ua:
        await escalate(client_ip, "MissingUA")
    elif any(bot.lower() in ua.lower() for bot in BAD_BOTS):
        await escalate(client_ip, "BadUA")
        return PlainTextResponse("Forbidden", status_code=403)

    if not request.headers.get("accept-language"):
        await escalate(client_ip, "MissingAcceptLanguage")
    accept = request.headers.get("accept")
    if accept and "*/*" in accept and "text/html" not in accept:
        await escalate(client_ip, "SuspiciousAccept")

    url = f"{settings.BACKEND_URL.rstrip('/')}/{path}"
    client = await get_http_client()
    try:
        with trace_span(
            "iis_gateway.proxy_request",
            attributes={"path": path, "method": request.method},
        ):
            resp = await client.request(
                request.method,
                url,
                headers=_build_forward_headers(request),
                content=request.stream(),
                params=request.query_params,
            )
    except httpx.TimeoutException:
        logger.exception("Backend request timed out")
        return PlainTextResponse("Gateway Timeout", status_code=504)
    except httpx.HTTPError:
        logger.exception("Backend request failed")
        return PlainTextResponse("Bad Gateway", status_code=502)

    return Response(
        content=resp.content, status_code=resp.status_code, headers=resp.headers
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import uvicorn

    # Default to loopback to avoid accidentally exposing the gateway on all interfaces.
    # For containerized deployments you can set IIS_GATEWAY_HOST=0.0.0.0 explicitly.
    host = os.getenv("IIS_GATEWAY_HOST", "127.0.0.1")
    uvicorn.run(app, host=host, port=9000)
