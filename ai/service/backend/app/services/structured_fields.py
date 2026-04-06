"""Structured common-field extraction from OCR blocks and transcript text."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from app.schemas.infer import OCRBlock

_KV_SPLIT_RE = re.compile(r"\s*[:：]\s*")
_WS_RE = re.compile(r"\s+")

_CANONICAL_KEYWORDS: dict[str, tuple[str, ...]] = {
    "name": ("name", "이름", "성명", "담당자"),
    "organization": ("organization", "org", "회사", "기관", "소속"),
    "department": ("department", "dept", "부서"),
    "position": ("position", "title", "직위", "직책"),
    "phone": ("phone", "tel", "mobile", "연락처", "전화"),
    "email": ("email", "e-mail", "이메일", "메일"),
    "date": ("date", "일자", "날짜", "기한"),
    "amount": ("amount", "금액", "합계", "총액"),
    "topic": ("topic", "주제", "과제", "분야"),
}

_PHONE_RE = re.compile(r"\b\d{2,3}[-.\s]?\d{3,4}[-.\s]?\d{4}\b")
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_DATE_RE = re.compile(r"\b(?:19|20)\d{2}[./-]\d{1,2}[./-]\d{1,2}\b")
_AMOUNT_RE = re.compile(r"\b\d{1,3}(?:,\d{3})*(?:\.\d+)?\s*(?:원|KRW|USD)?\b", re.IGNORECASE)
_TABLE_HEADER_KEYS = {"항목", "값", "key", "value", "field", "label"}


def _normalize_key(value: str) -> str:
    lower = str(value or "").strip().lower()
    return re.sub(r"[^a-z0-9가-힣]", "", lower)


def _canonical_key(raw_key: str) -> str | None:
    token = _normalize_key(raw_key)
    if not token:
        return None
    for canonical, keywords in _CANONICAL_KEYWORDS.items():
        for keyword in keywords:
            if _normalize_key(keyword) and _normalize_key(keyword) in token:
                return canonical
    return None


def _clean_value(value: str) -> str:
    return _WS_RE.sub(" ", str(value or "").strip())


def _upsert_field(bucket: dict[str, Any], key: str, value: str) -> None:
    v = _clean_value(value)
    if not v:
        return
    existing = bucket.get(key)
    if existing is None:
        bucket[key] = v
        return
    if isinstance(existing, list):
        if v not in existing:
            existing.append(v)
        return
    if existing != v:
        bucket[key] = [existing, v] if v != existing else existing


def _extract_pairs_from_text_lines(text: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if ":" in line or "：" in line:
            parts = _KV_SPLIT_RE.split(line, maxsplit=1)
            if len(parts) == 2:
                k, v = parts[0].strip(), parts[1].strip()
                if k and v:
                    pairs.append((k, v))
            continue
        # Fallback pattern for OCR lines like "이름 홍길동" without a delimiter.
        tokens = [t for t in re.split(r"\s{2,}|\t+", line) if t.strip()]
        if len(tokens) >= 2:
            k = tokens[0].strip()
            v = " ".join(tokens[1:]).strip()
            if _canonical_key(k) and v:
                pairs.append((k, v))
    return pairs


def _as_block_type(block: OCRBlock) -> str:
    raw = getattr(block, "block_type", "text")
    if hasattr(raw, "value"):
        return str(raw.value).strip().lower()
    return str(raw).strip().lower()


def _extract_pairs_from_table_blocks(blocks: list[OCRBlock]) -> list[tuple[str, str]]:
    grouped: dict[str, dict[int, list[tuple[int, str]]]] = defaultdict(lambda: defaultdict(list))
    for block in blocks:
        if _as_block_type(block) != "table":
            continue
        table_id = str(block.table_id or f"p{block.page_no}-tbl-unknown").strip()
        try:
            row_idx = int(block.row_idx or 0)
            col_idx = int(block.col_idx or 0)
        except (TypeError, ValueError):
            continue
        if row_idx <= 0 or col_idx <= 0:
            continue
        grouped[table_id][row_idx].append(
            (col_idx, str(block.text_corrected or block.text_raw or "").strip())
        )

    pairs: list[tuple[str, str]] = []
    for _table_id, rows in grouped.items():
        for _row_idx, cols in rows.items():
            ordered = [text for _col, text in sorted(cols, key=lambda item: item[0]) if text]
            if len(ordered) < 2:
                continue
            row_key = ordered[0].strip()
            row_val = " ".join(cell.strip() for cell in ordered[1:] if cell.strip())
            if row_key and row_val:
                if _normalize_key(row_key) not in {_normalize_key(v) for v in _TABLE_HEADER_KEYS}:
                    pairs.append((row_key, row_val))

            # Additional parse for rows like [k, v, k2, v2, ...].
            for i in range(0, len(ordered) - 1, 2):
                k = ordered[i].strip()
                v = ordered[i + 1].strip()
                if k and v:
                    pairs.append((k, v))
    return pairs


def _extract_fallbacks(text: str, fields: dict[str, Any]) -> None:
    if "phone" not in fields:
        phones = _PHONE_RE.findall(text or "")
        if phones:
            fields["phone"] = phones[0] if len(phones) == 1 else phones
    if "email" not in fields:
        emails = _EMAIL_RE.findall(text or "")
        if emails:
            fields["email"] = emails[0] if len(emails) == 1 else emails
    if "date" not in fields:
        dates = _DATE_RE.findall(text or "")
        if dates:
            fields["date"] = dates[0] if len(dates) == 1 else dates
    if "amount" not in fields:
        amounts = [
            _clean_value(m)
            for m in _AMOUNT_RE.findall(text or "")
            if any(ch.isdigit() for ch in m)
        ]
        if amounts:
            fields["amount"] = amounts[0] if len(amounts) == 1 else amounts


def extract_common_fields(blocks: list[OCRBlock], transcript: str) -> dict[str, Any]:
    """Return normalized common fields and source key-value pairs."""
    pairs = _extract_pairs_from_table_blocks(blocks) + _extract_pairs_from_text_lines(transcript)
    common: dict[str, Any] = {}
    kv_pairs: list[dict[str, str]] = []

    for raw_key, raw_val in pairs:
        key = _canonical_key(raw_key)
        val = _clean_value(raw_val)
        if not val:
            continue
        kv_pairs.append({"key": _clean_value(raw_key), "value": val})
        if key is not None:
            _upsert_field(common, key, val)

    _extract_fallbacks(transcript, common)
    return {
        "values": common,
        "pairs": kv_pairs[:100],
    }
