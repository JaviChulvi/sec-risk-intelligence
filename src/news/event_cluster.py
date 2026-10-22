from __future__ import annotations

from collections import defaultdict
from datetime import date
from difflib import SequenceMatcher

from .common import digest
from .normalize import normalized_text
from .schemas import NormalizedArticle


class EventClusterer:
    """Produce reviewable episode proposals; it never confirms that an event occurred."""

    def __init__(self, *, max_days: int = 5, similarity_threshold: float = 0.62):
        self.max_days = max_days
        self.similarity_threshold = similarity_threshold

    def propose(self, articles: list[NormalizedArticle]) -> list[dict]:
        candidates: dict[str, dict[str, NormalizedArticle]] = defaultdict(dict)
        for article in articles:
            if article.risk_family_candidates:
                candidates[article.company][article.article_id] = article
        proposals = []
        for company, indexed_rows in candidates.items():
            groups: list[list[NormalizedArticle]] = []
            rows = list(indexed_rows.values())
            for article in sorted(rows, key=lambda item: (item.published_at_utc or "", item.article_id)):
                group = next((candidate for candidate in groups if self._same_event(article, candidate[-1])), None)
                if group is None:
                    groups.append([article])
                else:
                    group.append(article)
            for group in groups:
                ids = sorted({article.article_id for article in group})
                families = sorted({family for article in group for family in article.risk_family_candidates})
                event_id = digest("event_proposal\n" + company + "\n" + "\n".join(families + ids))
                primary = max(
                    group,
                    key=lambda item: (
                        item.content_available in {"full", "partial"},
                        item.content_length_words,
                    ),
                )
                for article in group:
                    article.event_id = event_id
                proposals.append({
                    "event_id": event_id,
                    "company": company,
                    "risk_families": families,
                    "article_ids": ids,
                    "primary_article_id": primary.article_id,
                    "review_status": "candidate",
                    "method": "company + family + date proximity + title/content similarity",
                })
        return proposals

    def _same_event(self, left: NormalizedArticle, right: NormalizedArticle) -> bool:
        try:
            first = date.fromisoformat((left.published_at_utc or "")[:10])
            second = date.fromisoformat((right.published_at_utc or "")[:10])
        except ValueError:
            return False
        if abs((first - second).days) > self.max_days:
            return False
        title_a, title_b = normalized_text(left.title), normalized_text(right.title)
        body_a = normalized_text(left.title + " " + left.content[:1000])
        body_b = normalized_text(right.title + " " + right.content[:1000])
        similarities = [
            SequenceMatcher(None, title_a, title_b).ratio() if title_a and title_b else 0,
            SequenceMatcher(None, body_a, body_b).ratio() if body_a and body_b else 0,
        ]
        return max(similarities) >= self.similarity_threshold
