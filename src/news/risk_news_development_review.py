from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

from .common import file_sha256, write_csv
from .risk_news_review_sheet import (
    REVIEW_FIELDS as ANNOTATION_FIELDS,
    protect_pending_annotations,
    read_review_csv,
)


class RiskNewsDevelopmentReviewBuilder:
    """Build labels for risk-news selection without conflating them with episode matching."""

    REVIEW_FIELDS = ANNOTATION_FIELDS

    def build(
        self,
        recent_review_path: Path,
        recent_metadata_path: Path,
        episode_review_path: Path,
        output_path: Path,
    ) -> dict:
        self._protect_existing_annotations(output_path)
        recent_metadata = self._read_metadata(recent_metadata_path)
        recent_rows = self._recent_candidates(recent_review_path, recent_metadata)
        episode_rows = self._episode_candidates(episode_review_path)
        combined = recent_rows + episode_rows
        self._reject_duplicate_relations(combined)
        combined.sort(key=lambda row: (
            row["review_status"] != "pending",
            row["company"],
            row["published_at_utc"],
            row["article_id"],
        ))
        for order, row in enumerate(combined, start=1):
            row["review_order"] = order

        fields = ["review_order"] + [key for key in combined[0] if key != "review_order"]
        write_csv(output_path, fields, combined)
        statuses = Counter(row["review_status"] for row in combined)
        provenance = Counter(row["label_provenance"] for row in combined)
        return {
            "output": str(output_path),
            "output_sha256": file_sha256(output_path),
            "rows": len(combined),
            "reviewed": statuses["reviewed"],
            "pending": statuses["pending"],
            "reused_general_negatives": provenance["general_review_reused"],
            "reused_episode_positives": provenance["episode_positive_implies_risk_news"],
            "episode_negatives_requiring_relabel": provenance["episode_negative_requires_relabel"],
        }

    @classmethod
    def _recent_candidates(cls, review_path: Path, metadata: dict) -> list[dict]:
        rows = cls._read_csv(review_path)
        result = []
        for row in rows:
            if row["selection_stratum"] != "risk_candidate":
                continue
            if row["review_status"] != "reviewed" or row["relevant_event"] not in {"true", "false"}:
                raise ValueError("Recent risk candidates require definitive general-event annotations")
            key = (row["article_id"], row["company"])
            source = metadata.get(key)
            if source is None:
                raise ValueError(f"Recent review relation is absent from metadata: {key}")
            relevant = row["relevant_event"]
            if relevant == "true":
                raise ValueError(
                    "A general positive cannot be reused without a confirmed risk family; annotate it directly"
                )
            result.append(cls._base_row(
                source=source,
                development_source="recent_general_review",
                label_provenance="general_review_reused",
                prior_episode_relevance="",
                prior_noise_type=row["noise_type"],
                prior_notes=row["notes"],
                review_status="reviewed",
                relevant_risk_news="false",
                company_relevance="",
                event_status="",
                confirmed_risk_families="",
                noise_type=row["noise_type"],
                reviewer=row["reviewer"],
                notes=row["notes"],
            ))
        return result

    @classmethod
    def _episode_candidates(cls, review_path: Path) -> list[dict]:
        rows = cls._read_csv(review_path)
        result = []
        for row in rows:
            if row["review_status"] != "reviewed" or row["relevant_to_window_episode"] not in {
                "true", "false"
            }:
                raise ValueError("Episode candidates require definitive episode annotations")
            is_episode_positive = row["relevant_to_window_episode"] == "true"
            result.append(cls._base_row(
                source={
                    **row,
                    "risk_family_candidates": row["proposed_risk_families"],
                },
                development_source="known_episode_review",
                label_provenance=(
                    "episode_positive_implies_risk_news"
                    if is_episode_positive
                    else "episode_negative_requires_relabel"
                ),
                prior_episode_relevance=row["relevant_to_window_episode"],
                prior_noise_type=row["noise_type"],
                prior_notes=row["notes"],
                review_status="reviewed" if is_episode_positive else "pending",
                relevant_risk_news="true" if is_episode_positive else "",
                company_relevance="",
                event_status="materialized" if is_episode_positive else "",
                confirmed_risk_families=row["confirmed_risk_family"] if is_episode_positive else "",
                noise_type="",
                reviewer=row["reviewer"] if is_episode_positive else "",
                notes=row["notes"] if is_episode_positive else "",
            ))
        return result

    @staticmethod
    def _base_row(
        *,
        source: dict,
        development_source: str,
        label_provenance: str,
        prior_episode_relevance: str,
        prior_noise_type: str,
        prior_notes: str,
        **annotations,
    ) -> dict:
        return {
            "development_source": development_source,
            "label_provenance": label_provenance,
            "window_episode_id": source.get("window_episode_id", ""),
            "article_id": source["article_id"],
            "company": source["company"],
            "published_at_utc": source["published_at_utc"],
            "title": source["title"],
            "content_available": source["content_available"],
            "proposed_risk_families": cls_value(source.get("risk_family_candidates", "")),
            "risk_match_terms": source.get("risk_match_terms", ""),
            "link": source.get("link", ""),
            "prior_episode_relevance": prior_episode_relevance,
            "prior_noise_type": prior_noise_type,
            "prior_notes": prior_notes,
            **annotations,
        }

    @staticmethod
    def _read_metadata(path: Path) -> dict[tuple[str, str], dict]:
        rows = RiskNewsDevelopmentReviewBuilder._read_csv(path)
        result = {}
        for row in rows:
            key = (row["article_id"], row["company"])
            if key in result:
                raise ValueError(f"Duplicate article-company relation in metadata: {key}")
            result[key] = row
        return result

    @staticmethod
    def _read_csv(path: Path) -> list[dict]:
        return read_review_csv(path)

    @staticmethod
    def _reject_duplicate_relations(rows: list[dict]) -> None:
        seen = set()
        for row in rows:
            key = row["article_id"], row["company"]
            if key in seen:
                raise ValueError(f"Duplicate development relation: {key}")
            seen.add(key)

    @classmethod
    def _protect_existing_annotations(cls, path: Path) -> None:
        protect_pending_annotations(
            path,
            error_message="Refusing to overwrite an annotated risk-news development CSV",
        )


def cls_value(value: str) -> str:
    """Normalize list-shaped metadata values to the pipe-separated review convention."""
    if not value:
        return ""
    if value.startswith("["):
        parsed = ast.literal_eval(value)
        return "|".join(parsed)
    return value
