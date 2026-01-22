"""Shared error envelope and exception handlers."""

from __future__ import annotations

import uuid
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .observability import get_request_id

ERROR_CODE_BY_STATUS = {
    400: "invalid_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    422: "validation_error",
    429: "rate_limited",
    500: "internal_error",
    502: "bad_gateway",
    503: "service_unavailable",
    504: "gateway_timeout",
}


def _status_phrase(status_code: int) -> str:
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:
        return "Request failed"


def _error_code(status_code: int) -> str:
    return ERROR_CODE_BY_STATUS.get(status_code, f"http_{status_code}")


def _request_id_from_request(request: Request) -> tuple[str, str]:
    header_name = "X-Request-ID"
    state = getattr(request.app.state, "observability", None)
    if state and hasattr(state, "settings"):
        header_name = state.settings.request_id_header
    request_id = (
        request.headers.get(header_name) or get_request_id() or str(uuid.uuid4())
    )
    return request_id, header_name


def _build_payload(
    *,
    message: str,
    code: str,
    request_id: str,
    details: Any | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "error": {"code": code, "message": message},
        "request_id": request_id,
        # Preserve legacy "detail" for backwards compatibility with tests/clients.
        "detail": message,
    }
    if details is not None:
        payload["error"]["details"] = details
    return payload


def register_error_handlers(app: FastAPI) -> None:
    """Register shared error handlers that emit a stable envelope."""

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        message = (
            exc.detail
            if isinstance(exc.detail, str)
            else _status_phrase(exc.status_code)
        )
        details = None if isinstance(exc.detail, str) else exc.detail
        request_id, header_name = _request_id_from_request(request)
        payload = _build_payload(
            message=message,
            code=_error_code(exc.status_code),
            request_id=request_id,
            details=details,
        )
        response = JSONResponse(payload, status_code=exc.status_code)
        if exc.headers:
            response.headers.update(exc.headers)
        response.headers.setdefault(header_name, request_id)
        return response

    @app.exception_handler(RequestValidationError)
    async def _validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        request_id, header_name = _request_id_from_request(request)
        payload = _build_payload(
            message="Validation error",
            code=_error_code(422),
            request_id=request_id,
            details=exc.errors(),
        )
        response = JSONResponse(payload, status_code=422)
        response.headers.setdefault(header_name, request_id)
        return response

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        request_id, header_name = _request_id_from_request(request)
        payload = _build_payload(
            message="Internal server error",
            code=_error_code(500),
            request_id=request_id,
        )
        response = JSONResponse(payload, status_code=500)
        response.headers.setdefault(header_name, request_id)
        return response
