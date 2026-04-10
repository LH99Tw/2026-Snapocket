"""In-memory model registry with activation history and metrics."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock

from app.schemas.model import ModelInfo, ModelMetrics
from app.services.persistence import PersistenceStore


@dataclass
class _ModelState:
    info: ModelInfo
    metrics: ModelMetrics


class ModelRegistry:
    def __init__(self, persistence: PersistenceStore | None = None) -> None:
        self._lock = Lock()
        self._models: dict[str, _ModelState] = {}
        self._activation_history: list[str] = []
        self._persistence = persistence
        self._bootstrap_defaults()

    def _bootstrap_defaults(self) -> None:
        self.register_model(
            ModelInfo(
                model_id="llamacpp-paddleocr-vl",
                name="PaddleOCR-VL",
                engine="paddle",
                version="llama.cpp",
                active=False,
                status="inactive",
            )
        )
        self.register_model(
            ModelInfo(
                model_id="llamacpp-glm-ocr",
                name="GLM-OCR",
                engine="glm",
                version="llama.cpp",
                active=False,
                status="inactive",
            )
        )

    def register_model(self, model: ModelInfo) -> None:
        with self._lock:
            if model.active:
                for state in self._models.values():
                    state.info.active = False
            self._models[model.model_id] = _ModelState(
                info=model,
                metrics=ModelMetrics(model_id=model.model_id),
            )
            models_snapshot = [state.info.model_copy(deep=True) for state in self._models.values()]
        self._sync_persistence(models_snapshot)
        self._audit("model.register", model.model_id, {"engine": model.engine, "active": model.active})

    def list_models(self) -> list[ModelInfo]:
        with self._lock:
            return [state.info.model_copy(deep=True) for state in self._models.values()]

    def activate(self, model_id: str) -> ModelInfo:
        with self._lock:
            if model_id not in self._models:
                raise KeyError(model_id)
            current_active = None
            for mid, state in self._models.items():
                if state.info.active:
                    current_active = mid
                    break
            if current_active and current_active != model_id:
                self._activation_history.append(current_active)
            for state in self._models.values():
                state.info.active = False
            self._models[model_id].info.active = True
            self._models[model_id].info.status = "ready"
            activated = self._models[model_id].info.model_copy(deep=True)
            models_snapshot = [state.info.model_copy(deep=True) for state in self._models.values()]
        self._sync_persistence(models_snapshot)
        self._audit("model.activate", model_id, {})
        return activated

    def rollback(self, model_id: str | None = None) -> ModelInfo:
        with self._lock:
            if model_id:
                if model_id not in self._models:
                    raise KeyError(model_id)
                target = model_id
            else:
                if not self._activation_history:
                    raise RuntimeError("No rollback target")
                target = self._activation_history.pop()
                if target not in self._models:
                    raise RuntimeError("Rollback target not found")

            current_active = None
            for mid, state in self._models.items():
                if state.info.active:
                    current_active = mid
                    break
            if current_active and current_active != target:
                self._activation_history.append(current_active)

            for state in self._models.values():
                state.info.active = False
            self._models[target].info.active = True
            self._models[target].info.status = "ready"
            rolled = self._models[target].info.model_copy(deep=True)
            models_snapshot = [state.info.model_copy(deep=True) for state in self._models.values()]
        self._sync_persistence(models_snapshot)
        self._audit("model.rollback", target, {"requested_model_id": model_id})
        return rolled

    def deactivate(self, model_id: str) -> ModelInfo:
        with self._lock:
            if model_id not in self._models:
                raise KeyError(model_id)
            self._models[model_id].info.active = False
            self._models[model_id].info.status = "inactive"
            deactivated = self._models[model_id].info.model_copy(deep=True)
            models_snapshot = [state.info.model_copy(deep=True) for state in self._models.values()]
        self._sync_persistence(models_snapshot)
        self._audit("model.deactivate", model_id, {})
        return deactivated

    def sync_active_engine(self, engine: str, *, reason: str = "runtime.sync") -> ModelInfo | None:
        target_engine = str(engine or "").strip().lower()
        if target_engine not in {"paddle", "glm"}:
            return None

        with self._lock:
            target_id: str | None = None
            current_active_id: str | None = None
            for mid, state in self._models.items():
                if state.info.active:
                    current_active_id = mid
                if target_id is None and state.info.engine == target_engine:
                    target_id = mid

            if target_id is None:
                return None
            if current_active_id == target_id:
                return self._models[target_id].info.model_copy(deep=True)

            for state in self._models.values():
                state.info.active = False
            self._models[target_id].info.active = True
            if self._models[target_id].info.status == "inactive":
                self._models[target_id].info.status = "ready"
            synced = self._models[target_id].info.model_copy(deep=True)
            models_snapshot = [state.info.model_copy(deep=True) for state in self._models.values()]

        self._sync_persistence(models_snapshot)
        self._audit("model.sync_active", target_id, {"engine": target_engine, "reason": reason})
        return synced

    def active_engine(self) -> str:
        with self._lock:
            for state in self._models.values():
                if state.info.active:
                    return state.info.engine
        return "auto"

    def get_metrics(self, model_id: str) -> ModelMetrics:
        with self._lock:
            if model_id not in self._models:
                raise KeyError(model_id)
            return self._models[model_id].metrics.model_copy(deep=True)

    def record(self, model_id: str, success: bool, latency_ms: int) -> None:
        with self._lock:
            state = self._models.get(model_id)
            if not state:
                return
            m = state.metrics
            if success:
                m.success_count += 1
            else:
                m.failure_count += 1
            total = m.success_count + m.failure_count
            if total == 1:
                m.avg_latency_ms = float(latency_ms)
            else:
                m.avg_latency_ms = ((m.avg_latency_ms * (total - 1)) + latency_ms) / total

    def engine_runtime_stats(self) -> dict[str, dict[str, float]]:
        with self._lock:
            states = [state for state in self._models.values()]
        by_engine: dict[str, dict[str, float]] = {}
        for state in states:
            engine = state.info.engine
            metric = state.metrics
            bucket = by_engine.setdefault(
                engine,
                {"success_count": 0.0, "failure_count": 0.0, "latency_total": 0.0, "sample_count": 0.0},
            )
            success = float(metric.success_count)
            failure = float(metric.failure_count)
            sample = success + failure
            bucket["success_count"] += success
            bucket["failure_count"] += failure
            bucket["latency_total"] += float(metric.avg_latency_ms) * sample
            bucket["sample_count"] += sample

        normalized: dict[str, dict[str, float]] = {}
        for engine, raw in by_engine.items():
            sample = raw["sample_count"]
            success = raw["success_count"]
            failure = raw["failure_count"]
            success_rate = (success / (success + failure)) if (success + failure) > 0 else 0.5
            avg_latency = (raw["latency_total"] / sample) if sample > 0 else 0.0
            normalized[engine] = {
                "success_rate": float(success_rate),
                "avg_latency_ms": float(avg_latency),
                "sample_count": float(sample),
            }
        return normalized

    def _sync_persistence(self, models: list[ModelInfo]) -> None:
        if self._persistence is None:
            return
        self._persistence.sync_models(models)

    def _audit(self, action: str, model_id: str, detail: dict | None = None) -> None:
        if self._persistence is None:
            return
        self._persistence.insert_audit(
            action=action,
            target_type="model",
            target_id=model_id,
            detail=detail or {},
        )
