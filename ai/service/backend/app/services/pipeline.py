"""End-to-end OCR pipeline from file bytes to domain-shaped JSON output."""

from __future__ import annotations

import asyncio
import difflib
import io
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from uuid import uuid4

logger = logging.getLogger(__name__)

import fitz
from PIL import Image
from pypdf import PdfReader

from app.schemas.infer import InferPage, InferResult, OCRBlock
from app.services.cache import ResultCache
from app.services.domain_transformer import build_domain_payload
from app.services.file_types import (
    is_image_content_type,
    is_office_content_type,
    is_pdf_content_type,
    resolve_content_type,
)
from app.services.ingestion import ingest_office_document, to_ocr_blocks
from app.services.image_processor import ImageProcessor
from app.services.metrics import MetricsStore
from app.services.ocr.router import OCREngineRouter
from app.services.structured_fields import extract_common_fields


class InferencePipeline:
    _NOISE_LINE_RE = re.compile(r"^[^\w가-힣]{1,8}$")
    _REPEAT_SYMBOL_RE = re.compile(r"([^\w가-힣])\1{3,}")
    _TABLE_RULE_RE = re.compile(r"^\s*:?-{3,}:?\s*$")
    _FORM_HINT_RE = re.compile(
        r"(name|email|phone|address|department|position|company|org|"
        r"이름|성명|소속|부서|직위|직책|연락처|이메일|주소|기관|회사)",
        re.IGNORECASE,
    )
    _VERIFY_CRITICAL_RE = re.compile(r"(\d{2,}|[/:\-]|[@#]|₩|\$|원|%)")
    _VERIFY_SANITIZE_RE = re.compile(r"[^0-9a-z가-힣]+", re.IGNORECASE)

    def __init__(
        self,
        router: OCREngineRouter,
        prefer_embedded_pdf_text: bool = False,
        image_preprocessor: ImageProcessor | None = None,
        result_cache: ResultCache | None = None,
        max_concurrency: int = 4,
        metrics: MetricsStore | None = None,
        fallback_confidence_threshold: float = 0.4,
        vlm_ocr_verify_langs: str = "kor+eng",
        vlm_ocr_verify_timeout_s: float = 1.2,
        vlm_ocr_verify_max_chars: int = 800,
    ) -> None:
        self.router = router
        self.prefer_embedded_pdf_text = prefer_embedded_pdf_text
        self.preprocessor = image_preprocessor or ImageProcessor(enabled=False)
        self.cache = result_cache
        self.metrics = metrics
        self.fallback_confidence_threshold = max(0.0, min(1.0, float(fallback_confidence_threshold)))
        self.vlm_ocr_verify_langs = str(vlm_ocr_verify_langs or "kor+eng").strip() or "kor+eng"
        self.vlm_ocr_verify_timeout_s = max(0.2, float(vlm_ocr_verify_timeout_s))
        self.vlm_ocr_verify_max_chars = max(64, int(vlm_ocr_verify_max_chars))
        self._tesseract_binary: str | None = None
        self._tesseract_checked = False
        self._semaphore = asyncio.Semaphore(max_concurrency)

    @classmethod
    def _normalize_text(cls, text: str) -> str:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        cleaned = cls._filter_noise_lines(lines)
        merged = cls._merge_short_lines(cleaned)
        return "\n".join(merged)

    @classmethod
    def _filter_noise_lines(cls, lines: list[str]) -> list[str]:
        filtered: list[str] = []
        for line in lines:
            if cls._NOISE_LINE_RE.fullmatch(line):
                continue
            if cls._REPEAT_SYMBOL_RE.search(line):
                continue
            filtered.append(line)
        return filtered

    @staticmethod
    def _merge_short_lines(lines: list[str]) -> list[str]:
        merged: list[str] = []
        idx = 0
        while idx < len(lines):
            current = lines[idx]
            if (
                idx + 1 < len(lines)
                and len(current) < 15
                and not current.endswith((".", "!", "?", ":", ";"))
            ):
                next_line = lines[idx + 1]
                current = f"{current} {next_line}".strip()
                idx += 1
            merged.append(current)
            idx += 1
        return merged

    @classmethod
    def _sanitize_verify_text(cls, text: str) -> str:
        lines: list[str] = []
        for line in str(text or "").splitlines():
            normalized = line.strip()
            if not normalized:
                continue
            lines.append(normalized)
        return "\n".join(lines).strip()

    @classmethod
    def _normalize_for_similarity(cls, text: str) -> str:
        token = cls._VERIFY_SANITIZE_RE.sub("", str(text or "").lower())
        return token.strip()

    @classmethod
    def _line_similarity(cls, left: str, right: str) -> float:
        a = cls._normalize_for_similarity(left)
        b = cls._normalize_for_similarity(right)
        if not a or not b:
            return 0.0
        return float(difflib.SequenceMatcher(None, a, b).ratio())

    @classmethod
    def _is_critical_line(cls, text: str) -> bool:
        return bool(cls._VERIFY_CRITICAL_RE.search(str(text or "")))

    @classmethod
    def _prefer_verifier_line(cls, primary: str, verifier: str) -> bool:
        p = str(primary or "").strip()
        v = str(verifier or "").strip()
        if not p or not v or p == v:
            return False
        p_digits = sum(ch.isdigit() for ch in p)
        v_digits = sum(ch.isdigit() for ch in v)
        if cls._is_critical_line(p) or cls._is_critical_line(v):
            return v_digits >= p_digits
        return len(v) >= max(4, int(len(p) * 0.9))

    @staticmethod
    def _truncate_verify_text(text: str, max_chars: int) -> str:
        value = str(text or "").strip()
        if len(value) <= max_chars:
            return value
        clipped = value[:max_chars]
        boundary = max(clipped.rfind("\n"), clipped.rfind(" "))
        if boundary >= int(max_chars * 0.6):
            clipped = clipped[:boundary]
        return f"{clipped.strip()} ..."

    def _resolve_tesseract_binary(self) -> str | None:
        if self._tesseract_checked:
            return self._tesseract_binary
        self._tesseract_checked = True
        self._tesseract_binary = shutil.which("tesseract")
        if self._tesseract_binary is None:
            logger.warning("[vlm_verify] tesseract binary not found; verification pass bypassed")
        return self._tesseract_binary

    def _extract_verifier_text(self, image_bytes: bytes) -> str:
        binary = self._resolve_tesseract_binary()
        if not binary:
            return ""
        temp_path = ""
        try:
            image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                temp_path = tmp.name
            image.save(temp_path, format="PNG")
            proc = subprocess.run(
                [
                    binary,
                    temp_path,
                    "stdout",
                    "-l",
                    self.vlm_ocr_verify_langs,
                    "--oem",
                    "1",
                    "--psm",
                    "6",
                ],
                capture_output=True,
                text=True,
                timeout=self.vlm_ocr_verify_timeout_s,
                check=False,
            )
            if proc.returncode != 0 and not (proc.stdout or "").strip():
                return ""
            cleaned = self._sanitize_verify_text(proc.stdout or "")
            if len(cleaned) < 4:
                return ""
            return self._truncate_verify_text(cleaned, max_chars=self.vlm_ocr_verify_max_chars)
        except Exception:
            return ""
        finally:
            if temp_path:
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

    @classmethod
    def _merge_vlm_text_with_verifier(cls, *, vlm_text: str, verifier_text: str) -> str:
        base_lines = [line.strip() for line in str(vlm_text or "").splitlines() if line.strip()]
        verifier_lines = [line.strip() for line in str(verifier_text or "").splitlines() if line.strip()]
        if not base_lines or not verifier_lines:
            return str(vlm_text or "").strip()

        merged: list[str] = []
        for line in base_lines:
            best_line = ""
            best_score = 0.0
            for candidate in verifier_lines:
                score = cls._line_similarity(line, candidate)
                if score > best_score:
                    best_score = score
                    best_line = candidate
            threshold = 0.45 if cls._is_critical_line(line) else 0.58
            if best_score >= threshold and cls._prefer_verifier_line(line, best_line):
                merged.append(best_line)
            else:
                merged.append(line)
        return "\n".join(merged).strip()

    def _apply_vlm_ocr_verification(
        self,
        *,
        blocks: list[OCRBlock],
        image_bytes: bytes,
    ) -> tuple[list[OCRBlock], int]:
        started = time.perf_counter()
        verifier_text = self._extract_verifier_text(image_bytes)
        if not verifier_text:
            return blocks, int((time.perf_counter() - started) * 1000)

        patched = 0
        for block in blocks:
            block_type = str(getattr(block.block_type, "value", block.block_type))
            if block_type == "table":
                continue
            original = str(block.text_corrected or block.text_raw or "").strip()
            if not original:
                continue
            merged = self._merge_vlm_text_with_verifier(
                vlm_text=original,
                verifier_text=verifier_text,
            )
            if merged and merged != original:
                block.text_raw = merged
                block.text_corrected = merged
                patched += 1

        verify_ms = int((time.perf_counter() - started) * 1000)
        if patched > 0:
            logger.info("[vlm_verify] patched_blocks=%d verify_ms=%d", patched, verify_ms)
        return blocks, verify_ms

    @staticmethod
    def _guess_content_type(filename: str, content_type: str | None) -> str:
        return resolve_content_type(filename, content_type)

    @staticmethod
    def _resolve_engine_name(engine_hint: str | None, blocks: list[OCRBlock]) -> str:
        engines: set[str] = set()
        for block in blocks:
            if block.block_id.startswith("ocr-"):
                parts = block.block_id.split("-")
                if len(parts) >= 2:
                    engines.add(parts[1])
        if len(engines) == 1:
            return next(iter(engines))
        if len(engines) > 1:
            return "mixed"
        for block in blocks:
            if block.block_id.startswith("ocr-"):
                parts = block.block_id.split("-")
                if len(parts) >= 2:
                    return parts[1]
                return engine_hint or "auto"
        if engine_hint and engine_hint != "auto":
            return engine_hint
        return "unknown"

    @staticmethod
    def _average_confidence(blocks: list[OCRBlock]) -> float:
        if not blocks:
            return 0.0
        return float(sum(float(b.confidence) for b in blocks) / max(len(blocks), 1))

    @staticmethod
    def _source_loc(page_no: int, bbox: list[float] | None) -> str:
        if bbox and len(bbox) >= 4:
            x1, y1, x2, y2 = bbox[:4]
            return f"p{page_no}:x{x1:.1f},y{y1:.1f},x{x2:.1f},y{y2:.1f}"
        return f"p{page_no}"

    @staticmethod
    def _normalize_block_type(value: str | None) -> str:
        token = str(value or "text").strip().lower()
        if token in {"text", "table", "form", "header", "footer", "title", "unknown"}:
            return token
        return "text"

    @staticmethod
    def _bbox_to_list(bbox: tuple[float, float, float, float] | list[float] | None) -> list[float] | None:
        if bbox is None:
            return None
        if isinstance(bbox, list):
            return [float(v) for v in bbox[:4]]
        if isinstance(bbox, tuple) and len(bbox) >= 4:
            return [float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])]
        return None

    @staticmethod
    def _bbox_intersects(a: list[float] | None, b: list[float] | None) -> bool:
        if not a or not b or len(a) < 4 or len(b) < 4:
            return False
        ax1, ay1, ax2, ay2 = a[:4]
        bx1, by1, bx2, by2 = b[:4]
        inter_w = max(0.0, min(ax2, bx2) - max(ax1, bx1))
        inter_h = max(0.0, min(ay2, by2) - max(ay1, by1))
        return inter_w > 0 and inter_h > 0

    @classmethod
    def _looks_like_form_text(cls, text: str) -> bool:
        t = str(text or "").strip()
        if not t:
            return False
        if cls._FORM_HINT_RE.search(t) and (":" in t or len(t) <= 120):
            return True
        if ":" in t and len(t) <= 180:
            return True
        return False

    @classmethod
    def _classify_embedded_block(
        cls,
        *,
        text: str,
        bbox: list[float] | None,
        page_height: float,
        font_max: float,
    ) -> str:
        if bbox and len(bbox) >= 4 and page_height > 0:
            y1, y2 = float(bbox[1]), float(bbox[3])
            if y1 <= page_height * 0.08:
                return "header"
            if y2 >= page_height * 0.92:
                return "footer"
        compact_len = len(text.replace("\n", " ").strip())
        if font_max >= 13.0 and compact_len <= 90:
            return "title"
        if cls._looks_like_form_text(text):
            return "form"
        return "text"

    @staticmethod
    def _extract_text_and_font_from_fitz_block(block: dict) -> tuple[str, float]:
        lines = block.get("lines")
        if not isinstance(lines, list):
            return "", 0.0
        out_lines: list[str] = []
        font_max = 0.0
        for line in lines:
            spans = line.get("spans") if isinstance(line, dict) else None
            if not isinstance(spans, list):
                continue
            parts: list[str] = []
            for span in spans:
                if not isinstance(span, dict):
                    continue
                s = str(span.get("text", "") or "")
                if s:
                    parts.append(s)
                try:
                    font_max = max(font_max, float(span.get("size", 0.0) or 0.0))
                except Exception:
                    pass
            line_text = "".join(parts).strip()
            if line_text:
                out_lines.append(line_text)
        return "\n".join(out_lines).strip(), font_max

    @classmethod
    def _normalize_table_rows(cls, rows: list[list[str]]) -> list[list[str]]:
        valid = [row for row in rows if any(cell.strip() for cell in row)]
        if not valid:
            return []
        width = max(len(row) for row in valid)
        if width < 2:
            return []
        return [row + [""] * (width - len(row)) for row in valid]

    @classmethod
    def _parse_table_matrix(cls, text: str) -> list[list[str]] | None:
        lines = [line.rstrip() for line in str(text or "").splitlines() if line.strip()]
        if len(lines) < 2:
            return None

        pipe_rows: list[list[str]] = []
        pipe_candidates = [line for line in lines if "|" in line]
        if len(pipe_candidates) >= 2:
            for line in pipe_candidates:
                row = line.strip().strip("|")
                cells = [cell.strip() for cell in row.split("|")]
                if len(cells) < 2:
                    continue
                if cells and all(cls._TABLE_RULE_RE.fullmatch(cell or "") for cell in cells):
                    continue
                pipe_rows.append(cells)
            normalized = cls._normalize_table_rows(pipe_rows)
            if len(normalized) >= 2:
                return normalized

        tab_rows: list[list[str]] = []
        tab_candidates = [line for line in lines if "\t" in line]
        if len(tab_candidates) >= 2:
            for line in tab_candidates:
                cells = [cell.strip() for cell in line.split("\t")]
                if len(cells) >= 2:
                    tab_rows.append(cells)
            normalized = cls._normalize_table_rows(tab_rows)
            if len(normalized) >= 2:
                return normalized

        return None

    def _cache_scope(
        self,
        *,
        content_type: str,
        engine_hint: str | None,
        ) -> str:
        return f"{content_type}|{engine_hint or 'auto'}|embedded={self.prefer_embedded_pdf_text}"

    @staticmethod
    def _page_summaries(blocks: list[OCRBlock], page_count: int) -> list[InferPage]:
        by_page: dict[int, list[OCRBlock]] = {}
        for b in blocks:
            by_page.setdefault(int(b.page_no), []).append(b)
        pages: list[InferPage] = []
        for page_no in range(1, max(1, int(page_count)) + 1):
            page_blocks = by_page.get(page_no, [])
            types = sorted({str(block.block_type) for block in page_blocks})
            table_cells = sum(1 for block in page_blocks if str(block.block_type) == "table")
            pages.append(
                InferPage(
                    page_no=page_no,
                    block_count=len(page_blocks),
                    table_cell_count=table_cells,
                    block_types=types,
                )
            )
        return pages

    @staticmethod
    def _completeness_score(
        *,
        blocks: list[OCRBlock],
        page_count: int,
        missing_regions: list[str],
    ) -> float:
        if page_count <= 0:
            return 0.0
        pages_with_blocks = len({int(b.page_no) for b in blocks if (b.text_corrected or "").strip()})
        page_coverage = pages_with_blocks / float(page_count)
        non_empty_ratio = (
            sum(1 for b in blocks if (b.text_corrected or "").strip()) / float(max(1, len(blocks)))
        )
        structure_bonus = 1.0 if any(str(b.block_type) in {"table", "form"} for b in blocks) else 0.0
        missing_ratio = len(missing_regions) / float(page_count)
        score = 0.55 * page_coverage + 0.35 * non_empty_ratio + 0.10 * structure_bonus - 0.10 * missing_ratio
        return round(max(0.0, min(1.0, score)), 4)

    def process(
        self,
        *,
        filename: str,
        file_bytes: bytes,
        content_type: str | None,
        engine_hint: str | None,
        doc_id: str | None,
        vlm_ocr_verify: bool = False,
    ) -> InferResult:
        # This sync method is for worker threads and sync callers only.
        # Async routes must use `await process_async(...)`.
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(
                self.process_async(
                    filename=filename,
                    file_bytes=file_bytes,
                    content_type=content_type,
                    engine_hint=engine_hint,
                    doc_id=doc_id,
                    vlm_ocr_verify=vlm_ocr_verify,
                )
            )
        raise RuntimeError(
            "InferencePipeline.process() cannot be called from a running event loop. "
            "Use `await InferencePipeline.process_async(...)` instead."
        )

    async def process_async(
        self,
        *,
        filename: str,
        file_bytes: bytes,
        content_type: str | None,
        engine_hint: str | None,
        doc_id: str | None,
        vlm_ocr_verify: bool = False,
    ) -> InferResult:
        resolved_content_type = resolve_content_type(filename, content_type, file_bytes)
        cache_scope = self._cache_scope(
            content_type=resolved_content_type,
            engine_hint=engine_hint,
        )

        # Cache check
        if self.cache:
            cached = self.cache.get(file_bytes, scope=cache_scope)
            if cached:
                logger.info("[cache_hit] file=%s doc_id=%s", filename, cached.get("doc_id", "?"))
                if self.metrics:
                    self.metrics.inc("cache_hit_total")
                return InferResult(**cached)
            if self.metrics:
                self.metrics.inc("cache_miss_total")

        resolved_doc_id = doc_id or str(uuid4())

        logger.info(
            "[infer_start] file=%s size=%dB engine=%s doc_id=%s",
            filename, len(file_bytes), engine_hint or "auto", resolved_doc_id,
        )

        try:
            result = await self._process_async(
                filename=filename,
                file_bytes=file_bytes,
                content_type=resolved_content_type,
                engine_hint=engine_hint,
                doc_id=resolved_doc_id,
                vlm_ocr_verify=vlm_ocr_verify,
            )
        except Exception as exc:
            logger.error("[infer_error] file=%s error=%s", filename, exc)
            raise

        logger.info(
            "[infer_done] file=%s engine=%s confidence=%.2f blocks=%d latency_ms=%d doc_type=%s",
            filename, result.engine_used, result.confidence,
            len(result.blocks), result.latency_ms, result.domain.doc_type,
        )

        if self.cache:
            self.cache.set(file_bytes, result.model_dump(), scope=cache_scope)
        if self.metrics:
            self.metrics.observe("ocr_confidence", float(result.confidence))
            self.metrics.observe("ocr_blocks_per_document", float(len(result.blocks)))
            if result.engine_used not in {"embedded-pdf-text", "mixed"}:
                self.metrics.observe(
                    f"ocr_engine_latency_seconds_{result.engine_used}",
                    float(result.step_timings.get("ocr_ms", 0)) / 1000.0,
                )

        return result

    async def _process_async(
        self,
        *,
        filename: str,
        file_bytes: bytes,
        content_type: str,
        engine_hint: str | None,
        doc_id: str,
        vlm_ocr_verify: bool = False,
    ) -> InferResult:
        started = time.perf_counter()
        blocks: list[OCRBlock] = []
        preprocessing_ms = 0
        ocr_ms = 0
        ocr_verify_ms = 0
        page_count = 1
        missing_regions: list[str] = []

        if is_pdf_content_type(content_type) or filename.lower().endswith(".pdf"):
            blocks, page_stats = await self._process_pdf_async(
                engine_hint=engine_hint,
                file_bytes=file_bytes,
                vlm_ocr_verify=vlm_ocr_verify,
            )
            preprocessing_ms = page_stats.get("preprocessing_ms", 0)
            ocr_ms = page_stats.get("ocr_ms", 0)
            ocr_verify_ms = page_stats.get("ocr_verify_ms", 0)
            page_count = int(page_stats.get("page_count", 1) or 1)
            missing_regions = list(page_stats.get("missing_regions", []) or [])
        elif is_image_content_type(content_type):
            pre_started = time.perf_counter()
            processed = self.preprocessor.preprocess(file_bytes)
            preprocessing_ms = int((time.perf_counter() - pre_started) * 1000)
            blocks, ocr_ms, ocr_verify_ms = await self._infer_image_with_routing(
                image_bytes=processed,
                page_no=1,
                engine_hint=engine_hint,
                vlm_verify_with_ocr=vlm_ocr_verify,
            )
            page_count = 1
            if not blocks:
                missing_regions = ["p1:no-ocr-text"]
        elif is_office_content_type(content_type):
            ingested = ingest_office_document(filename=filename, content_type=content_type, payload=file_bytes)
            blocks = to_ocr_blocks(ingested.region_blocks)
            page_count = max(1, len(ingested.page_units))
            preprocessing_ms = 0
            ocr_ms = 0
            if not blocks:
                missing_regions = [f"p{p.page_no}:no-extractable-content" for p in ingested.page_units] or [
                    "p1:no-extractable-content"
                ]
        else:
            raise ValueError("Unsupported file type")

        post_started = time.perf_counter()
        raw_text = "\n".join(b.text_raw for b in blocks if b.text_raw.strip())
        corrected_text = self._normalize_text(raw_text)
        confidence = round(sum(b.confidence for b in blocks) / max(len(blocks), 1), 4)
        postprocess_ms = int((time.perf_counter() - post_started) * 1000)

        transform_started = time.perf_counter()
        domain = build_domain_payload(corrected_text, title_hint=filename)
        common_fields = extract_common_fields(blocks, corrected_text)
        if common_fields.get("values"):
            domain.fields.setdefault("common", {})
            if isinstance(domain.fields["common"], dict):
                domain.fields["common"].update(common_fields["values"])
            else:
                domain.fields["common"] = common_fields["values"]
        if common_fields.get("pairs"):
            domain.fields["kv_pairs"] = common_fields["pairs"]
        transform_ms = int((time.perf_counter() - transform_started) * 1000)
        latency_ms = int((time.perf_counter() - started) * 1000)
        pages = self._page_summaries(blocks, page_count=page_count)
        completeness_score = self._completeness_score(
            blocks=blocks,
            page_count=page_count,
            missing_regions=missing_regions,
        )

        return InferResult(
            doc_id=doc_id,
            filename=filename,
            content_type=content_type,
            engine_used=self._resolve_engine_name(engine_hint, blocks),
            confidence=confidence,
            raw_text=raw_text,
            corrected_text=corrected_text,
            blocks=blocks,
            domain=domain,
            latency_ms=latency_ms,
            page_count=page_count,
            pages=pages,
            completeness_score=completeness_score,
            missing_regions=missing_regions,
            step_timings={
                "preprocessing_ms": preprocessing_ms,
                "ocr_ms": ocr_ms,
                "ocr_verify_ms": ocr_verify_ms,
                "postprocess_ms": postprocess_ms,
                "transform_ms": transform_ms,
            },
        )

    async def _process_pdf_async(
        self,
        *,
        engine_hint: str | None,
        file_bytes: bytes,
        vlm_ocr_verify: bool = False,
    ) -> tuple[list[OCRBlock], dict[str, int]]:
        embedded_blocks, missing_pages, total_pages = self._extract_embedded_pdf_blocks(file_bytes)
        embedded_chars = sum(len(block.text_corrected) for block in embedded_blocks)
        full_embedded_coverage = total_pages > 0 and len(missing_pages) == 0

        # Automatic fast path for digital PDFs.
        if full_embedded_coverage and embedded_chars > 0:
            return embedded_blocks, {
                "preprocessing_ms": 0,
                "ocr_ms": 0,
                "ocr_verify_ms": 0,
                "page_count": total_pages,
                "missing_regions": [],
            }

        # Operator can prefer embedded text whenever available.
        if self.prefer_embedded_pdf_text and embedded_blocks and not missing_pages:
            return embedded_blocks, {
                "preprocessing_ms": 0,
                "ocr_ms": 0,
                "ocr_verify_ms": 0,
                "page_count": total_pages,
                "missing_regions": [],
            }

        # VLM OCR path — only missing pages if embedded extraction already covered some pages.
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        page_images: list[tuple[int, bytes]] = []
        target_dpi = float(getattr(self.preprocessor, "target_dpi", 300))
        render_scale = max(1.0, min(6.0, target_dpi / 72.0))
        for i in range(doc.page_count):
            page_no = i + 1
            if embedded_blocks and page_no not in missing_pages:
                continue
            page = doc.load_page(i)
            pix = page.get_pixmap(matrix=fitz.Matrix(render_scale, render_scale), alpha=False)
            page_images.append((page_no, pix.tobytes("png")))
        doc.close()

        if not page_images:
            unresolved = sorted(missing_pages)
            return embedded_blocks, {
                "preprocessing_ms": 0,
                "ocr_ms": 0,
                "ocr_verify_ms": 0,
                "page_count": total_pages,
                "missing_regions": [f"p{p}:no-extractable-content" for p in unresolved],
            }

        async def _process_one(page_no: int, img_bytes: bytes) -> tuple[list[OCRBlock], int, int, int]:
            async with self._semaphore:
                pre_started = time.perf_counter()
                processed = self.preprocessor.preprocess(img_bytes)
                pre_ms = int((time.perf_counter() - pre_started) * 1000)
                blocks, page_ocr_ms, page_verify_ms = await self._infer_image_with_routing(
                    image_bytes=processed,
                    page_no=page_no,
                    engine_hint=engine_hint,
                    vlm_verify_with_ocr=vlm_ocr_verify,
                )
                return blocks, pre_ms, page_ocr_ms, page_verify_ms

        results = await asyncio.gather(
            *[_process_one(pno, img) for pno, img in page_images]
        )
        ocr_blocks = [block for page_blocks, _pre_ms, _ocr_ms, _verify_ms in results for block in page_blocks]
        merged_blocks = embedded_blocks + ocr_blocks
        merged_blocks.sort(key=lambda block: (block.page_no, int(block.reading_order or 10_000)))
        total_pre_ms = sum(pre_ms for _blocks, pre_ms, _ocr_ms, _verify_ms in results)
        total_ocr_ms = sum(ocr_time for _blocks, _pre_ms, ocr_time, _verify_ms in results)
        total_verify_ms = sum(verify_time for _blocks, _pre_ms, _ocr_ms, verify_time in results)
        ocr_pages = {int(b.page_no) for b in ocr_blocks}
        unresolved = sorted(int(p) for p in missing_pages if int(p) not in ocr_pages)
        return merged_blocks, {
            "preprocessing_ms": total_pre_ms,
            "ocr_ms": total_ocr_ms,
            "ocr_verify_ms": total_verify_ms,
            "page_count": total_pages,
            "missing_regions": [f"p{p}:ocr-empty" for p in unresolved],
        }

    def _extract_embedded_pdf_blocks(
        self, file_bytes: bytes
    ) -> tuple[list[OCRBlock], set[int], int]:
        blocks: list[OCRBlock] = []
        missing_pages: set[int] = set()

        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
        except Exception:
            doc = None

        if doc is not None:
            total_pages = int(doc.page_count)
            for page_idx in range(total_pages):
                page_no = page_idx + 1
                page = doc.load_page(page_idx)
                page_height = float(page.rect.height or 0.0)
                reading_order = 0
                extracted_for_page = 0
                table_bboxes: list[list[float]] = []

                # 1) Table-first extraction for structure preservation.
                try:
                    finder = page.find_tables()
                    tables = list(getattr(finder, "tables", []) or [])
                except Exception:
                    tables = []

                for t_idx, table in enumerate(tables, start=1):
                    table_id = f"p{page_no}-tbl{t_idx}"
                    table_bbox = self._bbox_to_list(getattr(table, "bbox", None))
                    if table_bbox:
                        table_bboxes.append(table_bbox)
                    rows = []
                    try:
                        rows = table.extract() or []
                    except Exception:
                        rows = []
                    row_meta = list(getattr(table, "rows", []) or [])
                    for row_idx, row in enumerate(rows, start=1):
                        if not isinstance(row, list):
                            continue
                        for col_idx, cell in enumerate(row, start=1):
                            raw_cell = str(cell or "").strip()
                            normalized = self._normalize_text(raw_cell)
                            if not normalized:
                                continue
                            reading_order += 1
                            cell_bbox = None
                            if row_idx - 1 < len(row_meta):
                                row_cells = getattr(row_meta[row_idx - 1], "cells", None)
                                if isinstance(row_cells, list) and col_idx - 1 < len(row_cells):
                                    cell_bbox = self._bbox_to_list(row_cells[col_idx - 1])
                            if cell_bbox is None:
                                cell_bbox = table_bbox
                            blocks.append(
                                OCRBlock(
                                    block_id=f"{table_id}-r{row_idx}c{col_idx}",
                                    page_no=page_no,
                                    text_raw=raw_cell,
                                    text_corrected=normalized,
                                    confidence=1.0,
                                    bbox=cell_bbox,
                                    source_loc=self._source_loc(page_no, cell_bbox),
                                    block_type="table",
                                    reading_order=reading_order,
                                    table_id=table_id,
                                    row_idx=row_idx,
                                    col_idx=col_idx,
                                    rowspan=1,
                                    colspan=1,
                                )
                            )
                            extracted_for_page += 1

                # 2) Text block extraction with layout classification.
                try:
                    page_dict = page.get_text("dict")
                except Exception:
                    page_dict = {}
                raw_blocks = page_dict.get("blocks", []) if isinstance(page_dict, dict) else []
                for raw in raw_blocks:
                    if not isinstance(raw, dict):
                        continue
                    if int(raw.get("type", 1)) != 0:
                        continue
                    block_bbox = self._bbox_to_list(raw.get("bbox"))
                    if any(self._bbox_intersects(block_bbox, tbb) for tbb in table_bboxes):
                        continue
                    block_text, font_max = self._extract_text_and_font_from_fitz_block(raw)
                    normalized = self._normalize_text(block_text)
                    if not normalized:
                        continue
                    reading_order += 1
                    btype = self._classify_embedded_block(
                        text=normalized,
                        bbox=block_bbox,
                        page_height=page_height,
                        font_max=font_max,
                    )
                    blocks.append(
                        OCRBlock(
                            block_id=f"p{page_no}-b{reading_order}",
                            page_no=page_no,
                            text_raw=block_text,
                            text_corrected=normalized,
                            confidence=1.0,
                            bbox=block_bbox,
                            source_loc=self._source_loc(page_no, block_bbox),
                            block_type=btype,
                            reading_order=reading_order,
                        )
                    )
                    extracted_for_page += 1

                if extracted_for_page == 0:
                    missing_pages.add(page_no)
            doc.close()
            return blocks, missing_pages, total_pages

        # fallback parser if fitz dict parsing failed entirely
        try:
            reader = PdfReader(io.BytesIO(file_bytes))
        except Exception:
            return [], set(), 0

        total_pages = len(reader.pages)
        for page_idx, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if not text:
                missing_pages.add(page_idx)
                continue
            line_order = 0
            for line_idx, line in enumerate(text.splitlines(), start=1):
                normalized = self._normalize_text(line)
                if not normalized:
                    continue
                line_order += 1
                blocks.append(
                    OCRBlock(
                        block_id=f"p{page_idx}-t{line_idx}",
                        page_no=page_idx,
                        text_raw=line,
                        text_corrected=normalized,
                        confidence=1.0,
                        bbox=None,
                        source_loc=f"p{page_idx}",
                        block_type="text",
                        reading_order=line_order,
                    )
                )
            if line_order == 0:
                missing_pages.add(page_idx)
        return blocks, missing_pages, total_pages

    async def _infer_image_with_routing(
        self,
        *,
        image_bytes: bytes,
        page_no: int,
        engine_hint: str | None,
        vlm_verify_with_ocr: bool = False,
    ) -> tuple[list[OCRBlock], int, int]:
        primary_engine = self.router.select(engine_hint, image_bytes=image_bytes, text_hint=None)
        primary_blocks, primary_ocr_ms, primary_verify_ms = await self._process_image_async(
            engine=primary_engine,
            image_bytes=image_bytes,
            page_no=page_no,
            vlm_verify_with_ocr=vlm_verify_with_ocr,
        )
        primary_conf = self._average_confidence(primary_blocks)

        if engine_hint and engine_hint in {"paddle", "glm"}:
            return primary_blocks, primary_ocr_ms, primary_verify_ms

        fallback_engine = self.router.select_with_fallback(
            primary_engine=primary_engine.name,
            primary_confidence=primary_conf,
            threshold=self.fallback_confidence_threshold,
            image_bytes=image_bytes,
            text_hint="\n".join(block.text_corrected for block in primary_blocks),
        )
        if fallback_engine is None:
            return primary_blocks, primary_ocr_ms, primary_verify_ms

        fallback_blocks, fallback_ocr_ms, fallback_verify_ms = await self._process_image_async(
            engine=fallback_engine,
            image_bytes=image_bytes,
            page_no=page_no,
            vlm_verify_with_ocr=vlm_verify_with_ocr,
        )
        fallback_conf = self._average_confidence(fallback_blocks)
        if fallback_conf > primary_conf:
            logger.info(
                "[router_fallback] page=%d primary=%s(%.3f) -> fallback=%s(%.3f)",
                page_no,
                primary_engine.name,
                primary_conf,
                fallback_engine.name,
                fallback_conf,
            )
            return (
                fallback_blocks,
                primary_ocr_ms + fallback_ocr_ms,
                primary_verify_ms + fallback_verify_ms,
            )
        return (
            primary_blocks,
            primary_ocr_ms + fallback_ocr_ms,
            primary_verify_ms + fallback_verify_ms,
        )

    async def _process_image_async(
        self,
        *,
        engine,
        image_bytes: bytes,
        page_no: int,
        vlm_verify_with_ocr: bool = False,
    ) -> tuple[list[OCRBlock], int, int]:
        ocr_started = time.perf_counter()
        items = await engine.infer_image_async(image_bytes=image_bytes, page_no=page_no)
        blocks: list[OCRBlock] = []
        reading_order = 0
        for idx, item in enumerate(items, start=1):
            raw_text = str(item.text or "")
            text = self._normalize_text(raw_text)
            if not text:
                continue
            block_type = self._normalize_block_type(getattr(item, "block_type", "text"))
            source_loc = self._source_loc(page_no, item.bbox)
            table_matrix = self._parse_table_matrix(raw_text) if block_type in {"text", "table"} else None

            if block_type == "table" or table_matrix is not None:
                table_id = str(getattr(item, "table_id", "") or f"ocr-{engine.name}-p{page_no}-t{idx}")
                matrix = table_matrix if table_matrix is not None else [[text]]
                for row_idx, row in enumerate(matrix, start=1):
                    for col_idx, cell in enumerate(row, start=1):
                        cell_text = self._normalize_text(cell)
                        if not cell_text:
                            continue
                        reading_order += 1
                        blocks.append(
                            OCRBlock(
                                block_id=f"{table_id}-r{row_idx}c{col_idx}",
                                page_no=page_no,
                                text_raw=cell.strip(),
                                text_corrected=cell_text,
                                confidence=float(item.confidence),
                                bbox=item.bbox,
                                source_loc=f"{source_loc}:r{row_idx}c{col_idx}",
                                block_type="table",
                                parent_block_id=getattr(item, "parent_block_id", None),
                                reading_order=getattr(item, "reading_order", None) or reading_order,
                                table_id=table_id,
                                row_idx=getattr(item, "row_idx", None) or row_idx,
                                col_idx=getattr(item, "col_idx", None) or col_idx,
                                rowspan=getattr(item, "rowspan", None) or 1,
                                colspan=getattr(item, "colspan", None) or 1,
                            )
                        )
                continue

            reading_order += 1
            blocks.append(
                OCRBlock(
                    block_id=f"ocr-{engine.name}-p{page_no}-b{idx}",
                    page_no=page_no,
                    text_raw=raw_text,
                    text_corrected=text,
                    confidence=float(item.confidence),
                    bbox=item.bbox,
                    source_loc=source_loc,
                    block_type=block_type,
                    parent_block_id=getattr(item, "parent_block_id", None),
                    reading_order=getattr(item, "reading_order", None) or reading_order,
                    table_id=getattr(item, "table_id", None),
                    row_idx=getattr(item, "row_idx", None),
                    col_idx=getattr(item, "col_idx", None),
                    rowspan=getattr(item, "rowspan", None),
                    colspan=getattr(item, "colspan", None),
                )
            )
        ocr_ms = int((time.perf_counter() - ocr_started) * 1000)
        verify_ms = 0
        if vlm_verify_with_ocr and blocks:
            blocks, verify_ms = self._apply_vlm_ocr_verification(
                blocks=blocks,
                image_bytes=image_bytes,
            )
        return blocks, ocr_ms, verify_ms
