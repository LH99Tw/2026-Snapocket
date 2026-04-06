"""Per-engine non-blocking request gate for OCR inference endpoints."""

from __future__ import annotations

from threading import Lock


class EngineRequestGate:
    """Simple mutexes keyed by engine name (`paddle` / `glm`)."""

    def __init__(self) -> None:
        self._locks: dict[str, Lock] = {
            "paddle": Lock(),
            "glm": Lock(),
        }

    def try_acquire(self, engine: str) -> bool:
        key = str(engine or "").strip().lower()
        lock = self._locks.get(key)
        if lock is None:
            # Unknown engine should not be blocked here.
            return True
        return lock.acquire(blocking=False)

    def release(self, engine: str) -> None:
        key = str(engine or "").strip().lower()
        lock = self._locks.get(key)
        if lock is None:
            return
        if lock.locked():
            lock.release()
