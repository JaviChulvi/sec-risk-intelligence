from __future__ import annotations

import copy
from datetime import date
from pathlib import Path

import pytest

from src.news.common import write_json
from src.news.dataset_split import NewsDatasetSplit
from src.news.eodhd_config import EodhdPilotConfig


ROOT = Path(__file__).resolve().parents[2]
PILOT_CONFIG = ROOT / "config" / "eodhd_pilot.json"
SPLIT_CONFIG = ROOT / "config" / "eodhd_dataset_split.json"
MULTI_PERIOD_SPLIT_CONFIG = ROOT / "config" / "eodhd_dataset_2021_2026.json"


def configured_companies() -> set[str]:
    return set(EodhdPilotConfig.load(PILOT_CONFIG)["companies"])


def test_repository_split_freezes_roles_period_and_targets():
    split = NewsDatasetSplit.load(
        SPLIT_CONFIG,
        configured_companies=configured_companies(),
    )

    assert split.companies("train") == ["AAPL", "MSFT", "GOOGL", "NVDA"]
    assert split.companies("validation") == ["AMZN"]
    assert split.companies("test") == ["META", "TSLA"]
    assert (split.start, split.end) == (date(2026, 1, 1), date(2026, 9, 30))
    assert split.values["target_candidates"] == {
        "per_company": 200,
        "train": 800,
        "validation": 200,
        "test": 400,
        "total": 1400,
    }


def test_split_request_rejects_old_period_and_wrong_stage_companies():
    split = NewsDatasetSplit.load(
        SPLIT_CONFIG,
        configured_companies=configured_companies(),
    )

    with pytest.raises(ValueError, match="frozen validation period"):
        split.validate_request(
            start=date(2025, 1, 1),
            end=date(2025, 12, 31),
            stage="validation",
            companies=None,
        )
    with pytest.raises(ValueError, match="must match split stage"):
        split.validate_request(
            start=split.start,
            end=split.end,
            stage="validation",
            companies=["TSLA"],
        )
    with pytest.raises(ValueError, match="remain sealed"):
        split.validate_request(
            start=split.start,
            end=split.end,
            stage="validation",
            companies=["AMZN"],
        )


def test_split_configuration_rejects_overlap_with_inspected_period(tmp_path):
    split = NewsDatasetSplit.load(
        SPLIT_CONFIG,
        configured_companies=configured_companies(),
    )
    values = copy.deepcopy(split.values)
    values["dataset_period"] = {
        "from": "2026-10-13",
        "to": "2026-10-19",
        "status": "invalid_test_overlap",
    }
    path = tmp_path / "overlap.json"
    write_json(path, values)

    with pytest.raises(ValueError, match="overlaps an inspected exclusion"):
        NewsDatasetSplit.load(path, configured_companies=configured_companies())


def test_multi_period_split_extends_only_training_history():
    split = NewsDatasetSplit.load(
        MULTI_PERIOD_SPLIT_CONFIG,
        configured_companies=configured_companies(),
    )

    assert split.target_risk_families == ["cybersecurity", "critical_suppliers"]
    assert split.period("train") == (date(2021, 1, 1), date(2026, 9, 30))
    assert split.period("validation") == (date(2026, 1, 1), date(2026, 9, 30))
    assert split.period("test") == (date(2026, 1, 1), date(2026, 9, 30))
    assert split.validate_request(
        start=date(2021, 1, 1),
        end=date(2026, 9, 30),
        stage="train",
        companies=None,
    ) == ["AAPL", "MSFT", "GOOGL", "NVDA"]

    with pytest.raises(ValueError, match="acquired separately"):
        split.period("all")
    with pytest.raises(ValueError, match="frozen validation period"):
        split.validate_request(
            start=date(2021, 1, 1),
            end=date(2026, 9, 30),
            stage="validation",
            companies=None,
        )
    with pytest.raises(ValueError, match="remain sealed"):
        split.validate_request(
            start=date(2026, 1, 1),
            end=date(2026, 9, 30),
            stage="validation",
            companies=["AMZN"],
        )


def test_multi_period_manifest_records_stage_and_full_period_plan():
    split = NewsDatasetSplit.load(
        MULTI_PERIOD_SPLIT_CONFIG,
        configured_companies=configured_companies(),
    )

    manifest = split.manifest(stage="train")

    assert manifest["dataset_period"] == split.values["dataset_periods"]["train"]
    assert manifest["dataset_periods"] == split.values["dataset_periods"]
    assert manifest["target_risk_families"] == [
        "cybersecurity",
        "critical_suppliers",
    ]
