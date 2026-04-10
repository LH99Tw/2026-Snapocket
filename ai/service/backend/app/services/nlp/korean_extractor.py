"""Korean morphological analysis and entity extraction using kiwipiepy."""

from __future__ import annotations

import re
import logging
from collections import Counter

logger = logging.getLogger(__name__)

# Pattern constants
_PHONE_RE  = re.compile(r"\b0\d{1,2}-\d{3,4}-\d{4}\b")
_EMAIL_RE  = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_DATE_RE   = re.compile(r"\b(20\d{2}[./-]\d{1,2}[./-]\d{1,2}|\d{1,2}[./-]\d{1,2})\b")
_AMOUNT_RE = re.compile(r"\b\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?\s*(?:원|KRW|₩|\$|USD)\b", re.I)
_ORG_RE    = re.compile(r"(?:주식회사|㈜|\(주\)|유한회사|재단법인|사단법인)\s*[가-힣A-Za-z]+")
_PERSON_RE = re.compile(r"\b([가-힣]{2,4})(?:\s*)(?:님|씨|대표|교수|원장)\b")

# Document type keywords with weights
_DOC_KEYWORDS: dict[str, list[str]] = {
    "notice":   ["공지", "안내", "신청", "마감", "기간", "일정", "모집", "공고"],
    "lecture":  ["강의", "수업", "과제", "시험", "출석", "주차", "교수", "학점", "수강"],
    "receipt":  ["합계", "총액", "결제", "카드", "승인", "부가세", "vat", "영수증"],
    "invoice":  ["세금계산서", "공급가액", "청구서", "거래처", "사업자번호", "부가세", "공급자"],
    "contract": ["계약서", "계약", "갑", "을", "서명", "날인", "계약기간", "위약금"],
    "resume":   ["이력서", "경력사항", "학력", "자기소개서", "지원동기", "취득자격"],
    "form":     ["신청서", "신청인", "작성일", "서식", "양식", "기재", "작성자"],
    "report":   ["보고서", "분석", "결론", "요약", "연구", "검토", "현황", "방안"],
}


def classify_doc_type_enhanced(text: str) -> str:
    """Score text against all document type keywords; return best match or 'unknown'."""
    lowered = text.lower()
    scores: dict[str, int] = {}
    for doc_type, keywords in _DOC_KEYWORDS.items():
        scores[doc_type] = sum(lowered.count(kw) for kw in keywords)
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] > 0 else "unknown"


class KoreanExtractor:
    """kiwipiepy 기반 한국어 형태소 분석 + 패턴 기반 개체명 추출."""

    def __init__(self) -> None:
        self._kiwi = None
        self._load_kiwi()

    def _load_kiwi(self) -> None:
        try:
            from kiwipiepy import Kiwi
            self._kiwi = Kiwi()
        except ImportError:
            logger.warning("kiwipiepy not installed; falling back to regex tokenizer")

    def extract_nouns(self, text: str) -> list[str]:
        """명사(NNG/NNP) 추출. kiwipiepy 미설치 시 정규식 폴백."""
        if self._kiwi is None:
            tokens = re.findall(r"[가-힣]{2,}", text)
            return [w for w, _ in Counter(tokens).most_common(20)]

        results = self._kiwi.analyze(text)
        nouns: list[str] = []
        for token in results[0][0]:
            if token.tag in ("NNG", "NNP") and len(token.form) >= 2:
                nouns.append(token.form)
        return [w for w, _ in Counter(nouns).most_common(20)]

    def extract_phones(self, text: str) -> list[str]:
        return list(dict.fromkeys(_PHONE_RE.findall(text)))

    def extract_emails(self, text: str) -> list[str]:
        return list(dict.fromkeys(_EMAIL_RE.findall(text)))

    def extract_dates(self, text: str) -> list[str]:
        return list(dict.fromkeys(m.group(0) for m in _DATE_RE.finditer(text)))

    def extract_amounts(self, text: str) -> list[str]:
        return list(dict.fromkeys(m.group(0) for m in _AMOUNT_RE.finditer(text)))

    def extract_orgs(self, text: str) -> list[str]:
        return list(dict.fromkeys(_ORG_RE.findall(text)))

    def extract_persons(self, text: str) -> list[str]:
        return list(dict.fromkeys(m.group(1) for m in _PERSON_RE.finditer(text)))
