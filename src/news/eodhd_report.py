from __future__ import annotations

import json
from pathlib import Path

from .common import file_sha256, write_bytes
from .eodhd_config import EodhdPilotConfig


class EodhdReportBuilder:
    def __init__(self, config: EodhdPilotConfig):
        self.config = config

    def build(self, manifest_path: Path, output: Path) -> dict:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        counts = manifest.get("counts", {})
        availability = manifest.get("content_availability", {})
        total = counts.get("articles", 0)
        useful = availability.get("full", 0) + availability.get("partial", 0)
        useful_rate = useful / total if total else None
        candidates = counts.get("risk_candidates", 0)
        useful_candidates = counts.get("useful_risk_candidates", 0)
        candidate_useful_rate = useful_candidates / candidates if candidates else None
        duplicate_rate = counts.get("duplicate_excess_records", 0) / total if total else None
        recall = manifest.get("known_event_recall")
        reviewed_useful_rate = manifest.get("reviewed_relevant_useful_content_rate")
        decision, reason = self._decision(recall, reviewed_useful_rate, manifest)
        review_metrics_path = manifest_path.parent / "review_metrics.json"
        review_metrics = self._load_review_metrics(review_metrics_path, manifest_path)
        lines = [
            "# Piloto EODHD para noticias MAG7",
            "",
            f"Ejecución: `{manifest.get('mode', 'unknown')}`; intervalo "
            f"`{manifest.get('query_from', '?')}` a `{manifest.get('query_to', '?')}`.",
            "",
            "## Alcance medido",
            "",
            f"- Artículos recuperados: {total}.",
            f"- Identificadores únicos: {counts.get('unique_article_ids', 0)}.",
            f"- Llamadas HTTP consumidas al adquirir el caché: {counts.get('http_calls', 0)}; "
            f"en esta ejecución: {counts.get('http_calls_this_run', 0)}; reintentos: {counts.get('retries', 0)}.",
            f"- Ventanas completas: {counts.get('windows_complete', 0)}; fallidas: {counts.get('windows_failed', 0)}.",
            f"- Grupos duplicados propuestos: {counts.get('duplicate_groups', 0)}.",
            f"- Exceso de registros dentro de grupos duplicados: {counts.get('duplicate_excess_records', 0)} "
            f"({duplicate_rate:.1%})." if duplicate_rate is not None else "- Duplicación: no calculable.",
            f"- Episodios propuestos para revisión: {counts.get('event_proposals', 0)}.",
            f"- Candidatos léxicos: {candidates}; con texto `full` o `partial`: {useful_candidates} "
            f"({candidate_useful_rate:.1%})." if candidate_useful_rate is not None else "- Candidatos léxicos: 0.",
            f"- Longitud mediana: {manifest.get('content_length_words_median', 'n/d')} palabras.",
            "",
            "## Calidad del contenido",
            "",
        ]
        for label in ("full", "partial", "summary_only", "missing", "invalid"):
            value = availability.get(label, 0)
            rate = value / total if total else 0
            lines.append(f"- `{label}`: {value} ({rate:.1%}).")
        storage = manifest.get("storage_bytes", {})
        lines += [
            "",
            "## Viabilidad técnica inicial",
            "",
            f"- Almacenamiento restringido bruto: {storage.get('raw_restricted', 0)} bytes.",
            f"- Normalizados restringidos: {storage.get('normalized_restricted', 0)} bytes.",
            f"- Derivados sin cuerpos: {storage.get('derived_without_bodies', 0)} bytes.",
            "- El mínimo teórico del histórico es de 9 llamadas por mes (nueve símbolos de consulta); "
            "la paginación, los reintentos y eventuales subdivisiones elevarán ese valor.",
        ]
        observations_path = manifest_path.parent / "manual_observations.json"
        if observations_path.exists():
            observations = json.loads(observations_path.read_text(encoding="utf-8"))
            lines += ["", "## Inspección cualitativa del smoke test", ""]
            lines.extend(f"- {finding}" for finding in observations.get("findings", []))
            if observations.get("quantitative_noise_rate") is None and review_metrics is None:
                lines.append("- No se estima todavía una tasa de ruido: la muestra no fue anotada formalmente.")
        if review_metrics is not None:
            lines.extend(self._review_section(review_metrics))
        lines += [
            "",
            "## Decisión provisional",
            "",
            f"**{decision}** — {reason}",
            "",
            "Esta ejecución no convierte artículos en acontecimientos confirmados ni utiliza sentimiento "
            "como etiqueta adversa. Una ausencia de resultados significa únicamente ausencia de evidencia localizada.",
            "",
            "## Limitaciones pendientes",
            "",
            (
                "- Confirmar las anotaciones con revisión humana independiente y revisar duplicados y agrupaciones de episodios."
                if review_metrics is not None
                else "- Revisar manualmente candidatos, ruido, duplicados y agrupaciones de episodios."
            ),
            "- Completar la referencia de 49 fichas antes de medir recuperación por episodio.",
            "- Incorporar el manifiesto SEC para construir las ventanas posteriores a cada segundo 10-K.",
            "- Verificar condiciones de conservación y redistribución antes del histórico 2021–2026.",
            "",
        ]
        write_bytes(output, ("\n".join(lines) + "\n").encode("utf-8"))
        return {"decision": decision, "reason": reason, "useful_content_rate": useful_rate, "output": str(output)}

    def _review_section(self, metrics: dict) -> list[str]:
        rows = metrics["rows"]
        strata = metrics["strata"]
        candidate = strata["risk_candidate"]
        other = strata["other"]
        population = metrics["risk_candidate_population"]
        noise = metrics.get("risk_candidate_noise_types", {})
        noise_text = ", ".join(f"`{name}`: {count}" for name, count in noise.items()) or "ninguno"
        coverage = self._percentage(population.get("review_coverage"))
        observed = self._percentage(population.get("observed_relevant_rate"))
        upper = self._percentage(population.get("worst_case_relevant_rate"))
        complete = population["total"] > 0 and population["unreviewed"] == 0
        lines = [
            "",
            (
                "## Revisión completa de candidatos y muestra de contraste"
                if complete else "## Revisión de la muestra estratificada"
            ),
            "",
            f"- Filas revisadas: {rows['reviewed']} de {rows['total']}; la unidad es la relación artículo-empresa "
            f"({rows['unique_article_ids']} artículos únicos).",
            f"- Estrato `risk_candidate`: {candidate['reviewed']} revisados, {candidate['relevant']} relevantes "
            f"y {candidate['not_relevant']} no relevantes; tasa observada de relevancia: {observed}.",
            f"- Cobertura de candidatos del smoke test: {population['reviewed']} de {population['total']} ({coverage}); "
            f"quedan {population['unreviewed']} sin revisar.",
            f"- Estrato de contraste `other`: {other['reviewed']} revisados y {other['relevant']} relevantes.",
            f"- Causas de ruido entre candidatos revisados: {noise_text}.",
        ]
        if complete:
            lines.insert(
                5,
                f"- Al estar revisados los {population['total']} candidatos, el 0.0% es el resultado completo "
                "de este smoke test, no una extrapolación desde la muestra.",
            )
        else:
            lines.insert(
                5,
                f"- Incluso si todos los candidatos no revisados fueran relevantes, la tasa en los "
                f"{population['total']} candidatos no superaría {upper} "
                f"({population['worst_case_relevant_count']} casos).",
            )
        if not metrics.get("methodology", {}).get("independent_human_review", False):
            lines.append(
                "- La anotación figura como asistida por ChatGPT: es útil para diagnosticar reglas, pero no es un "
                "gold standard humano independiente ni una estimación estadística de precisión."
            )
        return lines

    @staticmethod
    def _percentage(value) -> str:
        return "n/d" if value is None else f"{value:.1%}"

    @staticmethod
    def _load_review_metrics(metrics_path: Path, manifest_path: Path) -> dict | None:
        if not metrics_path.exists():
            return None
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        expected_hash = metrics.get("manifest_file_sha256")
        if expected_hash != file_sha256(manifest_path):
            raise ValueError(
                "Review metrics do not correspond to the current manifest; rerun the review command"
            )
        return metrics

    def _decision(self, recall, reviewed_useful_rate, manifest) -> tuple[str, str]:
        if manifest.get("mode") != "pilot":
            return "PENDIENTE", "el smoke test no mide recuperación de episodios conocidos"
        if recall is None or reviewed_useful_rate is None:
            return "PENDIENTE", "faltan la referencia por episodios o la revisión del texto relevante"
        thresholds = self.config["decision_thresholds"]
        if recall >= thresholds["go_min_known_event_recall"] and reviewed_useful_rate >= thresholds["go_min_useful_content_rate"]:
            return "GO", "cumple los umbrales configurados de recuperación y texto útil"
        if recall >= thresholds["go_with_complements_min_known_event_recall"]:
            return "GO_CON_COMPLEMENTOS", "la recuperación requiere fuentes complementarias o mejora focalizada"
        return "NO_GO", "la recuperación queda por debajo del umbral mínimo configurado"
