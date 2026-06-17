from __future__ import annotations

import sys
import warnings
from contextlib import contextmanager
from importlib import import_module
from pathlib import Path
from typing import Any

import pandas as pd
from bs4 import XMLParsedAsHTMLWarning

from src.data_extraction.sec_filings import (
    FilingMetadata,
    SecFilingError,
    complete_text_filing_url,
    filing_index_url,
    normalize_cik,
)


DEFAULT_EDGAR_CACHE_DIR = Path("data") / "edgar_crawler_live"
EDGAR_CRAWLER_DIR = Path(__file__).resolve().parent / "edgar-crawler"


def extract_item_with_edgar_crawler(
    *,
    metadata: FilingMetadata,
    filing_html: str,
    item: str,
    cache_dir: Path | str = DEFAULT_EDGAR_CACHE_DIR,
) -> str:
    extracted = extract_filing_items_with_edgar_crawler(
        metadata=metadata,
        filing_html=filing_html,
        items_to_extract=[item],
        cache_dir=cache_dir,
    )
    item_key = edgar_crawler_item_key(item)
    item_text = extracted.get(item_key)
    if not isinstance(item_text, str) or not item_text.strip():
        raise SecFilingError(
            f"edgar-crawler did not extract Item {item} from {metadata.document_url}"
        )
    return item_text


def extract_filing_items_with_edgar_crawler(
    *,
    metadata: FilingMetadata,
    filing_html: str,
    items_to_extract: list[str],
    cache_dir: Path | str = DEFAULT_EDGAR_CACHE_DIR,
) -> dict[str, Any]:
    if metadata.form != "10-K":
        raise SecFilingError(f"edgar-crawler live adapter only supports 10-K, got {metadata.form}.")

    cache_path = Path(cache_dir)
    raw_filings_folder = cache_path / "RAW_FILINGS"
    filing_folder = raw_filings_folder / metadata.form
    filing_folder.mkdir(parents=True, exist_ok=True)

    filename = cached_filing_filename(metadata)
    filing_path = filing_folder / filename
    filing_path.write_text(filing_html, encoding="utf-8")

    ExtractItems = load_edgar_crawler_extract_items()
    extraction = ExtractItems(
        remove_tables=True,
        items_to_extract=items_to_extract,
        include_signature=False,
        raw_files_folder=str(raw_filings_folder),
        extracted_files_folder=str(cache_path / "EXTRACTED_FILINGS"),
        skip_extracted_filings=True,
    )

    filing_metadata = edgar_crawler_metadata_row(metadata, filename)
    extraction.determine_items_to_extract(filing_metadata)
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
        extracted = extraction.extract_items(filing_metadata)
    if not isinstance(extracted, dict):
        raise SecFilingError(f"edgar-crawler returned no extracted items for {metadata.document_url}")
    return extracted


def edgar_crawler_item_key(item: str) -> str:
    normalized = item.strip()
    if normalized.upper() == "SIGNATURE":
        return "SIGNATURE"
    return f"item_{normalized}"


def cached_filing_filename(metadata: FilingMetadata) -> str:
    suffix = Path(metadata.primary_document).suffix or ".htm"
    form = metadata.form.replace("-", "")
    accession = metadata.accession_number.replace("-", "")
    return f"{int(normalize_cik(metadata.cik))}_{form}_{metadata.year}_{accession}{suffix}"


def edgar_crawler_metadata_row(metadata: FilingMetadata, filename: str) -> pd.Series:
    return pd.Series(
        {
            "CIK": str(int(normalize_cik(metadata.cik))),
            "Company": metadata.company,
            "Type": metadata.form,
            "Date": metadata.filing_date,
            "complete_text_file_link": complete_text_filing_url(
                metadata.cik,
                metadata.accession_number,
            ),
            "html_index": filing_index_url(metadata.cik, metadata.accession_number),
            "Filing Date": metadata.filing_date,
            "Period of Report": metadata.report_date,
            "SIC": metadata.sic,
            "htm_file_link": metadata.document_url,
            "State of Inc": metadata.state_of_inc,
            "State location": metadata.state_location,
            "Fiscal Year End": metadata.fiscal_year_end,
            "filename": filename,
        }
    )


def load_edgar_crawler_extract_items() -> type[Any]:
    with edgar_crawler_import_path():
        return import_module("extract_items").ExtractItems


@contextmanager
def edgar_crawler_import_path():
    edgar_path = str(EDGAR_CRAWLER_DIR)
    inserted = edgar_path not in sys.path
    if inserted:
        sys.path.insert(0, edgar_path)
    try:
        yield
    finally:
        if inserted:
            sys.path.remove(edgar_path)
