from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from enum import Enum
from typing import Any


class ContentAvailability(str, Enum):
    FULL = "full"
    PARTIAL = "partial"
    SUMMARY_ONLY = "summary_only"
    MISSING = "missing"
    INVALID = "invalid"


@dataclass(frozen=True)
class QueryWindow:
    company: str
    ticker: str
    start: date
    end: date

    @property
    def key(self) -> str:
        return f"{self.company}__{self.ticker}__{self.start.isoformat()}__{self.end.isoformat()}"

    def split(self) -> tuple["QueryWindow", "QueryWindow"]:
        if self.start >= self.end:
            raise ValueError("A one-day window cannot be split further")
        midpoint = self.start + timedelta(days=(self.end - self.start).days // 2)
        return (
            QueryWindow(self.company, self.ticker, self.start, midpoint),
            QueryWindow(self.company, self.ticker, midpoint + timedelta(days=1), self.end),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "company": self.company,
            "ticker": self.ticker,
            "from": self.start.isoformat(),
            "to": self.end.isoformat(),
        }


@dataclass(frozen=True)
class PageRequest:
    window: QueryWindow
    limit: int
    offset: int


@dataclass(frozen=True)
class ProviderPage:
    request: PageRequest
    articles: list[dict[str, Any]]
    raw_bytes: bytes
    status_code: int
    retrieved_at_utc: str
    attempts: int
    from_cache: bool = False


@dataclass
class NormalizedArticle:
    article_id: str
    article_id_rule: str
    provider: str
    company: str
    query_ticker: str
    published_at_original: str
    published_at_utc: str | None
    title: str
    content: str
    content_available: str
    content_length_chars: int
    content_length_words: int
    link: str
    canonical_url: str
    symbols: list[str]
    tags: list[str]
    sentiment_polarity: float | None
    sentiment_negative: float | None
    sentiment_neutral: float | None
    sentiment_positive: float | None
    retrieved_at_utc: str
    query_from: str
    query_to: str
    raw_sha256: str
    content_sha256: str
    duplicate_group_id: str | None = None
    event_id: str | None = None
    risk_family_candidates: list[str] = field(default_factory=list)
    risk_match_terms: dict[str, list[str]] = field(default_factory=dict)
    language: str = "unknown"
    quality_flags: list[str] = field(default_factory=list)

    def to_dict(self, *, include_content: bool = True) -> dict[str, Any]:
        value = asdict(self)
        if not include_content:
            value.pop("content", None)
        return value
