from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .common import clean, digest
from .quality import ContentQualityClassifier
from .schemas import NormalizedArticle, QueryWindow
from .temporal import parse_date


TRACKING_PARAMETERS = {"fbclid", "gclid", "mc_cid", "mc_eid", "vero_conv", "vero_id"}


def canonical_url(value: str) -> str:
    try:
        parsed = urlsplit(value.strip())
        if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
            return ""
        port = f":{parsed.port}" if parsed.port else ""
        host = parsed.hostname.casefold() + port
        query = [
            (key, item)
            for key, item in parse_qsl(parsed.query, keep_blank_values=True)
            if not key.casefold().startswith("utm_") and key.casefold() not in TRACKING_PARAMETERS
        ]
        return urlunsplit((parsed.scheme.casefold(), host, parsed.path or "/", urlencode(sorted(query)), ""))
    except (ValueError, UnicodeError):
        return ""


def normalized_text(value: str) -> str:
    return " ".join(re.sub(r"[^\w]+", " ", value.casefold(), flags=re.UNICODE).split())


def string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        items = value
    elif isinstance(value, str):
        items = re.split(r"[,;|]", value)
    else:
        items = []
    return sorted({clean(item) for item in items if clean(item)})


def optional_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class EodhdNormalizer:
    def __init__(self, quality: ContentQualityClassifier):
        self.quality = quality

    def normalize(
        self,
        raw: dict[str, Any],
        *,
        window: QueryWindow,
        retrieved_at_utc: str,
        raw_sha256: str,
    ) -> NormalizedArticle:
        title = clean(raw.get("title"))
        content = clean(raw.get("content"))
        link = clean(raw.get("link"))
        canonical = canonical_url(link)
        published_original = clean(raw.get("date"))
        published = parse_date(published_original)
        sentiment = raw.get("sentiment") if isinstance(raw.get("sentiment"), dict) else {}
        assessment = self.quality.classify(title=title, content=content)
        if canonical:
            identity_material = canonical
            identity_rule = "sha256(provider + canonical_url)"
        else:
            identity_material = "\n".join((published.normalized or published.original, normalized_text(title)))
            identity_rule = "sha256(provider + published_at + normalized_title)"
        return NormalizedArticle(
            article_id=digest("eodhd\n" + identity_material),
            article_id_rule=identity_rule,
            provider="eodhd",
            company=window.company,
            query_ticker=window.ticker,
            published_at_original=published_original,
            published_at_utc=published.normalized,
            title=title,
            content=content,
            content_available=assessment.availability.value,
            content_length_chars=assessment.length_chars,
            content_length_words=assessment.length_words,
            link=link,
            canonical_url=canonical,
            symbols=string_list(raw.get("symbols")),
            tags=string_list(raw.get("tags")),
            sentiment_polarity=optional_float(sentiment.get("polarity")),
            sentiment_negative=optional_float(sentiment.get("neg")),
            sentiment_neutral=optional_float(sentiment.get("neu")),
            sentiment_positive=optional_float(sentiment.get("pos")),
            retrieved_at_utc=retrieved_at_utc,
            query_from=window.start.isoformat(),
            query_to=window.end.isoformat(),
            raw_sha256=raw_sha256,
            content_sha256=digest(content) if content else "",
            language=assessment.language,
            quality_flags=list(assessment.flags),
        )
