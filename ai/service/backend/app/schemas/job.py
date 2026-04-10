"""Job lifecycle schemas for asynchronous OCR execution."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pydantic import BaseModel


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class JobInfo(BaseModel):
    job_id: str
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    error: str | None = None
    attempt: int = 0
    max_retries: int = 0
    timeout_s: float | None = None
