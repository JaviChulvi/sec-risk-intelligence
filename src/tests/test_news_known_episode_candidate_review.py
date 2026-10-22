import csv
from pathlib import Path

import pytest

from src.news.known_episode_candidate_review import KnownEpisodeCandidateReviewBuilder


REPOSITORY = Path(__file__).resolve().parents[2]


def build(output):
    return KnownEpisodeCandidateReviewBuilder().build(
        REPOSITORY / "data/processed/eodhd_mag7/known_episode_probe/articles_metadata.csv",
        REPOSITORY / "data/processed/eodhd_mag7/known_episode_probe/manifest.json",
        REPOSITORY / "data/processed/eodhd_mag7/known_episode_query_manifest.json",
        REPOSITORY / "config/eodhd_known_episode_recovery_review.json",
        output,
    )


def test_builds_all_51_candidates_without_preempting_human_decisions(tmp_path):
    output = tmp_path / "review.csv"
    result = build(output)
    with output.open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))

    assert result["rows"] == 51
    assert len(rows) == 51
    assert result["window_episodes"] == 6
    assert result["previously_confirmed_evidence_rows"] == 5
    assert all(row["review_status"] == "pending" for row in rows)
    assert all(not row["relevant_to_window_episode"] for row in rows)
    assert {row["window_episode_id"] for row in rows} == {
        "AAPL-2021-NSO-LAWSUIT",
        "AAPL-2022-ZHENGZHOU",
        "MSFT-2023-STORM-0558",
        "MSFT-2024-MIDNIGHT-BLIZZARD",
        "MSFT-2024-CROWDSTRIKE-OUTAGE",
        "TSLA-2023-IF-METALL",
    }


def test_refuses_to_overwrite_reviewed_rows(tmp_path):
    output = tmp_path / "review.csv"
    build(output)
    text = output.read_text(encoding="utf-8")
    output.write_text(text.replace(",pending,", ",reviewed,", 1), encoding="utf-8")

    with pytest.raises(ValueError, match="Refusing to overwrite"):
        build(output)
