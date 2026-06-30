# Agent Instructions

## Eval Expected Content

When creating or revising expected eval content from an SEC `10-K` `Item 1A. Risk Factors` section, use the project skills as analysis guides:

- Use `$sec-risk-factor-identification` from `.codex/skills/sec-risk-factor-identification/` to produce explicit risk-factor heading content for `expected_result_by_llm.risk_factors` in `eval.json`.
- Use `$sec-hidden-risk-identification` from `.codex/skills/sec-hidden-risk-identification/` to produce evidence-backed `expected_hidden_risks` candidates for hidden-risk fixtures.

These skills are for reading the Risk Factors text and drafting fixture-ready expected content. Do not execute code, tests, eval runners, notebooks, or shell commands for this task unless the user explicitly asks for execution or validation.

For hidden-risk expected content, analyze one annual `Item 1A` section at a time, use only evidence from that section, and mark new expected findings as `review_status: candidate`.

Keep generated fixture content portable for teammates. Do not include personal absolute filesystem paths in committed files, notebooks, or documentation.
