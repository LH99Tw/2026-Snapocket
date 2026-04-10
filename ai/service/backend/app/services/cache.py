"""SHA-256 file hash-based TTL result cache."""

from __future__ import annotations

import copy
import hashlib
from typing import Any

from cachetools import TTLCache


class ResultCache:
    """SHA-256 파일 해시 기반 TTL 캐시. Redis 교체 가능 인터페이스."""

    def __init__(self, maxsize: int = 500, ttl: int = 3600) -> None:
        self._cache: TTLCache = TTLCache(maxsize=maxsize, ttl=ttl)

    @staticmethod
    def _key(file_bytes: bytes, scope: str = "") -> str:
        scope_bytes = scope.encode("utf-8")
        return hashlib.sha256(scope_bytes + b"\0" + file_bytes).hexdigest()

    def get(self, file_bytes: bytes, *, scope: str = "") -> dict[str, Any] | None:
        result = self._cache.get(self._key(file_bytes, scope=scope))
        if result is None:
            return None
        return copy.deepcopy(result)

    def set(self, file_bytes: bytes, result: dict[str, Any], *, scope: str = "") -> None:
        self._cache[self._key(file_bytes, scope=scope)] = copy.deepcopy(result)

    @property
    def size(self) -> int:
        return len(self._cache)
