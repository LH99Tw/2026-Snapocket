"""Dependency functions for auth and app state injection."""

from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, Request, status

from app.services.state import AppState


def get_state(request: Request) -> AppState:
    return request.app.state.container


def require_api_key(request: Request, x_api_key: str | None = Header(default=None)) -> None:
    expected = request.app.state.container.settings.api_key
    if not expected:
        return
    if x_api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "Invalid API key"},
        )


def require_ops_basic_auth(request: Request) -> None:
    # Keep ops UI open if no credentials configured.
    settings = request.app.state.container.settings
    if not settings.ops_basic_user or not settings.ops_basic_pass:
        return

    # Parse "Authorization: Basic ..."
    # We intentionally use HTTPBasic helper via dependency-like call.
    # FastAPI will not auto-resolve here, so we parse the header manually.
    auth_value = request.headers.get("authorization", "")
    if not auth_value.startswith("Basic "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "OPS_AUTH_REQUIRED", "message": "Basic auth required"},
            headers={"WWW-Authenticate": "Basic"},
        )

    import base64

    try:
        decoded = base64.b64decode(auth_value.split(" ", 1)[1]).decode("utf-8")
        username, password = decoded.split(":", 1)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "OPS_AUTH_INVALID", "message": "Invalid authorization header"},
            headers={"WWW-Authenticate": "Basic"},
        ) from exc

    if not (
        secrets.compare_digest(username, settings.ops_basic_user)
        and secrets.compare_digest(password, settings.ops_basic_pass)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "OPS_AUTH_INVALID", "message": "Invalid credentials"},
            headers={"WWW-Authenticate": "Basic"},
        )
