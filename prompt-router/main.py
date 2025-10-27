# Built-in modules
import asyncio
import hmac
import os
import re
import time

# Third-party modules
import httpx
from fastapi import HTTPException, Request, Response

from src.shared.middleware import SecuritySettings, create_app
from src.shared.observability import ObservabilitySettings
from src.shared.request_utils import read_json_body

LOCAL_LLM_URL = os.getenv("LOCAL_LLM_URL", "http://llama3:11434/api/generate")
CLOUD_PROXY_URL = os.getenv("CLOUD_PROXY_URL", "http://cloud_proxy:8008/api/chat")
MAX_LOCAL_TOKENS = int(os.getenv("MAX_LOCAL_TOKENS", "1000"))
TOKEN_PATTERN = re.compile(r"\w+|[^\w\s]")
SHARED_SECRET = os.getenv("SHARED_SECRET")
if not SHARED_SECRET:
    raise RuntimeError("SHARED_SECRET environment variable is required")
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "60"))
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))
TRUST_PROXY_HEADERS = os.getenv("TRUST_PROXY_HEADERS", "false").lower() in (
    "1",
    "true",
    "yes",
)

_request_counts: dict[str, tuple[int, float]] = {}
_rate_lock = asyncio.Lock()


def count_tokens(text: str) -> int:
    """Approximate the number of tokens in ``text`` using a simple heuristic."""
    return len(TOKEN_PATTERN.findall(text))


app = create_app(
    security_settings=SecuritySettings(
        rate_limit_requests=0,
        rate_limit_window=RATE_LIMIT_WINDOW,
        max_body_size=int(os.getenv("MAX_BODY_SIZE", 1 * 1024 * 1024)),
        enable_https=os.getenv("ENABLE_HTTPS", "false").lower() == "true",
    ),
    observability_settings=ObservabilitySettings(
        metrics_path="/observability/metrics",
        health_path="/observability/health",
    ),
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


def get_client_ip(request: Request) -> str:
    if TRUST_PROXY_HEADERS:
        x_forwarded_for = request.headers.get("X-Forwarded-For")
        if x_forwarded_for:
            return x_forwarded_for.split(",")[0].strip()
        x_real_ip = request.headers.get("X-Real-IP")
        if x_real_ip:
            return x_real_ip
    return request.client.host if request.client else "unknown"


def calculate_window_reset(now: float, window: int = RATE_LIMIT_WINDOW) -> int:
    return int(now // window * window + window)


def _cleanup_expired_requests(now: float) -> None:
    """Remove expired rate-limit entries.

    Caller must hold ``_rate_lock``.
    """
    expired = [ip for ip, (_, reset) in _request_counts.items() if now > reset]
    for ip in expired:
        del _request_counts[ip]


@app.post("/route")
async def route_prompt(request: Request, response: Response) -> dict:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = auth_header.split(" ", 1)[1]
    if not hmac.compare_digest(token, SHARED_SECRET):
        raise HTTPException(status_code=401, detail="Unauthorized")
    client_ip = get_client_ip(request)
    now = time.time()
    window_reset = calculate_window_reset(now)
    async with _rate_lock:
        _cleanup_expired_requests(now)
        count, reset = _request_counts.get(client_ip, (0, window_reset))
        if now > reset:
            count, reset = 0, window_reset
        if count + 1 > RATE_LIMIT_REQUESTS:
            retry_after = int(reset - now)
            headers = {
                "X-RateLimit-Limit": str(RATE_LIMIT_REQUESTS),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(reset)),
                "Retry-After": str(retry_after),
            }
            raise HTTPException(
                status_code=429, detail="Too Many Requests", headers=headers
            )
        _request_counts[client_ip] = (count + 1, reset)
        remaining = RATE_LIMIT_REQUESTS - (count + 1)

    response.headers["X-RateLimit-Limit"] = str(RATE_LIMIT_REQUESTS)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    response.headers["X-RateLimit-Reset"] = str(int(reset))

    payload = await read_json_body(request)
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
