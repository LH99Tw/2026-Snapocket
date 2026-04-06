"""Common response envelope builders for API routes."""

from __future__ import annotations

from fastapi import Request

from app.schemas.common import ApiResponse, ErrorPayload, ResponseMeta


def ok_response(request: Request, data) -> ApiResponse:
    return ApiResponse(ok=True, meta=ResponseMeta(request_id=request.state.request_id), data=data)


def error_response(request: Request, code: str, message: str) -> ApiResponse:
    return ApiResponse(
        ok=False,
        meta=ResponseMeta(request_id=request.state.request_id),
        error=ErrorPayload(code=code, message=message),
    )
