---
name: goal-v2-ledger
display_name: Goal v2 — Requirement Ledger
description: How to turn documents into a complete requirement ledger with the client's own IDs, acceptance bullets as rows, and the intent of the build. Use in the ledger step of goal_v2.
category: workflow
isBeta: false
tags:
- requirements
- traceability
- ledger
---

# Ledger (v2): every requirement, once, traceable

`.goal/ledger.json` is checked by code (`ledger_check`) at every later step. A requirement missing here is
missing from the product.

## 1. Rows

Read every `requirements` file page by page (`.extract/<fmt>/<slug>/pages/NN/text.md`).

- Numbered requirements (G1, U1-1, REQ-12 …): one row per number, the number is the id. Set `id_pattern` to a
  regex matching all of them, e.g. `^(G\d+|U\d+-\d+|UC\d+-A\d+)$`.
- **Acceptance bullets are rows too (mandatory).** Every bullet under an "Acceptance" heading of a use case gets
  its own row: id `UC<n>-A<k>` in reading order, kind `acceptance`, verbatim text. Include them in
  `id_pattern`.
- Out-of-scope items: rows of kind `constraint`, `testable: false`, text starting "Not built:".
- No numbering in the source: `R-001…` in reading order, `id_pattern` null.

Row shape (all fields required):

```json
{"id": "U4-6", "text": "<verbatim>", "source": {"file": "<upload name>", "page": 10},
 "kind": "display|functional|validation|output|acceptance|non-functional|constraint",
 "use_case": "UC4", "acceptance": "<how a tester proves it, with concrete values from the samples>",
 "testable": true, "status": "open"}
```

`testable: false` only when no browser test can observe it; say why in `acceptance`.

## 2. Completeness loop

1. `ledger_check` mode `harvest` until clean.
2. Re-read every requirements page against the ledger; add what you missed; repeat until a pass adds nothing
   (max 3). State the pass count.

## 3. Intent (`.goal/intent.json`)

`{"deliverable", "profile": "web_tool|prototype", "reason", "data_files": [...], "needs_design": false,
"needs_template": false, "decisions": [{"id", "question", "options", "recommended", "why"}]}`.
`web_tool` when the documents need real behaviour on real input (parse/generate files, validation with concrete
limits, copy/download, offline). The template and design system are the ones chosen at launch; never pick another.

## 4. Only humans decide some things

`decisions` holds only what the documents cannot answer and where a wrong guess changes the build. Everything
else you resolve and cite.

Reply with a short review for the approver: what will be built + profile; rows per use case (source ids vs
generated, acceptance rows); missing files and what they block; each decision with your recommendation.
