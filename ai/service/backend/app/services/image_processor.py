"""Image preprocessing utilities to improve OCR robustness on scanned docs."""

from __future__ import annotations

import logging

import cv2
import numpy as np
from scipy.ndimage import rotate

logger = logging.getLogger(__name__)


class ImageProcessor:
    """OCR 전처리: 해상도 정규화 → deskew → CLAHE → Otsu."""

    def __init__(
        self,
        enabled: bool = True,
        *,
        target_dpi: int = 300,
        assumed_input_dpi: int = 144,
        apply_otsu: bool = True,
        max_side_px: int = 4200,
    ) -> None:
        self.enabled = enabled
        self.target_dpi = max(72, int(target_dpi))
        self.assumed_input_dpi = max(72, int(assumed_input_dpi))
        self.apply_otsu = apply_otsu
        self.max_side_px = max(512, int(max_side_px))

    def preprocess(self, img_bytes: bytes) -> bytes:
        """이미지 바이트를 받아 전처리 후 PNG 바이트 반환."""
        if not self.enabled:
            return img_bytes

        try:
            arr = np.frombuffer(img_bytes, dtype=np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is None:
                return img_bytes

            img = self._normalize_resolution(img)
            img = self._deskew(img)
            img = self._enhance_contrast(img)
            if self.apply_otsu:
                img = self._otsu_binarize(img)
            _, buf = cv2.imencode(".png", img)
            return buf.tobytes()
        except Exception as exc:
            logger.warning("ImageProcessor.preprocess failed: %s", exc)
            return img_bytes

    def _normalize_resolution(self, img: np.ndarray) -> np.ndarray:
        """입력 DPI가 낮다고 가정하고 목표 DPI(기본 300)로 동적 업스케일."""
        h, w = img.shape[:2]
        if h <= 0 or w <= 0:
            return img

        scale = self.target_dpi / float(self.assumed_input_dpi)
        if scale <= 1.0:
            return img

        max_dim = max(h, w)
        # Prevent overly large tensors that hurt latency/OOM.
        if (max_dim * scale) > self.max_side_px:
            scale = self.max_side_px / float(max_dim)
        if scale <= 1.0:
            return img

        new_w = max(1, int(round(w * scale)))
        new_h = max(1, int(round(h * scale)))
        return cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_CUBIC)

    def _deskew(self, img: np.ndarray) -> np.ndarray:
        """Hough Line Transform으로 기울기 추정 후 보정."""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        angle = self._estimate_skew(gray)
        if abs(angle) < 0.5:
            return img
        rotated = rotate(img, angle, reshape=False, cval=255, mode="constant")
        return rotated.astype(np.uint8)

    def _estimate_skew(self, gray: np.ndarray) -> float:
        """그레이스케일 이미지에서 기울기 각도(도) 반환."""
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 50, 150, apertureSize=3)
        lines = cv2.HoughLines(edges, 1, np.pi / 180, threshold=100)
        if lines is None:
            return 0.0

        angles: list[float] = []
        for line in lines[:50]:  # 최대 50개만 처리
            rho, theta = line[0]
            angle = np.degrees(theta) - 90
            if abs(angle) < 45:
                angles.append(angle)

        if not angles:
            return 0.0
        return float(np.median(angles))

    def _enhance_contrast(self, img: np.ndarray) -> np.ndarray:
        """CLAHE 적응형 명암 대비 향상."""
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l_channel, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l_channel = clahe.apply(l_channel)
        enhanced = cv2.merge([l_channel, a, b])
        return cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)

    def _otsu_binarize(self, img: np.ndarray) -> np.ndarray:
        """Otsu 기반 이진화로 배경 노이즈를 줄인다."""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
