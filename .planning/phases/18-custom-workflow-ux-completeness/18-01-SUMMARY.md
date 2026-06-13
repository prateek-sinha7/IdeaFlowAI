---
phase: 18-custom-workflow-ux-completeness
plan: 01
subsystem: engine
tags: [deliverable, mimetype, pipeline_complete, characterization, inv-3, sc-001, capabilities]

requires:
  - phase: 07-deliverable-resolvers
    provides: the four DeliverableResolver capabilities (single_file/serialized_sandbox/streamed_text/ppt) + ectx.deliverable binding
  - phase: 13-degraded-completion
    provides: the conditional degraded pipeline_complete keys + the _VOLATILE_STRIP_KEYS precedent (model_id/estimated_cost_usd)
provides:
  - "DeliverableSpec.mimetype optional declared shape hint (manifest -> compiled plan)"
  - "per-resolver default mimetype helper (declared-shape-driven, import-pure)"
  - "deliverable_mimetype + deliverable_filename emitted on EVERY pipeline_complete"
  - "both new keys in _VOLATILE_STRIP_KEYS — INV-3 parity seam for the FE renderer (18-03)"
affects: [18-03 generic FE deliverable renderer, FE pipeline_complete consumers]

tech-stack:
  added: []
  patterns:
    - "Declared deliverable shape hint: the manifest DECLARES strategy/name; the mimetype is derived from the declaration, never content-sniffed (SC-001)"
    - "Additive-but-parity-neutral pipeline_complete keys live in _VOLATILE_STRIP_KEYS (mirrors model_id/estimated_cost_usd)"

key-files:
  created:
    - backend/agents/capabilities/deliverables/_mimetype.py
    - backend/tests/unit/test_deliverable_mimetype.py
  modified:
    - backend/agents/workflows/plan.py
    - backend/agents/workflows/compiler.py
    - backend/agents/capabilities/deliverables/single_file.py
    - backend/agents/capabilities/deliverables/streamed_text.py
    - backend/agents/capabilities/deliverables/serialized_sandbox.py
    - backend/agents/capabilities/deliverables/ppt.py
    - backend/agents/execution_engine/engine.py
    - backend/tests/agents/characterization/_normalize.py

key-decisions:
  - "mimetype derived from the DECLARED strategy/name, never from the bytes (rejected the content-sniff hack startswith('<!doctype'))"
  - "compiler is a thin pass-through (mimetype=raw.get('mimetype')); the per-resolver default is computed at EMISSION time, not in the compiler (INV-5)"
  - "engine prefers the author-declared mimetype, else the per-resolver default; both keys are UNCONDITIONAL (clean + degraded), placed beside final_output"
  - "INV-3 neutralization via _VOLATILE_STRIP_KEYS (not _REQUIRED_DATA_KEYS, which is a subset check) keeps the 5 goldens byte-identical"

patterns-established:
  - "Type-driven deliverable contract: a declared mimetype hint the FE dispatches on with zero per-workflow code (SC-001)"

requirements-completed: [ISS-021]

duration: 14 min
completed: 2026-06-13
---

# Phase 18 Plan 01: ISS-021 Backend — Type-Driven Deliverable Contract Summary

**Adds a DECLARED, resolver-defaulted `DeliverableSpec.mimetype` and emits `deliverable_mimetype`/`deliverable_filename` on every `pipeline_complete` (sourced from `ectx.deliverable`), neutralized in `_VOLATILE_STRIP_KEYS` so the 5 characterization goldens stay byte-identical.**

## Performance

- **Duration:** 14 min
- **Started:** 2026-06-13T15:04Z
- **Completed:** 2026-06-13T15:19Z
- **Tasks:** 2
- **Files modified:** 8 (2 created, 6 modified)

## Accomplishments

- `DeliverableSpec.mimetype: str | None = None` — an optional, author-declared deliverable shape hint; the compiler `_compile_deliverable` passes it through verbatim (no defaulting — INV-5).
- A new import-pure `_mimetype.default_mimetype(strategy, name)` helper + a `default_mimetype` staticmethod on each of the four resolvers: `single_file` infers from the declared name extension (`.html`/`.htm`→`text/html`, `.md`→`text/markdown`, unknown/none→`application/octet-stream`); `serialized_sandbox`→`application/zip`; `streamed_text`→`text/markdown`; `ppt`→`text/html`.
- `pipeline_complete` now carries two UNCONDITIONAL keys beside `final_output`, sourced ONLY from the already-resolved `ectx.deliverable` (no new plumbing, no cross-boundary import).
- INV-3 parity proven: both keys added to `_VOLATILE_STRIP_KEYS`; the 5 characterization goldens remain byte-identical with NO `SNAPSHOT_UPDATE`.

## Task Commits

1. **Task 1: Declare DeliverableSpec.mimetype + compiler pass-through + per-resolver defaults** — `e9bfae82` (feat)
2. **Task 2: Emit deliverable_mimetype + deliverable_filename on pipeline_complete + INV-3 _VOLATILE_STRIP_KEYS guard** — `2a607e57` (feat)

_TDD: the unit test file was authored RED-first (import-error RED), then driven GREEN across both tasks; the engine-emission + strip-membership assertions landed with Task 2's commit so each commit is green._

## The exact resolved-mimetype source expression (engine.py)

```python
from agents.capabilities.deliverables._mimetype import default_mimetype as _default_mimetype
_deliverable_name = getattr(ectx.deliverable, "name", None)
_deliverable_mimetype = getattr(ectx.deliverable, "mimetype", None) or (
    _default_mimetype(_deliverable_strategy, _deliverable_name)
)
# ... in _pipeline_complete_data, beside final_output:
"deliverable_mimetype": _deliverable_mimetype,
"deliverable_filename": _deliverable_name,
```

`_deliverable_strategy` (`= compiled.deliverable.strategy or "streamed_text"`) and `final_output` are both assigned unconditionally on the linear path just above the emission dict, so the keys ride every clean AND degraded `pipeline_complete`.

## The two `_VOLATILE_STRIP_KEYS` additions

Added to the frozenset in `backend/tests/agents/characterization/_normalize.py` (mirroring the `model_id`/`estimated_cost_usd` precedent), with a comment noting they are additive-but-parity-neutral, metadata-only (deliverable BYTES unchanged), and not in `_REQUIRED_DATA_KEYS`:

```python
"deliverable_mimetype",
"deliverable_filename",
```

## Files Created/Modified

- `backend/agents/capabilities/deliverables/_mimetype.py` — import-pure declared-shape→mimetype helper (no `app.*`, no content sniff).
- `backend/agents/workflows/plan.py` — `DeliverableSpec.mimetype` optional field.
- `backend/agents/workflows/compiler.py` — `_compile_deliverable` thin pass-through `mimetype=raw.get("mimetype")`.
- `backend/agents/capabilities/deliverables/{single_file,streamed_text,serialized_sandbox,ppt}.py` — `default_mimetype` staticmethod per resolver.
- `backend/agents/execution_engine/engine.py` — emit `deliverable_mimetype`/`deliverable_filename` on `pipeline_complete`.
- `backend/tests/agents/characterization/_normalize.py` — both keys in `_VOLATILE_STRIP_KEYS`.
- `backend/tests/unit/test_deliverable_mimetype.py` — 17 tests: compiler round-trip/None-default/extra-key tolerance, per-resolver defaults, strip-membership, scripted-run emission (prototype→`text/html`/`prototype.html`; od_ppt mimetype never null).

## INV-3 / Verification Evidence (PROVEN, not hand-waved)

- `python3.11 -m pytest tests/unit/test_deliverable_mimetype.py tests/agents/test_characterization_{prototype,od_prototype,prototype_revision,od_ppt,app_builder}.py -q` → **27 passed** in 41.37s. The 5 goldens were asserted with NO `SNAPSHOT_UPDATE` (default run = real byte-identity assertion).
- `/opt/homebrew/bin/lint-imports` → **Contracts: 4 kept, 0 broken.**
- Zero new tables/migrations: no `alembic/` changes; `git diff` carries no `op.create_table`/`op.add_column`. Deliverable bytes are unchanged (metadata-only addition).

## Decisions Made

See `key-decisions` frontmatter. Headline: the mimetype is a deterministic function of the DECLARED `strategy`/`name` (SC-001) — the rejected content-sniff hack was not used.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- The plan's `<read_first>` referenced `WorkflowManifest`/`DeliverableSpec` as if both lived in `plan.py`; `WorkflowManifest` actually lives in `agents/workflows/manifest.py` and requires `id/steps/deliverable/planner/clarify`. The test's manifest factory was adjusted accordingly (a test-construction detail, not a behavior change). No impact on the production change.

## Self-Check: PASSED

- `backend/agents/capabilities/deliverables/_mimetype.py` — FOUND
- `backend/tests/unit/test_deliverable_mimetype.py` — FOUND
- Commit `e9bfae82` — FOUND
- Commit `2a607e57` — FOUND

## Next Phase Readiness

The backend half of ISS-021 is complete and INV-3-clean. `pipeline_complete` now carries the type-driven contract `18-03` (the generic FE mimetype-dispatched renderer) dispatches on. No blockers.

---
*Phase: 18-custom-workflow-ux-completeness*
*Completed: 2026-06-13*
