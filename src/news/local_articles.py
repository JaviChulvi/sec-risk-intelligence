from __future__ import annotations

import json
from pathlib import Path

from .schemas import NormalizedArticle


def read_normalized_articles(root: Path) -> tuple[dict[tuple[str, str], NormalizedArticle], list[Path]]:
    """Load unique article-company relations from repository-local normalized caches."""
    files = sorted(root.glob("**/articles.jsonl"))
    if not files:
        raise ValueError(f"No normalized article caches found below {root}")
    articles = {}
    for path in files:
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                article = NormalizedArticle(**json.loads(line))
                key = article.article_id, article.company
                existing = articles.get(key)
                if existing and existing.content_sha256 != article.content_sha256:
                    raise ValueError(f"Conflicting normalized articles for relation: {key}")
                articles[key] = article
    return articles, files
