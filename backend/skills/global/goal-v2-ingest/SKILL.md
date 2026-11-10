---
name: goal-v2-ingest
display_name: Goal v2 — Ingest
description: Fast inventory of every file a run was given — type, role, what the documents reference that was never uploaded. Lists and classifies; does not read documents end to end.
category: workflow
isBeta: false
tags:
- ingest
- inventory
---

# Ingest (v2): a fast, literal inventory

Output: `.goal/inventory.json` and `.goal/missing.json`. Keep it fast — the ledger step reads the documents in
full; you only classify them.

## Steps

1. `read_file .uploads/manifest.json`.
2. For every file call `extract_text` once (this materialises PDFs/Office files for the later steps). Do NOT read
   the pages yourself; use the receipt (format, pages, path). For text files (xml, json, csv, …) look only at the
   first ~40 lines to learn the root element / top-level keys.
3. Give each file one role: `requirements`, `data`, `reference`, `design`, `unknown`.
4. Missing files: `grep` the extracted requirement documents (`.extract/**/document.md`) for file names and
   patterns (`\.(xml|json|xsd|csv|pdf|png|docx)\b`, "test assets", "schema"). Every named file that is not
   uploaded goes into `missing.json` with the page that names it.

## Shapes

`inventory.json`: `{"files": [{"name", "type", "bytes", "pages", "extracted", "role", "summary", "keys": {"root",
"ids", "counts"}}], "coverage_notes": ["what the sample data cannot exercise"]}`.
`missing.json`: `{"missing": [{"name", "named_on", "needed_for"}]}`.

Every upload appears exactly once; identifiers copied exactly. Reply with one line: files, roles, missing.
