"""Segment a 10-K Item 1A section into its individual risk factors.

Filers structure Item 1A as a two-level hierarchy: bold *category* headers
("Regulatory", "Market", "Credit") that group several bold *risk factor*
headings, each followed by body paragraphs. edgar-crawler flattens the HTML to
plain text and drops the bold styling, so the hierarchy has to be recovered.

Two detectors reconstruct it:

``BoldHeadingDetector``
    Reads the bold runs straight from the filing HTML and matches them against
    the extracted lines. Exact, and the preferred option whenever the raw HTML
    is at hand (``data/edgar_crawler_live/RAW_FILINGS``).

``HeuristicHeadingDetector``
    Fallback for text-only inputs: a short declarative line followed by a long
    paragraph. Cheaper but noisier — it both misses headings and promotes body
    sentences, so prefer the bold detector when the HTML is available.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Protocol

from src.text_analysis.sentences import count_sentences

# Page furniture and section titles that are bold but carry no risk content.
_FURNITURE = re.compile(r"^(part\s+[ivx]+|item\s+\d+[a-z]?\.?\s|summary$|other$)", re.IGNORECASE)
_BULLET_PREFIXES = ("•", "▪", "·", "-", "*", "•")
_WHITESPACE = re.compile(r"\s+")

# ``font-weight:700`` (JPM, BAC) and ``font-weight:bold`` (older filers) both
# mark headings; anything at 600+ is bold in practice.
_BOLD_STYLE = re.compile(r"font-weight\s*:\s*(bold|[6-9]00)", re.IGNORECASE)
_BOLD_TAGS = ("b", "strong")

# A bold run this short with no terminal period is a category header, not a
# risk factor (e.g. "Regulatory", "Business Operations").
_CATEGORY_MAX_CHARS = 40


def normalize(text: str) -> str:
    """Collapse whitespace and case-fold, for matching HTML runs to text lines."""
    return _WHITESPACE.sub(" ", text).strip().lower()


@dataclass(frozen=True)
class RiskFactor:
    """One risk factor: its heading, its body, and the category it sits under."""

    order: int
    heading: str
    body: str
    category: str | None = None

    @property
    def text(self) -> str:
        return f"{self.heading}\n{self.body}" if self.body else self.heading

    @property
    def word_count(self) -> int:
        return len(self.text.split())

    @property
    def sentence_count(self) -> int:
        return count_sentences(self.text)


class HeadingDetector(Protocol):
    """Decides, line by line, what role a line plays in the section."""

    def is_heading(self, line: str, next_line: str) -> bool: ...

    def is_category(self, line: str) -> bool: ...


class BoldHeadingDetector:
    """Headings recovered from the bold runs of the original filing HTML."""

    def __init__(self, bold_runs: Iterable[str]) -> None:
        self._bold = frozenset(normalize(run) for run in bold_runs if run.strip())

    @classmethod
    def from_html(cls, html: str) -> BoldHeadingDetector:
        """Collect every bold text run in ``html``.

        Parsing the whole filing is deliberate: the runs are only ever used as a
        lookup set, so there is no need to locate Item 1A here — the caller
        already holds the extracted section text.
        """
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")
        runs = []
        for element in soup.find_all(["span", "b", "strong"]):
            style = element.get("style") or ""
            if element.name in _BOLD_TAGS or _BOLD_STYLE.search(style):
                text = element.get_text(" ", strip=True)
                if text:
                    runs.append(text)
        return cls(runs)

    def is_heading(self, line: str, next_line: str) -> bool:
        if not self._is_bold(line) or _is_furniture(line):
            return False
        return not self.is_category(line)

    def is_category(self, line: str) -> bool:
        if not self._is_bold(line) or _is_furniture(line):
            return False
        return len(line) <= _CATEGORY_MAX_CHARS and not line.endswith(".")

    def _is_bold(self, line: str) -> bool:
        return normalize(line) in self._bold


class HeuristicHeadingDetector:
    """Length-based fallback: a short declarative line before a long paragraph."""

    def __init__(
        self,
        *,
        min_chars: int = 40,
        max_chars: int = 250,
        min_body_chars: int = 300,
    ) -> None:
        self.min_chars = min_chars
        self.max_chars = max_chars
        self.min_body_chars = min_body_chars

    def is_heading(self, line: str, next_line: str) -> bool:
        if _is_bullet(line) or _is_furniture(line):
            return False
        if not self.min_chars <= len(line) <= self.max_chars:
            return False
        # A trailing colon introduces a bullet list; a lowercase start means the
        # line is a fragment of a paragraph broken by extraction.
        if line.endswith(":") or not line[:1].isupper():
            return False
        return not _is_bullet(next_line) and len(next_line) >= self.min_body_chars

    def is_category(self, line: str) -> bool:
        # Without styling there is no reliable way to tell a category header from
        # a stray short line, so the heuristic detector reports no categories.
        return False


class RiskFactorSegmenter:
    """Split an Item 1A section into :class:`RiskFactor` objects."""

    def __init__(self, detector: HeadingDetector) -> None:
        self.detector = detector

    def segment(self, text: str) -> list[RiskFactor]:
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        factors: list[RiskFactor] = []
        category: str | None = None
        heading: str | None = None
        body: list[str] = []

        def flush() -> None:
            if heading is not None:
                factors.append(
                    RiskFactor(
                        order=len(factors) + 1,
                        heading=heading,
                        body="\n".join(body).strip(),
                        category=category,
                    )
                )

        for index, line in enumerate(lines):
            next_line = lines[index + 1] if index + 1 < len(lines) else ""
            if self.detector.is_category(line):
                flush()
                heading, body = None, []
                category = line
            elif self.detector.is_heading(line, next_line):
                flush()
                heading, body = line, []
            elif heading is not None:
                body.append(line)
        flush()
        return factors


def _is_bullet(line: str) -> bool:
    return line.startswith(_BULLET_PREFIXES)


def _is_furniture(line: str) -> bool:
    return bool(_FURNITURE.match(line))
