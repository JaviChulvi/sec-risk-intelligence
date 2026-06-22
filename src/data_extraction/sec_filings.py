from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

import requests

from src.settings import load_dotenv


SEC_DATA_BASE_URL = "https://data.sec.gov"
SEC_WWW_BASE_URL = "https://www.sec.gov"
DEFAULT_SEC_USER_AGENT = "sec-risk-intelligence/0.1 research@example.com"
DEFAULT_TIMEOUT_SECONDS = 30


class SecFilingError(RuntimeError):
    """Raised when an SEC filing cannot be found, downloaded, or parsed."""


@dataclass(frozen=True)
class CompanyReference:
    cik: str
    ticker: str
    name: str


@dataclass(frozen=True)
class FilingMetadata:
    company: str
    ticker: str
    cik: str
    form: str
    filing_date: str
    report_date: str
    accession_number: str
    primary_document: str
    document_url: str
    sic: str = ""
    state_of_inc: str = ""
    state_location: str = ""
    fiscal_year_end: str = ""

    @property
    def year(self) -> int:
        source = self.report_date or self.filing_date
        return int(source[:4])


class SecCompanyClient:
    def __init__(
        self,
        *,
        user_agent: str | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self.user_agent = user_agent or sec_user_agent()
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "User-Agent": self.user_agent,
                "Accept-Encoding": "gzip, deflate",
            }
        )

    def company_reference(self, identifier: str) -> CompanyReference:
        cleaned = identifier.strip()
        if not cleaned:
            raise SecFilingError("Company identifier cannot be empty.")

        if cleaned.isdigit():
            cik = normalize_cik(cleaned)
            submissions = self.get_json(submissions_url(cik))
            tickers = submissions.get("tickers") or []
            return CompanyReference(
                cik=cik,
                ticker=str(tickers[0]) if tickers else cleaned,
                name=str(submissions.get("name") or cleaned),
            )

        ticker = cleaned.upper()
        companies = self.get_json(f"{SEC_WWW_BASE_URL}/files/company_tickers.json")
        for company in companies.values():
            if str(company.get("ticker", "")).upper() == ticker:
                return CompanyReference(
                    cik=normalize_cik(str(company["cik_str"])),
                    ticker=ticker,
                    name=str(company.get("title") or ticker),
                )
        raise SecFilingError(f"Could not find SEC company ticker {ticker!r}.")

    def filing_metadata(
        self,
        identifier: str,
        *,
        form: str | None = None,
        limit: int | None = None,
        report_years: set[int] | None = None,
    ) -> list[FilingMetadata]:
        company = self.company_reference(identifier)
        submissions = self.get_json(submissions_url(company.cik))
        company_name = str(submissions.get("name") or company.name)
        common = {
            "ticker": company.ticker,
            "cik": company.cik,
            "sic": str(submissions.get("sic") or ""),
            "state_of_inc": str(submissions.get("stateOfIncorporation") or ""),
            "state_location": submission_state_location(submissions),
            "fiscal_year_end": str(submissions.get("fiscalYearEnd") or ""),
        }

        filings_block = submissions.get("filings", {})
        matches = self._search_filings_block(
            filings_block.get("recent", {}),
            form=form,
            limit=limit,
            report_years=report_years,
            company_name=company_name,
            common=common,
        )
        if limit is not None and len(matches) >= limit:
            return matches

        # High-volume filers (e.g. JPM) exhaust `recent` within months.
        # Fetch additional pages only when needed and only those whose date
        # range overlaps with the target years.
        if report_years:
            extra_files = filings_block.get("files", [])
            for file_entry in extra_files:
                if limit is not None and len(matches) >= limit:
                    break
                if not _file_entry_overlaps(file_entry, report_years):
                    continue
                name = file_entry.get("name", "")
                if not name:
                    continue
                extra = self.get_json(f"{SEC_DATA_BASE_URL}/submissions/{name}")
                page_matches = self._search_filings_block(
                    extra,
                    form=form,
                    limit=limit - len(matches) if limit is not None else None,
                    report_years=report_years,
                    company_name=company_name,
                    common=common,
                )
                matches.extend(page_matches)

        return matches

    def _search_filings_block(
        self,
        recent: dict[str, Any],
        *,
        form: str | None,
        limit: int | None,
        report_years: set[int] | None,
        company_name: str,
        common: dict[str, str],
    ) -> list[FilingMetadata]:
        matches: list[FilingMetadata] = []
        for filing in iter_recent_filings(recent):
            if form and filing.get("form") != form:
                continue
            report_date = str(filing.get("reportDate") or "")
            filing_date = str(filing["filingDate"])
            year_source = report_date or filing_date
            if report_years:
                if not year_source[:4].isdigit() or int(year_source[:4]) not in report_years:
                    continue
            accession_number = str(filing["accessionNumber"])
            primary_document = str(filing["primaryDocument"])
            matches.append(
                FilingMetadata(
                    company=company_name,
                    form=str(filing["form"]),
                    filing_date=filing_date,
                    report_date=report_date,
                    accession_number=accession_number,
                    primary_document=primary_document,
                    document_url=filing_document_url(
                        common["cik"],
                        accession_number,
                        primary_document,
                    ),
                    **common,
                )
            )
            if limit is not None and len(matches) >= limit:
                break
        return matches

    def get_json(self, url: str) -> dict[str, Any]:
        response = self.session.get(url, timeout=DEFAULT_TIMEOUT_SECONDS)
        if not response.ok:
            raise SecFilingError(f"SEC request failed with HTTP {response.status_code}: {url}")
        try:
            data = response.json()
        except ValueError as exc:
            raise SecFilingError(f"SEC response was not JSON: {url}") from exc
        if not isinstance(data, dict):
            raise SecFilingError(f"SEC JSON response was not an object: {url}")
        return data

    def get_text(self, url: str) -> str:
        response = self.session.get(url, timeout=DEFAULT_TIMEOUT_SECONDS)
        if not response.ok:
            raise SecFilingError(f"SEC filing download failed with HTTP {response.status_code}: {url}")
        return response.text


def _file_entry_overlaps(file_entry: dict[str, Any], report_years: set[int]) -> bool:
    """Return True if a submissions `files` entry covers any of the target years.

    A 10-K for fiscal year Y is typically filed in Q1 of Y+1, so we widen the
    search window by one year on each side to avoid missing edge cases.
    """
    filing_from = str(file_entry.get("filingFrom") or "")
    filing_to = str(file_entry.get("filingTo") or "")
    if not filing_from or not filing_to:
        return True
    try:
        from_year = int(filing_from[:4])
        to_year = int(filing_to[:4])
    except ValueError:
        return True
    return any(from_year <= y + 1 and to_year >= y - 1 for y in report_years)


def sec_user_agent(env_path: str = ".env") -> str:
    load_dotenv(env_path)
    return os.environ.get("SEC_USER_AGENT", DEFAULT_SEC_USER_AGENT)


def normalize_cik(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if not digits:
        raise SecFilingError(f"Invalid CIK value {value!r}.")
    return digits.zfill(10)


def submissions_url(cik: str) -> str:
    return f"{SEC_DATA_BASE_URL}/submissions/CIK{normalize_cik(cik)}.json"


def filing_document_url(cik: str, accession_number: str, primary_document: str) -> str:
    accession_path = accession_number.replace("-", "")
    cik_path = str(int(normalize_cik(cik)))
    return (
        f"{SEC_WWW_BASE_URL}/Archives/edgar/data/"
        f"{cik_path}/{accession_path}/{primary_document}"
    )


def filing_index_url(cik: str, accession_number: str) -> str:
    accession_path = accession_number.replace("-", "")
    cik_path = str(int(normalize_cik(cik)))
    return (
        f"{SEC_WWW_BASE_URL}/Archives/edgar/data/"
        f"{cik_path}/{accession_path}/{accession_number}-index.html"
    )


def complete_text_filing_url(cik: str, accession_number: str) -> str:
    accession_path = accession_number.replace("-", "")
    cik_path = str(int(normalize_cik(cik)))
    return (
        f"{SEC_WWW_BASE_URL}/Archives/edgar/data/"
        f"{cik_path}/{accession_path}/{accession_number}.txt"
    )


def iter_recent_filings(recent: dict[str, list[Any]]) -> list[dict[str, Any]]:
    forms = recent.get("form") or []
    filings: list[dict[str, Any]] = []
    for index in range(len(forms)):
        filing = {}
        for key, values in recent.items():
            if isinstance(values, list) and index < len(values):
                filing[key] = values[index]
        filings.append(filing)
    return filings


def submission_state_location(submissions: dict[str, Any]) -> str:
    addresses = submissions.get("addresses")
    if not isinstance(addresses, dict):
        return ""
    business = addresses.get("business")
    if not isinstance(business, dict):
        return ""
    return str(business.get("stateOrCountry") or "")
