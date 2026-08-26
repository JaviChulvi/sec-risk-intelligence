#!/usr/bin/env python3
"""Build self-contained annual Item 1A eval cases from the downloaded SaaS 10-Ks.

This prepares the source cases only. Human/agent-reviewed hidden-risk candidates
are merged separately, so Item 1A extraction remains reproducible and annotations
remain auditable.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from src.data_extraction.sec_filings import FilingMetadata
from bs4 import BeautifulSoup


DEFAULT_DATASET = Path("data") / "saas_50_latest_10_10ks"
DEFAULT_OUTPUT = DEFAULT_DATASET / "saas_50_hidden_risk_annual.prepared.json"

COHORT_METADATA = {
    "application": ("software", "horizontal application software", "subscription and enterprise software"),
    "vertical": ("software", "vertical application software", "industry-specific software and services"),
    "finance_hr": ("software", "financial and human-capital software", "recurring software, payroll, and financial services"),
    "security_data": ("technology", "cybersecurity and data infrastructure", "security, networking, and data-management products and services"),
    "cloud_platform": ("technology", "cloud and infrastructure platform", "cloud, communications, infrastructure, and platform services"),
}


def main() -> None:
    args = parse_args()
    dataset_dir = args.dataset_dir.resolve()
    manifest = json.loads((dataset_dir / "manifest.json").read_text(encoding="utf-8"))
    records = manifest.get("records")
    if not isinstance(records, list):
        raise RuntimeError("manifest.json must contain records.")

    selected_cohorts = set(args.cohort or COHORT_METADATA)
    unknown = selected_cohorts - COHORT_METADATA.keys()
    if unknown:
        raise ValueError(f"Unknown cohort(s): {sorted(unknown)}")

    partial_path = args.output.with_suffix(".cases.jsonl")
    prepared = load_partial_cases(partial_path)
    forced_accessions = set(args.force_accession)
    cases: list[dict[str, Any]] = []
    for number, record in enumerate(records, start=1):
        cohort = str(record["cohort"])
        if cohort not in selected_cohorts:
            continue
        metadata = FilingMetadata(
            company=str(record["company"]),
            ticker=str(record["ticker"]),
            cik=str(record["cik"]),
            form=str(record["form"]),
            filing_date=str(record["filing_date"]),
            report_date=str(record["report_date"]),
            accession_number=str(record["accession_number"]),
            primary_document=str(record["primary_document"]),
            document_url=str(record["document_url"]),
        )
        raw_path = dataset_dir / str(record["file_path"])
        case_id = case_id_for(metadata)
        existing = prepared.get(case_id)
        if existing is not None and metadata.accession_number not in forced_accessions:
            cases.append(existing)
            continue
        item_1a = extract_item_1a(raw_path.read_text(encoding="utf-8", errors="replace"))
        sector, industry, business_model = COHORT_METADATA[cohort]
        case = {
                "id": case_id,
                "company": metadata.company,
                "ticker": metadata.ticker,
                "cik": metadata.cik,
                "cohort": cohort,
                "sector": sector,
                "industry": industry,
                "business_model": business_model,
                "year": metadata.year,
                "filing": {
                    "filing_type": metadata.form,
                    "filing_date": metadata.filing_date,
                    "period_of_report": metadata.report_date,
                    "accession_number": metadata.accession_number,
                },
                "risk_factor_used": {
                    "section": "Item 1A. Risk Factors",
                    "source": "downloaded_sec_10k",
                    "word_count": len(item_1a.split()),
                },
                "input": {"section": "Item 1A. Risk Factors", "text": item_1a},
        }
        cases.append(case)
        append_jsonl(partial_path, case)
        print(f"Prepared {number}/{len(records)}: {metadata.ticker} {metadata.year}", flush=True)

    payload = {
        "eval_name": "saas_50_annual_hidden_risk_benchmark",
        "version": 1,
        "description": "Self-contained annual Item 1A cases for the 50-company SaaS and cloud 10-K corpus.",
        "task_contract": {
            "input": "The model receives one year of one company 10-K Item 1A Risk Factors.",
            "expected_behavior": "Return evidence-backed implicit or underemphasized risks.",
            "scoring_mode": "benchmark_when_expected_hidden_risks_present",
            "excluded_from_prompt": [
                "Prior-year filing text",
                "Future-year filing text",
                "MD&A or other non-Item 1A sections",
                "External market knowledge as evidence",
            ],
        },
        "cases": cases,
    }
    args.output.resolve().write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(cases)} prepared cases to {args.output.resolve()}")


def case_id_for(metadata: FilingMetadata) -> str:
    accession = metadata.accession_number.replace("-", "")
    return f"{metadata.ticker.lower()}-{metadata.year}-10k-item-1a-hidden-risk-discovery-{accession}"


def extract_item_1a(filing_html: str) -> str:
    """Return the longest Item 1A-to-1B span, avoiding table-of-contents copies."""
    text = BeautifulSoup(filing_html, "html.parser").get_text("\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text).strip()
    text = re.sub(r"\bIt\s+em\b", "Item", text, flags=re.I)
    starts = [
        match
        for match in re.finditer(r"\bitem\s*1a\.?\s*(?:\W|\s)*r(?:i\s*sk|is\s*k)\s+factors\b", text, flags=re.I)
        if not text[text.rfind("\n", 0, match.start()) + 1 : match.start()].strip()
    ]
    ends = list(re.finditer(r"\bitem\s*1b\.?\b", text, flags=re.I))
    spans = [
        text[start.start() : end.start()].strip()
        for start in starts
        if (end := next((end for end in ends if end.start() > start.end()), None)) is not None
    ]
    spans = [span for span in spans if len(span.split()) >= 100]
    if not spans:
        fallback_starts = list(re.finditer(r"\brisks\s+related\s+to\b", text, flags=re.I))
        fallback_ends = list(
            re.finditer(r"\b(?:item\s*1b\.?|unresolved\s+staff\s+comments)\b", text, flags=re.I)
        )
        spans = [
            text[start.start() : next((end.start() for end in fallback_ends if end.start() > start.end()), len(text))].strip()
            for start in fallback_starts
        ]
        spans = [span for span in spans if len(span.split()) >= 100]
    if not spans:
        raise RuntimeError("Could not locate a substantive Item 1A section.")
    return max(spans, key=len)


def load_partial_cases(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    cases: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        case = json.loads(line)
        if isinstance(case, dict) and isinstance(case.get("id"), str):
            cases[case["id"]] = case
    return cases


def append_jsonl(path: Path, case: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(case, ensure_ascii=False) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--cohort", action="append", choices=sorted(COHORT_METADATA))
    parser.add_argument("--force-accession", action="append", default=[])
    return parser.parse_args()


if __name__ == "__main__":
    main()
