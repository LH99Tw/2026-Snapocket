"""Request fingerprint helpers for idempotent API endpoints."""

from __future__ import annotations

import hashlib


def infer_request_hash(*, payload: bytes, filename: str, doc_id: str | None, engine_hint: str | None) -> str:
    # Fingerprint inputs that materially affect inference output.
    hasher = hashlib.sha256()
    hasher.update(payload)
    hasher.update(b"|")
    hasher.update((filename or "").encode("utf-8"))
    hasher.update(b"|")
    hasher.update((doc_id or "").encode("utf-8"))
    hasher.update(b"|")
    hasher.update((engine_hint or "").encode("utf-8"))
    return hasher.hexdigest()


def job_request_hash(*, payload: bytes, filename: str, doc_id: str | None, engine_hint: str | None) -> str:
    # Keep same fingerprinting semantics as /v1/infer.
    return infer_request_hash(
        payload=payload,
        filename=filename,
        doc_id=doc_id,
        engine_hint=engine_hint,
    )
