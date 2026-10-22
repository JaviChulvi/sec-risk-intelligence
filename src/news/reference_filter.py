from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

from .common import file_sha256, load_json, now_utc, write_bytes, write_json
from .temporal import classify_episode


class ReferenceEpisodeFilter:
    """Build an exhaustive, auditable eligibility decision for reference cards."""

    REQUIRED_EPISODE_FIELDS = {
        "episode_id",
        "company",
        "episode_name",
        "risk_family",
        "source_case_ids",
        "followup_case_ids",
        "prior_filing_date",
        "t0_filing_date",
        "event_date_start",
        "event_date_end",
        "first_public_disclosure_at",
        "article_published_at",
        "known_urls",
        "official_source",
        "notes",
        "used_for_filter_development",
        "review_status",
        "reviewer",
    }

    def build(
        self,
        review_path: Path,
        rules_path: Path,
        output_path: Path,
        report_path: Path,
    ) -> dict:
        cards = self._read_cards(review_path)
        rules = load_json(rules_path)
        allowed = set(rules.get("allowed_risk_families", []))
        episodes, assignments = self._prepare_episodes(rules, cards, allowed)
        exclusions = self._prepare_exclusions(rules, cards, assignments)
        missing = sorted(set(cards) - set(assignments))
        if missing:
            raise ValueError(f"Reference cards have no eligibility decision: {', '.join(missing)}")

        family_counts = Counter(episode["risk_family"] for episode in episodes)
        status_counts = Counter(item["status"] for item in assignments.values())
        result = {
            "generated_at_utc": now_utc(),
            "protocol_version": rules.get("protocol_version"),
            "source_review_file": str(review_path),
            "source_review_sha256": file_sha256(review_path),
            "rules_file": str(rules_path),
            "rules_sha256": file_sha256(rules_path),
            "allowed_risk_families": sorted(allowed),
            "counts": {
                "inventory_cards": len(cards),
                "eligible_independent_episodes": len(episodes),
                "eligible_source_cards": status_counts["eligible_source"],
                "linked_followup_cards": status_counts["linked_followup"],
                "excluded_cards": sum(
                    count for status, count in status_counts.items() if status.startswith("excluded_")
                ),
            },
            "episodes_by_family": {
                family: family_counts.get(family, 0) for family in sorted(allowed)
            },
            "episodes": episodes,
            "card_audit": [assignments[case_id] for case_id in sorted(assignments)],
            "exclusion_reasons": exclusions,
            "limitations": [
                "All episode decisions are candidates pending independent human confirmation",
                "The 49-card inventory contains no eligible customer_concentration episode",
                "No EODHD acquisition or known-event recovery measurement has been run",
            ],
        }
        write_json(output_path, result)
        self._write_report(report_path, result)
        return result

    def _read_cards(self, path: Path) -> dict[str, dict[str, str]]:
        with path.open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            if not reader.fieldnames or "case_id" not in reader.fieldnames:
                raise ValueError("Reference review CSV must contain case_id")
            cards: dict[str, dict[str, str]] = {}
            for row_number, row in enumerate(reader, start=2):
                case_id = (row.get("case_id") or "").strip()
                if not case_id:
                    raise ValueError(f"Reference review row {row_number} has no case_id")
                if case_id in cards:
                    raise ValueError(f"Duplicate reference case_id: {case_id}")
                cards[case_id] = {key: (value or "").strip() for key, value in row.items()}
        if not cards:
            raise ValueError("Reference review CSV contains no cards")
        return cards

    def _prepare_episodes(
        self,
        rules: dict,
        cards: dict[str, dict[str, str]],
        allowed: set[str],
    ) -> tuple[list[dict], dict[str, dict]]:
        assignments: dict[str, dict] = {}
        episodes: list[dict] = []
        episode_ids: set[str] = set()
        for raw in rules.get("episodes", []):
            missing_fields = sorted(self.REQUIRED_EPISODE_FIELDS - set(raw))
            if missing_fields:
                raise ValueError(f"Episode is missing fields: {', '.join(missing_fields)}")
            episode_id = raw["episode_id"]
            if episode_id in episode_ids:
                raise ValueError(f"Duplicate episode_id: {episode_id}")
            episode_ids.add(episode_id)
            if raw["risk_family"] not in allowed:
                raise ValueError(f"Episode {episode_id} has an out-of-scope risk family")
            if raw["used_for_filter_development"] is not False:
                raise ValueError(f"Episode {episode_id} must remain held out from filter development")
            if raw["review_status"] != "candidate":
                raise ValueError(f"Episode {episode_id} must remain a review candidate")
            source_ids = list(raw["source_case_ids"])
            followup_ids = list(raw["followup_case_ids"])
            if not source_ids:
                raise ValueError(f"Episode {episode_id} has no source cards")
            for case_id in source_ids + followup_ids:
                if case_id not in cards:
                    raise ValueError(f"Unknown source case_id: {case_id}")
                if cards[case_id]["company"] != raw["company"]:
                    raise ValueError(f"Episode {episode_id} mixes companies")
                if case_id in assignments:
                    raise ValueError(f"Reference card assigned more than once: {case_id}")
            temporal = classify_episode(
                raw["t0_filing_date"],
                article_published_at=raw["article_published_at"],
                event_occurred_at=raw["event_date_start"],
                first_public_disclosure_at=raw["first_public_disclosure_at"],
            )
            if not temporal["eligible"]:
                raise ValueError(
                    f"Episode {episode_id} is not temporally eligible: {temporal['temporal_relation']}"
                )
            episode = {**raw, "window_end": temporal["window_end"]["normalized"]}
            episodes.append(episode)
            for case_id in source_ids:
                assignments[case_id] = self._audit_row(
                    cards[case_id], "eligible_source", episode_id, raw["risk_family"], ""
                )
            for case_id in followup_ids:
                assignments[case_id] = self._audit_row(
                    cards[case_id], "linked_followup", episode_id, raw["risk_family"],
                    "Follow-up evidence for an existing episode; not counted independently",
                )
        return sorted(episodes, key=lambda item: (item["t0_filing_date"], item["episode_id"])), assignments

    def _prepare_exclusions(
        self,
        rules: dict,
        cards: dict[str, dict[str, str]],
        assignments: dict[str, dict],
    ) -> list[dict]:
        summaries = []
        for group in rules.get("exclusions", []):
            status = group.get("status", "")
            reason = group.get("reason", "")
            if not status.startswith("excluded_") or not reason:
                raise ValueError("Every exclusion group needs an excluded_* status and a reason")
            case_ids = list(group.get("case_ids", []))
            for case_id in case_ids:
                if case_id not in cards:
                    raise ValueError(f"Unknown excluded case_id: {case_id}")
                if case_id in assignments:
                    raise ValueError(f"Reference card assigned more than once: {case_id}")
                assignments[case_id] = self._audit_row(cards[case_id], status, "", "", reason)
            summaries.append({"status": status, "count": len(case_ids), "reason": reason})
        return summaries

    @staticmethod
    def _audit_row(card: dict, status: str, episode_id: str, family: str, reason: str) -> dict:
        return {
            "case_id": card["case_id"],
            "company": card.get("company", ""),
            "title": card.get("title", ""),
            "status": status,
            "episode_id": episode_id,
            "normalized_risk_family": family,
            "reason": reason,
        }

    def _write_report(self, path: Path, result: dict) -> None:
        counts = result["counts"]
        lines = [
            "# Filtrado de episodios conocidos para el piloto EODHD",
            "",
            "## Resultado",
            "",
            f"- Fichas auditadas: {counts['inventory_cards']}.",
            f"- Episodios independientes elegibles: {counts['eligible_independent_episodes']}.",
            f"- Fichas de seguimiento agrupadas: {counts['linked_followup_cards']}.",
            f"- Fichas excluidas: {counts['excluded_cards']}.",
            "",
            "## Cobertura por familia",
            "",
        ]
        for family, count in result["episodes_by_family"].items():
            lines.append(f"- `{family}`: {count} episodios.")
        lines += [
            "",
            "## Episodios candidatos",
            "",
            "| Episodio | Empresa | Familia | t0 | Ventana | Fichas |",
            "|---|---|---|---|---|---|",
        ]
        for episode in result["episodes"]:
            source_ids = ", ".join(episode["source_case_ids"] + episode["followup_case_ids"])
            lines.append(
                f"| {episode['episode_id']} | {episode['company']} | {episode['risk_family']} | "
                f"{episode['t0_filing_date']} | {episode['t0_filing_date']}–{episode['window_end']} | "
                f"{source_ids} |"
            )
        lines += ["", "## Exclusiones", ""]
        for exclusion in result["exclusion_reasons"]:
            lines.append(f"- `{exclusion['status']}`: {exclusion['count']}. {exclusion['reason']}")
        lines += [
            "",
            "## Limitaciones",
            "",
            "- Las decisiones son candidatas asistidas por ChatGPT y requieren confirmación humana independiente.",
            "- El inventario no aporta un episodio elegible de `customer_concentration`; no puede afirmarse cobertura de las tres familias.",
            "- Este filtrado no consulta EODHD ni mide recuperación.",
            "",
        ]
        write_bytes(path, ("\n".join(lines) + "\n").encode("utf-8"))
