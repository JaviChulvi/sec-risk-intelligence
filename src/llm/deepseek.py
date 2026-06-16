from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from src.settings import load_dotenv


DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_TIMEOUT_SECONDS = 180
DEFAULT_MAX_TOKENS = 16000


class DeepSeekAPIError(RuntimeError):
    """Raised when the DeepSeek API request or response is unusable."""


@dataclass(frozen=True)
class DeepSeekConfig:
    api_key: str
    model: str
    base_url: str = DEFAULT_DEEPSEEK_BASE_URL
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS


@dataclass(frozen=True)
class DeepSeekResponse:
    content: str
    model: str | None
    finish_reason: str | None
    usage: dict[str, Any] | None
    raw: dict[str, Any]


class DeepSeekClient:
    """Small OpenAI-compatible DeepSeek chat-completions client."""

    def __init__(
        self,
        config: DeepSeekConfig,
        session: requests.Session | None = None,
    ) -> None:
        if not config.api_key:
            raise DeepSeekAPIError("Missing DEEPSEEK_API_KEY.")
        if not config.model:
            raise DeepSeekAPIError("Missing DEEPSEEK_MODEL.")

        self.config = config
        self.session = session or requests.Session()

    @classmethod
    def from_env(
        cls,
        env_path: Path | str = ".env",
        model: str | None = None,
        base_url: str | None = None,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        session: requests.Session | None = None,
    ) -> "DeepSeekClient":
        load_dotenv(env_path)
        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        resolved_model = model or os.environ.get("DEEPSEEK_MODEL", "")
        return cls(
            DeepSeekConfig(
                api_key=api_key,
                model=resolved_model,
                base_url=base_url or os.environ.get("DEEPSEEK_BASE_URL", DEFAULT_DEEPSEEK_BASE_URL),
                timeout_seconds=timeout_seconds,
            ),
            session=session,
        )

    def chat_completion(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float | None = 0.0,
        json_mode: bool = True,
        retries: int = 2,
    ) -> DeepSeekResponse:
        request_body: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "stream": False,
            "max_tokens": max_tokens,
        }
        if temperature is not None:
            request_body["temperature"] = temperature
        if json_mode:
            request_body["response_format"] = {"type": "json_object"}

        raw = self._post_chat_completion(request_body, retries=retries)
        choices = raw.get("choices") or []
        if not choices:
            raise DeepSeekAPIError("DeepSeek response did not include choices.")

        choice = choices[0]
        message = choice.get("message") or {}
        content = message.get("content") or ""
        finish_reason = choice.get("finish_reason")
        if finish_reason == "length":
            raise DeepSeekAPIError("DeepSeek response was truncated before completion.")
        if not content.strip():
            raise DeepSeekAPIError("DeepSeek returned empty content.")

        return DeepSeekResponse(
            content=content,
            model=raw.get("model"),
            finish_reason=finish_reason,
            usage=raw.get("usage"),
            raw=raw,
        )

    def chat_json(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float | None = 0.0,
        retries: int = 2,
    ) -> tuple[dict[str, Any], DeepSeekResponse]:
        response = self.chat_completion(
            messages,
            max_tokens=max_tokens,
            temperature=temperature,
            json_mode=True,
            retries=retries,
        )
        return parse_json_content(response.content), response

    def _post_chat_completion(self, request_body: dict[str, Any], retries: int) -> dict[str, Any]:
        url = self.config.base_url.rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }

        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                response = self.session.post(
                    url,
                    headers=headers,
                    json=request_body,
                    timeout=self.config.timeout_seconds,
                )
            except requests.RequestException as exc:
                last_error = exc
                if attempt < retries:
                    time.sleep(2**attempt)
                    continue
                raise DeepSeekAPIError(f"DeepSeek request failed: {exc}") from exc

            if response.status_code in {429, 500, 502, 503, 504} and attempt < retries:
                time.sleep(2**attempt)
                continue

            if not response.ok:
                message = response.text[:800].replace(self.config.api_key, "[redacted]")
                raise DeepSeekAPIError(
                    f"DeepSeek API returned HTTP {response.status_code}: {message}"
                )

            try:
                return response.json()
            except json.JSONDecodeError as exc:
                raise DeepSeekAPIError("DeepSeek response was not valid JSON.") from exc

        raise DeepSeekAPIError(f"DeepSeek request failed after retries: {last_error}")


def parse_json_content(content: str) -> dict[str, Any]:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise DeepSeekAPIError("DeepSeek content did not contain a JSON object.")
        parsed = json.loads(cleaned[start : end + 1])

    if not isinstance(parsed, dict):
        raise DeepSeekAPIError("DeepSeek JSON content must be an object.")
    return parsed
