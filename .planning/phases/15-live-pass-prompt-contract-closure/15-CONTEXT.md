# Phase 15: Live-Pass Prompt Contract Closure - Context

**Gathered:** 2026-06-13
**Status:** Ready for planning
**Source:** Decisions locked with the user during/after the 2026-06-12 milestone-end live re-pass (no interactive discuss round needed — findings + dispositions are fully recorded in the live-pass report).

<domain>
## Phase Boundary

Close the three prompt-shaped findings of the 2026-06-12 live re-pass so the milestone can complete:

1. **LV-02 (major, product)** — od_ppt's resolved deliverable is the od-ppt-validator's QA narration, not the composer's deck; the FR-014 `deliverable` ref then feeds narration into the revision chain (Phase-14 SC4 content blocker).
2. **F4 residual** — the sdlc-governance agent family (`app-sdlc-governance`, `dotnet-sdlc-governance`, and check `mulesoft-sdlc-governance`) emits fabricated tool-call XML preambles (`<function_calls>`/`<invoke name="read_file">`) on live Haiku before real content.
3. **F5 residual** — `app-infra-generator` ignored the `/api/v1` prefix rule its prompt carries (0 occurrences in 3,083 output lines while api-design used it 58× and devops 50×).

IN SCOPE: AGENT.md prompt bodies, offline pinning tests, a cheap live re-check.
OUT OF SCOPE: any engine/capability/kernel/factory edit; the `deliverable: ppt` resolver; FE changes; the remaining live-pass items already dispositioned (LV-01, LV-03, getDb test mismatch, IN-01..06 advisories).

</domain>

<decisions>
## Implementation Decisions

### LV-02 fix approach (LOCKED)
- Fix is a PROMPT OUTPUT CONTRACT on `agents/prompts/od-ppt-validator/AGENT.md`: the validator must ALWAYS re-emit the complete corrected deck wrapped in `<artifact>` tags as its final output (QA commentary may precede, the artifact-wrapped full deck must be the emission the resolver unwraps). This mirrors the 13-03 app-devops output-contract precedent.
- The alternative — a fallback in the `deliverable: ppt` resolver (e.g., scan earlier streams for the largest `<section`-bearing artifact) — is REJECTED: engine-side behavior change, INV-3-sensitive, contradicts the "streamed deck IS the deliverable" capability contract.
- Do NOT touch `agents/capabilities/deliverables/ppt.py` or `_artifact.py`.

### sdlc-governance anti-fabrication (LOCKED)
- Add an explicit output-contract line to each sdlc-governance AGENT.md body: begin DIRECTLY with the deliverable content; never emit tool-call syntax (`<function_calls>`, `<invoke>`, `write_todos`) as text; the agent has no tools.
- The 13-02 factory-level `tool_availability` preamble stays untouched (it works for the other 14/15 agents); this is prompt-body reinforcement for the one agent family where the body's process framing overrides the preamble on live Haiku.

### infra-generator /api/v1 adherence (LOCKED)
- Strengthen and reposition the existing `/api/v1` rule in `agents/prompts/app-infra-generator/AGENT.md` so it is forceful and positionally prominent (top-of-body contract, concrete examples: healthchecks `/api/v1/health`, nginx location blocks, smoke curls). Keep the 13-03 single-literal-standard (`/api/v1`).

### Verification approach (LOCKED)
- Offline pins follow the 13-03 acceptance-grep precedent: tests asserting the contract lines exist in the five AGENT.md bodies (od-ppt-validator + 3× sdlc-governance + app-infra-generator).
- Plus one scripted-model pin: drive the od_ppt pipeline offline with a scripted validator that re-emits an artifact-wrapped deck and assert the resolved `final_output` is the deck (contains `<section`), proving the resolver+contract composition end-to-end at the harness level.
- INV-3: the 5 characterization snapshot pipelines (prototype / od_prototype / prototype_revision / od_ppt / app_builder) — od_ppt and app_builder ARE characterization pipelines; their scripted-model goldens must stay byte-identical. The scripted model ignores prompt content (Phase-3 documented caveat), so AGENT.md body edits do not perturb goldens — but the plan MUST include running the characterization suite to prove it.
- Live re-check (SC1 evidence): one od_ppt run + one FE-exact `od_ppt_output` revision (~$0.10) — resolved final_output is a deck, revision returns a revised deck. Criteria 2–3 live evidence may ride the same session or be recorded as next-live-pass items if quota-constrained.

### Confirmed gate semantics (context for any test wording — already shipped, do not revisit)
- WR-02 dedupe kept: one review per agent, inline gate wins.
- WR-04 pre-step edit semantics kept: declared-gate edits apply to the previous step's artifact.

### Claude's Discretion
- Exact wording of the contract lines (keep terse, imperative, mirroring 13-03 style).
- Whether the three sdlc-governance prompts share identical contract wording or per-pipeline phrasing.
- Test file placement (extend test_manifest_parity-style greps vs a new test_prompt_contracts.py — follow 13-03's actual test placement precedent found in the codebase).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Findings + evidence (the WHY)
- `.planning/live-verification/REPORT-2026-06-12.md` — LV-02 / F4-residual / F5-residual definitions, live evidence, fix candidates (sections "LV-02", "F5 re-audit", "F8 mulesoft-with-source").

### Fix-precedent (the HOW)
- `.planning/phases/13-live-verification-gap-closure/13-03-PLAN.md` + `13-03-SUMMARY.md` — the prompt re-template precedent: AGENT.md body-only edits, output-contract lines, acceptance greps, frontmatter untouched.
- `.planning/phases/13-live-verification-gap-closure/13-02-SUMMARY.md` — the tool_availability preamble + sanitizer (what already exists; this phase reinforces, not duplicates).

### Files to modify (bodies only, frontmatter untouched)
- `backend/agents/prompts/od-ppt-validator/AGENT.md`
- `backend/agents/prompts/app-sdlc-governance/AGENT.md`
- `backend/agents/prompts/dotnet-sdlc-governance/AGENT.md`
- `backend/agents/prompts/mulesoft-sdlc-governance/AGENT.md` (verify id/path; include if it exists)
- `backend/agents/prompts/app-infra-generator/AGENT.md`

### Behavior anchors
- `backend/agents/capabilities/deliverables/ppt.py` — `PptResolver.resolve` uses `ctx.last_streamed` (READ-ONLY anchor; do not modify).
- `backend/tests/agents/_scripted_model.py` — scripted harness branch points (od-ppt-validator scripted output lives here for the harness pin).
- `backend/tests/agents/test_manifest_parity.py` — 14-01 executable-pin precedent shape.

</canonical_refs>

<specifics>
## Specific Ideas

- LV-02 live evidence to reproduce in the pin: composer streamed 21,394 chars with `<artifact>` + `<section class="slide">`; validator streamed 1,350 chars QA narration with a small `<artifact>`; resolved final_output was the narration. The contract must make the validator's LAST artifact-wrapped emission BE the full corrected deck.
- sdlc-governance XML signature observed live: 5× `<function_calls>` each wrapping `<invoke name="read_file">` in the stream PREAMBLE (lines 2–36) before otherwise-valid content — the contract line should specifically forbid leading tool-syntax and demand the deliverable starts immediately.

</specifics>

<deferred>
## Deferred Ideas

- LV-01 (wait_for cancel-race at websocket.py:1669/:802/:1999 — `asyncio.timeout()` fix) — separate test-infra task, not prompt-shaped.
- LV-03 (token-delta test clarify hang) — separate test-infra task.
- `getDb`→`getDatabase` app_builder test-setup mismatch and any deeper cross-agent contract enforcement — live-model adherence variance items, monitor on next pass.
- IN-01..IN-06 advisories — unchanged disposition.

</deferred>

---

*Phase: 15-live-pass-prompt-contract-closure*
*Context gathered: 2026-06-13 from user-locked decisions (live-pass closure discussion)*
