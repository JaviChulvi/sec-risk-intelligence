from __future__ import annotations

from collections import Counter
from pathlib import Path

from .common import file_sha256, write_csv
from .local_articles import read_normalized_articles
from .risk_filter import RiskFamilyFilter
from .risk_news_review_sheet import (
    REVIEW_FIELDS as ANNOTATION_FIELDS,
    protect_pending_annotations,
)


class RevisedRiskNewsCandidateReviewBuilder:
    """Export only candidates newly introduced by the revised local risk filter."""

    REVIEW_FIELDS = ANNOTATION_FIELDS

    def __init__(self, config: dict):
        self.risk_filter = RiskFamilyFilter(
            config["risk_rules"],
            config.get("risk_filter"),
        )

    def build(self, normalized_root: Path, output_path: Path) -> dict:
        self._protect_existing_annotations(output_path)
        articles, files = read_normalized_articles(normalized_root)
        rows = []
        for article in articles.values():
            stored_families = set(article.risk_family_candidates)
            revised_matches = self.risk_filter.apply(article)
            if not revised_matches or stored_families:
                continue
            rows.append({
                "review_order": 0,
                "selection_provenance": "revised_filter_new_candidate",
                "article_id": article.article_id,
                "company": article.company,
                "published_at_utc": article.published_at_utc or "",
                "title": article.title,
                "content_available": article.content_available,
                "proposed_risk_families": "|".join(sorted(revised_matches)),
                "risk_match_terms": repr(revised_matches),
                "link": article.link,
                "review_status": "pending",
                "relevant_risk_news": "",
                "company_relevance": "",
                "event_status": "",
                "confirmed_risk_families": "",
                "noise_type": "",
                "reviewer": "",
                "notes": "",
            })
        rows.sort(key=lambda row: (
            row["company"],
            row["published_at_utc"],
            row["article_id"],
        ))
        for order, row in enumerate(rows, start=1):
            row["review_order"] = order
        if not rows:
            raise ValueError("The revised filter produced no new candidates")
        write_csv(output_path, list(rows[0]), rows)
        family_counts = Counter(
            family
            for row in rows
            for family in row["proposed_risk_families"].split("|")
        )
        return {
            "output": str(output_path),
            "output_sha256": file_sha256(output_path),
            "rows": len(rows),
            "pending": len(rows),
            "by_company": dict(sorted(Counter(row["company"] for row in rows).items())),
            "by_family_activation": dict(sorted(family_counts.items())),
            "normalized_cache_files": len(files),
            "network_calls": 0,
        }

    @classmethod
    def _protect_existing_annotations(cls, path: Path) -> None:
        protect_pending_annotations(
            path,
            error_message="Refusing to overwrite an annotated revised-candidate CSV",
        )
