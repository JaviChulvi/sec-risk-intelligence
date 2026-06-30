import json
from pathlib import Path
from types import SimpleNamespace

from src.evals.hidden_risk_annual import (
    case_input_text,
    load_hidden_risk_eval,
    run_hidden_risk_annual_eval,
    score_hidden_risk_annual,
)
from src.llm.deepseek import DeepSeekResponse
from src.prompts.hidden_risk_annual import build_hidden_risk_annual_messages


def test_hidden_risk_fixture_has_one_year_per_case() -> None:
    payload = load_hidden_risk_eval()

    assert payload["eval_name"] == "annual_hidden_risk_discovery_item_1a"
    assert len(payload["cases"]) == 5
    assert [case["year"] for case in payload["cases"]] == [2021, 2022, 2023, 2024, 2025]
    assert "risk_domains" in payload["schema"]
    for case in payload["cases"]:
        assert str(case["year"]) in case["id"]
        assert case_input_text(case)
        assert "expected_hidden_risks" not in case
        assert case["sector"]
        assert case["industry"]
        assert case["business_model"]


def test_hidden_risk_prompt_requires_strict_json_and_single_year_analysis() -> None:
    messages = build_hidden_risk_annual_messages(
        {
            "company": "Guidewire Software, Inc.",
            "ticker": "GWRE",
            "year": 2025,
            "risk_factor_used": {"section": "Item 1A. Risk Factors"},
        },
        "The use of AI by our workforce may present risks to our business.",
    )

    combined = "\n".join(message["content"] for message in messages)

    assert "strict JSON" in combined
    assert "Do not compare against another year" in combined
    assert "Every quote must be a short exact contiguous quote" in combined
    assert "risk_domain" in combined
    assert "sector_specific_topic" in combined
    assert "hiddenness_type" in combined
    assert "hidden_risks" in combined


def model_output(
    hidden_risks: list[dict[str, object]],
    *,
    company: str = "Guidewire Software, Inc.",
    ticker: str = "GWRE",
    year: int = 2025,
    section: str = "Item 1A. Risk Factors",
) -> dict[str, object]:
    return {
        "company": company,
        "ticker": ticker,
        "year": year,
        "section": section,
        "hidden_risks": hidden_risks,
    }


def test_score_hidden_risk_annual_accepts_supported_discovery_finding() -> None:
    case_text = "Deposit funding costs may increase when customers move cash to higher-yielding alternatives."
    actual = model_output(
        [
            {
                "risk_id": "actual-bank-liquidity",
                "risk_domain": "credit_liquidity_capital",
                "sector_specific_topic": "deposit_outflow_and_funding_cost_pressure",
                "hiddenness_type": "indirect_causal_chain",
                "implicit_risk": "Deposit migration may raise funding costs and pressure liquidity management.",
                "why_hidden_or_underemphasized": "The text frames deposit behavior as a funding issue, but the wider exposure is margin and liquidity pressure.",
                "evidence": [
                    {
                        "quote": "Deposit funding costs may increase",
                        "reason": "This directly supports funding-cost pressure.",
                    }
                ],
                "severity": "medium",
                "confidence": "high",
            }
        ]
    )

    score = score_hidden_risk_annual([], actual, case_text, min_precision=1.0)

    assert score.passed
    assert score.scoring_mode == "discovery"
    assert score.expected_count == 0
    assert score.predicted_count == 1
    assert score.risk_precision == 1.0
    assert score.unsupported_claim_count == 0


def test_score_hidden_risk_annual_accepts_perfect_supported_benchmark_finding() -> None:
    case_text = (
        "The use of AI by our workforce may present risks to our business. "
        "Evolving policy and regulatory responses to AI technologies may result in increased compliance costs."
    )
    expected = [
        {
            "risk_id": "expected-ai",
            "risk_domain": "technology_cyber",
            "sector_specific_topic": "ai_governance",
            "hiddenness_type": "emerging_risk",
            "implicit_risk": "AI creates internal workforce and regulatory governance exposure.",
            "required_evidence_terms": ["AI", "workforce", "regulatory"],
            "accepted_evidence_quotes": ["The use of AI by our workforce may present risks"],
            "review_status": "candidate",
        }
    ]
    actual = model_output(
        [
            {
                "risk_id": "actual-ai",
                "risk_domain": "technology_cyber",
                "sector_specific_topic": "ai_governance",
                "hiddenness_type": "emerging_risk",
                "implicit_risk": "AI creates internal workforce and regulatory governance exposure.",
                "why_hidden_or_underemphasized": "The risk spans workforce use and regulation.",
                "evidence": [
                    {
                        "quote": "The use of AI by our workforce may present risks to our business.",
                        "reason": "This identifies internal AI usage risk.",
                    }
                ],
                "severity": "medium",
                "confidence": "high",
            }
        ]
    )

    score = score_hidden_risk_annual(expected, actual, case_text, min_recall=1.0, min_precision=1.0)

    assert score.passed
    assert score.scoring_mode == "benchmark"
    assert score.matched_count == 1
    assert score.unsupported_claim_count == 0
    assert score.evidence_support_rate == 1.0


def test_score_hidden_risk_annual_penalizes_claim_without_supported_quote() -> None:
    case_text = "Cloud subscription adoption may be difficult."
    actual = model_output(
        [
            {
                "risk_id": "actual-cloud",
                "risk_domain": "strategic",
                "sector_specific_topic": "cloud_subscription_adoption",
                "hiddenness_type": "underemphasized",
                "implicit_risk": "Cloud adoption creates execution risk.",
                "why_hidden_or_underemphasized": "The filing points to adoption difficulty.",
                "evidence": [{"quote": "This quote is not in the filing.", "reason": "Unsupported."}],
                "severity": "medium",
                "confidence": "high",
            }
        ]
    )

    score = score_hidden_risk_annual([], actual, case_text, min_precision=1.0)

    assert not score.passed
    assert score.matched_count == 0
    assert score.unsupported_claim_count == 1
    assert score.unsupported_claim_rate == 1.0


def test_score_hidden_risk_annual_rejects_invalid_schema_even_with_supported_quote() -> None:
    case_text = "Cloud subscription adoption may be difficult."
    actual = model_output(
        [
            {
                "risk_id": "actual-cloud",
                "risk_domain": "cloud",
                "sector_specific_topic": "cloud_subscription_adoption",
                "hiddenness_type": "unclear",
                "implicit_risk": "Cloud adoption creates execution risk.",
                "why_hidden_or_underemphasized": "The filing points to adoption difficulty.",
                "evidence": [
                    {
                        "quote": "Cloud subscription adoption may be difficult",
                        "reason": "This supports the adoption risk.",
                    }
                ],
                "severity": "critical",
                "confidence": "certain",
            }
        ]
    )

    score = score_hidden_risk_annual([], actual, case_text, min_precision=1.0)

    assert not score.passed
    assert score.predicted_count == 1
    assert score.supported_predicted_count == 0
    assert score.schema_error_count == 4
    assert {error["field"] for error in score.schema_errors} == {
        "risk_domain",
        "hiddenness_type",
        "severity",
        "confidence",
    }


def test_score_hidden_risk_annual_rejects_missing_top_level_metadata() -> None:
    case_text = "Cloud subscription adoption may be difficult."
    actual = {
        "hidden_risks": [
            {
                "risk_id": "actual-cloud",
                "risk_domain": "strategic",
                "sector_specific_topic": "cloud_subscription_adoption",
                "hiddenness_type": "underemphasized",
                "implicit_risk": "Cloud adoption creates execution risk.",
                "why_hidden_or_underemphasized": "The filing points to adoption difficulty.",
                "evidence": [
                    {
                        "quote": "Cloud subscription adoption may be difficult",
                        "reason": "This supports the adoption risk.",
                    }
                ],
                "severity": "medium",
                "confidence": "high",
            }
        ]
    }

    score = score_hidden_risk_annual([], actual, case_text, min_precision=1.0)

    assert not score.passed
    assert score.schema_error_count == 4
    assert {error["field"] for error in score.schema_errors} == {"company", "ticker", "year", "section"}


def test_score_hidden_risk_annual_rejects_top_level_metadata_mismatch() -> None:
    case_text = "Cloud subscription adoption may be difficult."
    actual = model_output(
        [
            {
                "risk_id": "actual-cloud",
                "risk_domain": "strategic",
                "sector_specific_topic": "cloud_subscription_adoption",
                "hiddenness_type": "underemphasized",
                "implicit_risk": "Cloud adoption creates execution risk.",
                "why_hidden_or_underemphasized": "The filing points to adoption difficulty.",
                "evidence": [
                    {
                        "quote": "Cloud subscription adoption may be difficult",
                        "reason": "This supports the adoption risk.",
                    }
                ],
                "severity": "medium",
                "confidence": "high",
            }
        ],
        ticker="WRONG",
        year=2024,
    )

    score = score_hidden_risk_annual(
        [],
        actual,
        case_text,
        expected_metadata={
            "company": "Guidewire Software, Inc.",
            "ticker": "GWRE",
            "year": 2025,
            "section": "Item 1A. Risk Factors",
        },
        min_precision=1.0,
    )

    assert not score.passed
    assert score.schema_error_count == 2
    assert {error["field"] for error in score.schema_errors} == {"ticker", "year"}


def test_score_hidden_risk_annual_accepts_empty_model_output() -> None:
    score = score_hidden_risk_annual([], model_output([]), "No meaningful risk text.")

    assert score.expected_count == 0
    assert score.predicted_count == 0
    assert score.risk_recall == 1.0
    assert score.risk_precision == 1.0
    assert score.evidence_support_rate == 1.0
    assert score.passed


def test_benchmark_requires_accepted_evidence_quote_when_provided() -> None:
    case_text = (
        "The use of AI by our workforce may present risks to our business. "
        "Evolving policy and regulatory responses to AI technologies may result in increased compliance costs."
    )
    expected = [
        {
            "risk_id": "expected-ai",
            "risk_domain": "technology_cyber",
            "implicit_risk": "AI creates internal workforce and regulatory governance exposure.",
            "required_evidence_terms": ["AI"],
            "accepted_evidence_quotes": ["The use of AI by our workforce may present risks"],
            "review_status": "candidate",
        }
    ]
    actual = model_output(
        [
            {
                "risk_id": "actual-ai",
                "risk_domain": "technology_cyber",
                "sector_specific_topic": "ai_governance",
                "hiddenness_type": "emerging_risk",
                "implicit_risk": "AI creates internal workforce and regulatory governance exposure.",
                "why_hidden_or_underemphasized": "The risk spans workforce use and regulation.",
                "evidence": [
                    {
                        "quote": "Evolving policy and regulatory responses to AI technologies",
                        "reason": "This supports AI regulatory pressure, but not the accepted workforce quote.",
                    }
                ],
                "severity": "medium",
                "confidence": "high",
            }
        ]
    )

    score = score_hidden_risk_annual(expected, actual, case_text, min_recall=1.0, min_precision=1.0)

    assert not score.passed
    assert score.matched_count == 0
    assert len(score.missing) == 1
    assert len(score.unexpected) == 1


def test_run_hidden_risk_eval_uses_self_contained_fixture(tmp_path: Path) -> None:
    eval_path = tmp_path / "hidden_eval.json"
    eval_path.write_text(
        json.dumps(
            {
                "eval_name": "unit-hidden-risk",
                "cases": [
                    {
                        "id": "unit-2025-hidden",
                        "company": "Guidewire Software, Inc.",
                        "ticker": "GWRE",
                        "year": 2025,
                        "filing": {"form": "10-K"},
                        "risk_factor_used": {
                            "section": "Item 1A. Risk Factors",
                            "source": "embedded_eval_json",
                            "word_count": 8,
                        },
                        "input": {
                            "section": "Item 1A. Risk Factors",
                            "text": "Cloud subscription adoption may be difficult for customers.",
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    client = FakeHiddenRiskClient()
    summary = run_hidden_risk_annual_eval(
        client,
        eval_path=eval_path,
        output_dir=tmp_path / "eval_runs",
        min_recall=1.0,
        min_precision=1.0,
    )

    assert summary.all_passed
    assert summary.cases_passed == 1
    assert (summary.output_dir / "summary.json").exists()


class FakeHiddenRiskClient:
    def __init__(self) -> None:
        self.config = SimpleNamespace(model="fake-model", base_url="https://example.test")

    def chat_json(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int,
        temperature: float | None,
    ) -> tuple[dict[str, object], DeepSeekResponse]:
        assert any("Cloud subscription adoption" in message["content"] for message in messages)
        return (
            model_output(
                [
                    {
                        "risk_id": "actual-cloud",
                        "risk_domain": "strategic",
                        "sector_specific_topic": "cloud_subscription_adoption",
                        "hiddenness_type": "underemphasized",
                        "implicit_risk": "Cloud subscription adoption creates execution risk.",
                        "why_hidden_or_underemphasized": "The filing points to adoption difficulty.",
                        "evidence": [
                            {
                                "quote": "Cloud subscription adoption may be difficult",
                                "reason": "This supports the adoption risk.",
                            }
                        ],
                        "severity": "medium",
                        "confidence": "high",
                    }
                ]
            ),
            DeepSeekResponse(
                content='{"hidden_risks": []}',
                model="fake-model",
                finish_reason="stop",
                usage={"total_tokens": 1},
                raw={},
            ),
        )
