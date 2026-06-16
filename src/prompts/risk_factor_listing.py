from __future__ import annotations

from typing import Any


SYSTEM_PROMPT = """\
You are evaluating SEC 10-K Item 1A Risk Factors extraction.

Return strict JSON only. The user will provide the Item 1A section text for one
company and year. Your job is to list the explicit risk-factor headings
disclosed by the company.

Rules:
- Output JSON with keys: company, ticker, year, section, risk_factors.
- risk_factors must be an ordered array of objects with keys: order, category, title.
- Preserve the substance and wording of each risk-factor heading.
- Include only headings that introduce a disclosed risk factor.
- Ignore introductory boilerplate, table-of-contents artifacts, page labels,
  summary bullets, and body paragraphs.
- Do not infer hidden risks.
- Do not merge distinct headings.
- Do not invent categories or risks.
- If no disclosed risk-factor headings are present, return an empty array.

Example JSON shape:
{
  "company": "Example Company",
  "ticker": "EX",
  "year": 2025,
  "section": "Item 1A. Risk Factors",
  "risk_factors": [
    {
      "order": 1,
      "category": "Risks Related to our Business and Industry",
      "title": "We may experience significant quarterly and annual fluctuations in our results of operations due to a number of factors."
    }
  ]
}
"""


def build_risk_factor_listing_messages(
    eval_case: dict[str, Any],
    risk_factor_text: str,
) -> list[dict[str, str]]:
    company = eval_case["company"]
    ticker = eval_case["ticker"]
    year = eval_case["year"]
    section = eval_case["risk_factor_used"]["section"]

    user_prompt = f"""\
Extract the explicit company-listed risk-factor headings from this 10-K section
and return them as JSON.

Company: {company}
Ticker: {ticker}
Year: {year}
Section: {section}

Important extraction guidance:
- Category headers often start with "Risks Related" or "General Risk".
- The actual risk-factor headings are usually standalone risk statements below
  those category headers.
- Ignore any bullet list beginning with bullet characters; those
  are summary bullets, not the ordered risk-factor heading list for this eval.
- Ignore narrative paragraphs that explain a risk heading.

<item_1a_text>
{risk_factor_text}
</item_1a_text>
"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
