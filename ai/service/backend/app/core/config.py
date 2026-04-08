"""Environment-driven runtime settings for the API service."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


_DEFAULT_ALLOWED_UPLOAD_TYPES = (
    "application/pdf,image/png,image/jpeg,image/webp,image/tiff,"
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document,"
    "application/vnd.openxmlformats-officedocument.presentationml.presentation,"
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
_DEFAULT_ALLOWED_UPLOAD_EXTS = ".pdf,.png,.jpg,.jpeg,.webp,.tif,.tiff,.docx,.pptx,.xlsx"


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "Snapocket ML/AIOps API")
    app_env: str = os.getenv("APP_ENV", "dev")
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8080"))

    api_key: str = os.getenv("AIOPS_API_KEY", "")
    ops_basic_user: str = os.getenv("OPS_BASIC_USER", "")
    ops_basic_pass: str = os.getenv("OPS_BASIC_PASS", "")
    aiops_server_secret_key: str = os.getenv("AIOPS_SERVER_SECRET_KEY", "")
    require_api_key: bool = _as_bool(os.getenv("AIOPS_REQUIRE_API_KEY"), True)
    require_ops_basic_auth: bool = _as_bool(os.getenv("AIOPS_REQUIRE_OPS_BASIC_AUTH"), True)
    allowed_clients_raw: str = os.getenv(
        "AIOPS_ALLOWED_CLIENTS",
        "127.0.0.1/32,::1/128,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16",
    )
    trust_x_forwarded_for: bool = _as_bool(os.getenv("AIOPS_TRUST_X_FORWARDED_FOR"), False)
    allow_public_server_endpoints: bool = _as_bool(os.getenv("ALLOW_PUBLIC_SERVER_ENDPOINTS"), False)
    allow_hostname_server_endpoints: bool = _as_bool(os.getenv("ALLOW_HOSTNAME_SERVER_ENDPOINTS"), False)
    allow_zrok_server_endpoints: bool = _as_bool(os.getenv("ALLOW_ZROK_SERVER_ENDPOINTS"), True)

    default_engine: str = os.getenv("DEFAULT_ENGINE", "auto")
    paddle_enable: bool = _as_bool(os.getenv("PADDLE_ENABLE"), True)
    glm_enable: bool = _as_bool(os.getenv("GLM_ENABLE"), True)

    llm_base_url: str = os.getenv("LLM_BASE_URL", os.getenv("OLLAMA_BASE_URL", "http://llama-server:8080"))
    llm_model_paddle: str = os.getenv(
        "LLM_MODEL_PADDLE", os.getenv("OLLAMA_MODEL_PADDLE", "PaddleOCR-VL-1.5-BF16.gguf")
    )
    llm_model_glm: str = os.getenv(
        "LLM_MODEL_GLM", os.getenv("OLLAMA_MODEL_GLM", "PaddleOCR-VL-1.5-BF16.gguf")
    )
    llm_request_timeout_s: float = float(
        os.getenv("LLM_REQUEST_TIMEOUT_S", os.getenv("OLLAMA_REQUEST_TIMEOUT_S", "120"))
    )
    llm_keep_alive: str = os.getenv("LLM_KEEP_ALIVE", os.getenv("OLLAMA_KEEP_ALIVE", "10m"))
    llm_temperature: float = float(os.getenv("LLM_TEMPERATURE", os.getenv("OLLAMA_TEMPERATURE", "0")))
    llm_image_max_side_px: int = int(
        os.getenv("LLM_IMAGE_MAX_SIDE_PX", os.getenv("OLLAMA_IMAGE_MAX_SIDE_PX", "1536"))
    )
    llm_max_tokens: int = int(os.getenv("LLM_MAX_TOKENS", os.getenv("OLLAMA_MAX_TOKENS", "96")))
    dispatch_upstream_timeout_s: float = float(os.getenv("DISPATCH_UPSTREAM_TIMEOUT_S", "180"))

    # VLM OCR result verification with Tesseract
    local_model_hint_ocr_enable: bool = _as_bool(os.getenv("LOCAL_MODEL_HINT_OCR_ENABLE"), True)
    local_model_hint_ocr_langs: str = os.getenv("LOCAL_MODEL_HINT_OCR_LANGS", "kor+eng")
    local_model_hint_ocr_timeout_s: float = float(
        os.getenv("LOCAL_MODEL_HINT_OCR_TIMEOUT_S", "1.2")
    )
    local_model_hint_ocr_max_chars: int = int(
        os.getenv("LOCAL_MODEL_HINT_OCR_MAX_CHARS", "800")
    )

    playground_timeout_s: float = float(os.getenv("PLAYGROUND_TIMEOUT_S", "60"))

    max_upload_mb: int = int(os.getenv("MAX_UPLOAD_MB", "25"))
    allowed_upload_types_raw: str = os.getenv(
        "ALLOWED_UPLOAD_TYPES",
        _DEFAULT_ALLOWED_UPLOAD_TYPES,
    )
    allowed_upload_exts_raw: str = os.getenv("ALLOWED_UPLOAD_EXTS", _DEFAULT_ALLOWED_UPLOAD_EXTS)
    prefer_embedded_pdf_text: bool = _as_bool(os.getenv("PREFER_EMBEDDED_PDF_TEXT"), False)
    ocr_concurrency: int = int(os.getenv("OCR_CONCURRENCY", "1"))

    image_preprocess: bool = _as_bool(os.getenv("IMAGE_PREPROCESS"), True)
    image_target_dpi: int = int(os.getenv("IMAGE_TARGET_DPI", "300"))
    image_assumed_input_dpi: int = int(os.getenv("IMAGE_ASSUMED_INPUT_DPI", "144"))
    image_apply_otsu: bool = _as_bool(os.getenv("IMAGE_APPLY_OTSU"), True)
    image_max_side_px: int = int(os.getenv("IMAGE_MAX_SIDE_PX", "4200"))
    ocr_fallback_confidence_threshold: float = float(
        os.getenv("OCR_FALLBACK_CONFIDENCE_THRESHOLD", "0.4")
    )

    database_enable: bool = _as_bool(os.getenv("DATABASE_ENABLE"), True)
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./data/aiops.db")
    redis_enable: bool = _as_bool(os.getenv("REDIS_ENABLE"), False)
    redis_url: str = os.getenv("REDIS_URL", "redis://redis:6379/0")
    readiness_timeout_s: float = float(os.getenv("READINESS_TIMEOUT_S", "1.5"))

    job_timeout_s: float = float(os.getenv("JOB_TIMEOUT_S", "180"))
    job_max_retries: int = int(os.getenv("JOB_MAX_RETRIES", "1"))
    job_retry_backoff_s: float = float(os.getenv("JOB_RETRY_BACKOFF_S", "1.5"))
    job_queue_backend: str = os.getenv("JOB_QUEUE_BACKEND", "memory")
    idempotency_ttl_s: int = int(os.getenv("IDEMPOTENCY_TTL_S", "86400"))

    model_probe_enable: bool = _as_bool(os.getenv("MODEL_PROBE_ENABLE"), True)
    model_probe_interval_s: float = float(os.getenv("MODEL_PROBE_INTERVAL_S", "30"))
    model_availability_ttl_s: float = float(os.getenv("MODEL_AVAILABILITY_TTL_S", "15"))

    malware_scan_enable: bool = _as_bool(os.getenv("MALWARE_SCAN_ENABLE"), False)
    malware_scan_command: str = os.getenv("MALWARE_SCAN_COMMAND", "").strip()
    malware_scan_timeout_s: float = float(os.getenv("MALWARE_SCAN_TIMEOUT_S", "5"))

    @property
    def allowed_upload_types(self) -> set[str]:
        return {
            token.strip().lower()
            for token in self.allowed_upload_types_raw.split(",")
            if token.strip()
        }

    @property
    def allowed_upload_exts(self) -> set[str]:
        return {
            (token.strip().lower() if token.strip().startswith(".") else f".{token.strip().lower()}")
            for token in self.allowed_upload_exts_raw.split(",")
            if token.strip()
        }


def load_settings() -> Settings:
    return Settings(
        app_name=os.getenv("APP_NAME", "Snapocket ML/AIOps API"),
        app_env=os.getenv("APP_ENV", "dev"),
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8080")),
        api_key=os.getenv("AIOPS_API_KEY", ""),
        ops_basic_user=os.getenv("OPS_BASIC_USER", ""),
        ops_basic_pass=os.getenv("OPS_BASIC_PASS", ""),
        aiops_server_secret_key=os.getenv("AIOPS_SERVER_SECRET_KEY", ""),
        require_api_key=_as_bool(os.getenv("AIOPS_REQUIRE_API_KEY"), True),
        require_ops_basic_auth=_as_bool(os.getenv("AIOPS_REQUIRE_OPS_BASIC_AUTH"), True),
        allowed_clients_raw=os.getenv(
            "AIOPS_ALLOWED_CLIENTS",
            "127.0.0.1/32,::1/128,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16",
        ),
        trust_x_forwarded_for=_as_bool(os.getenv("AIOPS_TRUST_X_FORWARDED_FOR"), False),
        allow_public_server_endpoints=_as_bool(os.getenv("ALLOW_PUBLIC_SERVER_ENDPOINTS"), False),
        allow_hostname_server_endpoints=_as_bool(os.getenv("ALLOW_HOSTNAME_SERVER_ENDPOINTS"), False),
        allow_zrok_server_endpoints=_as_bool(os.getenv("ALLOW_ZROK_SERVER_ENDPOINTS"), True),
        default_engine=os.getenv("DEFAULT_ENGINE", "auto"),
        paddle_enable=_as_bool(os.getenv("PADDLE_ENABLE"), True),
        glm_enable=_as_bool(os.getenv("GLM_ENABLE"), True),
        llm_base_url=os.getenv("LLM_BASE_URL", os.getenv("OLLAMA_BASE_URL", "http://llama-server:8080")),
        llm_model_paddle=os.getenv(
            "LLM_MODEL_PADDLE", os.getenv("OLLAMA_MODEL_PADDLE", "PaddleOCR-VL-1.5-BF16.gguf")
        ),
        llm_model_glm=os.getenv(
            "LLM_MODEL_GLM", os.getenv("OLLAMA_MODEL_GLM", "PaddleOCR-VL-1.5-BF16.gguf")
        ),
        llm_request_timeout_s=float(
            os.getenv("LLM_REQUEST_TIMEOUT_S", os.getenv("OLLAMA_REQUEST_TIMEOUT_S", "120"))
        ),
        llm_keep_alive=os.getenv("LLM_KEEP_ALIVE", os.getenv("OLLAMA_KEEP_ALIVE", "10m")),
        llm_temperature=float(os.getenv("LLM_TEMPERATURE", os.getenv("OLLAMA_TEMPERATURE", "0"))),
        llm_image_max_side_px=int(
            os.getenv("LLM_IMAGE_MAX_SIDE_PX", os.getenv("OLLAMA_IMAGE_MAX_SIDE_PX", "1536"))
        ),
        llm_max_tokens=int(os.getenv("LLM_MAX_TOKENS", os.getenv("OLLAMA_MAX_TOKENS", "96"))),
        dispatch_upstream_timeout_s=float(os.getenv("DISPATCH_UPSTREAM_TIMEOUT_S", "180")),
        local_model_hint_ocr_enable=_as_bool(os.getenv("LOCAL_MODEL_HINT_OCR_ENABLE"), True),
        local_model_hint_ocr_langs=os.getenv("LOCAL_MODEL_HINT_OCR_LANGS", "kor+eng"),
        local_model_hint_ocr_timeout_s=float(
            os.getenv("LOCAL_MODEL_HINT_OCR_TIMEOUT_S", "1.2")
        ),
        local_model_hint_ocr_max_chars=int(
            os.getenv("LOCAL_MODEL_HINT_OCR_MAX_CHARS", "800")
        ),
        playground_timeout_s=float(os.getenv("PLAYGROUND_TIMEOUT_S", "60")),
        max_upload_mb=int(os.getenv("MAX_UPLOAD_MB", "25")),
        allowed_upload_types_raw=os.getenv(
            "ALLOWED_UPLOAD_TYPES",
            _DEFAULT_ALLOWED_UPLOAD_TYPES,
        ),
        allowed_upload_exts_raw=os.getenv("ALLOWED_UPLOAD_EXTS", _DEFAULT_ALLOWED_UPLOAD_EXTS),
        prefer_embedded_pdf_text=_as_bool(os.getenv("PREFER_EMBEDDED_PDF_TEXT"), False),
        ocr_concurrency=int(os.getenv("OCR_CONCURRENCY", "1")),
        image_preprocess=_as_bool(os.getenv("IMAGE_PREPROCESS"), True),
        image_target_dpi=int(os.getenv("IMAGE_TARGET_DPI", "300")),
        image_assumed_input_dpi=int(os.getenv("IMAGE_ASSUMED_INPUT_DPI", "144")),
        image_apply_otsu=_as_bool(os.getenv("IMAGE_APPLY_OTSU"), True),
        image_max_side_px=int(os.getenv("IMAGE_MAX_SIDE_PX", "4200")),
        ocr_fallback_confidence_threshold=float(
            os.getenv("OCR_FALLBACK_CONFIDENCE_THRESHOLD", "0.4")
        ),
        database_enable=_as_bool(os.getenv("DATABASE_ENABLE"), True),
        database_url=os.getenv("DATABASE_URL", "sqlite:///./data/aiops.db"),
        redis_enable=_as_bool(os.getenv("REDIS_ENABLE"), False),
        redis_url=os.getenv("REDIS_URL", "redis://redis:6379/0"),
        readiness_timeout_s=float(os.getenv("READINESS_TIMEOUT_S", "1.5")),
        job_timeout_s=float(os.getenv("JOB_TIMEOUT_S", "180")),
        job_max_retries=int(os.getenv("JOB_MAX_RETRIES", "1")),
        job_retry_backoff_s=float(os.getenv("JOB_RETRY_BACKOFF_S", "1.5")),
        job_queue_backend=os.getenv("JOB_QUEUE_BACKEND", "memory"),
        idempotency_ttl_s=int(os.getenv("IDEMPOTENCY_TTL_S", "86400")),
        model_probe_enable=_as_bool(os.getenv("MODEL_PROBE_ENABLE"), True),
        model_probe_interval_s=float(os.getenv("MODEL_PROBE_INTERVAL_S", "30")),
        model_availability_ttl_s=float(os.getenv("MODEL_AVAILABILITY_TTL_S", "15")),
        malware_scan_enable=_as_bool(os.getenv("MALWARE_SCAN_ENABLE"), False),
        malware_scan_command=os.getenv("MALWARE_SCAN_COMMAND", "").strip(),
        malware_scan_timeout_s=float(os.getenv("MALWARE_SCAN_TIMEOUT_S", "5")),
    )
