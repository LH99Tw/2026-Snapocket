"""FastAPI application entrypoint and global middleware/handlers."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1 import infer, jobs, models, system
from app.core.logging import configure_logging
from app.ops.routes import router as ops_router
from app.services.state import build_app_state

configure_logging()

_FRONTEND_CANDIDATES = (
    Path(__file__).resolve().parents[1] / "frontend",
    Path(__file__).resolve().parents[2] / "frontend",
)
_FRONTEND_DIR = next((p for p in _FRONTEND_CANDIDATES if p.exists()), _FRONTEND_CANDIDATES[0])

app = FastAPI(title="Snapocket ML/AIOps API", version="1.0.0")
app.mount("/static", StaticFiles(directory=str(_FRONTEND_DIR / "static")), name="static")


@app.middleware("http")
async def request_context(request: Request, call_next):
    request.state.request_id = request.headers.get("x-request-id") or str(uuid4())
    response = await call_next(request)
    response.headers["x-request-id"] = request.state.request_id
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "ok": False,
            "meta": {"request_id": request.state.request_id},
            "error": {"code": "INTERNAL_ERROR", "message": str(exc)},
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail
    code = "HTTP_ERROR"
    message = "Request failed"
    if isinstance(detail, dict):
        code = str(detail.get("code", code))
        message = str(detail.get("message", message))
    elif isinstance(detail, str):
        message = detail
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "ok": False,
            "meta": {"request_id": request.state.request_id},
            "error": {"code": code, "message": message},
        },
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "ok": False,
            "meta": {"request_id": request.state.request_id},
            "error": {
                "code": "INVALID_PAYLOAD",
                "message": str(exc.errors()),
            },
        },
    )


@app.on_event("startup")
def startup_event() -> None:
    app.state.container = build_app_state()


@app.on_event("shutdown")
def shutdown_event() -> None:
    container = getattr(app.state, "container", None)
    if container is None:
        return
    # Graceful teardown for background workers and SQL connections.
    if container.model_prober is not None:
        container.model_prober.stop()
    container.job_manager.shutdown()
    container.persistence.shutdown()


app.include_router(system.router)
app.include_router(infer.router)
app.include_router(jobs.router)
app.include_router(models.router)
app.include_router(ops_router)
