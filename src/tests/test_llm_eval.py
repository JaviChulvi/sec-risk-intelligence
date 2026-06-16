import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.llm.deepseek import DeepSeekAPIError, DeepSeekResponse, parse_json_content
from src.evals.risk_factor_listing import (
    case_input_text,
    coerce_risk_factor_items,
    run_risk_factor_listing_eval,
    score_risk_factor_listing,
)
from src.prompts.risk_factor_listing import build_risk_factor_listing_messages


def test_parse_json_content_accepts_plain_json() -> None:
    parsed = parse_json_content('{"risk_factors": []}')

    assert parsed == {"risk_factors": []}


def test_parse_json_content_accepts_fenced_json() -> None:
    parsed = parse_json_content('```json\n{"risk_factors": []}\n```')

    assert parsed == {"risk_factors": []}


def test_parse_json_content_rejects_non_object() -> None:
    with pytest.raises(DeepSeekAPIError):
        parse_json_content("[1, 2, 3]")


def test_coerce_risk_factor_items_handles_common_shapes() -> None:
    items = coerce_risk_factor_items(
        {
            "risk_factors": [
                {"order": 2, "category": "General", "heading": "A risk heading."},
                "Another risk heading.",
            ]
        }
    )

    assert items == [
        {"order": 2, "category": "General", "title": "A risk heading."},
        {"order": 2, "category": None, "title": "Another risk heading."},
    ]


def test_score_risk_factor_listing_matches_minor_wording_differences() -> None:
    expected = {
        "risk_factors": [
            {
                "order": 1,
                "category": "Risks Related to our Business",
                "title": "We may experience significant quarterly and annual fluctuations in our results of operations due to a number of factors.",
            }
        ]
    }
    actual = {
        "risk_factors": [
            {
                "order": 1,
                "category": "Risks Related to our Business",
                "title": "We may experience significant quarterly and annual fluctuations in results of operations due to a number of factors",
            }
        ]
    }

    score = score_risk_factor_listing(expected, actual, min_recall=1.0, min_precision=1.0)

    assert score.passed
    assert score.matched_count == 1
    assert not score.missing
    assert not score.unexpected


def test_build_prompt_tells_model_to_return_json_and_ignore_summary_bullets() -> None:
    messages = build_risk_factor_listing_messages(
        {
            "company": "Guidewire Software, Inc.",
            "ticker": "GWRE",
            "year": 2025,
            "risk_factor_used": {"section": "Item 1A. Risk Factors"},
        },
        "SUMMARY OF MATERIAL RISKS\n- summary bullet\nRisks Related to our Business\nActual risk heading.",
    )

    combined = "\n".join(message["content"] for message in messages)

    assert "strict JSON" in combined
    assert "Ignore any bullet list" in combined
    assert "Do not infer hidden risks" in combined
    assert "Guidewire Software" in combined


def test_case_input_text_reads_embedded_eval_text() -> None:
    assert case_input_text({"id": "case-1", "input": {"text": "Risk factor text"}}) == "Risk factor text"


def test_case_input_text_rejects_missing_embedded_text() -> None:
    with pytest.raises(ValueError, match="input.text"):
        case_input_text({"id": "case-1", "risk_factor_used": {"source": "legacy_file"}})


def test_run_eval_uses_self_contained_fixture(tmp_path: Path) -> None:
    eval_path = tmp_path / "eval.json"
    eval_path.write_text(
        json.dumps(
            {
                "eval_name": "unit-risk-factor-listing",
                "cases": [
                    {
                        "id": "unit-2025",
                        "company": "Guidewire Software, Inc.",
                        "ticker": "GWRE",
                        "year": 2025,
                        "filing": {"form": "10-K"},
                        "risk_factor_used": {
                            "section": "Item 1A. Risk Factors",
                            "source": "embedded_eval_json",
                            "word_count": 4,
                        },
                        "input": {"section": "Item 1A. Risk Factors", "text": "Actual risk heading."},
                        "expected_result_by_llm": {
                            "risk_factor_count": 1,
                            "risk_factors": [
                                {
                                    "order": 1,
                                    "category": "General",
                                    "title": "Actual risk heading.",
                                }
                            ],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    client = FakeDeepSeekClient()
    summary = run_risk_factor_listing_eval(
        client,
        eval_path=eval_path,
        output_dir=tmp_path / "eval_runs",
        min_recall=1.0,
        min_precision=1.0,
    )

    assert summary.all_passed
    assert summary.cases_passed == 1
    assert (summary.output_dir / "summary.json").exists()


class FakeDeepSeekClient:
    def __init__(self) -> None:
        self.config = SimpleNamespace(model="fake-model", base_url="https://example.test")

    def chat_json(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int,
        temperature: float | None,
    ) -> tuple[dict[str, object], DeepSeekResponse]:
        assert any("Actual risk heading." in message["content"] for message in messages)
        return (
            {
                "risk_factors": [
                    {
                        "order": 1,
                        "category": "General",
                        "title": "Actual risk heading.",
                    }
                ]
            },
            DeepSeekResponse(
                content='{"risk_factors": []}',
                model="fake-model",
                finish_reason="stop",
                usage={"total_tokens": 1},
                raw={},
            ),
        )
