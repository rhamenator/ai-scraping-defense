import os
import re
import httpx
from fastapi import FastAPI, HTTPException, Request

LOCAL_LLM_URL = os.getenv("LOCAL_LLM_URL", "http://llama3:11434/api/generate")
CLOUD_PROXY_URL = os.getenv("CLOUD_PROXY_URL", "http://cloud_proxy:8008/api/chat")
MAX_LOCAL_TOKENS = int(os.getenv("MAX_LOCAL_TOKENS", "1000"))
TOKEN_PATTERN = re.compile(r"\w+|[^\w\s]")

def count_tokens(text: str) -> int:
    """Approximate the number of tokens in ``text`` using a simple heuristic."""
    return len(TOKEN_PATTERN.findall(text))

app = FastAPI()

@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/route")
async def route_prompt(request: Request) -> dict:
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
