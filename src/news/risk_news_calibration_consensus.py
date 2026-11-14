from __future__ import annotations

from pathlib import Path

from .common import file_sha256, load_json, write_csv
from .risk_news_calibration_comparison import RiskNewsCalibrationComparator
from .risk_news_review_sheet import read_review_csv, reviewer_slug


class RiskNewsCalibrationConsensusBuilder:
    """Create a protected adjudication sheet from calibration discrepancies."""

    BASE_FIELDS = (
        "consensus_order",
        "calibration_order",
        "article_id",
        "company",
        "published_at_utc",
        "title",
        "content_available",
        "proposed_risk_families",
        "risk_match_terms",
        "link",
        "discrepant_fields",
    )
    CONSENSUS_FIELDS = tuple(
        f"consensus_{field}"
        for field in RiskNewsCalibrationComparator.COMPARISON_FIELDS
    )
    WORKFLOW_FIELDS = (
        "consensus_status",
        "adjudicator",
        "consensus_notes",
    )

    def build(self, *, comparison_path: Path, output_path: Path) -> dict:
        if comparison_path.resolve() == output_path.resolve():
            raise ValueError("Consensus output must differ from the comparison JSON")
        comparison = load_json(comparison_path)
        reviewers, reviewer_slugs = self._validate_comparison(comparison)
        fields = self._fields(reviewers, reviewer_slugs)
        rows = [
            self._consensus_row(
                order,
                discrepancy,
                reviewers=reviewers,
                reviewer_slugs=reviewer_slugs,
            )
            for order, discrepancy in enumerate(comparison["discrepancies"], start=1)
        ]
        self._protect_output(output_path, fields, rows)
        write_csv(output_path, fields, rows)
        return {
            "comparison": str(comparison_path),
            "comparison_sha256": file_sha256(comparison_path),
            "output": str(output_path),
            "output_sha256": file_sha256(output_path),
            "rows": len(rows),
            "status": {"pending": len(rows)},
            "reviewer_columns": {
                reviewer: reviewer_slugs[reviewer]
                for reviewer in reviewers
            },
        }

    @classmethod
    def _fields(cls, reviewers: list[str], reviewer_slugs: dict[str, str]) -> list[str]:
        reviewer_fields = [
            f"{reviewer_slugs[reviewer]}__{field}"
            for reviewer in reviewers
            for field in (*RiskNewsCalibrationComparator.COMPARISON_FIELDS, "notes")
        ]
        return [
            *cls.BASE_FIELDS,
            *reviewer_fields,
            *cls.CONSENSUS_FIELDS,
            *cls.WORKFLOW_FIELDS,
        ]

    @classmethod
    def _consensus_row(
        cls,
        order: int,
        discrepancy: dict,
        *,
        reviewers: list[str],
        reviewer_slugs: dict[str, str],
    ) -> dict:
        annotations = discrepancy["annotations_by_reviewer"]
        notes = discrepancy["notes_by_reviewer"]
        discrepant_fields = set(discrepancy["discrepant_fields"])
        row = {
            "consensus_order": order,
            "calibration_order": discrepancy["review_order"],
            "article_id": discrepancy["article_id"],
            "company": discrepancy["company"],
            "published_at_utc": discrepancy["published_at_utc"],
            "title": discrepancy["title"],
            "content_available": discrepancy["content_available"],
            "proposed_risk_families": discrepancy["proposed_risk_families"],
            "risk_match_terms": discrepancy["risk_match_terms"],
            "link": discrepancy["link"],
            "discrepant_fields": "|".join(
                field
                for field in RiskNewsCalibrationComparator.COMPARISON_FIELDS
                if field in discrepant_fields
            ),
            "consensus_status": "pending",
            "adjudicator": "",
            "consensus_notes": "",
        }
        for reviewer in reviewers:
            prefix = reviewer_slugs[reviewer]
            for field in RiskNewsCalibrationComparator.COMPARISON_FIELDS:
                row[f"{prefix}__{field}"] = annotations[reviewer][field]
            row[f"{prefix}__notes"] = notes[reviewer]
        for field in RiskNewsCalibrationComparator.COMPARISON_FIELDS:
            values = {annotations[reviewer][field] for reviewer in reviewers}
            row[f"consensus_{field}"] = (
                next(iter(values)) if len(values) == 1 else ""
            )
        return row

    @classmethod
    def _validate_comparison(
        cls,
        comparison: dict,
    ) -> tuple[list[str], dict[str, str]]:
        inputs = comparison.get("inputs")
        discrepancies = comparison.get("discrepancies")
        if not isinstance(inputs, dict) or not isinstance(discrepancies, list):
            raise ValueError("Comparison JSON is missing inputs or discrepancies")
        reviewers = inputs.get("reviewers")
        if not isinstance(reviewers, list) or len(reviewers) < 2:
            raise ValueError("Comparison JSON must contain at least two reviewers")
        if any(not isinstance(reviewer, str) or not reviewer.strip() for reviewer in reviewers):
            raise ValueError("Comparison reviewer names must be non-empty strings")
        if len({reviewer.casefold() for reviewer in reviewers}) != len(reviewers):
            raise ValueError("Comparison reviewer names must be unique")
        reviewer_slugs = {reviewer: reviewer_slug(reviewer) for reviewer in reviewers}
        if len(set(reviewer_slugs.values())) != len(reviewers):
            raise ValueError("Comparison reviewer names must produce unique column slugs")

        seen_orders = set()
        for index, discrepancy in enumerate(discrepancies, start=1):
            if not isinstance(discrepancy, dict):
                raise ValueError(f"Discrepancy {index} must be an object")
            order = discrepancy.get("review_order")
            if not isinstance(order, int) or order <= 0 or order in seen_orders:
                raise ValueError(f"Discrepancy {index} has invalid review_order")
            seen_orders.add(order)
            cls._validate_discrepancy(discrepancy, reviewers, index=index)
        return reviewers, reviewer_slugs

    @staticmethod
    def _validate_discrepancy(
        discrepancy: dict,
        reviewers: list[str],
        *,
        index: int,
    ) -> None:
        required = {
            "article_id",
            "company",
            "published_at_utc",
            "title",
            "content_available",
            "proposed_risk_families",
            "risk_match_terms",
            "link",
            "discrepant_fields",
            "annotations_by_reviewer",
            "notes_by_reviewer",
        }
        if required - set(discrepancy):
            raise ValueError(f"Discrepancy {index} is missing required fields")
        annotations = discrepancy["annotations_by_reviewer"]
        notes = discrepancy["notes_by_reviewer"]
        if not isinstance(annotations, dict) or not isinstance(notes, dict):
            raise ValueError(f"Discrepancy {index} has invalid reviewer data")
        if set(annotations) != set(reviewers) or set(notes) != set(reviewers):
            raise ValueError(f"Discrepancy {index} does not contain every reviewer")
        expected_fields = set(RiskNewsCalibrationComparator.COMPARISON_FIELDS)
        for reviewer in reviewers:
            if not isinstance(annotations[reviewer], dict):
                raise ValueError(
                    f"Discrepancy {index} has invalid annotations for {reviewer}"
                )
            if set(annotations[reviewer]) != expected_fields:
                raise ValueError(
                    f"Discrepancy {index} has incomplete annotations for {reviewer}"
                )
            if not isinstance(notes[reviewer], str):
                raise ValueError(f"Discrepancy {index} has invalid notes for {reviewer}")
        discrepant = discrepancy["discrepant_fields"]
        if not isinstance(discrepant, dict) or not discrepant:
            raise ValueError(f"Discrepancy {index} has no discrepant fields")
        if set(discrepant) - expected_fields:
            raise ValueError(f"Discrepancy {index} has unknown discrepant fields")
        for field in discrepant:
            expected_values = {
                reviewer: annotations[reviewer][field]
                for reviewer in reviewers
            }
            if discrepant[field] != expected_values:
                raise ValueError(
                    f"Discrepancy {index} has inconsistent values for {field}"
                )
            values = set(expected_values.values())
            if len(values) == 1:
                raise ValueError(
                    f"Discrepancy {index} marks agreed field {field} as discrepant"
                )

    @staticmethod
    def _protect_output(path: Path, fields: list[str], rows: list[dict]) -> None:
        if not path.exists():
            return
        existing = read_review_csv(path)
        expected = [
            {field: str(row.get(field, "")).strip() for field in fields}
            for row in rows
        ]
        if existing != expected:
            raise ValueError(f"Refusing to overwrite edited consensus sheet: {path}")
