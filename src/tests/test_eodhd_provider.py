import copy
import json
import os
from datetime import date
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests

from src.news.eodhd_config import EodhdPilotConfig
from src.news.eodhd_pilot import EodhdPilot
from src.news.providers import AuthenticationError, EodhdProvider, NewsProvider, ProviderResponseError
from src.news.schemas import PageRequest, ProviderPage
from src.tests.news_helpers import query_window


CONFIG = Path(__file__).resolve().parents[2] / "config" / "eodhd_pilot.json"
FIXTURE = Path(__file__).parent / "fixtures" / "eodhd" / "page.json"


def response(status, payload):
    result = Mock()
    result.status_code = status
    result.content = json.dumps(payload).encode()
    result.json.return_value = payload
    return result


def provider(session, sleeper=lambda _: None):
    return EodhdProvider(
        endpoint="https://example.test/news",
        api_token="top-secret-token",
        timeout_seconds=1,
        max_attempts=3,
        backoff_base_seconds=0.1,
        backoff_max_seconds=1,
        jitter_seconds=0,
        session=session,
        sleeper=sleeper,
    )


def test_retries_429_and_5xx_then_returns_page():
    session = Mock()
    session.get.side_effect = [response(429, {}), response(503, {}), response(200, json.loads(FIXTURE.read_text()))]
    sleeps = []
    page = provider(session, sleeps.append).fetch_page(PageRequest(query_window(), 1000, 0))
    assert len(page.articles) == 1
    assert page.attempts == 3
    assert sleeps == [0.1, 0.2]


def test_authentication_stops_without_retry_or_secret_in_error():
    session = Mock()
    session.get.return_value = response(401, {"message": "invalid top-secret-token"})
    with pytest.raises(AuthenticationError) as error:
        provider(session).fetch_page(PageRequest(query_window(), 1000, 0))
    assert session.get.call_count == 1
    assert "top-secret-token" not in str(error.value)


def test_network_exception_is_sanitized():
    session = Mock()
    session.get.side_effect = requests.RequestException("https://example.test?api_token=top-secret-token")
    with pytest.raises(Exception) as error:
        provider(session).fetch_page(PageRequest(query_window(), 1000, 0))
    assert "top-secret-token" not in str(error.value)


def test_unexpected_success_payload_is_rejected_and_sanitized():
    session = Mock()
    session.get.return_value = response(200, {"api_token": "top-secret-token", "message": "changed schema"})
    with pytest.raises(ProviderResponseError) as error:
        provider(session).fetch_page(PageRequest(query_window(), 1000, 0))
    assert error.value.sanitized_payload["api_token"] == "[REDACTED]"


class SyntheticProvider(NewsProvider):
    def __init__(self, behaviour):
        self.behaviour = behaviour
        self.requests = []

    def fetch_page(self, request):
        self.requests.append(request)
        articles = self.behaviour(request)
        raw = json.dumps(articles).encode()
        return ProviderPage(request, articles, raw, 200, "2026-10-19T00:00:00+00:00", 1)


def synthetic_config(limit=2, max_offset=4):
    values = copy.deepcopy(EodhdPilotConfig.load(CONFIG).values)
    values["pagination"] = {"limit": limit, "max_offset": max_offset}
    values["companies"] = {"AAPL": values["companies"]["AAPL"]}
    values["modes"]["demo"]["tickers"] = ["AAPL.US"]
    return EodhdPilotConfig(Path("config/eodhd_pilot.json"), values)


def raw_article(number, day="2026-10-18"):
    return {
        "date": day,
        "title": f"Synthetic article {number}",
        "content": f"Synthetic content {number}",
        "link": f"https://example.test/{day}/{number}",
        "symbols": ["AAPL.US"],
    }


def test_pagination_and_resume_without_duplicate_calls(tmp_path):
    source = SyntheticProvider(lambda request: [raw_article(request.offset + i) for i in range(2)] if request.offset == 0 else [raw_article(2)])
    config = synthetic_config()
    first = EodhdPilot(config, repository=tmp_path, provider=source).run(
        mode="demo", start=date(2026, 10, 18), end=date(2026, 10, 18)
    )
    assert first["counts"]["articles"] == 3
    assert first["counts"]["http_calls"] == 2
    assert first["counts"]["http_calls_this_run"] == 2
    assert [request.offset for request in source.requests] == [0, 2]
    failing = SyntheticProvider(lambda request: pytest.fail("resume called provider"))
    second = EodhdPilot(config, repository=tmp_path, provider=failing).run(
        mode="demo", start=date(2026, 10, 18), end=date(2026, 10, 18)
    )
    assert second["counts"]["articles"] == 3
    assert second["counts"]["windows_resumed"] == 1
    assert second["counts"]["http_calls"] == 2
    assert second["counts"]["http_calls_this_run"] == 0


def test_explicit_run_executes_only_supplied_windows_in_separate_derived_namespace(tmp_path):
    source = SyntheticProvider(lambda request: [raw_article(request.window.start.day)])
    config = synthetic_config()
    windows = [
        query_window(start=date(2024, 1, 1), end=date(2024, 1, 2)),
        query_window(start=date(2024, 2, 1), end=date(2024, 2, 2)),
    ]
    pilot = EodhdPilot(
        config,
        repository=tmp_path,
        provider=source,
        derived_namespace="known_episode_probe",
    )

    result = pilot.run_windows(mode="known_episode_probe", windows=windows)

    assert [request.window for request in source.requests] == windows
    assert result["counts"]["http_calls_this_run"] == 2
    assert (tmp_path / "data/processed/eodhd_mag7/known_episode_probe/manifest.json").exists()


def test_offset_ceiling_splits_date_window(tmp_path):
    def behaviour(request):
        if request.window.start != request.window.end:
            return [raw_article(request.offset), raw_article(request.offset + 1)]
        return [raw_article(request.window.start.day, request.window.start.isoformat())]
    source = SyntheticProvider(behaviour)
    result = EodhdPilot(synthetic_config(), repository=tmp_path, provider=source).run(
        mode="demo", start=date(2026, 10, 17), end=date(2026, 10, 18)
    )
    assert result["counts"]["articles"] == 2
    assert max(request.offset for request in source.requests) < 4
    assert {(request.window.start, request.window.end) for request in source.requests} >= {
        (date(2026, 10, 17), date(2026, 10, 17)),
        (date(2026, 10, 18), date(2026, 10, 18)),
    }


class RejectedProvider(NewsProvider):
    def fetch_page(self, request):
        raise ProviderResponseError("synthetic rejected window", status_code=400, attempts=1)


def test_invalid_window_is_recorded_without_crashing_run(tmp_path):
    result = EodhdPilot(synthetic_config(), repository=tmp_path, provider=RejectedProvider()).run(
        mode="demo", start=date(2026, 10, 18), end=date(2026, 10, 18)
    )
    assert result["counts"]["windows_failed"] == 1
    assert result["counts"]["http_calls"] == 1
    error = next(tmp_path.glob("data/restricted/news/eodhd/raw/**/error.sanitized.json"))
    assert "synthetic rejected window" in error.read_text()


@pytest.mark.integration
@pytest.mark.skipif(not os.environ.get("EODHD_API_TOKEN"), reason="EODHD_API_TOKEN not configured")
def test_optional_real_integration_uses_one_page_only():
    config = EodhdPilotConfig.load(CONFIG)
    real = EodhdProvider(
        endpoint=config["endpoint"], api_token=os.environ["EODHD_API_TOKEN"],
        timeout_seconds=10, max_attempts=2, backoff_base_seconds=0.2,
        backoff_max_seconds=1, jitter_seconds=0,
    )
    page = real.fetch_page(PageRequest(query_window(), 1, 0))
    assert isinstance(page.articles, list)
