from src.data_extraction.sec_filings import (
    FilingMetadata,
    filing_document_url,
    normalize_cik,
    submission_state_location,
)


def test_normalize_cik_zero_pads_numeric_value() -> None:
    assert normalize_cik("19617") == "0000019617"


def test_filing_document_url_uses_sec_archive_path() -> None:
    assert filing_document_url(
        "0000019617",
        "0001628280-26-008131",
        "jpm-20251231.htm",
    ) == (
        "https://www.sec.gov/Archives/edgar/data/"
        "19617/000162828026008131/jpm-20251231.htm"
    )


def test_filing_metadata_year_prefers_report_date() -> None:
    metadata = FilingMetadata(
        company="JPMORGAN CHASE & CO",
        ticker="JPM",
        cik="0000019617",
        form="10-K",
        filing_date="2026-02-13",
        report_date="2025-12-31",
        accession_number="0001628280-26-008131",
        primary_document="jpm-20251231.htm",
        document_url="https://www.sec.gov/example.htm",
    )

    assert metadata.year == 2025


def test_submission_state_location_reads_business_address() -> None:
    assert (
        submission_state_location(
            {
                "addresses": {
                    "business": {
                        "stateOrCountry": "NY",
                    }
                }
            }
        )
        == "NY"
    )
