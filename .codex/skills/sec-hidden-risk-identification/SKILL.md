---
name: sec-hidden-risk-identification
description: >-
  Use when working on the sec-risk-intelligence project to read a single SEC
  10-K Item 1A Risk Factors text and produce eval-ready expected content for
  implicit, hidden, underemphasized, or underlying risks, especially
  expected_hidden_risks candidates for hidden_risk_annual fixtures. Trigger for
  requests to identify hidden risks, explain why risks are hidden, generate
  evidence-backed expected findings, or analyze one annual Risk Factors section
  manually. This skill is analysis-only: do not execute code, tests, eval
  runners, notebooks, or shell commands as part of the skill workflow. Do not
  use for explicit risk-heading extraction.
---

# SEC Hidden Risk Identification

Read one annual `Item 1A. Risk Factors` section and identify implicit or underemphasized risks supported by that same text. The deliverable is eval-ready expected hidden-risk content, not an executed eval run.

## Output

Default to this fixture-compatible shape for `expected_hidden_risks`:

```json
{
  "expected_hidden_risks": [
    {
      "risk_id": "company-year-001",
      "risk_domain": "strategic",
      "sector_specific_topic": "concise_snake_case_topic",
      "hiddenness_type": "underemphasized",
      "implicit_risk": "The underlying risk stated as a clear, evidence-backed claim.",
      "required_evidence_terms": ["term_or_phrase"],
      "accepted_evidence_quotes": ["short exact quote from Item 1A"],
      "review_status": "candidate"
    }
  ]
}
```

When useful for human review, add a concise explanation outside the JSON or in a separate table with: risk id, why it is hidden or underemphasized, exact quote, and reason the quote supports the claim.

## Risk Classification

Use one universal `risk_domain`:

```text
strategic, operational, financial, market_macro, credit_liquidity_capital,
regulatory_legal, technology_cyber, third_party, governance_reputation,
accounting_reporting, other
```

Generate `sector_specific_topic` as concise snake_case from the filing evidence. Do not require a company-specific or sector-specific taxonomy file.

Use one `hiddenness_type`:

```text
underemphasized, fragmented_across_disclosure, softened_language,
indirect_causal_chain, emerging_risk, buried_in_boilerplate,
repeated_but_not_escalated, other
```

## Analysis Rules

- Analyze only the single provided year. Do not compare against prior or future filings.
- Use only the provided `Item 1A` text as evidence.
- Do not use sector metadata, company knowledge, MD&A, news, or outside context as evidence.
- Prefer 1 to 4 strong findings over a long speculative list.
- Do not merely restate an explicit heading; identify the broader underlying exposure implied by the language.
- Every finding must include at least one short exact quote from `Item 1A` in `accepted_evidence_quotes`.
- Use `required_evidence_terms` for key words or phrases that should appear in a good model answer or its evidence.
- If no implicit risk is sufficiently supported, return `"expected_hidden_risks": []`.

## Eval Alignment

- The content is intended for hidden-risk fixture cases that add manually reviewed `expected_hidden_risks`.
- The scorer can use `risk_domain`, `implicit_risk`, `required_evidence_terms`, and `accepted_evidence_quotes` to compare model findings.
- Mark new findings as `"review_status": "candidate"` until a human accepts or rejects them.
- The skill may use repository files such as `src/prompts/hidden_risk_annual.py`, `src/evals/hidden_risk_annual.py`, or `hidden_risk_annual.discovery.json` as schema references when already available in context, but it must not run them.
- Keep paths and examples portable for teammates; never include a personal checkout path in generated content.
