import json
import sys
from pathlib import Path

import pytest

from src.news.__main__ import main
from src.news.eodhd_config import EodhdPilotConfig
from src.news.episode_windows import EpisodeWindowPlanner


REPOSITORY = Path(__file__).resolve().parents[2]


def write_episodes(path: Path, episodes: list[dict]) -> None:
    path.write_text(json.dumps({"episodes": episodes}), encoding="utf-8")


def synthetic_episode(**overrides) -> dict:
    episode = {
        "episode_id": "AAPL-2024-EVENT",
        "company": "AAPL",
        "episode_name": "Synthetic event",
        "risk_family": "cybersecurity",
        "first_public_disclosure_at": "2024-01-19",
        "source_case_ids": ["AAPL-01"],
        "followup_case_ids": [],
        "known_urls": ["https://example.test/event"],
        "review_status": "candidate",
    }
    episode.update(overrides)
    return episode


def test_builds_eleven_day_disclosure_window_without_credential(tmp_path):
    source = tmp_path / "episodes.json"
    output = tmp_path / "manifest.json"
    write_episodes(source, [synthetic_episode()])
    config = EodhdPilotConfig.load(REPOSITORY / "config/eodhd_pilot.json")

    result = EpisodeWindowPlanner(config).build(source, output)

    assert json.loads(output.read_text()) == result
    assert result["counts"] == {
        "episodes": 1,
        "query_windows": 1,
        "planned_initial_calls": 1,
    }
    assert result["api_called"] is False
    assert result["credential_accessed"] is False
    assert result["windows"][0]["anchor_date"] == "2024-01-19"
    assert result["windows"][0]["from"] == "2024-01-16"
    assert result["windows"][0]["to"] == "2024-01-26"
    assert result["windows"][0]["ticker"] == "AAPL.US"
    assert "api_token" not in result["windows"][0]["initial_request_without_credential"]["params"]

    windows, source_manifest = EpisodeWindowPlanner(config).load_query_windows(output)
    assert [window.to_dict() for window in windows] == [{
        "company": "AAPL",
        "ticker": "AAPL.US",
        "from": "2024-01-16",
        "to": "2024-01-26",
    }]
    assert source_manifest["planned_windows"] == 1


def test_rejects_modified_query_manifest(tmp_path):
    source = tmp_path / "episodes.json"
    output = tmp_path / "manifest.json"
    write_episodes(source, [synthetic_episode()])
    config = EodhdPilotConfig.load(REPOSITORY / "config/eodhd_pilot.json")
    planner = EpisodeWindowPlanner(config)
    result = planner.build(source, output)
    result["windows"][0]["to"] = "2025-12-31"
    output.write_text(json.dumps(result), encoding="utf-8")

    with pytest.raises(ValueError, match="parameters do not match"):
        planner.load_query_windows(output)


def test_rejects_negative_margin_unknown_company_and_unknown_family(tmp_path):
    source = tmp_path / "episodes.json"
    output = tmp_path / "manifest.json"
    config = EodhdPilotConfig.load(REPOSITORY / "config/eodhd_pilot.json")
    planner = EpisodeWindowPlanner(config)
    write_episodes(source, [synthetic_episode()])
    with pytest.raises(ValueError, match="must not be negative"):
        planner.build(source, output, days_before=-1)

    write_episodes(source, [synthetic_episode(company="UNKNOWN")])
    with pytest.raises(ValueError, match="unconfigured company"):
        planner.build(source, output)

    write_episodes(source, [synthetic_episode(risk_family="unknown_family")])
    with pytest.raises(ValueError, match="unconfigured risk family"):
        planner.build(source, output)


def test_cli_dry_run_does_not_read_api_token(tmp_path, monkeypatch, capsys):
    source = tmp_path / "episodes.json"
    output = tmp_path / "manifest.json"
    write_episodes(source, [synthetic_episode()])
    monkeypatch.setattr(
        "src.news.__main__.require_env",
        lambda _name: (_ for _ in ()).throw(AssertionError("credential was read")),
    )
    monkeypatch.setattr(sys, "argv", [
        "news",
        "eodhd",
        "episode-dry-run",
        "--config",
        str(REPOSITORY / "config/eodhd_pilot.json"),
        "--episodes",
        str(source),
        "--output",
        str(output),
    ])

    main()

    printed = json.loads(capsys.readouterr().out)
    assert printed["api_called"] is False
    assert output.exists()


def test_repository_episode_manifest_has_six_windows(tmp_path):
    config = EodhdPilotConfig.load(REPOSITORY / "config/eodhd_pilot.json")
    result = EpisodeWindowPlanner(config).build(
        REPOSITORY / "data/reference/news_mag7/eligible_known_episodes.json",
        tmp_path / "manifest.json",
    )

    assert result["counts"] == {
        "episodes": 6,
        "query_windows": 6,
        "planned_initial_calls": 6,
    }
    assert result["episodes_by_company"] == {"AAPL": 2, "MSFT": 3, "TSLA": 1}
    assert result["episodes_by_family"] == {
        "critical_suppliers": 3,
        "customer_concentration": 0,
        "cybersecurity": 3,
    }
