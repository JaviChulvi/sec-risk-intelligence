from __future__ import annotations

import csv
import json

import pytest

from src.news.common import write_csv, write_json
from src.news.risk_news_dataset import RiskNewsDatasetPackager, StratifiedCandidateSelector


METADATA_FIELDS = [
    "article_id",
    "company",
    "query_ticker",
    "query_from",
    "query_to",
    "published_at_utc",
    "title",
    "content_available",
    "content_length_words",
    "risk_family_candidates",
    "risk_match_terms",
    "link",
    "canonical_url",
    "duplicate_group_id",
    "event_id",
]


def metadata_row(article_id, company, family):
    return {
        "article_id": article_id,
        "company": company,
        "query_ticker": f"{company}.US",
        "query_from": "2026-01-01",
        "query_to": "2026-01-31",
        "published_at_utc": "2026-01-10T00:00:00+00:00",
        "title": f"Risk news {article_id}",
        "content_available": "full",
        "content_length_words": "150",
        "risk_family_candidates": repr([family] if family else []),
        "risk_match_terms": repr({family: ["matched term"]} if family else {}),
        "link": f"https://example.test/{article_id}",
        "canonical_url": f"https://example.test/{article_id}",
        "duplicate_group_id": "",
        "event_id": "",
    }


def test_packager_exports_deterministic_bodyless_candidate_dataset(tmp_path):
    metadata = tmp_path / "articles_metadata.csv"
    acquisition = tmp_path / "manifest.json"
    output = tmp_path / "dataset"
    rows = [
        metadata_row("a1", "AAPL", "cybersecurity"),
        metadata_row("a2", "AAPL", "critical_suppliers"),
        metadata_row("m1", "MSFT", "cybersecurity"),
        metadata_row("m2", "MSFT", "critical_suppliers"),
        metadata_row("noise", "MSFT", ""),
    ]
    write_csv(metadata, METADATA_FIELDS, rows)
    write_json(acquisition, {
        "provider": "eodhd",
        "query_from": "2026-01-01",
        "query_to": "2026-01-31",
        "config_sha256": "config-hash",
        "acquisition_complete": False,
        "page_traversal": "breadth_first",
        "article_budget_unit": "unique_company_article_relation",
        "acquisition_budget": {"max_articles": 100, "articles_used": 100},
        "counts": {"articles": 100},
    })

    manifest = RiskNewsDatasetPackager(repository=tmp_path, selection_seed="fixed").build(
        dataset_id="mag7-risk-2026q1",
        metadata_path=metadata,
        acquisition_manifest_path=acquisition,
        output_root=output,
        risk_families=["cybersecurity", "critical_suppliers"],
        max_candidates=2,
    )

    exported = [json.loads(line) for line in (output / "risk_news_candidates.jsonl").read_text().splitlines()]
    assert manifest["counts"]["candidate_pool"] == 4
    assert manifest["counts"]["exported"] == 2
    assert manifest["acquisition"]["page_traversal"] == "breadth_first"
    assert manifest["acquisition"]["article_budget_unit"] == "unique_company_article_relation"
    assert len({row["company"] for row in exported}) == 2
    assert len({family for row in exported for family in row["risk_families"]}) == 2
    assert all(row["review_status"] == "candidate" for row in exported)
    assert all("content" not in row for row in exported)
    with (output / "risk_news_candidates.csv").open(newline="", encoding="utf-8") as stream:
        assert "content" not in csv.DictReader(stream).fieldnames


def test_packager_refuses_to_overwrite_existing_dataset(tmp_path):
    output = tmp_path / "dataset"
    output.mkdir()
    (output / "risk_news_candidates.csv").write_text("annotated data", encoding="utf-8")

    with pytest.raises(FileExistsError):
        RiskNewsDatasetPackager.ensure_destination_available(output)


def test_cross_split_duplicates_are_kept_only_in_highest_priority_split():
    base = {
        "canonical_url": "https://example.test/shared",
        "risk_families": ["cybersecurity"],
    }
    candidates = [
        {**base, "article_id": "shared", "company": "META", "split": "test"},
        {**base, "article_id": "shared", "company": "AAPL", "split": "train"},
        {
            **base,
            "article_id": "test-only",
            "canonical_url": "https://example.test/test-only",
            "company": "TSLA",
            "split": "test",
        },
    ]

    retained, excluded = RiskNewsDatasetPackager._exclude_cross_split_duplicates(candidates)

    assert {(row["article_id"], row["split"]) for row in retained} == {
        ("shared", "train"),
        ("test-only", "test"),
    }
    assert [(row["article_id"], row["split"]) for row in excluded] == [
        ("shared", "test")
    ]


def test_stratified_selector_enforces_company_cap():
    candidates = [
        {
            "article_id": article_id,
            "company": company,
            "risk_families": ["cybersecurity"],
        }
        for article_id, company in (
            ("a1", "AAPL"),
            ("a2", "AAPL"),
            ("a3", "AAPL"),
            ("m1", "MSFT"),
        )
    ]

    selected = StratifiedCandidateSelector("fixed").select(
        candidates,
        4,
        maximum_per_company=1,
    )

    assert len(selected) == 2
    assert {row["company"] for row in selected} == {"AAPL", "MSFT"}


@pytest.mark.parametrize("dataset_id", ["../escape", "has spaces", "", "/absolute"])
def test_dataset_id_must_be_a_safe_component(dataset_id):
    with pytest.raises(ValueError):
        RiskNewsDatasetPackager.validate_dataset_id(dataset_id)
