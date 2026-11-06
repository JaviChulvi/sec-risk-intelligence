from __future__ import annotations

import csv

import pytest

from src.news.common import write_csv
from src.news.risk_news_review_sheet import PackagedRiskNewsReviewBuilder


FIELDS = [
    "dataset_id",
    "selection_rank",
    "article_id",
    "company",
    "published_at_utc",
    "title",
    "content_available",
    "risk_families",
    "risk_match_terms",
    "link",
    "review_status",
]


def candidate(rank: int, company: str, families: str) -> dict:
    return {
        "dataset_id": "mag7-risk-train",
        "selection_rank": rank,
        "article_id": f"article-{rank}",
        "company": company,
        "published_at_utc": "2026-01-01T00:00:00+00:00",
        "title": f"Candidate {rank}",
        "content_available": "full",
        "risk_families": families,
        "risk_match_terms": '{"cybersecurity": ["breach"]}',
        "link": f"https://example.test/{rank}",
        "review_status": "candidate",
    }


def test_builds_bodyless_derived_review_sheet_and_protects_annotations(tmp_path):
    candidates = tmp_path / "candidates.csv"
    output = tmp_path / "review.csv"
    write_csv(candidates, FIELDS, [
        candidate(2, "MSFT", "cybersecurity|critical_suppliers"),
        candidate(1, "AAPL", "cybersecurity"),
    ])

    result = PackagedRiskNewsReviewBuilder().build(candidates, output)

    with output.open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    assert result["rows"] == 2
    assert result["by_family_activation"] == {
        "critical_suppliers": 1,
        "cybersecurity": 2,
    }
    assert [row["review_order"] for row in rows] == ["1", "2"]
    assert all(row["review_status"] == "pending" for row in rows)
    assert all(row["selection_provenance"] == "mag7-risk-train" for row in rows)
    assert "content" not in rows[0]

    rows[0]["review_status"] = "reviewed"
    rows[0]["relevant_risk_news"] = "true"
    write_csv(output, list(rows[0]), rows)
    with pytest.raises(ValueError, match="Refusing to overwrite"):
        PackagedRiskNewsReviewBuilder().build(candidates, output)


def test_rejects_non_contiguous_selection_ranks(tmp_path):
    candidates = tmp_path / "candidates.csv"
    write_csv(candidates, FIELDS, [candidate(2, "AAPL", "cybersecurity")])

    with pytest.raises(ValueError, match="contiguous"):
        PackagedRiskNewsReviewBuilder().build(candidates, tmp_path / "review.csv")
