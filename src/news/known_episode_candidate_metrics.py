from __future__ import annotations

import ast
import csv
from collections import Counter
from pathlib import Path

from .common import file_sha256, load_json, now_utc, write_bytes, write_json


class KnownEpisodeCandidateMetricsBuilder:
    """Validate candidate annotations and measure article-level filter precision."""

    REQUIRED_FIELDS = {
        "article_id",
        "window_episode_id",
        "company",
        "expected_risk_family",
        "title",
        "content_available",
        "proposed_risk_families",
        "review_status",
        "relevant_to_window_episode",
        "confirmed_episode_id",
        "confirmed_risk_family",
        "candidate_family_correct",
        "noise_type",
        "reviewer",
        "notes",
    }

    def build(
        self,
        review_path: Path,
        metadata_path: Path,
        acquisition_manifest_path: Path,
        query_manifest_path: Path,
        episode_metrics_path: Path,
        output_path: Path,
        report_path: Path,
    ) -> dict:
        rows = self._read_review(review_path)
        acquisition = load_json(acquisition_manifest_path)
        query_manifest = load_json(query_manifest_path)
        episode_metrics = load_json(episode_metrics_path)
        metadata = self._read_metadata(metadata_path)
        self._validate_provenance(
            acquisition,
            acquisition_manifest_path,
            query_manifest_path,
            episode_metrics,
        )
        windows = {row["episode_id"]: row for row in query_manifest["windows"]}
        self._validate_rows(rows, metadata, windows, acquisition)

        reviewed = [row for row in rows if row["review_status"] == "reviewed"]
        pending = [row for row in rows if row["review_status"] == "pending"]
        unclear = [row for row in reviewed if row["relevant_to_window_episode"] == "unclear"]
        if pending or unclear:
            raise ValueError(
                f"Candidate review is not definitive: {len(pending)} pending, {len(unclear)} unclear"
            )
        relevant = [row for row in reviewed if row["relevant_to_window_episode"] == "true"]
        irrelevant = [row for row in reviewed if row["relevant_to_window_episode"] == "false"]
        family_correct = [row for row in relevant if row["candidate_family_correct"] == "true"]
        useful = [row for row in relevant if row["content_available"] in {"full", "partial"}]

        result = {
            "generated_at_utc": now_utc(),
            "protocol_version": "eodhd-known-episode-candidate-metrics-v1",
            "sources": {
                "candidate_review": self._source(review_path),
                "articles_metadata": self._source(metadata_path),
                "acquisition_manifest": self._source(acquisition_manifest_path),
                "query_manifest": self._source(query_manifest_path),
                "episode_metrics": self._source(episode_metrics_path),
            },
            "review": {
                "unit": "article_company_lexical_candidate",
                "reviewers": dict(sorted(Counter(row["reviewer"] for row in reviewed).items())),
                "independent_human_review": True,
                "rows_total": len(rows),
                "rows_reviewed": len(reviewed),
                "rows_pending": len(pending),
                "rows_unclear": len(unclear),
            },
            "metrics": {
                "relevant_candidates": len(relevant),
                "false_positive_candidates": len(irrelevant),
                "candidate_precision": self._ratio(len(relevant), len(reviewed)),
                "false_positive_rate": self._ratio(len(irrelevant), len(reviewed)),
                "correct_family_candidates": len(family_correct),
                "correct_family_precision": self._ratio(len(family_correct), len(reviewed)),
                "family_accuracy_among_relevant": self._ratio(len(family_correct), len(relevant)),
                "relevant_with_useful_content": len(useful),
                "useful_content_rate_among_relevant": self._ratio(len(useful), len(relevant)),
                "known_event_recall": episode_metrics["metrics"]["known_event_recall"],
                "correct_family_episode_recall": episode_metrics["metrics"]["correct_family_recall"],
            },
            "by_episode": self._by_episode(reviewed),
            "by_expected_family": self._by_expected_family(reviewed),
            "by_proposed_family_activation": self._by_proposed_family(reviewed),
            "noise_types": dict(sorted(Counter(row["noise_type"] for row in irrelevant).items())),
            "interpretation": {
                "precision_threshold_configured": False,
                "note": (
                    "Recall is measured per episode; precision is measured per article-company candidate. "
                    "They must not be combined into a classical F1 score because their units differ."
                ),
            },
        }
        write_json(output_path, result)
        self._write_report(report_path, result)
        return result

    def _validate_rows(self, rows, metadata, windows, acquisition) -> None:
        expected_count = acquisition.get("counts", {}).get("risk_candidates")
        if len(rows) != expected_count:
            raise ValueError(f"Review row count differs from candidate population: {len(rows)} != {expected_count}")
        seen = set()
        errors = []
        for number, row in enumerate(rows, start=2):
            article_id = row["article_id"]
            if article_id in seen:
                errors.append(f"row {number}: duplicate article_id")
            seen.add(article_id)
            source = metadata.get(article_id)
            if source is None or not source["risk_family_candidates"]:
                errors.append(f"row {number}: article is not an acquisition candidate")
                continue
            for field in ("company", "title", "content_available"):
                if row[field] != source[field]:
                    errors.append(f"row {number}: {field} differs from acquisition metadata")
            proposed = set(filter(None, row["proposed_risk_families"].split("|")))
            if proposed != set(source["risk_family_candidates"]):
                errors.append(f"row {number}: proposed families differ from acquisition metadata")
            episode_id = row["window_episode_id"]
            window = windows.get(episode_id)
            if window is None:
                errors.append(f"row {number}: unknown window episode")
                continue
            if row["company"] != window["company"] or row["expected_risk_family"] != window["risk_family"]:
                errors.append(f"row {number}: episode context differs from query manifest")
            status = row["review_status"].casefold()
            relevance = row["relevant_to_window_episode"].casefold()
            if status not in {"pending", "reviewed"}:
                errors.append(f"row {number}: invalid review_status")
            if status == "reviewed":
                if relevance not in {"true", "false", "unclear"}:
                    errors.append(f"row {number}: invalid relevance")
                if not row["reviewer"] or not row["notes"]:
                    errors.append(f"row {number}: reviewer and notes are required")
                if relevance == "true":
                    if row["confirmed_episode_id"] != episode_id:
                        errors.append(f"row {number}: confirmed episode differs from window episode")
                    if row["confirmed_risk_family"] != row["expected_risk_family"]:
                        errors.append(f"row {number}: confirmed family differs from expected family")
                    expected_correct = str(row["confirmed_risk_family"] in proposed).lower()
                    if row["candidate_family_correct"].casefold() != expected_correct:
                        errors.append(f"row {number}: candidate_family_correct is inconsistent")
                    if row["noise_type"]:
                        errors.append(f"row {number}: relevant row has noise_type")
                elif relevance == "false":
                    if row["confirmed_episode_id"] or row["confirmed_risk_family"] or row["candidate_family_correct"]:
                        errors.append(f"row {number}: irrelevant row has confirmation fields")
                    if not row["noise_type"]:
                        errors.append(f"row {number}: irrelevant row has no noise_type")
        if errors:
            raise ValueError("Invalid candidate annotations:\n- " + "\n- ".join(errors))

    @classmethod
    def _by_episode(cls, rows):
        result = {}
        for episode_id in sorted({row["window_episode_id"] for row in rows}):
            selected = [row for row in rows if row["window_episode_id"] == episode_id]
            relevant = [row for row in selected if row["relevant_to_window_episode"] == "true"]
            correct = [row for row in relevant if row["candidate_family_correct"] == "true"]
            result[episode_id] = cls._group_metrics(selected, relevant, correct)
        return result

    @classmethod
    def _by_expected_family(cls, rows):
        result = {}
        for family in sorted({row["expected_risk_family"] for row in rows}):
            selected = [row for row in rows if row["expected_risk_family"] == family]
            relevant = [row for row in selected if row["relevant_to_window_episode"] == "true"]
            correct = [row for row in relevant if row["candidate_family_correct"] == "true"]
            result[family] = cls._group_metrics(selected, relevant, correct)
        return result

    @classmethod
    def _by_proposed_family(cls, rows):
        families = sorted({family for row in rows for family in row["proposed_risk_families"].split("|")})
        result = {}
        for family in families:
            selected = [row for row in rows if family in row["proposed_risk_families"].split("|")]
            relevant = [row for row in selected if row["relevant_to_window_episode"] == "true"]
            correct = [row for row in relevant if row["confirmed_risk_family"] == family]
            result[family] = {
                "activations": len(selected),
                "relevant_activations": len(relevant),
                "relevance_precision": cls._ratio(len(relevant), len(selected)),
                "correct_family_activations": len(correct),
                "family_precision": cls._ratio(len(correct), len(selected)),
            }
        return result

    @classmethod
    def _group_metrics(cls, selected, relevant, correct):
        return {
            "candidates": len(selected),
            "relevant": len(relevant),
            "precision": cls._ratio(len(relevant), len(selected)),
            "correct_family": len(correct),
            "correct_family_precision": cls._ratio(len(correct), len(selected)),
            "family_accuracy_among_relevant": cls._ratio(len(correct), len(relevant)),
        }

    @staticmethod
    def _read_review(path: Path):
        with path.open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            missing = sorted(KnownEpisodeCandidateMetricsBuilder.REQUIRED_FIELDS - set(reader.fieldnames or []))
            if missing:
                raise ValueError(f"Candidate review CSV is missing fields: {', '.join(missing)}")
            return [
                {key: (value or "").strip() for key, value in row.items()}
                for row in reader
            ]

    @staticmethod
    def _read_metadata(path: Path):
        with path.open(newline="", encoding="utf-8-sig") as stream:
            rows = list(csv.DictReader(stream))
        result = {}
        for row in rows:
            row["risk_family_candidates"] = ast.literal_eval(row["risk_family_candidates"])
            result[row["article_id"]] = row
        return result

    @staticmethod
    def _validate_provenance(
        acquisition,
        acquisition_manifest_path,
        query_manifest_path,
        episode_metrics,
    ):
        if acquisition.get("source_query_manifest", {}).get("sha256") != file_sha256(query_manifest_path):
            raise ValueError("Acquisition manifest does not match the query manifest")
        if episode_metrics.get("sources", {}).get("acquisition_manifest", {}).get("sha256") != file_sha256(
            acquisition_manifest_path
        ):
            raise ValueError("Episode metrics provenance is stale")

    @staticmethod
    def _ratio(numerator, denominator):
        return numerator / denominator if denominator else None

    @staticmethod
    def _source(path):
        return {"path": str(path), "sha256": file_sha256(path)}

    @staticmethod
    def _write_report(path: Path, result: dict) -> None:
        metrics = result["metrics"]
        lines = [
            "# Precisión del filtro en ventanas de episodios conocidos",
            "",
            "## Resultado confirmado",
            "",
            f"- Candidatos relevantes: {metrics['relevant_candidates']}/{result['review']['rows_reviewed']} "
            f"({metrics['candidate_precision']:.1%}).",
            f"- Falsos positivos: {metrics['false_positive_candidates']}/{result['review']['rows_reviewed']} "
            f"({metrics['false_positive_rate']:.1%}).",
            f"- Candidatos relevantes con familia correcta: {metrics['correct_family_candidates']}/"
            f"{result['review']['rows_reviewed']} ({metrics['correct_family_precision']:.1%}).",
            f"- Exactitud de familia entre candidatos relevantes: "
            f"{metrics['family_accuracy_among_relevant']:.1%}.",
            f"- Contenido útil entre relevantes: {metrics['useful_content_rate_among_relevant']:.1%}.",
            f"- Recall por episodio: {metrics['known_event_recall']:.1%}; recall con familia correcta: "
            f"{metrics['correct_family_episode_recall']:.1%}.",
            "",
            "## Por episodio",
            "",
            "| Episodio | Candidatos | Relevantes | Precisión | Familia correcta |",
            "|---|---:|---:|---:|---:|",
        ]
        for episode_id, row in result["by_episode"].items():
            lines.append(
                f"| {episode_id} | {row['candidates']} | {row['relevant']} | "
                f"{row['precision']:.1%} | {row['correct_family']} |"
            )
        lines += [
            "",
            "## Interpretación",
            "",
            "- No hay un umbral de precisión configurado; no se asigna automáticamente GO/NO_GO.",
            "- Recall y precisión usan unidades distintas (episodios frente a artículos-empresa), por lo que no se calcula F1.",
            "- Las métricas describen estas seis ventanas confirmadas y no estiman por sí solas el rendimiento del histórico completo.",
            "",
        ]
        write_bytes(path, ("\n".join(lines) + "\n").encode("utf-8"))
