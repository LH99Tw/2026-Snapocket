"""In-memory + persistent idempotency key replay store."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Lock

from app.services.persistence import PersistenceStore


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class _CacheEntry:
    request_hash: str
    response_data: dict | list | None
    created_at: datetime


class IdempotencyConflictError(ValueError):
    pass


class IdempotencyStore:
    def __init__(
        self,
        *,
        ttl_s: int,
        persistence: PersistenceStore | None = None,
    ) -> None:
        self.ttl_s = ttl_s
        self.persistence = persistence
        self._lock = Lock()
        # Fast in-memory front cache; DB is authoritative fallback.
        self._cache: dict[str, _CacheEntry] = {}

    def get(
        self,
        *,
        route: str,
        key: str,
        request_hash: str,
    ) -> dict | list | None:
        storage_key = self._storage_key(route, key)
        self._evict_expired()

        with self._lock:
            entry = self._cache.get(storage_key)

        if entry is None and self.persistence is not None:
            # Process restart safe path.
            persisted = self.persistence.get_idempotency(
                route=route,
                idempotency_key=key,
                ttl_s=self.ttl_s,
            )
            if persisted is not None:
                entry = _CacheEntry(
                    request_hash=persisted.request_hash,
                    response_data=persisted.response_data,
                    created_at=persisted.created_at,
                )
                with self._lock:
                    self._cache[storage_key] = entry

        if entry is None:
            return None

        # Same key must represent exactly the same request fingerprint.
        if entry.request_hash != request_hash:
            raise IdempotencyConflictError("idempotency key reused with different payload")

        return entry.response_data

    def put(
        self,
        *,
        route: str,
        key: str,
        request_hash: str,
        response_data: dict | list | None,
    ) -> None:
        storage_key = self._storage_key(route, key)
        entry = _CacheEntry(
            request_hash=request_hash,
            response_data=response_data,
            created_at=_utcnow(),
        )

        with self._lock:
            self._cache[storage_key] = entry

        if self.persistence is not None:
            # Persist for replay after server restart.
            self.persistence.put_idempotency(
                route=route,
                idempotency_key=key,
                request_hash=request_hash,
                response_data=response_data,
            )

    def _evict_expired(self) -> None:
        threshold = _utcnow() - timedelta(seconds=self.ttl_s)
        with self._lock:
            stale = [key for key, item in self._cache.items() if item.created_at < threshold]
            for key in stale:
                self._cache.pop(key, None)

    @staticmethod
    def _storage_key(route: str, key: str) -> str:
        return f"{route}:{key}"
