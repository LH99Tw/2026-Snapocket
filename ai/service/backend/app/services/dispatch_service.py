"""Dispatch local or remote execution based on active server selection."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4
from urllib import error as urlerror
from urllib import request as urlrequest

from app.schemas.job import JobInfo
from app.schemas.server import ServerKind, ServerRecord
from app.services.server_registry import ServerRegistry


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class DispatchRequestError(RuntimeError):
    status_code: int
    code: str
    message: str


class DispatchService:
    def __init__(
        self,
        *,
        server_registry: ServerRegistry,
        pipeline,
        job_manager,
        settings,
        router,
        request_timeout_s: float = 120.0,
    ) -> None:
        self.server_registry = server_registry
        self.pipeline = pipeline
        self.job_manager = job_manager
        self.settings = settings
        self.router = router
        self.request_timeout_s = max(5.0, float(request_timeout_s))

    def active_server(self) -> ServerRecord:
        return self.server_registry.get_active_server()

    def active_backend_label(self) -> str:
        active = self.active_server()
        if active.kind == ServerKind.local:
            return "local aiops-api"
        return f"remote aiops-api @ {active.base_url or active.name}"

    def local_runtime(self) -> dict[str, bool]:
        return {
            "paddle": bool(self.router.paddle_engine.available()),
            "glm": bool(self.router.glm_engine.available()),
        }

    async def infer(
        self,
        *,
        filename: str,
        file_bytes: bytes,
        content_type: str,
        engine_hint: str,
        doc_id: str | None,
        vlm_ocr_verify: bool = False,
    ) -> dict:
        active = self.active_server()
        if active.kind == ServerKind.local:
            result = await self.pipeline.process_async(
                filename=filename,
                file_bytes=file_bytes,
                content_type=content_type,
                engine_hint=engine_hint,
                doc_id=doc_id,
                vlm_ocr_verify=vlm_ocr_verify,
            )
            return result.model_dump() if hasattr(result, "model_dump") else dict(result)

        return await asyncio.to_thread(
            self._infer_remote_sync,
            server_id=active.server_id,
            filename=filename,
            content_type=content_type,
            file_bytes=file_bytes,
            engine_hint=engine_hint,
            doc_id=doc_id,
        )

    async def infer_batch(
        self,
        *,
        files: list[tuple[str, str | None, bytes]],
        engine_hint: str,
    ) -> dict:
        active = self.active_server()
        if active.kind == ServerKind.local:
            raise DispatchRequestError(
                status_code=400,
                code="LOCAL_ONLY",
                message="local batch path should be handled directly",
            )
        return await asyncio.to_thread(
            self._infer_batch_remote_sync,
            server_id=active.server_id,
            files=files,
            engine_hint=engine_hint,
        )

    def create_job(
        self,
        *,
        filename: str,
        file_bytes: bytes,
        content_type: str | None,
        engine_hint: str,
        doc_id: str | None,
    ) -> str:
        active = self.active_server()
        if active.kind == ServerKind.local:
            return self.job_manager.submit(
                self.pipeline.process,
                filename=filename,
                file_bytes=file_bytes,
                content_type=content_type,
                engine_hint=engine_hint,
                doc_id=doc_id,
                job_meta={
                    "filename": filename,
                    "content_type": content_type,
                    "engine_hint": engine_hint,
                    "doc_id": doc_id,
                },
            )

        return self._create_job_remote_sync(
            server_id=active.server_id,
            filename=filename,
            content_type=content_type,
            file_bytes=file_bytes,
            engine_hint=engine_hint,
            doc_id=doc_id,
        )

    def list_jobs(self) -> list[dict]:
        active = self.active_server()
        if active.kind == ServerKind.local:
            return [job.model_dump(mode="json") for job in self.job_manager.list_jobs()]
        return self._list_jobs_remote_sync(server_id=active.server_id)

    def get_job(self, *, job_id: str) -> dict:
        active = self.active_server()
        if active.kind == ServerKind.local:
            info: JobInfo = self.job_manager.get_info(job_id)
            return info.model_dump(mode="json")
        return self._get_job_remote_sync(server_id=active.server_id, job_id=job_id)

    def get_job_result(self, *, job_id: str) -> dict:
        active = self.active_server()
        if active.kind == ServerKind.local:
            info = self.job_manager.get_info(job_id)
            result = self.job_manager.get_result(job_id)
            dumped = result.model_dump() if hasattr(result, "model_dump") else result
            status_value = getattr(info.status, "value", info.status)
            return {"status": status_value, "result": dumped, "error": info.error}
        return self._get_job_result_remote_sync(server_id=active.server_id, job_id=job_id)

    def cancel_job(self, *, job_id: str) -> bool:
        active = self.active_server()
        if active.kind == ServerKind.local:
            return bool(self.job_manager.cancel(job_id))
        payload = self._cancel_job_remote_sync(server_id=active.server_id, job_id=job_id)
        return bool(payload.get("cancelled"))

    def retry_job(self, *, job_id: str) -> str:
        active = self.active_server()
        if active.kind == ServerKind.local:
            return str(self.job_manager.retry(job_id))
        payload = self._retry_job_remote_sync(server_id=active.server_id, job_id=job_id)
        return str(payload.get("retry_job_id") or "")

    def health_check_server(self, *, server_id: str) -> dict[str, object]:
        server = self.server_registry.get_server(server_id)
        if server.kind == ServerKind.local:
            runtime = self.local_runtime()
            ok = bool(runtime.get("paddle") or runtime.get("glm"))
            message = "" if ok else "no runtime is currently available"
            self.server_registry.mark_health(server_id=server_id, ok=ok, error_message=message)
            return {"ok": ok, "runtime": runtime, "checked_at": _utcnow().isoformat(), "message": message}

        try:
            base_url, api_key = self.server_registry.get_server_secrets(server_id)
            payload = self._request_json(
                method="GET",
                url=f"{base_url}/health/ready",
                headers=self._auth_headers(api_key),
                timeout_s=min(8.0, self.request_timeout_s),
            )
            ok = bool(payload.get("ok")) if isinstance(payload, dict) else False
            message = "" if ok else str(payload)[:500]
            self.server_registry.mark_health(server_id=server_id, ok=ok, error_message=message)
            return {"ok": ok, "runtime": payload.get("runtime", {}), "checked_at": _utcnow().isoformat(), "message": message}
        except DispatchRequestError as exc:
            self.server_registry.mark_health(server_id=server_id, ok=False, error_message=exc.message)
            return {"ok": False, "runtime": {}, "checked_at": _utcnow().isoformat(), "message": exc.message}

    def active_queue_summary(self) -> dict[str, int]:
        active = self.active_server()
        if active.kind == ServerKind.local:
            jobs = [job.model_dump(mode="json") for job in self.job_manager.list_jobs()]
            return self.server_registry.queue_summary_from_jobs(jobs)
        try:
            jobs = self._list_jobs_remote_sync(server_id=active.server_id)
            return self.server_registry.queue_summary_from_jobs(jobs)
        except DispatchRequestError as exc:
            self.server_registry.mark_health(server_id=active.server_id, ok=False, error_message=exc.message)
            return {"queued": 0, "running": 0, "succeeded": 0, "failed": 0, "cancelled": 0, "total": 0}

    def active_runtime(self) -> dict[str, bool]:
        active = self.active_server()
        if active.kind == ServerKind.local:
            return self.local_runtime()
        try:
            base_url, api_key = self.server_registry.get_server_secrets(active.server_id)
            payload = self._request_json(
                method="GET",
                url=f"{base_url}/health/ready",
                headers=self._auth_headers(api_key),
                timeout_s=min(8.0, self.request_timeout_s),
            )
            runtime = payload.get("runtime", {}) if isinstance(payload, dict) else {}
            self.server_registry.mark_health(server_id=active.server_id, ok=bool(payload.get("ok", False)))
            return {
                "paddle": bool(runtime.get("paddle")),
                "glm": bool(runtime.get("glm")),
            }
        except DispatchRequestError as exc:
            self.server_registry.mark_health(server_id=active.server_id, ok=False, error_message=exc.message)
            return {"paddle": False, "glm": False}

    def _infer_remote_sync(
        self,
        *,
        server_id: str,
        filename: str,
        content_type: str,
        file_bytes: bytes,
        engine_hint: str,
        doc_id: str | None,
    ) -> dict:
        base_url, api_key = self.server_registry.get_server_secrets(server_id)
        fields = [("engine_hint", engine_hint)]
        if doc_id:
            fields.append(("doc_id", doc_id))
        content_type_value, body = self._encode_multipart(
            fields=fields,
            files=[("file", filename, content_type or "application/octet-stream", file_bytes)],
        )
        try:
            payload = self._request_json(
                method="POST",
                url=f"{base_url}/v1/infer",
                headers={"Content-Type": content_type_value, **self._auth_headers(api_key)},
                body=body,
                timeout_s=self.request_timeout_s,
            )
        except DispatchRequestError as exc:
            self.server_registry.mark_health(server_id=server_id, ok=False, error_message=exc.message)
            raise
        data = self._unwrap_api_envelope(payload, fallback_code="INFER_FAILED")
        self.server_registry.mark_health(server_id=server_id, ok=True)
        return data if isinstance(data, dict) else {}

    def _infer_batch_remote_sync(
        self,
        *,
        server_id: str,
        files: list[tuple[str, str | None, bytes]],
        engine_hint: str,
    ) -> dict:
        base_url, api_key = self.server_registry.get_server_secrets(server_id)
        multipart_files: list[tuple[str, str, str, bytes]] = []
        for filename, content_type, file_bytes in files:
            multipart_files.append(("files", filename, content_type or "application/octet-stream", file_bytes))
        content_type_value, body = self._encode_multipart(
            fields=[("engine_hint", engine_hint)],
            files=multipart_files,
        )
        try:
            payload = self._request_json(
                method="POST",
                url=f"{base_url}/v1/infer/batch",
                headers={"Content-Type": content_type_value, **self._auth_headers(api_key)},
                body=body,
                timeout_s=self.request_timeout_s,
            )
        except DispatchRequestError as exc:
            self.server_registry.mark_health(server_id=server_id, ok=False, error_message=exc.message)
            raise
        data = self._unwrap_api_envelope(payload, fallback_code="INFER_FAILED")
        self.server_registry.mark_health(server_id=server_id, ok=True)
        return data if isinstance(data, dict) else {}

    def _create_job_remote_sync(
        self,
        *,
        server_id: str,
        filename: str,
        content_type: str | None,
        file_bytes: bytes,
        engine_hint: str,
        doc_id: str | None,
    ) -> str:
        base_url, api_key = self.server_registry.get_server_secrets(server_id)
        fields = [("engine_hint", engine_hint)]
        if doc_id:
            fields.append(("doc_id", doc_id))
        content_type_value, body = self._encode_multipart(
            fields=fields,
            files=[("file", filename, content_type or "application/octet-stream", file_bytes)],
        )
        try:
            payload = self._request_json(
                method="POST",
                url=f"{base_url}/v1/jobs",
                headers={"Content-Type": content_type_value, **self._auth_headers(api_key)},
                body=body,
                timeout_s=self.request_timeout_s,
            )
        except DispatchRequestError as exc:
            self.server_registry.mark_health(server_id=server_id, ok=False, error_message=exc.message)
            raise
        data = self._unwrap_api_envelope(payload, fallback_code="JOB_CREATE_FAILED")
        self.server_registry.mark_health(server_id=server_id, ok=True)
        job_id = str((data or {}).get("job_id") or "")
        if not job_id:
            raise DispatchRequestError(
                status_code=502,
                code="JOB_CREATE_FAILED",
                message="upstream response missing job_id",
            )
        return job_id

    def _list_jobs_remote_sync(self, *, server_id: str) -> list[dict]:
        payload = self._remote_request(server_id=server_id, method="GET", path="/v1/jobs")
        data = self._unwrap_api_envelope(payload, fallback_code="JOB_LIST_FAILED")
        return list(data) if isinstance(data, list) else []

    def _get_job_remote_sync(self, *, server_id: str, job_id: str) -> dict:
        payload = self._remote_request(server_id=server_id, method="GET", path=f"/v1/jobs/{job_id}")
        data = self._unwrap_api_envelope(payload, fallback_code="JOB_FETCH_FAILED")
        return dict(data) if isinstance(data, dict) else {}

    def _get_job_result_remote_sync(self, *, server_id: str, job_id: str) -> dict:
        payload = self._remote_request(server_id=server_id, method="GET", path=f"/v1/jobs/{job_id}/result")
        data = self._unwrap_api_envelope(payload, fallback_code="JOB_RESULT_FAILED")
        return dict(data) if isinstance(data, dict) else {}

    def _cancel_job_remote_sync(self, *, server_id: str, job_id: str) -> dict:
        payload = self._remote_request(server_id=server_id, method="POST", path=f"/v1/jobs/{job_id}/cancel")
        data = self._unwrap_api_envelope(payload, fallback_code="JOB_CANCEL_FAILED")
        return dict(data) if isinstance(data, dict) else {}

    def _retry_job_remote_sync(self, *, server_id: str, job_id: str) -> dict:
        payload = self._remote_request(server_id=server_id, method="POST", path=f"/v1/jobs/{job_id}/retry")
        data = self._unwrap_api_envelope(payload, fallback_code="JOB_RETRY_FAILED")
        return dict(data) if isinstance(data, dict) else {}

    def _remote_request(
        self,
        *,
        server_id: str,
        method: str,
        path: str,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict:
        base_url, api_key = self.server_registry.get_server_secrets(server_id)
        merged_headers = dict(headers or {})
        merged_headers.update(self._auth_headers(api_key))
        try:
            payload = self._request_json(
                method=method,
                url=f"{base_url}{path}",
                headers=merged_headers,
                body=body,
                timeout_s=self.request_timeout_s,
            )
        except DispatchRequestError as exc:
            self.server_registry.mark_health(server_id=server_id, ok=False, error_message=exc.message)
            raise
        self.server_registry.mark_health(server_id=server_id, ok=True)
        return payload

    def _request_json(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        timeout_s: float,
    ) -> dict:
        req = urlrequest.Request(
            url=url,
            method=method.upper(),
            data=body,
            headers={"Accept": "application/json", **(headers or {})},
        )
        try:
            with urlrequest.urlopen(req, timeout=timeout_s) as response:
                raw = response.read().decode("utf-8", errors="replace")
                status_code = int(getattr(response, "status", 200))
        except urlerror.HTTPError as exc:
            body_text = exc.read().decode("utf-8", errors="replace") if exc.fp is not None else ""
            payload = self._try_parse_json(body_text)
            code, message = self._extract_error(payload, default_message=f"upstream http {exc.code}")
            raise DispatchRequestError(status_code=int(exc.code), code=code, message=message) from exc
        except urlerror.URLError as exc:
            raise DispatchRequestError(status_code=502, code="UPSTREAM_UNREACHABLE", message=str(exc.reason)) from exc
        except Exception as exc:
            raise DispatchRequestError(status_code=502, code="UPSTREAM_ERROR", message=str(exc)) from exc

        payload = self._try_parse_json(raw)
        if status_code >= 400:
            code, message = self._extract_error(payload, default_message=f"upstream http {status_code}")
            raise DispatchRequestError(status_code=status_code, code=code, message=message)
        if payload is None:
            raise DispatchRequestError(status_code=502, code="UPSTREAM_INVALID_RESPONSE", message="non-json response")
        return payload

    @staticmethod
    def _unwrap_api_envelope(payload: dict, *, fallback_code: str) -> dict | list | None:
        if not isinstance(payload, dict):
            raise DispatchRequestError(status_code=502, code="UPSTREAM_INVALID_RESPONSE", message="invalid payload")
        ok = bool(payload.get("ok"))
        if ok:
            return payload.get("data")
        error_obj = payload.get("error")
        if isinstance(error_obj, dict):
            code = str(error_obj.get("code") or fallback_code)
            message = str(error_obj.get("message") or "upstream request failed")
        else:
            code = fallback_code
            message = "upstream request failed"
        raise DispatchRequestError(status_code=502, code=code, message=message)

    @staticmethod
    def _extract_error(payload: dict | None, *, default_message: str) -> tuple[str, str]:
        if not isinstance(payload, dict):
            return "UPSTREAM_ERROR", default_message
        error_obj = payload.get("error")
        if isinstance(error_obj, dict):
            return str(error_obj.get("code") or "UPSTREAM_ERROR"), str(error_obj.get("message") or default_message)
        return "UPSTREAM_ERROR", default_message

    @staticmethod
    def _try_parse_json(raw: str) -> dict | None:
        text = str(raw or "").strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except Exception:
            return None
        return parsed if isinstance(parsed, dict) else {"data": parsed}

    @staticmethod
    def _auth_headers(api_key: str) -> dict[str, str]:
        token = str(api_key or "").strip()
        if not token:
            return {}
        return {"x-api-key": token}

    @staticmethod
    def _encode_multipart(
        *,
        fields: list[tuple[str, str]],
        files: list[tuple[str, str, str, bytes]],
    ) -> tuple[str, bytes]:
        boundary = f"----snapocket-{uuid4().hex}"
        chunks: list[bytes] = []

        for name, value in fields:
            chunks.append(f"--{boundary}\r\n".encode("utf-8"))
            chunks.append(
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode("utf-8")
            )

        for field_name, filename, content_type, file_bytes in files:
            safe_name = filename.replace('"', "'")
            chunks.append(f"--{boundary}\r\n".encode("utf-8"))
            chunks.append(
                (
                    f'Content-Disposition: form-data; name="{field_name}"; filename="{safe_name}"\r\n'
                    f"Content-Type: {content_type}\r\n\r\n"
                ).encode("utf-8")
            )
            chunks.append(file_bytes)
            chunks.append(b"\r\n")

        chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
        body = b"".join(chunks)
        return f"multipart/form-data; boundary={boundary}", body
