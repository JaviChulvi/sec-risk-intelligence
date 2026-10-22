from __future__ import annotations

import ast
import csv
import json
from collections import Counter
from pathlib import Path

from .common import file_sha256, load_json, write_csv


class KnownEpisodeCandidateReviewBuilder:
    """Prepare every lexical candidate from known-episode windows for human review."""

    REVIEW_FIELDS = (
        "review_status",
        "relevant_to_window_episode",
        "confirmed_episode_id",
        "confirmed_risk_family",
        "candidate_family_correct",
        "noise_type",
        "reviewer",
        "notes",
    )

    def build(
        self,
        metadata_path: Path,
        acquisition_manifest_path: Path,
        query_manifest_path: Path,
        confirmed_review_path: Path,
        output_path: Path,
    ) -> dict:
        acquisition = load_json(acquisition_manifest_path)
        query_manifest = load_json(query_manifest_path)
        confirmed_review = load_json(confirmed_review_path)
        self._validate_provenance(acquisition, query_manifest_path)

        window_episodes = {
            self._window_key(row): row for row in query_manifest.get("windows", [])
        }
        if len(window_episodes) != len(query_manifest.get("windows", [])):
            raise ValueError("Query manifest contains duplicate windows")
        decisions = {
            row["episode_id"]: row for row in confirmed_review.get("decisions", [])
        }
        evidence_roles = self._evidence_roles(decisions)
        articles = self._read_articles(metadata_path)
        candidates = [row for row in articles if row["risk_family_candidates"]]
        expected = acquisition.get("counts", {}).get("risk_candidates")
        if expected != len(candidates):
            raise ValueError(
                f"Candidate count differs from acquisition manifest: {len(candidates)} != {expected}"
            )
        self._protect_existing_annotations(output_path)

        duplicate_sizes = Counter(row["duplicate_group_id"] or row["article_id"] for row in articles)
        event_sizes = Counter(row["event_id"] or row["article_id"] for row in articles)
        candidate_duplicate_sizes = Counter(
            row["duplicate_group_id"] or row["article_id"] for row in candidates
        )
        candidate_event_sizes = Counter(row["event_id"] or row["article_id"] for row in candidates)
        duplicate_representatives = self._representatives(candidates)
        episode_order = {
            row["episode_id"]: index for index, row in enumerate(query_manifest["windows"], start=1)
        }
        candidates.sort(key=lambda row: (
            episode_order[self._episode_for(row, window_episodes)["episode_id"]],
            row["event_id"] or row["article_id"],
            row["duplicate_group_id"] or row["article_id"],
            row["published_at_utc"],
            row["article_id"],
        ))

        rows = []
        for review_order, article in enumerate(candidates, start=1):
            window = self._episode_for(article, window_episodes)
            episode_id = window["episode_id"]
            decision = decisions.get(episode_id)
            if decision is None:
                raise ValueError(f"No confirmed episode decision for {episode_id}")
            duplicate_key = article["duplicate_group_id"] or article["article_id"]
            event_key = article["event_id"] or article["article_id"]
            rows.append({
                "review_order": review_order,
                "window_episode_id": episode_id,
                "company": article["company"],
                "expected_risk_family": window["risk_family"],
                "known_episode_recovered": str(decision["recovered"]).lower(),
                "article_id": article["article_id"],
                "published_at_utc": article["published_at_utc"],
                "title": article["title"],
                "content_available": article["content_available"],
                "content_length_words": article["content_length_words"],
                "proposed_risk_families": "|".join(article["risk_family_candidates"]),
                "risk_match_terms": article["risk_match_terms"],
                "duplicate_group_id": article["duplicate_group_id"],
                "duplicate_group_size_all_articles": duplicate_sizes[duplicate_key],
                "duplicate_group_candidate_count": candidate_duplicate_sizes[duplicate_key],
                "is_duplicate_representative": str(
                    duplicate_representatives[duplicate_key] == article["article_id"]
                ).lower(),
                "event_id": article["event_id"],
                "event_group_size_all_articles": event_sizes[event_key],
                "event_group_candidate_count": candidate_event_sizes[event_key],
                "prior_evidence_role": "|".join(sorted(evidence_roles.get(article["article_id"], []))),
                "link": article["link"],
                "query_from": article["query_from"],
                "query_to": article["query_to"],
                "review_status": "pending",
                "relevant_to_window_episode": "",
                "confirmed_episode_id": "",
                "confirmed_risk_family": "",
                "candidate_family_correct": "",
                "noise_type": "",
                "reviewer": "",
                "notes": "",
            })
        fields = list(rows[0]) if rows else []
        write_csv(output_path, fields, rows)
        return {
            "output": str(output_path),
            "output_sha256": file_sha256(output_path),
            "rows": len(rows),
            "window_episodes": len({row["window_episode_id"] for row in rows}),
            "candidate_duplicate_groups": len(candidate_duplicate_sizes),
            "candidate_event_groups": len(candidate_event_sizes),
            "candidates_linked_to_duplicate_groups": sum(
                duplicate_sizes[row["duplicate_group_id"] or row["article_id"]] > 1
                for row in candidates
            ),
            "candidates_linked_to_event_groups": sum(
                event_sizes[row["event_id"] or row["article_id"]] > 1
                for row in candidates
            ),
            "previously_confirmed_evidence_rows": sum(bool(row["prior_evidence_role"]) for row in rows),
            "review_status": "pending",
        }

    @staticmethod
    def _validate_provenance(acquisition: dict, query_manifest_path: Path) -> None:
        if acquisition.get("source_query_manifest", {}).get("sha256") != file_sha256(query_manifest_path):
            raise ValueError("Acquisition manifest does not match the query manifest")
        if acquisition.get("mode") != "known_episode_probe":
            raise ValueError("Acquisition manifest is not a known-episode probe")

    @staticmethod
    def _read_articles(path: Path) -> list[dict]:
        with path.open(newline="", encoding="utf-8-sig") as stream:
            rows = list(csv.DictReader(stream))
        for row in rows:
            families = ast.literal_eval(row["risk_family_candidates"])
            row["risk_family_candidates"] = families
        return rows

    @staticmethod
    def _window_key(row: dict) -> tuple[str, str, str]:
        return row["company"], row["from"], row["to"]

    @classmethod
    def _episode_for(cls, article: dict, windows: dict) -> dict:
        key = (article["company"], article["query_from"], article["query_to"])
        if key not in windows:
            raise ValueError(f"Candidate article belongs to no known-episode window: {article['article_id']}")
        return windows[key]

    @staticmethod
    def _evidence_roles(decisions: dict) -> dict[str, set[str]]:
        roles: dict[str, set[str]] = {}
        for decision in decisions.values():
            for article_id in decision.get("representative_article_ids", []):
                roles.setdefault(article_id, set()).add("confirmed_representative")
            for article_id in decision.get("family_evidence_article_ids", []):
                roles.setdefault(article_id, set()).add("confirmed_family_evidence")
        return roles

    @staticmethod
    def _representatives(rows: list[dict]) -> dict[str, str]:
        quality_rank = {"full": 0, "partial": 1, "summary_only": 2, "missing": 3, "invalid": 4}
        groups: dict[str, list[dict]] = {}
        for row in rows:
            key = row["duplicate_group_id"] or row["article_id"]
            groups.setdefault(key, []).append(row)
        return {
            key: min(group, key=lambda row: (
                quality_rank.get(row["content_available"], 9),
                -int(row["content_length_words"] or 0),
                row["article_id"],
            ))["article_id"]
            for key, group in groups.items()
        }

    @classmethod
    def _protect_existing_annotations(cls, path: Path) -> None:
        if not path.exists():
            return
        with path.open(newline="", encoding="utf-8-sig") as stream:
            rows = list(csv.DictReader(stream))
        for row in rows:
            if row.get("review_status", "pending").strip().casefold() != "pending":
                raise ValueError("Refusing to overwrite an annotated candidate review CSV")
            if any(row.get(field, "").strip() for field in cls.REVIEW_FIELDS[1:]):
                raise ValueError("Refusing to overwrite an annotated candidate review CSV")
