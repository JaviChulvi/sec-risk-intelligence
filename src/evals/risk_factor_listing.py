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
from src.prompts.risk_factor_listing import build_risk_factor_listing_messages


DEFAULT_MIN_RECALL = 0.98
DEFAULT_MIN_PRECISION = 0.95
DEFAULT_MATCH_THRESHOLD = 0.88


@dataclass(frozen=True)
class CaseScore:
    expected_count: int
    predicted_count: int
    matched_count: int
    recall: float
    precision: float
    passed: bool
    missing: list[dict[str, Any]]
    unexpected: list[dict[str, Any]]
    matches: list[dict[str, Any]]


@dataclass(frozen=True)
class EvalRunSummary:
    run_id: str
    output_dir: Path
    cases_total: int
    cases_passed: int
    all_passed: bool
    results: list[dict[str, Any]]


def load_eval(path: Path | str = "eval.json") -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def run_risk_factor_listing_eval(
    client: DeepSeekClient,
    eval_path: Path | str = "eval.json",
    output_dir: Path | str = "eval_runs",
    case_ids: set[str] | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    min_recall: float = DEFAULT_MIN_RECALL,
    min_precision: float = DEFAULT_MIN_PRECISION,
    match_threshold: float = DEFAULT_MATCH_THRESHOLD,
    temperature: float | None = 0.0,
    progress_callback: Callable[[str], None] | None = None,
) -> EvalRunSummary:
    eval_payload = load_eval(eval_path)
    cases = list(eval_payload["cases"])
    if case_ids:
        cases = [case for case in cases if case["id"] in case_ids]
    if not cases:
        raise ValueError("No eval cases selected.")

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
            match_threshold=match_threshold,
            temperature=temperature,
        )
        results.append(result)
        if progress_callback:
            score = result["score"]
            status = "PASS" if score["passed"] else "FAIL"
            progress_callback(
                f"{status} {eval_case['id']} "
                f"matched {score['matched_count']}/{score['expected_count']} "
                f"predicted {score['predicted_count']}"
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
    match_threshold: float,
    temperature: float | None,
) -> dict[str, Any]:
    risk_factor_text = case_input_text(eval_case)
    messages = build_risk_factor_listing_messages(eval_case, risk_factor_text)
    model_json, response = client.chat_json(
        messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    score = score_risk_factor_listing(
        expected=eval_case["expected_result_by_llm"],
        actual=model_json,
        min_recall=min_recall,
        min_precision=min_precision,
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
        raise ValueError(f"Eval case {eval_case.get('id', '<unknown>')} is missing input.text.")

    text = case_input.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ValueError(f"Eval case {eval_case.get('id', '<unknown>')} is missing input.text.")
    return text


def score_risk_factor_listing(
    expected: dict[str, Any],
    actual: dict[str, Any],
    min_recall: float = DEFAULT_MIN_RECALL,
    min_precision: float = DEFAULT_MIN_PRECISION,
    match_threshold: float = DEFAULT_MATCH_THRESHOLD,
) -> CaseScore:
    expected_items = expected.get("risk_factors") or []
    predicted_items = coerce_risk_factor_items(actual)
    matches, missing, unexpected = match_risk_factors(
        expected_items,
        predicted_items,
        threshold=match_threshold,
    )

    expected_count = len(expected_items)
    predicted_count = len(predicted_items)
    matched_count = len(matches)
    recall = matched_count / expected_count if expected_count else 1.0
    precision = matched_count / predicted_count if predicted_count else 0.0

    return CaseScore(
        expected_count=expected_count,
        predicted_count=predicted_count,
        matched_count=matched_count,
        recall=recall,
        precision=precision,
        passed=recall >= min_recall and precision >= min_precision,
        missing=missing,
        unexpected=unexpected,
        matches=matches,
    )


def coerce_risk_factor_items(actual: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = actual.get("risk_factors")
    if candidates is None and isinstance(actual.get("expected_result_by_llm"), dict):
        candidates = actual["expected_result_by_llm"].get("risk_factors")
    if candidates is None and isinstance(actual.get("result"), dict):
        candidates = actual["result"].get("risk_factors")
    if not isinstance(candidates, list):
        return []

    items: list[dict[str, Any]] = []
    for index, item in enumerate(candidates, start=1):
        if isinstance(item, str):
            title = item
            category = None
            order = index
        elif isinstance(item, dict):
            title = item.get("title") or item.get("risk_factor") or item.get("heading") or ""
            category = item.get("category")
            order = item.get("order", index)
        else:
            continue
        title = str(title).strip()
        if not title:
            continue
        items.append({"order": order, "category": category, "title": title})
    return items


def match_risk_factors(
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
        expected_title = str(expected["title"])
        expected_normalized = normalize_title(expected_title)
        for index in unmatched_predicted:
            predicted_title = str(predicted_items[index]["title"])
            predicted_normalized = normalize_title(predicted_title)
            score = title_similarity(expected_normalized, predicted_normalized)
            if score > best_score:
                best_score = score
                best_index = index

        if best_index is not None and best_score >= threshold:
            predicted = predicted_items[best_index]
            unmatched_predicted.remove(best_index)
            matches.append(
                {
                    "expected_order": expected.get("order"),
                    "predicted_order": predicted.get("order"),
                    "expected_title": expected_title,
                    "predicted_title": predicted["title"],
                    "similarity": round(best_score, 4),
                }
            )
        else:
            missing.append(expected)

    unexpected = [predicted_items[index] for index in sorted(unmatched_predicted)]
    return matches, missing, unexpected


def title_similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    return SequenceMatcher(None, left, right).ratio()


def normalize_title(value: str) -> str:
    value = value.lower()
    value = value.replace("\u2019", "'").replace("\u2018", "'")
    value = value.replace("\u201c", '"').replace("\u201d", '"')
    value = value.replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def score_to_dict(score: CaseScore) -> dict[str, Any]:
    return {
        "expected_count": score.expected_count,
        "predicted_count": score.predicted_count,
        "matched_count": score.matched_count,
        "recall": round(score.recall, 4),
        "precision": round(score.precision, 4),
        "passed": score.passed,
        "missing": score.missing,
        "unexpected": score.unexpected,
        "matches": score.matches,
    }
