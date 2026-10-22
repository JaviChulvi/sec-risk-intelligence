import json
from datetime import date
from pathlib import Path

from src.news.normalize import EodhdNormalizer, canonical_url
from src.news.quality import ContentQualityClassifier
from src.tests.news_helpers import query_window


FIXTURE = Path(__file__).parent / "fixtures" / "eodhd" / "page.json"


def normalizer():
    return EodhdNormalizer(ContentQualityClassifier(partial_min_words=5, full_min_words=10))


def test_valid_response_normalizes_timezone_tracking_and_sentiment():
    raw = json.loads(FIXTURE.read_text())[0]
    article = normalizer().normalize(raw, window=query_window(), retrieved_at_utc="2026-10-19T00:00:00+00:00", raw_sha256="raw")
    assert article.published_at_utc == "2026-10-18T08:30:00+00:00"
    assert article.canonical_url == "https://example.test/story?id=7"
    assert article.sentiment_negative == 0.7
    assert article.content_available == "full"


def test_missing_content_and_url_use_deterministic_fallback_id():
    raw = {"date": "2026-10-18", "title": "Synthetic headline", "content": None}
    first = normalizer().normalize(raw, window=query_window(), retrieved_at_utc="x", raw_sha256="one")
    second = normalizer().normalize(raw, window=query_window(), retrieved_at_utc="y", raw_sha256="two")
    assert first.content_available == "missing"
    assert first.canonical_url == ""
    assert first.article_id == second.article_id
    assert "normalized_title" in first.article_id_rule


def test_url_id_is_stable_across_tracking_variants():
    base = {"date": "2026-10-18", "title": "One", "content": "short body"}
    left = normalizer().normalize({**base, "link": "https://EXAMPLE.test/a?b=2&utm_medium=x&a=1#x"}, window=query_window(), retrieved_at_utc="x", raw_sha256="x")
    right = normalizer().normalize({**base, "link": "https://example.test/a?a=1&b=2"}, window=query_window(), retrieved_at_utc="x", raw_sha256="x")
    assert left.article_id == right.article_id
    assert left.canonical_url == "https://example.test/a?a=1&b=2"


def test_error_and_title_only_content_are_not_full():
    invalid = normalizer().quality.classify(title="Story", content="Access denied. Enable cookies.")
    title = normalizer().quality.classify(title="Same title", content="Same title")
    assert invalid.availability.value == "invalid"
    assert title.availability.value == "summary_only"


def test_canonical_url_rejects_non_http_and_keeps_identifying_parameters():
    assert canonical_url("javascript:alert(1)") == ""
    assert canonical_url("https://example.test/a?id=9&gclid=x") == "https://example.test/a?id=9"
