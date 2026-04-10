"""JSON logging setup used by API and background services."""

import json
import logging
import os
import re
import sys
from datetime import datetime, timezone


_EMAIL_RE = re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE_RE = re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?(?:\d{2,3}[-.\s]?)\d{3,4}[-.\s]?\d{4}\b")
_APIKEY_RE = re.compile(r"(?i)(api[_-]?key\s*[=:]\s*)([A-Za-z0-9._\-]{8,})")
_BEARER_RE = re.compile(r"(?i)(bearer\s+)([A-Za-z0-9._\-]{8,})")


def _mask_pii(text: str) -> str:
    masked = _EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    masked = _PHONE_RE.sub("[REDACTED_PHONE]", masked)
    masked = _APIKEY_RE.sub(r"\1[REDACTED_KEY]", masked)
    masked = _BEARER_RE.sub(r"\1[REDACTED_TOKEN]", masked)
    return masked


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": _mask_pii(record.getMessage()),
        }
        if hasattr(record, "request_id"):
            payload["request_id"] = record.request_id
        if record.exc_info:
            payload["exc_info"] = _mask_pii(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> None:
    root = logging.getLogger()
    root.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.handlers.clear()
    root.addHandler(handler)
