import copy
from pathlib import Path

from src.news.eodhd_config import EodhdPilotConfig
from src.news.risk_filter import RiskFamilyFilter
from src.tests.news_helpers import normalized_article


CONFIG = Path(__file__).resolve().parents[2] / "config" / "eodhd_pilot.json"


def test_specific_phrases_can_select_multiple_families_and_preserve_terms():
    rules = EodhdPilotConfig.load(CONFIG)["risk_rules"]
    article = normalized_article(content="A data breach followed a critical supplier disruption and reduced purchases.")
    matches = RiskFamilyFilter(rules).apply(article)
    assert set(matches) == {"customer_concentration", "critical_suppliers", "cybersecurity"}
    assert "data breach" in matches["cybersecurity"]


def test_bare_customer_or_supplier_mentions_do_not_select_article():
    rules = EodhdPilotConfig.load(CONFIG)["risk_rules"]
    article = normalized_article(content="A customer met a supplier during an ordinary product launch.")
    assert RiskFamilyFilter(rules).apply(article) == {}


def test_configured_selection_requires_adverse_evidence_near_the_company():
    config = EodhdPilotConfig.load(CONFIG)
    risk_filter = RiskFamilyFilter(config["risk_rules"], config["risk_filter"])
    article = normalized_article(
        title="Other company reports a data breach",
        content=("Hackers breached its systems. " + "unrelated words " * 40 + "Apple shares rose."),
    )
    assert risk_filter.apply(article) == {}


def test_provider_update_outage_is_classified_as_supplier_not_cyberattack():
    config = EodhdPilotConfig.load(CONFIG)
    risk_filter = RiskFamilyFilter(config["risk_rules"], config["risk_filter"])
    article = normalized_article(
        company="MSFT",
        title="Global IT outage affects Microsoft Windows",
        content=(
            "A faulty software update caused the outage. The provider said it was not a cyberattack."
        ),
    )
    assert set(risk_filter.apply(article)) == {"critical_suppliers"}
