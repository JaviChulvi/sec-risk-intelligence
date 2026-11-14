from __future__ import annotations

import json
import sys

import pytest

from src.news.__main__ import main
from src.news.common import write_csv, write_json
from src.news.risk_news_calibration_comparison import RiskNewsCalibrationComparator
from src.news.risk_news_review_sheet import REVIEW_SHEET_FIELDS


def annotated_row(
    order: int,
    reviewer: str,
    *,
    relevant: bool,
    company_relevance: str | None = None,
    event_status: str = "materialized",
    confirmed_families: str = "cybersecurity",
    noise_type: str = "other_company",
) -> dict:
    return {
        "review_order": order,
        "selection_provenance": "test-dataset",
        "article_id": f"article-{order}",
        "company": "AAPL",
        "published_at_utc": f"202{order}-01-01T00:00:00+00:00",
        "title": f"Candidate {order}",
        "content_available": "full",
        "proposed_risk_families": "cybersecurity",
        "risk_match_terms": "{'cybersecurity': ['attack']}",
        "link": f"https://example.test/{order}",
        "review_status": "reviewed",
        "relevant_risk_news": str(relevant).lower(),
        "company_relevance": company_relevance or ("true" if relevant else "false"),
        "event_status": event_status if relevant else "",
        "confirmed_risk_families": confirmed_families if relevant else "",
        "noise_type": "" if relevant else noise_type,
        "reviewer": reviewer,
        "notes": "Confirmed risk" if relevant else "Different company",
    }


def write_fixture(tmp_path, reviewer_rows: dict[str, list[dict]]):
    manifest = tmp_path / "manifest.json"
    first_rows = next(iter(reviewer_rows.values()))
    write_json(manifest, {
        "purpose": "independent_human_annotation_calibration",
        "sample_size": len(first_rows),
        "rows": [{
            "calibration_order": row["review_order"],
            "article_id": row["article_id"],
            "company": row["company"],
            "published_year": row["published_at_utc"][:4],
            "content_available": row["content_available"],
            "proposed_risk_families": row["proposed_risk_families"],
        } for row in first_rows],
    })
    paths = []
    for slug, rows in reviewer_rows.items():
        path = tmp_path / f"{slug}.csv"
        write_csv(path, list(REVIEW_SHEET_FIELDS), rows)
        paths.append(path)
    return manifest, paths


def test_validates_complete_aligned_calibration_reviews(tmp_path):
    manifest, paths = write_fixture(tmp_path, {
        "ana": [
            annotated_row(1, "Ana", relevant=True),
            annotated_row(2, "Ana", relevant=False),
        ],
        "bea": [
            annotated_row(1, "Bea", relevant=False),
            annotated_row(2, "Bea", relevant=False),
        ],
    })

    result = RiskNewsCalibrationComparator().validate_inputs(
        manifest_path=manifest,
        review_paths=paths,
    )

    assert result["sample_size"] == 2
    assert result["reviewers"] == ["Ana", "Bea"]
    assert len(result["review_files"]) == 2


def test_rejects_incomplete_annotations(tmp_path):
    ana = [annotated_row(1, "Ana", relevant=True)]
    bea = [annotated_row(1, "Bea", relevant=False)]
    bea[0].update({
        "review_status": "pending",
        "relevant_risk_news": "",
        "company_relevance": "",
        "noise_type": "",
        "notes": "",
    })
    manifest, paths = write_fixture(tmp_path, {"ana": ana, "bea": bea})

    with pytest.raises(ValueError, match="review is not complete"):
        RiskNewsCalibrationComparator().validate_inputs(
            manifest_path=manifest,
            review_paths=paths,
        )


def test_rejects_review_metadata_that_differs_from_manifest(tmp_path):
    ana = [annotated_row(1, "Ana", relevant=True)]
    bea = [annotated_row(1, "Bea", relevant=True)]
    manifest, paths = write_fixture(tmp_path, {"ana": ana, "bea": bea})
    bea[0]["title"] = "Changed title"
    write_csv(paths[1], list(REVIEW_SHEET_FIELDS), bea)

    with pytest.raises(ValueError, match="immutable field title"):
        RiskNewsCalibrationComparator().validate_inputs(
            manifest_path=manifest,
            review_paths=paths,
        )


def test_rejects_duplicate_reviewer_names(tmp_path):
    manifest, paths = write_fixture(tmp_path, {
        "ana-1": [annotated_row(1, "Ana", relevant=True)],
        "ana-2": [annotated_row(1, "Ana", relevant=False)],
    })

    with pytest.raises(ValueError, match="reviewer names must be unique"):
        RiskNewsCalibrationComparator().validate_inputs(
            manifest_path=manifest,
            review_paths=paths,
        )


def test_calculates_conditional_exact_agreement_and_structured_discrepancies(tmp_path):
    reviewers = {}
    for reviewer in ("Ana", "Bea", "Carla"):
        reviewers[reviewer.casefold()] = [
            annotated_row(
                1,
                reviewer,
                relevant=True,
                event_status="exposure" if reviewer == "Carla" else "materialized",
            ),
            annotated_row(2, reviewer, relevant=reviewer == "Carla"),
            annotated_row(
                3,
                reviewer,
                relevant=False,
                company_relevance="true",
                noise_type="lexical_ambiguity",
            ),
        ]
    manifest, paths = write_fixture(tmp_path, reviewers)

    result = RiskNewsCalibrationComparator().compare(
        manifest_path=manifest,
        review_paths=paths,
    )

    assert result["agreement"]["rows"] == {
        "total": 3,
        "full_agreement": 1,
        "with_discrepancies": 2,
        "full_agreement_rate": 1 / 3,
    }
    assert result["agreement"]["fields"] == {
        "relevant_risk_news": {
            "scope": "all_rows",
            "eligible_rows": 3,
            "agreed_rows": 2,
            "discrepant_rows": 1,
            "exact_agreement": 2 / 3,
        },
        "company_relevance": {
            "scope": "all_rows",
            "eligible_rows": 3,
            "agreed_rows": 2,
            "discrepant_rows": 1,
            "exact_agreement": 2 / 3,
        },
        "event_status": {
            "scope": "any_annotator_positive",
            "eligible_rows": 2,
            "agreed_rows": 0,
            "discrepant_rows": 2,
            "exact_agreement": 0,
        },
        "confirmed_risk_families": {
            "scope": "any_annotator_positive",
            "eligible_rows": 2,
            "agreed_rows": 1,
            "discrepant_rows": 1,
            "exact_agreement": 0.5,
        },
        "noise_type": {
            "scope": "any_annotator_negative",
            "eligible_rows": 2,
            "agreed_rows": 1,
            "discrepant_rows": 1,
            "exact_agreement": 0.5,
        },
    }
    first = result["discrepancies"][0]
    assert first["review_order"] == 1
    assert first["discrepant_fields"] == {
        "event_status": {
            "Ana": "materialized",
            "Bea": "materialized",
            "Carla": "exposure",
        },
    }
    assert first["notes_by_reviewer"] == {
        "Ana": "Confirmed risk",
        "Bea": "Confirmed risk",
        "Carla": "Confirmed risk",
    }
    second = result["discrepancies"][1]
    assert set(second["discrepant_fields"]) == {
        "relevant_risk_news",
        "company_relevance",
        "event_status",
        "confirmed_risk_families",
        "noise_type",
    }


def test_compares_confirmed_families_as_an_unordered_set(tmp_path):
    manifest, paths = write_fixture(tmp_path, {
        "ana": [annotated_row(
            1,
            "Ana",
            relevant=True,
            confirmed_families="cybersecurity|critical_suppliers",
        )],
        "bea": [annotated_row(
            1,
            "Bea",
            relevant=True,
            confirmed_families="critical_suppliers|cybersecurity",
        )],
    })

    result = RiskNewsCalibrationComparator().compare(
        manifest_path=manifest,
        review_paths=paths,
    )

    assert result["agreement"]["rows"]["full_agreement"] == 1
    assert result["discrepancies"] == []


def test_cli_writes_calibration_comparison_json(tmp_path, monkeypatch, capsys):
    manifest, paths = write_fixture(tmp_path, {
        "ana": [annotated_row(1, "Ana", relevant=True)],
        "bea": [annotated_row(1, "Bea", relevant=False)],
    })
    output = tmp_path / "derived" / "comparison.json"
    monkeypatch.setattr(sys, "argv", [
        "python3 -m src.news",
        "eodhd",
        "dataset-calibration-compare",
        "--manifest",
        str(manifest),
        "--reviews",
        *(str(path) for path in paths),
        "--output",
        str(output),
    ])

    main()

    printed = json.loads(capsys.readouterr().out)
    stored = json.loads(output.read_text(encoding="utf-8"))
    assert stored == printed
    assert stored["agreement"]["rows"]["with_discrepancies"] == 1
    assert stored["discrepancies"][0]["review_order"] == 1
