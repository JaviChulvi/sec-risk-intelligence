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
