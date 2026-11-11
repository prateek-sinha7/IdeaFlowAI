# Reference requests and requirement-fit checks

The builder's behavior is measured on fixed requests. Each run costs model calls, so an operator
runs them, not CI. This file fixes the requests, what each should produce, and the pass criteria.
It is the eval set for the builder's behavior (the spike, NFR-12 in the builder specification).

## How to run one

1. Start from a clean session in the Composer, at `user` trust, with the model under test.
2. Send the request text exactly as written below. For R1, attach the two documents listed.
3. When the builder asks its questions, answer with the answers listed for that request.
4. Save the draft, launch it with Run once, and record the result in the table at the end.
5. For a stored draft, run the offline fit check (below) on the manifest.

## R1: prototype from two documents (UI prototype, Full)

Request: "Create a workflow that builds a clickable prototype of the approval portal from the
attached requirement documents."

Attachments: two requirement documents for one approval portal (about 3 pages each; a fixture
is kept by the team, not in this repo).

Expected:
- The builder asks "Fast or Thorough?" with the outline in one message, and waits.
- Depth Full. Stages: read, analyze, clarify, spec, design, build, QA.
- A `human` gate after the analyst, `redoable`; the reader has `file_extract`.
- The build step has `html_static` and `html_render` with `fix.max_attempts` 2.
- Fit check at full depth: 100 %.

Answers to give when asked: Thorough; the approval rules are those in the documents; no others.

## R2: requirements document from a brief (requirements document, Full)

Request: "Write a product requirements document for a leave-request feature: employees request
leave, managers approve, HR sees the balance."

Attachments: none.

Expected:
- The builder asks what the document must cover (for example approval limits and the balance
  rule) and asks for the form (PRD, not a spec), with the outline.
- Stages: read (may be a short intake), analyze, clarify, stories, NFR, assemble, review.
- The assemble step writes `prd.md`, with every requirement in its acceptance section.
- Fit check at full depth: at least 6 of 7 stages.

Answers to give when asked: the balance rule is "accrued days minus booked days"; approval limit
is "managers approve up to their own team"; PRD form.

## R3: launch email (no playbook, Simple)

Request: "Write a launch email for the new billing module. 150 to 200 words, friendly, for
existing customers. Include the date 1 December and the link to the release notes."

Attachments: none.

Expected:
- No playbook matches; the builder triages it as SIMPLE, asks no question, and builds 2 to 3 steps.
- The word count (150 to 200) and the date and link are in the prompts of the writing and the
  review step, and in the review step's CHECK lines. No validator checks the count.
- No `human` gate, no validators, no fan-out.

## Pass criteria (all requests)

These are the Q-60 criteria, plus the fit check for R1 and R2:

- An accepted draft after at most two Server_Gate rejections.
- The skill validator's last run on the manifest is VALID.
- The adherence record shows the four mandatory skill files read in full, and `overview` and
  `example` run.
- The saved workflow survives a round trip (save, reload, the same manifest).
- The fit check for R1 and R2 meets the threshold above.
- Within 900 seconds and 60 tool calls.
- The operator judges the design right for the request.

## Recording results

| Request | Model | Turns to first save | Gate rejections | Validator | Adherence | Fit (%) | Time (s) | Tool calls | Judgment |
|---|---|---|---|---|---|---|---|---|---|
| R1 | | | | | | | | | |
| R2 | | | | | | | | | |
| R3 | | | | | | | | | |

## Requirement-fit check (offline)

```text
python <skill>/scripts/playbook_fit.py <manifest.json> --playbook ui-prototype --depth full
python <skill>/scripts/playbook_fit.py <manifest.json> --playbook requirements-document --depth full
```

The check looks for the files each playbook stage names, the human gate on the clarify stage,
the HTML validators on the build stage and a critic loop on the QA stage. It is a coverage
check, not a quality check: a prompt can name a file and still write nothing useful. Read the
prompts before you accept a score.
