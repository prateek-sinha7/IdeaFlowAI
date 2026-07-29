# `grading/code/` — deterministic grading of built artifacts

The second grading track, which runs **after the build stage**. Where
[`../model/`](../model/) grades prose an LLM must read, this track grades the
built `prototype.html` with executable checks — no judge model, no tokens, a
binary verdict with a machine-readable reason.

**Status: defined, not yet populated.** This README fixes the contract so the
first agent added here has somewhere to land.

## Why it is a separate track

The distinction is not "cheap vs expensive" — it is what the verdict *means*. A
model grade is a calibrated opinion (95/100, might drift, needs a baseline to
interpret). A code grade is a fact ("route `#/invoices` has no matching
`<section data-page="invoices">`"). Facts belong in CI on every commit; opinions
belong in a scheduled run with a tracked baseline. Keeping them in one track
would make the free checks hostage to the expensive ones.

## What belongs here

Checks over a rendered/parsed HTML document, roughly the grading equivalent of
what `app/agents/static_check.py` and `render_check.py` already do inside the
run loop:

- **Structural** — routes ↔ `data-page` sections, the routes map, nav handlers,
  exactly one `is-active`, no duplicate ids.
- **Design-system conformance** — `:root` tokens match the active design
  system's actual values; no seed-template defaults survive; declared CSS classes
  are the ones actually used.
- **Content presence** — no empty or near-empty page section, no filler text.
- **Rendered behaviour** (headless Chromium) — nav switches pages, no console
  errors, no unstyled/overflowing layout.

## What does *not* belong here

Anything requiring judgement about whether the content is *good* — data realism,
whether a page serves the brief, whether the visual style suits the audience.
That is `model/`'s job, and duplicating it here produces two verdicts that
disagree.

## Planned layout

Mirrors `model/` so the two tracks stay navigable together:

```
code/
└── workflows/<workflow>/
    ├── <agent>_checks.py        ← the executable checks
    ├── <agent>_expectations.yaml ← which checks run, thresholds, per-row overrides
    └── example-run/             ← one committed real run, as reference
```

Input is the built artifact from a `model/` run of the same dataset — the same
`dataset_id`, so a row can be traced from brief → spec → tasks → HTML → verdict.

## Open decisions

- Does this track re-use `static_check`/`render_check` directly, or restate the
  checks so a grading regression is distinguishable from a runtime regression?
  (Re-using couples grading to runtime; restating risks the two drifting.)
- Does it grade only the final `prototype.html`, or also each per-task
  intermediate state from the build loop?
