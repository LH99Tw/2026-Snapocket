"""Upload validation helpers (size/type checks for file endpoints)."""

from __future__ import annotations

from pathlib import Path

from fastapi import UploadFile, status

from app.api.errors import api_error
from app.services.file_types import resolve_content_type
from app.services.state import AppState


def validate_upload(state: AppState, file: UploadFile, payload: bytes) -> None:
    max_bytes = state.settings.max_upload_mb * 1024 * 1024
    if len(payload) > max_bytes:
        raise api_error(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "PAYLOAD_TOO_LARGE", "File too large")

    filename = file.filename or ""
    ext = Path(filename).suffix.lower()
    content_type = resolve_content_type(filename, file.content_type, payload)

    if ext and ext not in state.settings.allowed_upload_exts:
        raise api_error(status.HTTP_400_BAD_REQUEST, "UNSUPPORTED_FORMAT", f"Unsupported extension: {ext}")

    # Some clients do not send content-type for form uploads.
    if content_type and content_type not in state.settings.allowed_upload_types:
        raise api_error(
            status.HTTP_400_BAD_REQUEST,
            "UNSUPPORTED_MIMETYPE",
            f"Unsupported content type: {content_type}",
        )

    # Optional malware scanning hook (signature and/or external scanner command).
    scan = state.scanner.scan(filename=filename or "upload.bin", payload=payload)
    if not scan.safe:
        code = scan.code or "MALWARE_SCAN_FAILED"
        message = scan.message or "Malware scan failed"
        status_code = (
            status.HTTP_422_UNPROCESSABLE_ENTITY
            if code == "MALWARE_DETECTED"
            else status.HTTP_503_SERVICE_UNAVAILABLE
        )
        raise api_error(status_code, code, message)


def guess_content_type(filename: str, given_type: str | None) -> str:
    return resolve_content_type(filename, given_type, payload=None)
