from __future__ import annotations

from abc import ABC, abstractmethod

from ..schemas import PageRequest, ProviderPage


class ProviderError(RuntimeError):
    """Safe provider error whose message never includes credentials or article bodies."""

    def __init__(self, message: str, *, attempts: int = 0):
        super().__init__(message)
        self.attempts = attempts


class AuthenticationError(ProviderError):
    pass


class ProviderResponseError(ProviderError):
    def __init__(self, message: str, *, status_code: int | None = None, sanitized_payload=None, attempts: int = 0):
        super().__init__(message, attempts=attempts)
        self.status_code = status_code
        self.sanitized_payload = sanitized_payload


class NewsProvider(ABC):
    @abstractmethod
    def fetch_page(self, request: PageRequest) -> ProviderPage:
        raise NotImplementedError
