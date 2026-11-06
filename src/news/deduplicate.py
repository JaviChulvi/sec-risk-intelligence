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

        normalized_titles = [normalized_text(article.title) for article in articles]
        dated_by_company: dict[str, list[tuple[date, int]]] = defaultdict(list)
        for index, article in enumerate(articles):
            published = self._published_date(article)
            if published is not None:
                dated_by_company[article.company].append((published, index))

        # Fuzzy comparisons only need articles from the same company and the
        # configured date window. Sorting first preserves the previous matching
        # semantics without the quadratic scan across the entire corpus.
        for dated_rows in dated_by_company.values():
            dated_rows.sort(key=lambda item: (item[0], item[1]))
            for left_position, (left_date, left) in enumerate(dated_rows):
                title_a = normalized_titles[left]
                if not title_a:
                    continue
                for right_position in range(left_position + 1, len(dated_rows)):
                    right_date, right = dated_rows[right_position]
                    if (right_date - left_date).days > self.date_tolerance_days:
                        break
                    title_b = normalized_titles[right]
                    if not title_b:
                        continue
                    if title_a == title_b:
                        union(left, right)
                        continue
                    maximum_ratio = (
                        2 * min(len(title_a), len(title_b))
                        / (len(title_a) + len(title_b))
                    )
                    if maximum_ratio < self.title_similarity_threshold:
                        continue
                    matcher = SequenceMatcher(None, title_a, title_b)
                    if matcher.quick_ratio() < self.title_similarity_threshold:
                        continue
                    if matcher.ratio() >= self.title_similarity_threshold:
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
        a = self._published_date(left)
        b = self._published_date(right)
        if a is None or b is None:
            return False
        return abs((a - b).days) <= self.date_tolerance_days

    @staticmethod
    def _published_date(article: NormalizedArticle) -> date | None:
        try:
            return date.fromisoformat((article.published_at_utc or "")[:10])
        except ValueError:
            return None
