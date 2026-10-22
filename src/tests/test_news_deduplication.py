from src.news.deduplicate import ArticleDeduplicator
from src.tests.news_helpers import normalized_article


def test_groups_same_url_content_and_near_identical_title_without_deleting_records():
    rows = [
        normalized_article(article_id="a"),
        normalized_article(article_id="b", query_ticker="GOOGL.US"),
        normalized_article(article_id="c", canonical_url="https://other.test/c", content_sha256="content-a"),
        normalized_article(
            article_id="d", canonical_url="https://other.test/d", content_sha256="content-d",
            title="Synthetic incident at the company", published_at_utc="2026-10-19T10:00:00+00:00",
        ),
    ]
    groups = ArticleDeduplicator(title_similarity_threshold=0.85).assign(rows)
    assert len(rows) == 4
    assert len(groups) == 1
    assert {row.duplicate_group_id for row in rows} == {groups[0]["duplicate_group_id"]}


def test_does_not_fuzzy_merge_different_companies_or_distant_dates():
    rows = [
        normalized_article(article_id="a"),
        normalized_article(
            article_id="b", company="MSFT", canonical_url="https://example.test/b", content_sha256="content-b"
        ),
        normalized_article(
            article_id="c", canonical_url="https://example.test/c", content_sha256="content-c",
            published_at_utc="2026-11-18T10:00:00+00:00",
        ),
    ]
    assert ArticleDeduplicator().assign(rows) == []
