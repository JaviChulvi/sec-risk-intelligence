from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .common import file_sha256, load_json


SPLIT_NAMES = ("train", "validation", "test")


@dataclass(frozen=True)
class NewsDatasetSplit:
    source_path: Path
    values: dict

    @classmethod
    def load(cls, path: Path, *, configured_companies: set[str]) -> "NewsDatasetSplit":
        values = load_json(path)
        cls._validate(values, configured_companies=configured_companies)
        return cls(path, values)

    @staticmethod
    def _validate(values: dict, *, configured_companies: set[str]) -> None:
        required = {
            "protocol_version",
            "unit",
            "splits",
            "target_candidates",
            "filter_freeze",
            "blind_data_policy",
        }
        missing = required - set(values)
        if missing:
            raise ValueError(f"Missing dataset split keys: {sorted(missing)}")
        if values["unit"] != "article_company_relation":
            raise ValueError("Dataset split unit must be article_company_relation")
        period_keys = {"dataset_period", "dataset_periods"} & set(values)
        if len(period_keys) != 1:
            raise ValueError(
                "Dataset split must define exactly one of dataset_period or dataset_periods"
            )
        if set(values["splits"]) != set(SPLIT_NAMES):
            raise ValueError(f"Dataset splits must be exactly {list(SPLIT_NAMES)}")

        assigned = [
            company
            for split_name in SPLIT_NAMES
            for company in values["splits"][split_name]
        ]
        if len(assigned) != len(set(assigned)):
            raise ValueError("A company cannot occur in more than one dataset split")
        if set(assigned) != configured_companies:
            raise ValueError(
                "Dataset splits must assign every configured company exactly once; "
                f"assigned={sorted(assigned)} configured={sorted(configured_companies)}"
            )
        expected_sizes = {"train": 4, "validation": 1, "test": 2}
        for split_name, expected in expected_sizes.items():
            if len(values["splits"][split_name]) != expected:
                raise ValueError(f"{split_name} must contain {expected} companies")

        split_periods = NewsDatasetSplit._periods(values)
        company_splits = {
            company: split_name
            for split_name in SPLIT_NAMES
            for company in values["splits"][split_name]
        }
        exclusions = values["blind_data_policy"].get("excluded_company_periods", {})
        unknown_exclusions = set(exclusions) - configured_companies
        if unknown_exclusions:
            raise ValueError(f"Excluded periods reference unknown companies: {sorted(unknown_exclusions)}")
        for company, periods in exclusions.items():
            period_start, period_end = split_periods[company_splits[company]]
            for excluded in periods:
                excluded_start, excluded_end = NewsDatasetSplit._period(excluded)
                if max(period_start, excluded_start) <= min(period_end, excluded_end):
                    raise ValueError(
                        f"Dataset period overlaps an inspected exclusion for {company}: {excluded}"
                    )

        targets = values["target_candidates"]
        per_company = targets.get("per_company")
        if not isinstance(per_company, int) or per_company <= 0:
            raise ValueError("target_candidates.per_company must be positive")
        for split_name in SPLIT_NAMES:
            expected = per_company * len(values["splits"][split_name])
            if targets.get(split_name) != expected:
                raise ValueError(f"Target for {split_name} must equal {expected}")
        if targets.get("total") != per_company * len(assigned):
            raise ValueError("Total candidate target does not match per-company targets")
        if values["blind_data_policy"].get("rule_tuning_allowed_splits") != ["train"]:
            raise ValueError("Only the train split may be used to tune rules")
        target_families = values.get("target_risk_families")
        if target_families is not None:
            if (
                not isinstance(target_families, list)
                or not target_families
                or len(target_families) != len(set(target_families))
                or any(not isinstance(family, str) or not family for family in target_families)
            ):
                raise ValueError("target_risk_families must be a non-empty unique list")
        freeze = values["filter_freeze"]
        if freeze.get("status") not in {"pending", "frozen"}:
            raise ValueError("filter_freeze.status must be pending or frozen")
        if freeze["status"] == "frozen":
            required_freeze = {"status", "frozen_at_utc", "config_sha256", "risk_filter_sha256"}
            if set(freeze) != required_freeze:
                raise ValueError(
                    "A frozen filter requires frozen_at_utc, config_sha256 and risk_filter_sha256"
                )
        artifacts = values["blind_data_policy"].get("excluded_development_artifacts", [])
        if not artifacts:
            raise ValueError("Excluded development artifacts must be recorded")
        for artifact in artifacts:
            if set(artifact) != {"path", "sha256"}:
                raise ValueError("Excluded artifact entries require path and sha256")
            path = Path(artifact["path"])
            if path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] != "data":
                raise ValueError("Excluded artifact paths must be repository-relative below data/")
            checksum = artifact["sha256"]
            if len(checksum) != 64 or any(character not in "0123456789abcdef" for character in checksum):
                raise ValueError("Excluded artifact sha256 must be a lowercase SHA-256 digest")

    @staticmethod
    def _period(value: dict) -> tuple[date, date]:
        try:
            start = date.fromisoformat(value["from"])
            end = date.fromisoformat(value["to"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid date period: {value!r}") from exc
        if start > end:
            raise ValueError(f"Period starts after it ends: {value!r}")
        return start, end

    @classmethod
    def _periods(cls, values: dict) -> dict[str, tuple[date, date]]:
        if "dataset_period" in values:
            period = cls._period(values["dataset_period"])
            return {split_name: period for split_name in SPLIT_NAMES}
        periods = values["dataset_periods"]
        if not isinstance(periods, dict) or set(periods) != set(SPLIT_NAMES):
            raise ValueError(f"dataset_periods must define exactly {list(SPLIT_NAMES)}")
        return {
            split_name: cls._period(periods[split_name])
            for split_name in SPLIT_NAMES
        }

    def period(self, stage: str) -> tuple[date, date]:
        periods = self._periods(self.values)
        if stage == "all":
            unique_periods = set(periods.values())
            if len(unique_periods) != 1:
                raise ValueError(
                    "Split stages use different periods and must be acquired separately"
                )
            return next(iter(unique_periods))
        if stage not in SPLIT_NAMES:
            raise ValueError(f"Unknown dataset split stage: {stage}")
        return periods[stage]

    def _period_value(self, stage: str) -> dict:
        if "dataset_period" in self.values:
            return self.values["dataset_period"]
        if stage == "all":
            self.period(stage)
            return self.values["dataset_periods"]["train"]
        return self.values["dataset_periods"][stage]

    @property
    def start(self) -> date:
        return self.period("train")[0]

    @property
    def end(self) -> date:
        return self.period("train")[1]

    @property
    def target_risk_families(self) -> list[str] | None:
        families = self.values.get("target_risk_families")
        return list(families) if families is not None else None

    @property
    def company_roles(self) -> dict[str, str]:
        return {
            company: split_name
            for split_name in SPLIT_NAMES
            for company in self.values["splits"][split_name]
        }

    def companies(self, stage: str) -> list[str]:
        if stage == "all":
            return [
                company
                for split_name in SPLIT_NAMES
                for company in self.values["splits"][split_name]
            ]
        if stage not in SPLIT_NAMES:
            raise ValueError(f"Unknown dataset split stage: {stage}")
        return list(self.values["splits"][stage])

    def validate_request(
        self,
        *,
        start: date,
        end: date,
        stage: str,
        companies: list[str] | None,
    ) -> list[str]:
        expected_start, expected_end = self.period(stage)
        if (start, end) != (expected_start, expected_end):
            raise ValueError(
                f"Split protocol requires the frozen {stage} period "
                f"{expected_start.isoformat()} to {expected_end.isoformat()}"
            )
        expected = self.companies(stage)
        if companies is not None and companies != expected:
            raise ValueError(
                f"--companies must match split stage {stage}: expected {expected}"
            )
        if stage != "train" and self.values["filter_freeze"]["status"] != "frozen":
            raise ValueError(
                "Validation and test remain sealed until the target risk-news "
                "filter is frozen"
            )
        return expected

    def manifest(self, *, stage: str) -> dict:
        portable_path = (
            str(self.source_path) if not self.source_path.is_absolute() else self.source_path.name
        )
        manifest = {
            "protocol_version": self.values["protocol_version"],
            "protocol_path": portable_path,
            "protocol_sha256": file_sha256(self.source_path),
            "stage": stage,
            "dataset_period": self._period_value(stage),
            "splits": self.values["splits"],
            "target_candidates": self.values["target_candidates"],
            "filter_freeze": self.values["filter_freeze"],
            "blind_data_policy": self.values["blind_data_policy"],
        }
        if "dataset_periods" in self.values:
            manifest["dataset_periods"] = self.values["dataset_periods"]
        if self.target_risk_families is not None:
            manifest["target_risk_families"] = self.target_risk_families
        return manifest
