import json
from pathlib import Path

import pytest

from src.news.eodhd_config import EodhdPilotConfig
from src.news.known_episode_metrics import KnownEpisodeMetricsBuilder


REPOSITORY = Path(__file__).resolve().parents[2]


def test_repository_confirmed_metrics_are_reproducible(tmp_path):
    result = KnownEpisodeMetricsBuilder(EodhdPilotConfig.load(
        REPOSITORY / "config/eodhd_pilot.json"
    )).build(
        REPOSITORY / "data/reference/news_mag7/eligible_known_episodes.json",
        REPOSITORY / "data/processed/eodhd_mag7/known_episode_query_manifest.json",
        REPOSITORY / "data/processed/eodhd_mag7/known_episode_probe/manifest.json",
        REPOSITORY / "data/processed/eodhd_mag7/known_episode_probe/articles_metadata.csv",
        REPOSITORY / "config/eodhd_known_episode_recovery_review.json",
        tmp_path / "metrics.json",
        tmp_path / "report.md",
    )

    assert result["metrics"] == {
        "expected_episodes": 6,
        "recovered_episodes": 5,
        "missed_episodes": 1,
        "known_event_recall": 5 / 6,
        "recovered_with_useful_content": 5,
        "reviewed_relevant_useful_content_rate": 1.0,
        "correct_family_recovered_episodes": 5,
        "correct_family_recall": 5 / 6,
    }
    assert result["by_family"]["customer_concentration"]["recall"] is None
    assert result["threshold_evaluation"]["numeric_gate"] == "GO"
    assert (tmp_path / "report.md").exists()


def test_rejects_review_article_outside_episode_window(tmp_path):
    config = EodhdPilotConfig.load(REPOSITORY / "config/eodhd_pilot.json")
    review = json.loads((REPOSITORY / "config/eodhd_known_episode_recovery_review.json").read_text())
    review["decisions"][0]["representative_article_ids"] = [
        review["decisions"][1]["representative_article_ids"][0]
    ]
    review_path = tmp_path / "review.json"
    review_path.write_text(json.dumps(review))

    with pytest.raises(ValueError, match="does not belong to episode"):
        KnownEpisodeMetricsBuilder(config).build(
            REPOSITORY / "data/reference/news_mag7/eligible_known_episodes.json",
            REPOSITORY / "data/processed/eodhd_mag7/known_episode_query_manifest.json",
            REPOSITORY / "data/processed/eodhd_mag7/known_episode_probe/manifest.json",
            REPOSITORY / "data/processed/eodhd_mag7/known_episode_probe/articles_metadata.csv",
            review_path,
            tmp_path / "metrics.json",
            tmp_path / "report.md",
        )
