from __future__ import annotations

from collections.abc import Callable, Hashable
from dataclasses import dataclass, field
from typing import TypeVar


T = TypeVar("T")


@dataclass
class AcquisitionBudget:
    """Mutable, run-scoped limits for an EODHD acquisition.

    ``max_articles`` limits article units admitted to the run, including records
    read from cache. Callers may deduplicate and define the identity of that unit
    with :meth:`admit_unique`. ``max_network_pages`` limits new logical provider
    pages, while ``max_http_attempts`` also includes provider retries.
    """

    max_articles: int | None = None
    max_network_pages: int | None = None
    max_http_attempts: int | None = None
    articles_used: int = 0
    network_pages_used: int = 0
    http_attempts_used: int = 0
    stop_reason: str | None = None
    records_considered: int = 0
    duplicate_records_skipped: int = 0
    _seen_article_keys: set[Hashable] = field(default_factory=set, repr=False)

    def __post_init__(self) -> None:
        for name, value in (
            ("max_articles", self.max_articles),
            ("max_network_pages", self.max_network_pages),
            ("max_http_attempts", self.max_http_attempts),
        ):
            if value is not None and value <= 0:
                raise ValueError(f"{name} must be positive when configured")

    @property
    def remaining_articles(self) -> int | None:
        if self.max_articles is None:
            return None
        return max(0, self.max_articles - self.articles_used)

    def page_limit(self, configured_limit: int) -> int | None:
        """Return the next network-page size, or stop when no budget remains."""
        remaining = self.remaining_articles
        if remaining == 0:
            self.stop_reason = "max_articles"
            return None
        if (
            self.max_network_pages is not None
            and self.network_pages_used >= self.max_network_pages
        ):
            self.stop_reason = "max_network_pages"
            return None
        return min(configured_limit, remaining) if remaining is not None else configured_limit

    def register_network_page(self) -> None:
        self.network_pages_used += 1

    def http_attempt_limit(self, provider_max_attempts: int) -> int | None:
        if self.max_http_attempts is None:
            return provider_max_attempts
        remaining = self.max_http_attempts - self.http_attempts_used
        if remaining <= 0:
            self.stop_reason = "max_http_attempts"
            return None
        return min(provider_max_attempts, remaining)

    def register_http_attempts(self, attempts: int) -> None:
        if attempts < 0:
            raise ValueError("attempts must not be negative")
        if (
            self.max_http_attempts is not None
            and self.http_attempts_used + attempts > self.max_http_attempts
        ):
            raise RuntimeError("Provider exceeded the configured HTTP-attempt budget")
        self.http_attempts_used += attempts

    def admit(self, rows: list[T]) -> tuple[list[T], bool]:
        """Admit as many records as possible and report whether rows were cut."""
        self.records_considered += len(rows)
        remaining = self.remaining_articles
        if remaining is None:
            accepted = rows
        else:
            accepted = rows[:remaining]
        self.articles_used += len(accepted)
        truncated = len(accepted) < len(rows)
        if truncated:
            self.stop_reason = "max_articles"
        return accepted, truncated

    def admit_unique(
        self,
        rows: list[T],
        *,
        identity: Callable[[T], Hashable],
    ) -> tuple[list[T], bool]:
        """Deduplicate rows before charging unique units to the article budget."""
        self.records_considered += len(rows)
        accepted = []
        truncated = False
        for row in rows:
            key = identity(row)
            if key in self._seen_article_keys:
                self.duplicate_records_skipped += 1
                continue
            if self.remaining_articles == 0:
                truncated = True
                self.stop_reason = "max_articles"
                continue
            self._seen_article_keys.add(key)
            accepted.append(row)
            self.articles_used += 1
        return accepted, truncated

    def require_article_capacity(self) -> bool:
        if self.remaining_articles == 0:
            self.stop_reason = "max_articles"
            return False
        return True

    def snapshot(self) -> dict:
        return {
            "max_articles": self.max_articles,
            "max_network_pages": self.max_network_pages,
            "max_http_attempts": self.max_http_attempts,
            "articles_used": self.articles_used,
            "network_pages_used": self.network_pages_used,
            "http_attempts_used": self.http_attempts_used,
            "stop_reason": self.stop_reason,
            "article_budget_unit": "caller-defined unique article identity",
            "records_considered": self.records_considered,
            "duplicate_records_skipped_before_budget": self.duplicate_records_skipped,
            "network_page_definition": (
                "One new logical provider page request; HTTP retries are counted separately"
            ),
        }
