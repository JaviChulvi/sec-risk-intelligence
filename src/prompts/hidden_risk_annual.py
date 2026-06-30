from __future__ import annotations

from typing import Any


SYSTEM_PROMPT = """\
You are evaluating implicit or underemphasized risks inside one SEC 10-K Item 1A
Risk Factors section.

Return strict JSON only. The user will provide the Item 1A section text for one
company and year. Your job is not to list every explicit heading. Your job is to
identify the most important underlying risks that are implied by the risk-factor
language, repeated across disclosures, or stated in a way that may understate a
broader exposure.

Universal risk domains:
- strategic
- operational
- financial
- market_macro
- credit_liquidity_capital
- regulatory_legal
- technology_cyber
- third_party
- governance_reputation
- accounting_reporting
- other

Hiddenness types:
- underemphasized
- fragmented_across_disclosure
- softened_language
- indirect_causal_chain
- emerging_risk
- buried_in_boilerplate
- repeated_but_not_escalated
- other

Rules:
- Output JSON with keys: company, ticker, year, section, hidden_risks.
- hidden_risks must be an array of objects with keys: risk_id, risk_domain,
  sector_specific_topic, hiddenness_type, implicit_risk,
  why_hidden_or_underemphasized, evidence, severity, confidence.
- risk_domain must come from the universal risk domains list.
- sector_specific_topic is free text generated from the filing evidence. Use a
  concise snake_case topic that fits the company's actual business, sector, and
  disclosure language.
- hiddenness_type must come from the hiddenness types list.
- severity and confidence must each be one of: low, medium, high.
- evidence must be an array of objects with keys: quote, reason.
- Every quote must be a short exact contiguous quote from the provided Item 1A
  text.
- Do not invent facts, external context, or risks unsupported by the text.
- Do not merely restate a heading. Explain the underlying exposure signaled by
  the language.
- If there are no sufficiently supported implicit risks, return hidden_risks: [].
- Prefer 1 to 4 high-confidence findings. Omit weak findings.

Example JSON shape:
{
  "company": "Example Company",
  "ticker": "EX",
  "year": 2025,
  "section": "Item 1A. Risk Factors",
  "hidden_risks": [
    {
      "risk_id": "ex-2025-001",
      "risk_domain": "strategic",
      "sector_specific_topic": "subscription_cloud_execution",
      "hiddenness_type": "indirect_causal_chain",
      "implicit_risk": "The business model is becoming more dependent on reliable cloud delivery and subscription expansion.",
      "why_hidden_or_underemphasized": "The text frames cloud delivery as a disclosed operational risk, but the broader exposure is recurring-revenue execution risk.",
      "evidence": [
        {
          "quote": "cloud-based offerings on a subscription basis",
          "reason": "This language ties the business model to subscription cloud adoption."
        }
      ],
      "severity": "medium",
      "confidence": "high"
    }
  ]
}
"""


def build_hidden_risk_annual_messages(
    eval_case: dict[str, Any],
    risk_factor_text: str,
) -> list[dict[str, str]]:
    company = eval_case["company"]
    ticker = eval_case["ticker"]
    year = eval_case["year"]
    section = eval_case["risk_factor_used"]["section"]
    sector = eval_case.get("sector") or "not provided"
    industry = eval_case.get("industry") or "not provided"
    business_model = eval_case.get("business_model") or "not provided"

    user_prompt = f"""\
Analyze this single-year 10-K Item 1A section for implicit or underemphasized
risks and return them as strict JSON.

Company: {company}
Ticker: {ticker}
Year: {year}
Section: {section}
Sector metadata: {sector}
Industry metadata: {industry}
Business model metadata: {business_model}

Important analysis guidance:
- Look for underlying exposures implied by the disclosures, not just explicit
  headings.
- Treat a risk as supported only when the provided Item 1A text contains direct
  evidence for it.
- Use the generic risk_domain for cross-company comparison, then create a
  sector_specific_topic yourself from the filing text.
- Prefer a small number of high-confidence, evidence-backed findings over a long
  speculative list.
- Do not compare against another year. This case contains only one filing year.
- If a finding cannot be supported with exact quotes, omit it.
- Do not use the sector metadata as evidence. It is only orientation; evidence
  must come from Item 1A.

<item_1a_text>
{risk_factor_text}
</item_1a_text>
"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
