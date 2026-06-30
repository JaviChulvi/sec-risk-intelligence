from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable

from src.llm.deepseek import (
    DEFAULT_MAX_TOKENS,
    DeepSeekClient,
)
from src.prompts.hidden_risk_annual import build_hidden_risk_annual_messages


DEFAULT_MIN_RECALL = 0.70
DEFAULT_MIN_PRECISION = 0.80
DEFAULT_MAX_UNSUPPORTED_CLAIM_RATE = 0.20
DEFAULT_MATCH_THRESHOLD = 0.60
ALLOWED_RISK_DOMAINS = {
    "strategic",
    "operational",
    "financial",
    "market_macro",
    "credit_liquidity_capital",
    "regulatory_legal",
    "technology_cyber",
    "third_party",
    "governance_reputation",
    "accounting_reporting",
    "other",
}
ALLOWED_HIDDENNESS_TYPES = {
    "underemphasized",
    "fragmented_across_disclosure",
    "softened_language",
    "indirect_causal_chain",
    "emerging_risk",
    "buried_in_boilerplate",
    "repeated_but_not_escalated",
    "other",
}
ALLOWED_LEVELS = {"low", "medium", "high"}


@dataclass(frozen=True)
class HiddenRiskScore:
    scoring_mode: str
    expected_count: int
    predicted_count: int
    matched_count: int
    supported_predicted_count: int
    unsupported_claim_count: int
    schema_error_count: int
    risk_recall: float
    risk_precision: float
    evidence_support_rate: float
    unsupported_claim_rate: float
    schema_valid_rate: float
    passed: bool
    missing: list[dict[str, Any]]
    unexpected: list[dict[str, Any]]
    unsupported_claims: list[dict[str, Any]]
    schema_errors: list[dict[str, Any]]
    matches: list[dict[str, Any]]


@dataclass(frozen=True)
class EvalRunSummary:
    run_id: str
    output_dir: Path
    cases_total: int
    cases_passed: int
    all_passed: bool
    results: list[dict[str, Any]]


def load_hidden_risk_eval(path: Path | str = "hidden_risk_annual.discovery.json") -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def run_hidden_risk_annual_eval(
    client: DeepSeekClient,
    eval_path: Path | str = "hidden_risk_annual.discovery.json",
    output_dir: Path | str = "eval_runs",
    case_ids: set[str] | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    min_recall: float = DEFAULT_MIN_RECALL,
    min_precision: float = DEFAULT_MIN_PRECISION,
    max_unsupported_claim_rate: float = DEFAULT_MAX_UNSUPPORTED_CLAIM_RATE,
    match_threshold: float = DEFAULT_MATCH_THRESHOLD,
    temperature: float | None = 0.0,
    progress_callback: Callable[[str], None] | None = None,
) -> EvalRunSummary:
    eval_payload = load_hidden_risk_eval(eval_path)
    cases = list(eval_payload["cases"])
    if case_ids:
        cases = [case for case in cases if case["id"] in case_ids]
    if not cases:
        raise ValueError("No hidden-risk eval cases selected.")

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = Path(output_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    for eval_case in cases:
        if progress_callback:
            progress_callback(f"Starting {eval_case['id']}")
        result = run_single_case(
            client=client,
            eval_case=eval_case,
            run_dir=run_dir,
            max_tokens=max_tokens,
            min_recall=min_recall,
            min_precision=min_precision,
            max_unsupported_claim_rate=max_unsupported_claim_rate,
            match_threshold=match_threshold,
            temperature=temperature,
        )
        results.append(result)
        if progress_callback:
            score = result["score"]
            status = "PASS" if score["passed"] else "FAIL"
            if score.get("scoring_mode") == "benchmark":
                progress_callback(
                    f"{status} {eval_case['id']} "
                    f"matched {score['matched_count']}/{score['expected_count']} "
                    f"predicted {score['predicted_count']} "
                    f"unsupported {score['unsupported_claim_count']}"
                )
            else:
                progress_callback(
                    f"{status} {eval_case['id']} "
                    f"supported {score['supported_predicted_count']}/{score['predicted_count']} "
                    f"unsupported {score['unsupported_claim_count']}"
                )

    cases_passed = sum(1 for result in results if result["score"]["passed"])
    summary_payload = {
        "run_id": run_id,
        "eval_name": eval_payload.get("eval_name"),
        "model": client.config.model,
        "base_url": client.config.base_url,
        "thresholds": {
            "min_recall": min_recall,
            "min_precision": min_precision,
            "max_unsupported_claim_rate": max_unsupported_claim_rate,
            "match_threshold": match_threshold,
        },
        "cases_total": len(results),
        "cases_passed": cases_passed,
        "all_passed": cases_passed == len(results),
        "results": results,
    }
    (run_dir / "summary.json").write_text(
        json.dumps(summary_payload, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )

    return EvalRunSummary(
        run_id=run_id,
        output_dir=run_dir,
        cases_total=len(results),
        cases_passed=cases_passed,
        all_passed=cases_passed == len(results),
        results=results,
    )


def run_single_case(
    client: DeepSeekClient,
    eval_case: dict[str, Any],
    run_dir: Path,
    max_tokens: int,
    min_recall: float,
    min_precision: float,
    max_unsupported_claim_rate: float,
    match_threshold: float,
    temperature: float | None,
) -> dict[str, Any]:
    risk_factor_text = case_input_text(eval_case)
    messages = build_hidden_risk_annual_messages(eval_case, risk_factor_text)
    model_json, response = client.chat_json(
        messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    score = score_hidden_risk_annual(
        expected=eval_case.get("expected_hidden_risks") or [],
        actual=model_json,
        case_text=risk_factor_text,
        expected_metadata=expected_model_metadata(eval_case),
        min_recall=min_recall,
        min_precision=min_precision,
        max_unsupported_claim_rate=max_unsupported_claim_rate,
        match_threshold=match_threshold,
    )

    case_payload = {
        "case_id": eval_case["id"],
        "year": eval_case["year"],
        "filing": eval_case["filing"],
        "risk_factor_used": eval_case["risk_factor_used"],
        "model": response.model,
        "finish_reason": response.finish_reason,
        "usage": response.usage,
        "model_output": model_json,
        "score": score_to_dict(score),
    }
    case_path = run_dir / f"{eval_case['id']}.json"
    case_path.write_text(
        json.dumps(case_payload, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    return {
        "case_id": eval_case["id"],
        "year": eval_case["year"],
        "case_result_path": str(case_path),
        "score": score_to_dict(score),
        "usage": response.usage,
    }


def case_input_text(eval_case: dict[str, Any]) -> str:
    case_input = eval_case.get("input")
    if not isinstance(case_input, dict):
        raise ValueError(f"Hidden-risk eval case {eval_case.get('id', '<unknown>')} is missing input.text.")

    text = case_input.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ValueError(f"Hidden-risk eval case {eval_case.get('id', '<unknown>')} is missing input.text.")
    return text


def score_hidden_risk_annual(
    expected: list[dict[str, Any]],
    actual: dict[str, Any],
    case_text: str,
    expected_metadata: dict[str, Any] | None = None,
    min_recall: float = DEFAULT_MIN_RECALL,
    min_precision: float = DEFAULT_MIN_PRECISION,
    max_unsupported_claim_rate: float = DEFAULT_MAX_UNSUPPORTED_CLAIM_RATE,
    match_threshold: float = DEFAULT_MATCH_THRESHOLD,
) -> HiddenRiskScore:
    expected_items = coerce_expected_hidden_risks(expected)
    envelope_schema_errors = validate_model_output_envelope(actual, expected_metadata)
    predicted_items, risk_schema_errors = coerce_hidden_risks(actual)
    schema_errors = envelope_schema_errors + risk_schema_errors
    schema_valid_predicted = [item for item in predicted_items if not item.get("schema_errors")]
    supported_predicted, unsupported_claims = split_supported_hidden_risks(schema_valid_predicted, case_text)
    matches, missing, unexpected = match_hidden_risks(
        expected_items,
        supported_predicted,
        threshold=match_threshold,
    )

    expected_count = len(expected_items)
    predicted_count = len(predicted_items)
    matched_count = len(matches)
    supported_predicted_count = len(supported_predicted)
    unsupported_claim_count = len(unsupported_claims)
    schema_error_count = len(schema_errors)
    scoring_mode = "benchmark" if expected_count else "discovery"
    risk_recall = matched_count / expected_count if expected_count else 1.0
    risk_precision = (
        matched_count / predicted_count
        if expected_count and predicted_count
        else evidence_support_rate_for_counts(supported_predicted_count, predicted_count)
    )
    evidence_support_rate = supported_predicted_count / predicted_count if predicted_count else 1.0
    unsupported_claim_rate = unsupported_claim_count / predicted_count if predicted_count else 0.0
    if predicted_count:
        schema_valid_rate = len(schema_valid_predicted) / predicted_count
    else:
        schema_valid_rate = 1.0 if schema_error_count == 0 else 0.0
    passed = (
        risk_recall >= min_recall
        and risk_precision >= min_precision
        and unsupported_claim_rate <= max_unsupported_claim_rate
        and schema_error_count == 0
    )
    if scoring_mode == "discovery":
        passed = (
            evidence_support_rate >= min_precision
            and unsupported_claim_rate <= max_unsupported_claim_rate
            and schema_error_count == 0
        )

    return HiddenRiskScore(
        scoring_mode=scoring_mode,
        expected_count=expected_count,
        predicted_count=predicted_count,
        matched_count=matched_count,
        supported_predicted_count=supported_predicted_count,
        unsupported_claim_count=unsupported_claim_count,
        schema_error_count=schema_error_count,
        risk_recall=risk_recall,
        risk_precision=risk_precision,
        evidence_support_rate=evidence_support_rate,
        unsupported_claim_rate=unsupported_claim_rate,
        schema_valid_rate=schema_valid_rate,
        passed=passed,
        missing=missing,
        unexpected=unexpected,
        unsupported_claims=unsupported_claims,
        schema_errors=schema_errors,
        matches=matches,
    )


def expected_model_metadata(eval_case: dict[str, Any]) -> dict[str, Any]:
    risk_factor_used = eval_case.get("risk_factor_used") or {}
    return {
        "company": eval_case.get("company"),
        "ticker": eval_case.get("ticker"),
        "year": eval_case.get("year"),
        "section": risk_factor_used.get("section"),
    }


def coerce_expected_hidden_risks(expected: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index, item in enumerate(expected, start=1):
        if not isinstance(item, dict):
            continue
        risk_domain = str(item.get("risk_domain") or item.get("theme") or "other").strip()
        implicit_risk = str(item.get("implicit_risk") or "").strip()
        if not implicit_risk:
            continue
        items.append(
            {
                "risk_id": str(item.get("risk_id") or f"expected-{index}"),
                "risk_domain": normalize_risk_domain(risk_domain),
                "sector_specific_topic": str(
                    item.get("sector_specific_topic") or item.get("sector_specific_theme") or ""
                ).strip(),
                "hiddenness_type": normalize_hiddenness_type(str(item.get("hiddenness_type") or "other")),
                "implicit_risk": implicit_risk,
                "required_evidence_terms": [
                    str(term).strip()
                    for term in item.get("required_evidence_terms", [])
                    if str(term).strip()
                ],
                "accepted_evidence_quotes": [
                    str(quote).strip()
                    for quote in item.get("accepted_evidence_quotes", [])
                    if str(quote).strip()
                ],
                "review_status": str(item.get("review_status") or "candidate"),
            }
        )
    return items


def validate_model_output_envelope(
    actual: dict[str, Any],
    expected_metadata: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    string_fields = ("company", "ticker", "section")
    for field in string_fields:
        value = actual.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(schema_error("response", 0, field, f"{field} must be a non-empty string."))
            continue

        expected_value = (expected_metadata or {}).get(field)
        if expected_value is not None and value.strip() != str(expected_value).strip():
            errors.append(
                schema_error(
                    "response",
                    0,
                    field,
                    f"{field} must match expected value {expected_value!r}.",
                )
            )

    year = actual.get("year")
    if type(year) is not int:
        errors.append(schema_error("response", 0, "year", "year must be an integer."))
    else:
        expected_year = (expected_metadata or {}).get("year")
        if expected_year is not None and year != expected_year:
            errors.append(
                schema_error(
                    "response",
                    0,
                    "year",
                    f"year must match expected value {expected_year!r}.",
                )
            )

    return errors


def coerce_hidden_risks(actual: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    candidates = actual.get("hidden_risks")
    if candidates is None and isinstance(actual.get("result"), dict):
        candidates = actual["result"].get("hidden_risks")
    if candidates is None and isinstance(actual.get("expected_result_by_llm"), dict):
        candidates = actual["expected_result_by_llm"].get("hidden_risks")
    if not isinstance(candidates, list):
        return [], [
            schema_error(
                risk_id="response",
                index=0,
                field="hidden_risks",
                message="hidden_risks must be an array.",
            )
        ]

    items: list[dict[str, Any]] = []
    schema_errors: list[dict[str, Any]] = []
    for index, item in enumerate(candidates, start=1):
        if not isinstance(item, dict):
            schema_errors.append(
                schema_error(
                    risk_id=f"risk-{index}",
                    index=index,
                    field="hidden_risks[]",
                    message="Each hidden_risks item must be an object.",
                )
            )
            continue

        raw_risk_id = item.get("risk_id")
        risk_id = str(raw_risk_id or f"risk-{index}").strip()
        item_errors: list[dict[str, Any]] = []
        if not isinstance(raw_risk_id, str) or not raw_risk_id.strip():
            item_errors.append(schema_error(risk_id, index, "risk_id", "risk_id must be a non-empty string."))

        implicit_risk = str(item.get("implicit_risk") or item.get("risk") or item.get("claim") or "").strip()
        if not implicit_risk:
            item_errors.append(
                schema_error(risk_id, index, "implicit_risk", "implicit_risk must be a non-empty string.")
            )

        raw_risk_domain = item.get("risk_domain")
        risk_domain = str(raw_risk_domain or item.get("theme") or "").strip()
        normalized_risk_domain = normalize_topic(risk_domain)
        if not isinstance(raw_risk_domain, str) or not raw_risk_domain.strip():
            item_errors.append(schema_error(risk_id, index, "risk_domain", "risk_domain must be present."))
        elif normalized_risk_domain not in ALLOWED_RISK_DOMAINS:
            item_errors.append(
                schema_error(
                    risk_id,
                    index,
                    "risk_domain",
                    f"risk_domain must be one of {sorted(ALLOWED_RISK_DOMAINS)}.",
                )
            )

        sector_specific_topic = str(
            item.get("sector_specific_topic") or item.get("sector_specific_theme") or ""
        ).strip()
        if not isinstance(item.get("sector_specific_topic"), str) or not sector_specific_topic:
            item_errors.append(
                schema_error(
                    risk_id,
                    index,
                    "sector_specific_topic",
                    "sector_specific_topic must be a non-empty string.",
                )
            )

        raw_hiddenness_type = item.get("hiddenness_type")
        hiddenness_type = str(raw_hiddenness_type or "").strip()
        normalized_hiddenness_type = normalize_topic(hiddenness_type)
        if not isinstance(raw_hiddenness_type, str) or not raw_hiddenness_type.strip():
            item_errors.append(schema_error(risk_id, index, "hiddenness_type", "hiddenness_type must be present."))
        elif normalized_hiddenness_type not in ALLOWED_HIDDENNESS_TYPES:
            item_errors.append(
                schema_error(
                    risk_id,
                    index,
                    "hiddenness_type",
                    f"hiddenness_type must be one of {sorted(ALLOWED_HIDDENNESS_TYPES)}.",
                )
            )

        why_hidden = str(item.get("why_hidden_or_underemphasized") or "").strip()
        if not isinstance(item.get("why_hidden_or_underemphasized"), str) or not why_hidden:
            item_errors.append(
                schema_error(
                    risk_id,
                    index,
                    "why_hidden_or_underemphasized",
                    "why_hidden_or_underemphasized must be a non-empty string.",
                )
            )

        severity = str(item.get("severity") or "").lower().strip()
        if severity not in ALLOWED_LEVELS:
            item_errors.append(schema_error(risk_id, index, "severity", "severity must be low, medium, or high."))

        confidence = str(item.get("confidence") or "").lower().strip()
        if confidence not in ALLOWED_LEVELS:
            item_errors.append(schema_error(risk_id, index, "confidence", "confidence must be low, medium, or high."))

        evidence, evidence_errors = coerce_evidence_items(item.get("evidence"), risk_id=risk_id, index=index)
        item_errors.extend(evidence_errors)
        schema_errors.extend(item_errors)
        items.append(
            {
                "risk_id": risk_id,
                "risk_domain": normalize_risk_domain(risk_domain),
                "sector_specific_topic": normalize_topic(sector_specific_topic),
                "hiddenness_type": normalize_hiddenness_type(hiddenness_type),
                "implicit_risk": implicit_risk,
                "why_hidden_or_underemphasized": why_hidden,
                "evidence": evidence,
                "severity": severity if severity in ALLOWED_LEVELS else "",
                "confidence": confidence if confidence in ALLOWED_LEVELS else "",
                "schema_errors": item_errors,
            }
        )
    return items, schema_errors


def coerce_evidence_items(
    evidence: Any,
    *,
    risk_id: str,
    index: int,
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    schema_errors: list[dict[str, Any]] = []
    if not isinstance(evidence, list):
        return [], [
            schema_error(risk_id, index, "evidence", "evidence must be an array of quote/reason objects.")
        ]

    items: list[dict[str, str]] = []
    for evidence_index, item in enumerate(evidence, start=1):
        if not isinstance(item, dict):
            schema_errors.append(
                schema_error(
                    risk_id,
                    index,
                    f"evidence[{evidence_index}]",
                    "Each evidence item must be an object with quote and reason.",
                )
            )
            continue
        quote = item.get("quote") or item.get("text") or ""
        reason = item.get("reason") or ""
        quote = str(quote).strip()
        reason = str(reason).strip()
        if not quote:
            schema_errors.append(
                schema_error(risk_id, index, f"evidence[{evidence_index}].quote", "quote must be non-empty.")
            )
        if not reason:
            schema_errors.append(
                schema_error(risk_id, index, f"evidence[{evidence_index}].reason", "reason must be non-empty.")
            )
        if quote:
            items.append({"quote": quote, "reason": reason})
    return items, schema_errors


def schema_error(risk_id: str, index: int, field: str, message: str) -> dict[str, Any]:
    return {
        "risk_id": risk_id,
        "index": index,
        "field": field,
        "message": message,
    }


def split_supported_hidden_risks(
    predicted_items: list[dict[str, Any]],
    case_text: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    supported: list[dict[str, Any]] = []
    unsupported: list[dict[str, Any]] = []
    for item in predicted_items:
        evidence = item.get("evidence") or []
        supported_quotes = [
            evidence_item["quote"]
            for evidence_item in evidence
            if quote_is_supported(str(evidence_item.get("quote") or ""), case_text)
        ]
        annotated = {**item, "supported_evidence_quotes": supported_quotes}
        if supported_quotes:
            supported.append(annotated)
        else:
            unsupported.append(annotated)
    return supported, unsupported


def match_hidden_risks(
    expected_items: list[dict[str, Any]],
    predicted_items: list[dict[str, Any]],
    threshold: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    unmatched_predicted = set(range(len(predicted_items)))
    matches: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []

    for expected in expected_items:
        best_index = None
        best_score = 0.0
        best_term_ratio = 0.0
        best_accepted_quote_match = False
        for index in unmatched_predicted:
            predicted = predicted_items[index]
            if expected["risk_domain"] != predicted["risk_domain"]:
                continue
            accepted_quote_match = has_accepted_evidence_quote(expected, predicted)
            if not accepted_quote_match:
                continue
            similarity = text_similarity(expected["implicit_risk"], predicted["implicit_risk"])
            term_ratio = evidence_term_ratio(expected.get("required_evidence_terms", []), predicted)
            score = (0.75 * similarity) + (0.25 * term_ratio)
            if score > best_score:
                best_score = score
                best_term_ratio = term_ratio
                best_accepted_quote_match = accepted_quote_match
                best_index = index

        if best_index is not None and best_score >= threshold:
            predicted = predicted_items[best_index]
            unmatched_predicted.remove(best_index)
            matches.append(
                {
                    "expected_risk_id": expected["risk_id"],
                    "predicted_risk_id": predicted["risk_id"],
                    "risk_domain": expected["risk_domain"],
                    "sector_specific_topic": predicted.get("sector_specific_topic", ""),
                    "hiddenness_type": predicted.get("hiddenness_type", ""),
                    "expected_implicit_risk": expected["implicit_risk"],
                    "predicted_implicit_risk": predicted["implicit_risk"],
                    "similarity": round(text_similarity(expected["implicit_risk"], predicted["implicit_risk"]), 4),
                    "evidence_term_ratio": round(best_term_ratio, 4),
                    "accepted_evidence_quote_match": best_accepted_quote_match,
                    "match_score": round(best_score, 4),
                }
            )
        else:
            missing.append(expected)

    unexpected = [predicted_items[index] for index in sorted(unmatched_predicted)]
    return matches, missing, unexpected


def evidence_term_ratio(required_terms: list[str], predicted: dict[str, Any]) -> float:
    terms = [normalize_for_match(term) for term in required_terms if normalize_for_match(term)]
    if not terms:
        return 1.0
    evidence_text = " ".join(
        [
            str(predicted.get("implicit_risk") or ""),
            str(predicted.get("why_hidden_or_underemphasized") or ""),
            str(predicted.get("sector_specific_topic") or ""),
            " ".join(str(item.get("quote") or "") for item in predicted.get("evidence", [])),
        ]
    )
    normalized_evidence = normalize_for_match(evidence_text)
    matches = sum(1 for term in terms if term in normalized_evidence)
    return matches / len(terms)


def has_accepted_evidence_quote(expected: dict[str, Any], predicted: dict[str, Any]) -> bool:
    accepted_quotes = [
        str(quote).strip()
        for quote in expected.get("accepted_evidence_quotes", [])
        if str(quote).strip()
    ]
    if not accepted_quotes:
        return True
    predicted_quotes = [
        str(item.get("quote") or "").strip()
        for item in predicted.get("evidence", [])
        if str(item.get("quote") or "").strip()
    ]
    return any(
        quotes_match(predicted_quote, accepted_quote)
        for predicted_quote in predicted_quotes
        for accepted_quote in accepted_quotes
    )


def quotes_match(predicted_quote: str, accepted_quote: str) -> bool:
    predicted_normalized = normalize_for_evidence(predicted_quote)
    accepted_normalized = normalize_for_evidence(accepted_quote)
    if not predicted_normalized or not accepted_normalized:
        return False
    return predicted_normalized in accepted_normalized or accepted_normalized in predicted_normalized


def text_similarity(left: str, right: str) -> float:
    left_normalized = normalize_for_match(left)
    right_normalized = normalize_for_match(right)
    if not left_normalized or not right_normalized:
        return 0.0
    if left_normalized == right_normalized:
        return 1.0
    return SequenceMatcher(None, left_normalized, right_normalized).ratio()


def evidence_support_rate_for_counts(supported_count: int, predicted_count: int) -> float:
    return supported_count / predicted_count if predicted_count else 1.0


def normalize_risk_domain(value: str) -> str:
    normalized = normalize_topic(value)
    return normalized if normalized in ALLOWED_RISK_DOMAINS else "other"


def normalize_hiddenness_type(value: str) -> str:
    normalized = normalize_topic(value)
    return normalized if normalized in ALLOWED_HIDDENNESS_TYPES else "other"


def normalize_topic(value: str) -> str:
    value = value.strip().lower()
    value = value.replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return re.sub(r"_+", "_", value).strip("_")


def quote_is_supported(quote: str, case_text: str) -> bool:
    normalized_quote = normalize_for_evidence(quote)
    if not normalized_quote:
        return False
    return normalized_quote in normalize_for_evidence(case_text)


def normalize_for_match(value: str) -> str:
    value = value.lower()
    value = value.replace("\u2019", "'").replace("\u2018", "'")
    value = value.replace("\u201c", '"').replace("\u201d", '"')
    value = value.replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def normalize_for_evidence(value: str) -> str:
    value = value.replace("\u2019", "'").replace("\u2018", "'")
    value = value.replace("\u201c", '"').replace("\u201d", '"')
    return re.sub(r"\s+", " ", value).strip().lower()


def score_to_dict(score: HiddenRiskScore) -> dict[str, Any]:
    return {
        "scoring_mode": score.scoring_mode,
        "expected_count": score.expected_count,
        "predicted_count": score.predicted_count,
        "matched_count": score.matched_count,
        "supported_predicted_count": score.supported_predicted_count,
        "unsupported_claim_count": score.unsupported_claim_count,
        "schema_error_count": score.schema_error_count,
        "risk_recall": round(score.risk_recall, 4),
        "risk_precision": round(score.risk_precision, 4),
        "evidence_support_rate": round(score.evidence_support_rate, 4),
        "unsupported_claim_rate": round(score.unsupported_claim_rate, 4),
        "schema_valid_rate": round(score.schema_valid_rate, 4),
        "passed": score.passed,
        "missing": score.missing,
        "unexpected": score.unexpected,
        "unsupported_claims": score.unsupported_claims,
        "schema_errors": score.schema_errors,
        "matches": score.matches,
    }
