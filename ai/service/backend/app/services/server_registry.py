"""Persistent server registry for dispatching local/remote AI workloads."""

from __future__ import annotations

import ipaddress
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from app.schemas.server import (
    ServerCreateRequest,
    ServerHealthStatus,
    ServerKind,
    ServerRecord,
)
from app.services.persistence import PersistenceStore
from app.services.secret_cipher import SecretCipher

LOCAL_SERVER_ID = "local"
_ZROK_SUFFIXES = ("share.zrok.io", "shares.zrok.io")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_base_url(
    base_url: str,
    *,
    allow_public: bool,
    allow_hostname: bool,
    allow_zrok: bool,
) -> str:
    token = str(base_url or "").strip().rstrip("/")
    if not token:
        raise ValueError("base_url is empty")
    if token.startswith("http://") or token.startswith("https://"):
        parsed = urlparse(token)
    else:
        parsed = urlparse(f"http://{token}")

    if parsed.scheme not in {"http", "https"}:
        raise ValueError("base_url scheme must be http or https")
    if not parsed.hostname:
        raise ValueError("base_url host is missing")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("base_url must not include path/query/fragment")
    host = str(parsed.hostname).strip()
    port = parsed.port
    try:
        ip_obj = ipaddress.ip_address(host)
    except ValueError:
        host_lower = host.lower()
        is_zrok = any(host_lower == suffix or host_lower.endswith(f".{suffix}") for suffix in _ZROK_SUFFIXES)

        if is_zrok and allow_zrok:
            if parsed.scheme != "https":
                raise ValueError("zrok endpoint must use https")
            return f"https://{host}:{port or 443}"

        if not allow_hostname:
            raise ValueError("base_url host must be an IP address")
        return f"{parsed.scheme}://{host}:{port or (443 if parsed.scheme == 'https' else 80)}"

    if port is None:
        raise ValueError("base_url must include explicit port (e.g. :18080)")

    if ip_obj.is_unspecified or ip_obj.is_multicast:
        raise ValueError("base_url host is not routable")
    if ip_obj.is_reserved:
        raise ValueError("base_url host is reserved")
    if ip_obj.is_link_local:
        raise ValueError("base_url host must not be link-local")

    if not allow_public and ip_obj.is_global:
        raise ValueError("public IP endpoints are blocked by policy")
    return f"{parsed.scheme}://{ip_obj.compressed}:{port}"


class ServerRegistry:
    def __init__(
        self,
        *,
        persistence: PersistenceStore,
        cipher: SecretCipher,
        allow_public_endpoints: bool = False,
        allow_hostname_endpoints: bool = False,
        allow_zrok_endpoints: bool = True,
    ) -> None:
        self.persistence = persistence
        self.cipher = cipher
        self.allow_public_endpoints = bool(allow_public_endpoints)
        self.allow_hostname_endpoints = bool(allow_hostname_endpoints)
        self.allow_zrok_endpoints = bool(allow_zrok_endpoints)
        self.ensure_local_default()

    def ensure_local_default(self) -> None:
        rows = self.persistence.list_servers()
        if not rows:
            self.persistence.upsert_server(
                {
                    "server_id": LOCAL_SERVER_ID,
                    "name": "Local",
                    "kind": ServerKind.local.value,
                    "active": True,
                    "base_url_enc": "",
                    "api_key_enc": "",
                    "health_status": ServerHealthStatus.healthy.value,
                    "last_error": "",
                    "last_checked_at": _utcnow(),
                }
            )
            return

        if not any(str(row.get("server_id")) == LOCAL_SERVER_ID for row in rows):
            has_active = any(bool(row.get("active")) for row in rows)
            self.persistence.upsert_server(
                {
                    "server_id": LOCAL_SERVER_ID,
                    "name": "Local",
                    "kind": ServerKind.local.value,
                    "active": not has_active,
                    "base_url_enc": "",
                    "api_key_enc": "",
                    "health_status": ServerHealthStatus.healthy.value,
                    "last_error": "",
                    "last_checked_at": _utcnow(),
                }
            )

    def list_servers(self) -> list[ServerRecord]:
        rows = self.persistence.list_servers()
        servers = [self._row_to_record(row) for row in rows]
        servers.sort(key=lambda item: (0 if item.server_id == LOCAL_SERVER_ID else 1, item.name.lower()))
        if not any(server.active for server in servers):
            self.activate_server(LOCAL_SERVER_ID)
            return self.list_servers()
        return servers

    def get_server(self, server_id: str) -> ServerRecord:
        row = self.persistence.get_server(server_id)
        if not row:
            raise KeyError(server_id)
        return self._row_to_record(row)

    def get_active_server(self) -> ServerRecord:
        active = self.persistence.get_active_server()
        if active:
            return self._row_to_record(active)
        self.activate_server(LOCAL_SERVER_ID)
        row = self.persistence.get_active_server()
        if not row:
            raise RuntimeError("active server not available")
        return self._row_to_record(row)

    def create_remote_server(self, payload: ServerCreateRequest) -> ServerRecord:
        if not self.cipher.enabled:
            raise RuntimeError("AIOPS_SERVER_SECRET_KEY is required to add remote servers")

        base_url = _normalize_base_url(
            payload.base_url,
            allow_public=self.allow_public_endpoints,
            allow_hostname=self.allow_hostname_endpoints,
            allow_zrok=self.allow_zrok_endpoints,
        )
        api_key = str(payload.api_key or "").strip()
        if not api_key:
            raise ValueError("api_key is required")

        server_id = f"srv-{uuid4().hex[:12]}"
        has_active = self.persistence.get_active_server() is not None
        self.persistence.upsert_server(
            {
                "server_id": server_id,
                "name": str(payload.name).strip(),
                "kind": ServerKind.remote.value,
                "active": not has_active,
                "base_url_enc": self.cipher.encrypt_text(base_url),
                "api_key_enc": self.cipher.encrypt_text(api_key),
                "health_status": ServerHealthStatus.unknown.value,
                "last_error": "",
                "last_checked_at": None,
            }
        )
        return self.get_server(server_id)

    def activate_server(self, server_id: str) -> ServerRecord:
        row = self.persistence.get_server(server_id)
        if not row:
            raise KeyError(server_id)
        self.persistence.set_active_server(server_id)
        return self.get_server(server_id)

    def delete_server(self, server_id: str) -> None:
        if server_id == LOCAL_SERVER_ID:
            raise RuntimeError("local server cannot be removed")
        row = self.persistence.get_server(server_id)
        if not row:
            raise KeyError(server_id)
        was_active = bool(row.get("active"))
        self.persistence.delete_server(server_id)
        if was_active:
            self.activate_server(LOCAL_SERVER_ID)

    def mark_health(
        self,
        *,
        server_id: str,
        ok: bool,
        error_message: str = "",
    ) -> None:
        try:
            row = self.persistence.get_server(server_id)
            if not row:
                return
            self.persistence.upsert_server(
                {
                    "server_id": str(row.get("server_id")),
                    "name": str(row.get("name") or ""),
                    "kind": str(row.get("kind") or ServerKind.remote.value),
                    "active": bool(row.get("active")),
                    "base_url_enc": str(row.get("base_url_enc") or ""),
                    "api_key_enc": str(row.get("api_key_enc") or ""),
                    "health_status": (
                        ServerHealthStatus.healthy.value if ok else ServerHealthStatus.unreachable.value
                    ),
                    "last_error": "" if ok else str(error_message or "")[:500],
                    "last_checked_at": _utcnow(),
                }
            )
        except Exception:
            return

    def queue_summary_from_jobs(self, jobs: list[dict[str, Any]]) -> dict[str, int]:
        summary = {
            "queued": 0,
            "running": 0,
            "succeeded": 0,
            "failed": 0,
            "cancelled": 0,
            "total": 0,
        }
        for item in jobs:
            raw_status = item.get("status")
            if hasattr(raw_status, "value"):
                raw_status = getattr(raw_status, "value")
            status = str(raw_status or "").lower()
            if status in summary:
                summary[status] += 1
            summary["total"] += 1
        return summary

    def _row_to_record(self, row: dict[str, Any]) -> ServerRecord:
        kind = str(row.get("kind") or ServerKind.remote.value)
        base_url = ""
        api_key = ""
        base_url_enc = str(row.get("base_url_enc") or "")
        api_key_enc = str(row.get("api_key_enc") or "")
        if kind == ServerKind.remote.value:
            try:
                if base_url_enc:
                    base_url = self.cipher.decrypt_text(base_url_enc)
            except Exception:
                base_url = ""
            try:
                if api_key_enc:
                    api_key = self.cipher.decrypt_text(api_key_enc)
            except Exception:
                api_key = ""

        created_at = row.get("created_at")
        updated_at = row.get("updated_at")
        last_checked_at = row.get("last_checked_at")
        health_token = str(row.get("health_status") or ServerHealthStatus.unknown.value)
        try:
            health_status = ServerHealthStatus(health_token)
        except ValueError:
            health_status = ServerHealthStatus.unknown

        return ServerRecord(
            server_id=str(row.get("server_id") or ""),
            name=str(row.get("name") or ""),
            kind=ServerKind.local if kind == ServerKind.local.value else ServerKind.remote,
            active=bool(row.get("active")),
            base_url=base_url,
            has_api_key=bool(api_key),
            health_status=health_status,
            last_error=str(row.get("last_error") or ""),
            last_checked_at=last_checked_at if isinstance(last_checked_at, datetime) else None,
            created_at=created_at if isinstance(created_at, datetime) else None,
            updated_at=updated_at if isinstance(updated_at, datetime) else None,
        )

    def get_server_secrets(self, server_id: str) -> tuple[str, str]:
        row = self.persistence.get_server(server_id)
        if not row:
            raise KeyError(server_id)
        kind = str(row.get("kind") or "")
        if kind == ServerKind.local.value:
            return "", ""
        base_url_enc = str(row.get("base_url_enc") or "")
        api_key_enc = str(row.get("api_key_enc") or "")
        if not base_url_enc:
            raise RuntimeError("remote server base_url is missing")
        if not self.cipher.enabled:
            raise RuntimeError("AIOPS_SERVER_SECRET_KEY is not configured")
        base_url = self.cipher.decrypt_text(base_url_enc)
        api_key = self.cipher.decrypt_text(api_key_enc) if api_key_enc else ""
        return (
            _normalize_base_url(
                base_url,
                allow_public=self.allow_public_endpoints,
                allow_hostname=self.allow_hostname_endpoints,
                allow_zrok=self.allow_zrok_endpoints,
            ),
            api_key,
        )
