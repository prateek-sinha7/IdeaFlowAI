## Phase 19 — Prompt and Deliverable Adherence (post-milestone)

**Folder:** `.planning/phases/19-prompt-and-deliverable-adherence/`  ·  **Status:** Complete (2026-06-13) — gsd-verifier PASS, 4/4 must-haves, 0 overrides  ·  **Plans:** 3/3  ·  **Plan-id → §25:** (post-milestone — no source-plan id, like Phases 13–18)
**Requirements delivered:** none new — closes **cluster D** of the 2026-06-13 deep root-cause investigation (`ISS-006` / `ISS-005` / `ISS-004`) with **durable STRUCTURAL** fixes; subsumes the earlier F4/F5 live-verification residuals (ISS-004/005) + the app_builder cross-agent drift (ISS-006). Phase 15 had only added the prompt-only contracts; Phase 19 adds the deterministic backstops. → see `.planning/ROADMAP.md` "### Phase 19" + `.planning/ISSUES-REGISTER.md` "Deep Root-Cause Investigation" (cluster D) rows ISS-004/005/006.
**One-line outcome:** Three non-deterministic-model residuals get code-level guards — a shared `getDatabase` accessor literal threaded across the app_builder producer/consumer prompts (+ grep pin), a pure-stdlib `api_prefix` Validator wired as an **event-free `post_step`** on the infra step, and the existing tool-XML sanitizer extended to the **streamed `agent_chunk`** path with chunk-straddle buffering — all three landed with the 5 characterization goldens byte/event-identical.

### 1. Goal & Success Criteria (what was PLANNED)

Cluster D = the three prompt/deliverable-adherence residuals. The phase boundary (`19-CONTEXT.md` → "Phase Boundary") is explicit: close them with **DURABLE structural fixes, NOT prompt-only "ask the model nicely"**, so a non-deterministic model can't silently regress them. Depends on **Phase 18**.

Four success criteria (`ROADMAP.md` "### Phase 19"):
1. **ISS-006** — the app_builder producer (`app-code-generator`) + consumer (`app-test-implementation`) AGENT.md bodies share a single canonical `getDatabase` accessor literal (incl. the Jest/Vitest global-setup file `tests/setup.ts`/`globalSetup`), pinned by an offline acceptance-grep; reverting either side fails the pin. INV-3-safe (scripted model ignores prompt bodies).
2. **ISS-005** — a pure-stdlib `api_prefix` `Validator` capability (modeled on `spec_plan_coverage.py`) exists, self-registers, and is wired as an **event-free `post_step`** on the app_builder infra-generator step — flagging infra endpoints lacking `/api/v1` and writing a `validation_results` row, **WITHOUT adding any event to the run** (so the app_builder golden stays byte-identical). Import-pure (lint-imports 4/0).
3. **ISS-004** — the engine sanitizes the streamed `agent_chunk` path (reusing `_strip_fabricated_tool_xml`, with a chunk-straddle buffer) for tool-less agents, so fabricated `<function_calls>`/`<invoke>` XML is removed from the live UI stream, not just the accumulated output. SC-001: keys on the generic tool-less condition, never a workflow name.
4. **INV-3 parity** — the 5 characterization goldens stay byte/event-identical; lint-imports 4/0; zero new tables/migrations. The live re-confirms (004/005/006) are recorded as next-live-pass items, not phase blockers.

### 2. What Was Implemented — per plan (BUILT)

| Plan | Issue | Built | Key files | Commits |
|------|-------|-------|-----------|---------|
| **19-01** | ISS-006 | Threaded the canonical named-export literal `getDatabase` through both prompt bodies (producer states a MANDATORY DB ACCESSOR CONTRACT: single NAMED export `getDatabase`, never default/`getDb`, at `src/db/index.ts`; consumer's Contract-fidelity rule extended to explicitly cover the Jest/Vitest global-setup file). Added offline acceptance-grep pin `test_getdatabase_accessor_contract_shared` asserting on `load_agent_spec(id).prompt_body` for both agents; fault-injected both revert directions. Body-only edits — frontmatter untouched. | `app-code-generator/AGENT.md`, `app-test-implementation/AGENT.md`, `tests/agents/test_prompt_contracts.py` | `58f2ae09`, `d98cc421` |
| **19-02** | ISS-005 | New pure-stdlib `api_prefix` Validator (clone of `spec_plan_coverage.py`): globs the run sandbox for infra files (`Dockerfile*`, `*.yml`/`*.yaml`, nginx `*.conf`, `.github/workflows/*`), regex-flags app endpoints not under the single `API_PREFIX = "/api/v1"` constant, emits one P2 `Issue` per violation, writes a `validation_results` row via `target.runner.record_validation_result`. New event-free `api_prefix_audit` post_step (mirrors `revision_validation.py`) wired on the `app-infra-generator` step (`gates: []`, no validation gate). Registered on **both** registry surfaces; drift guard bumped (`_EXPECTED_NAMES` += 2 pairs, `len(_KNOWN)` 61 → 63). Gate-wiring fault-injection proves the validation gate would emit `validation_warning` and break the golden. | `validators/api_prefix.py`, `post_steps/api_prefix_audit.py`, `capabilities/registry.py`, `app_builder/workflow.yaml`, `tests/agents/test_registry_capabilities.py`, `tests/agents/test_api_prefix_validator.py` | `a9a90cd7`, `5ee40626` |
| **19-03** | ISS-004 | Added module-level `_ChunkStreamSanitizer` to `engine.py` (+ `_TOOL_XML_OPENERS`/`_TOOL_XML_CLOSE_FOR`): a per-stream chunk-straddle buffer that holds an unterminated `<function_calls>`/`<invoke` opener (incl. a partial opener token split mid-tag) until its close arrives in a later chunk, and flushes a never-closed opener at stream end. Wired at the `agent_chunk` yield, **probe-gated** on the tool-less runner capability (feed a fabricated-XML probe to `sanitize_output` once → detects an active sanitizer; tool-using streams bypass entirely → byte-AND-chunk-identical). Authoritative `output_chunks` path left RAW so the post-loop `sanitize_output` keeps the golden `final_output`/`output_length`. Split-across-deltas fault-injection test driving the real engine `_run_agent` loop offline. | `engine.py`, `tests/agents/test_chunk_sanitizer.py` | `21f4d571`, `0a901b41` |

### 3. Capabilities, Modules, Schema & API Added

**New capability — `api_prefix` Validator** (`backend/agents/capabilities/validators/api_prefix.py`): pure-stdlib, registered `@register("validator", "api_prefix", user_allowed=True)`. Modeled verbatim on `spec_plan_coverage.py` (`Issue` dataclass, single `map_severity` source, `_worst_label`/`_SEVERITY_ORDER`/`_record` helpers, `await target.runner.record_validation_result`). Single module constant `API_PREFIX = "/api/v1"`. Import-pure (no `app.*`/`execution_engine` import), sandbox-confined, degrade-not-crash.

**New post_step — `api_prefix_audit`** (`backend/agents/capabilities/post_steps/api_prefix_audit.py`): registered `@register("post_step", "api_prefix_audit")`, mirrors `revision_validation.py` — resolves the `api_prefix` validator via the registry, builds a tiny `DeliverableContext`-shaped target from `ctx`, runs it side-effects-only, **emits NO events**, wrapped in try/except that never aborts the run.

**Two-surface registration** (`registry.py`): both `(kind,name)` pairs added to the `_KNOWN` literal (compiler `is_registered` membership) AND both module paths added to `discover()`'s `_builtin_modules` import tuple (runtime `@register` → `_IMPLS` binding). `_KNOWN` count is now **63** (was 61); the drift guard's `_EXPECTED_NAMES` mirror in `test_registry_capabilities.py` was updated in lockstep. The post_step invocation seam is `engine.py:1889-1891` (`_run_step`).

**Manifest wiring** (`app_builder/workflow.yaml`): `post_step: api_prefix_audit` on the `app-infra-generator` step with `gates: []` — NOT a `gates:[validation]` gate.

**Streamed-chunk sanitizer reuse** (`engine.py`): `_ChunkStreamSanitizer` delegates the actual stripping to the existing runner `sanitize_output` / `_strip_fabricated_tool_xml` (13-02) — no second/divergent regex; it only token-scans to find WHERE to hold an open/partial span.

**Shared accessor literal** (`getDatabase`): a prompt-contract literal threaded across the two app_builder AGENT.md bodies (13-03 shared-literal pattern), pinned by the offline grep.

**Schema:** **ZERO new tables / migrations.** The `validation_results` table already exists; the validator writes an audit row into it. No DB rows are golden-tracked.

### 4. What Was Deleted / Superseded (INV-12)

Largely **additive** — no engine subsystem was removed. The structural substance is **supersession of the Phase-15 prompt-only contracts with enforced structural backstops**, stated explicitly:
- ISS-005's prose-only `/api/v1` rule (3 AGENT.md bodies, zero code enforcement) is now backed by the deterministic `api_prefix` validator — the prompt remains, but it is no longer the sole enforcement mechanism.
- ISS-004's accumulated-output-only sanitization (`sanitize_output()` post-loop) is extended to the streamed path — the single sanitization locus now covers the live UI stream + durable-replay collector + reconnect tail, closing the gap the prior design left intentionally unfiltered.
- ISS-006's model-invented accessor name on each side is replaced by one shared canonical literal.
- Minor in-phase cleanup during the review-fix pass: dead/duplicate branches and an unused `Issue.validator` field were removed from `api_prefix.py` (IN-01/IN-02).

### 5. Key Decisions & Locked Constraints (do NOT contradict)

- **The `api_prefix` enforcement is an EVENT-FREE `post_step`, NOT a `gates:[validation]` gate.** This is the load-bearing INV-3 decision. The `validation` gate emits a `validation_warning` event when residual issues exist; the 85-event app_builder golden has no such slot → a gate breaks parity. Proven both directions: event-free → golden byte-identical; the in-test gate-wiring fault-injection emits the warning (golden would FAIL). **Do not "promote" this validator to a gate on the golden pipeline.**
- **The chunk sanitizer is a same-object no-op on clean text** and **probe-gated on the tool-less runner capability** — a tool-using agent's stream is byte-AND-chunk-identical (not merely join-identical). The authoritative `output_chunks` path stays RAW so the post-loop `sanitize_output` keeps the golden output. **Do not double-strip into the authoritative path; do not strip in the FE; do not add a second/divergent regex.**
- **WR-01 hold-threshold:** the partial-opener hold only fires on a trailing prefix of length ≥ 2 (`range(len-1, 1, -1)`), so a lone `<` — common in legit tool-less prose (HTML/JSX, `a < b`) — is never buffered and chunk granularity is preserved.
- **SC-001 keying:** the validator keys on infra-file content + the declared capability; the chunk sanitizer keys on the generic tool-less probe; the prompt literal is a shared contract. **No workflow/agent-name (`app_builder`, `sdlc-governance`, `app-infra-generator`, `prototype-`) branch in the kernel** (grep gate = 0; the sole `app_builder` token in the engine is an INV-3 rationale comment, not a branch).
- **INV-3:** the 5 characterization goldens (prototype/od_prototype/prototype_revision/od_ppt/app_builder) stay byte/event-identical. Three independent guards: (006) scripted model never reads prompt bodies; (005) the post_step is event-free + DB rows aren't golden-tracked; (004) goldens normalize `agent_chunk.chunk` to a sentinel + pin only post-sanitized `final_output`/`output_length`.
- **Import purity:** validator + post_step shim are pure-stdlib; `lint-imports` stays **4 kept / 0 broken**.
- **Additive only:** zero new tables/migrations (`validation_results` pre-exists).
- **Two-surface registration discipline:** a capability in `_KNOWN` but absent from `discover()`'s `_builtin_modules` compiles but raises `RuntimeError("known but has no bound impl")` at the runtime post_step seam. Both surfaces moved together; a post-discover `resolve()`-returns-instance test pins `_IMPLS` is bound.

### 6. Status, Verification & Evidence (what HAPPENED)

**Verdict (`19-VERIFICATION.md`):** PASSED — 4/4 must-haves verified, 0 overrides, independently confirmed by reading source + running the targeted offline suite + executing registry-resolve / validator / chunk-sanitizer behaviors directly. No gaps. The two-surface registration (historical latent blocker) is closed and proven at runtime.

**Evidence:**
- Phase-19 four test files: **117 passed** (`test_chunk_sanitizer` 7, `test_api_prefix_validator` 12, `test_registry_capabilities` 86, `test_prompt_contracts` 12).
- 5 characterization goldens: **10 passed**, NO `SNAPSHOT_UPDATE` (byte/event-identical — INV-3 held even with `engine.py` + the validator both touched).
- `/opt/homebrew/bin/lint-imports`: **4 kept / 0 broken**.
- Behavioral spot-checks: validator violation → 1 P2; external URL → 0 (WR-02); bare-path healthcheck → 1 (WR-03); clean `/api/v1` → 0; empty sandbox → 0 (no crash). Chunk sanitizer: split-XML stripped; tool-using stream byte+chunk-identical; lone-`<`/`<div>`/`a < b` at boundaries chunk-identical; benign held tail flushed verbatim.
- Zero new migrations (`validation_results` pre-exists).

**Review → fix arc (`19-REVIEW.md` → `19-REVIEW-FIX.md`):** standard review found **0 critical / 4 warning / 5 info**; all 8 in-scope (WR-01..04 + IN-01..04) fixed in iteration 1 (IN-05 was a doc-only "confirm intent" note, no action). Notable fixes: **WR-02** constrained the URL regex to app-local hosts (dotless host token) so external package/registry/release URLs no longer pollute audit rows; **WR-03** added the bare-path healthcheck regex the docstring advertised; **WR-04** added flush-tail data-loss pins (benign tail survives; never-closed opener stripped). Post-fix combined set: **127 passed**, goldens still byte/event-identical, lint 4/0. Fix commits `1baeb3c0` (WR-01), `b0627909` (WR-04), `e43ce55c` (WR-02), `18c761c2` (WR-03), `22de51a6` (IN-01..04).

### 7. Gotchas, Survivors & Carry-Forward

- **Goldens live in `tests/agents/test_characterization_*.py` (5 files), NOT a `tests/agents/characterization` collectable path** — the latter collects 0 items. Run the 5 files explicitly without `SNAPSHOT_UPDATE`.
- **Pre-existing, out-of-scope failure** (`deferred-items.md`): `test_phase5_revision_validation.py::TestEventVocabularyUnchanged::test_event_types_subset_of_documented_vocabulary` — `prototype_revision` (fix-loop) emits an undocumented `gate_blocked` event in the offline harness. Proven pre-existing (fails with 19-02 changes stashed); untouched by this phase. Candidate for a focused debug pass (likely an offline-DB/FK interaction).
- **DEFERRED live re-confirms (004/005/006)** on the now-active `default` Bedrock profile, recorded in each plan's `<deferred>` block — NOT phase-exit blockers (offline grep pin / fault-injection / golden parity are the gates). **Carry-forward status (per `ISSUES-REGISTER.md` line 79, CAMPAIGN-2026-06-13-phases16-19):** the consolidated live + Playwright pass on `default` has since **live+visually confirmed ISS-005 and ISS-006**; **ISS-004 remains offline-proven only** (sdlc-governance didn't reach in the app_builder window — its chunk-sanitizer fault-injection is deterministic, so no product defect surfaced).
- **ISSUES-REGISTER now records all three as FIXED:** ISS-006 → FIXED (19-01, live re-confirm done), ISS-005 → FIXED (19-02, structural, live-confirmed), ISS-004 → FIXED (19-03, structural; live re-confirm pending). All are **structural (not prompt-only)** closures.
- **N3/v2 follow-ups (out of scope here):** a `tsc --noEmit`/`code_typecheck`/`symbol_contract` validator for ISS-006 (needs exec + a TS toolchain).

### 8. File Index (every file in this folder)

| File | What it is |
|------|------------|
| `19-CONTEXT.md` | Locked cluster-D decisions (no discuss round); the 3 LOCKED fixes + REJECTED hacks + INV-3/SC-001 rationale + canonical refs (file:line) + deferred ideas. |
| `19-01-PLAN.md` | ISS-006: shared `getDatabase` accessor literal across producer + consumer prompts + offline grep pin (2 tasks). |
| `19-01-SUMMARY.md` | ISS-006 outcome: both bodies carry the literal; pin green; both revert directions fault-injected; goldens byte-identical; lint 4/0; 0 migrations. |
| `19-02-PLAN.md` | ISS-005: pure-stdlib `api_prefix` validator + event-free `api_prefix_audit` post_step; the two-surface registration rule; the gate-wiring fault-injection (2 tasks). |
| `19-02-SUMMARY.md` | ISS-005 outcome: validator + post_step + both registry surfaces + manifest wiring; drift guard 61→63; 94 unit + 10 golden tests green; 3 auto-fixed deviations (F401, regex bug, SC-001 prose). |
| `19-03-PLAN.md` | ISS-004: engine streamed-`agent_chunk` sanitizer reusing `_strip_fabricated_tool_xml` with a chunk-straddle buffer; split-chunk fault-injection (2 tasks). |
| `19-03-SUMMARY.md` | ISS-004 outcome: `_ChunkStreamSanitizer` probe-gated buffer; authoritative path RAW; 4 fault-injection cases green; goldens byte-identical; declares Phase 19 COMPLETE. |
| `19-REVIEW.md` | Standard code review: 0 critical / 4 warning / 5 info; deepest scrutiny on the live-stream sanitizer (span-straddle, false-positive prose, flush, probe gate, per-stream isolation). |
| `19-REVIEW-FIX.md` | Fix report: all 8 in-scope findings fixed iteration 1 (WR-01 lone-`<`; WR-02 app-local hosts; WR-03 bare-path healthcheck; WR-04 flush pins; IN-01..04); INV-3 re-proven; 127 passed. |
| `19-VERIFICATION.md` | gsd-verifier PASS, 4/4 truths verified, all artifacts + key links + behavioral spot-checks confirmed; live re-confirms recorded as deferred (not gaps). |
| `deferred-items.md` | The pre-existing, out-of-scope `test_phase5_revision_validation` `gate_blocked` failure (proven pre-existing by stashing 19-02). |
| `.gitkeep` | Empty placeholder. |
