"""Inference endpoints: sync OCR and batch OCR APIs."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile, status

from app.api.deps import get_state, require_api_key
from app.api.errors import api_error
from app.api.idempotency import infer_request_hash
from app.api.uploads import validate_upload
from app.api.utils import ok_response
from app.services.dispatch_service import DispatchRequestError
from app.services.idempotency import IdempotencyConflictError
from app.services.ocr.base import OCREngineBusyError
from app.services.model_runtime import is_engine_active, resolve_effective_engine
from app.schemas.server import ServerKind
from app.services.state import AppState

router = APIRouter(prefix="/v1", tags=["inference"])

_INFER_RESPONSE_EXAMPLE = {
    "ok": True,
    "meta": {"request_id": "ab12cd34", "timestamp": "2026-03-24T18:00:00+09:00"},
    "data": {
        "doc_id": "c8f5a8f8-8b3a-4ac2-9f3c-0d8bcf271111",
        "filename": "sample.pdf",
        "content_type": "application/pdf",
        "engine_used": "glm",
        "confidence": 0.93,
        "raw_text": "raw extracted text",
        "corrected_text": "normalized text",
        "blocks": [],
        "domain": {
            "doc_type": "notice",
            "title": "sample.pdf",
            "summary": None,
            "entities": {
                "dates": [],
                "amounts": [],
                "subjects": [],
                "keywords": [],
                "persons": [],
                "orgs": [],
                "phones": [],
                "emails": [],
            },
            "fields": {},
        },
        "latency_ms": 832,
        "step_timings": {
            "preprocessing_ms": 48,
            "ocr_ms": 621,
            "postprocess_ms": 12,
            "transform_ms": 21,
        },
    },
}

_ERROR_EXAMPLE = {
    "ok": False,
    "meta": {"request_id": "ab12cd34"},
    "error": {"code": "INFER_FAILED", "message": "Unsupported file type"},
}


def _normalize_engine_hint(engine_hint: str | None) -> str | None:
    if engine_hint is None:
        return None
    value = str(engine_hint).strip().lower()
    return value or None


def _resolve_engine_hint(state: AppState, engine_hint: str | None) -> str | None:
    normalized = _normalize_engine_hint(engine_hint)
    if normalized and normalized != "auto":
        if not is_engine_active(state, normalized):
            raise RuntimeError(
                f"Engine `{normalized}` is not active. Activate the model first from /ops/models."
            )
        if normalized == "paddle" and not state.router.paddle_engine.available():
            raise RuntimeError("Active Paddle model is unavailable")
        if normalized == "glm" and not state.router.glm_engine.available():
            raise RuntimeError("Active GLM model is unavailable")
        return normalized

    active_engine = resolve_effective_engine(state, sync_registry=True)
    if active_engine == "paddle" and state.router.paddle_engine.available():
        return "paddle"
    if active_engine == "glm" and state.router.glm_engine.available():
        return "glm"
    if active_engine in {"paddle", "glm"}:
        raise RuntimeError(f"Active model `{active_engine}` is unavailable")
    raise RuntimeError("No active model. Activate a model from /ops/models first.")


def _record_model_metric(state: AppState, engine_used: str, success: bool, latency_ms: int) -> None:
    for model in state.model_registry.list_models():
        if model.engine == engine_used:
            state.model_registry.record(model.model_id, success=success, latency_ms=latency_ms)
            break


def _try_acquire_engine_gate(state: AppState, engine: str) -> bool:
    gate = getattr(state, "engine_gate", None)
    if gate is None:
        return True
    return bool(gate.try_acquire(engine))


def _release_engine_gate(state: AppState, engine: str) -> None:
    gate = getattr(state, "engine_gate", None)
    if gate is None:
        return
    gate.release(engine)


@router.post(
    "/infer",
    dependencies=[Depends(require_api_key)],
    responses={
        200: {"description": "Inference completed", "content": {"application/json": {"example": _INFER_RESPONSE_EXAMPLE}}},
        400: {"description": "Inference error", "content": {"application/json": {"example": _ERROR_EXAMPLE}}},
        409: {
            "description": "Idempotency conflict",
            "content": {
                "application/json": {
                    "example": {
                        "ok": False,
                        "meta": {"request_id": "ab12cd34"},
                        "error": {
                            "code": "IDEMPOTENCY_CONFLICT",
                            "message": "idempotency key reused with different payload",
                        },
                    }
                }
            },
        },
    },
)
async def infer(
    request: Request,
    file: UploadFile = File(...),
    doc_id: str | None = Form(default=None),
    engine_hint: str | None = Form(default="auto"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    state: AppState = Depends(get_state),
):
    if state.dispatch is None:
        raise api_error(status.HTTP_500_INTERNAL_SERVER_ERROR, "DISPATCH_UNAVAILABLE", "dispatch service is unavailable")

    payload = await file.read()
    validate_upload(state, file, payload)

    active_server = state.dispatch.active_server()
    if active_server.kind == ServerKind.local:
        try:
            resolved_engine = _resolve_engine_hint(state, engine_hint)
        except RuntimeError as exc:
            raise api_error(status.HTTP_409_CONFLICT, "MODEL_NOT_READY", str(exc)) from exc
    else:
        resolved_engine = _normalize_engine_hint(engine_hint) or "auto"

    filename = file.filename or "upload.bin"
    req_hash = infer_request_hash(
        payload=payload,
        filename=filename,
        doc_id=doc_id,
        engine_hint=f"{active_server.server_id}|{resolved_engine}",
    )

    if idempotency_key:
        # Replay exact same request safely without re-running OCR.
        try:
            cached = state.idempotency.get(
                route="/v1/infer",
                key=idempotency_key,
                request_hash=req_hash,
            )
        except IdempotencyConflictError as exc:
            raise api_error(
                status.HTTP_409_CONFLICT,
                "IDEMPOTENCY_CONFLICT",
                str(exc),
            ) from exc
        if cached is not None:
            state.metrics.inc("infer_idempotent_hit_total")
            return ok_response(request, cached)

    gate_acquired = True
    if active_server.kind == ServerKind.local:
        gate_acquired = _try_acquire_engine_gate(state, resolved_engine)
        if not gate_acquired:
            raise api_error(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "ENGINE_BUSY",
                f"{resolved_engine} inference already running",
            )
    try:
        response_data = await state.dispatch.infer(
            filename=filename,
            file_bytes=payload,
            content_type=file.content_type or "application/octet-stream",
            engine_hint=resolved_engine,
            doc_id=doc_id,
        )
    except DispatchRequestError as exc:
        state.metrics.inc("infer_failure_total")
        raise api_error(exc.status_code, exc.code, exc.message) from exc
    except OCREngineBusyError as exc:
        raise api_error(status.HTTP_429_TOO_MANY_REQUESTS, "ENGINE_BUSY", str(exc)) from exc
    except Exception as exc:
        state.metrics.inc("infer_failure_total")
        raise api_error(status.HTTP_400_BAD_REQUEST, "INFER_FAILED", str(exc)) from exc
    finally:
        if active_server.kind == ServerKind.local and gate_acquired:
            _release_engine_gate(state, resolved_engine)

    state.metrics.inc("infer_success_total")
    engine_used = str(response_data.get("engine_used") or "")
    latency_ms = int(response_data.get("latency_ms", 0) or 0)
    if active_server.kind == ServerKind.local and engine_used:
        _record_model_metric(state, engine_used, success=True, latency_ms=latency_ms)
    if idempotency_key:
        state.idempotency.put(
            route="/v1/infer",
            key=idempotency_key,
            request_hash=req_hash,
            response_data=response_data,
        )
    # Sync inference is persisted directly because there is no job wrapper.
    state.persistence.insert_result(job_id=None, result_data=response_data)
    state.persistence.insert_audit(
        action="infer.sync",
        target_type="document",
        target_id=str(response_data.get("doc_id", "")),
        detail={
            "filename": response_data.get("filename"),
            "engine_used": response_data.get("engine_used"),
            "latency_ms": response_data.get("latency_ms"),
        },
    )
    return ok_response(request, response_data)


@router.post(
    "/infer/batch",
    dependencies=[Depends(require_api_key)],
    responses={
        200: {
            "description": "Batch inference completed",
            "content": {
                "application/json": {
                    "example": {
                        "ok": True,
                        "meta": {"request_id": "ab12cd34"},
                        "data": {
                            "total": 2,
                            "success": 1,
                            "failed": 1,
                            "results": [{"doc_id": "doc-1", "engine_used": "paddle"}],
                            "errors": [
                                {
                                    "index": 2,
                                    "filename": "bad.txt",
                                    "code": "INFER_FAILED",
                                    "message": "Unsupported extension: .txt",
                                }
                            ],
                        },
                    }
                }
            },
        }
    },
)
async def infer_batch(
    request: Request,
    files: list[UploadFile] = File(...),
    engine_hint: str | None = Form(default="auto"),
    state: AppState = Depends(get_state),
):
    if state.dispatch is None:
        raise api_error(status.HTTP_500_INTERNAL_SERVER_ERROR, "DISPATCH_UNAVAILABLE", "dispatch service is unavailable")

    if not files:
        raise api_error(status.HTTP_400_BAD_REQUEST, "INVALID_PAYLOAD", "No files provided")
    if len(files) > 20:
        raise api_error(status.HTTP_400_BAD_REQUEST, "INVALID_PAYLOAD", "Max 20 files per batch")

    active_server = state.dispatch.active_server()
    if active_server.kind == ServerKind.local:
        try:
            resolved_engine = _resolve_engine_hint(state, engine_hint)
        except RuntimeError as exc:
            raise api_error(status.HTTP_409_CONFLICT, "MODEL_NOT_READY", str(exc)) from exc
    else:
        resolved_engine = _normalize_engine_hint(engine_hint) or "auto"

    results: list[dict] = []
    errors: list[dict] = []
    prepared: list[tuple[int, str, str | None, bytes]] = []

    for idx, file in enumerate(files, start=1):
        payload = await file.read()
        try:
            validate_upload(state, file, payload)
        except HTTPException as exc:
            state.metrics.inc("infer_failure_total")
            detail = exc.detail if isinstance(exc.detail, dict) else {"code": "INFER_FAILED", "message": str(exc.detail)}
            errors.append(
                {
                    "index": idx,
                    "filename": file.filename,
                    "code": str(detail.get("code", "INFER_FAILED")),
                    "message": str(detail.get("message", "Validation failed")),
                }
            )
            continue
        except Exception as exc:
            state.metrics.inc("infer_failure_total")
            errors.append(
                {
                    "index": idx,
                    "filename": file.filename,
                    "code": "INFER_FAILED",
                    "message": str(exc),
                }
            )
            continue
        prepared.append((idx, file.filename or f"upload-{idx}.bin", file.content_type, payload))

    if active_server.kind != ServerKind.local:
        remote_files = [(filename, content_type, payload) for _idx, filename, content_type, payload in prepared]
        try:
            data = await state.dispatch.infer_batch(files=remote_files, engine_hint=resolved_engine)
        except DispatchRequestError as exc:
            raise api_error(exc.status_code, exc.code, exc.message) from exc
        return ok_response(request, data)

    concurrency = max(1, int(getattr(state.settings, "ocr_concurrency", 1)))
    sem = asyncio.Semaphore(concurrency)

    async def _run_one(
        idx: int,
        filename: str,
        content_type: str | None,
        payload: bytes,
    ):
        async with sem:
            try:
                result = await state.pipeline.process_async(
                    filename=filename,
                    file_bytes=payload,
                    content_type=content_type,
                    engine_hint=resolved_engine,
                    doc_id=None,
                )
            except OCREngineBusyError as exc:
                raise RuntimeError(f"ENGINE_BUSY: {exc}") from exc
            return idx, filename, result

    outcomes = await asyncio.gather(
        *[
            _run_one(idx=idx, filename=filename, content_type=content_type, payload=payload)
            for idx, filename, content_type, payload in prepared
        ],
        return_exceptions=True,
    )

    for (idx, filename, _content_type, _payload), outcome in zip(prepared, outcomes):
        if isinstance(outcome, Exception):
            state.metrics.inc("infer_failure_total")
            errors.append(
                {
                    "index": idx,
                    "filename": filename,
                    "code": "INFER_FAILED",
                    "message": str(outcome),
                }
            )
            continue

        _idx, _filename, result = outcome
        state.metrics.inc("infer_success_total")
        _record_model_metric(state, result.engine_used, success=True, latency_ms=result.latency_ms)
        dumped = result.model_dump()
        results.append(dumped)
        state.persistence.insert_result(job_id=None, result_data=dumped)

    return ok_response(
        request,
        {
            "total": len(files),
            "success": len(results),
            "failed": len(errors),
            "results": results,
            "errors": errors,
        },
    )
