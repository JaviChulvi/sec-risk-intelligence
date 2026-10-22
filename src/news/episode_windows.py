from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from pathlib import Path

from .common import config_fingerprint, file_sha256, load_json, now_utc, write_json
from .eodhd_config import EodhdPilotConfig
from .schemas import QueryWindow


class EpisodeWindowPlanner:
    """Create credential-free EODHD requests around known public disclosures."""

    PROTOCOL_VERSION = "eodhd-known-episode-query-v1"

    def __init__(self, config: EodhdPilotConfig):
        self.config = config

    def build(
        self,
        episodes_path: Path,
        output_path: Path,
        *,
        days_before: int = 3,
        days_after: int = 7,
    ) -> dict:
        if days_before < 0 or days_after < 0:
            raise ValueError("Episode window margins must not be negative")

        source = load_json(episodes_path)
        episodes = source.get("episodes")
        if not isinstance(episodes, list) or not episodes:
            raise ValueError("Eligible episode file must contain a non-empty episodes list")

        planned_windows = []
        episode_ids: set[str] = set()
        episode_companies = Counter()
        query_companies = Counter()
        families = Counter()
        for episode in episodes:
            episode_id = self._required_text(episode, "episode_id")
            if episode_id in episode_ids:
                raise ValueError(f"Duplicate episode_id: {episode_id}")
            episode_ids.add(episode_id)

            company = self._required_text(episode, "company")
            if company not in self.config["companies"]:
                raise ValueError(f"Episode {episode_id} has an unconfigured company: {company}")
            risk_family = self._required_text(episode, "risk_family")
            if risk_family not in self.config["risk_rules"]:
                raise ValueError(f"Episode {episode_id} has an unconfigured risk family: {risk_family}")
            anchor = self._parse_date(episode, "first_public_disclosure_at", episode_id)
            start = anchor - timedelta(days=days_before)
            end = anchor + timedelta(days=days_after)

            episode_companies[company] += 1
            families[risk_family] += 1
            for ticker in self.config["companies"][company]["query_tickers"]:
                window = QueryWindow(company, ticker, start, end)
                query_companies[company] += 1
                planned_windows.append(self._window_entry(episode, window, anchor))

        planned_windows.sort(key=lambda item: (item["from"], item["episode_id"], item["ticker"]))
        allowed_families = sorted(self.config["risk_rules"])
        result = {
            "generated_at_utc": now_utc(),
            "protocol_version": self.PROTOCOL_VERSION,
            "provider": self.config["provider"],
            "mode": "known_episode_probe",
            "dry_run": True,
            "api_called": False,
            "credential_accessed": False,
            "source_episodes_file": str(episodes_path),
            "source_episodes_sha256": file_sha256(episodes_path),
            "config_file": str(self.config.source_path),
            "config_sha256": config_fingerprint(self.config.values),
            "window_policy": {
                "anchor": "first_public_disclosure_at",
                "days_before": days_before,
                "days_after": days_after,
                "calendar_days_per_window": days_before + days_after + 1,
            },
            "counts": {
                "episodes": len(episodes),
                "query_windows": len(planned_windows),
                "planned_initial_calls": len(planned_windows),
            },
            "episodes_by_company": dict(sorted(episode_companies.items())),
            "query_windows_by_company": dict(sorted(query_companies.items())),
            "episodes_by_family": {
                family: families.get(family, 0) for family in allowed_families
            },
            "windows": planned_windows,
            "limitations": [
                "No API request was made and no credential was read",
                "Planned initial calls exclude pagination, retries, and automatic window subdivision",
                "Reference episodes remain candidates pending independent human confirmation",
                "The reference inventory contains no eligible customer_concentration episode",
            ],
        }
        write_json(output_path, result)
        return result

    def load_query_windows(self, manifest_path: Path) -> tuple[list[QueryWindow], dict]:
        """Validate a dry-run manifest and return exactly its bounded windows."""
        manifest = load_json(manifest_path)
        if manifest.get("protocol_version") != self.PROTOCOL_VERSION:
            raise ValueError("Unsupported known-episode query manifest protocol")
        if manifest.get("provider") != self.config["provider"]:
            raise ValueError("Query manifest provider does not match configuration")
        if manifest.get("config_sha256") != config_fingerprint(self.config.values):
            raise ValueError("Query manifest configuration fingerprint does not match")
        if manifest.get("api_called") is not False or manifest.get("dry_run") is not True:
            raise ValueError("Episode execution requires an unexecuted dry-run manifest")

        rows = manifest.get("windows")
        if not isinstance(rows, list) or not rows:
            raise ValueError("Query manifest contains no windows")
        expected_count = manifest.get("counts", {}).get("query_windows")
        if expected_count != len(rows):
            raise ValueError("Query manifest window count does not match its contents")

        windows = []
        for row in rows:
            company = self._required_text(row, "company")
            ticker = self._required_text(row, "ticker")
            if company not in self.config["companies"]:
                raise ValueError(f"Query manifest has an unconfigured company: {company}")
            if ticker not in self.config["companies"][company]["query_tickers"]:
                raise ValueError(f"Query manifest has an unconfigured ticker for {company}: {ticker}")
            start = self._parse_date(row, "from", row.get("episode_id", "unknown"))
            end = self._parse_date(row, "to", row.get("episode_id", "unknown"))
            if start > end:
                raise ValueError("Query manifest window starts after it ends")
            request = row.get("initial_request_without_credential", {})
            params = request.get("params", {}) if isinstance(request, dict) else {}
            if "api_token" in params:
                raise ValueError("Query manifest must not contain a credential")
            expected = {
                "s": ticker,
                "from": start.isoformat(),
                "to": end.isoformat(),
                "limit": self.config["pagination"]["limit"],
                "offset": 0,
                "fmt": "json",
            }
            if params != expected:
                raise ValueError("Query manifest request parameters do not match its window")
            windows.append(QueryWindow(company, ticker, start, end))
        if len({window.key for window in windows}) != len(windows):
            raise ValueError("Query manifest contains duplicate windows")
        return windows, {
            "path": str(manifest_path),
            "sha256": file_sha256(manifest_path),
            "protocol_version": manifest["protocol_version"],
            "planned_windows": len(windows),
        }

    def _window_entry(self, episode: dict, window: QueryWindow, anchor: date) -> dict:
        request = {
            "endpoint": self.config["endpoint"],
            "params": {
                "s": window.ticker,
                "from": window.start.isoformat(),
                "to": window.end.isoformat(),
                "limit": self.config["pagination"]["limit"],
                "offset": 0,
                "fmt": "json",
            },
        }
        return {
            "episode_id": episode["episode_id"],
            "episode_name": episode.get("episode_name", ""),
            "risk_family": episode["risk_family"],
            "anchor_field": "first_public_disclosure_at",
            "anchor_date": anchor.isoformat(),
            **window.to_dict(),
            "source_case_ids": list(episode.get("source_case_ids", [])),
            "followup_case_ids": list(episode.get("followup_case_ids", [])),
            "known_urls": list(episode.get("known_urls", [])),
            "review_status": episode.get("review_status", ""),
            "initial_request_without_credential": request,
        }

    @staticmethod
    def _required_text(episode: dict, field: str) -> str:
        value = episode.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Episode is missing a non-empty {field}")
        return value.strip()

    @classmethod
    def _parse_date(cls, episode: dict, field: str, episode_id: str) -> date:
        value = cls._required_text(episode, field)
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"Episode {episode_id} has an invalid {field}: {value}") from exc
