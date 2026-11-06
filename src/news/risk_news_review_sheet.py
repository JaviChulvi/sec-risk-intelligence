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
