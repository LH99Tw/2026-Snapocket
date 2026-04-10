"""Schema definitions for OCR inference inputs/outputs."""

from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field


class EngineHint(str, Enum):
    auto = "auto"
    paddle = "paddle"
    glm = "glm"


class BlockType(str, Enum):
    text = "text"
    table = "table"
    form = "form"
    header = "header"
    footer = "footer"
    title = "title"
    unknown = "unknown"


class OCRBlock(BaseModel):
    block_id: str
    page_no: int
    text_raw: str
    text_corrected: str
    confidence: float = 0.0
    bbox: list[float] | None = None
    source_loc: str | None = None
    block_type: BlockType = BlockType.text
    parent_block_id: str | None = None
    reading_order: int | None = None
    table_id: str | None = None
    row_idx: int | None = None
    col_idx: int | None = None
    rowspan: int | None = None
    colspan: int | None = None


class DomainEntities(BaseModel):
    dates: list[str] = Field(default_factory=list)
    amounts: list[str] = Field(default_factory=list)
    subjects: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    persons: list[str] = Field(default_factory=list)
    orgs: list[str] = Field(default_factory=list)
    phones: list[str] = Field(default_factory=list)
    emails: list[str] = Field(default_factory=list)


class DomainPayload(BaseModel):
    doc_type: str
    title: str | None = None
    summary: str | None = None
    entities: DomainEntities
    fields: dict = Field(default_factory=dict)


class InferPage(BaseModel):
    page_no: int
    block_count: int = 0
    table_cell_count: int = 0
    block_types: list[str] = Field(default_factory=list)


class InferResult(BaseModel):
    doc_id: str
    filename: str
    content_type: str
    engine_used: str
    confidence: float
    raw_text: str
    corrected_text: str
    blocks: list[OCRBlock]
    domain: DomainPayload
    latency_ms: int
    page_count: int = 1
    pages: list[InferPage] = Field(default_factory=list)
    completeness_score: float = 0.0
    missing_regions: list[str] = Field(default_factory=list)
    step_timings: dict[str, int] = Field(default_factory=dict)
