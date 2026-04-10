"""HTTP multimodal OCR engine adapter for llama.cpp OpenAI-compatible API."""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import re
import time
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Lock
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest

from PIL import Image

from app.services.ocr.base import OCREngine, OCREngineBusyError, OCREngineResult

logger = logging.getLogger(__name__)

_FENCE_LINE_RE = re.compile(r"^\s*`{3,}\s*([A-Za-z0-9_.:+-]+)?\s*$")
_PROFILE_PROMPTS: dict[str, str] = {
    "paddle": (
        "You are an OCR engine for document images. "
        "Extract all visible text exactly as written. "
        "Preserve line breaks. Return plain text only without explanation."
    ),
    "glm": (
        "You are an OCR engine for document images. "
        "Extract all visible text exactly as written. "
        "Preserve line breaks and keep Korean/English tokens unchanged. "
        "Return plain text only without explanation."
    ),
}
_STOP_TOKENS = ["</s>", "<|end_of_sentence|>"]


class LlamaCppVisionEngine(OCREngine):
    """OCR engine backed by llama.cpp server (/v1 OpenAI-compatible endpoints)."""

    def __init__(
        self,
        *,
        name: str,
        model: str,
        profile: str,
        enabled: bool = True,
        base_url: str = "http://llama-server:8080",
        availability_ttl_s: float = 15.0,
        request_timeout_s: float = 120.0,
        keep_alive: str = "10m",
        temperature: float = 0.0,
        max_side_px: int = 1536,
        max_tokens: int = 96,
    ) -> None:
        self.name = name
        self.model = str(model or "").strip()
        self.profile = str(profile or "").strip().lower()
        self.enabled = bool(enabled)
        self.base_url = self._normalize_base_url(base_url)
        self.availability_ttl_s = max(1.0, float(availability_ttl_s))
        self.request_timeout_s = max(5.0, float(request_timeout_s))
        self.keep_alive = str(keep_alive or "10m").strip() or "10m"
        self.temperature = float(temperature)
        self.max_side_px = max(256, int(max_side_px))
        self.max_tokens = max(16, min(2048, int(max_tokens)))

        self._lock = Lock()
        self._last_error: str | None = None
        self._availability_cache: bool | None = None
        self._availability_checked_at: float = 0.0
        self._resolved_model: str | None = None
        self._generation_warm: bool = False
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"llamacpp-{self.name}")
        self._active_inference: Future[list[OCREngineResult]] | None = None

    @staticmethod
    def _normalize_base_url(base_url: str) -> str:
        token = str(base_url or "").strip().rstrip("/")
        if not token:
            return "http://llama-server:8080"
        if token.startswith("http://") or token.startswith("https://"):
            return token
        return f"http://{token}"

    def reconfigure_model(self, model: str) -> None:
        new_model = str(model or "").strip()
        if not new_model:
            raise ValueError("model must not be empty")
        with self._lock:
            self.model = new_model
            self._resolved_model = None
            self._availability_cache = None
            self._availability_checked_at = 0.0
            self._last_error = None
            self._generation_warm = False

    def availability_detail(self) -> dict[str, Any]:
        with self._lock:
            return {
                "cached": self._availability_cache,
                "checked_at_monotonic": self._availability_checked_at,
                "last_error": self._last_error,
                "backend": "llama.cpp-openai",
                "base_url": self.base_url,
                "model": self.model,
                "resolved_model": self._resolved_model or self.model,
                "profile": self.profile,
                "request_timeout_s": self.request_timeout_s,
                "keep_alive": self.keep_alive,
                "temperature": self.temperature,
                "max_side_px": self.max_side_px,
                "max_tokens": self.max_tokens,
                "generation_warm": self._generation_warm,
                "inflight": bool(self._active_inference is not None and not self._active_inference.done()),
            }

    def _request_json(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urlrequest.Request(url=url, data=data, method=method.upper(), headers=headers)
        try:
            with urlrequest.urlopen(req, timeout=self.request_timeout_s) as resp:
                body = resp.read().decode("utf-8", errors="replace")
        except urlerror.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace") if exc.fp is not None else ""
            raise RuntimeError(f"HTTP {exc.code}: {body[:240]}") from exc
        except urlerror.URLError as exc:
            raise RuntimeError(f"connection failed: {exc.reason}") from exc

        body = body.strip()
        if not body:
            return {}
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"backend returned non-JSON response: {body[:240]}") from exc
        if not isinstance(parsed, dict):
            raise RuntimeError("backend returned unexpected JSON shape")
        return parsed

    @staticmethod
    def _model_match(available_name: str, target: str) -> bool:
        left = str(available_name or "").strip()
        right = str(target or "").strip()
        if not left or not right:
            return False
        if left == right:
            return True
        if ":" not in right and left.startswith(f"{right}:"):
            return True
        if right.endswith(":latest") and left == right.split(":", 1)[0]:
            return True
        if right.lower() in left.lower():
            return True
        return False

    def _probe_openai(self) -> tuple[bool, str | None]:
        payload = self._request_json("GET", "/v1/models")
        rows = payload.get("data")
        if not isinstance(rows, list):
            return False, "openai /v1/models response is invalid"

        ids: list[str] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            model_id = str(row.get("id") or "").strip()
            if model_id:
                ids.append(model_id)
        if not ids:
            return False, "no models found in /v1/models"

        resolved: str | None = None
        if self.model:
            for model_id in ids:
                if self._model_match(model_id, self.model):
                    resolved = model_id
                    break
        if resolved is None and len(ids) == 1:
            resolved = ids[0]
        if resolved is None:
            return False, f"model '{self.model}' not found in /v1/models ({', '.join(ids[:8])})"

        self._resolved_model = resolved
        return True, None

    def _probe(self) -> bool:
        if not self.enabled:
            self._last_error = f"{self.name} engine is disabled"
            return False

        try:
            ok, err = self._probe_openai()
            if ok:
                self._last_error = None
                return True
            self._last_error = err or "backend unavailable"
            return False
        except Exception as exc:
            self._last_error = str(exc) or repr(exc)
            return False

    def probe(self) -> bool:
        ok = self._probe()
        with self._lock:
            self._availability_cache = ok
            self._availability_checked_at = time.monotonic()
        return ok

    def available(self) -> bool:
        with self._lock:
            checked_at = self._availability_checked_at
            cached = self._availability_cache
        if cached is not None and (time.monotonic() - checked_at) < self.availability_ttl_s:
            return cached
        return self.probe()

    def warmup(self) -> bool:
        if not self.available():
            raise RuntimeError(self._last_error or f"{self.name} model unavailable")

        with self._lock:
            if self._generation_warm:
                return True

        # Trigger one tiny multimodal generation during activation so the first
        # Playground request is not forced to pay model cold-start cost.
        probe = Image.new("RGB", (96, 96), color=(255, 255, 255))
        out = io.BytesIO()
        probe.save(out, format="JPEG", quality=60)
        probe_b64 = base64.b64encode(out.getvalue()).decode("ascii")
        try:
            _ = self._infer_with_openai(probe_b64, max_tokens_override=1)
        except Exception as exc:
            with self._lock:
                self._last_error = str(exc) or repr(exc)
                self._availability_cache = False
                self._availability_checked_at = time.monotonic()
                self._generation_warm = False
            raise RuntimeError(f"{self.name} warmup failed: {exc}") from exc

        with self._lock:
            self._generation_warm = True
            self._last_error = None
            self._availability_cache = True
            self._availability_checked_at = time.monotonic()
        return True

    def unload(self) -> bool:
        # llama.cpp server does not expose explicit unload API.
        # If a request is still running, keep engine pinned busy.
        with self._lock:
            if self._active_inference is not None and not self._active_inference.done():
                return False
            self._generation_warm = False
        return True

    def _prepare_image_b64(self, image_bytes: bytes) -> str:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        width, height = image.size
        max_side = max(width, height)
        if max_side > self.max_side_px:
            scale = float(self.max_side_px) / float(max_side)
            resized = (
                max(1, int(round(width * scale))),
                max(1, int(round(height * scale))),
            )
            image = image.resize(resized, Image.Resampling.LANCZOS)

        out = io.BytesIO()
        image.save(out, format="JPEG", quality=82)
        return base64.b64encode(out.getvalue()).decode("ascii")

    @staticmethod
    def _strip_fence_lines(text: str) -> str:
        lines = str(text or "").splitlines()
        kept: list[str] = []
        for line in lines:
            if _FENCE_LINE_RE.match(line):
                continue
            kept.append(line)
        return "\n".join(kept).strip()

    @staticmethod
    def _coerce_ocr_text(raw: str) -> str:
        text = str(raw or "").strip()
        if not text:
            return ""

        candidate = text
        if candidate.startswith("{") or candidate.startswith("["):
            try:
                data = json.loads(candidate)
                if isinstance(data, dict):
                    if isinstance(data.get("text"), str):
                        return str(data["text"]).strip()
                    if isinstance(data.get("content"), str):
                        return str(data["content"]).strip()
                    lines = data.get("lines")
                    if isinstance(lines, list):
                        joined = "\n".join(str(line).strip() for line in lines if str(line).strip())
                        if joined:
                            return joined
                elif isinstance(data, list):
                    joined = "\n".join(str(line).strip() for line in data if str(line).strip())
                    if joined:
                        return joined
            except Exception:
                pass

        return LlamaCppVisionEngine._strip_fence_lines(text)

    def _prompt(self) -> str:
        return _PROFILE_PROMPTS.get(self.profile, _PROFILE_PROMPTS["paddle"])

    @staticmethod
    def _extract_openai_message_content(response: dict[str, Any]) -> str:
        choices = response.get("choices")
        if not isinstance(choices, list) or not choices:
            return ""
        first = choices[0] if isinstance(choices[0], dict) else {}
        message = first.get("message") if isinstance(first, dict) else {}
        if not isinstance(message, dict):
            return ""
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if not isinstance(item, dict):
                    continue
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
            return "\n".join(parts).strip()
        return ""

    def _infer_with_openai(self, image_b64: str, *, max_tokens_override: int | None = None) -> str:
        max_tokens = self.max_tokens if max_tokens_override is None else max(1, int(max_tokens_override))
        payload = {
            "model": self._resolved_model or self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": self._prompt()},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                        },
                    ],
                }
            ],
            "temperature": self.temperature,
            "max_tokens": max_tokens,
            "stop": _STOP_TOKENS,
        }
        response = self._request_json("POST", "/v1/chat/completions", payload)
        return self._extract_openai_message_content(response)

    def infer_image(self, image_bytes: bytes, page_no: int = 1) -> list[OCREngineResult]:
        if not self.available():
            raise RuntimeError(self._last_error or f"{self.name} model unavailable")
        if not image_bytes:
            raise RuntimeError("empty image payload")

        try:
            image_b64 = self._prepare_image_b64(image_bytes)
            content = self._infer_with_openai(image_b64)

            text = self._coerce_ocr_text(content)
            if not text:
                raise RuntimeError("empty OCR output from backend")

            lines = [line.strip() for line in text.splitlines() if line.strip()]
            if not lines:
                lines = [text]

            deduped: list[str] = []
            seen: set[str] = set()
            for line in lines:
                if line in seen:
                    continue
                seen.add(line)
                deduped.append(line)

            with self._lock:
                self._generation_warm = True

            return [
                OCREngineResult(
                    text=line,
                    confidence=0.86,
                    bbox=None,
                    page_no=page_no,
                    block_type="text",
                )
                for line in deduped
            ]
        except Exception as exc:
            with self._lock:
                self._last_error = str(exc) or repr(exc)
                self._availability_cache = False
                self._availability_checked_at = time.monotonic()
            raise RuntimeError(f"{self.name} OCR failed: {exc}") from exc

    async def infer_image_async(
        self,
        image_bytes: bytes,
        page_no: int = 1,
    ) -> list[OCREngineResult]:
        # Ensure one in-flight request per engine. If timeout cancels the caller,
        # the backend task may still be running; keep busy state until it truly ends.
        with self._lock:
            if self._active_inference is not None and not self._active_inference.done():
                raise OCREngineBusyError(
                    f"{self.name} inference already running. Wait for completion and retry."
                )
            future: Future[list[OCREngineResult]] = self._executor.submit(
                self.infer_image, image_bytes, page_no
            )
            self._active_inference = future

        def _clear_inflight(done_future: Future[list[OCREngineResult]]) -> None:
            with self._lock:
                if self._active_inference is done_future:
                    self._active_inference = None

        future.add_done_callback(_clear_inflight)
        return await asyncio.wrap_future(future)
