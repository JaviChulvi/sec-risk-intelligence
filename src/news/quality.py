from __future__ import annotations

import re
from dataclasses import dataclass

from .schemas import ContentAvailability


INVALID_PATTERNS = (
    re.compile(r"\b(access denied|forbidden|page not found|error 404)\b", re.I),
    re.compile(r"\b(enable cookies|cookie consent|accept cookies|javascript is disabled)\b", re.I),
)
TRUNCATION_PATTERNS = (
    re.compile(r"(?:\.\.\.|…|\[\.\.\.\]|\[truncated\])\s*$", re.I),
    re.compile(r"\b(read more|continue reading)\s*$", re.I),
)
ENGLISH_MARKERS = {"the", "and", "of", "to", "in", "for", "on", "with", "said", "company"}


@dataclass(frozen=True)
class ContentAssessment:
    availability: ContentAvailability
    length_chars: int
    length_words: int
    language: str
    flags: tuple[str, ...]


class ContentQualityClassifier:
    """Transparent heuristics; this does not infer factual accuracy or relevance."""

    def __init__(self, *, partial_min_words: int = 80, full_min_words: int = 250):
        if not 1 <= partial_min_words < full_min_words:
            raise ValueError("Content word thresholds must be positive and ordered")
        self.partial_min_words = partial_min_words
        self.full_min_words = full_min_words

    def classify(self, *, title: str, content: str) -> ContentAssessment:
        compact = " ".join(content.split())
        words = re.findall(r"\b[\w'-]+\b", compact, re.UNICODE)
        flags: list[str] = []
        if not compact:
            return ContentAssessment(ContentAvailability.MISSING, 0, 0, "unknown", ("empty",))
        if any(pattern.search(compact[:1000]) for pattern in INVALID_PATTERNS):
            return ContentAssessment(
                ContentAvailability.INVALID,
                len(content),
                len(words),
                self._language(words),
                ("error_or_consent_page",),
            )
        if self._normalise(compact) == self._normalise(title):
            flags.append("content_identical_to_title")
            availability = ContentAvailability.SUMMARY_ONLY
        elif len(words) < self.partial_min_words:
            flags.append("short_content")
            availability = ContentAvailability.SUMMARY_ONLY
        elif any(pattern.search(compact) for pattern in TRUNCATION_PATTERNS):
            flags.append("truncation_indicator")
            availability = ContentAvailability.PARTIAL
        elif len(words) < self.full_min_words:
            flags.append("below_full_length_threshold")
            availability = ContentAvailability.PARTIAL
        else:
            availability = ContentAvailability.FULL
        return ContentAssessment(availability, len(content), len(words), self._language(words), tuple(flags))

    @staticmethod
    def _normalise(value: str) -> str:
        return " ".join(value.casefold().split())

    @staticmethod
    def _language(words: list[str]) -> str:
        lowered = {word.casefold() for word in words}
        return "en" if len(lowered.intersection(ENGLISH_MARKERS)) >= 3 else "unknown"
