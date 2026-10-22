from __future__ import annotations

import csv
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SECRET_KEYS = {"api_token", "authorization", "token", "eodhd_api_token"}


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(value: str | bytes) -> str:
    payload = value if isinstance(value, bytes) else value.encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def write_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_bytes(value)
    temporary.replace(path)


def write_json(path: Path, value: Any) -> None:
    write_bytes(path, (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def write_csv(path: Path, fields: list[str], rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    with temporary.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({
                key: "'" + value
                if isinstance(value, str) and value.startswith(("=", "+", "-", "@"))
                else value
                for key, value in row.items()
            })
    temporary.replace(path)


def clean(value: Any) -> str:
    text = str(value or "").strip()
    return "" if text.casefold() in {"null", "nan", "none", "n/a"} else text


def load_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Configuration must be a JSON object")
    return payload


def config_fingerprint(config: dict) -> str:
    return digest(json.dumps(config, sort_keys=True, separators=(",", ":")))


def redact_secrets(value: Any) -> Any:
    """Return a serialisable copy with credentials and token-like URL values removed."""
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if key.casefold() in SECRET_KEYS else redact_secrets(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    if isinstance(value, str):
        return re.sub(r"(?i)(api_token|token)=([^&\s]+)", r"\1=[REDACTED]", value)
    return value


def sanitize_error_payload(value: Any) -> dict:
    """Keep diagnostic shape and short scalar messages, never article-like nested bodies."""
    sanitized = redact_secrets(value)
    if not isinstance(sanitized, dict):
        return {"response_type": type(sanitized).__name__}
    result = {}
    for key, item in sanitized.items():
        if isinstance(item, (str, int, float, bool)) or item is None:
            result[key] = item[:500] if isinstance(item, str) else item
        elif isinstance(item, list):
            result[key] = {"type": "list", "items": len(item)}
        elif isinstance(item, dict):
            result[key] = {"type": "object", "keys": sorted(map(str, item))[:50]}
        else:
            result[key] = {"type": type(item).__name__}
    return result


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"Required environment variable is not configured: {name}")
    return value
