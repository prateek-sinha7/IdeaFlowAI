---
phase: 07-prototype-as-manifest-parity-proof-sc-001-2
plan: 02
subsystem: infra
tags: [capabilities, deliverable-resolver, context-provider, ports-and-adapters, move-dont-copy, ownership, opendesign]

# Dependency graph
requires:
  - phase: 07-01
    provides: "CapabilityRegistry.resolve(kind,name) + install() seam; the D-03 object-typed ctx.runner handle contract strategies/providers/resolvers call against"
  - phase: 05-typed-substrate
    provides: "agents.authz.ScopedStore.assert_owns (the L16 ownership read the previous_run provider calls before seeding)"
  - phase: 04-capability-seam
    provides: "the 6 Protocol ports (base.py) incl. DeliverableResolver + ContextProvider; the _KNOWN membership set"
provides:
  - "SingleFileResolver (deliverable/single_file) — folds the prototype build + revision branches by deliverable.name, no workflow-name branch"
  - "SerializedSandboxResolver (deliverable/serialized_sandbox) — the code-gen filename:-block bundle behind a count>0 guard"
  - "StreamedTextResolver (deliverable/streamed_text) — _unwrap_artifact(last_streamed)"
  - "PptResolver (deliverable/ppt) — owns BOTH carousel-sanitize behaviors + artifact-unwrap (PARITY-07)"
  - "OpenDesignProvider (context_provider/opendesign) — composes the L12 {block-name -> content} map from the boundary od_context dict + handle (Assumption A6)"
  - "PreviousRunProvider (context_provider/previous_run) — assert_owns-before-seed parent spec/design/tasks, propagating PermissionError (INV-8/L16)"
  - "The 3 prototype OD loaders relocated to agents/execution_engine/od_context.py (their single new home, move-don't-copy)"
affects: [07-03-compaction-validators-gates, 07-04-engine-wiring, 07-05-leak-deletion]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Deliverable resolution by deliverable.name/strategy (INV-1) — never by workflow name; the engine's _resolve_final_output chooser decomposed into 4 port-satisfying capabilities"
    - "Capability heavy-dep reach via the boundary od_context dict + the ctx.runner handle (Assumption A6) — keeps capabilities import-pure under the import-linter contract while the app.* loaders live one layer out"
    - "Ownership-gate-before-side-effect: assert_owns is called BEFORE any parent seed; the cross-owner PermissionError propagates, never swallowed (L16 ratchet)"

key-files:
  created:
    - backend/agents/capabilities/deliverables/__init__.py
    - backend/agents/capabilities/deliverables/_artifact.py
    - backend/agents/capabilities/deliverables/single_file.py
    - backend/agents/capabilities/deliverables/serialized_sandbox.py
    - backend/agents/capabilities/deliverables/streamed_text.py
    - backend/agents/capabilities/deliverables/ppt.py
    - backend/agents/capabilities/context_providers/__init__.py
    - backend/agents/capabilities/context_providers/opendesign.py
    - backend/agents/capabilities/context_providers/previous_run.py
    - backend/tests/agents/test_deliverable_resolvers.py
    - backend/tests/agents/test_context_providers.py
  modified:
    - backend/agents/capabilities/registry.py
    - backend/agents/execution_engine/od_context.py
    - backend/agents/prototype/context.py
    - backend/agents/execution_engine/engine.py

key-decisions:
  - "Relocation target for the 3 OD loaders is agents/execution_engine/od_context.py (NOT inside the capability) — putting app.services.od_loader-importing code inside agents.capabilities would break the import-linter contract 'capabilities must not import app'. od_context.py already imports od_loader and is the boundary builder, so it is the natural single home that satisfies move-don't-copy (INV-12) AND the hexagonal boundary."
  - "OpenDesignProvider.load(ctx) composes blocks FROM the pre-built od_context dict + handle helpers (template_injection_parts / template_example) — Assumption A6 — so the capability imports no app.*; the kernel backs those handle helpers with the relocated loaders in 07-04."
  - "previous_run reaches the parent files + current sandbox through the ctx.runner handle (read_parent_file / sandbox.write) and the store via ctx.scoped_store — no app.* import; the engine's RunSandbox(disk_principal, parent_run_id) construction becomes a handle method in 07-04."
  - "Shared _artifact.py hosts _unwrap_artifact + _sanitize_carousel_deck_html (verbatim engine lift) so streamed_text + ppt share one byte-identical impl."

patterns-established:
  - "Deliverable resolvers + context providers satisfy their ports structurally (name attr + method); name == registry key == manifest reference; bound via registry.install()"
  - "Move-don't-copy completeness is grep-proven: 0 remaining defs/imports of the relocated symbols outside the new home, 0 agents.prototype.context references in src"

requirements-completed: [PARITY-02, PARITY-03, PARITY-07]

# Metrics
duration: ~30min
completed: 2026-06-08
---

# Phase 7 Plan 02: Deliverable Resolvers + Context Providers Summary

**The four DeliverableResolver families (single_file/serialized_sandbox/streamed_text/ppt) and the two ContextProvider families (opendesign/previous_run) built behind their ports — decomposing the engine's _resolve_final_output chooser and the L12 od-injection / L4 revision-seed leaks into declared capabilities, with the 3 prototype OD loaders physically relocated (move-don't-copy) and all importers rewired, zero kernel/app imports.**

## Performance

- **Duration:** ~30 min
- **Started:** 2026-06-08
- **Completed:** 2026-06-08
- **Tasks:** 2
- **Files modified:** 15 (11 created, 4 modified)

## Accomplishments
- Decomposed `engine._resolve_final_output` (engine.py:447-528) into 4 `DeliverableResolver` capabilities that resolve by `deliverable.name`/`deliverable.strategy` — **no `pipeline_type` branch** (INV-1). `single_file` folds the prototype build + revision branches into one name-keyed resolver with the stream → seeded-original fallback chain; `serialized_sandbox` keeps the `filename:`-block UI contract behind the `count > 0` guard; `streamed_text`/`ppt` share a lifted `_unwrap_artifact`; `ppt` owns BOTH carousel-sanitize behaviors (final-output engine.py:1394 + mid-stream engine.py:1916) so 07-05 can delete both kernel call sites (PARITY-07).
- Built the `opendesign` + `previous_run` providers behind the `ContextProvider` port. `opendesign.load(ctx)` reproduces the L12 block-name keys (`ACTIVE DESIGN SYSTEM: <id>`, `ACTIVE TEMPLATE (SKILL.md): <id>`, `TEMPLATE EXAMPLE (example.html): <id>`, + the injection-part blocks) in declared order, composed from the boundary `od_context` dict + the handle (Assumption A6). `previous_run.load(ctx)` calls `ScopedStore.assert_owns` BEFORE seeding the parent spec/design/tasks and lets a cross-owner `PermissionError` propagate (INV-8 / L16).
- **Move-don't-copy relocation (INV-12):** physically moved `load_prototype_context`/`get_template_injection_parts`/`get_example_html` from `agents/prototype/context.py` into `agents/execution_engine/od_context.py` (single new home — emptied the old defs), keeping `load_ppt_od_context` + the `load_prototype_od_context` alias intact. Rewired all 4 importers (`engine.py:3373/3384/3508` repointed; the WS/NDJSON boundary re-resolves through od_context's own defs).
- 21 new Wave-0 unit tests (12 deliverable + 9 context-provider) incl. the ppt byte-for-byte engine-transform parity check, the move-don't-copy relocation assertions, and the cross-owner `PermissionError` propagation.

## Task Commits

Each task was committed atomically:

1. **Task 1: Deliverable resolvers (single_file/serialized_sandbox/streamed_text/ppt)** — `d677944` (feat)
2. **Task 2: opendesign + previous_run providers (move-don't-copy + ownership seed)** — `fda337d` (feat)

**Plan metadata:** _(this commit)_

## Files Created/Modified
- `backend/agents/capabilities/deliverables/{__init__,_artifact,single_file,serialized_sandbox,streamed_text,ppt}.py` — the 4 resolvers + the shared transform helper.
- `backend/agents/capabilities/context_providers/{__init__,opendesign,previous_run}.py` — the 2 providers.
- `backend/agents/capabilities/registry.py` — bound the 4 deliverables + 2 providers into `install()`.
- `backend/agents/execution_engine/od_context.py` — RELOCATED the 3 prototype loaders here (their new single home) alongside `load_ppt_od_context`.
- `backend/agents/prototype/context.py` — emptied of the 3 relocated defs (package removal is 07-05).
- `backend/agents/execution_engine/engine.py` — rewired the 3 `get_template_injection_parts`/`get_example_html` importers to `od_context`.
- `backend/tests/agents/test_deliverable_resolvers.py`, `backend/tests/agents/test_context_providers.py` — 21 Wave-0 unit tests.

## Decisions Made
- See `key-decisions` frontmatter. The load-bearing one: the relocation target is `od_context.py` (a kernel-package module that legitimately imports `app.services.od_loader`), NOT the capability module — because the import-linter contract forbids `agents.capabilities` from importing `app`. This satisfies BOTH the move-don't-copy mandate (single home, old emptied) and the hexagonal boundary; the capability composes its blocks via the boundary dict + handle (Assumption A6, anticipated by the plan's Heavy-dep note).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Reworded `pipeline_type` docstring/comment prose to satisfy the literal grep gate**
- **Found during:** Task 1
- **Issue:** The acceptance grep `grep -nE "pipeline_type" deliverables/*.py` must return 0, but the resolver docstrings *described* the INV-1 rule ("no `pipeline_type` branch"), false-tripping the literal-token gate exactly as 07-01 documented for its own gates.
- **Fix:** Reworded the docstrings/comments to say "no workflow-name branch" (and "today gated on the prototype/PPT workflow names") — same meaning, no literal token. The code never branched on `pipeline_type`.
- **Files modified:** all 5 `deliverables/*.py` docstrings.
- **Verification:** `grep -nE "pipeline_type" deliverables/*.py` exit 1 (0 matches); all 12 deliverable tests pass.
- **Committed in:** `d677944`.

### Interpretation note (not a deviation)

The plan's action text says relocate the 3 loaders "into this [opendesign] module". Doing so literally would import `app.services.od_loader` from inside `agents.capabilities`, breaking the standing import-linter contract (verified green at baseline). The plan's own **Heavy-dep note** + **Assumption A6** + the **threat register T-07-02-03** explicitly sanction the alternative: ride the heavy reads through the boundary `od_context` dict so the capability imports no `app.*`. I therefore relocated the loaders to `agents/execution_engine/od_context.py` (the boundary's own loader module, the single new home — satisfying INV-12) and kept `OpenDesignProvider` import-pure. This honors the explicit constraint ("all capabilities reach kernel/app.* primitives ONLY through the ctx.runner handle"; "capability may [not] import the kernel or app.* directly") which takes precedence over the example wording.

**Total deviations:** 1 auto-fixed (1 blocking, cosmetic).
**Impact on plan:** No behavioral change; no scope creep.

## Issues Encountered
- `tests/unit/` shows the 8 KNOWN pre-existing failures (7× `test_logout.py` JWT/JTI, 1× `test_pipeline_cancel.py`) — confirmed unrelated to this plan (it touches only `agents/capabilities/**`, `agents/execution_engine/od_context.py`, the 3 engine importer lines, and `agents/prototype/context.py`). Not fixed per the SCOPE BOUNDARY rule; no NEW unit failures introduced.

## Known Stubs
- `OpenDesignProvider` reaches the template seed/reference parts + example.html through the handle methods `template_injection_parts` / `template_example`, and `PreviousRunProvider` reaches the parent files through `read_parent_file` — these handle methods are part of the D-03 `KernelServices` shape whose concrete class lands in 07-04 (the engine attaches the real handle then). Intentional and parity-safe (the providers are exercised against a fake handle this plan). Resolved by: 07-04.
- No leak deleted and engine not yet rewired to use the new capabilities (by design — 07-04 wires, 07-05 deletes). L1–L13 stay live; the relocation is byte-preserving (0A characterization green).

## Threat Flags
None — no new security surface beyond the plan's `<threat_model>`. The one high-risk surface (cross-owner parent-run read) is gated by the propagating `assert_owns` and re-confirmed green by `test_parent_run_ownership.py`.

## User Setup Required
None.

## Next Phase Readiness
- 07-03 registers compaction/validators/gates into `install()` and reaches kernel primitives via `ctx.runner` (the same seam used here).
- 07-04 implements the concrete `KernelServices` class — it must back `template_injection_parts(template_id)`, `template_example(template_id)`, `read_parent_file(parent_run_id, name)`, `serialize_sandbox_deliverable(root)`, `count_sandbox_deliverables(root)` (the handle surface these capabilities call against) — and attach the deliverable resolvers + context providers via `resolve(...)` instead of the legacy `_resolve_final_output` / L12 injection / L4 seed paths.
- 07-05 deletes the now-superseded engine leaks (`_resolve_final_output`, both carousel-sanitize call sites, the L4 revision-seed block, the L12 od-injection branches) and removes the emptied `agents/prototype/` package.

## Self-Check: PASSED

All 11 created files exist on disk; both task commits (`d677944`, `fda337d`) exist in git history.

---
*Phase: 07-prototype-as-manifest-parity-proof-sc-001-2*
*Completed: 2026-06-08*
