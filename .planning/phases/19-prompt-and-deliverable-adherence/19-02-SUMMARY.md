---
phase: 19-prompt-and-deliverable-adherence
plan: 02
subsystem: testing
tags: [validator, capability-registry, post_step, api_prefix, app_builder, INV-3, ISS-005]

# Dependency graph
requires:
  - phase: 08-capability-kernel
    provides: "the CapabilityRegistry (_KNOWN / discover() / resolve()), the Validator port + spec_plan_coverage template, the single map_severity source, record_validation_result handle"
  - phase: 07-kernel-extraction
    provides: "the event-free post_step seam (engine.py:~1720) + the revision_validation post_step precedent"
provides:
  - "A pure-stdlib api_prefix Validator capability that deterministically flags infra endpoints missing /api/v1 and writes a validation_results audit row"
  - "An event-free api_prefix_audit post_step wired on the app_builder infra-generator step (side-effects only, NO events) — the INV-3-safe enforcement of ISS-005"
  - "Both registry surfaces (the _KNOWN compiler-membership literal AND discover()'s _builtin_modules runtime-binding tuple) updated together so resolve() returns an instance at runtime, not raise"
affects: [app_builder, capability-registry, future-infra-validators]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Deterministic deliverable-contract enforcement as a registered Validator + event-free post_step (the durable replacement for prose-only AGENT.md rules)"
    - "Two-surface registry registration discipline: _KNOWN literal (compiler is_registered) AND discover()'s _builtin_modules (runtime @register -> _IMPLS binding) must move together"

key-files:
  created:
    - backend/agents/capabilities/validators/api_prefix.py
    - backend/agents/capabilities/post_steps/api_prefix_audit.py
    - backend/tests/agents/test_api_prefix_validator.py
  modified:
    - backend/agents/capabilities/registry.py
    - backend/agents/workflows/app_builder/workflow.yaml
    - backend/tests/agents/test_registry_capabilities.py

key-decisions:
  - "Wire api_prefix as an EVENT-FREE post_step (api_prefix_audit), NOT a gates:[validation] gate — the validation gate emits a validation_warning event the 85-event app_builder golden has no slot for, so a gate would break INV-3. Proven both directions (event-free golden byte-identical; gate-wiring fault-injection emits the warning)."
  - "Register on BOTH registry surfaces together: the _KNOWN literal (compiler membership) AND discover()'s _builtin_modules import tuple (runtime @register -> _IMPLS). Updating only _KNOWN compiles but raises RuntimeError at the engine post_step seam — the latent blocker the revised plan called out. A post-discover resolve()-returns-instance test proves _IMPLS is bound."
  - "Single API_PREFIX = '/api/v1' module constant (SC-001): the validator keys on infra-file content + the declared capability, never a workflow/agent-name literal."

patterns-established:
  - "Pure-stdlib kernel-side Validator modeled verbatim on spec_plan_coverage (Issue dataclass, map_severity single source, _record/_worst_label helpers, await target.runner.record_validation_result) — import-pure, degrade-not-crash, sandbox-confined."
  - "Event-free post_step shim modeled on revision_validation: resolves a sibling capability via the registry, builds a tiny DeliverableContext-shaped target from ctx, side-effects only, wrapped in try/except that never aborts the run."

requirements-completed: [ISS-005]

# Metrics
duration: 23 min
completed: 2026-06-13
---

# Phase 19 Plan 02: api_prefix Infra Validator + Event-Free post_step (ISS-005) Summary

**A pure-stdlib `api_prefix` Validator wired as an EVENT-FREE `api_prefix_audit` post_step on the app_builder infra-generator step — deterministically flagging infra endpoints missing `/api/v1` and writing a `validation_results` audit row, with the 85-event app_builder golden staying byte-identical and a gate-wiring fault-injection proving why event-free is load-bearing.**

## Performance

- **Duration:** ~23 min
- **Started:** 2026-06-13T16:27Z (approx)
- **Completed:** 2026-06-13T16:50:42Z
- **Tasks:** 2
- **Files modified:** 6 (3 created, 3 modified)

## Accomplishments

- New `api_prefix` Validator (`backend/agents/capabilities/validators/api_prefix.py`): globs the run sandbox for infra files (`Dockerfile*`, `*.yml`/`*.yaml`, nginx `*.conf`, `.github/workflows/*`), regex-flags app endpoints not under the single `API_PREFIX = "/api/v1"` constant (curl/healthcheck URLs + nginx `location` blocks), emits one P2 `Issue` per violation, writes a `validation_results` row via `target.runner.record_validation_result` (best-effort). Pure-stdlib, import-pure, sandbox-confined, degrade-not-crash.
- New event-free `api_prefix_audit` post_step (`backend/agents/capabilities/post_steps/api_prefix_audit.py`) mirroring `revision_validation`: resolves the `api_prefix` validator, builds a tiny target from `ctx`, runs it side-effects-only, emits NO events, never raises.
- BOTH registry surfaces updated together in `registry.py`: the two `(kind,name)` pairs in the `_KNOWN` literal (compiler `is_registered`) AND both module paths in `discover()`'s `_builtin_modules` tuple (runtime `@register` → `_IMPLS` binding) — so `resolve("post_step","api_prefix_audit")` and `resolve("validator","api_prefix")` each return an instance at runtime, not raise.
- `app_builder/workflow.yaml`: `post_step: api_prefix_audit` declared on the `app-infra-generator` step (no `gates:`/`validators:` — the REJECTED hack).
- Drift guard bumped: `_EXPECTED_NAMES` += both pairs; `len(_KNOWN)` 61 → 63.
- INV-3 proven: all 5 characterization goldens byte/event-identical (app_builder unchanged); gate-wiring fault-injection emits the `validation_warning` event (golden would FAIL); lint-imports 4/0; zero migrations.

## Task Commits

1. **Task 1: pure-stdlib `api_prefix` Validator (+ unit tests)** — `a9a90cd7` (feat)
2. **Task 2: event-free post_step + both registry surfaces + manifest wiring + drift-guard bump + INV-3 fault-injection** — `5ee40626` (feat)

_Both tasks committed atomically with pre-commit hooks ON (ruff + pyright); never `--no-verify`._

## Files Created/Modified

- `backend/agents/capabilities/validators/api_prefix.py` — the Validator (globber + regex scan + P2 Issue + record helper, single `/api/v1` constant).
- `backend/agents/capabilities/post_steps/api_prefix_audit.py` — the event-free post_step shim.
- `backend/agents/capabilities/registry.py` — both surfaces (`_KNOWN` literal + `discover()` `_builtin_modules`) + header comments.
- `backend/agents/workflows/app_builder/workflow.yaml` — `post_step: api_prefix_audit` on the infra-generator step.
- `backend/tests/agents/test_api_prefix_validator.py` — validator behaviors + the post-discover resolve()-returns-instance guard + the gate-wiring INV-3 fault-injection.
- `backend/tests/agents/test_registry_capabilities.py` — drift guard (`_EXPECTED_NAMES` += both pairs; count 61 → 63).

## Verification Results

- `pytest tests/agents/test_api_prefix_validator.py tests/agents/test_registry_capabilities.py` → **94 passed** (validator behaviors, resolve()-returns-instance for both pairs, gate fault-injection emits validation_warning, drift guard at 63).
- `pytest` the 5 characterization goldens (app_builder/prototype/od_prototype/prototype_revision/od_ppt) WITHOUT `SNAPSHOT_UPDATE` → **10 passed** — byte/event-identical; the event-free post_step + DB-row audit do not perturb any golden.
- Compile check: `compile_for_run('app_builder')` resolves `post_step = api_prefix_audit`; `resolve()` returns `ApiPrefixAuditPostStep` + `ApiPrefixValidator` instances; `is_user_allowed("validator","api_prefix") == True`.
- `lint-imports` (/opt/homebrew/bin/lint-imports) → **4 kept / 0 broken** (validator + shim import-pure).
- SC-001 grep over the validator (non-comment) → **0** workflow/agent-name literals.
- `git status` → no new migration file; only the 6 declared files changed.

## Decisions Made

See `key-decisions` frontmatter: event-free post_step over the validation gate (INV-3 load-bearing); both registry surfaces together (closes the latent runtime-raise blocker); single `/api/v1` constant (SC-001).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Dropped the unused `Validator` port import (F401 vs. pre-commit ruff hook)**
- **Found during:** Task 1 (validator module)
- **Issue:** The `spec_plan_coverage` template imports `from agents.capabilities.base import Validator` purely as a documented port marker (it uses structural typing, never references the symbol) — this raises ruff F401. The repo now runs ruff as a **blocking, no-`--fix`** pre-commit hook, so a verbatim copy would be uncommittable.
- **Fix:** Removed the unused import; the port is documented in the module docstring and registration is structural (the same pattern the precedent's class uses). No behavior change.
- **Files modified:** backend/agents/capabilities/validators/api_prefix.py
- **Verification:** `ruff check` clean; validator behaviors green; lint-imports 4/0.
- **Committed in:** a9a90cd7 (Task 1 commit)

**2. [Rule 1 - Bug] Tightened the endpoint regex so the scheme separator `//` is never captured as a path**
- **Found during:** Task 1 (validator behavior tests, RED→GREEN)
- **Issue:** The first-draft curl/healthcheck regexes captured `//localhost` (the `//` after `http:`) as the endpoint path, producing false-positive P2 issues on a clean `/api/v1/health` target.
- **Fix:** Collapsed to a single `https?://[^/\s]+(/path)` URL regex (host segment consumes `host:port`, capture begins at the first `/` of the URL path) + the nginx `location` regex. Linear single-pass (no catastrophic backtracking, T-19-02-02).
- **Files modified:** backend/agents/capabilities/validators/api_prefix.py
- **Verification:** violation fixture → 1 P2; clean `/api/v1` fixture → 0 issues.
- **Committed in:** a9a90cd7 (Task 1 commit)

**3. [Rule 3 - Doc] Reworded SC-001 prose to drop the literal `app_builder`/`app-infra-generator` tokens from the validator module**
- **Found during:** Task 1 (SC-001 acceptance grep)
- **Issue:** The acceptance grep `grep -v '^#' … | grep -cE 'app_builder|app-infra-generator'` counted docstring/comment mentions (prose, not code branching) → returned 2.
- **Fix:** Reworded the three prose lines to "infra-generator" / "workflow-id or agent-id literal" so the validator carries zero such tokens. No code/behavior change — SC-001 was never violated (the validator keys on infra-file content + the declared capability).
- **Files modified:** backend/agents/capabilities/validators/api_prefix.py
- **Verification:** SC-001 grep → 0.
- **Committed in:** a9a90cd7 (Task 1 commit)

---

**Total deviations:** 3 auto-fixed (1 blocking-hook adaptation, 1 regex bug, 1 doc/SC-001 grep). **Impact:** All necessary for correctness + committability; no scope creep; no behavior change beyond the validator's own correctness.

## Issues Encountered

**Pre-existing, out-of-scope test failure (NOT introduced by this plan):** `tests/agents/test_phase5_revision_validation.py::TestEventVocabularyUnchanged::test_event_types_subset_of_documented_vocabulary` fails (the `prototype_revision` fix-loop run emits an undocumented `gate_blocked` event in the offline harness). Proven pre-existing by re-running with the 19-02 changes stashed (still FAILED). It touches `prototype_revision` + the documented event vocabulary — none of which this plan changes. Logged to `.planning/phases/19-prompt-and-deliverable-adherence/deferred-items.md`; not fixed here per the scope boundary.

## Deferred

- LIVE re-confirm on `default` Bedrock: a real Haiku app_builder (+ dotnet + mulesoft) run showing the infra-generator output's `/api/v1` count non-zero AND the post_step writing a clean `validation_results` row with zero P2 issues. Runs in the consolidated live + Playwright pass (per memory: defer live verification to milestone-end). The offline fault-injection + golden parity are the phase-exit gate.

## Next Phase Readiness

- 19-02 (ISS-005) complete. Phase 19 remaining: 19-03 (ISS-004 — engine streamed-`agent_chunk` sanitizer with chunk-straddle buffer). Ready for 19-03.

---
*Phase: 19-prompt-and-deliverable-adherence*
*Completed: 2026-06-13*

## Self-Check: PASSED

- `backend/agents/capabilities/validators/api_prefix.py` — FOUND
- `backend/agents/capabilities/post_steps/api_prefix_audit.py` — FOUND
- `backend/tests/agents/test_api_prefix_validator.py` — FOUND
- registry.py / workflow.yaml / test_registry_capabilities.py — modified + committed
- Commit `a9a90cd7` — FOUND; Commit `5ee40626` — FOUND
- 94 unit tests + 10 characterization goldens green; lint-imports 4/0; zero migrations
