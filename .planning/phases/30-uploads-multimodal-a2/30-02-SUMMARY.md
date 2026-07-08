---
phase: 30-uploads-multimodal-a2
plan: 02
subsystem: agents
tags: [capabilities, context-provider, uploads, sticky-context, kernel-pure, import-linter, tdd]

# Dependency graph
requires:
  - phase: 30-uploads-multimodal-a2 (30-01)
    provides: "the .uploads/manifest.json + .uploads/<name>.txt sidecar contract ({name,mime,has_text}) written by RunSandbox under sandbox._UPLOADS_PREFIX"
provides:
  - "context_provider:uploaded_files — a kernel-pure ContextProvider surfacing the run's uploaded-document text as sticky agent context"
  - "registry lockstep at 66 capabilities (context_provider:uploaded_files added to _KNOWN + discover() + header + both drift guards)"
  - "end-to-end sticky-context proof: uploaded text present in EVERY agent_input for an opted-in workflow, with zero engine edits (SC-001)"
affects: [uploads, multimodal, context-providers, custom-workflows, capability-palette]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "kernel-pure context provider: @register + stdlib only; reach disk via the ctx.runner sandbox handle, never app.* (import-linter)"
    - "self-gate on the DECLARED inject token in ctx.current_spec_injects (never a workflow name / spec.id / pipeline_type) — INV-1"
    - "own-run-only disk read: no source_run_id / cross-owner accessor exists (T-30-06)"

key-files:
  created:
    - "backend/agents/capabilities/context_providers/uploaded_files.py"
    - "backend/tests/agents/test_uploaded_files_provider.py"
  modified:
    - "backend/agents/capabilities/registry.py"
    - "backend/tests/agents/test_registry_capabilities.py"
    - "backend/tests/agents/test_input_providers_run_images.py"

key-decisions:
  - "Block key is uploaded_files_context (per the plan's explicit return shape); content leads with a '## Uploaded Files' header — the engine's generic injector wraps it as an === uploaded_files_context === envelope."
  - "Reach the own-run sandbox via ctx.runner.sandbox (the RunSandbox keyed on run_id/user_id at construction) — NOT by importing/constructing RunSandbox locally, which would break kernel purity (import-linter)."
  - "SC-001 proven by asserting engine.py source carries ZERO textual reference to 'uploaded_files' — the capability is picked up purely via the existing _compose_context_message provider loop."

patterns-established:
  - "Sticky context: the provider re-reads the durable .uploads sidecar on every dispatch, so an opted-in agent sees the upload text in every agent_input (no consume-once)."
  - "Degrade-not-crash: a missing/empty/corrupt manifest or unreadable sidecar returns {} (mirrors repo.py); dormant on golden runs → INV-3 byte/event parity."

requirements-completed: [UPLD-03]

# Metrics
duration: ~8min
completed: 2026-07-08
---

# Phase 30 Plan 02: uploaded_files sticky context provider Summary

**A kernel-pure `context_provider:uploaded_files` that reads the run's own `.uploads` sidecar (staged by 30-01) and surfaces the extracted document text as sticky context in every subsequent `agent_input` for an opted-in workflow — with zero engine edits (SC-001).**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-07-08T04:23Z (first commit)
- **Completed:** 2026-07-08T04:26Z (last task commit)
- **Tasks:** 2 (Task 1 TDD: RED + GREEN)
- **Files modified:** 5 (2 created, 3 modified)

## Accomplishments
- `UploadedFilesProvider` (`name="uploaded_files"`): reads `.uploads/manifest.json` + each `<name>.txt` sidecar via the `ctx.runner` sandbox handle, composes one `uploaded_files_context` block.
- Self-gates on the `uploaded_files` inject token in `ctx.current_spec_injects` (T-30-08); own-run only, no cross-owner path (T-30-06); degrades to `{}` on any read miss.
- Registry lockstep moved 65→66 together: `_KNOWN` + `discover()` `_builtin_modules` + header comment, plus both drift-guard count asserts (`test_registry_capabilities.py` and `test_input_providers_run_images.py`) and the `_EXPECTED_NAMES` tuple.
- End-to-end sticky proof: the uploaded doc text appears in the composed context for EVERY agent of a 3-agent opted-in fixture workflow; SC-001 (zero engine reference) + INV-3 dormancy (byte-identical to baseline) proven.
- Import purity held at 4 kept / 0 broken; `engine.py` untouched (verified by `git diff`).

## Task Commits

1. **Task 1 (RED): failing tests + drift-guard bump to 66** - `24d3770e` (test)
2. **Task 1 (GREEN): kernel-pure provider + registry lockstep** - `c85246e6` (feat)
3. **Task 2: sticky proof + SC-001 + INV-3 dormancy** - `fbc10107` (test)

**Plan metadata:** (this commit) (docs: complete plan)

## Files Created/Modified
- `backend/agents/capabilities/context_providers/uploaded_files.py` - the `UploadedFilesProvider` (kernel-pure: `@register` + stdlib; reads the own-run `.uploads` sidecar via `ctx.runner`).
- `backend/agents/capabilities/registry.py` - added `(context_provider, uploaded_files)` to `_KNOWN`, the module to `discover()` `_builtin_modules`, and a header-comment line.
- `backend/tests/agents/test_uploaded_files_provider.py` - provider unit tests + the end-to-end sticky/SC-001/INV-3 proof.
- `backend/tests/agents/test_registry_capabilities.py` - `_EXPECTED_NAMES` += tuple; count assert 65→66; derivation comment updated.
- `backend/tests/agents/test_input_providers_run_images.py` - count assert 65→66 (test renamed `..._sixty_five` → `..._sixty_six`) + docstring note.

## Decisions Made
- Kept the return-block key `uploaded_files_context` (explicit in the plan's behavior spec); the generic engine injector wraps it — the plan's "=== UPLOADED FILES ===" phrasing was descriptive, and the block content leads with `## Uploaded Files` so the marker is present in the agent_input regardless.
- Replicated the `.uploads/` prefix as a local module constant rather than importing `app.agents.sandbox._UPLOADS_PREFIX` — importing it would cross the capability→app boundary the import-linter forbids.

## Deviations from Plan

None - plan executed exactly as written. The plan noted a fallback of "build `RunSandbox(ctx.user_id, ctx.run_id)` locally if no ctx accessor exists"; the `ctx.runner.sandbox` accessor DOES exist (same handle `previous_run.py`/`repo.py` use), so the own-run sandbox was reached through the handle — the import-pure path the plan's primary guidance prefers. This is the intended branch, not a deviation.

## Issues Encountered
None. RED failed for exactly the expected reasons (provider module absent + `_KNOWN` at 65≠66); GREEN passed cleanly; import-linter stayed 4/0.

## Verification (offline)
- `python3.11 -m pytest tests/agents/test_uploaded_files_provider.py tests/agents/test_registry_capabilities.py tests/agents/test_input_providers_run_images.py` → **113 passed**.
- `/opt/homebrew/bin/lint-imports` (from `backend/`) → **4 kept, 0 broken**.
- `git diff HEAD -- agents/execution_engine/engine.py` → empty (SC-001 zero-engine-edit confirmed).
- Live/Bedrock/Postgres verification: not required for this plan (kernel-pure capability + offline injector drive). No DEFERRED-to-live items.

## Threat surface
No new network endpoints, auth paths, or schema changes. The one trust boundary (own-run `.uploads` read) is closed by construction: the provider consults only `ctx.runner.sandbox` (own run) and has no cross-owner accessor — covered by `test_reads_only_own_run_sandbox_no_cross_owner_path`. No new threat flags.

## Next Phase Readiness
- UPLD-03 delivered: uploaded documents are `read_file`-able (raw bytes, 30-01) AND their extracted text is sticky context in every `agent_input` for an opted-in workflow, via a registered kernel-pure capability keyed on the declared name — zero engine edits, goldens byte-identical.
- To opt a real workflow in later: add `context_providers: [uploaded_files]` to its `workflow.yaml` + `injects: [uploaded_files]` on the consuming agents' `AGENT.md`. No kernel change required.

## Self-Check: PASSED
- `backend/agents/capabilities/context_providers/uploaded_files.py` — FOUND
- `backend/tests/agents/test_uploaded_files_provider.py` — FOUND
- commit `24d3770e` — FOUND
- commit `c85246e6` — FOUND
- commit `fbc10107` — FOUND

---
*Phase: 30-uploads-multimodal-a2*
*Completed: 2026-07-08*
