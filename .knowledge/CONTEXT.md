---
built_from_commit: e24821ae20dfadcd17f7c384323070d558ee6511
built_at: 2026-08-17
cards_indexed: 582
modules_indexed: 36
---

# Velocity — Context Pack

## 1. What Velocity is

Velocity (internally **Flowin**) is a **workflow-agnostic agent execution
runtime**. A workflow is described by a declarative, file-backed manifest. A
thin compiler (no DSL) turns that manifest into a typed `CompiledWorkflow` /
`ExecutionPlan`. A small kernel executes the plan and knows no workflow by
name — there is no `if pipeline_type == "prototype"` anywhere in it.
Everything that makes a workflow powerful (execution strategies, validators,
deliverable resolvers, context providers, gates, merge strategies, task
parsers, worker agents, runtimes, skills, hooks, tools, MCP servers,
integrations) is a **registered capability** a manifest opts into by
declaration.

**SC-001 (the load-bearing invariant):** A brand-new custom workflow can
replicate the built-in `prototype` workflow using a manifest and an
`AGENT.md` alone — with zero engine edits. If everything else here is
negotiable, this is not.

```
manifest -> WorkflowCompiler (no DSL) -> CompiledWorkflow/ExecutionPlan
    -> Kernel (backend/agents) -> CapabilityRegistry.resolve(kind, name)
    -> Workspace/RuntimeEnvironment (local today; ECS is a swap)
FastAPI (backend/app/api) <-> SSE/WS <-> frontend (Next.js)
```

## 2. Invariants and boundaries

**Always**
- The kernel stays workflow-agnostic — no `if pipeline_type == ...` /
  `if spec.id == ...` branch anywhere in it (INV-1).
- Every capability is resolved through `CapabilityRegistry.resolve(kind,
  name)` behind a Protocol port.
- Database migrations are additive only.
- Import the real LangChain `deepagents` library (INV-13) — a hand-rolled or
  vendored deep-agent runtime is banned and CI-gated.

**Ask first**
- Anything that would violate SC-001 (a new workflow must be expressible as
  manifest + `AGENT.md` with zero engine edits).
- Changes to the `Workspace`/`RuntimeEnvironment` port, which an
  import-linter contract locks shut to keep the ECS swap possible.
- Enabling local exec, which is off by default and sits behind the
  `security` + `approval` gates.

**Never**
- Edit below an architecture card's `<!-- AUTO-GENERATED BELOW THIS LINE`
  marker, or hand-edit `INDEX.md` / `state.yaml` / `modules.json` — all are
  generated.
- Renumber, reuse or delete a card ID — corrections supersede.
- Run `git commit` / `git add` / `git push` or any branch operation — the
  user handles all git.

## 3. Card store

| type | total | open/active |
|---|---|---|
| adr | 28 | 28 |
| fix | 326 | 33 |
| issue | 186 | 66 |
| bug | 42 | 18 |

**adr (28):**
- [ADR-0001](cards/20260727-ADR-0001.md) — That terminal frames mark the connection non-reconnecting synchronously inside the frame dispatcher
- [ADR-0021](cards/20260806-ADR-0021.md) — Authentication moved to Amazon Cognito with group-based authorization, keeping the single-bearer browser seam
- [ADR-0002](cards/20260811-ADR-0002.md) — That `workflow` is the only vocabulary the system knows and `pipeline` is removed rather than deprecated
- [ADR-0003](cards/20260811-ADR-0003.md) — The compiled plan is the single source of the roster and the assertion is deleted rather than relaxed
- [ADR-0004](cards/20260811-ADR-0004.md) — Declared order wins whenever the compiled plan carries a depends_on edge
- [ADR-0005](cards/20260811-ADR-0005.md) — The set is derived from disk once at import and template agents mark themselves with a `template: true` flag
- [ADR-0006](cards/20260811-ADR-0006.md) — Staging prunes directories not attached to the current step rather than wiping and rewriting the tree
- [ADR-0007](cards/20260811-ADR-0007.md) — The separator is a hyphen
- [ADR-0008](cards/20260811-ADR-0008.md) — The roster has three ordered sources and the plan FILLS IN rather than OVERRULES — the caller's list wins when
- [ADR-0009](cards/20260811-ADR-0009.md) — The wave surface is COMPILER-DERIVED (`Step
- [ADR-0010](cards/20260811-ADR-0010.md) — To RETIRE run-level skill attachment entirely (UI, launch payload and save payload) and make `AgentSkillsPicke
- [ADR-0011](cards/20260813-ADR-0011.md) — The delivery block's `artifact_name(instance_id, topic)` is AUTHORITATIVE and a filename written into a step p
- [ADR-0012](cards/20260813-ADR-0012.md) — The grants are FIXED (`read_files` and `write_files` always on, `exec` and `spawn_subagents` always off) and n
- [ADR-0022](cards/20260823-ADR-0022.md) — A revision request is pre-classified into a tier, and the tier selects which revision manifest runs
- [ADR-0023](cards/20260823-ADR-0023.md) — An agent declares pipeline_type as a string OR a list, so one AGENT.md can serve several pipelines
- [ADR-0013](cards/20260824-1630-ADR-0013.md) — A human gate declares WHEN it runs in its own name — `human` is post-step, `before-human` is pre-step
- [ADR-0014](cards/20260824-1630-ADR-0014.md) — A built-in workflow opens on the canvas at its own URL and can only be saved as a copy
- [ADR-0015](cards/20260824-1630-ADR-0015.md) — A conditional gate moves a mutable dispatch cursor, and a cross-workflow trigger STOPS the run rather than waiting for its child
- [ADR-0016](cards/20260824-1630-ADR-0016.md) — An unsaved composition may be launched by sending its manifest inline, compiled at trust="user"
- [ADR-0017](cards/20260824-1630-ADR-0017.md) — Route targets are authored BARE and resolved by suffix in the engine — every other consumer must normalise to the composed id itself
- [ADR-0018](cards/20260824-1631-ADR-0018.md) — Every URL in the app is built and parsed by routes.ts, and all 34 screens render behind one required catch-all segment
- [ADR-0019](cards/20260824-1631-ADR-0019.md) — Session expiry is handled by one guarded fetch wrapper, not at each call site
- [ADR-0020](cards/20260824-1831-ADR-0020.md) — Every run launch is exactly one of three LaunchSource shapes — file-based, file-based-with-DB-overrides, or DB-based
- [ADR-0024](cards/20260824-2100-ADR-0024.md) — On a 401 the REST client refreshes once first, and only treats the session as expired when that refresh fails
- [ADR-0025](cards/20260825-1115-ADR-0025.md) — The composer canvas lays out a layered DAG by Sugiyama, hand-rolled, with measured card heights
- [ADR-0026](cards/20260825-1600-ADR-0026.md) — A conditional gate publishes its declared outcomes as choices, and the human's chip click — not model prose — is what the route parses
- [ADR-0027](cards/20260825-2115-ADR-0027.md) — A user override of a built-in overlays STEPS only, never the workflow-level fields
- [ADR-0028](cards/20260826-0124-ADR-0028.md) — Never regenerate a golden while the environment that produces it is degraded

Start every card lookup at [INDEX.md](INDEX.md) — one line per card, each carrying a `compact_summary` that states the root cause or resolution. Match the query against those lines, then open only the handful of cards that matched. Never read or grep `cards/*.md` in bulk (see section 5).

## 4. Module map

- [MOD-backend](architecture/MOD-backend.md) — backend — 10 files — backend/init_db.py is a **one-shot dev-bootstrap script**: it runs every Alembic…
- [MOD-backend-agents](architecture/MOD-backend-agents.md) — backend/agents — 122 files — `backend/agents` is the execution kernel. It compiles declarative `workflow.yaml`…
- [MOD-backend-alembic](architecture/MOD-backend-alembic.md) — backend/alembic — 1 file — backend/alembic/env.py is the Alembic migration environment: it resolves the database…
- [MOD-backend-alembic-versions](architecture/MOD-backend-alembic-versions.md) — backend/alembic/versions — 38 files — The Alembic revision chain for the backend's SQLAlchemy schema — a single linear history…
- [MOD-backend-app](architecture/MOD-backend-app.md) — backend/app — 2 files — The FastAPI application entry point (main.py) — process-level wiring only: logging setup…
- [MOD-backend-app-agents](architecture/MOD-backend-app-agents.md) — backend/app/agents — 39 files — The `deepagents` runtime **adapter layer**: it turns a `create_deep_agent` LangGraph…
- [MOD-backend-app-api](architecture/MOD-backend-app-api.md) — backend/app/api — 31 files — `backend/app/api/` is the FastAPI route layer: 27 modules of thin HTTP/SSE/WebSocket…
- [MOD-backend-app-core](architecture/MOD-backend-app-core.md) — backend/app/core — 10 files — Cross-cutting security and configuration primitives with no knowledge of any specific…
- [MOD-backend-app-models](architecture/MOD-backend-app-models.md) — backend/app/models — 24 files — This module is the SQLAlchemy persistence layer: 22 ORM model files plus database.py…
- [MOD-backend-app-scripts](architecture/MOD-backend-app-scripts.md) — backend/app/scripts — 2 files — One-shot, deploy-time CLI operations run inside the backend container, outside the…
- [MOD-backend-app-services](architecture/MOD-backend-app-services.md) — backend/app/services — 5 files — Self-contained integration/export services that sit outside the pipeline agent runtime…
- [MOD-backend-evals](architecture/MOD-backend-evals.md) — backend/evals — 9 files — Prompt/agent evaluation tooling — runs real agents against a dataset, scores the output…
- [MOD-backend-scripts](architecture/MOD-backend-scripts.md) — backend/scripts — 9 files — Operator-run, one-off maintenance scripts — data migration, forensic audit, build-time…
- [MOD-frontend-src](architecture/MOD-frontend-src.md) — frontend/src — 33 files — not yet authored
- [MOD-frontend-src-app](architecture/MOD-frontend-src-app.md) — frontend/src/app — 28 files — This is the Next.js App Router tree: it owns the root HTML shell, fonts, and global…
- [MOD-frontend-src-components-analytics](architecture/MOD-frontend-src-components-analytics.md) — frontend/src/components/analytics — 6 files — Renders the Analytics page — token usage, spend, success rate, and per-pipeline/per-model…
- [MOD-frontend-src-components-catalog](architecture/MOD-frontend-src-components-catalog.md) — frontend/src/components/catalog — 4 files — The Home landing screen: a data-driven grid of launchable workflow types plus a "Jump…
- [MOD-frontend-src-components-chat](architecture/MOD-frontend-src-components-chat.md) — frontend/src/components/chat — 38 files — Renders the concierge chat lane that lives on every run screen — the message transcript…
- [MOD-frontend-src-components-handoff](architecture/MOD-frontend-src-components-handoff.md) — frontend/src/components/handoff — 8 files — Renders the `/flowin-handoff` feature: a standalone page where an IDE-launched coding…
- [MOD-frontend-src-components-history](architecture/MOD-frontend-src-components-history.md) — frontend/src/components/history — 12 files — Implements the run-history browser: the searchable/filterable list of past runs grouped…
- [MOD-frontend-src-components-home](architecture/MOD-frontend-src-components-home.md) — frontend/src/components/home — 1 file — `CreationHub` is a static list-style variant of the home "what would you like to build"…
- [MOD-frontend-src-components-layout](architecture/MOD-frontend-src-components-layout.md) — frontend/src/components/layout — 7 files — The application shell: `AppHeader` (top nav, running-pipeline badge/dropdown…
- [MOD-frontend-src-components-library](architecture/MOD-frontend-src-components-library.md) — frontend/src/components/library — 3 files — Renders the Library page — a single-file browsable/searchable catalog of the agents…
- [MOD-frontend-src-components-preview](architecture/MOD-frontend-src-components-preview.md) — frontend/src/components/preview — 18 files — Renders a run's deliverable in the Preview surface: `PreviewPanel` is the tab shell…
- [MOD-frontend-src-components-results](architecture/MOD-frontend-src-components-results.md) — frontend/src/components/results — 27 files — Implements the Results/Steps/Files/Audit surfaces mounted inside `PreviewPanel`: the…
- [MOD-frontend-src-components-savedworkflows](architecture/MOD-frontend-src-components-savedworkflows.md) — frontend/src/components/savedworkflows — 3 files — Renders "My Workflows" — the user's saved custom-agent-selection workflows, as a…
- [MOD-frontend-src-components-settings](architecture/MOD-frontend-src-components-settings.md) — frontend/src/components/settings — 4 files — Renders the Account Settings page — profile/password, AI model preference, usage & plan…
- [MOD-frontend-src-components-sidebar](architecture/MOD-frontend-src-components-sidebar.md) — frontend/src/components/sidebar — 2 files — A workflow-history sidebar (branded header, "New Project" CTA, search, date-grouped…
- [MOD-frontend-src-components-ui](architecture/MOD-frontend-src-components-ui.md) — frontend/src/components/ui — 11 files — Project-owned, token-driven visual primitives (`Button`, `Badge`, `Card`, `Pill`, `Tabs`…
- [MOD-frontend-src-components-workflow](architecture/MOD-frontend-src-components-workflow.md) — frontend/src/components/workflow — 59 files — Renders every pre-run surface for composing and launching a deliverable — the unified…
- [MOD-frontend-src-context](architecture/MOD-frontend-src-context.md) — frontend/src/context — 1 file — Holds `SkillsHooksContext`, a small React context tracking which skills and hooks (from…
- [MOD-frontend-src-hooks](architecture/MOD-frontend-src-hooks.md) — frontend/src/hooks — 32 files — React hooks layer split into two concerns: **live-run/SSE state** (transport, replay…
- [MOD-frontend-src-lib](architecture/MOD-frontend-src-lib.md) — frontend/src/lib — 46 files — The frontend's non-UI core: everything that talks to the FastAPI backend, and every piece…
- [MOD-frontend-src-providers](architecture/MOD-frontend-src-providers.md) — frontend/src/providers — 2 files — Hosts `RunConnectionProvider`, **the single app-level owner of the SSE run…
- [MOD-frontend-src-styles](architecture/MOD-frontend-src-styles.md) — frontend/src/styles — 2 files — Global CSS design tokens for the run subtree. **`globals.css` is the canonical…
- [MOD-frontend-src-types](architecture/MOD-frontend-src-types.md) — frontend/src/types — 2 files — This module is the frontend's shared TypeScript contract surface. Every domain shape the…

## 5. Retrieval protocol

**NEVER read or grep `cards/*.md` or `architecture/*.md` in bulk.** That is
951 + 36 files; it blows out the context window and buries the answer. The
index exists so you never have to. Reading whole directories is the single
worst thing you can do in this knowledge base.

Always go index-first:

1. **Read [INDEX.md](INDEX.md)** — one file, one line per card:
   `- [ID](cards/<file>.md) — <compact_summary>`. Every card's summary states
   its root cause, resolution, or mechanism, so the index alone is usually
   enough to tell which cards matter.
2. **Match the user's query against those summary lines** — semantically, not
   by exact keyword. A symptom is rarely worded the way the card is. Shortlist
   the handful of plausible IDs.
3. **Open ONLY those candidate cards**, by following the link on the matched
   line. Typically 2-5 files. If the shortlist is empty, re-read the index
   with a broader reading of the symptom before widening anything else.
4. **For architecture**, do the same: start from the module map in section 4,
   pick the ONE module that owns the behaviour, and open only that
   `MOD-*.md`. Never sweep the directory.

- **Resolve a known card ID**: glob `.knowledge/cards/*-<ID>.md`. Files are
  named `{YYYYMMDD}[-{HHMM}]-{ID}.md`, so the ID is a suffix, not a prefix.
  (Some cards are date-only — their authoring time was not recoverable.)
- **Symptom -> module**: use the index (steps 1-3), then read the matched
  card's `applies_to.modules` / `applies_to.globs` and look that module up in
  section 4. Do not grep the corpus for the glob.
- **Architecture card divider contract**: in each `MOD-*.md`, the YAML
  frontmatter and everything from the `<!-- AUTO-GENERATED BELOW THIS LINE`
  marker downward is machine-generated and rewritten by
  `tools/knowledge/build_architecture.py`; `## Purpose` / `## Shape` / `## Why this
  shape`, above that marker, are hand-authored and preserved across
  regeneration.
- **IDs are permanent.** Corrections supersede rather than edit: a new card
  is filed pointing at the old ID, whose status then changes — the old ID
  and content stay intact as a historical record.
