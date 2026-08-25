from unittest.mock import patch

from src.data_extraction.edgar_crawler_adapter import (
    cached_filing_filename,
    edgar_crawler_metadata_row,
    extract_item_with_edgar_crawler,
)
from src.data_extraction.company_filings import ExtractedFilingSection
from src.data_extraction.sec_filings import FilingMetadata


def test_extract_item_with_edgar_crawler_persists_reuses_and_repairs_cache(
    tmp_path,
) -> None:
    metadata = filing_metadata()
    html = filing_html("Cached risk heading.")
    expected = extract_item_with_edgar_crawler(
        metadata=metadata,
        filing_html=html,
        item="1A",
        cache_dir=tmp_path,
    )
    extracted_path = (
        tmp_path
        / "EXTRACTED_FILINGS"
        / "10-K"
        / f"{cached_filing_filename(metadata).removesuffix('.htm')}.json"
    )

    assert expected.startswith("Item 1A. Risk Factors")
    assert "Cached risk heading" in expected
    assert "Item 1B" not in expected
    assert (tmp_path / "RAW_FILINGS" / "10-K" / cached_filing_filename(metadata)).exists()
    assert extracted_path.exists()

    with patch(
        "src.data_extraction.edgar_crawler_adapter.load_edgar_crawler_extract_items",
        side_effect=AssertionError("crawler should not run on a cache hit"),
    ):
        actual = extract_item_with_edgar_crawler(
            metadata=metadata,
            filing_html=html,
            item="1A",
            cache_dir=tmp_path,
        )

    assert actual == expected

    extracted_path.write_text("{invalid", encoding="utf-8")

    repaired = extract_item_with_edgar_crawler(
        metadata=metadata,
        filing_html=html,
        item="1A",
        cache_dir=tmp_path,
    )

    assert repaired == expected


def test_extract_item_with_edgar_crawler_rebuilds_cache_when_html_changes(tmp_path) -> None:
    metadata = filing_metadata()
    extract_item_with_edgar_crawler(
        metadata=metadata,
        filing_html=filing_html("Old risk heading."),
        item="1A",
        cache_dir=tmp_path,
    )

    section = extract_item_with_edgar_crawler(
        metadata=metadata,
        filing_html=filing_html("Updated risk heading."),
        item="1A",
        cache_dir=tmp_path,
    )

    assert "Updated risk heading" in section
    assert "Old risk heading" not in section


def test_edgar_crawler_metadata_row_matches_expected_columns() -> None:
    metadata = filing_metadata()

    row = edgar_crawler_metadata_row(metadata, "cached.htm")

    assert row["CIK"] == "19617"
    assert row["Type"] == "10-K"
    assert row["filename"] == "cached.htm"
    assert row["htm_file_link"] == "https://www.sec.gov/example.htm"
    assert row["complete_text_file_link"].endswith("0001628280-26-008131.txt")


def test_extracted_filing_section_can_be_shaped_like_eval_case() -> None:
    section = ExtractedFilingSection(
        metadata=filing_metadata(),
        item="1A",
        section="Item 1A. Risk Factors",
        text="Item 1A. Risk Factors\nA risk heading.",
    )

    eval_case = section.to_eval_case()

    assert eval_case["company"] == "JPMORGAN CHASE & CO"
    assert eval_case["ticker"] == "JPM"
    assert eval_case["year"] == 2025
    assert eval_case["input"]["text"].startswith("Item 1A")
    assert eval_case["id"] == "jpm-2025-10k-item-1a-risk-factor-listing"
    assert eval_case["risk_factor_used"]["source"] == "edgar_crawler"


def filing_metadata() -> FilingMetadata:
    return FilingMetadata(
        company="JPMORGAN CHASE & CO",
        ticker="JPM",
        cik="0000019617",
        form="10-K",
        filing_date="2026-02-13",
        report_date="2025-12-31",
        accession_number="0001628280-26-008131",
        primary_document="jpm-20251231.htm",
        document_url="https://www.sec.gov/example.htm",
        sic="6021",
        state_of_inc="DE",
        state_location="NY",
        fiscal_year_end="1231",
    )


def filing_html(risk_heading: str) -> str:
    return f"""
    <html>
      <body>
        <h1>Item 1. Business</h1>
        <p>Business description.</p>
        <h1>Item 1A. Risk Factors</h1>
        <p>{risk_heading} This is the real edgar-crawler extracted section.</p>
        <p>Risk heading two. This keeps the section comfortably long.</p>
        <h1>Item 1B. Unresolved Staff Comments</h1>
        <p>Next section.</p>
      </body>
    </html>
    """
