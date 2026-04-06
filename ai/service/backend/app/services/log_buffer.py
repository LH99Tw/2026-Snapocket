"""In-memory circular log buffer with Python logging handler integration."""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock


@dataclass
class LogEntry:
    timestamp: str
    level: str
    logger: str
    message: str


class LogBuffer:
    """Thread-safe circular buffer capturing Python log records."""

    def __init__(self, maxlen: int = 500) -> None:
        self._buf: deque[LogEntry] = deque(maxlen=maxlen)
        self._lock = Lock()

    def append(self, entry: LogEntry) -> None:
        with self._lock:
            self._buf.append(entry)

    def recent(self, n: int = 200) -> list[LogEntry]:
        with self._lock:
            entries = list(self._buf)
        return entries[-n:]

    def clear(self) -> None:
        with self._lock:
            self._buf.clear()


class _BufferHandler(logging.Handler):
    """Logging handler that writes records into a LogBuffer."""

    def __init__(self, buf: LogBuffer) -> None:
        super().__init__()
        self._buf = buf

    def emit(self, record: logging.LogRecord) -> None:
        try:
            ts = datetime.fromtimestamp(record.created, tz=timezone.utc).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            self._buf.append(
                LogEntry(
                    timestamp=ts,
                    level=record.levelname,
                    logger=record.name,
                    message=self.format(record),
                )
            )
        except Exception:
            pass


def attach_to_logger(buf: LogBuffer, logger_name: str = "app", level: int = logging.INFO) -> None:
    """Attach buffer handler to a named logger (and all its children)."""
    handler = _BufferHandler(buf)
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler.setLevel(level)
    logging.getLogger(logger_name).addHandler(handler)
