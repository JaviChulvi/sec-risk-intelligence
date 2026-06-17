from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from src.data_extraction.edgar_crawler_adapter import (
    DEFAULT_EDGAR_CACHE_DIR,
    extract_item_with_edgar_crawler,
)
from src.data_extraction.sec_filings import FilingMetadata, SecCompanyClient, SecFilingError


@dataclass(frozen=True)
class ExtractedFilingSection:
    metadata: FilingMetadata
    item: str
    section: str
    text: str
    extraction_source: str = "edgar_crawler"

    @property
    def word_count(self) -> int:
        return len(self.text.split())

    def to_eval_case(self, *, case_id_suffix: str = "risk-factor-listing") -> dict[str, Any]:
        ticker = self.metadata.ticker
        year = self.metadata.year
        form_slug = self.metadata.form.lower().replace("-", "")
        item_slug = self.item.lower().replace(".", "_")
        return {
            "id": f"{ticker.lower()}-{year}-{form_slug}-item-{item_slug}-{case_id_suffix}",
            "company": self.metadata.company,
            "ticker": ticker,
            "cik": self.metadata.cik.lstrip("0"),
            "year": year,
            "filing": {
                "filing_type": self.metadata.form,
                "filing_date": self.metadata.filing_date,
                "period_of_report": self.metadata.report_date,
                "accession_number": self.metadata.accession_number,
                "document_url": self.metadata.document_url,
            },
            "risk_factor_used": {
                "section": self.section,
                "source": self.extraction_source,
                "word_count": self.word_count,
            },
            "input": {
                "section": self.section,
                "text": self.text,
            },
        }


def extract_company_filing_sections(
    identifier: str,
    *,
    form: str,
    item: str,
    section: str | None = None,
    limit: int | None = None,
    report_years: set[int] | None = None,
    user_agent: str | None = None,
    session: requests.Session | None = None,
    cache_dir: Path | str = DEFAULT_EDGAR_CACHE_DIR,
) -> list[ExtractedFilingSection]:
    client = SecCompanyClient(user_agent=user_agent, session=session)
    filings = client.filing_metadata(
        identifier,
        form=form,
        limit=limit,
        report_years=report_years,
    )
    return [
        extract_filing_section(
            client=client,
            metadata=metadata,
            item=item,
            section=section,
            cache_dir=cache_dir,
        )
        for metadata in filings
    ]


def extract_filing_section(
    *,
    client: SecCompanyClient,
    metadata: FilingMetadata,
    item: str,
    section: str | None = None,
    cache_dir: Path | str = DEFAULT_EDGAR_CACHE_DIR,
) -> ExtractedFilingSection:
    html = client.get_text(metadata.document_url)
    item_text = extract_item_with_edgar_crawler(
        metadata=metadata,
        filing_html=html,
        item=item,
        cache_dir=cache_dir,
    )
    return ExtractedFilingSection(
        metadata=metadata,
        item=item,
        section=section or f"Item {item}",
        text=item_text,
    )


def fetch_latest_10k_risk_factors(
    identifier: str,
    *,
    user_agent: str | None = None,
    session: requests.Session | None = None,
    cache_dir: Path | str = DEFAULT_EDGAR_CACHE_DIR,
) -> ExtractedFilingSection:
    sections = fetch_company_10k_risk_factors(
        identifier,
        limit=1,
        user_agent=user_agent,
        session=session,
        cache_dir=cache_dir,
    )
    if not sections:
        raise SecFilingError(f"No recent 10-K filing found for {identifier!r}.")
    return sections[0]


def fetch_company_10k_risk_factors(
    identifier: str,
    *,
    limit: int | None = None,
    report_years: set[int] | None = None,
    user_agent: str | None = None,
    session: requests.Session | None = None,
    cache_dir: Path | str = DEFAULT_EDGAR_CACHE_DIR,
) -> list[ExtractedFilingSection]:
    return extract_company_filing_sections(
        identifier,
        form="10-K",
        item="1A",
        section="Item 1A. Risk Factors",
        limit=limit,
        report_years=report_years,
        user_agent=user_agent,
        session=session,
        cache_dir=cache_dir,
    )
