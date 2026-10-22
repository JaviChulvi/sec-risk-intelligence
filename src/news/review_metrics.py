from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

from .common import file_sha256, load_json, now_utc, write_json


class ReviewMetricsBuilder:
    """Validate an article-company review sample and derive auditable metrics."""

    REQUIRED_FIELDS = {
        "article_id",
        "company",
        "content_available",
        "risk_family_candidates",
        "selection_stratum",
        "review_status",
        "relevant_event",
        "noise_type",
        "episode_id",
        "reviewer",
        "notes",
    }
    STRATA = {"risk_candidate", "other"}
    REVIEW_STATUSES = {"pending", "reviewed"}
    RELEVANCE_VALUES = {"true", "false", "unclear"}

    def build(self, review_path: Path, manifest_path: Path, output: Path) -> dict:
        rows = self._read_rows(review_path)
        self._validate(rows)
        manifest = load_json(manifest_path)
        metrics = self._summarize(rows, manifest)
        result = {
            "generated_at_utc": now_utc(),
            "review_file": str(review_path),
            "review_file_sha256": file_sha256(review_path),
            "manifest_file": str(manifest_path),
            "manifest_file_sha256": file_sha256(manifest_path),
            "review_unit": "article_company_relation",
            **metrics,
        }
        write_json(output, result)
        return result

    def _read_rows(self, path: Path) -> list[dict[str, str]]:
        with path.open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            missing = sorted(self.REQUIRED_FIELDS - set(reader.fieldnames or []))
            if missing:
                raise ValueError(f"Review CSV is missing fields: {', '.join(missing)}")
            return [
                {key: (value or "").strip() for key, value in row.items()}
                for row in reader
            ]

    def _validate(self, rows: list[dict[str, str]]) -> None:
        if not rows:
            raise ValueError("Review CSV contains no rows")
        seen: set[tuple[str, str]] = set()
        errors: list[str] = []
        for number, row in enumerate(rows, start=2):
            relation = (row["article_id"], row["company"])
            if not all(relation):
                errors.append(f"row {number}: article_id and company are required")
            elif relation in seen:
                errors.append(f"row {number}: duplicate article-company relation {relation}")
            seen.add(relation)

            stratum = row["selection_stratum"].casefold()
            status = row["review_status"].casefold()
            relevance = row["relevant_event"].casefold()
            if stratum not in self.STRATA:
                errors.append(f"row {number}: invalid selection_stratum {stratum!r}")
            if status not in self.REVIEW_STATUSES:
                errors.append(f"row {number}: invalid review_status {status!r}")
                continue
            if stratum == "risk_candidate" and not row["risk_family_candidates"]:
                errors.append(f"row {number}: risk_candidate has no candidate family")
            if stratum == "other" and row["risk_family_candidates"]:
                errors.append(f"row {number}: other stratum unexpectedly has candidate families")
            if status == "reviewed":
                if relevance not in self.RELEVANCE_VALUES:
                    errors.append(f"row {number}: reviewed row has invalid relevant_event {relevance!r}")
                if not row["reviewer"]:
                    errors.append(f"row {number}: reviewed row has no reviewer")
                if not row["notes"]:
                    errors.append(f"row {number}: reviewed row has no notes")
                if relevance == "false" and not row["noise_type"]:
                    errors.append(f"row {number}: non-relevant row has no noise_type")
                if relevance == "true" and not row["episode_id"]:
                    errors.append(f"row {number}: relevant row has no episode_id")
                if relevance == "false" and row["episode_id"]:
                    errors.append(f"row {number}: non-relevant row has an episode_id")
        if errors:
            detail = "\n- ".join(errors)
            raise ValueError(f"Invalid review annotations:\n- {detail}")

    def _summarize(self, rows: list[dict[str, str]], manifest: dict) -> dict:
        reviewed = [row for row in rows if row["review_status"].casefold() == "reviewed"]
        strata = {
            name: self._stratum_metrics(rows, name)
            for name in sorted(self.STRATA)
        }
        candidate = strata["risk_candidate"]
        population = int(manifest.get("counts", {}).get("risk_candidates", 0))
        candidate_reviewed = candidate["reviewed"]
        if candidate_reviewed > population:
            raise ValueError(
                "Reviewed risk candidates exceed the manifest risk-candidate population"
            )
        unreviewed_population = population - candidate_reviewed
        upper_bound_count = candidate["relevant"] + unreviewed_population
        reviewers = Counter(row["reviewer"] for row in reviewed)
        assisted = any(
            marker in reviewer.casefold()
            for reviewer in reviewers
            for marker in ("chatgpt", "assistant", "ai-assisted", "ia-assisted")
        )
        useful_states = {"full", "partial"}
        useful_reviewed_candidates = sum(
            row["selection_stratum"].casefold() == "risk_candidate"
            and row["review_status"].casefold() == "reviewed"
            and row["content_available"].casefold() in useful_states
            for row in rows
        )
        all_candidates_reviewed = population > 0 and candidate_reviewed == population
        return {
            "rows": {
                "total": len(rows),
                "unique_article_ids": len({row["article_id"] for row in rows}),
                "reviewed": len(reviewed),
                "pending": len(rows) - len(reviewed),
            },
            "strata": strata,
            "risk_candidate_population": {
                "total": population,
                "reviewed": candidate_reviewed,
                "unreviewed": unreviewed_population,
                "review_coverage": self._ratio(candidate_reviewed, population),
                "observed_relevant_rate": self._ratio(candidate["relevant"], candidate_reviewed),
                "worst_case_relevant_count": upper_bound_count,
                "worst_case_relevant_rate": self._ratio(upper_bound_count, population),
                "useful_content_reviewed": useful_reviewed_candidates,
                "useful_content_rate_reviewed": self._ratio(useful_reviewed_candidates, candidate_reviewed),
            },
            "noise_types": dict(sorted(Counter(
                row["noise_type"] for row in reviewed if row["relevant_event"].casefold() == "false"
            ).items())),
            "risk_candidate_noise_types": dict(sorted(Counter(
                row["noise_type"]
                for row in reviewed
                if row["selection_stratum"].casefold() == "risk_candidate"
                and row["relevant_event"].casefold() == "false"
            ).items())),
            "reviewers": dict(sorted(reviewers.items())),
            "methodology": {
                "selection": (
                    "all_risk_candidates_plus_deterministic_other_sample"
                    if all_candidates_reviewed
                    else "deterministic_stratified_sample"
                ),
                "independent_human_review": not assisted,
                "interpretation": (
                    "Diagnostic review metrics; not an independent human gold standard"
                    if assisted else "Human-reviewed sample metrics"
                ),
            },
        }

    def _stratum_metrics(self, rows: list[dict[str, str]], name: str) -> dict:
        selected = [row for row in rows if row["selection_stratum"].casefold() == name]
        reviewed = [row for row in selected if row["review_status"].casefold() == "reviewed"]
        relevance = Counter(row["relevant_event"].casefold() for row in reviewed)
        return {
            "total": len(selected),
            "reviewed": len(reviewed),
            "pending": len(selected) - len(reviewed),
            "relevant": relevance["true"],
            "not_relevant": relevance["false"],
            "unclear": relevance["unclear"],
            "observed_relevant_rate": self._ratio(relevance["true"], len(reviewed)),
        }

    @staticmethod
    def _ratio(numerator: int, denominator: int) -> float | None:
        return numerator / denominator if denominator else None
