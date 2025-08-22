"""Simple gateway service to replicate Nginx Lua logic on Windows.

Checks requests against a Redis blocklist and applies basic bot heuristics
before forwarding to the configured backend. Intended for use with IIS
when a custom HttpModule is not desired.
"""

import logging
import os
from dataclasses import dataclass

import httpx
import redis
from cachetools import TTLCache
from fastapi import Request, Response
from fastapi.responses import PlainTextResponse
from redis.exceptions import RedisError

from src.shared.middleware import create_app


@dataclass
class Settings:
    BACKEND_URL: str = os.getenv("BACKEND_URL", "http://localhost:8080")
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

app = create_app()
redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    db=settings.REDIS_DB_BLOCKLIST,
    decode_responses=True,
)

BLOCK_CACHE = TTLCache(maxsize=10000, ttl=60)


def ip_blocked(ip: str) -> bool:
    if ip in BLOCK_CACHE:
        return BLOCK_CACHE[ip]
    key = f"{settings.TENANT_ID}:blocklist:ip:{ip}"
    try:
        blocked = bool(redis_client.exists(key))
    except RedisError:
        logger.exception("Redis blocklist lookup failed")
        raise
    BLOCK_CACHE[ip] = blocked
    return blocked


async def rate_limited(ip: str) -> bool:
    limit = settings.RATE_LIMIT_PER_MINUTE
    if limit <= 0:
        return False
    key = f"{settings.TENANT_ID}:ratelimit:{ip}"
    try:
        count = redis_client.incr(key)
        if count == 1:
            redis_client.expire(key, 60)
        if count > limit:
            await escalate(ip, "RateLimit")
            return True
    except RedisError:
        logger.exception("Redis rate limit update failed")
        raise
    return False


async def escalate(ip: str, reason: str) -> None:
    if not settings.ESCALATION_ENDPOINT:
        return
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            await client.post(
                settings.ESCALATION_ENDPOINT, json={"ip": ip, "reason": reason}
            )
            logger.info("Escalated %s for %s", ip, reason)
        except httpx.TimeoutException:
            logger.exception("Escalation request timed out")
        except httpx.HTTPError:
            logger.exception("Escalation failed")


@app.api_route(
    "/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]
)
async def proxy(path: str, request: Request) -> Response:
    client_ip = request.client.host
    try:
        if ip_blocked(client_ip):
            return PlainTextResponse("Forbidden", status_code=403)
    except RedisError:
        return PlainTextResponse("Service Unavailable", status_code=503)

    try:
        if await rate_limited(client_ip):
            return PlainTextResponse("Too Many Requests", status_code=429)
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
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.request(
                request.method,
                url,
                headers=request.headers.raw,
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

    uvicorn.run(app, host="0.0.0.0", port=9000)
