from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

from .common import file_sha256, write_csv


REVIEW_FIELDS = (
    "review_status",
    "relevant_risk_news",
    "company_relevance",
    "event_status",
    "confirmed_risk_families",
    "noise_type",
    "reviewer",
    "notes",
)

REVIEW_SHEET_FIELDS = (
    "review_order",
    "selection_provenance",
    "article_id",
    "company",
    "published_at_utc",
    "title",
    "content_available",
    "proposed_risk_families",
    "risk_match_terms",
    "link",
    *REVIEW_FIELDS,
)


def reviewer_slug(value: str) -> str:
    slug = "".join(character for character in value.casefold() if character.isalnum())
    if not slug:
        raise ValueError("Reviewer name must contain at least one alphanumeric character")
    return slug


class RiskNewsAnnotationValidator:
    """Validate the annotation fields shared by risk-news review workflows."""

    EVENT_STATES = {"materialized", "exposure", "emerging"}
    COMPANY_RELEVANCE_VALUES = {"true", "false", "unclear"}

    def __init__(
        self,
        *,
        families: set[str],
        require_company_relevance: bool = False,
        require_positive_event_status: bool = True,
        require_positive_company_relevance: bool = False,
    ):
        if not families:
            raise ValueError("At least one risk family is required")
        self.families = set(families)
        self.require_company_relevance = require_company_relevance
        self.require_positive_event_status = require_positive_event_status
        self.require_positive_company_relevance = require_positive_company_relevance

    def errors(self, row: dict[str, str], *, row_number: int) -> list[str]:
        errors = []
        if row["review_status"] != "reviewed":
            errors.append(f"row {row_number}: review is not complete")

        relevance = row["relevant_risk_news"]
        if relevance not in {"true", "false"}:
            errors.append(f"row {row_number}: relevance must be definitive")

        company_relevance = row["company_relevance"]
        allowed_company_values = set(self.COMPANY_RELEVANCE_VALUES)
        if not self.require_company_relevance:
            allowed_company_values.add("")
        if company_relevance not in allowed_company_values:
            qualifier = "" if self.require_company_relevance else "optional "
            errors.append(
                f"row {row_number}: invalid {qualifier}company_relevance"
            )

        proposed = self._pipe_set(row["proposed_risk_families"])
        confirmed = self._pipe_set(row["confirmed_risk_families"])
        if (proposed | confirmed) - self.families:
            errors.append(f"row {row_number}: unknown risk family")
        if not row["reviewer"] or not row["notes"]:
            errors.append(f"row {row_number}: reviewer and notes are required")

        if relevance == "true":
            if not confirmed:
                errors.append(f"row {row_number}: positive row has no confirmed family")
            if self.require_positive_company_relevance and company_relevance != "true":
                errors.append(
                    f"row {row_number}: positive row must have company_relevance=true"
                )
            event_status = row["event_status"]
            if self.require_positive_event_status:
                if event_status not in self.EVENT_STATES:
                    errors.append(
                        f"row {row_number}: positive row has invalid event_status"
                    )
            elif event_status and event_status not in self.EVENT_STATES:
                errors.append(f"row {row_number}: invalid optional event_status")
            if row["noise_type"]:
                errors.append(f"row {row_number}: positive row has noise_type")
        elif relevance == "false":
            if confirmed or row["event_status"]:
                errors.append(
                    f"row {row_number}: negative row has positive-only annotations"
                )
            if not row["noise_type"]:
                errors.append(f"row {row_number}: negative row has no noise_type")
        return errors

    @staticmethod
    def _pipe_set(value: str) -> set[str]:
        return {item for item in value.split("|") if item}


def read_review_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return [
            {key: (value or "").strip() for key, value in row.items()}
            for row in csv.DictReader(stream)
        ]


def protect_pending_annotations(path: Path, *, error_message: str) -> None:
    """Allow regeneration only while an existing review sheet is still untouched."""
    if not path.exists():
        return
    for row in read_review_csv(path):
        if row.get("review_status", "pending").casefold() != "pending":
            raise ValueError(error_message)
        if any(row.get(field, "") for field in REVIEW_FIELDS[1:]):
            raise ValueError(error_message)


class PackagedRiskNewsReviewBuilder:
    """Create a bodyless annotation sheet from a packaged candidate CSV."""

    REQUIRED_SOURCE_FIELDS = {
        "dataset_id",
        "selection_rank",
        "article_id",
        "company",
        "published_at_utc",
        "title",
        "content_available",
        "risk_families",
        "risk_match_terms",
        "link",
        "review_status",
    }

    def build(self, candidates_path: Path, output_path: Path) -> dict:
        protect_pending_annotations(
            output_path,
            error_message="Refusing to overwrite an annotated packaged-candidate CSV",
        )
        source_rows = read_review_csv(candidates_path)
        if not source_rows:
            raise ValueError("The packaged candidate CSV contains no rows")
        missing = self.REQUIRED_SOURCE_FIELDS - set(source_rows[0])
        if missing:
            raise ValueError(f"Candidate CSV is missing required fields: {sorted(missing)}")

        dataset_ids = {row["dataset_id"] for row in source_rows}
        if "" in dataset_ids or len(dataset_ids) != 1:
            raise ValueError("Candidate CSV must contain exactly one non-empty dataset_id")
        dataset_id = next(iter(dataset_ids))

        ranked_rows = []
        seen_ranks = set()
        seen_relations = set()
        for source in source_rows:
            if source["review_status"] != "candidate":
                raise ValueError("Packaged source rows must have review_status=candidate")
            try:
                rank = int(source["selection_rank"])
            except ValueError as exc:
                raise ValueError("selection_rank values must be integers") from exc
            if rank <= 0 or rank in seen_ranks:
                raise ValueError("selection_rank values must be unique positive integers")
            relation = source["article_id"], source["company"]
            if not all(relation) or relation in seen_relations:
                raise ValueError(f"Duplicate or incomplete article-company relation: {relation}")
            seen_ranks.add(rank)
            seen_relations.add(relation)
            ranked_rows.append((rank, source))

        ranked_rows.sort(key=lambda item: item[0])
        if [rank for rank, _ in ranked_rows] != list(range(1, len(ranked_rows) + 1)):
            raise ValueError("selection_rank values must be contiguous from 1")

        rows = [
            {
                "review_order": rank,
                "selection_provenance": dataset_id,
                "article_id": source["article_id"],
                "company": source["company"],
                "published_at_utc": source["published_at_utc"],
                "title": source["title"],
                "content_available": source["content_available"],
                "proposed_risk_families": source["risk_families"],
                "risk_match_terms": source["risk_match_terms"],
                "link": source["link"],
                "review_status": "pending",
                "relevant_risk_news": "",
                "company_relevance": "",
                "event_status": "",
                "confirmed_risk_families": "",
                "noise_type": "",
                "reviewer": "",
                "notes": "",
            }
            for rank, source in ranked_rows
        ]
        write_csv(output_path, list(REVIEW_SHEET_FIELDS), rows)
        family_counts = Counter(
            family
            for row in rows
            for family in row["proposed_risk_families"].split("|")
            if family
        )
        return {
            "dataset_id": dataset_id,
            "source": str(candidates_path),
            "source_sha256": file_sha256(candidates_path),
            "output": str(output_path),
            "output_sha256": file_sha256(output_path),
            "rows": len(rows),
            "pending": len(rows),
            "by_company": dict(sorted(Counter(row["company"] for row in rows).items())),
            "by_family_activation": dict(sorted(family_counts.items())),
        }
