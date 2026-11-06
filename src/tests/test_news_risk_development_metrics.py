import csv
import json
from pathlib import Path

from src.news.eodhd_config import EodhdPilotConfig
from src.news.risk_news_development_metrics import RiskNewsDevelopmentMetricsBuilder
from src.tests.news_helpers import normalized_article


CONFIG = Path(__file__).resolve().parents[2] / "config" / "eodhd_pilot.json"


def write_csv(path, fields, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_compares_stored_and_revised_filters_using_only_local_articles(tmp_path):
    positive = normalized_article(
        article_id="positive",
        title="Apple responds to spyware attack",
        content="Apple said spyware infected targeted users.",
        risk_family_candidates=["cybersecurity"],
        risk_match_terms={"cybersecurity": ["cyberattack"]},
    )
    negative = normalized_article(
        article_id="negative",
        title="Other company reports a data breach",
        content=("Hackers breached its systems. " + "unrelated words " * 40 + "Apple shares rose."),
        risk_family_candidates=["cybersecurity"],
        risk_match_terms={"cybersecurity": ["data breach"]},
    )
    new_candidate = normalized_article(
        article_id="new-candidate",
        company="MSFT",
        title="Global IT outage affects Microsoft Windows",
        content="A faulty software update caused the outage.",
        risk_family_candidates=[],
        risk_match_terms={},
    )
    normalized_root = tmp_path / "normalized" / "AAPL" / "AAPL_US" / "window"
    normalized_root.mkdir(parents=True)
    with (normalized_root / "articles.jsonl").open("w", encoding="utf-8") as stream:
        for article in (positive, negative, new_candidate):
            stream.write(json.dumps(article.to_dict()) + "\n")

    metadata_fields = [
        "article_id", "company", "published_at_utc", "title", "content_available",
        "risk_family_candidates", "risk_match_terms", "link",
    ]
    metadata_rows = [{
        "article_id": article.article_id,
        "company": article.company,
        "published_at_utc": article.published_at_utc,
        "title": article.title,
        "content_available": article.content_available,
        "risk_family_candidates": repr(article.risk_family_candidates),
        "risk_match_terms": repr(article.risk_match_terms),
        "link": article.link,
    } for article in (positive, negative)]
    recent_metadata = tmp_path / "recent.csv"
    episode_metadata = tmp_path / "episode.csv"
    write_csv(recent_metadata, metadata_fields, [metadata_rows[1]])
    write_csv(episode_metadata, metadata_fields, [metadata_rows[0]])

    review_fields = [
        "review_order", "development_source", "label_provenance", "window_episode_id",
        "article_id", "company", "published_at_utc", "title", "content_available",
        "proposed_risk_families", "risk_match_terms", "link", "review_status",
        "relevant_risk_news", "company_relevance", "event_status",
        "confirmed_risk_families", "noise_type", "reviewer", "notes",
    ]
    review_rows = []
    for order, article, relevant in ((1, positive, True), (2, negative, False)):
        review_rows.append({
            "review_order": order,
            "development_source": "known_episode_review" if relevant else "recent_general_review",
            "label_provenance": (
                "episode_positive_implies_risk_news" if relevant else "general_review_reused"
            ),
            "window_episode_id": "AAPL-CYBER" if relevant else "",
            "article_id": article.article_id,
            "company": article.company,
            "published_at_utc": article.published_at_utc,
            "title": article.title,
            "content_available": article.content_available,
            "proposed_risk_families": "cybersecurity",
            "risk_match_terms": repr(article.risk_match_terms),
            "link": article.link,
            "review_status": "reviewed",
            "relevant_risk_news": str(relevant).lower(),
            "company_relevance": "",
            "event_status": "materialized" if relevant else "",
            "confirmed_risk_families": "cybersecurity" if relevant else "",
            "noise_type": "" if relevant else "other_company",
            "reviewer": "Reviewer",
            "notes": "Confirmed" if relevant else "Different company",
        })
    review = tmp_path / "review.csv"
    write_csv(review, review_fields, review_rows)
    new_review = tmp_path / "new_review.csv"
    new_review_fields = [
        "review_order", "selection_provenance", "article_id", "company",
        "published_at_utc", "title", "content_available", "proposed_risk_families",
        "risk_match_terms", "link", "review_status", "relevant_risk_news",
        "company_relevance", "event_status", "confirmed_risk_families", "noise_type",
        "reviewer", "notes",
    ]
    write_csv(new_review, new_review_fields, [{
        "review_order": 1,
        "selection_provenance": "revised_filter_new_candidate",
        "article_id": new_candidate.article_id,
        "company": new_candidate.company,
        "published_at_utc": new_candidate.published_at_utc,
        "title": new_candidate.title,
        "content_available": new_candidate.content_available,
        "proposed_risk_families": "critical_suppliers",
        "risk_match_terms": repr({
            "critical_suppliers": ["technology outage", "software update failure"]
        }),
        "link": new_candidate.link,
        "review_status": "reviewed",
        "relevant_risk_news": "true",
        "company_relevance": "",
        "event_status": "",
        "confirmed_risk_families": "critical_suppliers",
        "noise_type": "",
        "reviewer": "Reviewer",
        "notes": "Provider update disrupted Windows systems",
    }])

    config = EodhdPilotConfig.load(CONFIG)
    result = RiskNewsDevelopmentMetricsBuilder(config.values).build(
        review,
        recent_metadata,
        episode_metadata,
        tmp_path / "normalized",
        tmp_path / "metrics.json",
        tmp_path / "report.md",
        new_review,
    )

    assert result["baseline_stored_filter"]["selection"]["precision"] == 0.5
    assert result["revised_local_filter"]["selection"]["precision"] == 1.0
    assert result["revised_local_filter"]["selection"]["positive_retention"] == 1.0
    assert result["local_cached_corpus"]["retained_candidate_relations"] == 1
    assert result["local_cached_corpus"]["removed_candidate_relations"] == 1
    assert result["local_cached_corpus"]["new_candidate_relations"] == 1
    assert result["candidate_union_comparison"]["stored_filter"]["selection"]["positive_retention"] == 0.5
    assert result["candidate_union_comparison"]["revised_filter"]["selection"]["precision"] == 1.0
    assert result["candidate_union_comparison"]["revised_filter"]["selection"]["positive_retention"] == 1.0
    assert result["methodology"]["network_calls"] == 0
