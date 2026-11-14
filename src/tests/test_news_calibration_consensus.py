from __future__ import annotations

import csv
import json
import sys

import pytest

from src.news.__main__ import main
from src.news.common import write_csv, write_json
from src.news.risk_news_calibration_consensus import (
    RiskNewsCalibrationConsensusBuilder,
)


def comparison_payload() -> dict:
    ana = {
        "relevant_risk_news": "true",
        "company_relevance": "true",
        "event_status": "materialized",
        "confirmed_risk_families": "cybersecurity",
        "noise_type": "",
    }
    bea = {
        **ana,
        "event_status": "exposure",
    }
    return {
        "inputs": {"reviewers": ["Ana", "Bea"]},
        "discrepancies": [{
            "review_order": 7,
            "article_id": "article-7",
            "company": "AAPL",
            "published_at_utc": "2026-01-01T00:00:00+00:00",
            "title": "Security incident",
            "content_available": "full",
            "proposed_risk_families": "cybersecurity",
            "risk_match_terms": "{'cybersecurity': ['incident']}",
            "link": "https://example.test/article-7",
            "discrepant_fields": {
                "event_status": {"Ana": "materialized", "Bea": "exposure"},
            },
            "annotations_by_reviewer": {"Ana": ana, "Bea": bea},
            "notes_by_reviewer": {
                "Ana": "Impact already occurred",
                "Bea": "Only exposure is demonstrated",
            },
        }],
    }


def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        return list(reader), reader.fieldnames


def test_builds_consensus_sheet_with_agreed_fields_prefilled(tmp_path):
    comparison = tmp_path / "comparison.json"
    output = tmp_path / "consensus.csv"
    write_json(comparison, comparison_payload())

    result = RiskNewsCalibrationConsensusBuilder().build(
        comparison_path=comparison,
        output_path=output,
    )

    rows, fields = read_csv(output)
    assert result["rows"] == 1
    assert result["status"] == {"pending": 1}
    assert "ana__notes" in fields
    assert "bea__event_status" in fields
    assert rows[0]["calibration_order"] == "7"
    assert rows[0]["discrepant_fields"] == "event_status"
    assert rows[0]["consensus_relevant_risk_news"] == "true"
    assert rows[0]["consensus_company_relevance"] == "true"
    assert rows[0]["consensus_confirmed_risk_families"] == "cybersecurity"
    assert rows[0]["consensus_event_status"] == ""
    assert rows[0]["consensus_status"] == "pending"


def test_refuses_to_overwrite_an_edited_consensus_sheet(tmp_path):
    comparison = tmp_path / "comparison.json"
    output = tmp_path / "consensus.csv"
    write_json(comparison, comparison_payload())
    builder = RiskNewsCalibrationConsensusBuilder()
    builder.build(comparison_path=comparison, output_path=output)
    rows, fields = read_csv(output)
    rows[0]["consensus_event_status"] = "materialized"
    write_csv(output, fields, rows)

    with pytest.raises(ValueError, match="Refusing to overwrite edited consensus sheet"):
        builder.build(comparison_path=comparison, output_path=output)


def test_cli_writes_consensus_sheet(tmp_path, monkeypatch, capsys):
    comparison = tmp_path / "comparison.json"
    output = tmp_path / "derived" / "consensus.csv"
    write_json(comparison, comparison_payload())
    monkeypatch.setattr(sys, "argv", [
        "python3 -m src.news",
        "eodhd",
        "dataset-calibration-consensus-sheet",
        "--comparison",
        str(comparison),
        "--output",
        str(output),
    ])

    main()

    printed = json.loads(capsys.readouterr().out)
    rows, _ = read_csv(output)
    assert printed["rows"] == 1
    assert len(rows) == 1
