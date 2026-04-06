"""System endpoints for liveness/readiness/metrics/status."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse

from app.api.deps import get_state, require_api_key
from app.api.utils import ok_response
from app.services.dependency_checks import ping_redis
from app.services.model_runtime import resolve_effective_engine
from app.services.state import AppState

router = APIRouter(tags=["system"])


@router.get("/health/live")
def live():
    return {"ok": True}


@router.get("/health/ready")
def ready(state: AppState = Depends(get_state)):
    resolve_effective_engine(state, sync_registry=True)
    configured = {
        "paddle": state.settings.paddle_enable and bool(state.settings.llm_model_paddle),
        "glm": state.settings.glm_enable and bool(state.settings.llm_model_glm),
    }
    runtime = {
        "paddle": state.router.paddle_engine.available(),
        "glm": state.router.glm_engine.available(),
    }
    db = state.persistence.health(timeout_s=state.settings.readiness_timeout_s)
    redis = ping_redis(
        state.settings.redis_url if state.settings.redis_enable else None,
        timeout_s=state.settings.readiness_timeout_s,
    )
    dependencies = {
        "database": db,
        "redis": {
            "configured": redis.configured,
            "ok": redis.ok,
            "error": redis.error,
        },
    }

    # Ready policy: OCR configuration present AND core infra dependencies reachable.
    ready_ok = any(configured.values()) and db.get("ok", False) and redis.ok
    return {
        "ok": ready_ok,
        "configured": configured,
        "runtime": runtime,
        "dependencies": dependencies,
    }


@router.get("/metrics", response_class=PlainTextResponse)
def metrics(state: AppState = Depends(get_state)):
    return state.metrics.to_prometheus()


@router.get("/v1/system/status", dependencies=[Depends(require_api_key)])
def system_status(request: Request, state: AppState = Depends(get_state)):
    resolve_effective_engine(state, sync_registry=True)
    db = state.persistence.health(timeout_s=state.settings.readiness_timeout_s)
    redis = ping_redis(
        state.settings.redis_url if state.settings.redis_enable else None,
        timeout_s=state.settings.readiness_timeout_s,
    )
    llm_backend = {
        "base_url": state.settings.llm_base_url,
        "paddle_model": state.settings.llm_model_paddle,
        "glm_model": state.settings.llm_model_glm,
        "request_timeout_s": state.settings.llm_request_timeout_s,
        "keep_alive": state.settings.llm_keep_alive,
        "temperature": state.settings.llm_temperature,
        "image_max_side_px": state.settings.llm_image_max_side_px,
        "max_tokens": state.settings.llm_max_tokens,
    }
    data = {
        "queue": {
            "backend": state.settings.job_queue_backend,
        },
        "llm_backend": llm_backend,
        "engines": {
            "paddle_available": state.router.paddle_engine.available(),
            "glm_available": state.router.glm_engine.available(),
            "paddle_cache": (
                state.router.paddle_engine.availability_detail()
                if hasattr(state.router.paddle_engine, "availability_detail")
                else {}
            ),
            "glm_cache": (
                state.router.glm_engine.availability_detail()
                if hasattr(state.router.glm_engine, "availability_detail")
                else {}
            ),
        },
        "dependencies": {
            "database": db,
            "redis": {
                "configured": redis.configured,
                "ok": redis.ok,
                "error": redis.error,
            },
        },
        "models": [m.model_dump() for m in state.model_registry.list_models()],
        "jobs": [j.model_dump() for j in state.job_manager.list_jobs()],
        "metrics": state.metrics.snapshot(),
    }
    return ok_response(request, data)
