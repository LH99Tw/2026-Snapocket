"""SQL persistence adapter for models/jobs/results/audit/idempotency records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    delete,
    insert,
    select,
    text,
    update,
)
from sqlalchemy.engine import Engine

from app.schemas.job import JobInfo
from app.schemas.model import ModelInfo


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class IdempotencyRecord:
    key: str
    route: str
    request_hash: str
    response_data: dict | list | None
    created_at: datetime


class PersistenceStore:
    """Lightweight SQL persistence for control-plane entities.

    Designed for Postgres in production (`DATABASE_URL`) and sqlite fallback in local/dev.
    """

    def __init__(self, database_url: str, enabled: bool = True) -> None:
        self.database_url = database_url
        self.enabled = enabled and bool(database_url)
        self._engine: Engine | None = None
        self._last_error: str | None = None

        self.metadata = MetaData()
        self.models_table = Table(
            "models",
            self.metadata,
            Column("model_id", String(255), primary_key=True),
            Column("name", String(255), nullable=False),
            Column("engine", String(64), nullable=False),
            Column("version", String(128), nullable=False),
            Column("active", Boolean, nullable=False, default=False),
            Column("status", String(64), nullable=False, default="ready"),
            Column("updated_at", DateTime(timezone=True), nullable=False, default=_utcnow),
        )

        self.jobs_table = Table(
            "jobs",
            self.metadata,
            Column("job_id", String(64), primary_key=True),
            Column("status", String(32), nullable=False),
            Column("created_at", DateTime(timezone=True), nullable=False),
            Column("updated_at", DateTime(timezone=True), nullable=False),
            Column("error", String(1024), nullable=True),
            Column("attempt", Integer, nullable=False, default=0),
            Column("max_retries", Integer, nullable=False, default=0),
            Column("timeout_s", Float, nullable=True),
            Column("request_meta", JSON, nullable=True),
            Column("result_data", JSON, nullable=True),
        )

        self.results_table = Table(
            "results",
            self.metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("job_id", String(64), nullable=True),
            Column("doc_id", String(128), nullable=False),
            Column("filename", String(512), nullable=False),
            Column("content_type", String(128), nullable=False),
            Column("engine_used", String(64), nullable=False),
            Column("confidence", Float, nullable=False, default=0.0),
            Column("latency_ms", Integer, nullable=False, default=0),
            Column("payload", JSON, nullable=False),
            Column("created_at", DateTime(timezone=True), nullable=False, default=_utcnow),
        )

        self.audit_logs_table = Table(
            "audit_logs",
            self.metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("action", String(128), nullable=False),
            Column("target_type", String(64), nullable=False),
            Column("target_id", String(255), nullable=False),
            Column("detail", JSON, nullable=True),
            Column("created_at", DateTime(timezone=True), nullable=False, default=_utcnow),
        )

        self.idempotency_table = Table(
            "idempotency_keys",
            self.metadata,
            Column("idempotency_key", String(255), primary_key=True),
            Column("route", String(255), nullable=False),
            Column("request_hash", String(128), nullable=False),
            Column("response_data", JSON, nullable=True),
            Column("created_at", DateTime(timezone=True), nullable=False, default=_utcnow),
            Column("updated_at", DateTime(timezone=True), nullable=False, default=_utcnow),
        )

        self.servers_table = Table(
            "servers",
            self.metadata,
            Column("server_id", String(64), primary_key=True),
            Column("name", String(80), nullable=False),
            Column("kind", String(16), nullable=False, default="remote"),
            Column("active", Boolean, nullable=False, default=False),
            Column("base_url_enc", String(2048), nullable=True),
            Column("api_key_enc", String(4096), nullable=True),
            Column("health_status", String(32), nullable=False, default="unknown"),
            Column("last_error", String(512), nullable=True),
            Column("last_checked_at", DateTime(timezone=True), nullable=True),
            Column("created_at", DateTime(timezone=True), nullable=False, default=_utcnow),
            Column("updated_at", DateTime(timezone=True), nullable=False, default=_utcnow),
        )

    def start(self) -> None:
        if not self.enabled:
            return

        connect_args: dict[str, Any] = {}
        if self.database_url.startswith("sqlite:///"):
            # sqlite file path bootstrap for local execution.
            db_path = self.database_url.replace("sqlite:///", "", 1)
            if db_path and db_path != ":memory:":
                Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            connect_args["check_same_thread"] = False

        try:
            self._engine = create_engine(
                self.database_url,
                future=True,
                pool_pre_ping=True,
                connect_args=connect_args,
            )
            self.metadata.create_all(self._engine)
            self._last_error = None
        except Exception as exc:  # pragma: no cover - env-dependent
            # Best-effort startup: keep API booting even if DB is down.
            # Readiness endpoint will expose this failure.
            self._last_error = str(exc)
            self._engine = None

    def shutdown(self) -> None:
        if self._engine is not None:
            self._engine.dispose()

    def health(self, timeout_s: float = 1.5) -> dict[str, Any]:
        if not self.enabled:
            return {"configured": False, "ok": True, "error": None}
        if self._engine is None:
            return {"configured": True, "ok": False, "error": self._last_error or "engine not initialized"}

        try:
            with self._engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            self._last_error = None
            return {"configured": True, "ok": True, "error": None}
        except Exception as exc:
            self._last_error = str(exc)
            return {"configured": True, "ok": False, "error": self._last_error}

    def upsert_model(self, model: ModelInfo) -> None:
        if self._engine is None:
            return

        # Keep an always-fresh mirror of in-memory registry state.
        now = _utcnow()
        values = {
            "model_id": model.model_id,
            "name": model.name,
            "engine": model.engine,
            "version": model.version,
            "active": model.active,
            "status": model.status,
            "updated_at": now,
        }

        try:
            with self._engine.begin() as conn:
                row = conn.execute(
                    select(self.models_table.c.model_id).where(
                        self.models_table.c.model_id == model.model_id
                    )
                ).first()
                if row:
                    conn.execute(
                        update(self.models_table)
                        .where(self.models_table.c.model_id == model.model_id)
                        .values(**values)
                    )
                else:
                    conn.execute(insert(self.models_table).values(**values))
            self._last_error = None
        except Exception as exc:  # pragma: no cover - env-dependent
            self._last_error = str(exc)

    def sync_models(self, models: list[ModelInfo]) -> None:
        if self._engine is None:
            return
        for model in models:
            self.upsert_model(model)

    def list_models(self) -> list[dict[str, Any]]:
        """Return model rows persisted in DB (best effort)."""
        if self._engine is None:
            return []
        try:
            with self._engine.connect() as conn:
                rows = conn.execute(
                    select(
                        self.models_table.c.model_id,
                        self.models_table.c.name,
                        self.models_table.c.engine,
                        self.models_table.c.version,
                        self.models_table.c.active,
                        self.models_table.c.status,
                        self.models_table.c.updated_at,
                    ).order_by(self.models_table.c.model_id.asc())
                ).all()
            out: list[dict[str, Any]] = []
            for row in rows:
                out.append(
                    {
                        "model_id": str(row.model_id),
                        "name": str(row.name),
                        "engine": str(row.engine),
                        "version": str(row.version),
                        "active": bool(row.active),
                        "status": str(row.status),
                        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                    }
                )
            return out
        except Exception as exc:  # pragma: no cover - env-dependent
            self._last_error = str(exc)
            return []

    def upsert_job(
        self,
        info: JobInfo,
        *,
        request_meta: dict[str, Any] | None = None,
        result_data: dict[str, Any] | list | None = None,
    ) -> None:
        if self._engine is None:
            return

        # `jobs` table keeps lifecycle metadata; large OCR payloads are stored separately.
        values = {
            "job_id": info.job_id,
            "status": str(info.status),
            "created_at": info.created_at,
            "updated_at": info.updated_at,
            "error": info.error,
            "attempt": int(getattr(info, "attempt", 0)),
            "max_retries": int(getattr(info, "max_retries", 0)),
            "timeout_s": float(getattr(info, "timeout_s", 0.0) or 0.0),
            "request_meta": request_meta,
            "result_data": result_data,
        }

        try:
            with self._engine.begin() as conn:
                row = conn.execute(
                    select(self.jobs_table.c.job_id).where(self.jobs_table.c.job_id == info.job_id)
                ).first()
                if row:
                    conn.execute(
                        update(self.jobs_table)
                        .where(self.jobs_table.c.job_id == info.job_id)
                        .values(**values)
                    )
                else:
                    conn.execute(insert(self.jobs_table).values(**values))
            self._last_error = None
        except Exception as exc:  # pragma: no cover - env-dependent
            self._last_error = str(exc)

    def insert_result(self, *, job_id: str | None, result_data: dict[str, Any]) -> None:
        if self._engine is None:
            return

        # Persist the full transformed document payload for re-query/replay.
        try:
            with self._engine.begin() as conn:
                conn.execute(
                    insert(self.results_table).values(
                        job_id=job_id,
                        doc_id=str(result_data.get("doc_id", "")),
                        filename=str(result_data.get("filename", "")),
                        content_type=str(result_data.get("content_type", "")),
                        engine_used=str(result_data.get("engine_used", "")),
                        confidence=float(result_data.get("confidence", 0.0) or 0.0),
                        latency_ms=int(result_data.get("latency_ms", 0) or 0),
                        payload=result_data,
                        created_at=_utcnow(),
                    )
                )
            self._last_error = None
        except Exception as exc:  # pragma: no cover - env-dependent
            self._last_error = str(exc)

    def insert_audit(self, *, action: str, target_type: str, target_id: str, detail: dict | None = None) -> None:
        if self._engine is None:
            return
        # Audit is append-only by design.
        try:
            with self._engine.begin() as conn:
                conn.execute(
                    insert(self.audit_logs_table).values(
                        action=action,
                        target_type=target_type,
                        target_id=target_id,
                        detail=detail,
                        created_at=_utcnow(),
                    )
                )
            self._last_error = None
        except Exception as exc:  # pragma: no cover - env-dependent
            self._last_error = str(exc)

    def get_idempotency(
        self,
        *,
        route: str,
        idempotency_key: str,
        ttl_s: int,
    ) -> IdempotencyRecord | None:
        if self._engine is None:
            return None

        # Route is part of key namespace so same client key can be reused across endpoints.
        storage_key = self._idempotency_storage_key(route, idempotency_key)
        try:
            with self._engine.begin() as conn:
                row = conn.execute(
                    select(
                        self.idempotency_table.c.idempotency_key,
                        self.idempotency_table.c.route,
                        self.idempotency_table.c.request_hash,
                        self.idempotency_table.c.response_data,
                        self.idempotency_table.c.created_at,
                    ).where(self.idempotency_table.c.idempotency_key == storage_key)
                ).first()

                if not row:
                    return None

                created_at = row.created_at
                if isinstance(created_at, datetime):
                    if created_at.tzinfo is None:
                        created_at = created_at.replace(tzinfo=timezone.utc)
                    # Hard TTL eviction to avoid unbounded idempotency storage.
                    if created_at < (_utcnow() - timedelta(seconds=ttl_s)):
                        conn.execute(
                            delete(self.idempotency_table).where(
                                self.idempotency_table.c.idempotency_key == storage_key
                            )
                        )
                        return None

                return IdempotencyRecord(
                    key=idempotency_key,
                    route=row.route,
                    request_hash=row.request_hash,
                    response_data=row.response_data,
                    created_at=created_at,
                )
        except Exception as exc:  # pragma: no cover - env-dependent
            self._last_error = str(exc)
            return None

    def put_idempotency(
        self,
        *,
        route: str,
        idempotency_key: str,
        request_hash: str,
        response_data: dict | list | None,
    ) -> None:
        if self._engine is None:
            return

        storage_key = self._idempotency_storage_key(route, idempotency_key)
        now = _utcnow()
        values = {
            "idempotency_key": storage_key,
            "route": route,
            "request_hash": request_hash,
            "response_data": response_data,
            "created_at": now,
            "updated_at": now,
        }

        try:
            with self._engine.begin() as conn:
                row = conn.execute(
                    select(self.idempotency_table.c.idempotency_key).where(
                        self.idempotency_table.c.idempotency_key == storage_key
                    )
                ).first()
                if row:
                    conn.execute(
                        update(self.idempotency_table)
                        .where(self.idempotency_table.c.idempotency_key == storage_key)
                        .values(**values)
                    )
                else:
                    conn.execute(insert(self.idempotency_table).values(**values))
            self._last_error = None
        except Exception as exc:  # pragma: no cover - env-dependent
            self._last_error = str(exc)

    @staticmethod
    def _idempotency_storage_key(route: str, idempotency_key: str) -> str:
        return f"{route}:{idempotency_key}"

    def list_servers(self) -> list[dict[str, Any]]:
        if self._engine is None:
            return []
        try:
            with self._engine.connect() as conn:
                rows = conn.execute(
                    select(
                        self.servers_table.c.server_id,
                        self.servers_table.c.name,
                        self.servers_table.c.kind,
                        self.servers_table.c.active,
                        self.servers_table.c.base_url_enc,
                        self.servers_table.c.api_key_enc,
                        self.servers_table.c.health_status,
                        self.servers_table.c.last_error,
                        self.servers_table.c.last_checked_at,
                        self.servers_table.c.created_at,
                        self.servers_table.c.updated_at,
                    ).order_by(self.servers_table.c.created_at.asc())
                ).all()
            return [dict(row._mapping) for row in rows]
        except Exception as exc:  # pragma: no cover - env-dependent
            self._last_error = str(exc)
            return []

    def get_server(self, server_id: str) -> dict[str, Any] | None:
        if self._engine is None:
            return None
        try:
            with self._engine.connect() as conn:
                row = conn.execute(
                    select(
                        self.servers_table.c.server_id,
                        self.servers_table.c.name,
                        self.servers_table.c.kind,
                        self.servers_table.c.active,
                        self.servers_table.c.base_url_enc,
                        self.servers_table.c.api_key_enc,
                        self.servers_table.c.health_status,
                        self.servers_table.c.last_error,
                        self.servers_table.c.last_checked_at,
                        self.servers_table.c.created_at,
                        self.servers_table.c.updated_at,
                    ).where(self.servers_table.c.server_id == server_id)
                ).first()
            if not row:
                return None
            return dict(row._mapping)
        except Exception as exc:  # pragma: no cover - env-dependent
            self._last_error = str(exc)
            return None

    def get_active_server(self) -> dict[str, Any] | None:
        if self._engine is None:
            return None
        try:
            with self._engine.connect() as conn:
                row = conn.execute(
                    select(
                        self.servers_table.c.server_id,
                        self.servers_table.c.name,
                        self.servers_table.c.kind,
                        self.servers_table.c.active,
                        self.servers_table.c.base_url_enc,
                        self.servers_table.c.api_key_enc,
                        self.servers_table.c.health_status,
                        self.servers_table.c.last_error,
                        self.servers_table.c.last_checked_at,
                        self.servers_table.c.created_at,
                        self.servers_table.c.updated_at,
                    ).where(self.servers_table.c.active.is_(True))
                ).first()
            if not row:
                return None
            return dict(row._mapping)
        except Exception as exc:  # pragma: no cover - env-dependent
            self._last_error = str(exc)
            return None

    def upsert_server(self, values: dict[str, Any]) -> None:
        if self._engine is None:
            return
        now = _utcnow()
        row_values = {
            "server_id": str(values.get("server_id") or "").strip(),
            "name": str(values.get("name") or "").strip(),
            "kind": str(values.get("kind") or "remote").strip(),
            "active": bool(values.get("active")),
            "base_url_enc": str(values.get("base_url_enc") or ""),
            "api_key_enc": str(values.get("api_key_enc") or ""),
            "health_status": str(values.get("health_status") or "unknown"),
            "last_error": str(values.get("last_error") or ""),
            "last_checked_at": values.get("last_checked_at"),
            "updated_at": now,
        }
        if not row_values["server_id"]:
            return
        try:
            with self._engine.begin() as conn:
                existing = conn.execute(
                    select(self.servers_table.c.server_id, self.servers_table.c.created_at).where(
                        self.servers_table.c.server_id == row_values["server_id"]
                    )
                ).first()
                if existing:
                    conn.execute(
                        update(self.servers_table)
                        .where(self.servers_table.c.server_id == row_values["server_id"])
                        .values(**row_values)
                    )
                else:
                    row_values["created_at"] = now
                    conn.execute(insert(self.servers_table).values(**row_values))
            self._last_error = None
        except Exception as exc:  # pragma: no cover - env-dependent
            self._last_error = str(exc)

    def set_active_server(self, server_id: str) -> None:
        if self._engine is None:
            return
        try:
            with self._engine.begin() as conn:
                conn.execute(update(self.servers_table).values(active=False, updated_at=_utcnow()))
                conn.execute(
                    update(self.servers_table)
                    .where(self.servers_table.c.server_id == server_id)
                    .values(active=True, updated_at=_utcnow())
                )
            self._last_error = None
        except Exception as exc:  # pragma: no cover - env-dependent
            self._last_error = str(exc)

    def delete_server(self, server_id: str) -> None:
        if self._engine is None:
            return
        try:
            with self._engine.begin() as conn:
                conn.execute(delete(self.servers_table).where(self.servers_table.c.server_id == server_id))
            self._last_error = None
        except Exception as exc:  # pragma: no cover - env-dependent
            self._last_error = str(exc)
