from __future__ import annotations

from collections import defaultdict
from datetime import date
from difflib import SequenceMatcher

from .common import digest
from .normalize import normalized_text
from .schemas import NormalizedArticle


class ArticleDeduplicator:
    def __init__(self, *, date_tolerance_days: int = 2, title_similarity_threshold: float = 0.94):
        self.date_tolerance_days = date_tolerance_days
        self.title_similarity_threshold = title_similarity_threshold

    def assign(self, articles: list[NormalizedArticle]) -> list[dict]:
        parents = list(range(len(articles)))

        def find(index):
            while parents[index] != index:
                parents[index] = parents[parents[index]]
                index = parents[index]
            return index

        def union(left, right):
            a, b = find(left), find(right)
            if a != b:
                parents[max(a, b)] = min(a, b)

        exact: dict[tuple[str, str], int] = {}
        for index, article in enumerate(articles):
            keys = []
            if article.canonical_url:
                keys.append(("url", article.canonical_url))
            if article.content_sha256:
                keys.append(("content", article.content_sha256))
            for key in keys:
                if key in exact:
                    union(index, exact[key])
                else:
                    exact[key] = index

        for left, a in enumerate(articles):
            for right in range(left + 1, len(articles)):
                b = articles[right]
                if a.company != b.company or not self._near(a, b):
                    continue
                title_a, title_b = normalized_text(a.title), normalized_text(b.title)
                if not title_a or not title_b:
                    continue
                similarity = SequenceMatcher(None, title_a, title_b).ratio()
                if title_a == title_b or similarity >= self.title_similarity_threshold:
                    union(left, right)

        grouped: dict[int, list[int]] = defaultdict(list)
        for index in range(len(articles)):
            grouped[find(index)].append(index)
        result = []
        for members in grouped.values():
            if len(members) < 2:
                continue
            ids = sorted(articles[index].article_id for index in members)
            group_id = digest("duplicate\n" + "\n".join(ids))
            for index in members:
                articles[index].duplicate_group_id = group_id
            result.append({"duplicate_group_id": group_id, "article_ids": ids, "count": len(ids)})
        return sorted(result, key=lambda row: row["duplicate_group_id"])

    def _near(self, left: NormalizedArticle, right: NormalizedArticle) -> bool:
        try:
            a = date.fromisoformat((left.published_at_utc or "")[:10])
            b = date.fromisoformat((right.published_at_utc or "")[:10])
        except ValueError:
            return False
        return abs((a - b).days) <= self.date_tolerance_days
