from __future__ import annotations

import ast
import csv
from collections import Counter
from pathlib import Path

from .common import file_sha256, now_utc, write_bytes, write_json
from .local_articles import read_normalized_articles
from .risk_filter import RiskFamilyFilter
from .risk_news_review_sheet import RiskNewsAnnotationValidator


class RiskNewsDevelopmentMetricsBuilder:
    """Validate development labels and compare the stored and current local filters."""

    REQUIRED_FIELDS = {
        "review_order",
        "development_source",
        "label_provenance",
        "window_episode_id",
        "article_id",
        "company",
        "published_at_utc",
        "title",
        "content_available",
        "proposed_risk_families",
        "risk_match_terms",
        "link",
        "review_status",
        "relevant_risk_news",
        "company_relevance",
        "event_status",
        "confirmed_risk_families",
        "noise_type",
        "reviewer",
        "notes",
    }
    CONTENT_STATES = {"full", "partial", "summary_only", "missing", "invalid"}
    NEW_REVIEW_REQUIRED_FIELDS = {
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
        "review_status",
        "relevant_risk_news",
        "company_relevance",
        "event_status",
        "confirmed_risk_families",
        "noise_type",
        "reviewer",
        "notes",
    }

    def __init__(self, config: dict):
        self.config = config
        self.families = set(config["risk_rules"])
        self.risk_filter = RiskFamilyFilter(
            config["risk_rules"],
            config.get("risk_filter"),
        )
        self.annotation_validator = RiskNewsAnnotationValidator(
            families=self.families,
        )
        self.revised_annotation_validator = RiskNewsAnnotationValidator(
            families=self.families,
            require_positive_event_status=False,
        )

    def build(
        self,
        review_path: Path,
        recent_metadata_path: Path,
        episode_metadata_path: Path,
        normalized_root: Path,
        output_path: Path,
        report_path: Path,
        revised_new_review_path: Path | None = None,
    ) -> dict:
        rows = self._read_review(review_path)
        metadata = self._read_metadata((recent_metadata_path, episode_metadata_path))
        articles, article_files = read_normalized_articles(normalized_root)
        self._validate(rows, metadata, articles)
        stored_candidate_keys = {
            key for key, article in articles.items() if article.risk_family_candidates
        }
        corpus_comparison = self._corpus_comparison(
            articles,
            labelled_keys={self._key(row) for row in rows},
        )
        new_rows = []
        if revised_new_review_path is not None:
            new_rows = self._read_new_review(revised_new_review_path)
            self._validate_new_review(new_rows, articles, stored_candidate_keys)
            new_keys = {self._key(row) for row in new_rows}
            corpus_comparison["revised_relations_with_all_labels"] = (
                corpus_comparison["revised_relations_with_development_labels"] + len(new_keys)
            )
            corpus_comparison["revised_relations_without_any_labels"] = (
                corpus_comparison["revised_candidate_relations"]
                - corpus_comparison["revised_relations_with_all_labels"]
            )

        baseline_predictions = {
            self._key(row): self._pipe_set(row["proposed_risk_families"])
            for row in rows
        }
        baseline_terms = {
            self._key(row): self._parse_match_terms(row["risk_match_terms"])
            for row in rows
        }
        revised_predictions: dict[tuple[str, str], set[str]] = {}
        revised_terms: dict[tuple[str, str], dict[str, list[str]]] = {}
        for row in rows:
            key = self._key(row)
            matches = self.risk_filter.apply(articles[key])
            revised_predictions[key] = set(matches)
            revised_terms[key] = matches

        baseline = self._evaluate(rows, baseline_predictions)
        revised = self._evaluate(rows, revised_predictions)
        new_predictions = {
            self._key(row): self._pipe_set(row["proposed_risk_families"])
            for row in new_rows
        }
        new_evaluation = self._evaluate(new_rows, new_predictions) if new_rows else None
        union_comparison = None
        if new_rows:
            union_rows = rows + new_rows
            empty_new_predictions = {self._key(row): set() for row in new_rows}
            union_comparison = {
                "review": {
                    "rows": len(union_rows),
                    "positives": sum(row["relevant_risk_news"] == "true" for row in union_rows),
                    "negatives": sum(row["relevant_risk_news"] == "false" for row in union_rows),
                    "scope": "union_of_stored_and_revised_candidates",
                },
                "stored_filter": self._evaluate(
                    union_rows,
                    {**baseline_predictions, **empty_new_predictions},
                ),
                "revised_filter": self._evaluate(
                    union_rows,
                    {**revised_predictions, **new_predictions},
                ),
            }
        result = {
            "generated_at_utc": now_utc(),
            "protocol_version": "eodhd-risk-news-development-metrics-v1",
            "sources": {
                "development_review": self._source(review_path),
                "recent_metadata": self._source(recent_metadata_path),
                "episode_metadata": self._source(episode_metadata_path),
                "normalized_articles": [self._source(path) for path in article_files],
                **(
                    {"revised_new_candidate_review": self._source(revised_new_review_path)}
                    if revised_new_review_path is not None else {}
                ),
            },
            "review": {
                "unit": "article_company_relation",
                "rows": len(rows),
                "positives": sum(row["relevant_risk_news"] == "true" for row in rows),
                "negatives": sum(row["relevant_risk_news"] == "false" for row in rows),
                "reviewers": dict(sorted(Counter(row["reviewer"] for row in rows).items())),
                "company_relevance_optional": True,
            },
            "baseline_stored_filter": baseline,
            "revised_local_filter": revised,
            **(
                {
                    "revised_new_candidate_review": {
                        "review": {
                            "rows": len(new_rows),
                            "positives": sum(
                                row["relevant_risk_news"] == "true" for row in new_rows
                            ),
                            "negatives": sum(
                                row["relevant_risk_news"] == "false" for row in new_rows
                            ),
                            "reviewers": dict(sorted(Counter(
                                row["reviewer"] for row in new_rows
                            ).items())),
                        },
                        "metrics": new_evaluation,
                    },
                    "candidate_union_comparison": union_comparison,
                }
                if new_rows else {}
            ),
            "change": {
                "selected_relations": revised["selection"]["selected"]
                - baseline["selection"]["selected"],
                "false_positive_relations": revised["selection"]["false_positives"]
                - baseline["selection"]["false_positives"],
                "selection_precision": revised["selection"]["precision"]
                - baseline["selection"]["precision"],
                "positive_retention": revised["selection"]["positive_retention"]
                - baseline["selection"]["positive_retention"],
                "family_accuracy_all_positives": revised["classification"][
                    "family_accuracy_all_positives"
                ]
                - baseline["classification"]["family_accuracy_all_positives"],
            },
            "diagnostics": {
                "baseline_by_match_term": self._term_diagnostics(rows, baseline_terms),
                "revised_by_match_term": self._term_diagnostics(rows, revised_terms),
            },
            "local_cached_corpus": corpus_comparison,
            "methodology": {
                "purpose": "development_only",
                "independent_holdout": False,
                "new_candidate_labels_added_after_rule_freeze": bool(new_rows),
                "selection_denominator": (
                    "All candidates in the union of the stored and revised filters are labelled; "
                    "metrics do not cover relations selected by neither filter."
                    if new_rows else
                    "Only previously selected lexical candidates are labelled; precision and positive "
                    "retention are development diagnostics, not population estimates."
                ),
                "news_role": (
                    "Post-10-K news is exploratory contrast and does not define documentary-loss labels."
                ),
                "network_calls": 0,
            },
        }
        write_json(output_path, result)
        self._write_report(report_path, result)
        return result

    def _validate(self, rows, metadata, articles) -> None:
        errors = []
        seen = set()
        orders = []
        for number, row in enumerate(rows, start=2):
            key = self._key(row)
            if key in seen:
                errors.append(f"row {number}: duplicate article-company relation")
            seen.add(key)
            try:
                orders.append(int(row["review_order"]))
            except ValueError:
                errors.append(f"row {number}: invalid review_order")
            source = metadata.get(key)
            article = articles.get(key)
            if source is None:
                errors.append(f"row {number}: relation absent from acquisition metadata")
                continue
            if article is None:
                errors.append(f"row {number}: relation absent from normalized local cache")
                continue
            for field in ("published_at_utc", "title", "content_available", "link"):
                if row[field] != source[field]:
                    errors.append(f"row {number}: {field} differs from acquisition metadata")
            proposed = self._pipe_set(row["proposed_risk_families"])
            source_families = set(ast.literal_eval(source["risk_family_candidates"]))
            if proposed != source_families:
                errors.append(f"row {number}: proposed families differ from acquisition metadata")
            if self._parse_match_terms(row["risk_match_terms"]) != self._parse_match_terms(
                source["risk_match_terms"]
            ):
                errors.append(f"row {number}: match terms differ from acquisition metadata")
            if row["content_available"] not in self.CONTENT_STATES:
                errors.append(f"row {number}: invalid content_available")
            errors.extend(self.annotation_validator.errors(row, row_number=number))
        if orders != list(range(1, len(rows) + 1)):
            errors.append("review_order must be the consecutive sequence 1..N")
        if errors:
            raise ValueError("Invalid risk-news development annotations:\n- " + "\n- ".join(errors))

    def _evaluate(self, rows, predictions) -> dict:
        positives = [row for row in rows if row["relevant_risk_news"] == "true"]
        negatives = [row for row in rows if row["relevant_risk_news"] == "false"]
        selected = [row for row in rows if predictions[self._key(row)]]
        selected_positives = [row for row in selected if row["relevant_risk_news"] == "true"]
        selected_negatives = [row for row in selected if row["relevant_risk_news"] == "false"]
        family_correct = [
            row for row in selected_positives
            if self._pipe_set(row["confirmed_risk_families"]) <= predictions[self._key(row)]
        ]
        exact_family = [
            row for row in selected_positives
            if self._pipe_set(row["confirmed_risk_families"]) == predictions[self._key(row)]
        ]
        family_confusions = Counter(
            f"{'|'.join(sorted(predictions[self._key(row)])) or '(not selected)'}->"
            f"{'|'.join(sorted(self._pipe_set(row['confirmed_risk_families'])))}"
            for row in selected_positives
            if self._pipe_set(row["confirmed_risk_families"]) != predictions[self._key(row)]
        )
        episodes = sorted({row["window_episode_id"] for row in positives if row["window_episode_id"]})
        retained_by_episode = {
            episode: sum(
                row["window_episode_id"] == episode and row in selected_positives
                for row in positives
            )
            for episode in episodes
        }
        return {
            "selection": {
                "selected": len(selected),
                "true_positives": len(selected_positives),
                "false_positives": len(selected_negatives),
                "false_negatives_within_development_candidates": len(positives) - len(selected_positives),
                "precision": self._ratio(len(selected_positives), len(selected)),
                "positive_retention": self._ratio(len(selected_positives), len(positives)),
            },
            "classification": {
                "correct_family_selected_positives": len(family_correct),
                "exact_family_selected_positives": len(exact_family),
                "family_accuracy_selected_positives": self._ratio(
                    len(family_correct), len(selected_positives)
                ),
                "exact_family_accuracy_selected_positives": self._ratio(
                    len(exact_family), len(selected_positives)
                ),
                "family_accuracy_all_positives": self._ratio(len(family_correct), len(positives)),
                "family_confusions": dict(sorted(family_confusions.items())),
            },
            "episode_evidence": {
                "episodes": len(episodes),
                "episodes_with_retained_evidence": sum(value > 0 for value in retained_by_episode.values()),
                "retained_positive_articles": retained_by_episode,
            },
            "by_company": self._by_company(rows, predictions),
            "by_family_activation": self._by_family(rows, predictions),
            "negative_noise_types": {
                noise: {
                    "labelled": sum(row["noise_type"] == noise for row in negatives),
                    "selected": sum(
                        row["noise_type"] == noise and bool(predictions[self._key(row)])
                        for row in negatives
                    ),
                }
                for noise in sorted({row["noise_type"] for row in negatives})
            },
        }

    def _validate_new_review(self, rows, articles, stored_candidate_keys) -> None:
        expected_keys = {
            key for key, article in articles.items()
            if article.risk_family_candidates and key not in stored_candidate_keys
        }
        errors = []
        seen = set()
        orders = []
        for number, row in enumerate(rows, start=2):
            key = self._key(row)
            if key in seen:
                errors.append(f"row {number}: duplicate article-company relation")
            seen.add(key)
            try:
                orders.append(int(row["review_order"]))
            except ValueError:
                errors.append(f"row {number}: invalid review_order")
            article = articles.get(key)
            if article is None:
                errors.append(f"row {number}: relation absent from normalized local cache")
                continue
            if key not in expected_keys:
                errors.append(f"row {number}: relation is not a new revised candidate")
            for field, source in (
                ("published_at_utc", article.published_at_utc or ""),
                ("title", article.title),
                ("content_available", article.content_available),
                ("link", article.link),
            ):
                if row[field] != source:
                    errors.append(f"row {number}: {field} differs from normalized cache")
            proposed = self._pipe_set(row["proposed_risk_families"])
            if proposed != set(article.risk_family_candidates):
                errors.append(f"row {number}: proposed families differ from revised filter")
            if self._parse_match_terms(row["risk_match_terms"]) != self._parse_match_terms(
                repr(article.risk_match_terms)
            ):
                errors.append(f"row {number}: match terms differ from revised filter")
            errors.extend(
                self.revised_annotation_validator.errors(row, row_number=number)
            )
        if seen != expected_keys:
            errors.append(
                f"new-candidate set differs: {len(expected_keys - seen)} missing, "
                f"{len(seen - expected_keys)} extra"
            )
        if orders != list(range(1, len(rows) + 1)):
            errors.append("review_order must be the consecutive sequence 1..N")
        if errors:
            raise ValueError("Invalid revised-candidate annotations:\n- " + "\n- ".join(errors))

    def _by_company(self, rows, predictions):
        result = {}
        for company in sorted({row["company"] for row in rows}):
            group = [row for row in rows if row["company"] == company]
            selected = [row for row in group if predictions[self._key(row)]]
            result[company] = {
                "labelled": len(group),
                "selected": len(selected),
                "positive_total": sum(row["relevant_risk_news"] == "true" for row in group),
                "true_positives": sum(row["relevant_risk_news"] == "true" for row in selected),
                "false_positives": sum(row["relevant_risk_news"] == "false" for row in selected),
            }
        return result

    def _by_family(self, rows, predictions):
        result = {}
        for family in sorted(self.families):
            activated = [row for row in rows if family in predictions[self._key(row)]]
            correct = [
                row for row in activated
                if row["relevant_risk_news"] == "true"
                and family in self._pipe_set(row["confirmed_risk_families"])
            ]
            result[family] = {
                "activations": len(activated),
                "correct_activations": len(correct),
                "false_activations": len(activated) - len(correct),
                "precision": self._ratio(len(correct), len(activated)),
            }
        return result

    def _term_diagnostics(self, rows, terms_by_key):
        counts: dict[str, Counter] = {}
        for row in rows:
            outcome = row["relevant_risk_news"]
            for family, terms in terms_by_key[self._key(row)].items():
                for term in terms:
                    counts.setdefault(f"{family}:{term}", Counter()).update([outcome])
        return {
            name: {
                "activations": values["true"] + values["false"],
                "positives": values["true"],
                "false_positives": values["false"],
                "precision": self._ratio(values["true"], values["true"] + values["false"]),
            }
            for name, values in sorted(counts.items())
        }

    def _corpus_comparison(self, articles, labelled_keys):
        old_counts = Counter()
        revised_counts = Counter()
        old_candidates = set()
        revised_candidates = set()
        for key, article in articles.items():
            old = set(article.risk_family_candidates)
            if old:
                old_candidates.add(key)
                old_counts.update(old)
            revised = set(self.risk_filter.apply(article))
            if revised:
                revised_candidates.add(key)
                revised_counts.update(revised)
        return {
            "article_company_relations": len(articles),
            "unique_articles": len({key[0] for key in articles}),
            "stored_candidate_relations": len(old_candidates),
            "revised_candidate_relations": len(revised_candidates),
            "retained_candidate_relations": len(old_candidates & revised_candidates),
            "removed_candidate_relations": len(old_candidates - revised_candidates),
            "new_candidate_relations": len(revised_candidates - old_candidates),
            "candidate_relation_change": len(revised_candidates) - len(old_candidates),
            "revised_relations_with_development_labels": len(revised_candidates & labelled_keys),
            "revised_relations_without_development_labels": len(revised_candidates - labelled_keys),
            "stored_family_activations": dict(sorted(old_counts.items())),
            "revised_family_activations": dict(sorted(revised_counts.items())),
        }

    @classmethod
    def _read_review(cls, path: Path):
        with path.open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            missing = sorted(cls.REQUIRED_FIELDS - set(reader.fieldnames or []))
            if missing:
                raise ValueError(f"Development review CSV is missing fields: {', '.join(missing)}")
            return [{key: (value or "").strip() for key, value in row.items()} for row in reader]

    @classmethod
    def _read_new_review(cls, path: Path):
        with path.open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            missing = sorted(cls.NEW_REVIEW_REQUIRED_FIELDS - set(reader.fieldnames or []))
            if missing:
                raise ValueError(f"Revised-candidate CSV is missing fields: {', '.join(missing)}")
            rows = [{key: (value or "").strip() for key, value in row.items()} for row in reader]
        for row in rows:
            row.setdefault("window_episode_id", "")
        return rows

    @staticmethod
    def _read_metadata(paths):
        result = {}
        for path in paths:
            with path.open(newline="", encoding="utf-8-sig") as stream:
                for row in csv.DictReader(stream):
                    key = row["article_id"], row["company"]
                    if key in result and result[key] != row:
                        raise ValueError(f"Conflicting acquisition metadata for relation: {key}")
                    result[key] = row
        return result

    @staticmethod
    def _parse_match_terms(value: str) -> dict[str, list[str]]:
        parsed = ast.literal_eval(value) if value else {}
        if not isinstance(parsed, dict):
            raise ValueError("risk_match_terms must be a dictionary")
        return {str(family): sorted(map(str, terms)) for family, terms in parsed.items()}

    @staticmethod
    def _pipe_set(value: str) -> set[str]:
        return set(filter(None, value.split("|")))

    @staticmethod
    def _key(row) -> tuple[str, str]:
        return row["article_id"], row["company"]

    @staticmethod
    def _ratio(numerator, denominator):
        return numerator / denominator if denominator else None

    @staticmethod
    def _source(path):
        return {"path": str(path), "sha256": file_sha256(path)}

    @staticmethod
    def _write_report(path: Path, result: dict) -> None:
        baseline = result["baseline_stored_filter"]
        revised = result["revised_local_filter"]
        union = result.get("candidate_union_comparison")
        evaluated_baseline = union["stored_filter"] if union else baseline
        evaluated_revised = union["revised_filter"] if union else revised
        old_selection = evaluated_baseline["selection"]
        new_selection = evaluated_revised["selection"]
        old_classification = evaluated_baseline["classification"]
        new_classification = evaluated_revised["classification"]
        episodes = evaluated_revised["episode_evidence"]
        corpus = result["local_cached_corpus"]
        baseline_terms = result["diagnostics"]["baseline_by_match_term"]
        top_terms = sorted(
            baseline_terms.items(),
            key=lambda item: (-item[1]["false_positives"], item[0]),
        )
        lines = [
            "# Métricas de desarrollo del filtro de noticias de riesgo",
            "",
            "## Resultado",
            "",
            f"- Filtro almacenado: {old_selection['true_positives']}/{old_selection['selected']} "
            f"positivos ({old_selection['precision']:.1%} de precisión de desarrollo).",
            f"- Filtro revisado: {new_selection['true_positives']}/{new_selection['selected']} "
            f"positivos ({new_selection['precision']:.1%} de precisión en el corpus local etiquetado).",
            f"- Cobertura de positivos en la unión de candidatos: "
            f"{new_selection['true_positives']}/"
            f"{union['review']['positives'] if union else result['review']['positives']} "
            f"({new_selection['positive_retention']:.1%}).",
            f"- Falsos positivos retenidos: {new_selection['false_positives']} frente a "
            f"{old_selection['false_positives']} en el filtro almacenado.",
            f"- Familia correcta entre positivos seleccionados: "
            f"{old_classification['family_accuracy_selected_positives']:.1%} → "
            f"{new_classification['family_accuracy_selected_positives']:.1%}"
            ".",
            f"- Evidencia conservada: {episodes['episodes_with_retained_evidence']}/"
            f"{episodes['episodes']} episodios recuperados.",
            *(
                [
                    f"- Estrato de candidatos nuevos: "
                    f"{result['revised_new_candidate_review']['metrics']['selection']['true_positives']}/"
                    f"{result['revised_new_candidate_review']['review']['rows']} positivos "
                    f"({result['revised_new_candidate_review']['metrics']['selection']['precision']:.1%})."
                ]
                if union else []
            ),
            *(
                [
                    "- Confusiones de familia restantes: "
                    + ", ".join(
                        f"`{name}`: {count}"
                        for name, count in new_classification["family_confusions"].items()
                    )
                    + "."
                ]
                if new_classification["family_confusions"] else []
            ),
            "",
            "## Diagnóstico de falsos positivos",
            "",
            "### Por familia",
            "",
            "| Familia | Activaciones anteriores | Incorrectas antes | Activaciones revisadas | Incorrectas ahora |",
            "|---|---:|---:|---:|---:|",
            *[
                f"| `{family}` | {evaluated_baseline['by_family_activation'][family]['activations']} | "
                f"{evaluated_baseline['by_family_activation'][family]['false_activations']} | "
                f"{evaluated_revised['by_family_activation'][family]['activations']} | "
                f"{evaluated_revised['by_family_activation'][family]['false_activations']} |"
                for family in sorted(evaluated_baseline["by_family_activation"])
            ],
            "",
            "### Por empresa",
            "",
            "| Empresa | FP anteriores | FP revisados | Positivos retenidos |",
            "|---|---:|---:|---:|",
            *[
                f"| `{company}` | {evaluated_baseline['by_company'][company]['false_positives']} | "
                f"{evaluated_revised['by_company'][company]['false_positives']} | "
                f"{evaluated_revised['by_company'][company]['true_positives']}/"
                f"{evaluated_revised['by_company'][company]['positive_total']} |"
                for company in sorted(evaluated_baseline["by_company"])
            ],
            "",
            "### Por tipo de ruido",
            "",
            "| Tipo | Etiquetados | Seleccionados antes | Seleccionados ahora |",
            "|---|---:|---:|---:|",
            *[
                f"| `{noise}` | {evaluated_baseline['negative_noise_types'][noise]['labelled']} | "
                f"{evaluated_baseline['negative_noise_types'][noise]['selected']} | "
                f"{evaluated_revised['negative_noise_types'][noise]['selected']} |"
                for noise in sorted(evaluated_baseline["negative_noise_types"])
            ],
            "",
            "### Términos anteriores con más falsos positivos",
            "",
            "| Término | Activaciones | Falsos positivos | Precisión |",
            "|---|---:|---:|---:|",
            *[
                f"| `{name}` | {values['activations']} | {values['false_positives']} | "
                f"{values['precision']:.1%} |"
                for name, values in top_terms
                if values["false_positives"]
            ],
            "",
            "## Reprocesado local",
            "",
            f"Se evaluaron {corpus['article_company_relations']} relaciones artículo-empresa de las cachés "
            "locales, sin llamadas de red.",
            "",
            f"- Candidatos almacenados: {corpus['stored_candidate_relations']}.",
            f"- Candidatos con las reglas revisadas: {corpus['revised_candidate_relations']}.",
            f"- Candidatos retenidos/nuevos/eliminados: {corpus['retained_candidate_relations']}/"
            f"{corpus['new_candidate_relations']}/{corpus['removed_candidate_relations']}.",
            f"- Candidatos revisados sin ninguna etiqueta: "
            f"{corpus.get('revised_relations_without_any_labels', corpus['revised_relations_without_development_labels'])}.",
            "",
            "## Interpretación",
            "",
            "Las 75 etiquetas nuevas se añadieron después de fijar las reglas y completan la revisión de "
            "los 98 candidatos del filtro revisado en estas cachés. La comparación sigue sin ser un "
            "holdout temporal independiente y no estima el recall sobre noticias que ninguno de los dos "
            "filtros seleccionó.",
            "No hay positivos etiquetados de `customer_concentration`; su comportamiento no puede "
            "validarse con este conjunto.",
            "",
            "Las noticias posteriores al 10-K se mantienen como contraste exploratorio y no construyen "
            "las etiquetas de pérdida documental entre informes anuales.",
            "",
        ]
        write_bytes(path, "\n".join(lines).encode("utf-8"))
