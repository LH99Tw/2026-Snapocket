"""Common response envelope schemas shared by all endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from pydantic import BaseModel, Field


class ErrorPayload(BaseModel):
    code: str
    message: str


class ResponseMeta(BaseModel):
    request_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ApiResponse(BaseModel):
    ok: bool = True
    meta: ResponseMeta
    data: dict | list | None = None
    error: ErrorPayload | None = None
