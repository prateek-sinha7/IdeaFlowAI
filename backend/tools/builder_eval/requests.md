# Builder eval requests

The requests the live harness (`builder_eval_live.py`) sends. From Phase 3 the builder model
and the critic model in evals are `eu.anthropic.claude-haiku-5-5` (`--model` overrides it);
Phase 0-2 results used `eu.anthropic.claude-sonnet-5-5`. Spend is priced with the
platform's `estimate_cost_usd`, which includes the EU regional premium. R1-R3 come from the skill's
`docs/evals/reference-requests.md`. From Phase 1 onward the held-out requests (H1-H3) are the
measure of question quality.

| Id | Request | Notes |
|---|---|---|
| R1 | Create a workflow that builds a clickable prototype of the approval portal from the attached requirement documents. | Reference; the builder chat takes no attachments, so it is sent as text only. |
| R2 | Write a product requirements document for a leave-request feature: employees request leave, managers approve, HR sees the balance. | Reference. |
| R3 | Write a launch email for the new billing module. 150 to 200 words, friendly, for existing customers. Include the date 1 December and the link to the release notes. | Reference; fully specified, so the intake must ask nothing. |
| vague-a | create workflow for converting pdf to md content | **Contaminated by the worked example**: `docs/examples/intake-dialogue.md` uses this exact request, so its questions measure copying, not quality. Kept for regression only. |
| vague-b | make a workflow that summarises documents | Shares the document-conversion slot mix with vague-a. |
| vague-c | workflow to post release notes to slack | Irreversible post: checks the gate rule and write destinations. |
| H1 | workflow to turn customer call transcripts into CRM notes | Held out. Write to an external system (CRM), input variability (transcript formats), output structure. |
| H2 | create a workflow that builds a weekly status report from jira | Held out. External read (Jira), trigger (weekly), output structure, volume. |
| H3 | workflow to translate our product descriptions into german and french | Held out. Constraints (languages, tone, terminology), deliverable per language, quality bar. |

Scripted answers pick an option by LETTER on the question about a slot (`--answer-plan`,
`{slot: letter}`), or are free text (`--followup`); never by keyword.
