import csv
import json
from pathlib import Path

import pytest

from src.news.eodhd_config import EodhdPilotConfig
from src.news.eodhd_report import EodhdReportBuilder
from src.news.review_metrics import ReviewMetricsBuilder


FIELDS = [
    "article_id", "company", "content_available", "risk_family_candidates",
    "selection_stratum", "review_status", "relevant_event", "noise_type",
    "episode_id", "reviewer", "notes",
]
CONFIG = Path(__file__).resolve().parents[2] / "config" / "eodhd_pilot.json"


def write_review(path, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def row(**overrides):
    value = {
        "article_id": "a1",
        "company": "AAPL",
        "content_available": "full",
        "risk_family_candidates": "cybersecurity",
        "selection_stratum": "risk_candidate",
        "review_status": "reviewed",
        "relevant_event": "false",
        "noise_type": "other_company",
        "episode_id": "",
        "reviewer": "ChatGPT-assisted",
        "notes": "Synthetic review note",
    }
    value.update(overrides)
    return value


def build(tmp_path, rows, population=3):
    review = tmp_path / "review.csv"
    manifest = tmp_path / "manifest.json"
    output = tmp_path / "metrics.json"
    write_review(review, rows)
    manifest.write_text(json.dumps({"counts": {"risk_candidates": population}}))
    result = ReviewMetricsBuilder().build(review, manifest, output)
    assert json.loads(output.read_text()) == result
    return result


def test_builds_stratified_metrics_and_conservative_population_bound(tmp_path):
    result = build(tmp_path, [
        row(),
        row(article_id="a2", relevant_event="true", noise_type="", episode_id="event-1", reviewer="Ana"),
        row(
            article_id="a3", risk_family_candidates="", selection_stratum="other",
            noise_type="routine_news", reviewer="Ana",
        ),
    ])
    assert result["review_unit"] == "article_company_relation"
    assert result["strata"]["risk_candidate"]["relevant"] == 1
    assert result["risk_candidate_population"]["review_coverage"] == pytest.approx(2 / 3)
    assert result["risk_candidate_population"]["observed_relevant_rate"] == 0.5
    assert result["risk_candidate_population"]["worst_case_relevant_rate"] == pytest.approx(2 / 3)
    assert result["methodology"]["independent_human_review"] is False


@pytest.mark.parametrize(
    "invalid, message",
    [
        ([row(), row()], "duplicate article-company"),
        ([row(noise_type="")], "no noise_type"),
        ([row(relevant_event="true", noise_type="", episode_id="")], "no episode_id"),
        ([row(reviewer="")], "no reviewer"),
        ([row(selection_stratum="other")], "unexpectedly has candidate families"),
    ],
)
def test_rejects_inconsistent_annotations(tmp_path, invalid, message):
    with pytest.raises(ValueError, match=message):
        build(tmp_path, invalid)


def test_report_includes_metrics_only_for_the_matching_manifest(tmp_path):
    review = tmp_path / "review.csv"
    manifest = tmp_path / "manifest.json"
    output = tmp_path / "report.md"
    write_review(review, [row()])
    manifest.write_text(json.dumps({
        "mode": "demo",
        "query_from": "2026-10-19",
        "query_to": "2026-10-19",
        "counts": {"risk_candidates": 1},
    }))
    ReviewMetricsBuilder().build(review, manifest, tmp_path / "review_metrics.json")

    EodhdReportBuilder(EodhdPilotConfig.load(CONFIG)).build(manifest, output)
    assert "## Revisión completa de candidatos y muestra de contraste" in output.read_text()

    manifest.write_text(json.dumps({"mode": "demo", "counts": {"risk_candidates": 2}}))
    with pytest.raises(ValueError, match="do not correspond"):
        EodhdReportBuilder(EodhdPilotConfig.load(CONFIG)).build(manifest, output)
