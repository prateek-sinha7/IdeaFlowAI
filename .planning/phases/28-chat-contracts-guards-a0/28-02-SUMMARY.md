---
phase: 28-chat-contracts-guards-a0
plan: 02
subsystem: ui
tags: [contracts, run-ui, steps, live-state, figure-pinning, d-12, chat-lane, context_sources]

# Dependency graph
requires:
  - phase: 28-chat-contracts-guards-a0 (plan 01)
    provides: chat event vocabulary + golden guards contract
provides:
  - "STEPS-ARTIFACT-DERIVATION-CONTRACT.md — four Steps-L2 kinds pinned to exact backend sources (pages<-route_table, tasks<-task_list, checks<-validation_results, construction<-task_progress + wave_*/subagent_*) with the KAN-99 N-1 checklist cap and L3 per-task shape"
  - "FIGURE-TO-FIELD-PINNING.md — every run-screen number pinned to a VERIFIED engine emit field; agent_input.context_sources name (agent_name) + size (full_output_length/summary_length) verified in code; cache/reduction % + uploaded-file rows marked UNVERIFIED"
  - "LIVE-STATE-CONTRACT.md — D-12 real-state -> chat-lane/composer/Steps four-column table with all post-merge deltas (Update the Specs, spec-revision loop-back, planner window, N-1 cap, event-driven gates)"
affects: [31-chat-lane, 32-run-redesign, RUNUI-03]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Figure-to-field pinning: every displayed UI number resolves to a named, in-code-verified backend emit field; unconfirmable figures marked UNVERIFIED, never synthesized (anti-mock-fiction, POR SC-2)"
    - "UI-SPEC contract docs transcribed verbatim from the locked POR + evidence pack (no re-derivation), with one read-only in-code field-verification step"

key-files:
  created:
    - .planning/phases/28-chat-contracts-guards-a0/contracts/STEPS-ARTIFACT-DERIVATION-CONTRACT.md
    - .planning/phases/28-chat-contracts-guards-a0/contracts/FIGURE-TO-FIELD-PINNING.md
    - .planning/phases/28-chat-contracts-guards-a0/contracts/LIVE-STATE-CONTRACT.md
  modified: []

key-decisions:
  - "context_sources carries name via agent_name and size via full_output_length/summary_length (char counts) — VERIFIED in code (engine.py:5116-5143); NO literal name/size keys, NO cache/reduction % sub-field"
  - "context_sources describes UPSTREAM AGENT OUTPUTS (produces/consumes routing), not uploaded files — the mock's file-name+byte-size+cache% rail is a semantic mismatch; cache/reduction % must come from separate P26 telemetry (marked UNVERIFIED in context_sources)"
  - "Terminology rule recorded: spec-revision loop (intra-run, KAN-101) != revision run (family child, D-02) — never conflate"

patterns-established:
  - "Pattern 1: UNVERIFIED marking — a figure whose producing field cannot be confirmed in code is explicitly flagged so the downstream FE phase chases it rather than wiring a fabricated number"

requirements-completed: [CHAT-06]

# Metrics
duration: 12min
completed: 2026-07-07
---

# Phase 28 Plan 02: Steps Artifact-Derivation, Figure-to-Field Pinning & D-12 Live-State Contract Summary

**Three UI-SPEC contract docs pinning the Steps-L2 artifact derivation (4 kinds -> exact backend sources + KAN-99 N-1 cap), every run-screen figure to a code-verified emit field (context_sources name+size verified), and the full D-12 live-state table with all five post-merge deltas — the durable inputs phases 31/32 build against.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-07-07T21:14:42Z
- **Completed:** 2026-07-07T21:27:00Z (approx)
- **Tasks:** 2
- **Files modified:** 3 created (docs only)

## Accomplishments
- **STEPS-ARTIFACT-DERIVATION-CONTRACT.md** — the four Steps-L2 kinds each pinned to their exact backend source: `pages` ← `route_table.py` (`parse_routes_table`/`resolve_route` `(pattern, page)` tuples), `tasks` ← the `task_list` typed artifact, `checks` ← `validation_results` (green status-palette exception), `construction` ← DUAL SOURCE `task_progress` (task-loop) + `wave_*`/`subagent_*` (fan-out). The KAN-99 N-1 checklist cap and the L3 per-task shape (`n, title, status, dur, thinking, tools[]`) are recorded.
- **FIGURE-TO-FIELD-PINNING.md** — evidence 07 §3's seed list completed by reading the engine emit sites: per-agent duration/tokens/cache split → `agent_complete`; run totals + cache + `estimated_cost_usd` + `model_id` + deliverable → `pipeline_complete`; construction checklist → `task_progress`; waves/workers → `wave_*`/`subagent_*`; version → `/family` `revision_index`. `agent_input.context_sources` name+size sub-fields VERIFIED in code.
- **LIVE-STATE-CONTRACT.md** — the full D-12 four-column table (real state → chat lane / composer mode / Steps behavior) for all ten states, plus the five post-merge deltas as first-class rows/notes, plus the excluded mock devices (phase scrubber) and the transcript-accumulation rule.

## Task Commits

Each task was committed atomically on `feat/ui-2`:

1. **Task 1: Steps-L2 artifact-derivation contract + figure-to-field pinning** — `51518417` (docs)
2. **Task 2: D-12 live-state contract table** — `cae7f2dd` (docs)

Both automated grep verify gates printed **OK**.

## Files Created/Modified
- `.planning/phases/28-chat-contracts-guards-a0/contracts/STEPS-ARTIFACT-DERIVATION-CONTRACT.md` — four L2 kinds → sources, KAN-99 cap, L3 shape
- `.planning/phases/28-chat-contracts-guards-a0/contracts/FIGURE-TO-FIELD-PINNING.md` — every figure → verified emit field; context_sources name+size verified; UNVERIFIED list
- `.planning/phases/28-chat-contracts-guards-a0/contracts/LIVE-STATE-CONTRACT.md` — D-12 table + five post-merge deltas + terminology rule

## Decisions Made
- **`context_sources` name+size — VERIFIED in code (with a load-bearing caveat).** The `agent_input.context_sources` entries (built at `engine.py:5116-5143`, emitted at `engine.py:2771-2778`) carry per-source sub-fields `type`, `agent_id`, `agent_name`, `summary_length`, `full_output_length`. NAME is verified as `agent_name` (no literal `name` key); SIZE is verified as `full_output_length`/`summary_length` (character counts, no literal `size` key). **Semantic caveat:** these describe upstream AGENT outputs (produces/consumes handoffs), not uploaded files, and there is NO cache/reduction % sub-field — so the mock's file-name + byte-size + cache-% "Context received" rail is a partial/semantic mismatch. The cache/reduction −% is therefore marked **UNVERIFIED** in `context_sources` and pinned to separate P26 cache telemetry (`cache_read_tokens`/`cache_write_tokens`) + compaction ratios instead.
- **Transcribed verbatim; no decision re-opened.** Per the AUTONOMOUS-RUN DECISION LOCK (yolo/skip_discuss), the docs fold POR D-12 + evidence 07/01/03 + the post-merge CORRECTIONS block without re-deriving.

## Deviations from Plan

None - plan executed exactly as written. (No source file was edited; the only code interaction was read-only field verification, as mandated.)

## Known Stubs

None. All three docs are complete prose + tables. The `UNVERIFIED` markings in `FIGURE-TO-FIELD-PINNING.md` (context-source cache/reduction −%, uploaded-file context rows, per-agent live interim token counts) are **intentional, documented gaps** for Phase 32 to chase — they are honest anti-mock-fiction flags, not incomplete work. No UI-rendering stub or hardcoded empty value was introduced (docs-only plan).

## Issues Encountered
None. The one investigation point — whether `context_sources` truly carries name+size — was resolved by reading `_build_context_sources` and the `agent_input` emit site directly; the result (verified name/size + the semantic caveat) is recorded in the pinning doc.

## Threat Flags

None. Documentation-only plan; no new network endpoint, auth path, file-access pattern, or schema change. The threat register's T-28-03 (mock-fiction regression) is mitigated exactly as planned: `context_sources` was verified in code and the unconfirmable cache-% figure is marked UNVERIFIED rather than asserted.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phases 31 (chat lane) and 32 (run redesign) now have three pinned UI-SPEC input docs to build against instead of ad-hoc mock interpretation.
- Phase 32 must resolve the three `UNVERIFIED` figures (compute cache/reduction −% from P26 telemetry; decide uploaded-file context row source pending UPLD-01/03; define the live interim token running sum).
- The spec-revision-loop vs revision-run terminology rule is recorded for the chat-lane rendering work.

## Self-Check: PASSED

- All three contract docs + SUMMARY.md exist on disk (verified).
- Both task commits (`51518417`, `cae7f2dd`) exist in git history (verified).
- No source file was edited (`git diff` on `backend/` = empty; only `.planning/` docs created).

---
*Phase: 28-chat-contracts-guards-a0*
*Completed: 2026-07-07*
