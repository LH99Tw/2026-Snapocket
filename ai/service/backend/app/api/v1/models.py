"""Model registry endpoints (register/activate/rollback/metrics)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from app.api.deps import get_state, require_api_key
from app.api.errors import api_error
from app.api.utils import ok_response
from app.schemas.model import ModelInfo
from app.services.model_runtime import (
    activate_model_runtime,
    deactivate_model_runtime,
    resolve_effective_engine,
)
from app.services.state import AppState

router = APIRouter(prefix="/v1", tags=["models"])


def _canonical_model_id(model_id: str) -> str:
    token = str(model_id or "").strip()
    if token == "ollama-paddleocr-vl":
        return "llamacpp-paddleocr-vl"
    if token == "ollama-glm-ocr":
        return "llamacpp-glm-ocr"
    return token


@router.get("/models", dependencies=[Depends(require_api_key)])
def list_models(request: Request, state: AppState = Depends(get_state)):
    resolve_effective_engine(state, sync_registry=True)
    models = [model.model_dump() for model in state.model_registry.list_models()]
    return ok_response(request, models)


@router.post("/models/register", dependencies=[Depends(require_api_key)])
def register_model(model: ModelInfo, request: Request, state: AppState = Depends(get_state)):
    state.model_registry.register_model(model)
    return ok_response(request, {"registered": model.model_id})


@router.post("/models/{model_id}/activate", dependencies=[Depends(require_api_key)])
def activate_model(model_id: str, request: Request, state: AppState = Depends(get_state)):
    model_id = _canonical_model_id(model_id)
    try:
        activated, runtime = activate_model_runtime(state, model_id)
    except KeyError as exc:
        raise api_error(status.HTTP_404_NOT_FOUND, "MODEL_NOT_FOUND", "Model not found") from exc
    except RuntimeError as exc:
        raise api_error(status.HTTP_409_CONFLICT, "MODEL_ACTIVATION_FAILED", str(exc)) from exc
    payload = activated.model_dump()
    payload.update(runtime)
    return ok_response(request, payload)


@router.post("/models/{model_id}/deactivate", dependencies=[Depends(require_api_key)])
def deactivate_model(model_id: str, request: Request, state: AppState = Depends(get_state)):
    model_id = _canonical_model_id(model_id)
    try:
        deactivated, runtime = deactivate_model_runtime(state, model_id)
    except KeyError as exc:
        raise api_error(status.HTTP_404_NOT_FOUND, "MODEL_NOT_FOUND", "Model not found") from exc
    payload = deactivated.model_dump()
    payload.update(runtime)
    return ok_response(request, payload)


@router.post("/models/{model_id}/rollback", dependencies=[Depends(require_api_key)])
def rollback_model(model_id: str, request: Request, state: AppState = Depends(get_state)):
    model_id = _canonical_model_id(model_id)
    try:
        target = state.model_registry.rollback(model_id)
        rolled_back, runtime = activate_model_runtime(state, target.model_id)
    except KeyError as exc:
        raise api_error(status.HTTP_404_NOT_FOUND, "MODEL_NOT_FOUND", "Model not found") from exc
    except RuntimeError as exc:
        raise api_error(status.HTTP_409_CONFLICT, "ROLLBACK_UNAVAILABLE", str(exc)) from exc
    payload = rolled_back.model_dump()
    payload.update(runtime)
    return ok_response(request, payload)


@router.post("/models/rollback", dependencies=[Depends(require_api_key)])
def rollback_latest(request: Request, state: AppState = Depends(get_state)):
    try:
        target = state.model_registry.rollback()
        rolled_back, runtime = activate_model_runtime(state, target.model_id)
    except RuntimeError as exc:
        raise api_error(status.HTTP_409_CONFLICT, "ROLLBACK_UNAVAILABLE", str(exc)) from exc
    payload = rolled_back.model_dump()
    payload.update(runtime)
    return ok_response(request, payload)


@router.get("/models/{model_id}/metrics", dependencies=[Depends(require_api_key)])
def model_metrics(model_id: str, request: Request, state: AppState = Depends(get_state)):
    model_id = _canonical_model_id(model_id)
    try:
        metrics = state.model_registry.get_metrics(model_id)
    except KeyError as exc:
        raise api_error(status.HTTP_404_NOT_FOUND, "MODEL_NOT_FOUND", "Model not found") from exc
    return ok_response(request, metrics.model_dump())
