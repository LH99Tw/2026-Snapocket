"""Domain normalization helpers that convert OCR text into business JSON."""

from __future__ import annotations

from collections import Counter
import re

from app.schemas.infer import DomainEntities, DomainPayload
from app.services.nlp.korean_extractor import KoreanExtractor, classify_doc_type_enhanced

_extractor = KoreanExtractor()

# Backward-compatible alias
classify_doc_type = classify_doc_type_enhanced


def extract_entities(text: str) -> DomainEntities:
    subjects: list[str] = []
    for line in text.splitlines():
        if any(k in line for k in ["과목", "강의", "수업"]):
            stripped = line.strip()[:80]
            if stripped:
                subjects.append(stripped)

    seen: set[str] = set()
    unique_subjects = [s for s in subjects if not (s in seen or seen.add(s))]  # type: ignore[func-returns-value]

    return DomainEntities(
        dates=_extractor.extract_dates(text),
        amounts=_extractor.extract_amounts(text),
        subjects=unique_subjects,
        keywords=_extractor.extract_nouns(text)[:10],
        persons=_extractor.extract_persons(text)[:20],
        orgs=_extractor.extract_orgs(text)[:20],
        phones=_extractor.extract_phones(text)[:20],
        emails=_extractor.extract_emails(text)[:20],
    )


def _sentence_summary(text: str, limit: int = 3) -> str:
    sentences = [s.strip() for s in re.split(r"[\n.!?]+", text) if s.strip()]
    if not sentences:
        return ""
    if len(sentences) <= limit:
        return " ".join(sentences)[:300]

    nouns = _extractor.extract_nouns(text)
    weights = Counter(nouns)
    scored: list[tuple[int, int]] = []
    for idx, sentence in enumerate(sentences):
        score = sum(weights.get(token, 0) for token in _extractor.extract_nouns(sentence))
        scored.append((score, idx))

    top_indices = [idx for _, idx in sorted(scored, key=lambda item: (item[0], -item[1]), reverse=True)[:limit]]
    ordered = [sentences[idx] for idx in sorted(top_indices)]
    return " ".join(ordered)[:300]


def build_domain_payload(text: str, title_hint: str | None = None) -> DomainPayload:
    doc_type = classify_doc_type_enhanced(text)
    entities = extract_entities(text)

    title = title_hint
    if not title:
        for line in text.splitlines():
            if line.strip():
                title = line.strip()[:120]
                break

    summary = _sentence_summary(text, limit=3)

    fields: dict = {}
    if doc_type in {"receipt", "invoice"}:
        fields["total_candidates"] = entities.amounts[:3]
    if doc_type in {"notice", "lecture", "contract"}:
        fields["date_candidates"] = entities.dates[:3]

    return DomainPayload(
        doc_type=doc_type,
        title=title,
        summary=summary or None,
        entities=entities,
        fields=fields,
    )
