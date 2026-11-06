import csv
import json
from pathlib import Path

import pytest

from src.news.eodhd_config import EodhdPilotConfig
from src.news.risk_news_revised_candidate_review import RevisedRiskNewsCandidateReviewBuilder
from src.tests.news_helpers import normalized_article


CONFIG = Path(__file__).resolve().parents[2] / "config" / "eodhd_pilot.json"


def test_exports_only_new_revised_candidates_and_protects_annotations(tmp_path):
    stored_candidate = normalized_article(
        article_id="stored",
        title="Apple responds to spyware attack",
        content="Apple said spyware infected targeted users.",
        risk_family_candidates=["cybersecurity"],
        risk_match_terms={"cybersecurity": ["cyberattack"]},
    )
    new_candidate = normalized_article(
        article_id="new",
        company="MSFT",
        title="Global IT outage affects Microsoft Windows",
        content="A faulty software update caused the outage.",
        risk_family_candidates=[],
        risk_match_terms={},
    )
    non_candidate = normalized_article(
        article_id="ordinary",
        title="Apple launches an ordinary product",
        content="Apple announced a routine update.",
        risk_family_candidates=[],
        risk_match_terms={},
    )
    root = tmp_path / "normalized" / "company" / "ticker" / "window"
    root.mkdir(parents=True)
    with (root / "articles.jsonl").open("w", encoding="utf-8") as stream:
        for article in (stored_candidate, new_candidate, non_candidate):
            stream.write(json.dumps(article.to_dict()) + "\n")

    config = EodhdPilotConfig.load(CONFIG)
    builder = RevisedRiskNewsCandidateReviewBuilder(config.values)
    output = tmp_path / "review.csv"
    result = builder.build(tmp_path / "normalized", output)

    with output.open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    assert result["rows"] == 1
    assert rows[0]["article_id"] == "new"
    assert rows[0]["proposed_risk_families"] == "critical_suppliers"
    assert rows[0]["review_status"] == "pending"
    assert "content" not in rows[0]

    rows[0]["review_status"] = "reviewed"
    rows[0]["relevant_risk_news"] = "false"
    with output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ValueError, match="Refusing to overwrite"):
        builder.build(tmp_path / "normalized", output)
