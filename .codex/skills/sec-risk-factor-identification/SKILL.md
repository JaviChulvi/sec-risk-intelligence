---
name: sec-risk-factor-identification
description: >-
  Use when working on the sec-risk-intelligence project to read an SEC 10-K
  Item 1A Risk Factors text and produce eval-ready expected content for explicit
  company-disclosed risk-factor headings, especially
  expected_result_by_llm.risk_factors for eval.json. Trigger for requests to
  identify listed risks, extract risk headings, draft expected risk-factor
  content, or review the Risk Factors section manually. This skill is
  analysis-only: do not execute code, tests, eval runners, notebooks, or shell
  commands as part of the skill workflow. Do not use for implicit or hidden risk
  discovery.
---

# SEC Risk Factor Identification

Read the provided `Item 1A. Risk Factors` text and extract the explicit risk-factor headings that the company lists. The deliverable is eval-ready expected content, not an executed eval run.

## Output

Default to this fixture-compatible shape:

```json
{
  "company": "Company Name",
  "ticker": "TICKER",
  "year": 2025,
  "section": "Item 1A. Risk Factors",
  "task": "List the risk factors explicitly disclosed by the company in the 10-K Item 1A section.",
  "risk_factor_count": 0,
  "risk_factors": [
    {
      "order": 1,
      "category": "Risks Related to ...",
      "title": "Exact risk-factor heading."
    }
  ]
}
```

If the user asks for a compact answer instead of fixture JSON, still preserve `order`, `category`, and `title`.

## Extraction Rules

- Include only standalone headings that introduce disclosed risk factors.
- Preserve the substance and wording of each heading.
- Keep the filing order.
- Use the nearest applicable category header, often headings such as `Risks Related to ...` or `General Risks`.
- Ignore introductory boilerplate, table-of-contents artifacts, page labels, summary bullet lists, and body paragraphs.
- Do not infer hidden risks, merge distinct headings, invent categories, or add risks not listed by the company.
- If no disclosed risk-factor headings are present, return `risk_factor_count: 0` and `risk_factors: []`.

## Eval Alignment

- The content is intended for `expected_result_by_llm` in `eval.json`.
- The eval compares model output titles against `expected_result_by_llm.risk_factors[].title`, so title wording matters more than commentary.
- The skill may use repository files such as `src/prompts/risk_factor_listing.py`, `src/evals/risk_factor_listing.py`, or `eval.json` as schema references when already available in context, but it must not run them.
- Keep paths and examples portable for teammates; never include a personal checkout path in generated content.
