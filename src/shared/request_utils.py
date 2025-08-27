import io
import json
import os

from fastapi import HTTPException, Request

DEFAULT_MAX_PAYLOAD_BYTES = 1048576  # 1MB default limit
MAX_JSON_PAYLOAD_SIZE = int(
    os.getenv("MAX_JSON_PAYLOAD_SIZE", str(DEFAULT_MAX_PAYLOAD_BYTES))
)


async def read_json_body(
    request: Request, max_bytes: int = MAX_JSON_PAYLOAD_SIZE
) -> dict:
    """Read JSON body from request with a maximum size limit."""
    body = io.BytesIO()
    async for chunk in request.stream():
        if body.tell() + len(chunk) > max_bytes:
            raise HTTPException(status_code=413, detail="Payload too large")
        body.write(chunk)
    raw_bytes = body.getvalue()
    try:
        data = json.loads(raw_bytes.decode())
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc
    request.state.body_bytes = raw_bytes
    return data
