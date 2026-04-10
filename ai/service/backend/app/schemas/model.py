"""Model registry and model-level metrics schemas."""

from __future__ import annotations

from pydantic import BaseModel


class ModelInfo(BaseModel):
    model_id: str
    name: str
    engine: str
    version: str
    active: bool = False
    status: str = "ready"


class ModelMetrics(BaseModel):
    model_id: str
    success_count: int = 0
    failure_count: int = 0
    avg_latency_ms: float = 0.0
