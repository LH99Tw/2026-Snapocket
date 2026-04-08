"""Server registry schemas for local/remote AI dispatch targets."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ServerKind(str, Enum):
    local = "local"
    remote = "remote"


class ServerHealthStatus(str, Enum):
    unknown = "unknown"
    healthy = "healthy"
    unreachable = "unreachable"


class QueueSummary(BaseModel):
    queued: int = 0
    running: int = 0
    succeeded: int = 0
    failed: int = 0
    cancelled: int = 0
    total: int = 0


class ServerRecord(BaseModel):
    server_id: str
    name: str
    kind: ServerKind
    active: bool = False
    base_url: str = ""
    has_api_key: bool = False
    health_status: ServerHealthStatus = ServerHealthStatus.unknown
    last_error: str = ""
    last_checked_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ServerCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    base_url: str = Field(min_length=8, max_length=512)
    api_key: str = Field(min_length=1, max_length=1024)
