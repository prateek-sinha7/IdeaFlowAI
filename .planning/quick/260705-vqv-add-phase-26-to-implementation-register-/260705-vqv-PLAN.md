---
phase: quick-260705-vqv
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - .planning/IMPLEMENTATION-REGISTER.md
autonomous: true
requirements:
  - DOCS-P26
must_haves:
  truths:
    - "A new `## Phase 26 — Cost, Caching, Cache-Token Accounting & Pricing Single-Source (post-milestone)` section exists at the END of IMPLEMENTATION-REGISTER.md"
    - "The Phase 26 section is a structural peer of Phase 25 (same subsection headers, same bold-line shape)"
    - "All 5 quick tasks (p10, t2x, ttk, uvs, ed8) each have their own bullet under `### The 5 quick tasks`"
    - "The `### Key locked decisions (do NOT contradict)` subsection captures the single-source, Bedrock-only caching, subtract-cached-tokens, thinking default-OFF, and regional-premium decisions"
    - "No file other than IMPLEMENTATION-REGISTER.md is modified"
  artifacts:
    - path: ".planning/IMPLEMENTATION-REGISTER.md"
      provides: "Phase 26 register section (append-only)"
      contains: "## Phase 26 — Cost, Caching, Cache-Token Accounting & Pricing Single-Source"
  key_links:
    - from: ".planning/IMPLEMENTATION-REGISTER.md Phase 25 section"
      to: "new Phase 26 section"
      via: "appended after the last line (Phase 26 follows Phase 25 with a `---` separator)"
      pattern: "## Phase 26 — Cost, Caching"
---

<objective>
Append a single new `## Phase 26 — Cost, Caching, Cache-Token Accounting & Pricing Single-Source (post-milestone)` section to the END of `.planning/IMPLEMENTATION-REGISTER.md`, documenting this session's 5 cost/caching/pricing quick tasks (p10, t2x, ttk, uvs, ed8) as a structural peer of the existing Phase 25 section.

Purpose: IMPLEMENTATION-REGISTER.md is the pointer-first, code-free doc a future agent reads BEFORE any fix/feature to avoid duplicating code or contradicting locked decisions. The `### Key locked decisions (do NOT contradict)` subsection is the load-bearing part — it must accurately encode the single-source pricing, Bedrock-only caching, subtract-cached-tokens cost math, and thinking-default-OFF rules so no future change silently reverses them.

Output: One appended `## Phase 26` section in `.planning/IMPLEMENTATION-REGISTER.md`. No other file touched.
</objective>

<execution_context>
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/.claude/gsd-core/workflows/execute-plan.md
</execution_context>

<context>
# The exact structural template to clone — read this FIRST and copy its markdown shape verbatim
# Phase 25 section lives at ~lines 2499-2545 (currently the LAST section in the file)
@.planning/IMPLEMENTATION-REGISTER.md

# Evidence sources — READ each SUMMARY + VERIFICATION for accuracy; DO NOT invent facts
@.planning/quick/260704-p10-bedrock-prompt-caching-thinking-config-k/260704-p10-SUMMARY.md
@.planning/quick/260704-p10-bedrock-prompt-caching-thinking-config-k/260704-p10-VERIFICATION.md
@.planning/quick/260704-t2x-per-model-region-aware-run-cost-pricing/260704-t2x-SUMMARY.md
@.planning/quick/260704-t2x-per-model-region-aware-run-cost-pricing/260704-t2x-VERIFICATION.md
@.planning/quick/260704-ttk-iss-032-capture-prompt-cache-tokens-for-/260704-ttk-SUMMARY.md
@.planning/quick/260704-ttk-iss-032-capture-prompt-cache-tokens-for-/260704-ttk-VERIFICATION.md
@.planning/quick/260704-uvs-show-prompt-cache-token-breakdown-in-ui/260704-uvs-SUMMARY.md
@.planning/quick/260704-uvs-show-prompt-cache-token-breakdown-in-ui/260704-uvs-VERIFICATION.md
@.planning/quick/260705-ed8-model-pricing-inv12-single-source/260705-ed8-SUMMARY.md
@.planning/quick/260705-ed8-model-pricing-inv12-single-source/260705-ed8-VERIFICATION.md

# Cross-reference registers for FIX-IDs and ISS-IDs
@.planning/FIX-REGISTER.md
@.planning/ISSUES-REGISTER.md
</context>

<tasks>

<task type="auto">
  <name>Task 1: Append the Phase 26 section to IMPLEMENTATION-REGISTER.md</name>
  <files>.planning/IMPLEMENTATION-REGISTER.md</files>
  <action>
APPEND ONLY. Do not modify Phase 1-25 or any other line of the file; do not touch any other file (no STATE.md — the orchestrator owns the STATE row for this docs task).

Step 1 — Clone the shape. Read the existing Phase 25 section (`## Phase 25 — Revision Families & Run-Inputs Surfacing (post-milestone)`, ~lines 2499-2545, currently the file's last section) and copy its EXACT markdown shape for the new section:
  - A leading `---` separator, then the `## Phase 26 — Cost, Caching, Cache-Token Accounting & Pricing Single-Source (post-milestone)` heading.
  - A bold lead block with `**Folder:** … · **Status:** … · **Plans:** …` line, then `**Requirements delivered:**`, then `**Driver:**`, then a `**One-line outcome:**` line — matching Phase 25's spacing and the ` · ` inline separators.
  - Then these `###` subsections IN THIS ORDER (peer to Phase 25): `### The 5 quick tasks`, `### Where the code lives (as-built)`, `### Key locked decisions (do NOT contradict)`, `### Invariants & verification`, `### Known follow-ups (out of scope)`.
Keep it pointer-first and code-free: describe behavior, cite identifiers in `backticks`, use `→ file` pointers. DO NOT paste code, function bodies, or fenced code blocks.

Step 2 — Fill content from the SUMMARYs/VERIFICATIONs (verify every claim; do not invent). The section MUST capture the material below — confirm each against the read evidence, correcting any detail that the SUMMARY/VERIFICATION contradicts:

  `### The 5 quick tasks` — one bullet per task:
  - p10 — Bedrock prompt caching config-gated default-ON via `_BedrockCachePointsMiddleware` on `ChatBedrockConverse` only + extended-thinking `THINKING_BUDGET_TOKENS` enable-only default-OFF, clamped `[1024, max_tokens-1]`, `temperature=1`; both `build_model` branches; commit `5346c242`.
  - t2x — per-model/region-aware pricing: both cost sites previously hardcoded Claude-3-Haiku `$0.25/$1.25`/M → under-report 4-20x; new kernel-pure `model_pricing.py` + shared `estimate_cost_usd` + regional premium; commit `4d949f9a`; superseded internally by ed8.
  - ttk / ISS-032 — runner `_cache_token_counts` surfaces `input_token_details` → engine accumulates → BOTH cost sites price the uncached split `input=max(0, total-cache_read-cache_write)` + cache_read 0.1x + cache_write 1.25/2x, no double-count; golden-neutral via additive `_VOLATILE_STRIP_KEYS`; commit `16b89f03`.
  - uvs — FE `⚡ N cached (X%)` in `TokenUsageSummary`, byte-identical when 0; no FE dollar math; commit `3d8ff806`.
  - ed8 — INV-12 single-source restore of a t2x regression: frozen `Pricing` dataclass + `pricing` field on `ModelEntry` in `model_catalog.py`; `model_pricing.py` DERIVES from the catalog with ZERO model-id literals; `$24.85` reconciliation pin preserved; commit `102135ed`, FIX-038.

  `**Driver:**` — user's high AWS Bedrock bill → gut-feel investigation confirmed 21.46M input tokens = ~$24.85/build REAL (from Bedrock `usage_metadata`, not a counting bug); root causes = caching silently OFF on Bedrock + cost under-reported 4-20x + cache tokens unaccounted + no UI visibility + t2x's own INV-12 regression.

  `### Where the code lives (as-built)` — pointers only:
  `backend/app/agents/model_factory.py`; `backend/app/agents/deep_agent_runner.py` (`_BedrockCachePointsMiddleware` + `_cache_token_counts`); `backend/app/core/config.py` (`BEDROCK_PROMPT_CACHE_ENABLED`/`_TTL`, `THINKING_BUDGET_TOKENS`); `backend/agents/capabilities/model_pricing.py` + `model_catalog.py` (frozen `Pricing`/`pricing`/`estimate_cost_usd`/`_resolve_pricing`/`_regional_premium`); `backend/agents/execution_engine/engine.py` + `backend/app/api/websocket.py` (both cost sites); `backend/tests/agents/characterization/_normalize.py` (`_VOLATILE_STRIP_KEYS`); FE `TokenUsageSummary.tsx` / `useWorkflow.ts` / `types/index.ts`.

  `### Key locked decisions (do NOT contradict)` — the load-bearing subsection; capture all five:
  (a) Pricing DERIVES from `model_catalog.py`'s frozen `Pricing` field; `model_pricing.py` has ZERO `claude-(haiku|sonnet|opus)-4` literals; `test_model_catalog::test_single_source_grep` enforces it; do NOT add a 2nd model list OR pricing table — this EXTENDS the Phase-06 locked single-source decision; ed8 restored this after t2x broke it.
  (b) Caching is Bedrock-only via `_BedrockCachePointsMiddleware` (no-op on ChatAnthropic/scripted; deepagents' `AnthropicPromptCachingMiddleware` covers ChatAnthropic), gated `BEDROCK_PROMPT_CACHE_ENABLED` default ON, TTL 5m.
  (c) Cost math SUBTRACTS cached tokens (langchain_aws sets `input_tokens`=TOTAL incl. cache, split in `input_token_details`) via the ONE shared `estimate_cost_usd` — never double-count.
  (d) Thinking enable-only, default OFF.
  (e) Regional premium +10% for `eu.`/`us.`/`apac.` (region strings, not model-id literals).

  `### Invariants & verification`:
  INV-3 (5 goldens byte/event-identical; `cost` + `model_id` are `_VOLATILE_STRIP_KEYS` + 4 additive cache keys; NO regen, `SNAPSHOT_UPDATE` unset), INV-12 (one `estimate_cost_usd`; single model+pricing source restored by ed8), INV-13 (deepagents middleware/kwargs only), SC-001 (isinstance/`model_id` dispatch). Evidence: goldens 10/10; model_pricing+iss032 39; model_catalog 9 incl `single_source_grep` GREEN; bedrock cache/thinking 10; lint 4/0.

  `### Known follow-ups (out of scope)`:
  ISS-033 (SmartPlanner `smart_planner.py:389` + ClarifyEngine `clarify_engine.py:492-493` + handoff agents call the model DIRECTLY, bypassing the runner → no caching + uncounted cost, ~150k tok/450k brief — the last caching-everywhere gap); ISS-034 (dollar-savings display via `estimated_cost_full_usd`); live Bedrock `cache_read>0` confirmation deferred to end-of-milestone; adjacent same-window tasks er8 (FIX-033) + d4v (FIX-029) → STATE quick-tasks table.

Reconcile all FIX-IDs (FIX-034..038) and ISS-IDs (ISS-032/033/034) against `.planning/FIX-REGISTER.md` and `.planning/ISSUES-REGISTER.md` while writing — cite them where the corresponding fact appears.
  </action>
  <verify>
    <automated>test "$(git diff --name-only .planning/IMPLEMENTATION-REGISTER.md | wc -l | tr -d ' ')" = "1" && grep -q '^## Phase 26 — Cost, Caching, Cache-Token Accounting & Pricing Single-Source (post-milestone)$' .planning/IMPLEMENTATION-REGISTER.md && grep -q '^### Key locked decisions (do NOT contradict)$' .planning/IMPLEMENTATION-REGISTER.md && for id in p10 t2x ttk uvs ed8; do grep -q "$id" .planning/IMPLEMENTATION-REGISTER.md || { echo "MISSING task $id"; exit 1; }; done && test "$(git diff --name-only | grep -v '^.planning/IMPLEMENTATION-REGISTER.md$' | wc -l | tr -d ' ')" = "0"</automated>
  </verify>
  <done>
`.planning/IMPLEMENTATION-REGISTER.md` ends with a new `## Phase 26 — Cost, Caching, Cache-Token Accounting & Pricing Single-Source (post-milestone)` section that reads as a structural peer of Phase 25 (same six subsection headers: bold lead block, `### The 5 quick tasks`, `### Where the code lives (as-built)`, `### Key locked decisions (do NOT contradict)`, `### Invariants & verification`, `### Known follow-ups (out of scope)`); all 5 tasks (p10, t2x, ttk, uvs, ed8) and all five locked decisions are present and accurate; `git diff --name-only` for the code commit shows ONLY `.planning/IMPLEMENTATION-REGISTER.md`.
  </done>
</task>

</tasks>

<verification>
- `.planning/IMPLEMENTATION-REGISTER.md` is the ONLY changed file (`git diff --name-only`).
- The appended section is byte-append (Phase 1-25 content unchanged — verify Phase 25 still ends at its prior `Window-vs-authoritative version count` bullet, with a `---` separator before the new `## Phase 26` heading).
- All 5 task ids + all five locked decisions present; content matches the SUMMARY/VERIFICATION evidence (no invented facts).
- Docs-only, no code, no packages, no trust boundaries crossed → STRIDE threat model N/A.
</verification>

<success_criteria>
- New `## Phase 26` section exists at the end of the register, a structural peer of Phase 25.
- The 5 quick tasks (p10, t2x, ttk, uvs, ed8) and the five key locked decisions are captured accurately and pointer-first (code-free).
- No file other than `.planning/IMPLEMENTATION-REGISTER.md` is modified.
- Single commit: `docs(register): add Phase 26 — cost/caching/cache-token accounting & pricing single-source` (NO Co-Authored-By, NO Claude-Session trailer).
</success_criteria>

<output>
Update `.planning/quick/260705-vqv-add-phase-26-to-implementation-register-/260705-vqv-SUMMARY.md` when done.
</output>
