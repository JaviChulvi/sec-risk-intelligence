from src.features.risk_shares import (
    RiskCategoryTaxonomy,
    RiskShareProfile,
    build_risk_share_profile,
)
from src.text_analysis.risk_factors import RiskFactor


def factor(category: str | None, words: int, order: int = 1) -> RiskFactor:
    return RiskFactor(order=order, heading="H.", body=" ".join(["w"] * (words - 1)), category=category)


def test_canonical_collapses_jpm_split_labels_and_bac_merged_label() -> None:
    taxonomy = RiskCategoryTaxonomy()

    # JPM filed these separately through FY2024 and merged them in FY2025.
    assert taxonomy.canonical("Regulatory") == "regulatory_legal"
    assert taxonomy.canonical("Legal") == "regulatory_legal"
    assert taxonomy.canonical("Legal and Regulatory") == "regulatory_legal"
    # BAC files a single merged label.
    assert taxonomy.canonical("Regulatory, Compliance and Legal") == "regulatory_legal"


def test_canonical_maps_filer_specific_labels_to_shared_categories() -> None:
    taxonomy = RiskCategoryTaxonomy()

    assert taxonomy.canonical("Business Operations") == "operational"
    assert taxonomy.canonical("Operational") == "operational"
    assert taxonomy.canonical("Political") == "geopolitical"
    assert taxonomy.canonical("Country") == "geopolitical"
    assert taxonomy.canonical("Geopolitical") == "geopolitical"


def test_canonical_falls_back_to_other_for_unknown_and_missing_labels() -> None:
    taxonomy = RiskCategoryTaxonomy()

    assert taxonomy.canonical("Something Unheard Of") == "other"
    assert taxonomy.canonical(None) == "other"
    assert taxonomy.canonical("") == "other"


def test_taxonomy_is_configurable() -> None:
    taxonomy = RiskCategoryTaxonomy({"conduct": ("conduct",), "regulatory": ("regulator",)})

    assert taxonomy.canonical("Conduct") == "conduct"
    assert taxonomy.canonical("Regulatory") == "regulatory"
    assert "other" in taxonomy.categories


def test_merging_a_split_label_leaves_the_share_unchanged() -> None:
    taxonomy = RiskCategoryTaxonomy()
    split = [factor("Regulatory", 100), factor("Legal", 50), factor("Market", 150)]
    merged = [factor("Legal and Regulatory", 150), factor("Market", 150)]

    assert build_risk_share_profile(split, taxonomy).share("regulatory_legal") == 0.5
    assert build_risk_share_profile(merged, taxonomy).share("regulatory_legal") == 0.5


def test_build_profile_sums_words_and_reports_unclassified_labels() -> None:
    profile = build_risk_share_profile([factor("Regulatory", 100), factor("Zoology", 100)])

    assert profile.total_words == 200
    assert profile.share("regulatory_legal") == 0.5
    assert profile.unclassified_labels == ("Zoology",)


def test_uncategorised_factors_are_not_reported_as_unclassified_labels() -> None:
    profile = build_risk_share_profile([factor(None, 100)])

    assert profile.share("other") == 1.0
    assert profile.unclassified_labels == ()


def test_share_of_empty_profile_is_zero_rather_than_dividing_by_zero() -> None:
    assert RiskShareProfile(words_by_category={}).share("regulatory_legal") == 0.0


def test_as_features_emits_a_stable_column_per_category() -> None:
    profile = build_risk_share_profile([factor("Regulatory", 100), factor("Market", 100)])

    features = profile.as_features(["regulatory_legal", "market", "credit"])

    assert features == {"share_regulatory_legal": 0.5, "share_market": 0.5, "share_credit": 0.0}
