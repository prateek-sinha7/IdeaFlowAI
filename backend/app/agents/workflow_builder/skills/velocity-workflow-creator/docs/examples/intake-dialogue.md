# Intake dialogues: when to ask, and when not to

Two worked examples for the builder's intake step (`docs/intake-slots.md`). The first is a
vague request: the gap analysis finds blocking gaps, so the intake asks one round of
questions and only then settles the Brief. The second is fully specified: every blocking
slot is filled from the request, so the intake asks nothing.

## Example 1: "create workflow for converting pdf to md content"

### Gap analysis first

Before writing any Brief, go through the slots and ask "does the request state this?"

| Slot | Criticality | From the request? | Source | Why it matters here |
|---|---|---|---|---|
| goal | blocking | "converting pdf to md content" | request | Clear enough: PDF in, Markdown out. |
| deliverable | blocking | Markdown, but one file per PDF or one combined file? | unknown | Changes the deliverable strategy and the last step. |
| done_when | blocking | Not stated | unknown | Follows from the fidelity answer; ask that instead. |
| input_source | blocking | "pdf", but uploaded at launch, pasted, or from a system? | unknown | Decides the reading step and what a launch needs. |
| input_variability | blocking | Not stated: digital PDFs only, or scans? | unknown | Scans need an OCR branch; digital text does not. |
| output_structure | blocking | Not stated: what must the Markdown keep? | unknown | Tables, images and page markers each change the prompts. |
| external_systems | blocking | None mentioned, nothing to post | not_applicable (reason: the Markdown is returned in the run) | - |
| write_destinations | blocking | Nothing is written outside the run | not_applicable (reason: no writes) | - |
| irreversible_actions | blocking | Nothing is posted or deleted | not_applicable (reason: read-only conversion) | - |
| human_approval_points | blocking | Not stated | unknown | A review pause adds a gate and a redo loop. |
| volume_scale | important | Not stated | assumed: up to 8 PDFs per run | Echoed as an assumption. |
| constraints | important | Not stated | assumed: keep the source language | Echoed as an assumption. |
| depth | important | No playbook matches | unknown (value null) | Not asked. |

Six blocking slots are open. `done_when` follows from `output_structure`, so five questions
cover them. Each passes the litmus test, for example input_variability: "If the user answers
differently, the workflow changes because scanned PDFs need an OCR reading branch."

### The questions (the intake's JSON, `questions` only)

```json
[
 {"slot": "input_source", "text": "Where do the PDFs come from?", "litmus": "uploads need a file_extract reading step; pasted text needs none", "options": [{"label": "Uploaded when the run starts", "recommended": true}, {"label": "Text pasted into the brief"}, {"label": "Not sure - use default", "fallback": true}]},
 {"slot": "input_variability", "text": "Are some PDFs scans (images of pages) rather than digital text?", "litmus": "scans need an OCR branch from page images", "options": [{"label": "Digital PDFs only", "recommended": true}, {"label": "Some are scans: add an OCR branch"}, {"label": "Mostly scans"}, {"label": "Not sure - use default", "fallback": true}]},
 {"slot": "output_structure", "text": "What must the Markdown keep from the PDF?", "litmus": "tables and images change the conversion rules and the checks", "options": [{"label": "Headings, lists and tables", "recommended": true}, {"label": "Headings, lists, tables and image placeholders with captions"}, {"label": "Plain text with headings only"}, {"label": "Not sure - use default", "fallback": true}]},
 {"slot": "deliverable", "text": "With several PDFs, do you want one Markdown file per PDF or one combined file?", "litmus": "one file per PDF needs a bundle deliverable and a fan-out", "options": [{"label": "One combined file, a section per PDF", "recommended": true}, {"label": "One file per PDF, as a bundle"}, {"label": "Not sure - use default", "fallback": true}]},
 {"slot": "human_approval_points", "text": "Should a person review the Markdown before the run finishes?", "litmus": "a review adds a human gate and a redo loop", "options": [{"label": "No, finish without a pause", "recommended": true}, {"label": "Yes, pause for review and corrections"}, {"label": "Not sure - use default", "fallback": true}]}
]
```

### What the user sees

```text
Before I design this workflow I need a few decisions.

1. Where do the PDFs come from?
   - a) Uploaded when the run starts (recommended)
   - b) Text pasted into the brief
   - c) Not sure - use default
2. Are some PDFs scans (images of pages) rather than digital text?
   - a) Digital PDFs only (recommended)
   - b) Some are scans: add an OCR branch
   - c) Mostly scans
   - d) Not sure - use default
3. ... (output_structure, deliverable, human_approval_points the same way)

- Assumption: volume_scale = up to 8 PDFs per run - correct me if wrong
- Assumption: constraints = keep the source language - correct me if wrong

Reply e.g. "1a 2c 3b", or "defaults" to accept all recommended options.
```

### The user answers: "1a 2b 3b 4a 5a"

The answers merge into the slots (`message_kind: "answer"`). 2b and 3b differ from the
recommendation, so the design changes: an OCR branch, and image placeholders with captions.

| Slot | Value | Source |
|---|---|---|
| goal | Turn uploaded PDFs into faithful Markdown | request |
| deliverable | One combined Markdown file, a section per PDF | user |
| done_when | Every PDF has a section; headings, lists, tables and image captions are kept; scanned pages are read by OCR | user |
| input_source | Uploaded when the run starts | user |
| input_variability | Some are scans: add an OCR branch | user |
| output_structure | Headings, lists, tables and image placeholders with captions | user |
| external_systems | none (returned in the run) | not_applicable |
| write_destinations | none (no writes) | not_applicable |
| irreversible_actions | none (read-only) | not_applicable |
| human_approval_points | No, finish without a pause | user |
| volume_scale | up to 8 PDFs per run | assumed |
| constraints | keep the source language | assumed |

Every blocking slot is filled: READY. `done_when` was derived from the answers, so its
source is `user`.

### The Brief the builder receives

```text
Goal:         turn uploaded PDFs into faithful Markdown, one combined file
Deliverable:  one file, converted.md, a section per PDF
Done when:    every PDF has a section; headings, lists, tables and image captions kept;
              scanned pages read by OCR
Inputs:       uploads (PDF, some scanned)
Variation:    branch on digital text vs scanned page
Quality bar:  none; no human review
Assumptions:  volume_scale = up to 8 PDFs per run; constraints = keep the source language
```

If the user had replied "defaults", every question would take its recommended option with
`source: assumed`, the intake would be ready anyway, and all five would be listed under
Assumptions and Risks in the builder's final response.

## Example 2: a fully specified request, zero questions

Request: "Write a launch email for the new billing module. 150 to 200 words, friendly, for
existing customers. Include the date 1 December and the link to the release notes."

| Slot | Value | Source |
|---|---|---|
| goal | A launch email announcing the billing module to existing customers | request |
| deliverable | The email text as the reply | request |
| done_when | 150-200 words, friendly tone, names the date 1 December, includes the release-notes link | request |
| input_source | The brief only | request |
| input_variability | - (reason: one text brief, no files) | not_applicable |
| output_structure | A short email: subject line, body, call to the release notes | request |
| external_systems | - (reason: the email is returned, not sent) | not_applicable |
| write_destinations | - (reason: nothing is written outside the run) | not_applicable |
| irreversible_actions | - (reason: nothing is sent or written outside the run) | not_applicable |
| human_approval_points | - (reason: the user reads the draft; nothing irreversible follows) | not_applicable |
| constraints | friendly, for existing customers, 150-200 words | request |
| quality_bar | Checks in the prompts: word range, date, link | assumed |

Every blocking slot is filled from the request: READY with `questions: []`. Asking anything
here would be a defect: every answer is already in the request. Because
`human_approval_points` is not_applicable, the builder is told not to add an intake step or a
human gate.

## Example 3: a workflow that posts outside the run

Request: "workflow to post release notes to slack". The post is an irreversible action, so a
person's gate before it is a platform rule, not a question. The intake asks WHERE it posts
(`write_destinations`) and WHAT the person approves (`human_approval_points`), never WHETHER:

```text
2. Which Slack channel should it post to?
   - a) One fixed channel, named now (recommended)
   - b) A channel chosen at each launch
   - c) Not sure - use default
3. What should a person approve before it posts?
   - a) The final message, just before it posts (recommended)
   - b) The draft earlier; later edits still pass a confirm step before posting
   - c) Not sure - use default
```

There is no "No, post automatically" option. If the user writes "post automatically" anyway,
`human_approval_points` becomes `gate-before-post (platform requirement)` and the builder's
reply says in one line why the gate stays.
