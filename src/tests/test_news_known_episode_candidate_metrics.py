import csv
from pathlib import Path

import pytest

from src.news.known_episode_candidate_metrics import KnownEpisodeCandidateMetricsBuilder


REPOSITORY = Path(__file__).resolve().parents[2]


def build(review_path, output_path, report_path):
    return KnownEpisodeCandidateMetricsBuilder().build(
        review_path,
        REPOSITORY / "data/processed/eodhd_mag7/known_episode_probe/articles_metadata.csv",
        REPOSITORY / "data/processed/eodhd_mag7/known_episode_probe/manifest.json",
        REPOSITORY / "data/processed/eodhd_mag7/known_episode_query_manifest.json",
        REPOSITORY / "data/processed/eodhd_mag7/known_episode_probe/recovery_metrics.json",
        output_path,
        report_path,
    )


def test_repository_candidate_review_yields_confirmed_precision(tmp_path):
    result = build(
        REPOSITORY / "data/processed/eodhd_mag7/known_episode_probe/known_episode_candidate_review.csv",
        tmp_path / "metrics.json",
        tmp_path / "report.md",
    )

    assert result["review"]["rows_reviewed"] == 51
    assert result["metrics"] == {
        "relevant_candidates": 20,
        "false_positive_candidates": 31,
        "candidate_precision": 20 / 51,
        "false_positive_rate": 31 / 51,
        "correct_family_candidates": 10,
        "correct_family_precision": 10 / 51,
        "family_accuracy_among_relevant": 10 / 20,
        "relevant_with_useful_content": 20,
        "useful_content_rate_among_relevant": 1.0,
        "known_event_recall": 5 / 6,
        "correct_family_episode_recall": 5 / 6,
    }
    assert result["by_episode"]["TSLA-2023-IF-METALL"]["precision"] == 0
    assert result["noise_types"] == {"off_topic": 31}


def test_rejects_inconsistent_family_annotation(tmp_path):
    source = REPOSITORY / "data/processed/eodhd_mag7/known_episode_probe/known_episode_candidate_review.csv"
    review = tmp_path / "review.csv"
    with source.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
        fields = reader.fieldnames
    row = next(item for item in rows if item["candidate_family_correct"] == "true")
    row["candidate_family_correct"] = "false"
    with review.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    with pytest.raises(ValueError, match="candidate_family_correct is inconsistent"):
        build(review, tmp_path / "metrics.json", tmp_path / "report.md")
