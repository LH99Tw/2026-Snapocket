"""Helpers to keep registry active model aligned with runtime availability."""

from __future__ import annotations

import logging

from app.schemas.model import ModelInfo
from app.services.state import AppState

logger = logging.getLogger(__name__)


def resolve_effective_engine(state: AppState, *, sync_registry: bool = True) -> str:
    # NOTE:
    # `sync_registry` is intentionally ignored for now because automatic active-model
    # mutation makes explicit operator ON/OFF control impossible.
    del sync_registry
    active = state.model_registry.active_engine()
    return active if active in {"paddle", "glm"} else "auto"


def _find_model(state: AppState, model_id: str) -> ModelInfo:
    for model in state.model_registry.list_models():
        if model.model_id == model_id:
            return model
    raise KeyError(model_id)


def _engine_adapter(state: AppState, engine: str):
    if engine == "paddle":
        return state.router.paddle_engine
    if engine == "glm":
        return state.router.glm_engine
    raise RuntimeError(f"unsupported engine: {engine}")


def _active_model(state: AppState) -> ModelInfo | None:
    for model in state.model_registry.list_models():
        if model.active:
            return model
    return None


def _resolve_model_ref(state: AppState, model: ModelInfo) -> str:
    if model.engine == "paddle":
        return state.settings.llm_model_paddle
    if model.engine == "glm":
        return state.settings.llm_model_glm
    raise RuntimeError(f"unsupported engine: {model.engine}")


def _rebind_engine_model_ref(engine: object, model_ref: str) -> None:
    ref = str(model_ref or "").strip()
    if not ref:
        raise RuntimeError("model reference is empty")

    if hasattr(engine, "reconfigure_model"):
        engine.reconfigure_model(ref)
        return
    if hasattr(engine, "reconfigure_model_path"):
        engine.reconfigure_model_path(ref)
        return

    setattr(engine, "model", ref)
    setattr(engine, "_availability_cache", None)
    setattr(engine, "_availability_checked_at", 0.0)
    setattr(engine, "_last_error", None)


def is_engine_active(state: AppState, engine: str) -> bool:
    target = str(engine or "").strip().lower()
    for model in state.model_registry.list_models():
        if model.engine == target and model.active:
            return True
    return False


def activate_model_runtime(state: AppState, model_id: str) -> tuple[ModelInfo, dict[str, str | bool]]:
    model = _find_model(state, model_id)
    engine = _engine_adapter(state, model.engine)
    currently_active = _active_model(state)
    prev_engine = None
    if currently_active is not None and currently_active.model_id != model_id:
        prev_engine = _engine_adapter(state, currently_active.engine)

    # Free memory from currently loaded engine before loading another large VLM.
    if prev_engine is not None:
        if hasattr(prev_engine, "set_pinned"):
            try:
                prev_engine.set_pinned(False)
            except Exception:
                pass
        try:
            prev_engine.unload()
        except Exception as exc:
            logger.warning("previous engine unload failed before activate(%s): %s", model.engine, exc)

    target_ref = _resolve_model_ref(state, model)
    _rebind_engine_model_ref(engine, target_ref)

    # Some engines expose `set_pinned` to keep model runtime prepared while active.
    if hasattr(engine, "set_pinned"):
        try:
            engine.set_pinned(True)
        except Exception:
            pass

    warmup_ok = False
    warmup_message = ""
    try:
        warmup_ok = bool(engine.warmup())
        if not warmup_ok:
            warmup_message = "engine warmup returned false"
            raise RuntimeError(warmup_message)
    except Exception as exc:
        warmup_message = warmup_message or (str(exc) or repr(exc))
        if hasattr(engine, "set_pinned"):
            try:
                engine.set_pinned(False)
            except Exception:
                pass
        raise RuntimeError(warmup_message) from exc

    activated = state.model_registry.activate(model_id)
    return activated, {"runtime_prepared": warmup_ok, "runtime_message": warmup_message}


def deactivate_model_runtime(state: AppState, model_id: str) -> tuple[ModelInfo, dict[str, str | bool]]:
    model = _find_model(state, model_id)
    engine = _engine_adapter(state, model.engine)
    deactivated = state.model_registry.deactivate(model_id)
    if not model.active:
        return deactivated, {"runtime_unloaded": False, "runtime_message": "model was not active"}

    if hasattr(engine, "set_pinned"):
        try:
            engine.set_pinned(False)
        except Exception:
            pass

    unload_ok = False
    unload_message = ""
    try:
        unload_ok = bool(engine.unload())
        if not unload_ok:
            unload_message = "engine unload returned false"
    except Exception as exc:
        unload_message = str(exc) or repr(exc)
        logger.warning("engine unload failed for %s: %s", model.engine, unload_message)

    return deactivated, {"runtime_unloaded": unload_ok, "runtime_message": unload_message}
