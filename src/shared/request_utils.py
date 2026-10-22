import io
import json
import os

from fastapi import HTTPException, Request

DEFAULT_MAX_PAYLOAD_BYTES = 1048576  # 1MB default limit
MAX_JSON_PAYLOAD_SIZE = int(
    os.getenv("MAX_JSON_PAYLOAD_SIZE", str(DEFAULT_MAX_PAYLOAD_BYTES))
)


async def read_body_bytes(
    request: Request, max_bytes: int = MAX_JSON_PAYLOAD_SIZE
) -> bytes:
    """Read raw body bytes with a maximum size limit."""
    body = io.BytesIO()
    async for chunk in request.stream():
        if body.tell() + len(chunk) > max_bytes:
            raise HTTPException(status_code=413, detail="Payload too large")
        body.write(chunk)
    raw_bytes = body.getvalue()
    request.state.body_bytes = raw_bytes
    return raw_bytes


def parse_json_bytes(raw_bytes: bytes) -> dict:
    """Parse a JSON body after callers perform any required authentication."""
    try:
        data = json.loads(raw_bytes.decode())
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc
    return data


async def read_json_body(
    request: Request, max_bytes: int = MAX_JSON_PAYLOAD_SIZE
) -> dict:
    """Read JSON body from request with a maximum size limit."""
    return parse_json_bytes(await read_body_bytes(request, max_bytes))
