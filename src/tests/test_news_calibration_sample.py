from __future__ import annotations

import csv
import json

import pytest

from src.news.common import write_csv
from src.news.risk_news_calibration_sample import RiskNewsCalibrationSampler
from src.news.risk_news_review_sheet import REVIEW_SHEET_FIELDS


CANDIDATE_FIELDS = [
    "article_id", "company", "risk_families", "duplicate_group_id",
]


def review_row(index: int, company: str, family: str, content: str) -> dict:
    return {
        "review_order": index,
        "selection_provenance": "test-dataset",
        "article_id": f"article-{index}",
        "company": company,
        "published_at_utc": f"{2020 + (index % 6)}-01-01T00:00:00+00:00",
        "title": f"Candidate {index}",
        "content_available": content,
        "proposed_risk_families": family,
        "risk_match_terms": "{}",
        "link": f"https://example.test/{index}",
        "review_status": "pending",
        "relevant_risk_news": "",
        "company_relevance": "",
        "event_status": "",
        "confirmed_risk_families": "",
        "noise_type": "",
        "reviewer": "",
        "notes": "",
    }


def test_builds_reproducible_identical_annotator_samples(tmp_path):
    review = tmp_path / "review.csv"
    candidates = tmp_path / "candidates.csv"
    rows = []
    candidate_rows = []
    index = 0
    for company in ("AAPL", "MSFT"):
        for family in ("critical_suppliers", "cybersecurity"):
            for content in ("summary_only", "partial", "full", "full"):
                index += 1
                row = review_row(index, company, family, content)
                rows.append(row)
                candidate_rows.append({
                    "article_id": row["article_id"],
                    "company": company,
                    "risk_families": family,
                    "duplicate_group_id": f"duplicate-{index}" if index % 2 else "",
                })
    write_csv(review, list(REVIEW_SHEET_FIELDS), rows)
    write_csv(candidates, CANDIDATE_FIELDS, candidate_rows)

    result = RiskNewsCalibrationSampler(seed="fixed").build(
        review_path=review,
        candidates_path=candidates,
        output_dir=tmp_path / "calibration",
        annotators=["Javi", "Hugo", "Higinio"],
        sample_size=12,
    )

    assert result["counts"]["by_company"] == {"AAPL": 6, "MSFT": 6}
    assert result["counts"]["by_designated_family"] == {
        "critical_suppliers": 6,
        "cybersecurity": 6,
    }
    samples = []
    for name in ("javi", "hugo", "higinio"):
        with (tmp_path / "calibration" / f"calibration_sample_12_{name}.csv").open(
            newline="", encoding="utf-8-sig"
        ) as stream:
            samples.append(list(csv.DictReader(stream)))
    assert all(
        [row["article_id"] for row in sample] ==
        [row["article_id"] for row in samples[0]]
        for sample in samples[1:]
    )
    assert [[row["reviewer"] for row in sample] for sample in samples] == [
        ["Javi"] * 12,
        ["Hugo"] * 12,
        ["Higinio"] * 12,
    ]
    manifest = json.loads(
        (tmp_path / "calibration" / "calibration_sample_12_manifest.json").read_text()
    )
    assert manifest["seed"] == "fixed"
    assert len(manifest["rows"]) == 12


def test_refuses_to_overwrite_started_annotation(tmp_path):
    path = tmp_path / "calibration_sample_1_javi.csv"
    row = review_row(1, "AAPL", "cybersecurity", "full")
    row["review_status"] = "reviewed"
    row["reviewer"] = "Javi"
    write_csv(path, list(REVIEW_SHEET_FIELDS), [row])

    with pytest.raises(ValueError, match="Refusing to overwrite"):
        RiskNewsCalibrationSampler._protect_output(path, expected_reviewer="Javi")
