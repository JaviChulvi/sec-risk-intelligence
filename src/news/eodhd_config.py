from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from .common import load_json


@dataclass(frozen=True)
class EodhdPilotConfig:
    source_path: Path
    values: dict

    @classmethod
    def load(cls, path: Path) -> "EodhdPilotConfig":
        values = load_json(path)
        cls._validate(values)
        return cls(path, values)

    @staticmethod
    def _validate(values: dict) -> None:
        required = {"provider", "endpoint", "http", "pagination", "paths", "companies", "modes", "risk_rules"}
        missing = sorted(required - set(values))
        if missing:
            raise ValueError(f"Missing EODHD configuration keys: {', '.join(missing)}")
        endpoint = urlsplit(values["endpoint"])
        if endpoint.scheme != "https" or not endpoint.hostname:
            raise ValueError("EODHD endpoint must be an HTTPS URL")
        if values["provider"] != "eodhd":
            raise ValueError("Provider must be eodhd")
        pagination = values["pagination"]
        if not 1 <= pagination["limit"] <= 1000:
            raise ValueError("EODHD page limit must be between 1 and 1000")
        if not 1 <= pagination["max_offset"] <= 9000:
            raise ValueError("EODHD max_offset must be between 1 and 9000")
        if pagination["max_offset"] % pagination["limit"]:
            raise ValueError("max_offset must be divisible by the page limit")
        for mode in ("demo", "pilot"):
            if mode not in values["modes"]:
                raise ValueError(f"Missing execution mode: {mode}")
        for company, details in values["companies"].items():
            if not details.get("query_tickers"):
                raise ValueError(f"Company {company} has no query tickers")
        configured = {ticker for details in values["companies"].values() for ticker in details["query_tickers"]}
        unknown_demo = set(values["modes"]["demo"]["tickers"]) - configured
        if unknown_demo:
            raise ValueError(f"Unknown demo tickers: {sorted(unknown_demo)}")
        for name, path in values["paths"].items():
            candidate = Path(path)
            if candidate.is_absolute() or ".." in candidate.parts or not candidate.parts or candidate.parts[0] != "data":
                raise ValueError(f"Path {name} must be a repository-relative path below data/")
        for family, entries in values["risk_rules"].items():
            if not entries or any(set(entry) != {"label", "pattern"} for entry in entries):
                raise ValueError(f"Risk rules for {family} must contain label/pattern objects")

    def __getitem__(self, key):
        return self.values[key]
