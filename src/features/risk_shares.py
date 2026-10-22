"""Turn segmented risk factors into per-category word shares.

Filers publish their own risk taxonomy in the bold category headers of Item 1A,
which is a far more precise instrument than a keyword dictionary applied to
sentences: the label *is* the classification, straight from the issuer.

The catch is that those labels are not stable. JPMorgan filed "Regulatory" and
"Legal" as separate categories through FY2024 and merged them into "Legal and
Regulatory" in FY2025; Bank of America files a single "Regulatory, Compliance
and Legal". Comparing raw labels across filers — or across years within one
filer — therefore measures relabelling as much as risk.

:class:`RiskCategoryTaxonomy` collapses filer labels onto a canonical set, so a
merge or a rename does not surface as a spurious change in the shares. This is
where the regulatory keyword dictionary actually lives, and it is deliberately
tiny: it matches a handful of short, topic-declarative labels rather than tens
of thousands of sentences.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from src.text_analysis.risk_factors import RiskFactor

OTHER = "other"

# Canonical category -> patterns matched against the filer's category label.
# Order matters: the first canonical category whose pattern matches a label wins,
# so more specific categories are declared first.
DEFAULT_CATEGORY_PATTERNS: Mapping[str, Sequence[str]] = {
    # "Conduct" is filed as its own category by JPM but is a compliance matter in
    # substance, so it is folded in here. Split it out if the thesis treats
    # conduct risk as distinct.
    "regulatory_legal": (
        "regulator",
        "compliance",
        "legal",
        "litigation",
        "conduct",
        "supervis",
    ),
    "geopolitical": ("political", "geopolitic", "country", "sovereign"),
    "market": ("market", "interest rate", "trading"),
    "credit": ("credit", "asset quality"),
    "liquidity": ("liquidity", "funding"),
    "capital": ("capital",),
    "operational": ("operational", "business operations", "technology", "cyber"),
    "strategic": ("strategic", "competition"),
    "reputation": ("reputation",),
    "people": ("people", "human capital", "employee"),
}


class RiskCategoryTaxonomy:
    """Collapse filer-specific category labels onto a canonical set."""

    def __init__(
        self,
        patterns: Mapping[str, Sequence[str]] = DEFAULT_CATEGORY_PATTERNS,
        *,
        default: str = OTHER,
    ) -> None:
        self.default = default
        self._patterns = {
            category: re.compile("|".join(re.escape(term) for term in terms), re.IGNORECASE)
            for category, terms in patterns.items()
        }

    @property
    def categories(self) -> tuple[str, ...]:
        """Every canonical category, including the catch-all."""
        return (*self._patterns, self.default)

    def canonical(self, label: str | None) -> str:
        """Return the canonical category for a filer's ``label``."""
        if not label:
            return self.default
        for category, pattern in self._patterns.items():
            if pattern.search(label):
                return category
        return self.default


@dataclass(frozen=True)
class RiskShareProfile:
    """Word counts and shares per canonical category for one filing."""

    words_by_category: Mapping[str, int]
    unclassified_labels: tuple[str, ...] = ()

    @property
    def total_words(self) -> int:
        return sum(self.words_by_category.values())

    def share(self, category: str) -> float:
        """Fraction of segmented risk-factor words in ``category``."""
        total = self.total_words
        return self.words_by_category.get(category, 0) / total if total else 0.0

    def as_features(self, categories: Iterable[str], *, prefix: str = "share_") -> dict[str, float]:
        """Feature row with one share per category, in a stable column order."""
        return {f"{prefix}{category}": self.share(category) for category in categories}


def build_risk_share_profile(
    factors: Sequence[RiskFactor],
    taxonomy: RiskCategoryTaxonomy | None = None,
) -> RiskShareProfile:
    """Aggregate ``factors`` into canonical-category word counts."""
    taxonomy = taxonomy or RiskCategoryTaxonomy()
    words: dict[str, int] = defaultdict(int)
    unclassified: list[str] = []
    for factor in factors:
        category = taxonomy.canonical(factor.category)
        words[category] += factor.word_count
        if category == taxonomy.default and factor.category:
            unclassified.append(factor.category)
    return RiskShareProfile(
        words_by_category=dict(words),
        unclassified_labels=tuple(sorted(set(unclassified))),
    )
