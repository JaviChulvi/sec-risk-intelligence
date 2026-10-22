from src.news.event_cluster import EventClusterer
from src.tests.news_helpers import normalized_article


def test_clusters_similar_nearby_candidates_and_selects_longer_primary():
    left = normalized_article(
        article_id="a", title="Synthetic data breach affects company", risk_family_candidates=["cybersecurity"]
    )
    right = normalized_article(
        article_id="b", title="Synthetic data breach affects the company", content="long " * 100,
        content_length_words=100, published_at_utc="2026-10-19T10:00:00+00:00",
        risk_family_candidates=["cybersecurity"], canonical_url="https://example.test/b",
    )
    proposals = EventClusterer(similarity_threshold=0.5).propose([left, right])
    assert len(proposals) == 1
    assert proposals[0]["article_ids"] == ["a", "b"]
    assert proposals[0]["risk_families"] == ["cybersecurity"]
    assert proposals[0]["primary_article_id"] == "b"
    assert proposals[0]["review_status"] == "candidate"


def test_distant_articles_remain_separate_event_proposals():
    left = normalized_article(article_id="a", risk_family_candidates=["cybersecurity"])
    right = normalized_article(
        article_id="b", published_at_utc="2026-11-19T10:00:00+00:00",
        risk_family_candidates=["cybersecurity"], canonical_url="https://example.test/b",
    )
    assert len(EventClusterer().propose([left, right])) == 2
