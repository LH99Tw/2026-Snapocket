"""Local HuggingFace safetensors OCR engine (GLM / PaddleOCR-VL)."""

from __future__ import annotations

import asyncio
import importlib.util
import io
import json
import logging
import math
import os
import re
import shutil
import subprocess
import tempfile
import time
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Lock
from typing import Any

from PIL import Image

from app.services.ocr.base import OCREngine, OCREngineBusyError, OCREngineResult

logger = logging.getLogger(__name__)

_FENCE_LINE_RE = re.compile(r"^\s*`{3,}\s*([A-Za-z0-9_.:+-]+)?\s*$")
_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)
_FORMAT_LABEL_TOKENS = {
    "markdown",
    "text",
    "plaintext",
    "plain",
    "json",
    "yaml",
    "xml",
    "html",
    "sql",
    "python",
    "javascript",
    "typescript",
    "bash",
    "shell",
    "marketing",
    "output",
}
_PROMPT_CATALOG: dict[str, list[str]] = {
    "glm": [
        "Text Recognition:",
        "Table Recognition:",
        "Formula Recognition:",
    ],
    "paddle": [
        "OCR:",
        "Table Recognition:",
        "Formula Recognition:",
        "Chart Recognition:",
        "Spotting:",
        "Seal Recognition:",
    ],
}


class LocalHFVisionEngine(OCREngine):
    """Inference adapter for local model folders containing safetensors."""

    def __init__(
        self,
        *,
        name: str,
        model_path: str,
        profile: str,
        enabled: bool = True,
        availability_ttl_s: float = 15.0,
        device: str = "auto",
        max_new_tokens: int = 512,
        max_side_px: int = 768,
        cpu_threads: int = 4,
        interop_threads: int = 1,
        trust_remote_code: bool = True,
        task_prompt_mode: str = "adaptive",
        task_prompt_max_passes: int = 2,
        task_prompt_adaptive_min_chars: int = 120,
        hint_ocr_enable: bool = True,
        hint_ocr_langs: str = "kor+eng",
        hint_ocr_timeout_s: float = 1.2,
        hint_ocr_max_chars: int = 800,
        paddle_official_fallback: bool = False,
    ) -> None:
        self.name = name
        self.model_path = model_path.strip()
        self.profile = profile.strip().lower()
        self.enabled = enabled
        self.availability_ttl_s = max(1.0, float(availability_ttl_s))
        self.device = device.strip().lower() or "auto"
        self.max_new_tokens = max(32, int(max_new_tokens))
        self.max_side_px = max(256, int(max_side_px))
        self.cpu_threads = max(1, int(cpu_threads))
        self.interop_threads = max(1, int(interop_threads))
        self.trust_remote_code = bool(trust_remote_code)
        mode = str(task_prompt_mode or "adaptive").strip().lower()
        self.task_prompt_mode = mode if mode in {"single", "adaptive", "multi"} else "adaptive"
        self.task_prompt_max_passes = max(1, min(6, int(task_prompt_max_passes)))
        self.task_prompt_adaptive_min_chars = max(1, int(task_prompt_adaptive_min_chars))
        self.hint_ocr_enable = bool(hint_ocr_enable)
        self.hint_ocr_langs = str(hint_ocr_langs or "kor+eng").strip() or "kor+eng"
        self.hint_ocr_timeout_s = max(0.2, float(hint_ocr_timeout_s))
        self.hint_ocr_max_chars = max(32, int(hint_ocr_max_chars))
        self.paddle_official_fallback = bool(paddle_official_fallback)

        self._lock = Lock()
        self._model: Any | None = None
        self._processor: Any | None = None
        self._torch: Any | None = None
        self._model_device: str = "cpu"
        self._thread_limits_applied = False
        self._generation_warm = False
        self._resolved_model_path: str = self.model_path
        self._paddle_official_pipeline: Any | None = None
        self._active_inference: Future[list[OCREngineResult]] | None = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"{self.name}-ocr")
        self._hint_ocr_binary: str | None = None
        self._hint_ocr_checked = False

        self._last_error: str | None = None
        self._availability_cache: bool | None = None
        self._availability_checked_at: float = 0.0

    def availability_detail(self) -> dict[str, Any]:
        with self._lock:
            return {
                "cached": self._availability_cache,
                "checked_at_monotonic": self._availability_checked_at,
                "last_error": self._last_error,
                "backend": "local-hf",
                "model_path": self.model_path,
                "resolved_model_path": self._resolved_model_path,
                "quantized_artifact": os.path.exists(
                    os.path.join(self._resolved_model_path, "quant_manifest.json")
                ),
                "profile": self.profile,
                "device": self.device,
                "max_side_px": self.max_side_px,
                "task_prompt_mode": self.task_prompt_mode,
                "task_prompt_max_passes": self.task_prompt_max_passes,
                "hint_ocr_enable": self.hint_ocr_enable,
                "hint_ocr_langs": self.hint_ocr_langs,
                "hint_ocr_timeout_s": self.hint_ocr_timeout_s,
                "paddle_official_fallback": self.paddle_official_fallback,
                "cpu_threads": self.cpu_threads,
                "interop_threads": self.interop_threads,
                "model_loaded": self._model is not None and self._processor is not None,
                "inference_running": bool(
                    self._active_inference is not None and not self._active_inference.done()
                ),
            }

    def reconfigure_model_path(self, model_path: str) -> None:
        new_path = str(model_path or "").strip()
        if not new_path:
            raise ValueError("model_path must not be empty")
        with self._lock:
            if self.model_path == new_path:
                return
            self.model_path = new_path
            self._resolved_model_path = new_path
            self._model = None
            self._processor = None
            self._torch = None
            self._model_device = "cpu"
            self._generation_warm = False
            self._availability_cache = None
            self._availability_checked_at = 0.0
            self._last_error = None

    def _infer_with_paddle_official_runtime(
        self,
        image_bytes: bytes,
        page_no: int,
    ) -> list[OCREngineResult]:
        if self.profile != "paddle":
            raise RuntimeError("paddle official fallback is only valid for paddle profile")
        self._ensure_hf_cache_env()
        with self._lock:
            if self._paddle_official_pipeline is None:
                from paddleocr import PaddleOCRVL

                self._paddle_official_pipeline = PaddleOCRVL()
            pipeline = self._paddle_official_pipeline

        temp_path = ""
        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                temp_path = tmp.name
                tmp.write(image_bytes)
            outputs = pipeline.predict(temp_path)
        finally:
            if temp_path:
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

        blocks = self._parse_paddle_outputs(outputs, page_no=page_no)
        if not blocks:
            raise RuntimeError("Paddle official fallback returned empty result")
        return blocks

    @staticmethod
    def _parse_paddle_outputs(outputs: Any, page_no: int) -> list[OCREngineResult]:
        if outputs is None:
            return []
        if isinstance(outputs, (list, tuple)):
            items = list(outputs)
        else:
            try:
                items = list(outputs)
            except TypeError:
                items = [outputs]

        results: list[OCREngineResult] = []
        seen: set[str] = set()
        for item in items:
            text = LocalHFVisionEngine._sanitize_text(str(item))
            if not text:
                continue
            for line in text.splitlines():
                s = line.strip()
                if not s or s in seen:
                    continue
                seen.add(s)
                results.append(OCREngineResult(text=s, confidence=0.0, bbox=None, page_no=page_no))
        return results

    def _resolve_model_path(self) -> str:
        raw = self.model_path.strip()
        candidates = [raw]
        base = os.path.basename(raw.rstrip("/"))
        if base:
            candidates.append(f"/app/{base}")
            candidates.append(f"/app/models/{base}")
            candidates.append(os.path.join(os.getcwd(), base))
        for path in candidates:
            if path and os.path.isdir(path):
                return path
        return raw

    @staticmethod
    def _prompt_for(profile: str) -> str:
        prompts = _PROMPT_CATALOG.get(profile.strip().lower())
        if prompts:
            return prompts[0]
        return "Extract all visible text from this image."

    @staticmethod
    def _prompt_catalog_for(profile: str) -> list[str]:
        prompts = _PROMPT_CATALOG.get(str(profile or "").strip().lower(), [])
        return prompts[:] if prompts else ["Extract all visible text from this image."]

    @staticmethod
    def _ensure_hf_cache_env() -> None:
        # Keep HF caches writable in sandboxed environments.
        hf_home = os.environ.get("HF_HOME", "").strip() or "/tmp/hf_home"
        os.environ.setdefault("HF_HOME", hf_home)
        os.environ.setdefault("HF_MODULES_CACHE", os.path.join(hf_home, "modules"))
        os.environ.setdefault("TRANSFORMERS_CACHE", os.path.join(hf_home, "transformers"))
        os.environ.setdefault("HUGGINGFACE_HUB_CACHE", os.path.join(hf_home, "hub"))
        os.environ.setdefault("PADDLE_PDX_CACHE_HOME", "/tmp/paddlex_cache")
        os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
        os.environ.setdefault("MPLCONFIGDIR", "/tmp/mpl")
        os.environ.setdefault("XDG_CACHE_HOME", "/tmp/xdg-cache")
        for key in ("HF_HOME", "HF_MODULES_CACHE", "TRANSFORMERS_CACHE", "HUGGINGFACE_HUB_CACHE"):
            try:
                os.makedirs(os.environ[key], exist_ok=True)
            except Exception:
                pass
        for key in ("PADDLE_PDX_CACHE_HOME", "MPLCONFIGDIR", "XDG_CACHE_HOME"):
            try:
                os.makedirs(os.environ[key], exist_ok=True)
            except Exception:
                pass

    def _probe(self) -> bool:
        if not self.enabled:
            self._last_error = f"{self.name} engine is disabled"
            return False

        resolved = self._resolve_model_path()
        self._resolved_model_path = resolved
        if not os.path.isdir(resolved):
            self._last_error = f"local model directory not found: {resolved}"
            return False

        config_path = os.path.join(resolved, "config.json")
        model_path = os.path.join(resolved, "model.safetensors")
        quant_manifest_path = os.path.join(resolved, "quant_manifest.json")
        has_standard = os.path.exists(model_path)
        has_quant = os.path.exists(quant_manifest_path)
        if not os.path.exists(config_path):
            self._last_error = f"missing model files in {resolved}: config.json"
            return False
        if not has_standard and not has_quant:
            self._last_error = (
                f"missing model weights in {resolved}: "
                "expected model.safetensors or quant_manifest.json"
            )
            return False
        if has_quant and not os.path.isdir(os.path.join(resolved, "quantized")):
            self._last_error = f"quantized model folder is missing: {resolved}/quantized"
            return False

        required_modules = ["torch", "transformers", "torchvision"]
        if self.profile == "paddle":
            required_modules.append("einops")
        missing = [name for name in required_modules if importlib.util.find_spec(name) is None]
        if missing:
            self._last_error = (
                f"local-hf dependencies missing: {', '.join(missing)}. "
                "Install required runtime packages before activation."
            )
            return False

        try:
            self._ensure_hf_cache_env()
            import torch  # noqa: F401
            from transformers import (  # noqa: F401
                AutoModelForCausalLM,
                AutoModelForImageTextToText,
                AutoProcessor,
            )
        except Exception as exc:
            self._last_error = f"local-hf runtime import failed: {exc}"
            return False

        self._last_error = None
        return True

    def available(self) -> bool:
        if not self.enabled:
            return False

        with self._lock:
            if (
                self._availability_cache is not None
                and (time.monotonic() - self._availability_checked_at) < self.availability_ttl_s
            ):
                return self._availability_cache

        ok = self._probe()
        with self._lock:
            self._availability_cache = ok
            self._availability_checked_at = time.monotonic()
        return ok

    def _select_device(self, torch_mod: Any) -> str:
        desired = self.device
        if desired not in {"auto", "cpu", "cuda", "mps"}:
            desired = "auto"
        if desired == "cpu":
            return "cpu"
        if desired == "cuda":
            return "cuda" if torch_mod.cuda.is_available() else "cpu"
        if desired == "mps":
            has_mps = bool(getattr(getattr(torch_mod, "backends", None), "mps", None))
            return "mps" if has_mps and torch_mod.backends.mps.is_available() else "cpu"
        if torch_mod.cuda.is_available():
            return "cuda"
        has_mps = bool(getattr(getattr(torch_mod, "backends", None), "mps", None))
        if has_mps and torch_mod.backends.mps.is_available():
            return "mps"
        return "cpu"

    @staticmethod
    def _orthogonal_matrix(size: int, seed: int, torch_mod: Any) -> Any:
        g = torch_mod.Generator(device="cpu")
        g.manual_seed(int(seed))
        a = torch_mod.randn(size, size, generator=g, dtype=torch_mod.float32)
        q, r = torch_mod.linalg.qr(a, mode="reduced")
        d = torch_mod.sign(torch_mod.diag(r))
        d[d == 0] = 1.0
        q = q * d.unsqueeze(0)
        return q.contiguous()

    @classmethod
    def _decode_turboquant_tensor(
        cls,
        *,
        info: dict[str, Any],
        fetch_tensor: Any,
        method: str,
        codebook: Any,
        out_dtype: Any,
        torch_mod: Any,
    ) -> Any:
        rows = int(info["rows"])
        cols = int(info["cols"])
        block_size = int(info["block_size"])
        pad = int(info.get("pad", 0))
        tensor_seed = int(info["tensor_seed"])

        idx = fetch_tensor(info["idx_key"]).to(torch_mod.long)
        gamma = fetch_tensor(info["gamma_key"]).to(torch_mod.float32)
        rot = cls._orthogonal_matrix(block_size, tensor_seed, torch_mod)

        y_hat = codebook[idx]
        u_hat = torch_mod.matmul(y_hat, rot.T)
        u_rec = u_hat

        qjl_key = info.get("qjl_sign_key")
        rn_key = info.get("residual_norm_key")
        if method == "turboquant-prod" and qjl_key and rn_key:
            qjl = fetch_tensor(qjl_key).to(torch_mod.float32)
            rn = fetch_tensor(rn_key).to(torch_mod.float32)
            s = cls._orthogonal_matrix(block_size, tensor_seed + 1_000_003, torch_mod)
            r_hat = math.sqrt(math.pi / 2.0) / float(block_size) * rn * torch_mod.matmul(qjl, s)
            u_rec = u_hat + r_hat

        x = u_rec * gamma
        x2d = x.reshape(rows, -1)
        if pad > 0:
            x2d = x2d[:, :cols]
        shape = tuple(int(v) for v in info["shape"])
        return x2d.reshape(shape).to(dtype=out_dtype).contiguous()

    @classmethod
    def _load_quantized_into_model(
        cls, *, model: Any, model_dir: str, torch_mod: Any
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        from safetensors import safe_open

        manifest_path = os.path.join(model_dir, "quant_manifest.json")
        with open(manifest_path, "r", encoding="utf-8") as fp:
            manifest = json.load(fp)

        qdir = os.path.join(model_dir, "quantized")
        shards = manifest.get("shards") or []
        tensors = manifest.get("tensors") or {}
        quant = manifest.get("quantization") or {}
        method = str(quant.get("method", "turboquant-mse")).strip().lower()
        codebook_values = quant.get("codebook") or []
        codebook = torch_mod.tensor(codebook_values, dtype=torch_mod.float32)

        if not shards:
            raise RuntimeError("quantized artifact has no shard files in manifest")
        if codebook.numel() == 0:
            raise RuntimeError("quantized artifact has empty TurboQuant codebook")

        shard_index: dict[str, str] = {}
        for shard_name in shards:
            shard_path = os.path.join(qdir, shard_name)
            if not os.path.exists(shard_path):
                raise RuntimeError(f"missing quant shard file: {shard_name}")
            with safe_open(shard_path, framework="pt", device="cpu") as sf:
                for key in sf.keys():
                    shard_index[key] = shard_path

        def fetch_tensor(tensor_key: str) -> Any:
            shard_path = shard_index.get(tensor_key)
            if shard_path is None:
                raise RuntimeError(f"quant tensor key not found in shards: {tensor_key}")
            with safe_open(shard_path, framework="pt", device="cpu") as sf:
                return sf.get_tensor(tensor_key)

        target_refs: dict[str, Any] = {}
        for n, p in model.named_parameters(recurse=True):
            target_refs[n] = p
        for n, b in model.named_buffers(recurse=True):
            target_refs.setdefault(n, b)

        loaded_count = 0
        unexpected_manifest_keys: list[str] = []
        for name, info in tensors.items():
            target = target_refs.get(name)
            if target is None:
                unexpected_manifest_keys.append(name)
                continue
            kind = str(info.get("kind", "")).strip().lower()
            if kind == "raw":
                decoded = fetch_tensor(info["raw_key"])
            elif kind == "turboquant":
                decoded = cls._decode_turboquant_tensor(
                    info=info,
                    fetch_tensor=fetch_tensor,
                    method=method,
                    codebook=codebook,
                    out_dtype=target.dtype,
                    torch_mod=torch_mod,
                )
            else:
                raise RuntimeError(f"unsupported quant tensor kind: {kind} for key={name}")

            if tuple(decoded.shape) != tuple(target.shape):
                raise RuntimeError(
                    f"quant tensor shape mismatch for {name}: "
                    f"got={tuple(decoded.shape)} expected={tuple(target.shape)}"
                )
            with torch_mod.no_grad():
                target.copy_(decoded.to(dtype=target.dtype, device=target.device))
            loaded_count += 1

        missing_target_keys = [k for k in target_refs.keys() if k not in tensors]
        meta = {
            "target_keys": len(target_refs),
            "manifest_keys": len(tensors),
            "loaded_keys": loaded_count,
            "missing_target_keys": len(missing_target_keys),
            "unexpected_manifest_keys": len(unexpected_manifest_keys),
        }
        return meta, manifest

    def _ensure_loaded(self) -> tuple[Any, Any, Any]:
        with self._lock:
            if self._model is not None and self._processor is not None and self._torch is not None:
                return self._model, self._processor, self._torch

            if not self._probe():
                raise RuntimeError(self._last_error or f"{self.name} local-hf model unavailable")

            self._ensure_hf_cache_env()
            import torch
            from transformers import AutoModelForCausalLM, AutoModelForImageTextToText, AutoProcessor

            resolved = self._resolved_model_path
            device = self._select_device(torch)
            if device == "cpu" and not self._thread_limits_applied:
                # Prevent one OCR request from saturating all CPU cores and starving the API loop.
                try:
                    torch.set_num_threads(self.cpu_threads)
                except Exception:
                    pass
                try:
                    torch.set_num_interop_threads(self.interop_threads)
                except Exception:
                    pass
                self._thread_limits_applied = True
            allow_remote_code = self.trust_remote_code
            dtype = "auto" if device == "cuda" else torch.float32
            model_kwargs: dict[str, Any] = {
                "trust_remote_code": allow_remote_code,
                "local_files_only": True,
                "torch_dtype": dtype,
                "low_cpu_mem_usage": True,
            }
            model_candidates = (
                [AutoModelForCausalLM, AutoModelForImageTextToText]
                if self.profile == "paddle"
                else [AutoModelForImageTextToText, AutoModelForCausalLM]
            )

            model = None
            load_errors: list[str] = []
            quant_manifest_path = os.path.join(resolved, "quant_manifest.json")
            use_quantized = os.path.exists(quant_manifest_path)
            if use_quantized:
                from transformers import AutoConfig

                for model_cls in model_candidates:
                    try:
                        cfg = AutoConfig.from_pretrained(
                            resolved,
                            trust_remote_code=allow_remote_code,
                            local_files_only=True,
                        )
                        try:
                            model = model_cls.from_config(
                                cfg,
                                trust_remote_code=allow_remote_code,
                            ).eval()
                        except TypeError:
                            model = model_cls.from_config(cfg).eval()
                        try:
                            model = model.to(dtype=torch.float32)
                        except Exception:
                            pass
                        load_meta, _manifest = self._load_quantized_into_model(
                            model=model, model_dir=resolved, torch_mod=torch
                        )
                        if load_meta["loaded_keys"] <= 0:
                            raise RuntimeError("no quantized tensors were loaded into the model")
                        if load_meta["missing_target_keys"] > max(
                            16, load_meta["target_keys"] // 20
                        ):
                            raise RuntimeError(
                                "too many missing target tensors in quantized load: "
                                f"{load_meta['missing_target_keys']} / {load_meta['target_keys']}"
                            )
                        break
                    except Exception as exc:
                        load_errors.append(f"{model_cls.__name__}: {exc}")
            else:
                for model_cls in model_candidates:
                    try:
                        model = model_cls.from_pretrained(resolved, **model_kwargs).eval()
                        break
                    except Exception as exc:
                        load_errors.append(f"{model_cls.__name__}: {exc}")
            if model is None:
                raise RuntimeError(
                    f"{self.name} local-hf model load failed: {' | '.join(load_errors)}"
                )

            processor = AutoProcessor.from_pretrained(
                resolved,
                trust_remote_code=allow_remote_code,
                local_files_only=True,
            )
            try:
                model = model.to(device)
            except Exception:
                # Some dynamic models may already be placed by internal dispatch.
                pass

            self._model = model
            self._processor = processor
            self._torch = torch
            self._model_device = str(getattr(model, "device", device))
            return model, processor, torch

    @classmethod
    def _extract_text_from_json_like(cls, text: str) -> str:
        candidate = text.strip()
        if not candidate:
            return ""
        match = _JSON_RE.search(candidate)
        if match:
            candidate = match.group(0)
        try:
            payload = json.loads(candidate)
        except Exception:
            return ""

        texts: list[str] = []
        if isinstance(payload, dict):
            if isinstance(payload.get("text"), str):
                texts.append(payload["text"])
            if isinstance(payload.get("text"), list):
                texts.extend(str(v) for v in payload["text"])
            blocks = payload.get("blocks")
            if isinstance(blocks, list):
                for block in blocks:
                    if isinstance(block, dict) and block.get("text"):
                        texts.append(str(block["text"]))
        elif isinstance(payload, list):
            texts.extend(str(v) for v in payload)
        return "\n".join(item for item in texts if item and str(item).strip()).strip()

    @classmethod
    def _sanitize_text(cls, text: str) -> str:
        raw = text.strip()
        if not raw:
            return ""
        from_json = cls._extract_text_from_json_like(raw)
        if from_json:
            raw = from_json

        lines: list[str] = []
        for line in raw.splitlines():
            s = line.strip()
            if not s:
                continue
            if _FENCE_LINE_RE.match(s):
                continue
            token = re.sub(r"[^a-z0-9_.:+-]", "", s.lower())
            if token in _FORMAT_LABEL_TOKENS and len(s) <= 24:
                continue
            lines.append(s)
        return "\n".join(lines).strip()

    @staticmethod
    def _merge_outputs(chunks: list[str]) -> str:
        lines_out: list[str] = []
        seen: set[str] = set()
        for chunk in chunks:
            for line in str(chunk or "").splitlines():
                s = line.strip()
                if not s:
                    continue
                if s in seen:
                    continue
                seen.add(s)
                lines_out.append(s)
        return "\n".join(lines_out).strip()

    def _prompt_sequence(self, *, base_text: str) -> list[str]:
        catalog = self._prompt_catalog_for(self.profile)
        if self.task_prompt_mode == "single":
            return catalog[:1]
        if self.task_prompt_mode == "multi":
            return catalog[: self.task_prompt_max_passes]
        # adaptive
        sequence = catalog[:1]
        if len(base_text.strip()) < self.task_prompt_adaptive_min_chars:
            sequence.extend(catalog[1 : self.task_prompt_max_passes])
        return sequence[: self.task_prompt_max_passes]

    def _resolve_hint_ocr_binary(self) -> str | None:
        if self._hint_ocr_checked:
            return self._hint_ocr_binary
        self._hint_ocr_checked = True
        self._hint_ocr_binary = shutil.which("tesseract")
        if self.hint_ocr_enable and not self._hint_ocr_binary:
            logger.warning("[%s] hint OCR disabled: tesseract binary not found in PATH", self.name)
        return self._hint_ocr_binary

    @staticmethod
    def _truncate_hint_text(text: str, *, max_chars: int) -> str:
        value = str(text or "").strip()
        if len(value) <= max_chars:
            return value
        clipped = value[:max_chars]
        boundary = max(clipped.rfind("\n"), clipped.rfind(" "))
        if boundary >= int(max_chars * 0.6):
            clipped = clipped[:boundary]
        return f"{clipped.strip()} ..."

    def _extract_hint_text(self, image: Image.Image) -> str:
        if not self.hint_ocr_enable:
            return ""
        binary = self._resolve_hint_ocr_binary()
        if not binary:
            return ""
        temp_path = ""
        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                temp_path = tmp.name
            image.save(temp_path, format="PNG")
            proc = subprocess.run(
                [
                    binary,
                    temp_path,
                    "stdout",
                    "-l",
                    self.hint_ocr_langs,
                    "--oem",
                    "1",
                    "--psm",
                    "6",
                ],
                capture_output=True,
                text=True,
                timeout=self.hint_ocr_timeout_s,
                check=False,
            )
            if proc.returncode != 0 and not (proc.stdout or "").strip():
                logger.debug(
                    "[%s] hint OCR failed (rc=%s, stderr=%s)",
                    self.name,
                    proc.returncode,
                    (proc.stderr or "").strip()[:160],
                )
                return ""
            cleaned = self._sanitize_text(proc.stdout or "")
            if len(cleaned) < 4:
                return ""
            return self._truncate_hint_text(cleaned, max_chars=self.hint_ocr_max_chars)
        except Exception as exc:
            logger.debug("[%s] hint OCR error: %s", self.name, exc)
            return ""
        finally:
            if temp_path:
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

    @staticmethod
    def _compose_prompt_with_hint(prompt: str, hint_text: str) -> str:
        hint = str(hint_text or "").strip()
        if not hint:
            return prompt
        return (
            f"{prompt}\n\n"
            "Reference OCR (may contain errors). Use it only as a weak hint, "
            "prioritize the image, and fix obvious mistakes.\n"
            f"{hint}"
        )

    def _generate_with_prompt(self, image: Image.Image, *, prompt: str, max_new_tokens: int) -> str:
        model, processor, torch_mod = self._ensure_loaded()
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": prompt},
                ],
            }
        ]
        inputs = processor.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            return_dict=True,
            return_tensors="pt",
        )
        if hasattr(inputs, "to"):
            inputs = inputs.to(model.device)
        if hasattr(inputs, "pop"):
            inputs.pop("token_type_ids", None)

        with self._lock:
            with torch_mod.inference_mode():
                outputs = model.generate(
                    **inputs,
                    max_new_tokens=min(max_new_tokens, 128),
                    do_sample=False,
                    use_cache=True,
                )
        seq = outputs[0]
        prompt_len = int(inputs["input_ids"].shape[-1]) if "input_ids" in inputs else 0
        if prompt_len and getattr(seq, "shape", [0])[0] > prompt_len:
            seq = seq[prompt_len:]
        text = processor.decode(seq, skip_special_tokens=True)
        return self._sanitize_text(text)

    def _generate_text(self, image: Image.Image, *, max_new_tokens: int) -> str:
        model, _processor, _torch_mod = self._ensure_loaded()
        # Keep VLM latency bounded on CPU by capping the largest image side.
        model_device = str(getattr(model, "device", "cpu")).lower()
        max_side = self.max_side_px if "cpu" in model_device else max(self.max_side_px, 1024)
        width, height = image.size
        if max(width, height) > max_side:
            ratio = max_side / float(max(width, height))
            image = image.resize((max(1, int(width * ratio)), max(1, int(height * ratio))), Image.LANCZOS)
        hint_text = self._extract_hint_text(image)
        primary_base_prompt = self._prompt_for(self.profile)
        primary_prompt = self._compose_prompt_with_hint(primary_base_prompt, hint_text)
        primary_text = self._generate_with_prompt(
            image,
            prompt=primary_prompt,
            max_new_tokens=max_new_tokens,
        )
        prompts = self._prompt_sequence(base_text=primary_text)
        if len(prompts) <= 1:
            return primary_text

        chunks: list[str] = [primary_text] if primary_text else []
        for prompt in prompts[1:]:
            extra = self._generate_with_prompt(
                image,
                prompt=self._compose_prompt_with_hint(prompt, hint_text),
                max_new_tokens=max(32, max_new_tokens // 2),
            )
            if extra:
                chunks.append(extra)
        return self._merge_outputs(chunks)

    def warmup(self) -> bool:
        if not self.available():
            raise RuntimeError(self._last_error or f"{self.name} local-hf unavailable")
        self._ensure_loaded()
        # Run one tiny generation at activation time so first user inference is not a cold start.
        if not self._generation_warm:
            probe = Image.new("RGB", (96, 96), color=(255, 255, 255))
            try:
                _ = self._generate_text(probe, max_new_tokens=8)
            except Exception:
                # Keep activation resilient: model load success is enough for operator control.
                pass
            self._generation_warm = True
        return True

    def unload(self) -> bool:
        with self._lock:
            if self._active_inference is not None and not self._active_inference.done():
                return False
            torch_mod = self._torch
            self._model = None
            self._processor = None
            self._torch = None
            self._generation_warm = False
        try:
            if torch_mod is not None and torch_mod.cuda.is_available():
                torch_mod.cuda.empty_cache()
        except Exception:
            pass
        return True

    def infer_image(
        self,
        image_bytes: bytes,
        page_no: int = 1,
        doc_type: str | None = None,
    ) -> list[OCREngineResult]:
        del doc_type
        if not self.enabled:
            raise RuntimeError(f"{self.name} engine is disabled")
        if self.profile == "paddle" and self.paddle_official_fallback:
            return self._infer_with_paddle_official_runtime(image_bytes, page_no)

        try:
            image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        except Exception as exc:
            raise RuntimeError(f"{self.name} local-hf image decode failed: {exc}") from exc

        text = self._generate_text(image, max_new_tokens=self.max_new_tokens)
        if not text:
            raise RuntimeError(f"{self.name} local-hf returned empty OCR text")
        return [OCREngineResult(text=text, confidence=0.0, bbox=None, page_no=page_no)]

    async def infer_image_async(
        self,
        image_bytes: bytes,
        page_no: int = 1,
    ) -> list[OCREngineResult]:
        # Local VLM is CPU/GPU-heavy. Keep only one in-flight request per engine.
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
