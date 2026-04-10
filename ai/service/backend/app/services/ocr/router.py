"""Policy router that picks an available OCR engine based on hint/runtime."""

from __future__ import annotations

from typing import Callable

import cv2
import numpy as np
from langdetect import detect_langs

from app.schemas.infer import EngineHint
from app.services.ocr.base import OCREngine


class OCREngineRouter:
    def __init__(
        self,
        paddle_engine: OCREngine,
        glm_engine: OCREngine,
        default_engine: str = "auto",
        performance_provider: Callable[[], dict[str, dict[str, float]]] | None = None,
    ) -> None:
        self.paddle_engine = paddle_engine
        self.glm_engine = glm_engine
        self.default_engine = default_engine
        self.performance_provider = performance_provider

    def _resolve_hint(self, engine_hint: str | None) -> str:
        if engine_hint:
            return str(engine_hint).strip().lower()
        return str(self.default_engine).strip().lower()

    @staticmethod
    def _detect_language(text_hint: str | None) -> tuple[str, float]:
        text = (text_hint or "").strip()
        if len(text) < 8:
            return "unknown", 0.0
        try:
            langs = detect_langs(text)
        except Exception:
            return "unknown", 0.0
        if not langs:
            return "unknown", 0.0
        best = langs[0]
        return str(best.lang), float(best.prob)

    @staticmethod
    def _complexity_score(image_bytes: bytes | None) -> float:
        if not image_bytes:
            return 0.0
        try:
            arr = np.frombuffer(image_bytes, dtype=np.uint8)
            gray = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
            if gray is None or gray.size == 0:
                return 0.0
            variance = float(cv2.Laplacian(gray, cv2.CV_64F).var())
            # Normalize to [0,1] with a soft cap around dense text/graphics docs.
            return max(0.0, min(1.0, variance / 250.0))
        except Exception:
            return 0.0

    @staticmethod
    def _unavailable_message(engine: OCREngine, label: str) -> str:
        detail = ""
        if hasattr(engine, "availability_detail"):
            try:
                info = engine.availability_detail()
                detail = str(info.get("last_error", "") or "").strip()
            except Exception:
                detail = ""
        return f"{label} profile unavailable" + (f": {detail}" if detail else "")

    def _performance_stats(self) -> dict[str, dict[str, float]]:
        if self.performance_provider is None:
            return {}
        try:
            return self.performance_provider() or {}
        except Exception:
            return {}

    def _engine_score(
        self,
        engine_name: str,
        *,
        language: str,
        language_confidence: float,
        complexity: float,
        perf: dict[str, dict[str, float]],
    ) -> float:
        score = 1.0

        if language == "ko" and language_confidence >= 0.6:
            score += 0.30 if engine_name == "glm" else -0.10
        elif language in {"en", "de", "fr", "es"} and language_confidence >= 0.6:
            score += 0.15 if engine_name == "paddle" else -0.05

        if complexity >= 0.35:
            score += 0.20 if engine_name == "glm" else -0.05
        else:
            score += 0.10 if engine_name == "paddle" else 0.00

        perf_info = perf.get(engine_name, {})
        success_rate = float(perf_info.get("success_rate", 0.5))
        avg_latency_ms = float(perf_info.get("avg_latency_ms", 0.0))
        score += success_rate * 0.45
        if avg_latency_ms > 0:
            score -= min(0.40, avg_latency_ms / 6000.0)

        return score

    def _available_candidates(self) -> list[tuple[str, OCREngine]]:
        candidates: list[tuple[str, OCREngine]] = []
        if self.paddle_engine.available():
            candidates.append(("paddle", self.paddle_engine))
        if self.glm_engine.available():
            candidates.append(("glm", self.glm_engine))
        return candidates

    def select(
        self,
        engine_hint: str | None,
        *,
        image_bytes: bytes | None = None,
        text_hint: str | None = None,
    ) -> OCREngine:
        hint = self._resolve_hint(engine_hint)

        if hint == EngineHint.paddle.value:
            if self.paddle_engine.available():
                return self.paddle_engine
            raise RuntimeError(self._unavailable_message(self.paddle_engine, "PaddleOCR-VL"))

        if hint == EngineHint.glm.value:
            if self.glm_engine.available():
                return self.glm_engine
            raise RuntimeError(self._unavailable_message(self.glm_engine, "GLM-OCR"))

        candidates = self._available_candidates()
        if len(candidates) == 1:
            return candidates[0][1]
        if len(candidates) > 1:
            language, language_conf = self._detect_language(text_hint)
            complexity = self._complexity_score(image_bytes)
            perf = self._performance_stats()

            best_name, best_engine = max(
                candidates,
                key=lambda item: (
                    self._engine_score(
                        item[0],
                        language=language,
                        language_confidence=language_conf,
                        complexity=complexity,
                        perf=perf,
                    ),
                    1 if item[0] == "paddle" else 0,
                ),
            )
            del best_name
            return best_engine

        paddle_msg = self._unavailable_message(self.paddle_engine, "PaddleOCR-VL")
        glm_msg = self._unavailable_message(self.glm_engine, "GLM-OCR")
        raise RuntimeError(f"No OCR profile is available. {paddle_msg}; {glm_msg}")

    def alternate(
        self,
        current_engine: str,
        *,
        image_bytes: bytes | None = None,
        text_hint: str | None = None,
    ) -> OCREngine | None:
        candidates = [
            (name, engine)
            for name, engine in self._available_candidates()
            if name != current_engine
        ]
        if not candidates:
            return None
        language, language_conf = self._detect_language(text_hint)
        complexity = self._complexity_score(image_bytes)
        perf = self._performance_stats()
        _, selected = max(
            candidates,
            key=lambda item: self._engine_score(
                item[0],
                language=language,
                language_confidence=language_conf,
                complexity=complexity,
                perf=perf,
            ),
        )
        return selected

    def select_with_fallback(
        self,
        *,
        primary_engine: str,
        primary_confidence: float,
        threshold: float = 0.4,
        image_bytes: bytes | None = None,
        text_hint: str | None = None,
    ) -> OCREngine | None:
        if primary_confidence >= threshold:
            return None
        return self.alternate(
            current_engine=primary_engine,
            image_bytes=image_bytes,
            text_hint=text_hint,
        )
