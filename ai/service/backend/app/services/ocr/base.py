"""Abstract OCR engine contract and normalized engine output schema."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class OCREngineResult:
    text: str
    confidence: float
    bbox: list[float] | None
    page_no: int
    block_type: str = "text"
    parent_block_id: str | None = None
    reading_order: int | None = None
    table_id: str | None = None
    row_idx: int | None = None
    col_idx: int | None = None
    rowspan: int | None = None
    colspan: int | None = None


class OCREngineBusyError(RuntimeError):
    """Raised when an OCR engine is already processing another request."""


class OCREngine(ABC):
    name: str

    @abstractmethod
    def available(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def infer_image(self, image_bytes: bytes, page_no: int = 1) -> list[OCREngineResult]:
        raise NotImplementedError

    async def infer_image_async(
        self, image_bytes: bytes, page_no: int = 1
    ) -> list[OCREngineResult]:
        """기본 구현: 동기 메서드를 executor에서 실행. 서브클래스에서 오버라이드 가능."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.infer_image, image_bytes, page_no)

    def warmup(self) -> bool:
        """Optional runtime warm-up hook. Engines may override."""
        return True

    def unload(self) -> bool:
        """Optional runtime unload hook. Engines may override."""
        return True
