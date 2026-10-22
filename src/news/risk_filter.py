from __future__ import annotations

import re

from .normalize import normalized_text
from .schemas import NormalizedArticle


class RiskFamilyFilter:
    """High-recall, auditable candidate selection; never a scientific label."""

    def __init__(self, rules: dict):
        self.rules: dict[str, list[tuple[str, re.Pattern]]] = {}
        for family, entries in rules.items():
            self.rules[family] = [
                (entry["label"], re.compile(entry["pattern"], re.I)) for entry in entries
            ]

    def apply(self, article: NormalizedArticle) -> dict[str, list[str]]:
        text = normalized_text(article.title + "\n" + article.content)
        matches = {
            family: [label for label, pattern in patterns if pattern.search(text)]
            for family, patterns in self.rules.items()
        }
        matches = {family: terms for family, terms in matches.items() if terms}
        article.risk_family_candidates = sorted(matches)
        article.risk_match_terms = matches
        return matches
