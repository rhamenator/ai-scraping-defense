from __future__ import annotations

import os
import secrets

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel

from .db import add_credit, charge, get_crawler, init_db, register_crawler
from .pricing import PricingEngine, load_pricing

PRICING_PATH = os.getenv("PRICING_CONFIG", "config/pricing.yaml")
UPSTREAM_URL = os.getenv("UPSTREAM_URL", "http://localhost:8080")
DEFAULT_PRICE = float(os.getenv("DEFAULT_PRICE", "0.0"))

pricing_engine = PricingEngine(load_pricing(PRICING_PATH), DEFAULT_PRICE)
init_db()

app = FastAPI()


class RegisterPayload(BaseModel):
    name: str
    purpose: str
    token: str | None = None


@app.post("/register-crawler")
def register(payload: RegisterPayload):
    token = payload.token or secrets.token_hex(16)
    register_crawler(payload.name, token, payload.purpose)
    return {"token": token}


class PayPayload(BaseModel):
    token: str
    amount: float


@app.post("/pay")
def pay(payload: PayPayload):
    add_credit(payload.token, payload.amount)
    return {"status": "ok"}


@app.api_route(
    "/{full_path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
)
async def proxy(full_path: str, request: Request):
    token = request.headers.get("X-API-Key")
    if not token:
        raise HTTPException(status_code=403, detail="Missing crawler token")

    info = get_crawler(token)
    if not info:
        raise HTTPException(status_code=403, detail="Crawler not registered")

    price = pricing_engine.price_for_path(full_path)
    if price > 0 and not charge(token, price):
        raise HTTPException(status_code=402, detail="Payment required")

    upstream = f"{UPSTREAM_URL.rstrip('/')}/{full_path}"
    headers = {k: v for k, v in request.headers.items() if k.lower() != "host"}
    body = await request.body()
    async with httpx.AsyncClient() as client:
        resp = await client.request(
            request.method,
            upstream,
            params=request.query_params,
            content=body,
            headers=headers,
        )
    return Response(
        content=resp.content, status_code=resp.status_code, headers=resp.headers
    )
