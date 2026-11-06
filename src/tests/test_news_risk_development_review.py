import csv

import pytest

from src.news.risk_news_development_review import RiskNewsDevelopmentReviewBuilder


def write_csv(path, fields, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def build_inputs(tmp_path):
    recent_metadata = tmp_path / "recent_metadata.csv"
    write_csv(recent_metadata, [
        "article_id", "company", "published_at_utc", "title", "content_available",
        "risk_family_candidates", "risk_match_terms", "link",
    ], [{
        "article_id": "recent-1", "company": "AAPL", "published_at_utc": "2026-01-01",
        "title": "Other company story", "content_available": "full",
        "risk_family_candidates": "['cybersecurity']",
        "risk_match_terms": "{'cybersecurity': ['data breach']}", "link": "https://example.com/1",
    }])
    recent_review = tmp_path / "recent_review.csv"
    write_csv(recent_review, [
        "article_id", "company", "selection_stratum", "review_status", "relevant_event",
        "noise_type", "reviewer", "notes",
    ], [{
        "article_id": "recent-1", "company": "AAPL", "selection_stratum": "risk_candidate",
        "review_status": "reviewed", "relevant_event": "false", "noise_type": "other_company",
        "reviewer": "Reviewer", "notes": "Not about Apple",
    }])
    episode_review = tmp_path / "episode_review.csv"
    write_csv(episode_review, [
        "window_episode_id", "article_id", "company", "published_at_utc", "title",
        "content_available", "proposed_risk_families", "risk_match_terms", "link",
        "review_status", "relevant_to_window_episode", "confirmed_risk_family",
        "noise_type", "reviewer", "notes",
    ], [
        {
            "window_episode_id": "MSFT-CYBER", "article_id": "episode-positive", "company": "MSFT",
            "published_at_utc": "2024-01-01", "title": "Microsoft discloses breach",
            "content_available": "full", "proposed_risk_families": "cybersecurity",
            "risk_match_terms": "{'cybersecurity': ['data breach']}", "link": "https://example.com/2",
            "review_status": "reviewed", "relevant_to_window_episode": "true",
            "confirmed_risk_family": "cybersecurity", "noise_type": "", "reviewer": "Reviewer",
            "notes": "Confirmed episode",
        },
        {
            "window_episode_id": "MSFT-CYBER", "article_id": "episode-negative", "company": "MSFT",
            "published_at_utc": "2024-01-02", "title": "Another company discloses breach",
            "content_available": "full", "proposed_risk_families": "cybersecurity",
            "risk_match_terms": "{'cybersecurity': ['data breach']}", "link": "https://example.com/3",
            "review_status": "reviewed", "relevant_to_window_episode": "false",
            "confirmed_risk_family": "", "noise_type": "off_topic", "reviewer": "Reviewer",
            "notes": "Not the window episode",
        },
    ])
    return recent_review, recent_metadata, episode_review


def test_separates_general_selection_labels_from_episode_mismatches(tmp_path):
    inputs = build_inputs(tmp_path)
    output = tmp_path / "development.csv"

    result = RiskNewsDevelopmentReviewBuilder().build(*inputs, output)
    with output.open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))

    assert result == {
        "output": str(output),
        "output_sha256": result["output_sha256"],
        "rows": 3,
        "reviewed": 2,
        "pending": 1,
        "reused_general_negatives": 1,
        "reused_episode_positives": 1,
        "episode_negatives_requiring_relabel": 1,
    }
    pending = next(row for row in rows if row["article_id"] == "episode-negative")
    assert pending["review_status"] == "pending"
    assert pending["relevant_risk_news"] == ""
    assert pending["prior_episode_relevance"] == "false"
    positive = next(row for row in rows if row["article_id"] == "episode-positive")
    assert positive["relevant_risk_news"] == "true"
    assert positive["confirmed_risk_families"] == "cybersecurity"


def test_refuses_to_overwrite_imported_or_human_annotations(tmp_path):
    inputs = build_inputs(tmp_path)
    output = tmp_path / "development.csv"
    RiskNewsDevelopmentReviewBuilder().build(*inputs, output)

    with pytest.raises(ValueError, match="Refusing to overwrite"):
        RiskNewsDevelopmentReviewBuilder().build(*inputs, output)
