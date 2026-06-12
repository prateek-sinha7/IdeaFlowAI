# Phase 15: Live-Pass Prompt Contract Closure - Research

**Researched:** 2026-06-13
**Domain:** AGENT.md prompt output-contracts + offline pinning tests (zero engine edits, SC-001)
**Confidence:** HIGH (every claim verified against the working tree in this session)

## Summary

Phase 15 is a prompt-body + test phase: five AGENT.md bodies get output-contract lines (od-ppt-validator deck re-emission; 3× sdlc-governance anti-fabrication; app-infra-generator /api/v1 strengthening), pinned by new offline tests. All five files, the resolver path, the 13-03 precedent, and the scripted-model harness were read in full this session. Three findings dominate planning:

1. **The unwrap semantics correct the contract wording.** `unwrap_artifact` (`backend/agents/capabilities/deliverables/_artifact.py:34-38`) is `re.search(r"<artifact[^>]*>\s*([\s\S]*?)\s*</artifact>", ...)` — it extracts the **FIRST** `<artifact>` block in `ctx.last_streamed` (non-greedy to the first `</artifact>`), not the last. The CONTEXT.md phrasing "the validator's LAST artifact-wrapped emission" must be implemented as "**exactly ONE** artifact block per response, whose content is the complete corrected deck" — any small artifact emitted earlier in QA commentary would win and reproduce LV-02. `[VERIFIED: codebase read]`

2. **The scripted validator already conforms — and its bytes ARE the od_ppt goldens.** `_scripts_for("od-ppt-validator")` (`backend/tests/agents/_scripted_model.py:322-342`) already streams `"Validation passed. No P0 issues.\n<artifact>{deck}</artifact>"`; `golden/od_ppt.html` is byte-identical to that unwrapped deck, and `golden/od_ppt.events.json` pins the validator's `output_length: 306` and `pipeline_complete.final_output` verbatim. **Any edit to that `_scripts_for` branch is a golden re-baseline = INV-3 violation.** The new harness pin must be a separate test injecting a custom per-agent model via `tests/agents/live_harness.drive_engine_pipeline(model=lambda aid: ...)` — zero edits to `_scripted_model.py`, zero golden perturbation. `[VERIFIED: codebase read + golden inspection]`

3. **The 13-03 "acceptance-grep precedent" left NO persistent test.** 13-03's greps lived only in the plan's `<verify>`/`<acceptance_criteria>` blocks (plus `test_loader.py -q` per task); no test file in `backend/tests/` pins 13-03's contract lines today. Phase 15's locked decision upgrades this to durable pytest pins — the right shape is `test_guardrails.py`-style assertions on `load_agent_spec(id).prompt_body` in a new `tests/agents/test_prompt_contracts.py`. `[VERIFIED: grep across backend/tests/]`

**Primary recommendation:** Three plans/waves of work: (1) edit the five prompt bodies (frontmatter byte-untouched), (2) add `tests/agents/test_prompt_contracts.py` (prompt_body substring pins, single-line phrases) + one LV-02 harness composition test via `drive_engine_pipeline`, (3) run the targeted offline gate (loader + 5 characterization snapshots + new tests + banned-patterns + ledger + lint-imports) proving goldens byte-identical; record the cheap live re-check as the milestone-end follow-up item.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### LV-02 fix approach (LOCKED)
- Fix is a PROMPT OUTPUT CONTRACT on `agents/prompts/od-ppt-validator/AGENT.md`: the validator must ALWAYS re-emit the complete corrected deck wrapped in `<artifact>` tags as its final output (QA commentary may precede, the artifact-wrapped full deck must be the emission the resolver unwraps). This mirrors the 13-03 app-devops output-contract precedent.
- The alternative — a fallback in the `deliverable: ppt` resolver (e.g., scan earlier streams for the largest `<section`-bearing artifact) — is REJECTED: engine-side behavior change, INV-3-sensitive, contradicts the "streamed deck IS the deliverable" capability contract.
- Do NOT touch `agents/capabilities/deliverables/ppt.py` or `_artifact.py`.

#### sdlc-governance anti-fabrication (LOCKED)
- Add an explicit output-contract line to each sdlc-governance AGENT.md body: begin DIRECTLY with the deliverable content; never emit tool-call syntax (`<function_calls>`, `<invoke>`, `write_todos`) as text; the agent has no tools.
- The 13-02 factory-level `tool_availability` preamble stays untouched (it works for the other 14/15 agents); this is prompt-body reinforcement for the one agent family where the body's process framing overrides the preamble on live Haiku.

#### infra-generator /api/v1 adherence (LOCKED)
- Strengthen and reposition the existing `/api/v1` rule in `agents/prompts/app-infra-generator/AGENT.md` so it is forceful and positionally prominent (top-of-body contract, concrete examples: healthchecks `/api/v1/health`, nginx location blocks, smoke curls). Keep the 13-03 single-literal-standard (`/api/v1`).

#### Verification approach (LOCKED)
- Offline pins follow the 13-03 acceptance-grep precedent: tests asserting the contract lines exist in the five AGENT.md bodies (od-ppt-validator + 3× sdlc-governance + app-infra-generator).
- Plus one scripted-model pin: drive the od_ppt pipeline offline with a scripted validator that re-emits an artifact-wrapped deck and assert the resolved `final_output` is the deck (contains `<section`), proving the resolver+contract composition end-to-end at the harness level.
- INV-3: the 5 characterization snapshot pipelines (prototype / od_prototype / prototype_revision / od_ppt / app_builder) — od_ppt and app_builder ARE characterization pipelines; their scripted-model goldens must stay byte-identical. The scripted model ignores prompt content (Phase-3 documented caveat), so AGENT.md body edits do not perturb goldens — but the plan MUST include running the characterization suite to prove it.
- Live re-check (SC1 evidence): one od_ppt run + one FE-exact `od_ppt_output` revision (~$0.10) — resolved final_output is a deck, revision returns a revised deck. Criteria 2–3 live evidence may ride the same session or be recorded as next-live-pass items if quota-constrained.

#### Confirmed gate semantics (context for any test wording — already shipped, do not revisit)
- WR-02 dedupe kept: one review per agent, inline gate wins.
- WR-04 pre-step edit semantics kept: declared-gate edits apply to the previous step's artifact.

### Claude's Discretion
- Exact wording of the contract lines (keep terse, imperative, mirroring 13-03 style).
- Whether the three sdlc-governance prompts share identical contract wording or per-pipeline phrasing.
- Test file placement (extend test_manifest_parity-style greps vs a new test_prompt_contracts.py — follow 13-03's actual test placement precedent found in the codebase).

### Deferred Ideas (OUT OF SCOPE)
- LV-01 (wait_for cancel-race at websocket.py:1669/:802/:1999 — `asyncio.timeout()` fix) — separate test-infra task, not prompt-shaped.
- LV-03 (token-delta test clarify hang) — separate test-infra task.
- `getDb`→`getDatabase` app_builder test-setup mismatch and any deeper cross-agent contract enforcement — live-model adherence variance items, monitor on next pass.
- IN-01..IN-06 advisories — unchanged disposition.
</user_constraints>

<phase_requirements>
## Phase Requirements

No new REQUIREMENTS.md IDs — the phase closes three live findings from `.planning/live-verification/REPORT-2026-06-12.md`:

| ID | Description | Research Support |
|----|-------------|------------------|
| LV-02 (major) | od_ppt resolved deliverable is the validator's QA narration, not the deck; FR-014 revision chain feeds narration downstream | Resolver semantics (§Resolver Anchor) prove first-artifact-wins → contract demands exactly one artifact block = the full deck; harness pin design (§Harness) proves resolver+contract composition offline with zero golden perturbation |
| F4 residual | sdlc-governance family emits fabricated tool-XML preamble (`<function_calls>`/`<invoke name="read_file">`) on live Haiku before content | Current bodies read (§Current Bodies): the process framing ("Read the concrete choices the upstream agents actually made") + `tools: []` mismatch elicits simulated tool calls; contract line placement + per-pipeline tailoring documented |
| F5 residual | app-infra-generator ignored its existing `/api/v1` rule (0× in 3,083 lines vs api-design 58×, devops 50×) | Existing rule located (RULES bullet 2, line 102 — bottom-of-body, conditional phrasing); strengthening = top-of-body contract with concrete examples |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **SC-001 / zero engine edits**: kernel knows no workflow by name; this phase touches ONLY `backend/agents/prompts/*/AGENT.md` bodies + `backend/tests/` — no engine/capability/factory/registry/resolver file may change.
- **INV-3 / no dual implementations / backward-compat**: characterization goldens (5 pipelines) stay byte-identical; no `SNAPSHOT_UPDATE=1` runs.
- **Runtime mandate (INV-13)**: untouched — no agent-loop code in scope.
- **Runtime/test interpreter**: `python3.11` (homebrew, no venv) — `python`/`python3` are wrong (backend/CLAUDE.md + dev-runtime memory).
- **Commit scopes** (backend/CLAUDE.md): `fix(prompts)` for the bulk prompt-body edits (13-03 used `fix` type for its prompt tasks), `test(agents)` for new test files. Subject < 72 chars, imperative.
- **GSD workflow enforcement**: edits go through `/gsd-execute-phase`.
- **Frontmatter is schema-validated**: `tests/agents/test_loader.py` re-validates all ~80 agents — run it after every prompt edit (13-03 did this per task).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Deck re-emission contract (LV-02) | Prompt layer (`agents/prompts/od-ppt-validator/AGENT.md` body) | — | Locked: resolver fallback rejected; "streamed deck IS the deliverable" capability contract holds |
| Anti-fabrication contract (F4) | Prompt layer (3× sdlc-governance bodies) | — | 13-02 factory `tool_availability` preamble stays untouched; body reinforcement only |
| /api/v1 adherence (F5) | Prompt layer (`app-infra-generator` body) | — | Rule exists; repositioning/strengthening is text-only |
| Contract pinning | Test layer (`backend/tests/agents/`) | — | New `test_prompt_contracts.py` + one harness composition test; no harness-module edits |
| Deliverable resolution (READ-ONLY) | Capability layer (`agents/capabilities/deliverables/ppt.py`, `_artifact.py`) | — | Behavior anchor only — frozen by locked decision; semantics documented below |
| Regression gate | Characterization suite (`tests/agents/test_characterization_*.py`) | — | INV-3 proof: run all 5, byte-identical goldens |

## Standard Stack

No new libraries, no new packages, no installs. The phase uses only what exists:

### Core
| Component | Location | Purpose | Why Standard |
|-----------|----------|---------|--------------|
| `load_agent_spec(id).prompt_body` | `backend/agents/loader.py:83,171` | Body-content access for contract pins | Goes through the real parser the factory composes from; `test_guardrails.py` precedent (lines 104, 211) `[VERIFIED: codebase read]` |
| `drive_engine_pipeline(...)` | `backend/tests/agents/live_harness.py:484` | Offline od_ppt drive with per-agent custom model | Accepts `model=lambda agent_id: BaseChatModel` (per-agent factory), `fake_planner=True`, `od_context=...`, `gate_agent_ids=()` — exactly the LV-02 pin shape `[VERIFIED: codebase read]` |
| `ScriptedFakeChatModel` + `_ScriptedTurn` | `backend/tests/agents/_scripted_model.py:76-216` | Deterministic offline model | The canonical scripted recipe (stock LangChain fakes do NOT drive deepagents) — import it, never edit it `[VERIFIED: codebase read]` |
| `pytest` via `python3.11 -m pytest` | existing | Test runner | Project standard `[VERIFIED: backend/CLAUDE.md]` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `load_agent_spec().prompt_body` assertions | Raw `Path(...).read_text()` greps | read_text also works (test_guardrails does both) but prompt_body proves the line survives frontmatter parsing — what the factory actually composes |
| `drive_engine_pipeline` with custom validator model | Reuse `_drive("od_ppt")` and assert `pipeline_complete.final_output` | `_drive` re-pins the same bytes characterization already pins (weaker); the custom-model drive reproduces the LV-02 evidence shape (long QA commentary + single artifact deck) without touching `_scripts_for` |
| New `tests/agents/test_prompt_contracts.py` | Extending `test_guardrails.py` or `test_manifest_parity.py` | `test_manifest_parity.py` pins COMPILER output (wrong shape); `test_guardrails.py` is guardrail-file-scoped; a dedicated file keeps the five pins discoverable and matches the CONTEXT discretion option |

## Package Legitimacy Audit

**Not applicable — this phase installs zero external packages.** All work is markdown prompt-body edits + pytest files using already-installed project dependencies. No `## Standard Stack` install commands exist for this phase.

## Current Bodies — Exact Anchors (the planner's edit map)

### 1. `backend/agents/prompts/od-ppt-validator/AGENT.md` (65 lines) `[VERIFIED: file read]`

**Frontmatter (FROZEN):** `id: od-ppt-validator`, `order: 3`, `pipeline_type: od_ppt`, `tools: [workspace]`, `max_tokens: 32768`, `consumes: [od-ppt-composer]`, `produces: [od-ppt-validator]`, `context_from: [$previous]`. Note `tools` is `workspace` (NOT `[]`) — a stale comment in `_scripted_model.py:290-292` calls the deck agents "text-only"; the frontmatter is authoritative and must not be "fixed".

**Existing OUTPUT CONTRACT already exists** (lines 54-65): "Emit the final HTML wrapped in `<artifact>` tags … One sentence before the artifact summarising the validation outcome. Nothing after `</artifact>`." Live Haiku violated it (1,350-char QA narration + a small artifact). Conflicting language that elicits QA-report mode:
- Line 23: "Your job: final QA pass… You **return the artifact EXACTLY as-is** unless you find a structural defect" — frames the job as judgment/reporting, not re-emission.
- Lines 28-46: the "Run each check" checklist framing primes a narrated checklist walk-through.
- The contract sits at the BOTTOM of the body; live evidence shows it loses to the process framing above it.

**Strengthening levers:** (a) move/duplicate the contract to the TOP of the body as a hard rule; (b) state the deck-re-emission invariant explicitly: "your response MUST contain exactly ONE `<artifact>` block and its content MUST be the COMPLETE corrected HTML deck (the full `<!DOCTYPE html>` document, all `<section class="slide">` elements) — even when you change nothing"; (c) explicitly forbid emitting a QA report/summary as the artifact content and forbid any second/partial artifact; (d) keep "commentary may precede" but bound it (the locked decision allows preceding commentary).

### 2. `backend/agents/prompts/app-sdlc-governance/AGENT.md` (117 lines) `[VERIFIED: file read]`

**Frontmatter (FROZEN):** `id: app-sdlc-governance`, `order: 15`, `pipeline_type: app_builder`, `tools: []`, `guardrails: []`, 6-agent `context_from`/`consumes`.
**Body:** 13-03 already re-templated it greenfield; output format = six `filename:` fenced blocks; last line: "Output ONLY the fenced file blocks above. No prose outside the blocks."
**The F4 trigger:** lines 36-41 — "**Read the concrete choices the upstream agents actually made** from the provided context" — process framing that elicits simulated `<invoke name="read_file">` calls on live Haiku (the agent has `tools: []`; live signature: 5× `<function_calls>` wrapping `<invoke name="read_file">` in stream lines 2-36).
**Contract line lands:** near the top of the body (before/at the "Read the concrete choices" paragraph): begin DIRECTLY with the first ```` ```filename: ```` block; you have NO tools — the upstream context is already IN your message, never emit tool-call syntax (`<function_calls>`, `<invoke>`, `write_todos`) as text.

### 3. `backend/agents/prompts/dotnet-sdlc-governance/AGENT.md` (86 lines) `[VERIFIED: file read]`

**Frontmatter (FROZEN):** `id: dotnet-sdlc-governance`, `order: 13`, `pipeline_type: dotnet_to_azure`, `tools: []`, `guardrails: [dotnet]`.
**Body:** migration-flavored (legitimately — this IS a migration pipeline; 13-03's de-migration applied only to app_builder). Output format: "Output as a structured Markdown document" — **NO `filename:` blocks**. The anti-fabrication line must be tailored: "begin directly with the deliverable content (the first Markdown heading)" — do NOT import the app_builder filename-block contract here.

### 4. `backend/agents/prompts/mulesoft-sdlc-governance/AGENT.md` (86 lines) `[VERIFIED: file read]`

Exists (CONTEXT's "verify it exists" → confirmed). **Frontmatter (FROZEN):** `id: mulesoft-sdlc-governance`, `order: 13`, `pipeline_type: mulesoft_to_springboot`, `tools: []`, `guardrails: [mulesoft, java-spring]`. Body is near-identical to the dotnet variant (structured Markdown output, no filename blocks) — same tailored contract line. Live evidence note: F8 re-capture had sdlc-governance among the 3 quota-killed (empty) agents, so its live fabrication is "check" status, not confirmed — the contract line is prophylactic per the locked decision.

### 5. `backend/agents/prompts/app-infra-generator/AGENT.md` (106 lines) `[VERIFIED: file read]`

**Frontmatter (FROZEN):** `id: app-infra-generator`, `order: 10`, `pipeline_type: app_builder`, `tools: [workspace]`, `max_tokens: 16000`.
**The existing weak rule** (line 102, RULES section bullet 2, bottom of body): "API paths: wherever health checks, route probes, ingress paths or smoke tests reference application API endpoints, use the literal `/api/v1` prefix (e.g. `/api/v1/health`), consistent with the API design context". Why it is weak: (a) bottom-of-body, after ~75 lines of file-by-file format spec; (b) conditional framing ("wherever … reference"); (c) one example. Live: 0× `/api/v1` in 3,083 lines while siblings complied.
**Strengthening levers (locked):** top-of-body contract block (before "OUTPUT FORMAT"), forceful phrasing, concrete examples — Docker/compose healthchecks (`curl -f http://localhost:PORT/api/v1/health`), nginx/ingress `location /api/v1/`, CI smoke-test curls. Keep the literal `/api/v1` (single standard shared with app-api-design 58× / app-devops 50× compliance). The bottom RULES bullet may stay (reinforcement) or be folded up — planner's choice; the pin should target the top-of-body contract.

## The 13-03 Precedent — Actual Mechanics `[VERIFIED: 13-03-PLAN.md + 13-03-SUMMARY.md + test-suite grep]`

- **Edit structure:** 3 tasks over 9 AGENT.md files; bodies only; frontmatter explicitly out of scope ("id/order/pipeline_type/context_from stay as-is"); no registry/loader change; `git diff --stat` confined to `backend/agents/prompts/`.
- **Acceptance:** shell grep gates embedded in each task's `<verify>`/`<acceptance_criteria>` (e.g. `grep -c "/api/v1" ... >= 1`, `! grep -liE "maven|nuget|..."`) + `python3.11 -m pytest tests/agents/test_loader.py -q` after every task.
- **CRITICAL: no persistent test was created.** Grep across `backend/tests/` finds NO test pinning 13-03's contract lines (`/api/v1`, "Output contract", "state the assumption") — acceptance was plan-grep-only. Phase 15's locked decision ("tests asserting the contract lines exist") therefore CREATES the durable pin layer 13-03 lacked; the closest existing shape is `test_guardrails.py` (asserts file content + `spec.prompt_body` substrings), not `test_manifest_parity.py` (compiler-output pins).
- **Wording lesson (13-03 Issues Encountered):** contract phrases that wrap across line breaks defeated the line-based grep gates — "Anti-stall phrasing kept on single lines so grep gates stay verifiable." Phase 15 contract lines must keep each pinned phrase on a single line (substring asserts are line-break-sensitive only if the pin includes the break — pin short single-line tokens).

## Resolver Anchor (READ-ONLY — frozen by locked decision) `[VERIFIED: file read]`

`backend/agents/capabilities/deliverables/ppt.py::PptResolver.resolve`:
```python
last_streamed = getattr(ctx, "last_streamed", "") or ""
return unwrap_artifact(sanitize_carousel_deck_html(last_streamed))
```
- `ctx.last_streamed` = the LAST agent's (validator's) full streamed text — earlier agents' streams are never consulted.
- `unwrap_artifact` (`_artifact.py:34-38`): `re.search(r"<artifact[^>]*>\s*([\s\S]*?)\s*</artifact>", text, re.IGNORECASE)` → **first `<artifact` opening, non-greedy to the first `</artifact>`**. If no wrapper, whole text passes through.
- `sanitize_carousel_deck_html` runs FIRST on the whole stream — order-equivalence vs legacy is pinned by `test_ppt_sanitize_unwrap_order_is_equivalent_on_wrapped_carousel` (WR-02, 07-09).

**Consequences for the contract wording (the planner MUST encode these):**
1. "Last artifact-wrapped emission" (CONTEXT phrasing) is WRONG at the mechanism level — the resolver takes the **FIRST** artifact block. The contract must demand **exactly one** `<artifact>` block per validator response, containing the complete deck. A small status-artifact before the deck artifact would be extracted instead of the deck (reproducing LV-02 in a new costume).
2. Preceding QA commentary is safe ONLY if it contains no `<artifact` token (the regex scans the whole string). The contract should forbid the word/tag `<artifact` anywhere outside the single deck block.
3. "Nothing after `</artifact>`" (already in the current contract) remains correct — trailing text is discarded by unwrap anyway, but keeping the rule reduces drift.

## Harness — Scripted-Model Pin Design `[VERIFIED: codebase read + golden inspection]`

### What is frozen
- `_scripts_for("od-ppt-validator")` (`_scripted_model.py:322-342`) emits `"Validation passed. No P0 issues.\n<artifact>{deck}</artifact>"` where deck = 4 `<section class='deck-slide'>` HTML (306 chars with prefix). **This output IS the goldens:**
  - `tests/agents/characterization/golden/od_ppt.html` = the unwrapped deck, byte-identical.
  - `golden/od_ppt.events.json` pins `agent_complete{agent_id: od-ppt-validator, output_length: 306}` and `pipeline_complete.final_output` = deck bytes verbatim (chunk text is normalized out, but output_length and final_output are NOT).
- Therefore: **editing the validator's `_scripts_for` branch (or its turn text/usage) re-baselines two goldens → INV-3 violation.** The pin must be a separate test with a per-test model.
- Conveniently, the existing scripted validator already CONFORMS to the new contract (commentary + single artifact-wrapped deck) — the goldens already prove the conforming composition. The phase adds an EXPLICIT named pin mirroring the live LV-02 shape.

### Sibling facts (why prompt edits can't perturb goldens)
- `app-sdlc-governance` and `app-infra-generator` are in `_scripts_for`'s `TEXT_ONLY` set (`_scripted_model.py:248-272`) → generic `f"{agent_id} output line one. line two."` (46 chars — matches `output_length: 46` in `golden/app_builder.events.json` for both). Scripted output never reads the system prompt (Phase-3 documented caveat) → AGENT.md edits cannot change goldens. The characterization suite run is still mandatory proof (locked decision).
- `dotnet_to_azure` / `mulesoft_to_springboot` are NOT characterization pipelines — no golden exposure at all.

### Recommended pin shape (composition test, zero harness edits)
New test (in `tests/agents/test_prompt_contracts.py` or a sibling `test_lv02_deck_contract.py`):
```python
# Source: tests/agents/live_harness.py::drive_engine_pipeline (per-agent model factory regime)
from tests.agents._scripted_model import ScriptedFakeChatModel, _ScriptedTurn, _scripts_for
from tests.agents.live_harness import drive_engine_pipeline

_DECK = "<!DOCTYPE html><html>...<section class=\"slide active\">...</section>...</html>"  # full deck, <section-bearing

def _model_for(agent_id):
    if agent_id == "od-ppt-validator":
        # LV-02 evidence shape: multi-line QA commentary FIRST, then the single
        # artifact-wrapped COMPLETE deck (contract-conformant output).
        return ScriptedFakeChatModel([_ScriptedTurn(
            texts=["Running the final QA pass...\nP0 checks complete. One fix applied.\n",
                   f"<artifact identifier=\"deck\" type=\"text/html\" title=\"Deck\">{_DECK}</artifact>"],
            usage=(22, 14))])
    return ScriptedFakeChatModel(_scripts_for(agent_id))  # other agents: stock scripts

# drive_engine_pipeline("od_ppt", model=_model_for, fake_planner=True,
#                       od_context={...as _scripted_model._drive seeds...}, gate_agent_ids=())
# assert: pipeline_complete final_output contains "<section", starts with "<!DOCTYPE",
#         and does NOT contain the QA narration prefix.
```
Notes for the planner:
- `drive_engine_pipeline` handles RUNS_ROOT, clarify-off, store no-op, unique run_id, patch-restore (live_harness.py:484-600). `fake_planner=True` skips the planner LLM. The od_ppt agents declare `injects=[template, design_system]` — pass an `od_context` (copy the seed dict from `_scripted_model._drive`, lines 570-579: `template_body`, `template_id`, `ds_id`, `ds_body`, `craft_block`, `is_design_system_required`).
- `final_output` arrives in the `pipeline_complete` event's data (verified in golden). Check `CaptureResult`'s exact accessor when writing the test (it captures the engine event list).
- The drive runs the REAL engine + REAL resolver + REAL prompts — only the model is scripted — so it proves contract-shaped output → deck resolution end-to-end, which is exactly the locked pin.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Body extraction for pins | Regex/manual frontmatter splitting | `load_agent_spec(id).prompt_body` | The loader is the single parser; manual splitting can diverge on edge cases and misses the cache/validation path |
| Offline od_ppt drive | A new engine driver/monkeypatch stack | `live_harness.drive_engine_pipeline` | It already owns the §12 gotchas (RUNS_ROOT, clarify-off, patch restore, unique run_id, per-agent model factory) |
| Scripted model | LangChain `FakeListChatModel` etc. | `ScriptedFakeChatModel` | Stock fakes do NOT drive the deepagents loop (documented in `_scripted_model.py:12-17`) |
| Deck resolution in the pin | Re-implementing unwrap/sanitize in the test | Assert on the engine's resolved `final_output` | The point is composition through the REAL `PptResolver`; duplicating the transform would prove nothing |

**Key insight:** every piece of machinery this phase needs already exists and is battle-tested; the phase's only creative surface is prompt wording + assertion selection.

## Common Pitfalls

### Pitfall 1: Editing `_scripts_for`'s od-ppt-validator branch
**What goes wrong:** `od_ppt.html` and `od_ppt.events.json` goldens break (output_length 306 + final_output bytes are pinned verbatim).
**Why it happens:** the CONTEXT asks for "a scripted validator that re-emits an artifact-wrapped deck" — tempting to "update" the shared script.
**How to avoid:** the shared script ALREADY conforms; build the pin with a per-test model factory via `drive_engine_pipeline(model=...)`. Zero edits to `_scripted_model.py`.
**Warning signs:** any diff in `tests/agents/_scripted_model.py` or `tests/agents/characterization/golden/`; any `SNAPSHOT_UPDATE=1` in a command.

### Pitfall 2: Contract wording says "last artifact"
**What goes wrong:** a validator that emits a small status artifact first, deck artifact second, still resolves to the status blob — LV-02 persists despite a "compliant" prompt.
**How to avoid:** word the contract as "exactly ONE `<artifact>` block; its content is the complete corrected deck; never use the `<artifact` tag anywhere else in your response" (first-match unwrap semantics, `_artifact.py:35`).
**Warning signs:** contract text containing "final"/"last artifact" without the exactly-one rule.

### Pitfall 3: Multi-line pinned phrases
**What goes wrong:** substring/grep pins fail when the prompt phrase wraps (13-03 hit this exactly — "state the assumption" wrapped in two files and defeated the gates).
**How to avoid:** keep each pinned phrase on one line in the AGENT.md body; pin short stable tokens (`/api/v1`, `<function_calls>`, `exactly one <artifact>`-class tokens), not sentences.

### Pitfall 4: Frontmatter drift
**What goes wrong:** loader schema break, or silent behavior change (tool grants, order).
**How to avoid:** edits strictly below the closing `---`; `python3.11 -m pytest tests/agents/test_loader.py -q` after each file; `git diff --stat` confined to `backend/agents/prompts/` + `backend/tests/` (13-03's exact gate). Optionally pin the five agents' frontmatter (id/order/tools/pipeline_type) in the new test file as an explicit frontmatter-freeze.
**Note:** od-ppt-validator's `tools: [workspace]` looks anomalous next to the sdlc family's `tools: []` — it is intentional (frontmatter frozen; do not "normalize").

### Pitfall 5: Importing the wrong output format into dotnet/mulesoft
**What goes wrong:** app-sdlc-governance ends "Output ONLY the fenced file blocks"; dotnet/mulesoft output "a structured Markdown document" (no filename blocks). A copy-pasted app_builder contract line ("begin with the first filename: block") would CHANGE the migration pipelines' deliverable format — out of scope and a behavior change.
**How to avoid:** per-pipeline tailoring of the deliverable-start phrase ("begin directly with the deliverable content / the first Markdown heading"); the anti-tool-XML sentence can be identical across all three.

### Pitfall 6: Running the full pytest suite offline
**What goes wrong:** full `tests/agents/ tests/unit/` HANGS offline (Chromium/Bedrock/Postgres-gated tests stall, not skip); orphaned pytest procs contend.
**How to avoid:** targeted suite only (see Validation Architecture). `pkill -9 -f pytest` if a run hangs.

### Pitfall 7: Prompt exemplars priming fabrication
**What goes wrong:** writing literal `<function_calls>`/`<invoke name="read_file">` exemplars into the sdlc bodies can ironically prime live Haiku to produce them.
**How to avoid:** name the forbidden tokens once, tersely, in a prohibition sentence (the locked decision's framing) — do not show a multi-line "bad example" block. The WR-01 sanitizer only cleans the persisted engine-path output; the UI chunk stream is deliberately unfiltered, so prompt-level prevention is the only stream-level fix.

## Code Examples

### Prompt-body contract pin (test_guardrails.py shape)
```python
# Source: backend/tests/agents/test_guardrails.py:104,211 (spec.prompt_body assertion precedent)
from agents.loader import load_agent_spec

def test_od_ppt_validator_deck_reemission_contract():
    body = load_agent_spec("od-ppt-validator").prompt_body
    assert "<artifact" in body                      # artifact contract present
    # + pin the phase's exact single-line contract tokens chosen by the planner,
    #   e.g. the exactly-one-artifact rule and the complete-corrected-deck rule.

def test_sdlc_governance_anti_fabrication_contract():
    for agent_id in ("app-sdlc-governance", "dotnet-sdlc-governance", "mulesoft-sdlc-governance"):
        body = load_agent_spec(agent_id).prompt_body
        assert "<function_calls>" in body           # forbidden-token named in the prohibition
        # + the begin-directly + no-tools tokens

def test_infra_generator_api_v1_contract():
    body = load_agent_spec("app-infra-generator").prompt_body
    assert body.count("/api/v1") >= 3               # contract + concrete examples (health, ingress, smoke)
```
(Optional frontmatter freeze: assert `spec.order`, `spec.tools`, `spec.pipeline_type` for the five agents.)

### 13-03-style shell acceptance greps (per-task verify commands)
```bash
# Source: .planning/phases/13-live-verification-gap-closure/13-03-PLAN.md verify blocks
cd backend && python3.11 -m pytest tests/agents/test_loader.py -q \
  && grep -c "/api/v1" agents/prompts/app-infra-generator/AGENT.md \
  && grep -ci "function_calls" agents/prompts/app-sdlc-governance/AGENT.md
```

## State of the Art (project-local)

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| 13-03: grep-only acceptance in the plan (no persistent test) | Phase 15: durable pytest pins on `prompt_body` | This phase (locked) | Contract lines survive future prompt rewrites |
| Engine-side artifact unwrap (`engine.py:_unwrap_artifact`) | `PptResolver` capability (`deliverables/ppt.py`), engine call sites deleted 07-05 | Phase 7 | Resolver is the frozen behavior anchor; fix must be prompt-side |
| 13-02 factory `tool_availability` preamble (anti-fabrication, all agents) | Stays untouched; sdlc family gets body-level reinforcement | This phase (locked) | No factory edit; reinforcement only where the body framing wins over the preamble |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Repositioning the contract to the top of the body + exactly-one-artifact wording will fix live-Haiku adherence (the existing bottom-of-body contract was ignored) | Current Bodies §1 | Live re-check fails → next escalation would be resolver-side (rejected) or model-side; recorded as next-live-pass item per the locked verification approach |
| A2 | The "Read the concrete choices…" framing is the F4 fabrication trigger (inference from live preamble shape: 5× `<invoke name="read_file">`) | Current Bodies §2 | Contract line still prophylactically forbids tool-XML, so the fix holds regardless of the precise trigger |
| A3 | `CaptureResult` from `drive_engine_pipeline` exposes the event list such that `pipeline_complete.final_output` is reachable (verified events carry it; the exact accessor name was not read this session) | Harness | Trivial — test author reads `live_harness.py` `CaptureResult` definition while writing the test |

## Open Questions

1. **Live re-check timing/budget** — CONTEXT locks the criteria (~$0.10, one od_ppt run + one FE-exact `od_ppt_output` revision) and allows recording as next-live-pass items if quota-constrained. Per the defer-live-verification project convention, the plan should mark phase completion on offline evidence + a recorded live-check item (Bedrock SSO/quota state on execution day decides). Recommendation: a `checkpoint:human-verify`-style closing task that either runs the cheap live check or records it.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `python3.11` (homebrew, no venv) | all tests | ✓ | 3.11 | — |
| `/opt/homebrew/bin/lint-imports` | targeted gate | ✓ (per memory note, verified path) | — | — |
| AWS Bedrock (SSO + quota) | live re-check ONLY | ✗ offline | — | Record live check as next-live-pass item (locked decision permits) |
| Postgres / Chromium | NOT needed | — | — | Targeted suite avoids the gated tests |

**Missing dependencies with no fallback:** none for the offline scope.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (project-pinned, `python3.11 -m pytest`) |
| Config file | backend pytest defaults (tests under `backend/tests/`) |
| Quick run command | `cd backend && python3.11 -m pytest tests/agents/test_loader.py tests/agents/test_prompt_contracts.py -q` |
| Full suite command | Targeted gate (full suite HANGS offline): `cd backend && python3.11 -m pytest tests/agents/test_characterization_prototype.py tests/agents/test_characterization_od_prototype.py tests/agents/test_characterization_prototype_revision.py tests/agents/test_characterization_od_ppt.py tests/agents/test_characterization_app_builder.py tests/agents/test_loader.py tests/agents/test_prompt_contracts.py tests/agents/test_banned_patterns.py tests/agents/test_migration_ledger.py -q && /opt/homebrew/bin/lint-imports` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| LV-02 (contract lines) | od-ppt-validator body carries the exactly-one-artifact complete-deck contract | unit (prompt pin) | `python3.11 -m pytest tests/agents/test_prompt_contracts.py -q -k validator` | ❌ Wave 0 |
| LV-02 (composition) | Contract-shaped validator output → resolved `final_output` is the deck (`<section`-bearing, not narration) | integration (offline engine drive) | `python3.11 -m pytest tests/agents/test_prompt_contracts.py -q -k deck_resolution` (or sibling file) | ❌ Wave 0 |
| F4 residual | 3× sdlc-governance bodies carry begin-directly + no-tool-XML contract | unit (prompt pin) | `python3.11 -m pytest tests/agents/test_prompt_contracts.py -q -k sdlc` | ❌ Wave 0 |
| F5 residual | app-infra-generator top-of-body /api/v1 contract with concrete examples | unit (prompt pin) | `python3.11 -m pytest tests/agents/test_prompt_contracts.py -q -k api_v1` | ❌ Wave 0 |
| INV-3 | 5 characterization goldens byte-identical after all edits | regression | the 5 `test_characterization_*.py` files (command above) | ✅ exists |
| Schema | All ~80 agents still load; frontmatter untouched | regression | `python3.11 -m pytest tests/agents/test_loader.py -q` | ✅ exists |
| SC1 live | One od_ppt run + one od_ppt_output revision resolve to decks | manual-only (live Bedrock, ~$0.10) | — quota-dependent; record as next-live-pass item if blocked (locked) | n/a |

### Sampling Rate
- **Per task commit:** `python3.11 -m pytest tests/agents/test_loader.py -q` + the task's contract-pin tests (13-03 cadence)
- **Per wave merge:** quick run command
- **Phase gate:** full targeted gate green (characterization byte-identical, zero `SNAPSHOT_UPDATE`) before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `backend/tests/agents/test_prompt_contracts.py` — covers LV-02/F4/F5 prompt pins + (optionally) the LV-02 harness composition test; no fixtures needed beyond existing harness imports
- No framework install needed; no conftest changes needed

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | — |
| V3 Session Management | no | — |
| V4 Access Control | no | — |
| V5 Input Validation | yes (marginal) | AGENT.md bodies are static, engineer-authored, version-controlled prompt content; loader schema validation (`test_loader.py`) re-validates every agent |
| V6 Cryptography | no | — |

### Known Threat Patterns (mirrors 13-03's threat model — same change class)

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Prompt edit silently changing tool grants/permissions | Tampering | Frontmatter out of scope; loader suite + `git diff --stat` confined to bodies + tests (13-03 T-13-03-02 disposition) |
| Prompt injection via interpolated user input | Spoofing | No user input interpolated by this phase; runtime skills/hooks channels unchanged (13-03 T-13-03-01 disposition) |
| Test harness weakening security gates | Tampering | New tests are additive; no engine/capability/gate file modified (SC-001 scope fence) |

## Sources

### Primary (HIGH confidence — all read in this session)
- `backend/agents/prompts/{od-ppt-validator,app-sdlc-governance,dotnet-sdlc-governance,mulesoft-sdlc-governance,app-infra-generator}/AGENT.md` — full bodies + frontmatter
- `backend/agents/capabilities/deliverables/ppt.py` + `_artifact.py` — resolver semantics (first-artifact unwrap)
- `backend/tests/agents/_scripted_model.py` — `_scripts_for` branches, `_drive`, od_context seed
- `backend/tests/agents/live_harness.py:484-600` — `drive_engine_pipeline` model-factory regime
- `backend/tests/agents/characterization/golden/od_ppt.{html,events.json}` + `app_builder.events.json` — byte-pin exposure verified
- `backend/tests/agents/characterization/_normalize.py` — what is/isn't normalized (output_length + final_output are pinned)
- `backend/tests/agents/test_guardrails.py`, `test_manifest_parity.py`, `test_deliverable_resolvers.py`, `test_characterization_od_ppt.py` — test-shape precedents
- `.planning/phases/13-live-verification-gap-closure/13-03-PLAN.md` + `13-03-SUMMARY.md` — precedent mechanics
- `.planning/live-verification/REPORT-2026-06-12.md` — LV-02 / F4-residual / F5-residual evidence
- `backend/CLAUDE.md` — AGENT.md schema, commit scopes, test commands
- `.planning/IMPLEMENTATION-REGISTER.md` (head + phase table) — milestone state

### Secondary (MEDIUM confidence)
- Project memory notes (offline-test-suite-targeted, dev-runtime, defer-live-verification) — operational conventions, consistent with backend/CLAUDE.md

### Tertiary (LOW confidence)
- None — no web research needed (project-internal domain).

## Metadata

**Confidence breakdown:**
- Edit anchors (five bodies): HIGH — files read in full, line numbers cited
- 13-03 precedent: HIGH — plan + summary read, test-suite grep confirms no persistent pin exists
- Harness/golden exposure: HIGH — goldens inspected byte-level (output_length 306 / 46, final_output verbatim)
- Resolver semantics: HIGH — regex read; first-match consequence is mechanical
- Live-adherence efficacy of the wording (A1/A2): MEDIUM — inherently probabilistic on live Haiku; covered by the locked live re-check / next-pass disposition

**Research date:** 2026-06-13
**Valid until:** stable while the branch is unchanged (project-internal facts; re-verify only if `agents/prompts/` or `tests/agents/` move under you)
