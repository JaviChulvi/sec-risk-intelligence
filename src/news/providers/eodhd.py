from __future__ import annotations

import random
import time
from typing import Callable

import requests

from ..common import now_utc, sanitize_error_payload
from ..schemas import PageRequest, ProviderPage
from .base import AuthenticationError, NewsProvider, ProviderError, ProviderResponseError


RETRYABLE_STATUSES = {429, 500, 502, 503, 504}
AUTH_STATUSES = {401, 403}


class EodhdProvider(NewsProvider):
    def __init__(
        self,
        *,
        endpoint: str,
        api_token: str,
        timeout_seconds: float,
        max_attempts: int,
        backoff_base_seconds: float,
        backoff_max_seconds: float,
        jitter_seconds: float,
        session: requests.Session | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        rng: random.Random | None = None,
    ):
        if not api_token:
            raise ValueError("api_token must not be empty")
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        self.endpoint = endpoint
        self._api_token = api_token
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts
        self.backoff_base_seconds = backoff_base_seconds
        self.backoff_max_seconds = backoff_max_seconds
        self.jitter_seconds = jitter_seconds
        self.session = session or requests.Session()
        self.sleeper = sleeper
        self.rng = rng or random.Random()

    def fetch_page(self, request: PageRequest) -> ProviderPage:
        params = {
            "s": request.window.ticker,
            "from": request.window.start.isoformat(),
            "to": request.window.end.isoformat(),
            "limit": request.limit,
            "offset": request.offset,
            "fmt": "json",
            "api_token": self._api_token,
        }
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self.session.get(self.endpoint, params=params, timeout=self.timeout_seconds)
            except requests.RequestException as exc:
                if attempt == self.max_attempts:
                    raise ProviderError(
                        f"EODHD request failed after {attempt} attempts ({type(exc).__name__})",
                        attempts=attempt,
                    ) from None
                self._sleep(attempt)
                continue

            if response.status_code in AUTH_STATUSES:
                raise AuthenticationError(
                    f"EODHD authentication failed with HTTP {response.status_code}", attempts=attempt
                )
            if response.status_code in RETRYABLE_STATUSES:
                if attempt == self.max_attempts:
                    raise ProviderResponseError(
                        f"EODHD returned retryable HTTP {response.status_code} after {attempt} attempts",
                        status_code=response.status_code,
                        attempts=attempt,
                    )
                self._sleep(attempt)
                continue
            if response.status_code >= 400:
                raise ProviderResponseError(
                    f"EODHD rejected the request with HTTP {response.status_code}",
                    status_code=response.status_code,
                    sanitized_payload=self._safe_error_payload(response),
                    attempts=attempt,
                )

            raw = response.content
            try:
                payload = response.json()
            except ValueError:
                raise ProviderResponseError(
                    "EODHD returned a non-JSON success response",
                    status_code=response.status_code,
                    attempts=attempt,
                ) from None
            if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
                raise ProviderResponseError(
                    "EODHD returned an unexpected JSON structure",
                    status_code=response.status_code,
                    sanitized_payload=sanitize_error_payload(payload),
                    attempts=attempt,
                )
            return ProviderPage(
                request=request,
                articles=payload,
                raw_bytes=raw,
                status_code=response.status_code,
                retrieved_at_utc=now_utc(),
                attempts=attempt,
            )
        raise AssertionError("unreachable")

    def _sleep(self, attempt: int) -> None:
        exponential = min(self.backoff_base_seconds * (2 ** (attempt - 1)), self.backoff_max_seconds)
        self.sleeper(exponential + self.rng.uniform(0, self.jitter_seconds))

    @staticmethod
    def _safe_error_payload(response):
        try:
            payload = response.json()
        except ValueError:
            return {"response_type": "non_json", "response_bytes": len(response.content)}
        return sanitize_error_payload(payload)
