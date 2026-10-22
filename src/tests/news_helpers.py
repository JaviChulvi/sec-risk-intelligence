from __future__ import annotations

from dataclasses import replace
from datetime import date

from src.news.schemas import NormalizedArticle, QueryWindow


def normalized_article(**changes) -> NormalizedArticle:
    base = NormalizedArticle(
        article_id="article-a",
        article_id_rule="synthetic",
        provider="eodhd",
        company="AAPL",
        query_ticker="AAPL.US",
        published_at_original="2026-10-18T10:00:00Z",
        published_at_utc="2026-10-18T10:00:00+00:00",
        title="Synthetic incident at company",
        content="Synthetic fixture text",
        content_available="partial",
        content_length_chars=22,
        content_length_words=3,
        link="https://example.test/a",
        canonical_url="https://example.test/a",
        symbols=["AAPL.US"],
        tags=[],
        sentiment_polarity=None,
        sentiment_negative=None,
        sentiment_neutral=None,
        sentiment_positive=None,
        retrieved_at_utc="2026-10-19T00:00:00+00:00",
        query_from="2026-10-13",
        query_to="2026-10-19",
        raw_sha256="raw",
        content_sha256="content-a",
    )
    return replace(base, **changes)


def query_window(start: date | None = None, end: date | None = None) -> QueryWindow:
    return QueryWindow("AAPL", "AAPL.US", start or date(2026, 10, 18), end or date(2026, 10, 18))
