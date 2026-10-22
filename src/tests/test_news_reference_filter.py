import csv
import json
from pathlib import Path

import pytest

from src.news.reference_filter import ReferenceEpisodeFilter


REPOSITORY = Path(__file__).resolve().parents[2]


def write_cards(path, case_ids):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["case_id", "company", "title"])
        writer.writeheader()
        for case_id in case_ids:
            writer.writerow({"case_id": case_id, "company": "AAPL", "title": case_id})


def episode():
    return {
        "episode_id": "AAPL-2022-EVENT",
        "company": "AAPL",
        "episode_name": "Synthetic event",
        "risk_family": "cybersecurity",
        "source_case_ids": ["AAPL-01"],
        "followup_case_ids": ["AAPL-02"],
        "prior_filing_date": "2021-01-01",
        "t0_filing_date": "2022-01-01",
        "event_date_start": "2022-02-01",
        "event_date_end": "2022-02-01",
        "first_public_disclosure_at": "2022-02-02",
        "article_published_at": "2022-02-03",
        "known_urls": ["https://example.test/event"],
        "official_source": "https://example.test/event",
        "notes": "Synthetic",
        "used_for_filter_development": False,
        "review_status": "candidate",
        "reviewer": "Synthetic reviewer",
    }


def build(tmp_path, rules):
    review = tmp_path / "review.csv"
    rules_path = tmp_path / "rules.json"
    output = tmp_path / "eligible.json"
    report = tmp_path / "report.md"
    write_cards(review, ["AAPL-01", "AAPL-02", "AAPL-03"])
    rules_path.write_text(json.dumps(rules))
    result = ReferenceEpisodeFilter().build(review, rules_path, output, report)
    assert json.loads(output.read_text()) == result
    return result, report


def test_builds_exhaustive_episode_filter_and_groups_followup(tmp_path):
    result, report = build(tmp_path, {
        "protocol_version": "test",
        "allowed_risk_families": ["cybersecurity", "critical_suppliers"],
        "episodes": [episode()],
        "exclusions": [{
            "status": "excluded_out_of_scope_family",
            "case_ids": ["AAPL-03"],
            "reason": "Synthetic exclusion",
        }],
    })
    assert result["counts"] == {
        "inventory_cards": 3,
        "eligible_independent_episodes": 1,
        "eligible_source_cards": 1,
        "linked_followup_cards": 1,
        "excluded_cards": 1,
    }
    assert result["episodes"][0]["window_end"] == "2023-01-01"
    assert "AAPL-2022-EVENT" in report.read_text()


def test_rejects_unassigned_reference_card(tmp_path):
    with pytest.raises(ValueError, match="no eligibility decision: AAPL-03"):
        build(tmp_path, {
            "allowed_risk_families": ["cybersecurity"],
            "episodes": [episode()],
            "exclusions": [],
        })


def test_repository_rules_cover_all_49_cards_and_yield_six_episodes(tmp_path):
    result = ReferenceEpisodeFilter().build(
        REPOSITORY / "data/reference/news_mag7/known_cases_review.csv",
        REPOSITORY / "config/eodhd_reference_filter.json",
        tmp_path / "eligible.json",
        tmp_path / "report.md",
    )
    assert result["counts"]["inventory_cards"] == 49
    assert result["counts"]["eligible_independent_episodes"] == 6
    assert result["episodes_by_family"] == {
        "critical_suppliers": 3,
        "customer_concentration": 0,
        "cybersecurity": 3,
    }
    assert result["counts"]["linked_followup_cards"] == 1
    assert result["counts"]["excluded_cards"] == 42
