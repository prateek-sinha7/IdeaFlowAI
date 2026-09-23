# Specification Quality Checklist: PDF extraction

**Purpose**: Validate specification completeness and quality before planning
**Created**: 2026-08-28 · **Revised**: 2026-08-28 (rewritten after measuring the real document)
**Feature**: [spec.md](../spec.md)

## Content Quality

- [~] No implementation details (languages, frameworks, APIs) — **deliberate deviation, see Notes**
- [x] Focused on user value and business needs
- [~] Written for non-technical stakeholders — **deliberate deviation, see Notes**
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic
- [x] All acceptance scenarios are defined — 11
- [x] Edge cases are identified — 10
- [x] Scope is clearly bounded — §6, 10 exclusions each with a reason
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [~] No implementation details leak into specification — **deliberate deviation, see Notes**

## Notes

### What changed in this revision

The first draft was written from the retired `014-pdf-tools` reasoning. It was then **tested
against the real target document** and one central decision was reversed on evidence:

| | First draft | Now | Why |
|---|---|---|---|
| Image source | embedded images | **crop of the rendered page** | embedded images lose the red annotation arrows that carry the instruction (§3.1) |
| Tool output | content returned to the model | **materialise to disk, return a receipt** | matches the two shipped visual specs; no tool in this codebase returns an image |
| Image→model path | image blocks in `tool_result` (unproven) | **`pdf_pages` input provider** | uses the port `run_images` already ships; **closes RISK-01 entirely** |
| Text/image pairing | interleaved in the tool's return value | **`@[[image-N.png]]` placeholders in `text.md`** | verified end to end on page 2 |
| Cache | separate `.pdfcache/pages.jsonl` | **deleted — the folder is the state** | a page directory exists ⇔ that page is done |
| Concurrency | "must be concurrency-safe" | **temp-dir-then-atomic-rename** | one idiom gives completeness, resume and concurrency safety together |
| Parallelism | not addressed | **processes above a page threshold, never threads** | measured: threads 0.99x, and rendering across threads crashes the process |
| Bounds | seven invented constants | **removed** — the whole document is ~22k tokens | measured; page-range bounds barely bind at this size |

### The three unmet Content Quality items

Knowingly not met, and the spec was not rewritten to meet them. This repository's specs are
engineering documents — [017](../../017-ppt-v2-pptx/spec.md) and [018](../../018-agent-browser-tools/spec.md),
the two most recent and both shipped, name concrete files, functions and libraries throughout.
Removing `pypdfium2`, `manifest.py`, `RunSandbox.path_for` and the `input_provider` port from
this spec would delete the evidence for its own central decisions — the render-vs-embedded
reversal, the grant route, and the mechanism that closed RISK-01. None of those arguments
survives being made generically.

Recorded as a deviation rather than silently passed. A non-technical summary, if wanted, belongs
alongside this document rather than instead of it.

### Evidence

Every figure in §3 was measured, not estimated. Scripts at `.reference/tmp/_run.py`,
`_interleave.py`, `_materialize.py`; output at `.reference/tmp/materialized/`. All re-runnable.

Two things are recorded as *unresolved* rather than papered over: dedupe (RISK-02 — the naive
fix is a correctness bug, not just an incomplete optimisation) and benchmark noise (RISK-04 —
two runs of the same benchmark disagreed by 60%).

**Ready for `/speckit-plan`.**
