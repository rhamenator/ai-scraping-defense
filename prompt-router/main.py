import asyncio
import os
import re
import time

import httpx
from fastapi import FastAPI, HTTPException, Request

LOCAL_LLM_URL = os.getenv("LOCAL_LLM_URL", "http://llama3:11434/api/generate")
CLOUD_PROXY_URL = os.getenv("CLOUD_PROXY_URL", "http://cloud_proxy:8008/api/chat")
MAX_LOCAL_TOKENS = int(os.getenv("MAX_LOCAL_TOKENS", "1000"))
TOKEN_PATTERN = re.compile(r"\w+|[^\w\s]")
SHARED_SECRET = os.getenv("SHARED_SECRET")
if not SHARED_SECRET:
    raise RuntimeError("SHARED_SECRET environment variable is required")
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "60"))
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))

_request_counts: dict[str, tuple[int, float]] = {}
_rate_lock = asyncio.Lock()


def count_tokens(text: str) -> int:
    """Approximate the number of tokens in ``text`` using a simple heuristic."""
    return len(TOKEN_PATTERN.findall(text))


app = FastAPI()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


def get_client_ip(request: Request) -> str:
    x_forwarded_for = request.headers.get("X-Forwarded-For")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    x_real_ip = request.headers.get("X-Real-IP")
    if x_real_ip:
        return x_real_ip
    return request.client.host if request.client else "unknown"


def _cleanup_expired_requests(now: float) -> None:
    expired = [ip for ip, (_, reset) in _request_counts.items() if now > reset]
    for ip in expired:
        del _request_counts[ip]


@app.post("/route")
async def route_prompt(request: Request) -> dict:
    auth_header = request.headers.get("Authorization", "")
    if auth_header != f"Bearer {SHARED_SECRET}":
        raise HTTPException(status_code=401, detail="Unauthorized")
    client_ip = get_client_ip(request)
    now = time.time()
    window_reset = int(now // RATE_LIMIT_WINDOW * RATE_LIMIT_WINDOW + RATE_LIMIT_WINDOW)
    async with _rate_lock:
        _cleanup_expired_requests(now)
        count, reset = _request_counts.get(client_ip, (0, window_reset))
        if now > reset:
            count, reset = 0, window_reset
        if count + 1 > RATE_LIMIT_REQUESTS:
            raise HTTPException(status_code=429, detail="Too Many Requests")
        _request_counts[client_ip] = (count + 1, reset)

    payload = await request.json()
    prompt = payload.get("prompt", "")
    prompt_tokens = count_tokens(prompt)
    target = LOCAL_LLM_URL if prompt_tokens <= MAX_LOCAL_TOKENS else CLOUD_PROXY_URL
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(target, json=payload, timeout=60)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8009"))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
