from __future__ import annotations

import ast
import csv
from collections import Counter
from pathlib import Path

from .common import file_sha256, load_json, now_utc, write_bytes, write_json
from .eodhd_config import EodhdPilotConfig


class KnownEpisodeMetricsBuilder:
    """Validate confirmed episode decisions and calculate recovery metrics."""

    def __init__(self, config: EodhdPilotConfig):
        self.config = config

    def build(
        self,
        episodes_path: Path,
        query_manifest_path: Path,
        acquisition_manifest_path: Path,
        metadata_path: Path,
        review_path: Path,
        output_path: Path,
        report_path: Path,
    ) -> dict:
        episodes_source = load_json(episodes_path)
        query_manifest = load_json(query_manifest_path)
        acquisition = load_json(acquisition_manifest_path)
        review = load_json(review_path)
        self._validate_provenance(query_manifest_path, acquisition)

        episodes = {row["episode_id"]: row for row in episodes_source.get("episodes", [])}
        windows = {row["episode_id"]: row for row in query_manifest.get("windows", [])}
        decisions = {row["episode_id"]: row for row in review.get("decisions", [])}
        if review.get("review_status") != "confirmed" or not review.get("reviewer"):
            raise ValueError("Recovery review must be confirmed by an identified reviewer")
        if len(decisions) != len(review.get("decisions", [])):
            raise ValueError("Recovery review contains duplicate episode decisions")
        if set(decisions) != set(episodes) or set(windows) != set(episodes):
            raise ValueError("Episodes, query windows, and review decisions must match exactly")

        articles = self._read_articles(metadata_path)
        results = []
        for episode_id, episode in episodes.items():
            results.append(self._validate_decision(
                episode, windows[episode_id], decisions[episode_id], articles
            ))
        results.sort(key=lambda row: row["episode_id"])

        recovered = sum(row["recovered"] for row in results)
        family_correct = sum(row["correct_family_candidate_found"] for row in results)
        useful = sum(row["recovered_with_useful_content"] for row in results)
        by_family = self._by_family(results, episodes_source.get("allowed_risk_families", []))
        recall = self._ratio(recovered, len(results))
        useful_rate = self._ratio(useful, recovered)
        thresholds = self.config["decision_thresholds"]
        numeric_gate = (
            "GO" if recall >= thresholds["go_min_known_event_recall"]
            and useful_rate >= thresholds["go_min_useful_content_rate"]
            else "GO_CON_COMPLEMENTOS" if recall >= thresholds["go_with_complements_min_known_event_recall"]
            else "NO_GO"
        )
        result = {
            "generated_at_utc": now_utc(),
            "protocol_version": "eodhd-known-episode-metrics-v1",
            "sources": {
                "episodes": self._source(episodes_path),
                "query_manifest": self._source(query_manifest_path),
                "acquisition_manifest": self._source(acquisition_manifest_path),
                "articles_metadata": self._source(metadata_path),
                "confirmed_review": self._source(review_path),
            },
            "review": {
                "status": review["review_status"],
                "reviewer": review["reviewer"],
                "confirmed_at": review.get("confirmed_at"),
                "independent_human_confirmation": True,
            },
            "metrics": {
                "expected_episodes": len(results),
                "recovered_episodes": recovered,
                "missed_episodes": len(results) - recovered,
                "known_event_recall": recall,
                "recovered_with_useful_content": useful,
                "reviewed_relevant_useful_content_rate": useful_rate,
                "correct_family_recovered_episodes": family_correct,
                "correct_family_recall": self._ratio(family_correct, len(results)),
            },
            "by_family": by_family,
            "threshold_evaluation": {
                "numeric_gate": numeric_gate,
                "thresholds": thresholds,
                "coverage_caveats": [
                    "customer_concentration no tiene ningún episodio de referencia elegible",
                    "El benchmark confirmado contiene solo seis episodios independientes",
                    "IF Metall no fue recuperado por EODHD en la ventana evaluada",
                ],
            },
            "episode_results": results,
        }
        write_json(output_path, result)
        self._write_report(report_path, result)
        return result

    def _validate_provenance(self, query_manifest_path: Path, acquisition: dict) -> None:
        source = acquisition.get("source_query_manifest", {})
        if source.get("sha256") != file_sha256(query_manifest_path):
            raise ValueError("Acquisition manifest does not match the query manifest")
        if acquisition.get("mode") != "known_episode_probe":
            raise ValueError("Acquisition manifest is not a known-episode probe")

    def _validate_decision(self, episode, window, decision, articles) -> dict:
        episode_id = episode["episode_id"]
        recovered = decision.get("recovered")
        correct_family = decision.get("correct_family_candidate_found")
        if not isinstance(recovered, bool) or not isinstance(correct_family, bool):
            raise ValueError(f"Episode {episode_id} has non-boolean review decisions")
        representative_ids = decision.get("representative_article_ids", [])
        family_ids = decision.get("family_evidence_article_ids", [])
        if recovered != bool(representative_ids):
            raise ValueError(f"Episode {episode_id} has inconsistent recovery evidence")
        if correct_family != bool(family_ids) or (correct_family and not recovered):
            raise ValueError(f"Episode {episode_id} has inconsistent family evidence")
        if not decision.get("notes"):
            raise ValueError(f"Episode {episode_id} has no review notes")

        representative = [self._article(article_id, articles, episode, window) for article_id in representative_ids]
        family_evidence = [self._article(article_id, articles, episode, window) for article_id in family_ids]
        if any(episode["risk_family"] not in row["risk_family_candidates"] for row in family_evidence):
            raise ValueError(f"Episode {episode_id} family evidence lacks the expected family")
        useful = recovered and any(
            row["content_available"] in {"full", "partial"} for row in representative
        )
        return {
            "episode_id": episode_id,
            "company": episode["company"],
            "risk_family": episode["risk_family"],
            "recovered": recovered,
            "recovered_with_useful_content": useful,
            "correct_family_candidate_found": correct_family,
            "representative_articles": [self._article_summary(row) for row in representative],
            "family_evidence_article_ids": family_ids,
            "notes": decision["notes"],
        }

    @staticmethod
    def _article(article_id, articles, episode, window):
        if article_id not in articles:
            raise ValueError(f"Unknown reviewed article_id: {article_id}")
        row = articles[article_id]
        expected = (episode["company"], window["from"], window["to"])
        actual = (row["company"], row["query_from"], row["query_to"])
        if actual != expected:
            raise ValueError(f"Article {article_id} does not belong to episode {episode['episode_id']}")
        return row

    @staticmethod
    def _article_summary(row):
        return {
            key: row[key]
            for key in ("article_id", "published_at_utc", "title", "content_available", "link")
        }

    @staticmethod
    def _read_articles(path: Path) -> dict[str, dict]:
        with path.open(newline="", encoding="utf-8-sig") as stream:
            rows = list(csv.DictReader(stream))
        articles = {}
        for row in rows:
            article_id = row["article_id"]
            if article_id in articles:
                raise ValueError(f"Duplicate article_id in metadata: {article_id}")
            row["risk_family_candidates"] = ast.literal_eval(row["risk_family_candidates"])
            articles[article_id] = row
        return articles

    def _by_family(self, results, allowed_families):
        expected = Counter(row["risk_family"] for row in results)
        recovered = Counter(row["risk_family"] for row in results if row["recovered"])
        correct = Counter(row["risk_family"] for row in results if row["correct_family_candidate_found"])
        return {
            family: {
                "expected": expected[family],
                "recovered": recovered[family],
                "recall": self._ratio(recovered[family], expected[family]),
                "correct_family_recovered": correct[family],
                "correct_family_recall": self._ratio(correct[family], expected[family]),
            }
            for family in sorted(allowed_families)
        }

    @staticmethod
    def _ratio(numerator, denominator):
        return numerator / denominator if denominator else None

    @staticmethod
    def _source(path: Path):
        return {"path": str(path), "sha256": file_sha256(path)}

    @staticmethod
    def _write_report(path: Path, result: dict) -> None:
        metrics = result["metrics"]
        lines = [
            "# Recuperación de episodios conocidos en EODHD",
            "",
            "## Métricas confirmadas",
            "",
            f"- Recuperación: {metrics['recovered_episodes']}/{metrics['expected_episodes']} "
            f"({metrics['known_event_recall']:.1%}).",
            f"- Recuperación con contenido útil: {metrics['recovered_with_useful_content']}/"
            f"{metrics['recovered_episodes']} ({metrics['reviewed_relevant_useful_content_rate']:.1%}).",
            f"- Recuperación con familia automática correcta: "
            f"{metrics['correct_family_recovered_episodes']}/{metrics['expected_episodes']} "
            f"({metrics['correct_family_recall']:.1%}).",
            f"- Umbral numérico configurado: `{result['threshold_evaluation']['numeric_gate']}`.",
            "",
            "## Resultado por episodio",
            "",
            "| Episodio | Familia | Recuperado | Familia correcta | Contenido útil |",
            "|---|---|---:|---:|---:|",
        ]
        for row in result["episode_results"]:
            mark = lambda value: "sí" if value else "no"
            lines.append(
                f"| {row['episode_id']} | {row['risk_family']} | {mark(row['recovered'])} | "
                f"{mark(row['correct_family_candidate_found'])} | "
                f"{mark(row['recovered_with_useful_content'])} |"
            )
        lines += ["", "## Límites", ""]
        lines.extend(f"- {item}." for item in result["threshold_evaluation"]["coverage_caveats"])
        write_bytes(path, ("\n".join(lines) + "\n").encode("utf-8"))
