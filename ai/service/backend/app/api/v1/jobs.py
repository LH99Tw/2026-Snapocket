"""Asynchronous job endpoints for OCR processing."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Header, Request, UploadFile, status

from app.api.deps import get_state, require_api_key
from app.api.errors import api_error
from app.api.idempotency import job_request_hash
from app.api.uploads import validate_upload
from app.api.utils import ok_response
from app.schemas.job import JobStatus
from app.schemas.server import ServerKind
from app.services.dispatch_service import DispatchRequestError
from app.services.idempotency import IdempotencyConflictError
from app.services.model_runtime import is_engine_active, resolve_effective_engine
from app.services.state import AppState

router = APIRouter(prefix="/v1", tags=["jobs"])

_CREATE_JOB_RESPONSE_EXAMPLE = {
    "ok": True,
    "meta": {"request_id": "ab12cd34"},
    "data": {"job_id": "7d824500-5218-4055-a8c4-f7aedb8c5edc"},
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


@router.post(
    "/jobs",
    dependencies=[Depends(require_api_key)],
    responses={
        200: {"description": "Job created", "content": {"application/json": {"example": _CREATE_JOB_RESPONSE_EXAMPLE}}},
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
async def create_job(
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

    req_hash = job_request_hash(
        payload=payload,
        filename=filename,
        doc_id=doc_id,
        engine_hint=f"{active_server.server_id}|{resolved_engine}",
    )
    if idempotency_key:
        # Same idempotency key + same payload => return existing job_id.
        try:
            cached = state.idempotency.get(
                route="/v1/jobs",
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
            state.metrics.inc("jobs_idempotent_hit_total")
            return ok_response(request, cached)

    try:
        job_id = state.dispatch.create_job(
            filename=filename,
            file_bytes=payload,
            content_type=file.content_type,
            engine_hint=resolved_engine,
            doc_id=doc_id,
        )
    except DispatchRequestError as exc:
        raise api_error(exc.status_code, exc.code, exc.message) from exc

    response_data = {"job_id": job_id}
    if idempotency_key:
        state.idempotency.put(
            route="/v1/jobs",
            key=idempotency_key,
            request_hash=req_hash,
            response_data=response_data,
        )
    state.persistence.insert_audit(
        action="job.create",
        target_type="job",
        target_id=job_id,
        detail={"filename": filename, "engine_hint": resolved_engine},
    )
    return ok_response(request, response_data)


@router.get("/jobs", dependencies=[Depends(require_api_key)])
def list_jobs(request: Request, state: AppState = Depends(get_state)):
    if state.dispatch is None:
        raise api_error(status.HTTP_500_INTERNAL_SERVER_ERROR, "DISPATCH_UNAVAILABLE", "dispatch service is unavailable")
    try:
        jobs = state.dispatch.list_jobs()
    except DispatchRequestError as exc:
        raise api_error(exc.status_code, exc.code, exc.message) from exc
    return ok_response(request, jobs)


@router.get("/jobs/{job_id}", dependencies=[Depends(require_api_key)])
def get_job(job_id: str, request: Request, state: AppState = Depends(get_state)):
    if state.dispatch is None:
        raise api_error(status.HTTP_500_INTERNAL_SERVER_ERROR, "DISPATCH_UNAVAILABLE", "dispatch service is unavailable")
    try:
        info = state.dispatch.get_job(job_id=job_id)
    except KeyError as exc:
        raise api_error(status.HTTP_404_NOT_FOUND, "JOB_NOT_FOUND", "Job not found") from exc
    except DispatchRequestError as exc:
        raise api_error(exc.status_code, exc.code, exc.message) from exc
    return ok_response(request, info)


@router.get("/jobs/{job_id}/result", dependencies=[Depends(require_api_key)])
def get_job_result(job_id: str, request: Request, state: AppState = Depends(get_state)):
    if state.dispatch is None:
        raise api_error(status.HTTP_500_INTERNAL_SERVER_ERROR, "DISPATCH_UNAVAILABLE", "dispatch service is unavailable")
    try:
        payload = state.dispatch.get_job_result(job_id=job_id)
    except KeyError as exc:
        raise api_error(status.HTTP_404_NOT_FOUND, "JOB_NOT_FOUND", "Job not found") from exc
    except DispatchRequestError as exc:
        raise api_error(exc.status_code, exc.code, exc.message) from exc
    return ok_response(request, payload)


@router.post("/jobs/{job_id}/cancel", dependencies=[Depends(require_api_key)])
def cancel_job(job_id: str, request: Request, state: AppState = Depends(get_state)):
    if state.dispatch is None:
        raise api_error(status.HTTP_500_INTERNAL_SERVER_ERROR, "DISPATCH_UNAVAILABLE", "dispatch service is unavailable")
    try:
        cancelled = state.dispatch.cancel_job(job_id=job_id)
    except KeyError as exc:
        raise api_error(status.HTTP_404_NOT_FOUND, "JOB_NOT_FOUND", "Job not found") from exc
    except DispatchRequestError as exc:
        raise api_error(exc.status_code, exc.code, exc.message) from exc

    if not cancelled:
        try:
            info = state.dispatch.get_job(job_id=job_id)
            status_value = info.get("status")
        except Exception:
            status_value = "unknown"
        if status_value in {JobStatus.running.value, JobStatus.succeeded.value, JobStatus.failed.value}:
            raise api_error(status.HTTP_409_CONFLICT, "JOB_NOT_CANCELLABLE", f"Job status is {status_value}")

    state.persistence.insert_audit(
        action="job.cancel",
        target_type="job",
        target_id=job_id,
        detail={"cancelled": cancelled},
    )
    return ok_response(request, {"job_id": job_id, "cancelled": cancelled})


@router.post("/jobs/{job_id}/retry", dependencies=[Depends(require_api_key)])
def retry_job(job_id: str, request: Request, state: AppState = Depends(get_state)):
    if state.dispatch is None:
        raise api_error(status.HTTP_500_INTERNAL_SERVER_ERROR, "DISPATCH_UNAVAILABLE", "dispatch service is unavailable")
    try:
        info = state.dispatch.get_job(job_id=job_id)
        status_value = str(info.get("status") or "")
        if status_value not in {JobStatus.failed.value, JobStatus.cancelled.value}:
            raise api_error(
                status.HTTP_409_CONFLICT,
                "JOB_NOT_RETRIABLE",
                f"Job status is {status_value}",
            )
        new_job_id = state.dispatch.retry_job(job_id=job_id)
    except KeyError as exc:
        raise api_error(status.HTTP_404_NOT_FOUND, "JOB_NOT_FOUND", "Job not found") from exc
    except DispatchRequestError as exc:
        raise api_error(exc.status_code, exc.code, exc.message) from exc
    state.persistence.insert_audit(
        action="job.retry",
        target_type="job",
        target_id=job_id,
        detail={"retry_job_id": new_job_id},
    )
    return ok_response(request, {"job_id": job_id, "retry_job_id": new_job_id})
