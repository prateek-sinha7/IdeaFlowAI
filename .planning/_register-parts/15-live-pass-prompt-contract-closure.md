## Phase 15 — Live-Pass Prompt Contract Closure (post-milestone)

**Folder:** `…/15-live-pass-prompt-contract-closure/`  ·  **Status:** Complete (2026-06-13) — VERIFICATION 5/5 truths verified, `status: passed`  ·  **Plans:** 3/3  ·  **Plan-id → §25:** (post-milestone — closes live-re-pass findings, maps to no plan-`§25` phase)
**Requirements delivered:** none new — closes the three prompt-shaped findings of the 2026-06-12 milestone-end live re-pass: **LV-02** (major, product) + the **F4** / **F5** earlier-live residuals. (Numbering note: LV-xx = the 2026-06-12 re-pass space; F4/F5 = earlier live-verification residuals — distinct id spaces, see `15-CONTEXT.md ## Phase Boundary`.) Tracked centrally in `.planning/ISSUES-REGISTER.md` (ISS-001 = LV-02 FIXED/live-confirmed; ISS-004/005 = F4/F5 DEFERRED). → see §6/§7.
**One-line outcome:** Five AGENT.md *prompt bodies* now carry output contracts — od-ppt-validator must re-emit the complete deck as its single `<artifact>` (so the `od_ppt` deliverable + the FR-014 revision chain carry a real deck, not QA narration), plus sdlc-governance anti-fabrication and app-infra-generator `/api/v1` contracts — with ZERO engine/capability/migration edits (SC-001).

### 1. Goal & Success Criteria (what was PLANNED)

Source: `ROADMAP.md ### Phase 15`, `15-CONTEXT.md`. Depends on **Phase 14** (the FR-014 revision chain / Phase-14 SC4 "revised deck in preview" was *blocked* by LV-02 — see `REPORT-2026-06-12.md` verdict row 6).

Five success criteria (`ROADMAP.md ### Phase 15` → "Success Criteria"):
1. **LV-02 closed** — `od-ppt-validator` AGENT.md carries an output contract (always re-emit the complete corrected deck wrapped in `<artifact>`); on a live `od_ppt` run the resolved `final_output` is the deck (`<section class="slide">`, not QA narration) and an FE-exact `od_ppt_output` revision returns a revised deck (Phase-14 SC4 content unblocked).
2. **sdlc-governance residual (F4) closed** — the `app-`/`dotnet-`/`mulesoft-sdlc-governance` bodies carry anti-fabrication contracts (begin directly with deliverable content; never emit tool-call syntax); live streams show zero `<function_calls>`/`<invoke>` preambles.
3. **infra-generator residual (F5) closed** — `app-infra-generator` makes the `/api/v1` prefix contract forceful and positionally prominent.
4. **Offline pins land** (13-03 precedent) — contract-grep tests for all five prompts + a scripted-model pin that the ppt deliverable resolution yields the validator's re-emitted deck; the 5 characterization goldens stay byte-identical.
5. **Live re-check recorded** — one `od_ppt` run + one revision (~$0.10) demonstrating criterion 1; criteria 2–3 may ride the session or defer to the next live pass (record disposition either way).

**Design wrinkle / REJECTED alternative (LOCKED — do not revisit):** the LV-02 fix is a *prompt output contract only*. The alternative — a **fallback inside the `deliverable: ppt` resolver** (scan earlier streams for the largest `<section>`-bearing artifact) — was **explicitly REJECTED** as an engine-side behavior change, INV-3-sensitive, contradicting the "streamed deck IS the deliverable" capability contract (`15-CONTEXT.md ## LV-02 fix approach (LOCKED)`). `agents/capabilities/deliverables/ppt.py` and `_artifact.py` are READ-ONLY anchors.

### 2. What Was Implemented — per plan (BUILT)

| Plan | Built | Key commits |
|------|-------|-------------|
| **15-01** (`15-01-SUMMARY.md`) | The five prompt-body output contracts — bodies only, frontmatter byte-untouched. od-ppt-validator: job statement rewritten judgment→re-emission, new `## OUTPUT CONTRACT — NON-NEGOTIABLE (read first)` above `## VALIDATION CHECKLIST`, old bottom contract DELETED (exactly one contract heading). 3× sdlc-governance: `OUTPUT CONTRACT (non-negotiable)` block (no-tools / never-emit-tool-XML / begin-directly) after the role line; app-sdlc's read_file-priming sentence defused. app-infra-generator: `API PATH CONTRACT` block (8 literal `/api/v1`) above `OUTPUT FORMAT`. | `cf5fb56b`, `3fff6879`, `dbcd88c8` |
| **15-02** (`15-02-SUMMARY.md`) | New durable pin file `backend/tests/agents/test_prompt_contracts.py` (11 nodes): prompt-body substring pins for all five contracts (via `load_agent_spec(id).prompt_body`), a frontmatter-freeze pin, and the **LV-02 composition test** — drives the real `od_ppt` pipeline through the REAL engine + REAL `PptResolver` with only a contract-shaped scripted validator (QA narration first, single artifact-wrapped deck second), asserting `final_output` is the deck and narration does not win. Then the full targeted offline gate proving the 5 characterization goldens byte-identical (INV-3). | `d4dc4861` |
| **15-03** (`15-03-SUMMARY.md`) | The cheap **live re-check** (D-05): one real-Haiku `od_ppt` run + one FE-exact `od_ppt_output` revision (~$0.10), with the disposition record `PHASE-15-RECHECK.md` + two saved live deck artifacts. LIVE branch ran (not deferred). | `ddaf367b`, `0d406521` |

### 3. Capabilities, Modules, Schema & API Added

**No engine, capability, factory, loader, registry, migration, or API changes** — this phase is bodies-only by mandate (SC-001). `git status --porcelain` on `agents/capabilities/`, `execution_engine/`, `factory.py`, `loader.py`, `registry.py` stayed empty across every phase commit (verified, `15-VERIFICATION.md` Behavioral Spot-Checks).

The five **prompt contracts** (refer to by name; do NOT rebuild — they already exist):
- `backend/agents/prompts/od-ppt-validator/AGENT.md` — deck re-emission contract: `## OUTPUT CONTRACT — NON-NEGOTIABLE (read first)`, demands **exactly ONE `<artifact>` = the complete corrected HTML deck**, positioned above `## VALIDATION CHECKLIST` (LV-02).
- `backend/agents/prompts/app-sdlc-governance/AGENT.md` — anti-fabrication contract; app-only "begin with the first `filename:` fenced block" (F4).
- `backend/agents/prompts/dotnet-sdlc-governance/AGENT.md` — anti-fabrication contract; "begin with the first Markdown heading" (no `filename:` contamination) (F4).
- `backend/agents/prompts/mulesoft-sdlc-governance/AGENT.md` — same as dotnet variant (F4).
- `backend/agents/prompts/app-infra-generator/AGENT.md` — `API PATH CONTRACT` block (8 literal `/api/v1`, healthcheck/nginx/smoke examples) above `OUTPUT FORMAT` (F5).

The one **new test file** (the durable pin layer — extend, don't duplicate):
- `backend/tests/agents/test_prompt_contracts.py` — 11 nodes pinning all five contracts + an extended frontmatter freeze + the LV-02 composition test. Asserts via `load_agent_spec(id).prompt_body` (parser-surviving, not raw file reads); the composition test injects a contract-shaped model via `drive_engine_pipeline(model=factory)` and imports `_scripted_model.py` helpers **import-only, zero edits** (that module's validator bytes ARE the `od_ppt` goldens).

### 4. What Was Deleted / Superseded (INV-12)

No code superseded — there is no dual-implementation to retire (bodies-only phase). Two prompt-body replacements only:
- od-ppt-validator's **old bottom `## OUTPUT CONTRACT`** section (with its fenced artifact example) was **deleted** so exactly one contract heading exists — its attribute-preservation guidance folded into the new top contract (`15-01-PLAN.md` Task 1 step 4; pinned by `## OUTPUT CONTRACT` count == 1).
- app-sdlc-governance's read_file-priming sentence ("Read the concrete choices … from the provided context") **replaced** by "Use the concrete choices … already provided in full in this message" (negative pin: `"Read the concrete choices"` absent).

The 13-02 factory-level `tool_availability` preamble was **left untouched** (it works for the other 14/15 agents); this phase only reinforces at the body level for the one agent family where live Haiku's process framing overrode the preamble (`15-CONTEXT.md ## sdlc-governance anti-fabrication (LOCKED)`).

### 5. Key Decisions & Locked Constraints (do NOT contradict)

- **Bodies-only / zero-engine-edit (SC-001) — LOCKED.** Every edit is below the closing frontmatter `---`; frontmatter is byte-frozen on all five agents (durable pin `test_contract_agents_frontmatter_frozen`, hardened by WR-03 to 8 fields × 5 agents). Do not "normalize" od-ppt-validator's intentional `tools: [workspace]` (RESEARCH Pitfall 4).
- **REJECTED: a `deliverable: ppt` resolver fallback** for LV-02 — engine-side, INV-3-sensitive (§1). `ppt.py` / `_artifact.py` are READ-ONLY. A future agent must NOT "fix" any od_ppt deliverable regression by editing the resolver; the fix lives in the validator's output contract.
- **exactly-ONE-artifact wording, never "last/final artifact"** — `unwrap_artifact` is **first-match** (`_artifact.py:34-38`, attribute-tolerant `<artifact[^>]*>`); a leading status artifact would otherwise win the unwrap and reproduce LV-02 (`15-01-SUMMARY.md` Decisions; RESEARCH Pitfall 2).
- **Anti-tool-XML line byte-identical across the 3 sdlc bodies; deliverable-start line tailored** — app = `filename:` fenced block, dotnet/mulesoft = first Markdown heading; importing the filename-block phrase into the migration prompts would change their deliverable format (Pitfall 5).
- **Forbidden tokens named exactly once per body, terse, no multi-line bad-example exemplars** — exemplars re-prime fabrication (Pitfall 7; pinned `body.count(token) == 1` per WR-04).
- **Live verification is non-blocking** (project defer-live-verification convention / D-05): phase completes on offline evidence; criteria 2–3 may be recorded as next-live-pass items.

### 6. Status, Verification & Evidence (what HAPPENED)

- **`15-VERIFICATION.md`: PASSED, 5/5 truths verified** (2026-06-13T02:05Z) — verifier re-executed suites, did not trust SUMMARY claims. Spot-checks: `test_prompt_contracts.py` 11 passed (0.81s); 8-file characterization battery 88 passed / 7 skipped (env-gated), 35.66s; `lint-imports` 4 kept / 0 broken; SC-001 fence diff `6be0c314..80118cf7` = only the 5 AGENT.md + the test file.
- **Review → fix arc:** `15-REVIEW.md` found **0 critical, 4 warning (WR-01..WR-04), 2 info (IN-01/IN-02)** — all defects were contract self-consistency / pins weaker than their own documented intent. `15-REVIEW-FIX.md`: **4/4 WR fixed** (WR-01 od-ppt-validator precedence rule "OUTPUT CONTRACT outranks the checklist" + bounded-P1 disambiguation, `aa33d5ea`; WR-02 assumptions-inside-file-block for app-sdlc, `e0cc2e84`; WR-03 frontmatter freeze widened 3→8 fields, `0557423f`; WR-04 exactly-once token + `filename:`-negative pins, `7b507ce7`). IN-01/IN-02 left documented (out of fix-scope).
- **`15-SECURITY.md`: verified, 10/10 threats closed, threats_open: 0** — re-derived (not doc-trusted): frontmatter-key diff empty, fence porcelain empty, gate re-run 99 passed / 7 skipped, golden porcelain 0 lines, 12-digit + credential leak screens on the live artifacts clean, zero package installs.
- **SC5 LIVE re-check — CLOSED live** (`PHASE-15-RECHECK.md`): od_ppt run `8c060c35` resolved `final_output` to the **real 18,661-char deck** (first line `<!DOCTYPE html>`, 5 `<section class="slide">`) — the 2026-06-12 failure shape (1,350-char QA narration winning over the 21,394-char deck) did not recur; validator streamed ~1,046 chars commentary then **exactly ONE** artifact = the deck. FE-exact `od_ppt_output` revision `4a027d51` returned a genuinely revised deck (title change applied, `cmp` differs) — FR-014 chain fed the deck, not narration. Cost **$0.092** (~$0.10 budget held). Saved: `artifacts/phase15-od-ppt-final.html`, `…-revision.html`.

### 7. Gotchas, Survivors & Carry-Forward

- **F4/F5 live re-confirm is DEFERRED to the next live pass** (`PHASE-15-RECHECK.md` F4/F5 sections → `ISSUES-REGISTER.md` ISS-004 / ISS-005, both DEFERRED). The contracts shipped + are offline-pinned, but the live-stream behaviour was NOT chased this session (app_builder / migration live runs gated by the ~$0.10 cost fence). **Named next-pass checks already exist:** F4 — zero `<function_calls>`/`<invoke>`/`write_todos` preamble lines across the three sdlc-governance live streams (2026-06-12 baseline: 10 fabricated elements); F5 — `/api/v1` occurrence count in app-infra-generator's live output clearly non-zero vs api-design 58× / devops 50× (baseline: 0× in 3,083 lines). A future agent re-confirming these should run a live app_builder pass, not re-edit the prompts.
- **The validator's pre-artifact commentary overran the contract's "at most two short sentences" cap (~1,046 chars) on live Haiku** — recorded as a **non-load-bearing adherence note** (`15-03-SUMMARY.md` Decisions): the load-bearing clauses (exactly ONE artifact / complete deck / nothing after) held and resolution was correct. Don't treat this as a regression.
- **Stale `_SPEC_CACHE` hazard:** the long-running backend caches prompt specs; the live driver **restarted the backend before driving** so the 15-01 edits loaded fresh (`15-03-SUMMARY.md` Issues). Any future live re-check of a prompt edit must do the same.
- **LV-01 and LV-03 are NOT this phase** — both are test-infra findings (LV-01 = `wait_for` cancel-race at `websocket.py`; LV-03 = token-delta clarify hang), explicitly out of scope and deferred separately (`15-CONTEXT.md ## Deferred Ideas`). Don't conflate them with the prompt closures.
- **INV-3 proof the goldens were untouched:** od_ppt and app_builder ARE characterization pipelines, yet the 5 snapshot goldens stayed byte-identical because **the scripted model ignores prompt-body content** (Phase-3 documented caveat) — prompt bodies are not characterization inputs. The gate ran with `SNAPSHOT_UPDATE` absent and `git status --porcelain golden/` = 0 lines (`15-02-SUMMARY.md` Phase Gate Evidence). A future prompt-body edit to any of these five agents will likewise not perturb goldens — but re-run the targeted characterization battery to prove it.

### 8. File Index (every file in this folder)

| File | Role |
|------|------|
| `15-CONTEXT.md` | Locked decisions (D-01..D-05), in-/out-of-scope, canonical refs, deferred ideas — gathered from the live-pass closure discussion (no interactive discuss round). |
| `15-RESEARCH.md` | Implementation research: current prompt bodies, resolver anchor, harness pin design, validation architecture, pitfalls (1–7) — the HOW for 15-01/02. |
| `15-VALIDATION.md` | Per-phase validation template — **left as an unfilled stub** (not populated this phase). |
| `15-01-PLAN.md` / `15-01-SUMMARY.md` | The five prompt-body contracts (LV-02 + F4 + F5), bodies only; exact shipped contract wording recorded for 15-02 to pin. |
| `15-02-PLAN.md` / `15-02-SUMMARY.md` | `test_prompt_contracts.py` durable pins + LV-02 composition test + the INV-3 byte-identical-goldens phase gate. |
| `15-03-PLAN.md` / `15-03-SUMMARY.md` | The live re-check (LIVE branch ran, $0.092) + `PHASE-15-RECHECK.md` disposition record. |
| `15-REVIEW.md` | Code review: 0 critical, WR-01..WR-04, IN-01/IN-02. |
| `15-REVIEW-FIX.md` | 4/4 WR fixed (commits `aa33d5ea`/`e0cc2e84`/`0557423f`/`7b507ce7`); IN-01/IN-02 documented out-of-scope. |
| `15-SECURITY.md` | 10/10 threats closed, threats_open 0; AR-15-01..03 accepted risks. |
| `15-VERIFICATION.md` | Goal-backward verification: 5/5 truths verified, `status: passed`. |

*Cross-references (outside this folder): `.planning/live-verification/REPORT-2026-06-12.md` (LV-01/02/03 definitions), `.planning/live-verification/PHASE-15-RECHECK.md` (SC5 live disposition + saved deck artifacts), `.planning/ISSUES-REGISTER.md` (ISS-001 FIXED, ISS-004/005 DEFERRED).*
