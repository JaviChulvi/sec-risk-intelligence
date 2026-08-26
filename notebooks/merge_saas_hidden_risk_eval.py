#!/usr/bin/env python3
"""Merge reviewed hidden-risk annotations into the prepared SaaS annual fixture."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DATASET_DIR = Path("data") / "saas_50_latest_10_10ks"
DEFAULT_PREPARED = DATASET_DIR / "saas_50_hidden_risk_annual.prepared.json"
DEFAULT_STAGING = DATASET_DIR / "eval_staging"
DEFAULT_OUTPUT = DATASET_DIR / "saas_50_hidden_risk_annual.json"
DOMAINS = {"strategic", "operational", "financial", "market_macro", "credit_liquidity_capital", "regulatory_legal", "technology_cyber", "third_party", "governance_reputation", "accounting_reporting", "other"}
HIDDENNESS = {"underemphasized", "fragmented_across_disclosure", "softened_language", "indirect_causal_chain", "emerging_risk", "buried_in_boilerplate", "repeated_but_not_escalated", "other"}


def main() -> None:
    args = parse_args()
    payload = json.loads(args.prepared.read_text(encoding="utf-8"))
    cases = payload.get("cases")
    if not isinstance(cases, list) or len(cases) != 500:
        raise RuntimeError("Prepared fixture must contain exactly 500 cases.")
    by_id = {case["id"]: case for case in cases}
    annotations = load_annotations(args.staging)
    unknown = set(annotations) - set(by_id)
    if unknown:
        raise RuntimeError(f"Unknown annotation case ids: {sorted(unknown)[:3]}")
    if not args.allow_incomplete and set(annotations) != set(by_id):
        raise RuntimeError(f"Missing annotations for {len(set(by_id) - set(annotations))} cases.")
    for case_id, expected in annotations.items():
        validate_expected(case_id, expected, by_id[case_id]["input"]["text"])
        by_id[case_id]["expected_hidden_risks"] = expected
    payload["description"] = "Self-contained, manually reviewed candidate hidden-risk benchmark for 500 SaaS and cloud annual 10-K Item 1A sections."
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(cases)} cases with {len(annotations)} annotated to {args.output}")


def load_annotations(staging: Path) -> dict[str, list[dict[str, Any]]]:
    merged: dict[str, list[dict[str, Any]]] = {}
    for path in sorted(staging.glob("*.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        case_map = value.get("cases") if isinstance(value, dict) and isinstance(value.get("cases"), dict) else value
        if not isinstance(case_map, dict):
            continue
        for case_id, entry in case_map.items():
            expected = entry.get("expected_hidden_risks") if isinstance(entry, dict) else entry
            if not isinstance(case_id, str) or not isinstance(expected, list):
                raise RuntimeError(f"Invalid annotation entry in {path}: {case_id!r}")
            if case_id in merged:
                raise RuntimeError(f"Duplicate annotation for {case_id}: {path}")
            merged[case_id] = expected
    return merged


def validate_expected(case_id: str, expected: list[dict[str, Any]], text: str) -> None:
    if not expected or len(expected) > 4:
        raise RuntimeError(f"{case_id} must contain 1-4 expected hidden risks.")
    seen_ids: set[str] = set()
    for item in expected:
        required = {"risk_id", "risk_domain", "sector_specific_topic", "hiddenness_type", "implicit_risk", "required_evidence_terms", "accepted_evidence_quotes", "review_status"}
        if not isinstance(item, dict) or required - set(item):
            raise RuntimeError(f"{case_id} has an incomplete expected hidden risk.")
        if item["risk_id"] in seen_ids or not str(item["risk_id"]).strip():
            raise RuntimeError(f"{case_id} has duplicate or empty risk_id.")
        seen_ids.add(item["risk_id"])
        if item["risk_domain"] not in DOMAINS or item["hiddenness_type"] not in HIDDENNESS:
            raise RuntimeError(f"{case_id} has an invalid taxonomy value.")
        if item["review_status"] != "candidate":
            raise RuntimeError(f"{case_id} must retain candidate review status.")
        quotes = item["accepted_evidence_quotes"]
        if not isinstance(quotes, list) or not quotes or any(not isinstance(quote, str) or quote not in text for quote in quotes):
            raise RuntimeError(f"{case_id} has a quote not found in Item 1A.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared", type=Path, default=DEFAULT_PREPARED)
    parser.add_argument("--staging", type=Path, default=DEFAULT_STAGING)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--allow-incomplete", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    main()
