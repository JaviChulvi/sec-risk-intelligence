from __future__ import annotations

import ast
import csv
import json
import re
from collections import Counter, defaultdict, deque
from pathlib import Path

from .common import digest, file_sha256, now_utc, write_bytes, write_csv, write_json


DATASET_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")


class StratifiedCandidateSelector:
    """Deterministic round-robin selection over company/risk-family strata."""

    def __init__(self, seed: str):
        if not seed.strip():
            raise ValueError("selection seed must not be empty")
        self.seed = seed

    def select(
        self,
        candidates: list[dict],
        maximum: int,
        *,
        maximum_per_company: int | None = None,
    ) -> list[dict]:
        if maximum <= 0:
            raise ValueError("max_candidates must be positive")
        if maximum_per_company is not None and maximum_per_company <= 0:
            raise ValueError("maximum_per_company must be positive")
        buckets: dict[tuple[str, str], deque] = {}
        available_strata = {
            (row["company"], family)
            for row in candidates
            for family in row["risk_families"]
        }
        companies = sorted({company for company, _ in available_strata})
        families = sorted({family for _, family in available_strata})
        ordered_strata = []
        for family_offset in range(len(families)):
            for company_index, company in enumerate(companies):
                family = families[(company_index + family_offset) % len(families)]
                if (company, family) in available_strata:
                    ordered_strata.append((company, family))
        for stratum in ordered_strata:
            ranked = sorted(
                (
                    row for row in candidates
                    if row["company"] == stratum[0] and stratum[1] in row["risk_families"]
                ),
                key=lambda row: digest(
                    f"{self.seed}|{stratum[0]}|{stratum[1]}|{row['article_id']}"
                ),
            )
            buckets[stratum] = deque(ranked)

        selected = []
        selected_keys = set()
        selected_by_company = Counter()
        while len(selected) < maximum:
            progress = False
            for stratum, bucket in buckets.items():
                while bucket and self._key(bucket[0]) in selected_keys:
                    bucket.popleft()
                if not bucket:
                    continue
                row = dict(bucket.popleft())
                if (
                    maximum_per_company is not None
                    and selected_by_company[row["company"]] >= maximum_per_company
                ):
                    continue
                key = self._key(row)
                selected_keys.add(key)
                selected_by_company[row["company"]] += 1
                row["selection_stratum"] = f"{stratum[0]}:{stratum[1]}"
                selected.append(row)
                progress = True
                if len(selected) == maximum:
                    break
            if not progress:
                break
        return selected

    @staticmethod
    def _key(row: dict) -> tuple[str, str]:
        return row["article_id"], row["company"]


class RiskNewsDatasetPackager:
    FIELDS = [
        "dataset_id",
        "selection_rank",
        "selection_stratum",
        "article_id",
        "company",
        "split",
        "published_at_utc",
        "title",
        "content_available",
        "content_length_words",
        "risk_families",
        "risk_match_terms",
        "query_tickers",
        "source_windows",
        "restricted_content_locators",
        "link",
        "canonical_url",
        "duplicate_group_id",
        "event_id",
        "review_status",
        "reviewer",
        "notes",
    ]

    def __init__(self, *, repository: Path, selection_seed: str = "eodhd-risk-dataset-v1"):
        self.repository = repository.resolve()
        self.selection_seed = selection_seed

    @staticmethod
    def validate_dataset_id(dataset_id: str) -> str:
        if not DATASET_ID_PATTERN.fullmatch(dataset_id):
            raise ValueError(
                "dataset_id must be 1-80 characters using letters, digits, dot, underscore or hyphen"
            )
        return dataset_id

    @classmethod
    def namespace(cls, dataset_id: str) -> str:
        return f"datasets/{cls.validate_dataset_id(dataset_id)}"

    @staticmethod
    def ensure_destination_available(output_root: Path) -> None:
        protected = (
            output_root / "dataset_manifest.json",
            output_root / "risk_news_candidates.csv",
            output_root / "risk_news_candidates.jsonl",
        )
        existing = [str(path) for path in protected if path.exists()]
        if existing:
            raise FileExistsError(
                "Dataset package already exists; use a new --dataset-id to preserve reproducibility: "
                + ", ".join(existing)
            )

    def build(
        self,
        *,
        dataset_id: str,
        metadata_path: Path,
        acquisition_manifest_path: Path,
        output_root: Path,
        risk_families: list[str],
        max_candidates: int,
        company_splits: dict[str, str] | None = None,
        split_protocol: dict | None = None,
    ) -> dict:
        dataset_id = self.validate_dataset_id(dataset_id)
        try:
            output_root.resolve().relative_to(self.repository)
        except ValueError as exc:
            raise ValueError("Dataset output must stay inside the repository") from exc
        if not metadata_path.exists():
            raise FileNotFoundError(metadata_path)
        if not acquisition_manifest_path.exists():
            raise FileNotFoundError(acquisition_manifest_path)
        self.ensure_destination_available(output_root)
        if len(set(risk_families)) != len(risk_families) or not risk_families:
            raise ValueError("risk_families must be a non-empty unique list")
        if max_candidates <= 0:
            raise ValueError("max_candidates must be positive")

        acquisition = json.loads(acquisition_manifest_path.read_text(encoding="utf-8"))
        self._validate_split_protocol(acquisition, split_protocol)
        candidates = self._load_candidates(
            metadata_path,
            set(risk_families),
            company_splits=company_splits,
        )
        candidates, cross_split_exclusions = self._exclude_cross_split_duplicates(candidates)
        maximum_per_company = (
            split_protocol["target_candidates"]["per_company"]
            if split_protocol
            else None
        )
        selected = StratifiedCandidateSelector(self.selection_seed).select(
            candidates,
            max_candidates,
            maximum_per_company=maximum_per_company,
        )
        for rank, row in enumerate(selected, start=1):
            row["dataset_id"] = dataset_id
            row["selection_rank"] = rank
            row["review_status"] = "candidate"
            row["reviewer"] = ""
            row["notes"] = ""

        jsonl_path = output_root / "risk_news_candidates.jsonl"
        csv_path = output_root / "risk_news_candidates.csv"
        write_bytes(
            jsonl_path,
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in selected).encode("utf-8"),
        )
        write_csv(csv_path, self.FIELDS, [self._csv_row(row) for row in selected])

        manifest = {
            "dataset_id": dataset_id,
            "created_at_utc": now_utc(),
            "provider": acquisition.get("provider"),
            "query_from": acquisition.get("query_from"),
            "query_to": acquisition.get("query_to"),
            "companies": acquisition.get("companies", []),
            "query_tickers": acquisition.get("query_tickers", []),
            "risk_families": risk_families,
            "split_protocol": split_protocol,
            "selection": {
                "strategy": "deterministic_round_robin_by_company_and_risk_family",
                "seed": self.selection_seed,
                "max_candidates": max_candidates,
                "unit": "article_company_relation",
            },
            "acquisition": {
                "complete": acquisition.get("acquisition_complete"),
                "page_traversal": acquisition.get("page_traversal"),
                "article_budget_unit": acquisition.get("article_budget_unit"),
                "budget": acquisition.get("acquisition_budget"),
                "counts": acquisition.get("counts"),
            },
            "counts": {
                "candidate_pool": len(candidates),
                "exported": len(selected),
                "excluded_cross_split_duplicates": len(cross_split_exclusions),
                "excluded_cross_split_duplicates_by_split": dict(Counter(
                    row["split"] for row in cross_split_exclusions
                )),
                "candidate_pool_by_company": dict(Counter(
                    row["company"] for row in candidates
                )),
                "candidate_pool_by_risk_family": dict(Counter(
                    family for row in candidates for family in row["risk_families"]
                )),
                "by_company": dict(Counter(row["company"] for row in selected)),
                "target_shortfall_by_company": {
                    company: max(
                        0,
                        maximum_per_company
                        - sum(row["company"] == company for row in selected),
                    )
                    for company in sorted(set(acquisition.get("companies", [])))
                } if maximum_per_company is not None else {},
                "by_split": dict(Counter(row["split"] for row in selected)),
                "by_risk_family": dict(Counter(
                    family for row in selected for family in row["risk_families"]
                )),
                "by_content_availability": dict(Counter(
                    row["content_available"] for row in selected
                )),
            },
            "artifacts": {
                "acquisition_manifest": acquisition_manifest_path.name,
                "all_articles_metadata": metadata_path.name,
                "candidates_csv": csv_path.name,
                "candidates_jsonl": jsonl_path.name,
                "bodies": "restricted EODHD normalized cache; not included in this package",
                "restricted_content_root": acquisition.get("storage_paths", {}).get(
                    "normalized_restricted"
                ),
                "restricted_content_locator_format": (
                    "company/ticker/window_from__window_to#article_id, relative to restricted_content_root"
                ),
            },
            "provenance": {
                "config_sha256": acquisition.get("config_sha256"),
                "metadata_sha256": file_sha256(metadata_path),
                "acquisition_manifest_sha256": file_sha256(acquisition_manifest_path),
                "candidates_csv_sha256": file_sha256(csv_path),
                "candidates_jsonl_sha256": file_sha256(jsonl_path),
                "packager_sha256": file_sha256(Path(__file__)),
            },
            "limitations": [
                "Rows are lexical filter candidates, not human-validated risk-news labels",
                "EODHD coverage is not assumed to be exhaustive",
                "Acquisition and candidate caps can change the observed company/family distribution",
                "Round-robin selection improves balance but is not a probability sample",
            ],
        }
        write_json(output_root / "dataset_manifest.json", manifest)
        return manifest

    def _load_candidates(
        self,
        path: Path,
        selected_families: set[str],
        *,
        company_splits: dict[str, str] | None,
    ) -> list[dict]:
        grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
        with path.open(newline="", encoding="utf-8") as stream:
            for row in csv.DictReader(stream):
                families = set(self._parse_literal(row.get("risk_family_candidates"), list))
                if families & selected_families:
                    grouped[(row["article_id"], row["company"])].append(row)

        candidates = []
        for (article_id, company), source_rows in sorted(grouped.items()):
            quality_order = {
                "full": 0,
                "partial": 1,
                "summary_only": 2,
                "missing": 3,
                "invalid": 4,
            }
            source_rows.sort(key=lambda row: (
                quality_order.get(row.get("content_available", ""), 5),
                -self._integer(row.get("content_length_words")),
                row.get("query_ticker", ""),
                row.get("query_from", ""),
                row.get("query_to", ""),
            ))
            primary = source_rows[0]
            split = company_splits.get(company, "") if company_splits else ""
            if company_splits is not None and not split:
                raise ValueError(f"No dataset split assigned to company {company}")
            families = sorted({
                family
                for row in source_rows
                for family in self._parse_literal(row.get("risk_family_candidates"), list)
                if family in selected_families
            })
            match_terms: dict[str, set[str]] = defaultdict(set)
            for row in source_rows:
                parsed_terms = self._parse_literal(row.get("risk_match_terms"), dict)
                for family in families:
                    match_terms[family].update(parsed_terms.get(family, []))
            candidates.append({
                "article_id": article_id,
                "company": company,
                "split": split,
                "published_at_utc": primary.get("published_at_utc", ""),
                "title": primary.get("title", ""),
                "content_available": primary.get("content_available", ""),
                "content_length_words": self._integer(primary.get("content_length_words")),
                "risk_families": families,
                "risk_match_terms": {
                    family: sorted(match_terms[family]) for family in families
                },
                "query_tickers": sorted({row.get("query_ticker", "") for row in source_rows}),
                "source_windows": sorted({
                    f"{row.get('query_from', '')}__{row.get('query_to', '')}"
                    for row in source_rows
                }),
                "restricted_content_locators": sorted({
                    self._content_locator(row, article_id) for row in source_rows
                }),
                "link": primary.get("link", ""),
                "canonical_url": primary.get("canonical_url", ""),
                "duplicate_group_id": primary.get("duplicate_group_id", ""),
                "event_id": primary.get("event_id", ""),
            })
        return candidates

    @staticmethod
    def _exclude_cross_split_duplicates(candidates: list[dict]) -> tuple[list[dict], list[dict]]:
        priority = {"train": 0, "validation": 1, "test": 2, "": 3}
        ordered = sorted(
            candidates,
            key=lambda row: (
                priority.get(row["split"], 4),
                row["company"],
                row["article_id"],
            ),
        )
        identity_splits: dict[str, str] = {}
        retained, excluded = [], []
        for row in ordered:
            identities = [row["article_id"]]
            if row["canonical_url"]:
                identities.append(row["canonical_url"])
            prior_splits = {identity_splits[item] for item in identities if item in identity_splits}
            if prior_splits - {row["split"]}:
                excluded.append(row)
                continue
            retained.append(row)
            for identity in identities:
                identity_splits[identity] = row["split"]
        return retained, excluded

    @staticmethod
    def _validate_split_protocol(acquisition: dict, split_protocol: dict | None) -> None:
        if not split_protocol:
            return
        period = split_protocol["dataset_period"]
        if (
            acquisition.get("query_from") != period["from"]
            or acquisition.get("query_to") != period["to"]
        ):
            raise ValueError("Acquisition dates do not match the frozen split protocol")
        stage = split_protocol["stage"]
        splits = split_protocol["splits"]
        expected = (
            {company for companies in splits.values() for company in companies}
            if stage == "all"
            else set(splits[stage])
        )
        if set(acquisition.get("companies", [])) != expected:
            raise ValueError("Acquisition companies do not match the frozen split stage")

    @staticmethod
    def _parse_literal(value: str | None, expected_type: type) -> list | dict:
        try:
            parsed = ast.literal_eval(value or "")
        except (SyntaxError, ValueError) as exc:
            raise ValueError(f"Invalid serialized metadata value: {value!r}") from exc
        if not isinstance(parsed, expected_type):
            raise ValueError(
                f"Expected {expected_type.__name__} metadata value, "
                f"got {type(parsed).__name__}"
            )
        return parsed

    @staticmethod
    def _integer(value: str | None) -> int:
        try:
            return int(value or 0)
        except ValueError as exc:
            raise ValueError(f"Invalid integer metadata value: {value!r}") from exc

    @staticmethod
    def _content_locator(row: dict, article_id: str) -> str:
        ticker = row.get("query_ticker", "").replace(".", "_")
        window = f"{row.get('query_from', '')}__{row.get('query_to', '')}"
        return f"{row.get('company', '')}/{ticker}/{window}#{article_id}"

    @staticmethod
    def _csv_row(row: dict) -> dict:
        result = dict(row)
        result["risk_families"] = "|".join(row["risk_families"])
        result["risk_match_terms"] = json.dumps(
            row["risk_match_terms"],
            ensure_ascii=False,
            sort_keys=True,
        )
        result["query_tickers"] = "|".join(row["query_tickers"])
        result["source_windows"] = "|".join(row["source_windows"])
        result["restricted_content_locators"] = "|".join(row["restricted_content_locators"])
        return result
