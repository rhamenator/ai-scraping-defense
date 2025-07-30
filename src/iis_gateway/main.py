"""Simple gateway service to replicate Nginx Lua logic on Windows.

Checks requests against a Redis blocklist and applies basic bot heuristics
before forwarding to the configured backend. Intended for use with IIS
when a custom HttpModule is not desired.
"""

import os

import httpx
import redis
from fastapi import FastAPI, Request, Response
from fastapi.responses import PlainTextResponse

CONFIG = {
    "BACKEND_URL": os.getenv("BACKEND_URL", "http://localhost:8080"),
    "ESCALATION_ENDPOINT": os.getenv("ESCALATION_ENDPOINT"),
    "REDIS_HOST": os.getenv("REDIS_HOST", "localhost"),
    "REDIS_PORT": int(os.getenv("REDIS_PORT", 6379)),
    "REDIS_DB_BLOCKLIST": int(os.getenv("REDIS_DB_BLOCKLIST", 2)),
    "TENANT_ID": os.getenv("TENANT_ID", "default"),
}

BAD_BOTS = [
    "GPTBot",
    "CCBot",
    "ClaudeBot",
    "Scrapy",
    "python-requests",
    "curl",
    "wget",
]

app = FastAPI()
redis_client = redis.Redis(
    host=CONFIG["REDIS_HOST"],
    port=CONFIG["REDIS_PORT"],
    db=CONFIG["REDIS_DB_BLOCKLIST"],
    decode_responses=True,
)


async def escalate(ip: str, reason: str) -> None:
    if not CONFIG["ESCALATION_ENDPOINT"]:
        return
    async with httpx.AsyncClient() as client:
        try:
            await client.post(
                CONFIG["ESCALATION_ENDPOINT"], json={"ip": ip, "reason": reason}
            )
        except httpx.HTTPError:
            pass


@app.api_route(
    "/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]
)
async def proxy(path: str, request: Request) -> Response:
    client_ip = request.client.host
    block_key = f"{CONFIG['TENANT_ID']}:blocklist:ip:{client_ip}"
    if redis_client.exists(block_key):
        return PlainTextResponse("Forbidden", status_code=403)

    ua = request.headers.get("user-agent", "")
    if not ua:
        await escalate(client_ip, "MissingUA")
    elif any(bot.lower() in ua.lower() for bot in BAD_BOTS):
        await escalate(client_ip, "BadUA")
        return PlainTextResponse("Forbidden", status_code=403)

    url = f"{CONFIG['BACKEND_URL'].rstrip('/')}/{path}"
    async with httpx.AsyncClient() as client:
        resp = await client.request(
            request.method,
            url,
            headers=request.headers.raw,
            content=await request.body(),
            params=request.query_params,
        )

    return Response(
        content=resp.content, status_code=resp.status_code, headers=resp.headers
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=9000)
