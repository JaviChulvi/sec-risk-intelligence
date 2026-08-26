#!/usr/bin/env python3
"""Download the ten latest SEC 10-Ks for a reproducible 50-company SaaS study.

The command selects exactly ten domestic 10-K filings per issuer from SEC
submissions metadata before downloading documents. It is resumable: every
successful file is recorded with its SHA-256 hash in a partial manifest.

Run with a real SEC contact identity, for example:
    set -a; source /path/to/.env; set +a
    python notebooks/ingest_saas_10k.py
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import requests

from src.data_extraction.sec_filings import (
    SEC_DATA_BASE_URL,
    SEC_WWW_BASE_URL,
    FilingMetadata,
    SecCompanyClient,
    SecFilingError,
    filing_document_url,
    iter_recent_filings,
    normalize_cik,
    submissions_url,
)


FILINGS_PER_COMPANY = 10
TARGETS_BY_COHORT = {
    "application": 11,
    "vertical": 8,
    "finance_hr": 10,
    "security_data": 10,
    "cloud_platform": 11,
}
MIN_REQUEST_INTERVAL_SECONDS = 0.20


@dataclass(frozen=True)
class Candidate:
    ticker: str
    cohort: str


# This deliberately includes a few more candidates than needed in every cohort.
# The SEC metadata, not an assumed IPO date, decides whether an issuer is eligible.
CANDIDATES = (
    Candidate("ADBE", "application"),
    Candidate("ADSK", "application"),
    Candidate("APPN", "application"),
    Candidate("BOX", "application"),
    Candidate("CRM", "application"),
    Candidate("HUBS", "application"),
    Candidate("MANH", "application"),
    Candidate("NOW", "application"),
    Candidate("ORCL", "application"),
    Candidate("PTC", "application"),
    Candidate("WDAY", "application"),
    Candidate("WK", "application"),
    Candidate("APPF", "vertical"),
    Candidate("BLKB", "vertical"),
    Candidate("GWRE", "vertical"),
    Candidate("TYL", "vertical"),
    Candidate("VEEV", "vertical"),
    Candidate("SPSC", "vertical"),
    Candidate("PRO", "vertical"),
    Candidate("ALRM", "vertical"),
    Candidate("EVBG", "vertical"),
    Candidate("BL", "vertical"),
    Candidate("ADP", "finance_hr"),
    Candidate("FICO", "finance_hr"),
    Candidate("FI", "finance_hr"),
    Candidate("FIS", "finance_hr"),
    Candidate("INTU", "finance_hr"),
    Candidate("PAYC", "finance_hr"),
    Candidate("PAYX", "finance_hr"),
    Candidate("PCTY", "finance_hr"),
    Candidate("QTWO", "finance_hr"),
    Candidate("SSNC", "finance_hr"),
    Candidate("JKHY", "finance_hr"),
    Candidate("AKAM", "security_data"),
    Candidate("CVLT", "security_data"),
    Candidate("FFIV", "security_data"),
    Candidate("FTNT", "security_data"),
    Candidate("PANW", "security_data"),
    Candidate("QLYS", "security_data"),
    Candidate("RPD", "security_data"),
    Candidate("VRNS", "security_data"),
    Candidate("CSCO", "security_data"),
    Candidate("IBM", "security_data"),
    Candidate("AMZN", "cloud_platform"),
    Candidate("ANET", "cloud_platform"),
    Candidate("CDNS", "cloud_platform"),
    Candidate("FIVN", "cloud_platform"),
    Candidate("GDDY", "cloud_platform"),
    Candidate("MSFT", "cloud_platform"),
    Candidate("NTAP", "cloud_platform"),
    Candidate("RNG", "cloud_platform"),
    Candidate("ROP", "cloud_platform"),
    Candidate("SNPS", "cloud_platform"),
    Candidate("TWLO", "cloud_platform"),
)


class RateLimitedSession(requests.Session):
    """Keep all SEC calls below the documented ten-requests-per-second limit."""

    def __init__(self, min_interval_seconds: float = MIN_REQUEST_INTERVAL_SECONDS) -> None:
        super().__init__()
        self.min_interval_seconds = min_interval_seconds
        self._last_request_at = 0.0

    def get(self, url: str, **kwargs: Any) -> requests.Response:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.min_interval_seconds:
            time.sleep(self.min_interval_seconds - elapsed)
        response = super().get(url, **kwargs)
        self._last_request_at = time.monotonic()
        return response


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    client = SecCompanyClient(session=RateLimitedSession())
    selection_path = output_dir / "selection.json"
    if selection_path.exists():
        selected = load_selection(selection_path)
        print(f"Reusing the existing selection of {len(selected)} companies.")
    else:
        selected, exclusions = select_companies(client)
        if len(selected) != sum(TARGETS_BY_COHORT.values()):
            raise RuntimeError(
                f"Only selected {len(selected)} companies; expected {sum(TARGETS_BY_COHORT.values())}."
            )
        write_json(
            selection_path,
            {
                "selection_rule": "Ten latest domestic 10-K filings per issuer from SEC submissions metadata.",
                "filings_per_company": FILINGS_PER_COMPANY,
                "targets_by_cohort": TARGETS_BY_COHORT,
                "selected": selected,
                "excluded_candidates": exclusions,
            },
        )
        print(f"Selected {len(selected)} companies from SEC metadata.")

    if args.selection_only:
        verify_selection(selected)
        print(f"Selection verified at {selection_path}")
        return

    records = download_selected_filings(client, selected, output_dir)
    verify_records(selected, records, output_dir)
    write_manifests(selected, records, output_dir)
    print(f"Verified {len(records)} downloaded 10-Ks for {len(selected)} companies at {output_dir}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data") / "saas_50_latest_10_10ks",
        help="Destination for the raw filings and manifests.",
    )
    parser.add_argument(
        "--selection-only",
        action="store_true",
        help="Validate and persist the 50-company cohort without downloading filings.",
    )
    return parser.parse_args()


def select_companies(client: SecCompanyClient) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ticker_lookup = load_ticker_lookup(client)
    selected: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []

    for cohort, target in TARGETS_BY_COHORT.items():
        cohort_candidates = [candidate for candidate in CANDIDATES if candidate.cohort == cohort]
        cohort_selected = 0
        for candidate in cohort_candidates:
            try:
                resolved = ticker_lookup[candidate.ticker]
            except KeyError:
                exclusions.append(
                    {"ticker": candidate.ticker, "cohort": cohort, "reason": "ticker_not_in_sec_company_tickers"}
                )
                continue

            try:
                filings = latest_ten_10ks(client, resolved["cik"], candidate.ticker, resolved["company"])
            except SecFilingError as exc:
                exclusions.append(
                    {"ticker": candidate.ticker, "cohort": cohort, "reason": str(exc)}
                )
                continue
            if len(filings) != FILINGS_PER_COMPANY:
                exclusions.append(
                    {
                        "ticker": candidate.ticker,
                        "cohort": cohort,
                        "reason": f"only_{len(filings)}_available_10_k_filings",
                    }
                )
                continue

            selected.append(
                {
                    "ticker": candidate.ticker,
                    "company": filings[0].company,
                    "cik": filings[0].cik,
                    "cohort": cohort,
                    "filings": [filing_to_dict(filing) for filing in filings],
                }
            )
            cohort_selected += 1
            if cohort_selected == target:
                break

        if cohort_selected != target:
            raise RuntimeError(f"Cohort {cohort!r} only yielded {cohort_selected}/{target} eligible issuers.")

    return selected, exclusions


def load_ticker_lookup(client: SecCompanyClient) -> dict[str, dict[str, str]]:
    companies = client.get_json(f"{SEC_WWW_BASE_URL}/files/company_tickers.json")
    lookup: dict[str, dict[str, str]] = {}
    for item in companies.values():
        ticker = str(item.get("ticker") or "").upper()
        cik = str(item.get("cik_str") or "")
        if ticker and cik:
            lookup[ticker] = {
                "cik": normalize_cik(cik),
                "company": str(item.get("title") or ticker),
            }
    return lookup


def latest_ten_10ks(
    client: SecCompanyClient,
    cik: str,
    ticker: str,
    fallback_company: str,
) -> list[FilingMetadata]:
    submissions = client.get_json(submissions_url(cik))
    company_name = str(submissions.get("name") or fallback_company)
    common = {
        "ticker": ticker,
        "cik": normalize_cik(cik),
        "sic": str(submissions.get("sic") or ""),
        "state_of_inc": str(submissions.get("stateOfIncorporation") or ""),
        "state_location": "",
        "fiscal_year_end": str(submissions.get("fiscalYearEnd") or ""),
    }
    filing_blocks = [submissions.get("filings", {}).get("recent", {})]
    for entry in submissions.get("filings", {}).get("files", []):
        name = str(entry.get("name") or "")
        if name:
            filing_blocks.append(client.get_json(f"{SEC_DATA_BASE_URL}/submissions/{name}"))

    filings: dict[str, FilingMetadata] = {}
    for block in filing_blocks:
        for filing in iter_recent_filings(block):
            if filing.get("form") != "10-K":
                continue
            accession_number = str(filing.get("accessionNumber") or "")
            primary_document = str(filing.get("primaryDocument") or "")
            filing_date = str(filing.get("filingDate") or "")
            if not accession_number or not primary_document or not filing_date:
                continue
            filings[accession_number] = FilingMetadata(
                company=company_name,
                form="10-K",
                filing_date=filing_date,
                report_date=str(filing.get("reportDate") or ""),
                accession_number=accession_number,
                primary_document=primary_document,
                document_url=filing_document_url(cik, accession_number, primary_document),
                **common,
            )

    return sorted(
        filings.values(),
        key=lambda filing: (filing.report_date or filing.filing_date, filing.filing_date, filing.accession_number),
        reverse=True,
    )[:FILINGS_PER_COMPANY]


def download_selected_filings(
    client: SecCompanyClient,
    selected: list[dict[str, Any]],
    output_dir: Path,
) -> list[dict[str, Any]]:
    partial_path = output_dir / "manifest.partial.jsonl"
    records_by_accession = load_partial_records(partial_path)
    raw_dir = output_dir / "RAW_FILINGS" / "10-K"
    raw_dir.mkdir(parents=True, exist_ok=True)

    total = len(selected) * FILINGS_PER_COMPANY
    completed = 0
    for company in selected:
        for filing_data in company["filings"]:
            filing = filing_from_dict(filing_data)
            existing = records_by_accession.get(filing.accession_number)
            if existing and verify_existing_record(existing, output_dir):
                completed += 1
                continue

            response = client._get(filing.document_url)
            content = response.content
            if not content:
                raise SecFilingError(f"SEC returned an empty filing for {filing.document_url}")
            relative_path = raw_relative_path(filing)
            destination = output_dir / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
            record = {
                "ticker": filing.ticker,
                "company": filing.company,
                "cik": filing.cik,
                "cohort": company["cohort"],
                "form": filing.form,
                "filing_date": filing.filing_date,
                "report_date": filing.report_date,
                "year": filing.year,
                "accession_number": filing.accession_number,
                "primary_document": filing.primary_document,
                "document_url": filing.document_url,
                "file_path": str(relative_path),
                "bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
            append_jsonl(partial_path, record)
            records_by_accession[filing.accession_number] = record
            completed += 1
            if completed % 10 == 0 or completed == total:
                print(f"Downloaded or reused {completed}/{total} filings.")

    return [
        records_by_accession[filing["accession_number"]]
        for company in selected
        for filing in company["filings"]
    ]


def verify_selection(selected: list[dict[str, Any]]) -> None:
    if len(selected) != sum(TARGETS_BY_COHORT.values()):
        raise RuntimeError(f"Expected 50 selected companies, found {len(selected)}.")
    seen_tickers: set[str] = set()
    seen_accessions: set[str] = set()
    counts_by_cohort = {cohort: 0 for cohort in TARGETS_BY_COHORT}
    for company in selected:
        ticker = str(company["ticker"])
        if ticker in seen_tickers:
            raise RuntimeError(f"Duplicate ticker in selection: {ticker}")
        seen_tickers.add(ticker)
        cohort = str(company["cohort"])
        counts_by_cohort[cohort] += 1
        filings = company["filings"]
        if len(filings) != FILINGS_PER_COMPANY:
            raise RuntimeError(f"{ticker} has {len(filings)} selected filings, expected {FILINGS_PER_COMPANY}.")
        for filing in filings:
            if filing["form"] != "10-K":
                raise RuntimeError(f"{ticker} includes non-10-K form {filing['form']}.")
            accession = filing["accession_number"]
            if accession in seen_accessions:
                raise RuntimeError(f"Duplicate accession in selection: {accession}")
            seen_accessions.add(accession)
    if counts_by_cohort != TARGETS_BY_COHORT:
        raise RuntimeError(f"Unexpected cohort counts: {counts_by_cohort}")


def verify_records(selected: list[dict[str, Any]], records: list[dict[str, Any]], output_dir: Path) -> None:
    verify_selection(selected)
    if len(records) != len(selected) * FILINGS_PER_COMPANY:
        raise RuntimeError(f"Expected 500 manifest records, found {len(records)}.")
    selected_accessions = {
        filing["accession_number"]
        for company in selected
        for filing in company["filings"]
    }
    record_accessions = {record["accession_number"] for record in records}
    if record_accessions != selected_accessions:
        raise RuntimeError("Manifest accessions do not exactly match the selected 10-Ks.")
    for record in records:
        path = output_dir / record["file_path"]
        content = path.read_bytes()
        if not content:
            raise RuntimeError(f"Empty downloaded filing: {path}")
        if len(content) != record["bytes"]:
            raise RuntimeError(f"Byte count mismatch: {path}")
        if hashlib.sha256(content).hexdigest() != record["sha256"]:
            raise RuntimeError(f"Checksum mismatch: {path}")


def write_manifests(selected: list[dict[str, Any]], records: list[dict[str, Any]], output_dir: Path) -> None:
    records = sorted(records, key=lambda record: (record["ticker"], record["report_date"], record["filing_date"]), reverse=False)
    write_json(output_dir / "manifest.json", {"records": records})
    with (output_dir / "manifest.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    write_json(
        output_dir / "summary.json",
        {
            "companies": len(selected),
            "filings_per_company": FILINGS_PER_COMPANY,
            "filings": len(records),
            "cohorts": TARGETS_BY_COHORT,
            "verified": True,
        },
    )


def load_selection(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    selected = payload.get("selected")
    if not isinstance(selected, list):
        raise RuntimeError(f"Selection file has no selected companies: {path}")
    verify_selection(selected)
    return selected


def filing_to_dict(filing: FilingMetadata) -> dict[str, Any]:
    return asdict(filing)


def filing_from_dict(value: dict[str, Any]) -> FilingMetadata:
    return FilingMetadata(**value)


def raw_relative_path(filing: FilingMetadata) -> Path:
    suffix = Path(filing.primary_document).suffix or ".htm"
    accession = filing.accession_number.replace("-", "")
    return Path("RAW_FILINGS") / "10-K" / f"{int(filing.cik)}_10K_{filing.year}_{accession}{suffix}"


def load_partial_records(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    records: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if isinstance(record, dict) and record.get("accession_number"):
            records[str(record["accession_number"])] = record
    return records


def verify_existing_record(record: dict[str, Any], output_dir: Path) -> bool:
    try:
        content = (output_dir / record["file_path"]).read_bytes()
    except OSError:
        return False
    return (
        bool(content)
        and len(content) == record.get("bytes")
        and hashlib.sha256(content).hexdigest() == record.get("sha256")
    )


def append_jsonl(path: Path, value: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, sort_keys=True) + "\n")


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
