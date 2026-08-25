from unittest.mock import Mock, call, patch

import pytest
import requests

from src.data_extraction.sec_filings import (
    FilingMetadata,
    SecCompanyClient,
    SecFilingError,
    filing_document_url,
    normalize_cik,
    sec_user_agent,
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


@pytest.mark.parametrize(
    "user_agent",
    [
        "",
        "sec-risk-intelligence/0.1 research@example.com",
        "sec-risk-intelligence/0.1",
        "research@company.org",
    ],
)
def test_sec_company_client_rejects_missing_or_placeholder_contact(
    user_agent,
) -> None:
    with pytest.raises(SecFilingError, match="real contact email"):
        SecCompanyClient(user_agent=user_agent, session=mock_session())


def test_sec_user_agent_rejects_missing_environment_value(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)

    with pytest.raises(SecFilingError, match="SEC_USER_AGENT"):
        sec_user_agent(str(tmp_path / "missing.env"))


def test_get_json_retries_rate_limit_using_retry_after() -> None:
    retry_response = mock_response(status_code=429, headers={"Retry-After": "0"})
    success_response = mock_response(json_data={"ok": True})
    session = mock_session(retry_response, success_response)
    client = SecCompanyClient(
        user_agent="Risk Intelligence research@company.org",
        session=session,
    )

    with patch("src.data_extraction.sec_filings.time.sleep") as sleep:
        result = client.get_json("https://data.sec.gov/example.json")

    assert result == {"ok": True}
    assert session.get.call_count == 2
    sleep.assert_called_once_with(0.0)


def test_get_text_retries_transport_error_with_exponential_backoff() -> None:
    success_response = mock_response(text="filing")
    session = mock_session(requests.ConnectionError("connection reset"), success_response)
    client = SecCompanyClient(
        user_agent="Risk Intelligence research@company.org",
        session=session,
    )

    with patch("src.data_extraction.sec_filings.time.sleep") as sleep:
        result = client.get_text("https://www.sec.gov/example.htm")

    assert result == "filing"
    sleep.assert_called_once_with(1.0)


def test_sec_request_stops_after_retry_limit() -> None:
    session = mock_session(
        requests.Timeout("first timeout"),
        requests.Timeout("second timeout"),
        requests.Timeout("third timeout"),
    )
    client = SecCompanyClient(
        user_agent="Risk Intelligence research@company.org",
        session=session,
    )

    with (
        patch("src.data_extraction.sec_filings.time.sleep") as sleep,
        pytest.raises(SecFilingError, match="failed after 3 attempts"),
    ):
        client.get_json("https://data.sec.gov/example.json")

    assert sleep.call_args_list == [call(1.0), call(2.0)]


def test_sec_request_does_not_retry_permanent_http_error() -> None:
    session = mock_session(mock_response(status_code=403))
    client = SecCompanyClient(
        user_agent="Risk Intelligence research@company.org",
        session=session,
    )

    with (
        patch("src.data_extraction.sec_filings.time.sleep") as sleep,
        pytest.raises(SecFilingError, match="HTTP 403"),
    ):
        client.get_json("https://data.sec.gov/example.json")

    assert session.get.call_count == 1
    sleep.assert_not_called()


def mock_session(*responses) -> Mock:
    session = Mock(spec=requests.Session)
    session.headers = {}
    session.get.side_effect = responses
    return session


def mock_response(
    *,
    status_code: int = 200,
    headers: dict[str, str] | None = None,
    json_data=None,
    text: str = "",
) -> Mock:
    response = Mock(spec=requests.Response)
    response.status_code = status_code
    response.ok = status_code < 400
    response.headers = headers or {}
    response.json.return_value = json_data
    response.text = text
    return response
