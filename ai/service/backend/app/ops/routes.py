"""SSR routes for lightweight ML/AIOps operator dashboard."""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from app.api.uploads import validate_upload
from app.api.deps import get_state, require_ops_basic_auth
from app.services.ocr.base import OCREngineBusyError
from app.services.model_runtime import (
    activate_model_runtime,
    deactivate_model_runtime,
    is_engine_active,
    resolve_effective_engine,
)
from app.services.state import AppState

router = APIRouter(prefix="/ops", tags=["ops"], dependencies=[Depends(require_ops_basic_auth)])
_FRONTEND_CANDIDATES = (
    Path(__file__).resolve().parents[2] / "frontend",
    Path(__file__).resolve().parents[3] / "frontend",
)
_FRONTEND_DIR = next((p for p in _FRONTEND_CANDIDATES if p.exists()), _FRONTEND_CANDIDATES[0])
templates = Jinja2Templates(directory=str(_FRONTEND_DIR / "templates"))


def _redirect_models(*, level: str = "warn", message: str = "") -> RedirectResponse:
    url = "/ops/models"
    msg = message.strip()
    if msg:
        safe_level = level if level in {"ok", "warn", "err"} else "warn"
        query = urlencode({"level": safe_level, "message": msg[:240]})
        url = f"{url}?{query}"
    return RedirectResponse(url=url, status_code=303)


def _paddle_model_ref(state: AppState) -> str:
    model = str(getattr(state.router.paddle_engine, "model", "") or "").strip()
    if not model:
        model = state.settings.llm_model_paddle
    return f"llm:{model}"


def _glm_model_ref(state: AppState) -> str:
    model = str(getattr(state.router.glm_engine, "model", "") or "").strip()
    if not model:
        model = state.settings.llm_model_glm
    return f"llm:{model}"


def _model_ref_for_row(state: AppState, model_id: str, engine: str) -> str:
    if model_id in {"llamacpp-paddleocr-vl", "ollama-paddleocr-vl", "llama-paddleocr-vl"}:
        return f"llm:{state.settings.llm_model_paddle}"
    if model_id in {"llamacpp-glm-ocr", "ollama-glm-ocr", "llama-glm-ocr"}:
        return f"llm:{state.settings.llm_model_glm}"
    if engine == "paddle":
        return _paddle_model_ref(state)
    if engine == "glm":
        return _glm_model_ref(state)
    return "llm:unknown"


def _model_map(state: AppState) -> dict[str, str]:
    return {
        "paddle": _paddle_model_ref(state),
        "glm": _glm_model_ref(state),
    }


def _canonical_model_id(model_id: str) -> str:
    token = str(model_id or "").strip()
    if token == "ollama-paddleocr-vl":
        return "llamacpp-paddleocr-vl"
    if token == "ollama-glm-ocr":
        return "llamacpp-glm-ocr"
    return token


@router.get("", response_class=HTMLResponse)
def ops_dashboard(request: Request, state: AppState = Depends(get_state)):
    resolve_effective_engine(state, sync_registry=True)
    paddle_up = state.router.paddle_engine.available()
    glm_up = state.router.glm_engine.available()
    paddle_model_ref = _paddle_model_ref(state)
    glm_model_ref = _glm_model_ref(state)

    engines = [
        {
            "name": "PaddleOCR-VL",
            "model": paddle_model_ref,
            "enabled": state.router.paddle_engine.enabled,
            "available": paddle_up,
        },
        {
            "name": "GLM-OCR",
            "model": glm_model_ref,
            "enabled": state.router.glm_engine.enabled,
            "available": glm_up,
        },
    ]

    engine_avail = {"paddle": paddle_up, "glm": glm_up}
    models = state.model_registry.list_models()
    for m in models:
        if m.active:
            m.status = "online" if engine_avail.get(m.engine) else "degraded"
        elif m.status != "inactive":
            m.status = "idle"

    context = {
        "request": request,
        "title": "Ops Dashboard",
        "engines": engines,
        "metrics": state.metrics.snapshot(),
        "jobs": state.job_manager.list_jobs(),
        "models": models,
    }
    return templates.TemplateResponse(name="ops_dashboard.html", context=context, request=request)


@router.get("/models", response_class=HTMLResponse)
def ops_models(request: Request, state: AppState = Depends(get_state)):
    resolve_effective_engine(state, sync_registry=True)
    paddle_up = state.router.paddle_engine.available()
    glm_up = state.router.glm_engine.available()
    engine_avail = {"paddle": paddle_up, "glm": glm_up}
    flash_message = request.query_params.get("message", "").strip()
    flash_level = request.query_params.get("level", "").strip().lower()
    if flash_level not in {"ok", "warn", "err"}:
        flash_level = "warn"
    flash = {"level": flash_level, "message": flash_message} if flash_message else None
    models = state.model_registry.list_models()
    model_refs = {m.model_id: _model_ref_for_row(state, m.model_id, m.engine) for m in models}
    for m in models:
        if m.active:
            m.status = "online" if engine_avail.get(m.engine) else "degraded"
        elif m.status != "inactive":
            m.status = "idle"

    context = {
        "request": request,
        "title": "Models",
        "models": models,
        "model_refs": model_refs,
        "engine_avail": engine_avail,
        "flash": flash,
    }
    return templates.TemplateResponse(name="ops_models.html", context=context, request=request)


@router.get("/models/{model_id}", response_class=HTMLResponse)
def ops_model_detail(model_id: str, request: Request, state: AppState = Depends(get_state)):
    resolve_effective_engine(state, sync_registry=True)
    models = state.model_registry.list_models()
    target = None
    for model in models:
        if model.model_id == model_id:
            target = model
            break
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")

    metrics = state.model_registry.get_metrics(model_id)
    context = {
        "request": request,
        "title": f"Model Detail · {model_id}",
        "model": target,
        "metrics": metrics,
    }
    return templates.TemplateResponse(name="ops_model_detail.html", context=context, request=request)


@router.post("/models/activate")
def ops_models_activate(model_id: str = Form(...), state: AppState = Depends(get_state)):
    model_id = _canonical_model_id(model_id)
    try:
        activate_model_runtime(state, model_id)
    except Exception as exc:
        return _redirect_models(level="err", message=f"Activate failed for {model_id}: {exc}")
    return _redirect_models(level="ok", message=f"Activated model {model_id}")


@router.post("/models/deactivate")
def ops_models_deactivate(model_id: str = Form(...), state: AppState = Depends(get_state)):
    model_id = _canonical_model_id(model_id)
    try:
        deactivate_model_runtime(state, model_id)
    except Exception as exc:
        return _redirect_models(level="err", message=f"Deactivate failed for {model_id}: {exc}")
    return _redirect_models(level="ok", message=f"Deactivated model {model_id}")


@router.post("/models/rollback")
def ops_models_rollback(model_id: str = Form(default=""), state: AppState = Depends(get_state)):
    model_id = _canonical_model_id(model_id)
    try:
        if model_id.strip():
            target = state.model_registry.rollback(model_id.strip())
        else:
            target = state.model_registry.rollback()
        activate_model_runtime(state, target.model_id)
    except Exception as exc:
        return _redirect_models(level="err", message=f"Rollback failed: {exc}")
    return _redirect_models(level="ok", message=f"Rolled back to {target.model_id}")


@router.get("/jobs", response_class=HTMLResponse)
def ops_jobs(
    request: Request,
    status_filter: str | None = Query(default=None),
    state: AppState = Depends(get_state),
):
    jobs = state.job_manager.list_jobs()
    if status_filter:
        jobs = [job for job in jobs if str(job.status) == status_filter]
    context = {
        "request": request,
        "title": "Jobs",
        "jobs": jobs,
        "status_filter": status_filter or "",
    }
    return templates.TemplateResponse(name="ops_jobs.html", context=context, request=request)


@router.post("/jobs/{job_id}/cancel")
def ops_jobs_cancel(job_id: str, state: AppState = Depends(get_state)):
    try:
        state.job_manager.cancel(job_id)
    except KeyError:
        pass
    return RedirectResponse(url="/ops/jobs", status_code=303)


@router.post("/jobs/{job_id}/retry")
def ops_jobs_retry(job_id: str, state: AppState = Depends(get_state)):
    try:
        info = state.job_manager.get_info(job_id)
        if str(info.status) in {"failed", "cancelled"}:
            state.job_manager.retry(job_id)
    except Exception:
        pass
    return RedirectResponse(url="/ops/jobs", status_code=303)


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_DOCKER_CONTAINER = "aiops-api"
_LOG_CONTAINERS = (
    "aiops-api",
    "aiops-redis",
    "aiops-postgres",
)
def _running_containers() -> set[str] | None:
    try:
        proc = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            check=False,
            timeout=1.0,
        )
    except (FileNotFoundError, PermissionError, subprocess.SubprocessError):
        return None

    if proc.returncode != 0:
        return None
    names = {
        line.strip()
        for line in (proc.stdout or "").splitlines()
        if line.strip()
    }
    return names


def _available_log_containers() -> tuple[str, ...]:
    names = _running_containers()
    if names is None:
        return _LOG_CONTAINERS

    preferred = tuple(c for c in _LOG_CONTAINERS if c in names)
    if preferred:
        return preferred

    if not names:
        return (_DOCKER_CONTAINER,)
    return tuple(sorted(names))


def _resolve_log_container_from(requested: str | None, available: tuple[str, ...]) -> str:
    candidate = (requested or "").strip()
    if candidate and candidate in available:
        return candidate
    if _DOCKER_CONTAINER in available:
        return _DOCKER_CONTAINER
    if available:
        return available[0]
    return _DOCKER_CONTAINER


@router.get("/logs", response_class=HTMLResponse)
def ops_logs(
    request: Request,
    tail: int = Query(default=200, ge=1, le=2000),
    container: str | None = Query(default=None),
):
    available = _available_log_containers()
    selected_container = _resolve_log_container_from(container, available)
    context = {
        "request": request,
        "title": "Logs",
        "tail": tail,
        "container": selected_container,
        "containers": available,
    }
    return templates.TemplateResponse(name="ops_logs.html", context=context, request=request)


@router.get("/logs/stream")
async def ops_logs_stream(
    request: Request,
    tail: int = Query(default=200, ge=1, le=2000),
    container: str | None = Query(default=None),
    state: AppState = Depends(get_state),
):
    available = _available_log_containers()
    selected_container = _resolve_log_container_from(container, available)

    async def _emit_log_buffer(prefix: str = ""):
        if prefix:
            yield f"data: {prefix}\n\n"
        entries = state.log_buffer.recent(tail)
        for entry in entries:
            text = f"{entry.timestamp} [{entry.level}] {entry.message}"
            yield f"data: {text}\n\n"

    async def _generate():
        proc = None
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "logs", "-f", "--tail", str(tail), selected_container,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            yield "event: connected\ndata: ok\n\n"

            while True:
                if await request.is_disconnected():
                    break
                try:
                    line = await asyncio.wait_for(proc.stdout.readline(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                if not line:
                    break
                text = _ANSI_RE.sub("", line.decode("utf-8", errors="replace")).rstrip()
                if text:
                    if "No such container" in text:
                        yield (
                            "event: warning\n"
                            f"data: {selected_container} not found; falling back to app log buffer\n\n"
                        )
                        async for payload in _emit_log_buffer():
                            yield payload
                        break
                    yield f"data: {text}\n\n"
        except FileNotFoundError:
            # Fallback for environments where docker binary/socket is unavailable in api runtime.
            yield "event: warning\ndata: Docker CLI unavailable; falling back to app log buffer\n\n"
            async for payload in _emit_log_buffer():
                yield payload
        except PermissionError:
            yield "event: warning\ndata: Docker socket permission denied; falling back to app log buffer\n\n"
            async for payload in _emit_log_buffer():
                yield payload
        except Exception as exc:
            yield f"event: error\ndata: {exc}\n\n"
        finally:
            if proc and proc.returncode is None:
                try:
                    proc.kill()
                    await proc.wait()
                except Exception:
                    pass
            yield "event: closed\ndata: stream ended\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/playground", response_class=HTMLResponse)
def ops_playground(request: Request, state: AppState = Depends(get_state)):
    effective_engine = resolve_effective_engine(state, sync_registry=True)
    model_map = _model_map(state)
    playground_timeout_ms = int(
        max(8_000, min(600_000, float(state.settings.playground_timeout_s) * 1000))
    )
    context = {
        "request": request,
        "title": "Inference Playground",
        "default_engine": state.settings.default_engine,
        "max_upload_mb": state.settings.max_upload_mb,
        "playground_timeout_ms": playground_timeout_ms,
        "active_engine": effective_engine or state.settings.default_engine,
        "model_map": model_map,
        "playground_backend_label": f"llama.cpp @ {state.settings.llm_base_url}",
        "runtime_engines": {
            "paddle": state.router.paddle_engine.available(),
            "glm": state.router.glm_engine.available(),
        },
    }
    return templates.TemplateResponse(name="ops_playground.html", context=context, request=request)


@router.post("/playground/infer")
async def ops_playground_infer(
    request: Request,
    file: UploadFile = File(...),
    engine_hint: str | None = Form(default="auto"),
    vlm_ocr_verify: bool = Form(default=False),
    doc_id: str | None = Form(default=None),
    state: AppState = Depends(get_state),
):
    from fastapi.responses import JSONResponse as _JSONResponse

    normalized_hint = (engine_hint or "auto").strip().lower()
    requested_engine = normalized_hint or "auto"
    if requested_engine != "auto":
        return _JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "PLAYGROUND_ENGINE_FIXED",
                    "message": "Playground engine selection is fixed to auto. Change active model in Models page.",
                }
            },
        )
    payload = await file.read()
    try:
        validate_upload(state, file, payload)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
        return _JSONResponse(status_code=exc.status_code, content={"error": detail})

    resolved: str | None = None
    active = resolve_effective_engine(state, sync_registry=True)
    if active == "paddle":
        if not is_engine_active(state, "paddle"):
            return _JSONResponse(
                status_code=409,
                content={"error": {"code": "MODEL_NOT_READY", "message": "Paddle model is not active"}},
            )
        if not state.router.paddle_engine.available():
            return _JSONResponse(
                status_code=409,
                content={"error": {"code": "MODEL_NOT_READY", "message": "Active Paddle model is unavailable"}},
            )
        resolved = "paddle"
    elif active == "glm":
        if not is_engine_active(state, "glm"):
            return _JSONResponse(
                status_code=409,
                content={"error": {"code": "MODEL_NOT_READY", "message": "GLM model is not active"}},
            )
        if not state.router.glm_engine.available():
            return _JSONResponse(
                status_code=409,
                content={"error": {"code": "MODEL_NOT_READY", "message": "Active GLM model is unavailable"}},
            )
        resolved = "glm"
    else:
        return _JSONResponse(
            status_code=409,
            content={
                "error": {
                    "code": "MODEL_NOT_READY",
                    "message": "No active model. Activate one from Models page first.",
                }
            },
        )

    timeout_s = max(8.0, min(600.0, float(state.settings.playground_timeout_s)))
    gate = getattr(state, "engine_gate", None)
    gate_acquired = True
    if gate is not None:
        gate_acquired = bool(gate.try_acquire(resolved))
    if not gate_acquired:
        return _JSONResponse(
            status_code=429,
            content={
                "error": {
                    "code": "ENGINE_BUSY",
                    "message": f"{resolved} inference already running",
                }
            },
        )
    try:
        process_kwargs = {
            "filename": file.filename or "upload.bin",
            "file_bytes": payload,
            "content_type": file.content_type or "",
            "engine_hint": resolved,
            "doc_id": doc_id,
        }
        if vlm_ocr_verify:
            process_kwargs["vlm_ocr_verify"] = True

        result = await asyncio.wait_for(
            state.pipeline.process_async(**process_kwargs),
            timeout=timeout_s,
        )
        body = result.model_dump()
        engine_used = str(body.get("engine_used") or resolved or requested_engine or "unknown")
        model_map = _model_map(state)
        body["requested_engine"] = requested_engine
        body["resolved_engine"] = resolved or requested_engine
        body["model_used"] = model_map.get(engine_used, "")
        body["vlm_ocr_verify"] = bool(vlm_ocr_verify)
        body["runtime"] = {
            "paddle": state.router.paddle_engine.available(),
            "glm": state.router.glm_engine.available(),
        }
        return body
    except asyncio.TimeoutError:
        return _JSONResponse(
            status_code=504,
            content={
                "error": {
                    "code": "PLAYGROUND_TIMEOUT",
                    "message": (
                        f"Inference timed out after {int(timeout_s)}s. "
                        "The engine may still be processing the previous request."
                    ),
                }
            },
        )
    except OCREngineBusyError as exc:
        return _JSONResponse(
            status_code=429,
            content={"error": {"code": "ENGINE_BUSY", "message": str(exc)}},
        )
    except Exception as exc:
        return _JSONResponse(
            status_code=400,
            content={"error": str(exc)},
        )
    finally:
        if gate is not None and gate_acquired:
            gate.release(resolved)


@router.get("/settings", response_class=HTMLResponse)
def ops_settings(request: Request, state: AppState = Depends(get_state)):
    env_items = [
        ("LLM_BASE_URL", "llm_base_url", "http://llama-server:8080"),
        ("LLM_MODEL_PADDLE", "llm_model_paddle", "PaddleOCR-VL-1.5-BF16.gguf"),
        ("LLM_MODEL_GLM", "llm_model_glm", "PaddleOCR-VL-1.5-BF16.gguf"),
        ("LLM_REQUEST_TIMEOUT_S", "llm_request_timeout_s", "120"),
        ("LLM_KEEP_ALIVE", "llm_keep_alive", "10m"),
        ("LLM_TEMPERATURE", "llm_temperature", "0"),
        ("LLM_IMAGE_MAX_SIDE_PX", "llm_image_max_side_px", "1536"),
        ("LLM_MAX_TOKENS", "llm_max_tokens", "96"),
        ("LOCAL_MODEL_HINT_OCR_ENABLE", "local_model_hint_ocr_enable", "true"),
        ("LOCAL_MODEL_HINT_OCR_LANGS", "local_model_hint_ocr_langs", "kor+eng"),
        ("LOCAL_MODEL_HINT_OCR_TIMEOUT_S", "local_model_hint_ocr_timeout_s", "1.2"),
        ("LOCAL_MODEL_HINT_OCR_MAX_CHARS", "local_model_hint_ocr_max_chars", "800"),
        ("OCR_CONCURRENCY", "ocr_concurrency", "1"),
        ("PLAYGROUND_TIMEOUT_S", "playground_timeout_s", "60"),
        ("DATABASE_URL", "database_url", "sqlite:///./data/aiops.db"),
        ("REDIS_URL", "redis_url", "redis://redis:6379/0"),
    ]
    settings_source: list[dict[str, str]] = []
    for env_key, attr, default in env_items:
        raw = os.getenv(env_key)
        settings_source.append(
            {
                "env_key": env_key,
                "value": str(getattr(state.settings, attr)),
                "source": "env" if raw is not None else "default",
                "raw": raw if raw is not None else default,
            }
        )

    model_checks: list[dict[str, str | bool]] = []
    engines = {
        "paddle": state.router.paddle_engine,
        "glm": state.router.glm_engine,
    }
    configured = {
        "paddle": state.settings.llm_model_paddle,
        "glm": state.settings.llm_model_glm,
    }
    for name in ("paddle", "glm"):
        engine = engines[name]
        detail = {}
        if hasattr(engine, "availability_detail"):
            try:
                detail = engine.availability_detail() or {}
            except Exception:
                detail = {}
        configured_model = str(configured[name])
        runtime_model = str(detail.get("model") or configured_model)
        backend = str(detail.get("base_url") or state.settings.llm_base_url)
        model_checks.append(
            {
                "engine": name,
                "configured_model": configured_model,
                "runtime_model": runtime_model,
                "base_url": backend,
                "available": bool(engine.available()),
                "last_error": str(detail.get("last_error") or ""),
            }
        )

    db_models = state.persistence.list_models()
    context = {
        "request": request,
        "title": "Settings",
        "settings": state.settings,
        "settings_source": settings_source,
        "model_checks": model_checks,
        "db_models": db_models,
    }
    return templates.TemplateResponse(name="ops_settings.html", context=context, request=request)
