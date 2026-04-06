"""Thread-based job runner with retry/backoff/timeout and persistence hooks."""

from __future__ import annotations

import time
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Callable
from uuid import uuid4

from app.schemas.job import JobInfo, JobStatus
from app.services.persistence import PersistenceStore


@dataclass
class _JobState:
    info: JobInfo
    future: Future | None = None
    result: Any | None = None
    fn: Callable[..., Any] | None = None
    args: tuple[Any, ...] = ()
    kwargs: dict[str, Any] | None = None
    cancel_requested: bool = False
    request_meta: dict[str, Any] | None = None
    result_persisted: bool = False


class JobManager:
    def __init__(
        self,
        max_workers: int = 2,
        *,
        timeout_s: float = 180.0,
        max_retries: int = 1,
        retry_backoff_s: float = 1.5,
        persistence: PersistenceStore | None = None,
    ) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        # These policies are global defaults for each submitted job.
        self._timeout_s = timeout_s
        self._max_retries = max_retries
        self._retry_backoff_s = retry_backoff_s
        self._persistence = persistence
        self._lock = Lock()
        self._jobs: dict[str, _JobState] = {}

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=False)

    def submit(
        self,
        fn: Callable[..., Any],
        *args,
        job_meta: dict[str, Any] | None = None,
        **kwargs,
    ) -> str:
        job_id = str(uuid4())
        now = datetime.now(timezone.utc)
        info = JobInfo(
            job_id=job_id,
            status=JobStatus.queued,
            created_at=now,
            updated_at=now,
            attempt=0,
            max_retries=self._max_retries,
            timeout_s=self._timeout_s,
        )
        state = _JobState(info=info, fn=fn, args=args, kwargs=kwargs, request_meta=job_meta)
        with self._lock:
            self._jobs[job_id] = state
        self._persist_job(job_id)

        def _runner() -> Any:
            # Retry loop is local to one logical job_id.
            attempts_allowed = self._max_retries + 1
            for attempt in range(1, attempts_allowed + 1):
                self._set_status(job_id, JobStatus.running)
                self._set_attempt(job_id, attempt)
                if self._is_cancel_requested(job_id):
                    self._set_error(job_id, "Cancelled by user")
                    self._set_status(job_id, JobStatus.cancelled)
                    return None

                try:
                    result = self._run_with_timeout(fn, args, kwargs)
                    self._set_result(job_id, result)
                    self._set_status(job_id, JobStatus.succeeded)
                    return result
                except Exception as exc:
                    should_retry = attempt < attempts_allowed and not self._is_cancel_requested(job_id)
                    if should_retry:
                        # Linear backoff: backoff * attempt.
                        self._set_error(
                            job_id,
                            f"{exc}. retrying {attempt}/{self._max_retries}",
                        )
                        if not self._sleep_with_cancel(job_id, self._retry_backoff_s * attempt):
                            self._set_error(job_id, "Cancelled by user")
                            self._set_status(job_id, JobStatus.cancelled)
                            return None
                        continue
                    self._set_error(job_id, str(exc))
                    self._set_status(job_id, JobStatus.failed)
                    raise

        future = self._executor.submit(_runner)
        state.future = future

        return job_id

    def _run_with_timeout(self, fn: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
        if self._timeout_s <= 0:
            return fn(*args, **kwargs)

        # Timeout wrapper runs the actual task in a temporary worker and returns
        # immediately on timeout without blocking caller shutdown path.
        inner_executor = ThreadPoolExecutor(max_workers=1)
        inner_future = inner_executor.submit(fn, *args, **kwargs)
        try:
            return inner_future.result(timeout=self._timeout_s)
        except FutureTimeoutError as exc:
            inner_future.cancel()
            raise TimeoutError(f"TIMEOUT: exceeded {self._timeout_s:.1f}s") from exc
        finally:
            # Do not block caller after timeout; best-effort cleanup only.
            inner_executor.shutdown(wait=False, cancel_futures=True)

    def _set_status(self, job_id: str, status: JobStatus) -> None:
        with self._lock:
            state = self._jobs.get(job_id)
            if not state:
                return
            state.info.status = status
            state.info.updated_at = datetime.now(timezone.utc)
        self._persist_job(job_id)

    def _set_attempt(self, job_id: str, attempt: int) -> None:
        with self._lock:
            state = self._jobs.get(job_id)
            if not state:
                return
            state.info.attempt = attempt
            state.info.updated_at = datetime.now(timezone.utc)
        self._persist_job(job_id)

    def _set_result(self, job_id: str, result: Any) -> None:
        with self._lock:
            state = self._jobs.get(job_id)
            if state:
                state.result = result
                state.info.updated_at = datetime.now(timezone.utc)
        self._persist_job(job_id)

    def _set_error(self, job_id: str, error: str) -> None:
        with self._lock:
            state = self._jobs.get(job_id)
            if state:
                state.info.error = error
                state.info.updated_at = datetime.now(timezone.utc)
        self._persist_job(job_id)

    def _persist_job(self, job_id: str) -> None:
        if self._persistence is None:
            return
        with self._lock:
            state = self._jobs.get(job_id)
            if not state:
                return
            info = state.info.model_copy(deep=True)
            result = state.result
            request_meta = dict(state.request_meta or {})
            persist_result = (
                state.info.status == JobStatus.succeeded
                and not state.result_persisted
                and result is not None
            )
            if persist_result:
                # Prevent duplicate inserts on repeated status updates.
                state.result_persisted = True
        payload = result.model_dump() if hasattr(result, "model_dump") else result
        self._persistence.upsert_job(info, request_meta=request_meta, result_data=payload)
        if persist_result and isinstance(payload, dict) and payload.get("doc_id"):
            self._persistence.insert_result(job_id=job_id, result_data=payload)

    def _is_cancel_requested(self, job_id: str) -> bool:
        with self._lock:
            state = self._jobs.get(job_id)
            return bool(state and state.cancel_requested)

    def _sleep_with_cancel(self, job_id: str, total_seconds: float) -> bool:
        if total_seconds <= 0:
            return True
        deadline = time.monotonic() + total_seconds
        while time.monotonic() < deadline:
            if self._is_cancel_requested(job_id):
                return False
            time.sleep(min(0.2, max(0.01, deadline - time.monotonic())))
        return not self._is_cancel_requested(job_id)

    def get_info(self, job_id: str) -> JobInfo:
        with self._lock:
            state = self._jobs.get(job_id)
            if not state:
                raise KeyError(job_id)
            return state.info.model_copy(deep=True)

    def get_result(self, job_id: str):
        with self._lock:
            state = self._jobs.get(job_id)
            if not state:
                raise KeyError(job_id)
            return state.result

    def list_jobs(self) -> list[JobInfo]:
        with self._lock:
            return [state.info.model_copy(deep=True) for state in self._jobs.values()]

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            state = self._jobs.get(job_id)
            if not state:
                raise KeyError(job_id)
            future = state.future
            state.cancel_requested = True
            status = state.info.status

        if status in {JobStatus.succeeded, JobStatus.failed, JobStatus.cancelled}:
            return False

        if future is None:
            self._set_status(job_id, JobStatus.cancelled)
            self._set_error(job_id, "Cancelled by user")
            return True

        cancelled = future.cancel()
        if cancelled:
            self._set_status(job_id, JobStatus.cancelled)
            self._set_error(job_id, "Cancelled by user")
            return True

        # Running jobs are cooperatively cancelled on next retry/sleep boundary.
        # Python threads cannot be force-killed safely here.
        self._set_error(job_id, "Cancellation requested")
        return True

    def retry(self, job_id: str) -> str:
        with self._lock:
            state = self._jobs.get(job_id)
            if not state:
                raise KeyError(job_id)
            if state.fn is None:
                raise RuntimeError("Job cannot be retried")
            fn = state.fn
            args = state.args
            kwargs = state.kwargs or {}
            request_meta = dict(state.request_meta or {})
        return self.submit(fn, *args, job_meta=request_meta, **kwargs)
