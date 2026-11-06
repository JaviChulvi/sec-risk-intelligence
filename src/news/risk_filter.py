from __future__ import annotations

import re
from dataclasses import dataclass

from .normalize import normalized_text
from .schemas import NormalizedArticle


@dataclass(frozen=True)
class FamilySuppressionRule:
    family: str
    when_family_present: str
    pattern: re.Pattern


class RiskFamilyFilter:
    """Auditable risk-news selection and family classification."""

    def __init__(self, rules: dict, selection: dict | None = None):
        self.rules: dict[str, list[tuple[str, re.Pattern]]] = {}
        for family, entries in rules.items():
            self.rules[family] = [
                (entry["label"], re.compile(entry["pattern"], re.I)) for entry in entries
            ]
        selection = selection or {}
        self.context_chars = int(selection.get("company_context_chars", 0))
        self.company_aliases = {
            company: re.compile(pattern, re.I)
            for company, pattern in selection.get("company_alias_patterns", {}).items()
        }
        self.adverse_event_patterns = [
            re.compile(entry["pattern"], re.I)
            for entry in selection.get("adverse_event_patterns", [])
        ]
        self.suppression_rules = [
            FamilySuppressionRule(
                family=entry["family"],
                when_family_present=entry["when_family_present"],
                pattern=re.compile(entry["pattern"], re.I),
            )
            for entry in selection.get("family_suppression_rules", [])
        ]

    def apply(self, article: NormalizedArticle) -> dict[str, list[str]]:
        text = self._evidence_text(article)
        matches = {
            family: [label for label, pattern in patterns if pattern.search(text)]
            for family, patterns in self.rules.items()
        }
        matches = {family: terms for family, terms in matches.items() if terms}
        if self.adverse_event_patterns and not any(
            pattern.search(text) for pattern in self.adverse_event_patterns
        ):
            matches = {}
        for rule in self.suppression_rules:
            if (
                rule.family in matches
                and rule.when_family_present in matches
                and rule.pattern.search(text)
            ):
                matches.pop(rule.family)
        article.risk_family_candidates = sorted(matches)
        article.risk_match_terms = matches
        return matches

    def _evidence_text(self, article: NormalizedArticle) -> str:
        text = normalized_text(article.title + "\n" + article.content)
        aliases = self.company_aliases.get(article.company)
        if not aliases or not self.context_chars:
            return text
        spans = [
            (max(0, match.start() - self.context_chars), min(len(text), match.end() + self.context_chars))
            for match in aliases.finditer(text)
        ]
        if not spans:
            return ""
        merged: list[list[int]] = []
        for start, end in spans:
            if merged and start <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, end])
        # A newline prevents bounded ``.`` patterns from joining unrelated context windows.
        return "\n".join(text[start:end] for start, end in merged)
