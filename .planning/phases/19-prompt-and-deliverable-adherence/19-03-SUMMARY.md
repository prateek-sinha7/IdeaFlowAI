---
phase: 19-prompt-and-deliverable-adherence
plan: 03
subsystem: engine
tags: [agent-chunk, sanitizer, tool-xml, deepagents, streaming, sc-001, inv-3]

# Dependency graph
requires:
  - phase: 13-prototype-validation
    provides: "_strip_fabricated_tool_xml + DeepAgentRunner.sanitize_output (the 13-02 fabricated-tool-XML sanitizer reused here)"
  - phase: 15-live-pass-prompt-contract-closure
    provides: "P15 prompt fix that defused the sdlc-governance tool-XML trigger (this plan adds the deterministic backstop)"
provides:
  - "Streamed agent_chunk path sanitized for tool-less agents — fabricated <function_calls>/<invoke XML is stripped from the LIVE UI stream (not just the accumulated output)"
  - "_ChunkStreamSanitizer: a per-agent-stream chunk-straddle buffer that holds an unterminated tool-XML opener across chunk-delta boundaries and flushes on close / at stream end"
  - "A behavioral probe gating buffering only for tool-less runners (tool-using streams byte-AND-chunk-identical)"
  - "Fault-injection test driving split-across-deltas tool-XML through the real engine stream loop"
affects: [live-bedrock-playwright-pass, engine, deep_agent_runner]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Chunk-straddle streaming buffer: hold from an unterminated opener token to its close/stream-end so a span split across two deltas is still sanitized"
    - "Behavioral capability probe (feed a known fabricated-XML probe to sanitize_output once) to gate work on a runner capability without a workflow/agent-name branch (SC-001)"
    - "Authoritative-vs-streamed split: accumulate the RAW chunk for the post-loop authoritative sanitize (INV-3 byte-parity) while sanitizing only the YIELDED chunk"

key-files:
  created:
    - backend/tests/agents/test_chunk_sanitizer.py
  modified:
    - backend/agents/execution_engine/engine.py

key-decisions:
  - "Reuse the runner's existing _strip_fabricated_tool_xml via the duck-typed sanitize_output — no second/divergent stripping regex (single sanitization locus; T-19-03-01 over-stripping mitigation)"
  - "Probe-gate the buffer on the runner capability (strip a fabricated-XML probe once at construction) so a tool-using stream is byte-AND-chunk-identical, not merely join-identical — SC-001 behavioral gate, no agent-name literal"
  - "Keep the authoritative output_chunks path RAW (unchanged) so the post-loop sanitize_output keeps the 5 goldens byte-identical (INV-3)"
  - "Detect the unterminated/partial-opener hold point by token scan (opener present without its matching close, or a trailing proper-prefix of an opener token) — the stripping itself stays delegated to the runner"

patterns-established:
  - "Chunk-straddle buffer: _hold_from_index() finds the earliest open/partial tool-XML span; feed() yields the sanitized prefix and holds the raw tail; flush() strips a never-closed opener at EOF"
  - "Probe-gated no-op: behavioral detection of an active sanitizer keeps the fast path verbatim for tool-using agents"

requirements-completed: [ISS-004]

# Metrics
duration: 9min
completed: 2026-06-13
---

# Phase 19 Plan 03: ISS-004 — Streamed agent_chunk Tool-XML Sanitizer Summary

**The engine now strips fabricated `<function_calls>`/`<invoke>` tool-XML from the LIVE streamed `agent_chunk` events of tool-less agents — reusing the 13-02 `_strip_fabricated_tool_xml` via a per-stream chunk-straddle buffer that catches a span split across two chunk deltas — while tool-using streams pass through byte-and-chunk-identical.**

## Performance

- **Duration:** 9 min
- **Started:** 2026-06-13T16:54:14Z
- **Completed:** 2026-06-13T17:03:37Z
- **Tasks:** 2 (both `tdd="true"`)
- **Files modified:** 2 (1 engine edit + 1 new test)

## Accomplishments
- Closed ISS-004's deterministic backstop: fabricated tool-XML a tool-less Haiku agent emits as plain text no longer reaches the live UI stream / durable-replay collector / reconnect tail — it was previously stripped only from the accumulated authoritative output (the chunk yield fired BEFORE sanitization).
- Implemented `_ChunkStreamSanitizer` with a span-straddle buffer: it holds an unterminated `<function_calls>`/`<invoke` opener (including a partial opener TOKEN split mid-tag, e.g. `…<inv` | `oke …`) until its close arrives in a later chunk, and flushes a never-closed opener at stream end (mirrors the runner's WR-01 `_UNTERMINATED_TOOL_XML_RE`) so legitimate trailing content is never swallowed.
- Wired it at the engine `agent_chunk` yield (gated on the generic tool-less runner capability — SC-001) with the authoritative `output_chunks` path left RAW so the goldens stay byte-identical.
- Added a split-across-deltas fault-injection test driving the real engine `_run_agent` stream loop end-to-end offline.

## Task Commits

Each task was committed atomically (hooks on, no `--no-verify`):

1. **Task 1: tool-less chunk sanitizer + span-straddle buffer at the agent_chunk yield** — `21f4d571` (feat)
2. **Task 2: split-chunk fault-injection test (+ probe-gating refinement for the tool-using untouched contract)** — `0a901b41` (test)

_Note: this `type: tdd` plan's RED was the standalone buffer logic + the fault-injection cases; GREEN was the engine implementation verified against them + the 5 byte-goldens. The probe-gating refinement landed with Task 2 because it is what proves the tool-using "untouched" assertion (same chunks, same boundaries)._

## Files Created/Modified
- `backend/agents/execution_engine/engine.py` — Added module-level `_ChunkStreamSanitizer` (+ `_TOOL_XML_OPENERS` / `_TOOL_XML_CLOSE_FOR`); construct the buffer per retry-attempt from the runner's duck-typed `sanitize_output`; route the YIELDED `agent_chunk` through `feed()` (suppressing empty deltas) and flush the held tail at clean stream end. Authoritative `output_chunks.append` left RAW.
- `backend/tests/agents/test_chunk_sanitizer.py` — Fault-injection driving `execute()` single-agent pipelines with a `ScriptedFakeChatModel` that splits `<function_calls>` across two deltas: tool-less (`domain-analyst`) → no `<function_calls>`/`<invoke` in the emitted stream, legit content on both sides preserved; tool-using (`prototype-revision-agent`) → emitted chunks byte+chunk-identical; single-chunk span stripped; clean stream byte-identical.

## Decisions Made
- **Single sanitization function, no divergent regex.** The actual stripping is delegated to the runner's `sanitize_output` (the 13-02 `_strip_fabricated_tool_xml`); the engine only token-scans to find WHERE to hold an open/partial span. This satisfies T-19-03-01 (no over-stripping via a second regex) and keeps one backend locus.
- **Probe-gate the buffer, don't just rely on identity.** A first implementation let the buffer re-chunk even tool-using streams (join-identical but boundaries shifted). Feeding a fabricated-XML probe to `sanitize_output` once at construction detects an active (tool-less) sanitizer; an inactive (tool-using / no-capability) one bypasses buffering entirely → same chunks, same boundaries. The gate is purely behavioral (no agent name) — SC-001.
- **Authoritative path untouched** so the post-loop `sanitize_output` still produces the byte-identical golden `final_output`/`output_length` (INV-3).
- **Fresh buffer per retry-attempt** so a model-fallback re-stream never inherits a held tail from the throttled prior attempt.

## Deviations from Plan

None - plan executed exactly as written.

The probe-gating addition is not a deviation from scope: the plan's must-have ("a tool-USING agent's identical stream is untouched — same chunks pass through verbatim") explicitly requires per-chunk identity, and the probe is the mechanism that delivers it while staying SC-001-clean. It is documented as a decision above.

## Issues Encountered
- The initial single-agent harness for the tool-USING case used `app-code-generator`, whose non-empty `consumes` made the one-agent DAG unsatisfiable (the run errored before streaming → zero `agent_chunk` events). Resolved by selecting `prototype-revision-agent` (tools: workspace, `consumes: []`), which drives as a satisfiable single-agent pipeline offline.
- The initial buffer used "sanitized remainder still contains an opener" to detect an unterminated span, but the runner's `_UNTERMINATED_TOOL_XML_RE` strips an open opener to empty, masking the open state and dropping the held tail. Resolved by detecting the hold point via a token scan for an opener-without-matching-close (plus a trailing partial-opener-token prefix), independent of the sanitizer's output.

## Verification

- `python3.11 -m pytest tests/agents/test_chunk_sanitizer.py -q` → 4 passed (split-across-deltas tool-less stripped; tool-using untouched byte+chunk-identical; single-chunk stripped; clean stream no-op).
- `python3.11 -m pytest tests/agents/test_characterization_{app_builder,prototype,prototype_revision,od_prototype,od_ppt}.py -q` → 10 passed, **byte/event-identical, NO SNAPSHOT_UPDATE** (INV-3 held).
- `python3.11 -m pytest tests/agents/test_phase3_cutover_verify.py -q` → 6 passed (no stream-contract regression).
- `/opt/homebrew/bin/lint-imports` → **4 kept / 0 broken**.
- SC-001 grep over the engine sanitizer region → **no `sdlc-governance` / `app_builder` / `prototype-` / `domain-analyst` literal** in the gate.
- `git status` → only the 2 declared files touched; **zero migrations; no FE file changed**.

## Deferred
- **LIVE re-confirm on `default` Bedrock:** a real Haiku sdlc-governance run (app_builder + dotnet + mulesoft) showing 0 fabricated tool-XML in the live UI chunk stream. Per the locked CONTEXT decision (and the defer-live-verification memory note), this runs in the consolidated live + Playwright pass — NOT a phase-exit blocker (the split-chunk fault-injection + golden parity are the gate).

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- **Phase 19 (Prompt & Deliverable Adherence) is COMPLETE** — all 3 plans closed: 19-01 (ISS-006 shared DB-accessor prompt contract), 19-02 (ISS-005 `api_prefix` event-free post_step validator), 19-03 (ISS-004 streamed chunk sanitizer).
- Cluster D (the three prompt/deliverable-adherence residuals) is closed offline with deterministic structural backstops. The only remaining item is the consolidated LIVE Bedrock + Playwright re-confirm pass for ISS-004/005/006.

## Self-Check: PASSED

- `backend/agents/execution_engine/engine.py` — present (modified).
- `backend/tests/agents/test_chunk_sanitizer.py` — present (created).
- `.planning/phases/19-prompt-and-deliverable-adherence/19-03-SUMMARY.md` — present.
- Commit `21f4d571` (feat task 1) — found in git log.
- Commit `0a901b41` (test task 2) — found in git log.

---
*Phase: 19-prompt-and-deliverable-adherence*
*Completed: 2026-06-13*
