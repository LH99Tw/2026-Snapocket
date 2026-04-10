"""Redis-backed job queue manager with cooperative cancellation and retries."""

from __future__ import annotations

import base64
import json
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import datetime, timezone
from threading import Event, Thread
from typing import Any, Callable
from uuid import uuid4

from app.schemas.job import JobInfo, JobStatus
from app.services.persistence import PersistenceStore

try:  # Optional dependency for environments that enable redis backend.
    import redis as redis_lib
except Exception:  # pragma: no cover - dependency optional
    redis_lib = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _json_default(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"__bytes_b64__": base64.b64encode(value).decode("ascii")}
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "model_dump"):
        return value.model_dump()
    raise TypeError(f"unsupported type for json serialization: {type(value)!r}")


def _json_object_hook(value: dict[str, Any]) -> Any:
    token = value.get("__bytes_b64__")
    if token is None:
        return value
    try:
        return base64.b64decode(token)
    except Exception:
        return b""


class RedisJobManager:
    def __init__(
        self,
        *,
        redis_url: str,
        task_handlers: dict[str, Callable[..., Any]],
        max_workers: int = 1,
        timeout_s: float = 180.0,
        max_retries: int = 1,
        retry_backoff_s: float = 1.5,
        persistence: PersistenceStore | None = None,
        namespace: str = "aiops",
    ) -> None:
        if redis_lib is None:
            raise RuntimeError("redis package is not installed")

        self._redis = redis_lib.Redis.from_url(redis_url, decode_responses=True)
        try:
            self._redis.ping()
        except Exception as exc:
            raise RuntimeError(f"redis unavailable: {exc}") from exc
        self._timeout_s = timeout_s
        self._max_retries = max_retries
        self._retry_backoff_s = retry_backoff_s
        self._persistence = persistence
        self._namespace = namespace
        self._queue_key = f"{namespace}:jobs:queue"
        self._index_key = f"{namespace}:jobs:index"

        self._task_handlers = dict(task_handlers)
        self._task_names_by_callable = {id(func): name for name, func in task_handlers.items()}

        self._stop_event = Event()
        self._workers: list[Thread] = []
        worker_count = max(1, int(max_workers))
        for idx in range(worker_count):
            thread = Thread(target=self._worker_loop, name=f"redis-job-worker-{idx+1}", daemon=True)
            thread.start()
            self._workers.append(thread)

    def shutdown(self) -> None:
        self._stop_event.set()
        for thread in self._workers:
            if thread.is_alive():
                thread.join(timeout=2.0)
        try:
            self._redis.close()
        except Exception:
            pass

    def submit(
        self,
        fn: Callable[..., Any],
        *args,
        job_meta: dict[str, Any] | None = None,
        **kwargs,
    ) -> str:
        task_name = self._task_names_by_callable.get(id(fn))
        if task_name is None:
            raise RuntimeError("Unsupported task for redis queue backend")

        task = {
            "name": task_name,
            "args": args,
            "kwargs": kwargs,
        }
        return self._submit_task(task=task, job_meta=job_meta)

    def _submit_task(self, *, task: dict[str, Any], job_meta: dict[str, Any] | None = None) -> str:
        job_id = str(uuid4())
        now = _utcnow()

        mapping = {
            "status": JobStatus.queued.value,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "error": "",
            "attempt": "0",
            "max_retries": str(self._max_retries),
            "timeout_s": str(self._timeout_s),
            "cancel_requested": "0",
            "task_json": json.dumps(task, default=_json_default),
            "request_meta_json": json.dumps(job_meta or {}, default=_json_default),
            "result_json": "",
        }

        key = self._job_key(job_id)
        self._redis.hset(key, mapping=mapping)
        self._redis.sadd(self._index_key, job_id)
        self._redis.lpush(self._queue_key, job_id)

        self._persist_job(job_id)
        return job_id

    def _job_key(self, job_id: str) -> str:
        return f"{self._namespace}:job:{job_id}"

    def _load_hash(self, job_id: str) -> dict[str, str]:
        key = self._job_key(job_id)
        data = self._redis.hgetall(key)
        if not data:
            raise KeyError(job_id)
        return data

    def _save_fields(self, job_id: str, **fields: str) -> None:
        key = self._job_key(job_id)
        update = dict(fields)
        update["updated_at"] = _utcnow().isoformat()
        self._redis.hset(key, mapping=update)
        self._persist_job(job_id)

    def _persist_job(self, job_id: str) -> None:
        if self._persistence is None:
            return

        try:
            info = self.get_info(job_id)
            job_hash = self._load_hash(job_id)
        except Exception:
            return

        request_meta = self._loads_json(job_hash.get("request_meta_json", "{}"))
        result_data = self._loads_json(job_hash.get("result_json", "")) if job_hash.get("result_json") else None

        self._persistence.upsert_job(
            info,
            request_meta=request_meta if isinstance(request_meta, dict) else None,
            result_data=result_data,
        )
        if info.status == JobStatus.succeeded and isinstance(result_data, dict) and result_data.get("doc_id"):
            self._persistence.insert_result(job_id=job_id, result_data=result_data)

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                item = self._redis.brpop(self._queue_key, timeout=1)
            except Exception:
                time.sleep(0.5)
                continue

            if not item:
                continue

            _, job_id = item
            try:
                self._execute_job(job_id)
            except Exception:
                # Worker must keep polling even on task failure.
                continue

    def _execute_job(self, job_id: str) -> None:
        job_hash = self._load_hash(job_id)
        if job_hash.get("cancel_requested") == "1":
            self._save_fields(job_id, status=JobStatus.cancelled.value, error="Cancelled by user")
            return

        task = self._loads_json(job_hash.get("task_json", "{}"))
        if not isinstance(task, dict) or "name" not in task:
            self._save_fields(job_id, status=JobStatus.failed.value, error="Invalid task payload")
            return

        attempts_allowed = int(job_hash.get("max_retries", "0") or "0") + 1
        for attempt in range(1, attempts_allowed + 1):
            self._save_fields(job_id, status=JobStatus.running.value, attempt=str(attempt), error="")
            refreshed = self._load_hash(job_id)
            if refreshed.get("cancel_requested") == "1":
                self._save_fields(job_id, status=JobStatus.cancelled.value, error="Cancelled by user")
                return

            try:
                result = self._run_task_with_timeout(task)
                payload = result.model_dump() if hasattr(result, "model_dump") else result
                result_json = json.dumps(payload, default=_json_default)
                self._save_fields(
                    job_id,
                    status=JobStatus.succeeded.value,
                    result_json=result_json,
                )
                return
            except Exception as exc:
                if attempt < attempts_allowed and self._load_hash(job_id).get("cancel_requested") != "1":
                    self._save_fields(
                        job_id,
                        error=f"{exc}. retrying {attempt}/{attempts_allowed - 1}",
                    )
                    if not self._sleep_with_cancel(job_id, self._retry_backoff_s * attempt):
                        self._save_fields(job_id, status=JobStatus.cancelled.value, error="Cancelled by user")
                        return
                    continue
                self._save_fields(job_id, status=JobStatus.failed.value, error=str(exc))
                return

    def _run_task_with_timeout(self, task: dict[str, Any]) -> Any:
        task_name = str(task.get("name", ""))
        fn = self._task_handlers.get(task_name)
        if fn is None:
            raise RuntimeError(f"Unknown task handler: {task_name}")

        args = self._decode(task.get("args", []))
        kwargs = self._decode(task.get("kwargs", {}))
        if not isinstance(args, list):
            args = []
        if not isinstance(kwargs, dict):
            kwargs = {}

        if self._timeout_s <= 0:
            return fn(*args, **kwargs)

        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(fn, *args, **kwargs)
        try:
            return future.result(timeout=self._timeout_s)
        except FutureTimeoutError as exc:
            future.cancel()
            raise TimeoutError(f"TIMEOUT: exceeded {self._timeout_s:.1f}s") from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _sleep_with_cancel(self, job_id: str, total_seconds: float) -> bool:
        deadline = time.monotonic() + max(0.0, total_seconds)
        while time.monotonic() < deadline:
            try:
                if self._load_hash(job_id).get("cancel_requested") == "1":
                    return False
            except Exception:
                return False
            time.sleep(0.2)
        return True

    def get_info(self, job_id: str) -> JobInfo:
        data = self._load_hash(job_id)
        created = self._parse_datetime(data.get("created_at"))
        updated = self._parse_datetime(data.get("updated_at"))
        status_str = data.get("status", JobStatus.failed.value)
        status = JobStatus(status_str)

        return JobInfo(
            job_id=job_id,
            status=status,
            created_at=created,
            updated_at=updated,
            error=data.get("error") or None,
            attempt=int(data.get("attempt", "0") or "0"),
            max_retries=int(data.get("max_retries", "0") or "0"),
            timeout_s=float(data.get("timeout_s", "0") or "0"),
        )

    def get_result(self, job_id: str):
        data = self._load_hash(job_id)
        raw = data.get("result_json")
        if not raw:
            return None
        return self._loads_json(raw)

    def list_jobs(self) -> list[JobInfo]:
        job_ids = sorted(self._redis.smembers(self._index_key))
        infos: list[JobInfo] = []
        for job_id in job_ids:
            try:
                infos.append(self.get_info(job_id))
            except Exception:
                continue
        infos.sort(key=lambda x: x.created_at, reverse=True)
        return infos

    def cancel(self, job_id: str) -> bool:
        info = self.get_info(job_id)
        if info.status in {JobStatus.succeeded, JobStatus.failed, JobStatus.cancelled}:
            return False

        self._save_fields(job_id, cancel_requested="1")

        # If still queued, remove from queue immediately.
        removed = self._redis.lrem(self._queue_key, 0, job_id)
        if removed > 0:
            self._save_fields(job_id, status=JobStatus.cancelled.value, error="Cancelled by user")
        return True

    def retry(self, job_id: str) -> str:
        data = self._load_hash(job_id)
        task = self._loads_json(data.get("task_json", "{}"))
        if not isinstance(task, dict):
            raise RuntimeError("Job cannot be retried")
        request_meta = self._loads_json(data.get("request_meta_json", "{}"))
        return self._submit_task(
            task=task,
            job_meta=request_meta if isinstance(request_meta, dict) else None,
        )

    @staticmethod
    def _parse_datetime(value: str | None) -> datetime:
        if not value:
            return _utcnow()
        try:
            dt = datetime.fromisoformat(value)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            return _utcnow()

    @staticmethod
    def _loads_json(value: str) -> Any:
        try:
            return json.loads(value, object_hook=_json_object_hook)
        except Exception:
            return {}

    @staticmethod
    def _decode(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                k: RedisJobManager._decode(v)
                for k, v in value.items()
            }
        if isinstance(value, list):
            return [RedisJobManager._decode(v) for v in value]
        return value
