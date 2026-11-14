from __future__ import annotations

from collections import Counter
from pathlib import Path

from .common import digest, file_sha256, now_utc, write_csv, write_json
from .risk_news_review_sheet import (
    REVIEW_FIELDS,
    REVIEW_SHEET_FIELDS,
    read_review_csv,
    reviewer_slug,
)


class RiskNewsCalibrationSampler:
    """Build identical, reproducible calibration sheets for independent annotators."""

    ALGORITHM_VERSION = "company_family_year_content_duplicate_greedy_v1"
    TARGET_FAMILIES = ("critical_suppliers", "cybersecurity")
    CONTENT_STATES = ("full", "partial", "summary_only")

    def __init__(self, *, seed: str = "mag7-risk-calibration-2021-2026-v1"):
        if not seed.strip():
            raise ValueError("Calibration seed must not be empty")
        self.seed = seed

    def build(
        self,
        *,
        review_path: Path,
        candidates_path: Path,
        output_dir: Path,
        annotators: list[str],
        sample_size: int = 40,
    ) -> dict:
        annotators = self._validate_annotators(annotators)
        review_rows = read_review_csv(review_path)
        candidate_rows = read_review_csv(candidates_path)
        self._validate_sources(review_rows, candidate_rows)

        candidate_by_relation = {
            self._key(row): row
            for row in candidate_rows
        }
        companies = sorted({row["company"] for row in review_rows})
        strata = [
            (company, family)
            for company in companies
            for family in self.TARGET_FAMILIES
        ]
        if sample_size <= 0 or sample_size % len(strata):
            raise ValueError(
                f"sample_size must be a positive multiple of {len(strata)} strata"
            )
        per_stratum = sample_size // len(strata)

        selected = []
        selected_keys = set()
        for company, family in strata:
            available = [
                row
                for row in review_rows
                if row["company"] == company
                and family in self._families(row["proposed_risk_families"])
                and self._key(row) not in selected_keys
            ]
            if len(available) < per_stratum:
                raise ValueError(
                    f"Insufficient candidates for calibration stratum {company}:{family}"
                )
            chosen = self._choose_stratum(
                available,
                candidate_by_relation,
                company=company,
                family=family,
                quota=per_stratum,
            )
            for row in chosen:
                selected_keys.add(self._key(row))
                selected.append({
                    "row": row,
                    "designated_family": family,
                    "source_review_order": int(row["review_order"]),
                })

        selected.sort(key=lambda item: digest(
            f"{self.seed}|final-order|{item['row']['company']}|{item['row']['article_id']}"
        ))
        output_dir.mkdir(parents=True, exist_ok=True)
        base_rows = []
        manifest_rows = []
        for order, item in enumerate(selected, start=1):
            source = item["row"]
            candidate = candidate_by_relation[self._key(source)]
            row = dict(source)
            row["review_order"] = order
            row["reviewer"] = ""
            base_rows.append(row)
            manifest_rows.append({
                "calibration_order": order,
                "source_review_order": item["source_review_order"],
                "article_id": row["article_id"],
                "company": row["company"],
                "designated_family": item["designated_family"],
                "proposed_risk_families": row["proposed_risk_families"],
                "published_year": row["published_at_utc"][:4],
                "content_available": row["content_available"],
                "duplicate_group_id": candidate.get("duplicate_group_id", ""),
            })

        base_path = output_dir / f"calibration_sample_{sample_size}.csv"
        self._protect_output(base_path, expected_reviewer="")
        write_csv(base_path, list(REVIEW_SHEET_FIELDS), base_rows)
        annotator_artifacts = {}
        for annotator in annotators:
            slug = self._slug(annotator)
            path = output_dir / f"calibration_sample_{sample_size}_{slug}.csv"
            self._protect_output(path, expected_reviewer=annotator)
            rows = [{**row, "reviewer": annotator} for row in base_rows]
            write_csv(path, list(REVIEW_SHEET_FIELDS), rows)
            annotator_artifacts[slug] = {
                "reviewer": annotator,
                "path": str(path),
                "sha256": file_sha256(path),
            }

        actual_families = Counter(
            family
            for row in base_rows
            for family in self._families(row["proposed_risk_families"])
        )
        duplicate_ids = [
            row["duplicate_group_id"]
            for row in manifest_rows
            if row["duplicate_group_id"]
        ]
        manifest = {
            "created_at_utc": now_utc(),
            "purpose": "independent_human_annotation_calibration",
            "algorithm": self.ALGORITHM_VERSION,
            "seed": self.seed,
            "sample_size": sample_size,
            "source": {
                "review_csv": str(review_path),
                "review_csv_sha256": file_sha256(review_path),
                "candidates_csv": str(candidates_path),
                "candidates_csv_sha256": file_sha256(candidates_path),
            },
            "selection_design": {
                "companies": companies,
                "target_families_in_selection_order": list(self.TARGET_FAMILIES),
                "quota_per_company_family_stratum": per_stratum,
                "preferred_content_per_stratum": self._content_plan(per_stratum),
                "content_fallback": (
                    "use the highest-ranked remaining row when a preferred content state "
                    "is unavailable in the stratum"
                ),
                "within_stratum_priority": [
                    "new published year",
                    "at least one duplicate-group relation where available",
                    "seeded SHA-256 rank",
                ],
                "final_order": "seeded SHA-256 rank independent of stratum order",
            },
            "counts": {
                "by_company": dict(sorted(Counter(
                    row["company"] for row in base_rows
                ).items())),
                "by_designated_family": dict(sorted(Counter(
                    row["designated_family"] for row in manifest_rows
                ).items())),
                "by_proposed_family_activation": dict(sorted(actual_families.items())),
                "by_year": dict(sorted(Counter(
                    row["published_year"] for row in manifest_rows
                ).items())),
                "by_content_availability": dict(sorted(Counter(
                    row["content_available"] for row in manifest_rows
                ).items())),
                "duplicate_group_rows": len(duplicate_ids),
                "distinct_duplicate_groups": len(set(duplicate_ids)),
            },
            "artifacts": {
                "base": {
                    "path": str(base_path),
                    "sha256": file_sha256(base_path),
                },
                "annotators": annotator_artifacts,
            },
            "rows": manifest_rows,
        }
        manifest_path = output_dir / f"calibration_sample_{sample_size}_manifest.json"
        write_json(manifest_path, manifest)
        manifest["manifest_path"] = str(manifest_path)
        manifest["manifest_sha256"] = file_sha256(manifest_path)
        return manifest

    def _choose_stratum(
        self,
        rows: list[dict],
        candidate_by_relation: dict[tuple[str, str], dict],
        *,
        company: str,
        family: str,
        quota: int,
    ) -> list[dict]:
        remaining = list(rows)
        chosen = []
        seen_years = set()
        duplicate_selected = False
        for slot, desired_content in enumerate(self._content_plan(quota), start=1):
            slots_left = quota - slot + 1
            duplicate_rows = [
                row for row in remaining
                if candidate_by_relation[self._key(row)].get("duplicate_group_id")
            ]
            if slots_left == 1 and not duplicate_selected and duplicate_rows:
                pool = duplicate_rows
            else:
                matching_content = [
                    row for row in remaining
                    if row["content_available"] == desired_content
                ]
                pool = matching_content or remaining
            pool.sort(key=lambda row: (
                row["published_at_utc"][:4] in seen_years,
                not (
                    not duplicate_selected
                    and bool(candidate_by_relation[self._key(row)].get("duplicate_group_id"))
                ),
                digest(
                    f"{self.seed}|{company}|{family}|{desired_content}|{row['article_id']}"
                ),
            ))
            selected = pool[0]
            chosen.append(selected)
            remaining.remove(selected)
            seen_years.add(selected["published_at_utc"][:4])
            duplicate_selected = duplicate_selected or bool(
                candidate_by_relation[self._key(selected)].get("duplicate_group_id")
            )
        return chosen

    @staticmethod
    def _content_plan(quota: int) -> list[str]:
        if quota == 1:
            return ["full"]
        if quota == 2:
            return ["partial", "full"]
        return ["summary_only", "partial"] + ["full"] * (quota - 2)

    @classmethod
    def _validate_sources(cls, review_rows: list[dict], candidate_rows: list[dict]) -> None:
        if not review_rows or not candidate_rows:
            raise ValueError("Calibration sources must not be empty")
        candidate_relations = {cls._key(row) for row in candidate_rows}
        if len(candidate_relations) != len(candidate_rows):
            raise ValueError("Candidate source contains duplicate article-company relations")
        for row in review_rows:
            if cls._key(row) not in candidate_relations:
                raise ValueError(f"Review relation absent from candidate source: {cls._key(row)}")
            if row["review_status"] != "pending":
                raise ValueError("Calibration source must contain only pending rows")
            if any(row.get(field, "") for field in REVIEW_FIELDS[1:]):
                raise ValueError("Calibration source must not contain annotations")
            families = cls._families(row["proposed_risk_families"])
            if not families or families - set(cls.TARGET_FAMILIES):
                raise ValueError(f"Unexpected proposed risk families: {sorted(families)}")
            if row["content_available"] not in cls.CONTENT_STATES:
                raise ValueError("Unexpected content availability value")

    @staticmethod
    def _validate_annotators(annotators: list[str]) -> list[str]:
        cleaned = [name.strip() for name in annotators if name.strip()]
        if not cleaned or len({name.casefold() for name in cleaned}) != len(cleaned):
            raise ValueError("Annotator names must be non-empty and unique")
        slugs = [RiskNewsCalibrationSampler._slug(name) for name in cleaned]
        if len(set(slugs)) != len(slugs):
            raise ValueError("Annotator names must produce unique file slugs")
        return cleaned

    @staticmethod
    def _protect_output(path: Path, *, expected_reviewer: str) -> None:
        if not path.exists():
            return
        for row in read_review_csv(path):
            if row.get("review_status", "pending") != "pending":
                raise ValueError(f"Refusing to overwrite annotated calibration file: {path}")
            if any(row.get(field, "") for field in REVIEW_FIELDS[1:-2]):
                raise ValueError(f"Refusing to overwrite annotated calibration file: {path}")
            if row.get("reviewer", "") != expected_reviewer or row.get("notes", ""):
                raise ValueError(f"Refusing to overwrite annotated calibration file: {path}")

    @staticmethod
    def _families(value: str) -> set[str]:
        return {family for family in value.split("|") if family}

    @staticmethod
    def _key(row: dict) -> tuple[str, str]:
        return row["article_id"], row["company"]

    @staticmethod
    def _slug(value: str) -> str:
        return reviewer_slug(value)
