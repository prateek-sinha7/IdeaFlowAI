# Phase 19: Prompt & Deliverable Adherence - Context

**Gathered:** 2026-06-13
**Status:** Ready for planning
**Source:** Locked decisions from the 2026-06-13 deep root-cause investigation (cluster D). Findings + proper (no-hack) fixes are in `.planning/ISSUES-REGISTER.md` → "Deep Root-Cause Investigation". Code-proven file:line. No discuss round.

<domain>
## Phase Boundary

Close cluster D — the three prompt/deliverable-adherence residuals — with DURABLE structural fixes (not prompt-only "ask the model nicely"), so a non-deterministic model can't silently regress them. The P15 prompt fixes for ISS-004/005 shipped already; this phase adds the structural backstops + the ISS-006 contract.

1. **ISS-006** (minor, product) — app_builder cross-agent contract drift: `tests/setup.ts` imports `getDb`, impl exports `getDatabase` (TS2305).
2. **ISS-005** (minor, product) — `app-infra-generator` ignored its own `/api/v1` rule live (P15 repositioned the prompt; add a deterministic validator).
3. **ISS-004** (minor, product) — sdlc-governance family fabricates tool-XML in the live UI stream (P15 defused the prompt trigger; add the stream sanitizer — the deterministic backstop).

IN SCOPE: prompt bodies (`backend/agents/prompts/app-code-generator/AGENT.md`, `app-test-implementation/AGENT.md`); a new pure-stdlib validator capability + an event-free `post_step` shim (`backend/agents/capabilities/validators/api_prefix.py` + the shim) wired on the app_builder infra step manifest; the engine `agent_chunk` sanitizer (`backend/agents/execution_engine/engine.py` ~:2330-2332) reusing the existing `_strip_fabricated_tool_xml`; offline pins (grep + fault-injection); the `_VOLATILE_STRIP_KEYS`/normalizer is NOT touched (no new event).

OUT OF SCOPE: the LIVE re-confirms of ISS-004/005/006 (run in the consolidated live + Playwright pass on `default` — acct 473293451041); a `tsc --noEmit`/`code_typecheck` validator for ISS-006 (N3-gated — needs exec + a TS toolchain; the prompt contract is the proportionate fix now); a `symbol_contract` validator (N3/v2 follow-up); clusters A/B/C/E (done in Phases 16-18).

</domain>

<decisions>
## Implementation Decisions (LOCKED — proven file:line)

### ISS-006 — shared canonical DB-accessor literal across producer + consumer prompts [LOCKED]
- **Root cause:** prompt-contract gap. Producer `app-code-generator` (registry.py order 8, `tools:[workspace]`) emits the DB module exporting `getDatabase`; consumer `app-test-implementation` (order 12, `tools:[workspace]`) emits `tests/setup.ts` importing `getDb`. No shared source of truth for the accessor name, AND `app-test-implementation`'s contract-fidelity rule (AGENT.md:34-52) is scoped to per-story domain symbols and excludes the Jest global-setup file. Symbols are model-invented (grep `getDb|getDatabase|setup.ts` over prompts + golden = 0).
- **Fix (13-03 shared-literal pattern, body-only AGENT.md edits + grep pin):**
  1. `app-code-generator/AGENT.md`: add a one-line export contract — the DB connection module MUST expose the accessor as a single canonical NAMED export `getDatabase` (never a default export), at a canonical path (e.g. `src/db/index.ts`).
  2. `app-test-implementation/AGENT.md`: extend "Contract fidelity" to explicitly cover test-infrastructure files — the Jest/Vitest global setup (`tests/setup.ts` / configured `globalSetup`) MUST import the DB accessor by the EXACT canonical named export the impl emits (`getDatabase`), quoted from context; never invent `getDb`/`getConnection`.
  3. (optional) name the same literal in `app-feature-implementation`/`app-test-compliance` so it's the single source of truth across all four touchpoints.
  4. Offline acceptance-grep pin (extend the Phase-15 `test_prompt_contracts.py` / `test_manifest_parity`-style placement): assert both producer + consumer bodies contain the canonical literal + the global-setup contract line; reverting either side FAILS the pin.
- **REJECTED hacks:** rename one side only (the other re-drifts); build a `tsc --noEmit`/`code_typecheck` gate NOW (TS + exec OFF until N3 + would add a gate to the golden pipeline). The type-check validator is a worthwhile N3-era follow-up; the proportionate fix now is the shared prompt contract + grep pin.
- **INV-3:** app_builder is a characterization pipeline, but the scripted model NEVER reads prompt bodies (`_scripted_model.py` drives goldens from `_scripts_for`; `app-code-generator` hardcoded to write `src/app.py`+`README.md`; `app-test-implementation` in TEXT_ONLY) + the event normalizer reduces chunk text — a body edit CANNOT perturb either golden. Run the characterization suite to PROVE it.

### ISS-005 — `api_prefix` deliverable-validator as an event-free post_step [LOCKED]
- **Root cause:** the `/api/v1` standard lives ONLY as prose in 3 AGENT.md bodies — ZERO code enforcement (`grep /api/v1 *.py` = 0). infra-generator's rule is incidental to its 12-file templating task → lost on live Haiku. P15 repositioned the contract (shipped + offline-pinned), but a prompt is a flaky enforcement mechanism.
- **Fix (durable, no-hack):** add `backend/agents/capabilities/validators/api_prefix.py` — a pure-stdlib `Validator` modeled VERBATIM on `backend/agents/capabilities/validators/spec_plan_coverage.py`: `@register("validator","api_prefix",user_allowed=True)`, `async def validate(self, target)`. It globs the run sandbox for infra files (`Dockerfile*`, `*.yml`/`*.yaml`, nginx `*.conf`, `.github/workflows/*`), regex-scans for app-endpoint references NOT under `/api/v1` (healthcheck paths, nginx `location`, smoke `curl`), emits a P2 `Issue` per violation, maps severity via the single `map_severity` import, writes a `validation_results` audit row via `target.runner.record_validation_result` (the `_record` helper, copied as-is). No exec, no `app.*` import.
- **Wiring (THE INV-3-CRITICAL DECISION):** wire it as an **event-free `post_step`** (mirror `revision_validation.py`), declared `post_step: api_prefix_audit` on the app_builder infra-generator step in `backend/agents/workflows/app_builder/workflow.yaml`. The engine invokes declared `post_step` at `engine.py:1666-1668` — side-effects only, NO yielded events — so the run's event stream is untouched and the `app_builder.events.json` golden stays byte-identical. Make the single `/api/v1` literal a real constant in the validator module.
- **REJECTED hacks:** declare `gates:[validation]` + `validators:[api_prefix]` (the `validation` gate emits a `validation_warning` event when residual issues exist → the 85-event app_builder golden has NO such event → **breaks INV-3**); prompt-only as the permanent answer (flaky).
- **INV-3:** SAFE iff wired event-free. The `validation_results` DB row is NOT golden-tracked (goldens capture events + the serialized_sandbox deliverable text, not DB rows). Run the 5 goldens to prove byte-identity; fault-inject by mis-wiring it as a gate and confirming the golden FAILS (proves WHY event-free is required).

### ISS-004 — sanitize the streamed agent_chunk path for tool-less agents [LOCKED]
- **Root cause:** the 13-02 sanitizer (`_strip_fabricated_tool_xml`, `deep_agent_runner.py:129-151`) is applied to the authoritative output (the done event + the engine's chunk-joined output via `sanitize_output()` at `engine.py:2480-2492`), but the engine YIELDS each raw `chunk` as an `agent_chunk` event at `engine.py:2330-2332` BEFORE accumulation/sanitization. So fabricated `<function_calls>`/`<invoke name="read_file">` reaches the live UI stream (downstream context + the persisted deliverable + `final_output` are already clean). It's UI-stream-cosmetic, but user-visible. P15 defused the prompt TRIGGER (sdlc-governance bodies); this is the deterministic belt.
- **Fix:** route each chunk through the runner's existing sanitizer before yielding the `agent_chunk` (`engine.py:~2330-2332`), gated on the agent being tool-less (the generic condition the fabrication arises under — NOT a workflow name). CRITICAL subtlety — **span-straddle:** `<function_calls>…</function_calls>` can split across two chunk deltas, so a naive per-chunk regex misses it. Use a small streaming buffer: hold a chunk's tail when an unterminated `<function_calls>`/`<invoke` opener is seen, flush on close or at stream end. Reuse `_strip_fabricated_tool_xml` (it returns the SAME object when the pattern is absent → no-op on clean chunks).
- **REJECTED hacks:** strip the XML in the FE (duplicates a backend concern; leaves the durable-replay collector + reconnect tail exposed; violates the single-sanitization-locus); rely solely on the prompt fix (non-deterministic).
- **INV-3:** the 5 characterization goldens normalize chunk text (`_normalize.py` reduces `agent_chunk.chunk` to a sentinel) + only `output_length`/`final_output` are pinned (both already post-loop-sanitized) → the streamed-chunk sanitizer cannot perturb the byte-goldens. Run them to PROVE it. SC-001-safe (duck-typed on the runner capability / tool-less condition, no workflow/agent-name literal).
- This is engine-touching but generic (no workflow special-casing) — appropriate for a code phase.

### INVARIANTS
- **INV-3:** the 5 characterization goldens (prototype/od_prototype/prototype_revision/od_ppt/app_builder) MUST stay byte/event-identical. Three independent guards: (006) scripted model ignores prompts; (005) the post_step is event-free + DB rows aren't golden-tracked; (004) goldens normalize chunk text + pin only post-sanitized output. Run the suite for EACH — do not assume.
- **SC-001:** the validator keys on the declared capability; the chunk sanitizer keys on the generic tool-less condition; the prompt literal is a shared contract — no workflow/agent-name branching in the kernel.
- **Ports & Adapters / import-linter:** the validator is pure-stdlib (no `app.*`/`execution_engine` import — same purity as `spec_plan_coverage`); the engine edit reads existing runner capability. `lint-imports` stays 4 kept / 0 broken.
- **Additive only:** the `validation_results` table already exists; zero new tables/migrations.

</decisions>

<canonical_refs>
## Canonical References (read before planning/implementing)

### The WHY
- `.planning/ISSUES-REGISTER.md` → "Deep Root-Cause Investigation" rows ISS-006 / ISS-005 / ISS-004.

### Behavior anchors
- ISS-006: `backend/agents/prompts/app-code-generator/AGENT.md` (producer), `backend/agents/prompts/app-test-implementation/AGENT.md:34-52` (consumer contract-fidelity); `backend/agents/registry.py:88` (the 15-agent app_builder roster + tools); `backend/tests/agents/test_prompt_contracts.py` (the Phase-15 pin layer to extend); `backend/tests/agents/_scripted_model.py` (proves prompts ignored by goldens).
- ISS-005: `backend/agents/capabilities/validators/spec_plan_coverage.py` (the VERBATIM template), `backend/agents/capabilities/hooks/revision_validation.py` (the event-free post_step precedent), `backend/agents/workflows/app_builder/workflow.yaml` (the infra-generator step to add `post_step`), `backend/agents/execution_engine/engine.py:1666-1668` (the post_step invocation seam), `backend/agents/prompts/{app-api-design,app-devops,app-infra-generator}/AGENT.md` (the `/api/v1` prose), `backend/tests/agents/characterization/golden/app_builder.events.json` (must stay byte-identical).
- ISS-004: `backend/app/agents/deep_agent_runner.py:129-151` (`_strip_fabricated_tool_xml` — reuse), `backend/agents/execution_engine/engine.py:2330-2332` (the `agent_chunk` yield — the edit site) + :2480-2492 (`sanitize_output` — the existing accumulated-output locus), `backend/tests/agents/characterization/_normalize.py` (chunk-text normalization — why goldens are safe), `backend/tests/agents/_scripted_model.py` (drive a split-tool-XML scripted stream for the fault-injection test).

</canonical_refs>

<specifics>
## Specific Ideas / Landmines
- ISS-005's load-bearing INV-3 decision is the EVENT-FREE post_step (not a validation gate) — get this wrong and the app_builder golden breaks. Prove both directions (event-free passes; gate-wired fails).
- ISS-004's load-bearing subtlety is span-straddle buffering — a per-chunk regex misses `<function_calls>` split across deltas. The buffer holds the tail on an unterminated opener.
- All three offline-verifiable; the LIVE re-confirms (a real Haiku app_builder + dotnet + mulesoft pass: 0 tool-XML in sdlc-governance chunks; `/api/v1` count non-zero in infra-generator output; `tsc`/grep no getDb mismatch) run in the consolidated live + Playwright pass on `default`.
- Validators ISS-005/006 share a natural "sibling validators behind one event-free post_step" shape, BUT only `api_prefix` is built here (ISS-006 uses the prompt contract; the symbol/type-check validator is N3/v2).

</specifics>

<deferred>
## Deferred Ideas
- LIVE re-confirms of ISS-004/005/006 on `default` Bedrock — the consolidated live + Playwright pass after this phase.
- A `symbol_contract` / `code_typecheck` (`tsc`) validator for ISS-006 — N3-era (needs exec + TS toolchain).
- Clusters A/B/C/E — done (Phases 16-18).
</deferred>

---

*Phase: 19-prompt-and-deliverable-adherence*
*Context: 2026-06-13 from the cluster-D deep investigation, code-proven file:line.*
