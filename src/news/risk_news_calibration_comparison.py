from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .common import file_sha256, load_json, now_utc, write_json
from .risk_news_review_sheet import (
    REVIEW_FIELDS,
    REVIEW_SHEET_FIELDS,
    RiskNewsAnnotationValidator,
    read_review_csv,
)


@dataclass(frozen=True)
class AnnotatorCalibrationReview:
    path: Path
    reviewer: str
    rows: tuple[dict[str, str], ...]


class RiskNewsCalibrationComparator:
    """Validate aligned calibration reviews before agreement is measured."""

    TARGET_FAMILIES = {"critical_suppliers", "cybersecurity"}
    COMPARISON_FIELDS = (
        "relevant_risk_news",
        "company_relevance",
        "event_status",
        "confirmed_risk_families",
        "noise_type",
    )
    FIELD_SCOPES = {
        "relevant_risk_news": "all_rows",
        "company_relevance": "all_rows",
        "event_status": "any_annotator_positive",
        "confirmed_risk_families": "any_annotator_positive",
        "noise_type": "any_annotator_negative",
    }
    IMMUTABLE_FIELDS = tuple(
        field for field in REVIEW_SHEET_FIELDS if field not in REVIEW_FIELDS
    )

    def __init__(self, *, families: set[str] | None = None):
        self.families = set(self.TARGET_FAMILIES if families is None else families)
        self.annotation_validator = RiskNewsAnnotationValidator(
            families=self.families,
            require_company_relevance=True,
            require_positive_company_relevance=True,
        )

    def validate_inputs(
        self,
        *,
        manifest_path: Path,
        review_paths: list[Path],
    ) -> dict:
        manifest, reviews = self._load_inputs(manifest_path, review_paths)
        return self._input_summary(manifest_path, manifest, reviews)

    def compare(
        self,
        *,
        manifest_path: Path,
        review_paths: list[Path],
    ) -> dict:
        manifest, reviews = self._load_inputs(manifest_path, review_paths)
        field_counts = {
            field: {"eligible_rows": 0, "agreed_rows": 0}
            for field in self.COMPARISON_FIELDS
        }
        discrepancies = []
        for row_index, reference_row in enumerate(reviews[0].rows):
            rows = [review.rows[row_index] for review in reviews]
            discrepant_fields = {}
            for field in self.COMPARISON_FIELDS:
                if not self._field_is_applicable(field, rows):
                    continue
                field_counts[field]["eligible_rows"] += 1
                values = {
                    review.reviewer: self._comparison_value(field, row[field])
                    for review, row in zip(reviews, rows)
                }
                if len(set(values.values())) == 1:
                    field_counts[field]["agreed_rows"] += 1
                else:
                    discrepant_fields[field] = values
            if discrepant_fields:
                discrepancies.append({
                    "review_order": int(reference_row["review_order"]),
                    "article_id": reference_row["article_id"],
                    "company": reference_row["company"],
                    "published_at_utc": reference_row["published_at_utc"],
                    "title": reference_row["title"],
                    "content_available": reference_row["content_available"],
                    "proposed_risk_families": reference_row["proposed_risk_families"],
                    "risk_match_terms": reference_row["risk_match_terms"],
                    "link": reference_row["link"],
                    "discrepant_fields": discrepant_fields,
                    "annotations_by_reviewer": {
                        review.reviewer: {
                            field: self._comparison_value(field, row[field])
                            for field in self.COMPARISON_FIELDS
                        }
                        for review, row in zip(reviews, rows)
                    },
                    "notes_by_reviewer": {
                        review.reviewer: row["notes"]
                        for review, row in zip(reviews, rows)
                    },
                })

        field_agreement = {}
        for field, counts in field_counts.items():
            eligible = counts["eligible_rows"]
            agreed = counts["agreed_rows"]
            field_agreement[field] = {
                "scope": self.FIELD_SCOPES[field],
                "eligible_rows": eligible,
                "agreed_rows": agreed,
                "discrepant_rows": eligible - agreed,
                "exact_agreement": agreed / eligible if eligible else None,
            }

        sample_size = manifest["sample_size"]
        return {
            "inputs": self._input_summary(manifest_path, manifest, reviews),
            "agreement": {
                "rows": {
                    "total": sample_size,
                    "full_agreement": sample_size - len(discrepancies),
                    "with_discrepancies": len(discrepancies),
                    "full_agreement_rate": (
                        (sample_size - len(discrepancies)) / sample_size
                    ),
                },
                "fields": field_agreement,
            },
            "discrepancies": discrepancies,
        }

    def build(
        self,
        *,
        manifest_path: Path,
        review_paths: list[Path],
        output_path: Path,
    ) -> dict:
        result = {
            "generated_at_utc": now_utc(),
            **self.compare(
                manifest_path=manifest_path,
                review_paths=review_paths,
            ),
        }
        write_json(output_path, result)
        return result

    @staticmethod
    def _input_summary(
        manifest_path: Path,
        manifest: dict,
        reviews: tuple[AnnotatorCalibrationReview, ...],
    ) -> dict:
        return {
            "manifest": str(manifest_path),
            "manifest_sha256": file_sha256(manifest_path),
            "sample_size": manifest["sample_size"],
            "reviewers": [review.reviewer for review in reviews],
            "review_files": [
                {
                    "reviewer": review.reviewer,
                    "path": str(review.path),
                    "sha256": file_sha256(review.path),
                }
                for review in reviews
            ],
        }

    @classmethod
    def _field_is_applicable(
        cls,
        field: str,
        rows: list[dict[str, str]],
    ) -> bool:
        scope = cls.FIELD_SCOPES[field]
        if scope == "all_rows":
            return True
        relevance = {row["relevant_risk_news"] for row in rows}
        if scope == "any_annotator_positive":
            return "true" in relevance
        if scope == "any_annotator_negative":
            return "false" in relevance
        raise ValueError(f"Unknown comparison scope: {scope}")

    @staticmethod
    def _comparison_value(field: str, value: str) -> str:
        if field == "confirmed_risk_families":
            return "|".join(sorted({item for item in value.split("|") if item}))
        return value

    def _load_inputs(
        self,
        manifest_path: Path,
        review_paths: list[Path],
    ) -> tuple[dict, tuple[AnnotatorCalibrationReview, ...]]:
        manifest = load_json(manifest_path)
        manifest_rows = manifest.get("rows")
        sample_size = manifest.get("sample_size")
        if manifest.get("purpose") != "independent_human_annotation_calibration":
            raise ValueError("Manifest is not an annotation calibration manifest")
        if not isinstance(sample_size, int) or sample_size <= 0:
            raise ValueError("Manifest sample_size must be a positive integer")
        if not isinstance(manifest_rows, list) or len(manifest_rows) != sample_size:
            raise ValueError("Manifest rows do not match sample_size")
        if len(review_paths) < 2:
            raise ValueError("At least two annotator review files are required")
        if len(set(review_paths)) != len(review_paths):
            raise ValueError("Annotator review file paths must be unique")

        reviews = tuple(
            self._load_review(path, manifest_rows)
            for path in review_paths
        )
        reviewers = [review.reviewer.casefold() for review in reviews]
        if len(set(reviewers)) != len(reviewers):
            raise ValueError("Annotator reviewer names must be unique")
        self._validate_alignment(reviews)
        return manifest, reviews

    def _load_review(
        self,
        path: Path,
        manifest_rows: list[dict],
    ) -> AnnotatorCalibrationReview:
        rows = read_review_csv(path)
        if not rows:
            raise ValueError(f"Calibration review is empty: {path}")
        missing = set(REVIEW_SHEET_FIELDS) - set(rows[0])
        if missing:
            raise ValueError(
                f"Calibration review {path} is missing fields: {sorted(missing)}"
            )

        errors = []
        seen_relations = set()
        orders = []
        for number, row in enumerate(rows, start=2):
            relation = self._key(row)
            if not all(relation) or relation in seen_relations:
                errors.append(
                    f"row {number}: duplicate or incomplete article-company relation"
                )
            seen_relations.add(relation)
            try:
                orders.append(int(row["review_order"]))
            except ValueError:
                errors.append(f"row {number}: invalid review_order")
            errors.extend(self.annotation_validator.errors(row, row_number=number))

        if len(rows) != len(manifest_rows):
            errors.append(
                f"row count {len(rows)} differs from manifest count {len(manifest_rows)}"
            )
        if orders != list(range(1, len(rows) + 1)):
            errors.append("review_order must be the consecutive sequence 1..N")
        if len(rows) == len(manifest_rows):
            errors.extend(self._manifest_alignment_errors(rows, manifest_rows))

        reviewer_values = {row["reviewer"] for row in rows if row["reviewer"]}
        if len(reviewer_values) != 1:
            errors.append("reviewer must be one consistent non-empty value per file")
        if errors:
            raise ValueError(
                f"Invalid calibration annotations in {path}:\n- " + "\n- ".join(errors)
            )
        return AnnotatorCalibrationReview(
            path=path,
            reviewer=next(iter(reviewer_values)),
            rows=tuple(rows),
        )

    @classmethod
    def _manifest_alignment_errors(
        cls,
        rows: list[dict[str, str]],
        manifest_rows: list[dict],
    ) -> list[str]:
        errors = []
        for number, (row, expected) in enumerate(zip(rows, manifest_rows), start=2):
            expected_values = {
                "review_order": str(expected.get("calibration_order", "")),
                "article_id": str(expected.get("article_id", "")),
                "company": str(expected.get("company", "")),
                "content_available": str(expected.get("content_available", "")),
                "proposed_risk_families": str(
                    expected.get("proposed_risk_families", "")
                ),
            }
            for field, value in expected_values.items():
                if row[field] != value:
                    errors.append(f"row {number}: {field} differs from manifest")
            if row["published_at_utc"][:4] != str(expected.get("published_year", "")):
                errors.append(f"row {number}: published year differs from manifest")
        return errors

    @classmethod
    def _validate_alignment(
        cls,
        reviews: tuple[AnnotatorCalibrationReview, ...],
    ) -> None:
        reference = reviews[0]
        errors = []
        for review in reviews[1:]:
            for number, (left, right) in enumerate(
                zip(reference.rows, review.rows),
                start=2,
            ):
                for field in cls.IMMUTABLE_FIELDS:
                    if left[field] != right[field]:
                        errors.append(
                            f"{review.path} row {number}: immutable field {field} "
                            f"differs from {reference.path}"
                        )
        if errors:
            raise ValueError("Calibration review files are not aligned:\n- " + "\n- ".join(errors))

    @staticmethod
    def _key(row: dict[str, str]) -> tuple[str, str]:
        return row["article_id"], row["company"]
