# Invariants

Project-wide constraints that bind **every** phase. Unlike the decisions in
`RULES.md`, these predate the card store — they are lifted verbatim from
`.planning/ROADMAP.md` and the implementation register, and are reproduced here so
they can be loaded in ~700 tokens instead of 144 KB.

Source of truth remains `.planning/ROADMAP.md`. If the two disagree, ROADMAP wins
and this file is stale.

| ID | Constraint |
|---|---|
| **INV-1** | Kernel knows no workflow by name — branches default `main`/`work`, never a workflow-name branch |
| **INV-2** | No per-run state on the singleton — state lives on `ExecutionContext` / durable rows |
| **INV-3** | Semantic event parity; deliverables byte-identical where deterministic (the 5 characterization goldens) |
| **INV-5** | No DSL — control-flow keys stay rejected; strict-key rejection preserved |
| **INV-7** | The engine decides, never the manifest (merge stays engine-selected — no merge picker) |
| **INV-8** | Default-deny ownership — `ScopedStore`, cross-owner access raises `PermissionError` |
| **INV-9** | exec / network / secrets default OFF; mcp / integrations default none |
| **INV-12** | Move, don't copy — deletion is an exit gate |
| **INV-13** | LangChain `deepagents` only, never hand-rolled; `create_deep_agent` confined to the adapter |
| **SC-001** | Launchability is keyed on the declared flag, never a hardcoded name list — a saved workflow is pure data, no new pipeline name |

Also load-bearing but not numbered as invariants: **Ports & Adapters** (import-linter
4 kept / 0 broken) and **additive migrations only** (every new table/column carries
`owner_id` + `workspace_id`).

## Gaps — read before trusting this file

- **INV-4, INV-6, INV-10, INV-11 have no definition** anywhere in `ROADMAP.md` or
  `IMPLEMENTATION-REGISTER.md`. They may never have existed, or their definitions
  live somewhere not yet indexed. Do not infer them.
- **The register's Invariants column is largely boilerplate.** 160+ of 168 fix cards
  cite `INV-1/3/12/SC-001`, which is a template rather than a considered claim. Treat
  a citation as weak evidence that a fix actually touched that invariant, and confirm
  against the fix body.
- This file is **hand-maintained**, unlike `INDEX.md` and `RULES.md`. It will drift
  when ROADMAP changes. Re-check it whenever a new invariant appears.
