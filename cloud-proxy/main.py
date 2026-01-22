import hmac
import os
import secrets

import httpx
from fastapi import Header, HTTPException

from src.shared.middleware import create_app

API_KEY = os.getenv("OPENAI_API_KEY")
LLM_URL = os.getenv("CLOUD_LLM_API_URL", "https://api.openai.com/v1/chat/completions")
PROXY_KEY = os.getenv("PROXY_KEY")
compare_digest = getattr(secrets, "compare_digest", hmac.compare_digest)

app = create_app()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/chat")
async def proxy_chat(payload: dict, x_proxy_key: str | None = Header(None)) -> dict:
    if not API_KEY:
        raise HTTPException(status_code=500, detail="API key not configured")
    if not PROXY_KEY:
        raise HTTPException(status_code=500, detail="Proxy key not configured")
    if not compare_digest(x_proxy_key or "", PROXY_KEY or ""):
        raise HTTPException(status_code=401, detail="Invalid proxy key")
    headers = {"Authorization": f"Bearer {API_KEY}"}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                LLM_URL, json=payload, headers=headers, timeout=60
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8008"))
    host = os.getenv("HOST", "0.0.0.0")  # nosec B104 - override for restricted binds
    uvicorn.run("main:app", host=host, port=port)
