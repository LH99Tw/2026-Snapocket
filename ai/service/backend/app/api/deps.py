"""Dependency functions for auth and app state injection."""

from __future__ import annotations

import ipaddress
import secrets
from functools import lru_cache

from fastapi import Header, HTTPException, Request, status

from app.services.state import AppState


def get_state(request: Request) -> AppState:
    return request.app.state.container


def _parse_ip_candidate(raw: str | None) -> ipaddress._BaseAddress | None:
    token = str(raw or "").strip()
    if not token:
        return None

    # [IPv6]:port
    if token.startswith("[") and "]" in token:
        token = token[1 : token.index("]")]
    # IPv4:port
    elif token.count(":") == 1 and "." in token.split(":", 1)[0]:
        token = token.split(":", 1)[0]

    # Drop IPv6 zone index (e.g. fe80::1%eth0)
    if "%" in token:
        token = token.split("%", 1)[0]

    try:
        parsed = ipaddress.ip_address(token)
    except ValueError:
        return None

    # Docker/Proxy can surface IPv4 mapped IPv6 addresses.
    if isinstance(parsed, ipaddress.IPv6Address) and parsed.ipv4_mapped:
        return parsed.ipv4_mapped
    return parsed


def _resolve_client_ip(request: Request) -> ipaddress._BaseAddress | None:
    settings = request.app.state.container.settings
    if bool(getattr(settings, "trust_x_forwarded_for", False)):
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            for token in forwarded.split(","):
                parsed = _parse_ip_candidate(token)
                if parsed is not None:
                    return parsed

    if request.client and request.client.host:
        parsed = _parse_ip_candidate(str(request.client.host))
        if parsed is not None:
            return parsed
    return None


@lru_cache(maxsize=8)
def _parse_allowed_networks(raw: str) -> tuple[object, ...]:
    networks: list[object] = []
    for token in str(raw or "").split(","):
        item = token.strip()
        if not item:
            continue
        try:
            networks.append(ipaddress.ip_network(item, strict=False))
        except Exception:
            continue
    return tuple(networks)


def _assert_client_allowed(request: Request) -> None:
    settings = request.app.state.container.settings
    networks = _parse_allowed_networks(settings.allowed_clients_raw)
    # Empty allowlist means unrestricted (opt-in hardening).
    if not networks:
        return

    client_ip = _resolve_client_ip(request)
    if client_ip is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "CLIENT_IP_DENIED", "message": "Client IP is not allowed"},
        )

    if any(client_ip in network for network in networks):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"code": "CLIENT_IP_DENIED", "message": "Client IP is not allowed"},
    )


def require_api_key(request: Request, x_api_key: str | None = Header(default=None)) -> None:
    _assert_client_allowed(request)
    expected = request.app.state.container.settings.api_key
    require_key = bool(request.app.state.container.settings.require_api_key)
    if not expected:
        if require_key:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "API_KEY_NOT_CONFIGURED", "message": "AIOPS_API_KEY is required"},
            )
        return
    if x_api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "Invalid API key"},
        )


def require_ops_basic_auth(request: Request) -> None:
    _assert_client_allowed(request)

    settings = request.app.state.container.settings
    if not settings.require_ops_basic_auth and (not settings.ops_basic_user or not settings.ops_basic_pass):
        return

    if not settings.ops_basic_user or not settings.ops_basic_pass:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "OPS_AUTH_NOT_CONFIGURED", "message": "OPS basic auth credentials are required"},
            headers={"WWW-Authenticate": "Basic"},
        )

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
