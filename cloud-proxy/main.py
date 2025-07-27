import os
import httpx
from fastapi import FastAPI, HTTPException

API_KEY = os.getenv("OPENAI_API_KEY")
LLM_URL = os.getenv("CLOUD_LLM_API_URL", "https://api.openai.com/v1/chat/completions")

app = FastAPI()

@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}

@app.post("/api/chat")
async def proxy_chat(payload: dict) -> dict:
    if not API_KEY:
        raise HTTPException(status_code=500, detail="API key not configured")
    headers = {"Authorization": f"Bearer {API_KEY}"}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(LLM_URL, json=payload, headers=headers, timeout=60)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8008"))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
