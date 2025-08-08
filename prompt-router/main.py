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
SHARED_SECRET = os.getenv("SHARED_SECRET", "")
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


@app.post("/route")
async def route_prompt(request: Request) -> dict:
    auth_header = request.headers.get("Authorization", "")
    if auth_header != f"Bearer {SHARED_SECRET}":
        raise HTTPException(status_code=401, detail="Unauthorized")

    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    async with _rate_lock:
        count, reset = _request_counts.get(client_ip, (0, now + RATE_LIMIT_WINDOW))
        if now > reset:
            count, reset = 0, now + RATE_LIMIT_WINDOW
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
