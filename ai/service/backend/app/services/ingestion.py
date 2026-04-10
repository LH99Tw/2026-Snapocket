"""Typed ingestors and internal representation for multimodal documents."""

from __future__ import annotations

import io
import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from app.schemas.infer import OCRBlock
from app.services.file_types import resolve_content_type


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def _node_text(node: ET.Element) -> str:
    parts: list[str] = []
    for child in node.iter():
        if _local_name(child.tag) == "t" and child.text:
            text = child.text.strip()
            if text:
                parts.append(text)
    return " ".join(parts).strip()


def _zip_root_names(payload: bytes) -> set[str]:
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        return set(zf.namelist())


def _read_xml_from_zip(payload: bytes, name: str) -> ET.Element | None:
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            with zf.open(name) as fp:
                raw = fp.read()
    except Exception:
        return None
    try:
        return ET.fromstring(raw)
    except Exception:
        return None


def _cell_ref_to_col_idx(cell_ref: str) -> int:
    # Excel A1 -> 1, B2 -> 2, AA1 -> 27
    letters = "".join(ch for ch in str(cell_ref or "") if ch.isalpha()).upper()
    if not letters:
        return 0
    value = 0
    for ch in letters:
        value = value * 26 + (ord(ch) - ord("A") + 1)
    return value


def _xlsx_shared_strings(payload: bytes) -> list[str]:
    root = _read_xml_from_zip(payload, "xl/sharedStrings.xml")
    if root is None:
        return []
    out: list[str] = []
    for node in root.iter():
        if _local_name(node.tag) != "si":
            continue
        text = _node_text(node)
        out.append(text)
    return out


def _xlsx_cell_text(cell: ET.Element, shared_strings: list[str]) -> str:
    ctype = (cell.attrib.get("t") or "").strip().lower()
    value_text = ""
    for child in cell:
        lname = _local_name(child.tag)
        if lname == "v" and child.text:
            value_text = child.text.strip()
        if lname == "is":
            inline = _node_text(child)
            if inline:
                return inline
    if ctype == "s":
        try:
            idx = int(value_text)
            if 0 <= idx < len(shared_strings):
                return shared_strings[idx]
        except Exception:
            return ""
        return ""
    return value_text.strip()


@dataclass
class PageUnit:
    page_no: int
    source_type: str
    width: int | None = None
    height: int | None = None
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass
class RegionBlock:
    block_id: str
    page_no: int
    text: str
    block_type: str = "text"
    confidence: float = 1.0
    bbox: list[float] | None = None
    parent_block_id: str | None = None
    reading_order: int | None = None
    table_id: str | None = None
    row_idx: int | None = None
    col_idx: int | None = None
    rowspan: int | None = None
    colspan: int | None = None


@dataclass
class TextLayer:
    page_no: int
    text: str
    source: str = "embedded"


@dataclass
class AssetRef:
    asset_id: str
    kind: str
    uri: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass
class IngestedDocument:
    input_kind: str
    input_format: str
    content_type: str
    page_units: list[PageUnit] = field(default_factory=list)
    region_blocks: list[RegionBlock] = field(default_factory=list)
    text_layers: list[TextLayer] = field(default_factory=list)
    assets: list[AssetRef] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)


def ingest_document_stub(filename: str, content_type: str, payload: bytes) -> IngestedDocument:
    """Return IR metadata for input routing (pdf/image handled by OCR pipeline)."""
    ext = Path(filename or "").suffix.lower().lstrip(".")
    kind = "unknown"
    if content_type.startswith("image/"):
        kind = "image"
    elif content_type == "application/pdf":
        kind = "pdf"
    elif content_type.startswith("application/vnd.openxmlformats-officedocument"):
        kind = "office"
    return IngestedDocument(
        input_kind=kind,
        input_format=ext or "unknown",
        content_type=content_type,
        page_units=[PageUnit(page_no=1, source_type=kind)],
        assets=[AssetRef(asset_id="origin", kind="binary", metadata={"bytes": str(len(payload or b""))})],
    )


def ingest_office_document(filename: str, content_type: str | None, payload: bytes) -> IngestedDocument:
    resolved_type = resolve_content_type(filename, content_type, payload)
    ext = Path(filename or "").suffix.lower()
    if resolved_type.endswith("wordprocessingml.document") or ext == ".docx":
        return _ingest_docx(filename, resolved_type, payload)
    if resolved_type.endswith("presentationml.presentation") or ext == ".pptx":
        return _ingest_pptx(filename, resolved_type, payload)
    if resolved_type.endswith("spreadsheetml.sheet") or ext == ".xlsx":
        return _ingest_xlsx(filename, resolved_type, payload)
    raise ValueError("Unsupported office format")


def _ingest_docx(filename: str, content_type: str, payload: bytes) -> IngestedDocument:
    root = _read_xml_from_zip(payload, "word/document.xml")
    if root is None:
        raise ValueError("Invalid DOCX payload")
    body = None
    for node in root.iter():
        if _local_name(node.tag) == "body":
            body = node
            break
    if body is None:
        raise ValueError("DOCX body not found")

    blocks: list[RegionBlock] = []
    text_lines: list[str] = []
    reading_order = 0
    table_idx = 0

    for child in list(body):
        lname = _local_name(child.tag)
        if lname == "tbl":
            table_idx += 1
            table_id = f"docx-tbl{table_idx}"
            row_idx = 0
            for row in child:
                if _local_name(row.tag) != "tr":
                    continue
                row_idx += 1
                col_idx = 0
                for cell in row:
                    if _local_name(cell.tag) != "tc":
                        continue
                    col_idx += 1
                    cell_text = _node_text(cell).strip()
                    if not cell_text:
                        continue
                    reading_order += 1
                    blocks.append(
                        RegionBlock(
                            block_id=f"{table_id}-r{row_idx}c{col_idx}",
                            page_no=1,
                            text=cell_text,
                            block_type="table",
                            reading_order=reading_order,
                            table_id=table_id,
                            row_idx=row_idx,
                            col_idx=col_idx,
                            rowspan=1,
                            colspan=1,
                        )
                    )
                    text_lines.append(cell_text)
            continue

        if lname == "p":
            paragraph = _node_text(child).strip()
            if paragraph:
                reading_order += 1
                blocks.append(
                    RegionBlock(
                        block_id=f"docx-b{reading_order}",
                        page_no=1,
                        text=paragraph,
                        block_type="text",
                        reading_order=reading_order,
                    )
                )
                text_lines.append(paragraph)

    return IngestedDocument(
        input_kind="office",
        input_format="docx",
        content_type=content_type,
        page_units=[PageUnit(page_no=1, source_type="docx")],
        region_blocks=blocks,
        text_layers=[TextLayer(page_no=1, text="\n".join(text_lines), source="docx-xml")],
        assets=[AssetRef(asset_id="origin", kind="docx", uri=filename)],
        metadata={"adapter": "office_ingestor"},
    )


def _slide_num(name: str) -> int:
    match = re.search(r"slide(\d+)\.xml$", name)
    if not match:
        return 10_000
    return int(match.group(1))


def _ingest_pptx(filename: str, content_type: str, payload: bytes) -> IngestedDocument:
    names = _zip_root_names(payload)
    slides = sorted(
        [name for name in names if name.startswith("ppt/slides/slide") and name.endswith(".xml")],
        key=_slide_num,
    )
    if not slides:
        raise ValueError("PPTX slides not found")

    blocks: list[RegionBlock] = []
    text_layers: list[TextLayer] = []
    pages: list[PageUnit] = []

    for page_no, slide_name in enumerate(slides, start=1):
        root = _read_xml_from_zip(payload, slide_name)
        if root is None:
            continue
        pages.append(PageUnit(page_no=page_no, source_type="pptx", metadata={"slide": slide_name}))
        reading_order = 0
        lines: list[str] = []
        for node in root.iter():
            if _local_name(node.tag) != "p":
                continue
            para = _node_text(node).strip()
            if not para:
                continue
            reading_order += 1
            blocks.append(
                RegionBlock(
                    block_id=f"pptx-p{page_no}-b{reading_order}",
                    page_no=page_no,
                    text=para,
                    block_type="text",
                    reading_order=reading_order,
                )
            )
            lines.append(para)
        if lines:
            text_layers.append(TextLayer(page_no=page_no, text="\n".join(lines), source="pptx-slide"))

    if not pages:
        pages = [PageUnit(page_no=1, source_type="pptx")]

    return IngestedDocument(
        input_kind="office",
        input_format="pptx",
        content_type=content_type,
        page_units=pages,
        region_blocks=blocks,
        text_layers=text_layers,
        assets=[AssetRef(asset_id="origin", kind="pptx", uri=filename)],
        metadata={"adapter": "office_ingestor"},
    )


def _worksheet_num(name: str) -> int:
    match = re.search(r"sheet(\d+)\.xml$", name)
    if not match:
        return 10_000
    return int(match.group(1))


def _ingest_xlsx(filename: str, content_type: str, payload: bytes) -> IngestedDocument:
    names = _zip_root_names(payload)
    worksheets = sorted(
        [name for name in names if name.startswith("xl/worksheets/") and name.endswith(".xml")],
        key=_worksheet_num,
    )
    if not worksheets:
        raise ValueError("XLSX worksheets not found")
    shared_strings = _xlsx_shared_strings(payload)

    pages: list[PageUnit] = []
    blocks: list[RegionBlock] = []
    text_layers: list[TextLayer] = []

    for page_no, sheet_name in enumerate(worksheets, start=1):
        root = _read_xml_from_zip(payload, sheet_name)
        if root is None:
            continue
        pages.append(PageUnit(page_no=page_no, source_type="xlsx", metadata={"sheet": sheet_name}))
        table_id = f"sheet{page_no}-tbl1"
        reading_order = 0
        lines: dict[int, dict[int, str]] = {}

        for row in root.iter():
            if _local_name(row.tag) != "row":
                continue
            row_idx = int(row.attrib.get("r") or "0")
            if row_idx <= 0:
                continue
            row_cells: dict[int, str] = {}
            for cell in row:
                if _local_name(cell.tag) != "c":
                    continue
                col_idx = _cell_ref_to_col_idx(cell.attrib.get("r") or "")
                if col_idx <= 0:
                    continue
                cell_text = _xlsx_cell_text(cell, shared_strings).strip()
                if not cell_text:
                    continue
                row_cells[col_idx] = cell_text
                reading_order += 1
                blocks.append(
                    RegionBlock(
                        block_id=f"{table_id}-r{row_idx}c{col_idx}",
                        page_no=page_no,
                        text=cell_text,
                        block_type="table",
                        reading_order=reading_order,
                        table_id=table_id,
                        row_idx=row_idx,
                        col_idx=col_idx,
                        rowspan=1,
                        colspan=1,
                    )
                )
            if row_cells:
                lines[row_idx] = row_cells

        if lines:
            out_lines: list[str] = []
            for row_idx in sorted(lines.keys()):
                cells = [text for _col, text in sorted(lines[row_idx].items(), key=lambda item: item[0])]
                out_lines.append("\t".join(cells))
            text_layers.append(TextLayer(page_no=page_no, text="\n".join(out_lines), source="xlsx-sheet"))

    if not pages:
        pages = [PageUnit(page_no=1, source_type="xlsx")]

    return IngestedDocument(
        input_kind="office",
        input_format="xlsx",
        content_type=content_type,
        page_units=pages,
        region_blocks=blocks,
        text_layers=text_layers,
        assets=[AssetRef(asset_id="origin", kind="xlsx", uri=filename)],
        metadata={"adapter": "office_ingestor"},
    )


def to_ocr_blocks(region_blocks: list[RegionBlock]) -> list[OCRBlock]:
    out: list[OCRBlock] = []
    for block in region_blocks:
        text = str(block.text or "").strip()
        if not text:
            continue
        out.append(
            OCRBlock(
                block_id=block.block_id,
                page_no=int(block.page_no),
                text_raw=text,
                text_corrected=text,
                confidence=float(block.confidence),
                bbox=block.bbox,
                source_loc=f"p{int(block.page_no)}",
                block_type=block.block_type,
                parent_block_id=block.parent_block_id,
                reading_order=block.reading_order,
                table_id=block.table_id,
                row_idx=block.row_idx,
                col_idx=block.col_idx,
                rowspan=block.rowspan,
                colspan=block.colspan,
            )
        )
    return out
