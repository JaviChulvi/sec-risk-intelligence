from __future__ import annotations

from typing import Any


SYSTEM_PROMPT = """\
You are analysing a section from an SEC 10-K annual report filed by a US financial institution.

Return strict JSON only. Identify the main subsections within the provided text
and produce a structured breakdown.

Output JSON with exactly these top-level keys:
  company     – company name (string)
  ticker      – stock ticker (string)
  year        – fiscal year (integer)
  item        – 10-K item label, e.g. "Item 1A. Risk Factors" (string)
  subsections – ordered array of subsection objects

Each subsection object must have:
  order       – integer starting at 1
  title       – heading or inferred name for this subsection (string)
  summary     – 2–3 sentence description of what this subsection covers (string)
  key_points  – array of 3–5 strings with the most important facts or disclosures

Rules:
- Derive subsections from the actual headings and structure present in the text.
- If the section has no explicit headings, divide it logically and infer concise titles.
- Do not fabricate data absent from the text.
- Keep summaries and key_points concise and factual.
- Return valid JSON with no markdown fences or extra commentary outside the JSON object.
"""


def build_subsection_breakdown_messages(
    eval_case: dict[str, Any],
    section_text: str,
) -> list[dict[str, str]]:
    company = eval_case["company"]
    ticker = eval_case["ticker"]
    year = eval_case["year"]
    item_label = eval_case["risk_factor_used"]["section"]

    user_prompt = f"""\
Break down the following 10-K section into its main subsections and return structured JSON.

Company: {company}
Ticker: {ticker}
Year: {year}
Section: {item_label}

<section_text>
{section_text}
</section_text>
"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
