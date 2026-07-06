---
phase: quick-260704-uvs
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - frontend/src/types/index.ts
  - frontend/src/hooks/useWorkflow.ts
  - frontend/src/components/workflow/TokenUsageSummary.tsx
  - frontend/src/components/workflow/TokenUsageSummary.cache.test.tsx
  - .planning/FIX-REGISTER.md
  - .planning/ISSUES-REGISTER.md
  - .planning/STATE.md
autonomous: true
requirements: [FIX-037]
must_haves:
  truths:
    - "When a cached run completes, the token summary renders a '⚡ N cached (X%)' segment after the input figure"
    - "When cacheReadTokens is 0 or undefined, the token summary renders exactly as today (zero regression)"
    - "cacheReadTokens/cacheWriteTokens flow from the pipeline_complete WS event into pipelineState"
    - "The persisted/history tokenUsage type carries total_cache_read_tokens/total_cache_write_tokens (parsed, no logic change in api.ts)"
    - "Cost figure is unchanged (already cache-discounted by FIX-036) — no FE dollar math added"
  artifacts:
    - path: "frontend/src/types/index.ts"
      provides: "Optional cache fields on tokenUsage + PipelineRunState"
      contains: "total_cache_read_tokens"
    - path: "frontend/src/hooks/useWorkflow.ts"
      provides: "cacheReadTokens/cacheWriteTokens threaded from WS events into pipelineState"
      contains: "total_cache_read_tokens"
    - path: "frontend/src/components/workflow/TokenUsageSummary.tsx"
      provides: "Conditional cached-tokens segment"
      contains: "cacheReadTokens"
    - path: "frontend/src/components/workflow/TokenUsageSummary.cache.test.tsx"
      provides: "Rendered-DOM specs for cached and no-cache cases"
  key_links:
    - from: "frontend/src/hooks/useWorkflow.ts"
      to: "pipelineState.cacheReadTokens"
      via: "pipeline_complete handler reads msg.total_cache_read_tokens"
      pattern: "cacheReadTokens:.*total_cache_read_tokens"
    - from: "frontend/src/components/workflow/TokenUsageSummary.tsx"
      to: "pipelineState.cacheReadTokens"
      via: "render gate cacheReadTokens > 0"
      pattern: "cacheReadTokens"
---

<objective>
Surface the prompt-cache token breakdown in the workflow token-usage UI. The backend (ISS-032 / FIX-036) already emits per-run `total_cache_read_tokens` / `total_cache_write_tokens` in the `pipeline_complete` `token_usage` payload AND in the persisted `workflow_runs.token_usage`, and `estimated_cost_usd` is already cache-discounted — but the FE never surfaces the cache split (grep of `frontend/src` for cache tokens = nothing today).

This is FRONTEND-ONLY. Consume the already-emitted fields: thread them through the types + WS parse, then render a compact "⚡ N cached (X%)" segment when `cache_read > 0`. No backend change, no golden touch, no per-model rate math on the FE (INV-12 — the discounted cost is already shown).

Purpose: Make prompt-cache savings visible to operators now that FIX-034 caching is ON in prod.
Output: Threaded cache fields, a conditional cached segment (byte-identical render when cache=0), rendered-DOM tests, and register/state docs.
</objective>

<execution_context>
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/.claude/gsd-core/workflows/execute-plan.md
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@CLAUDE.md

# Read-first source (contracts + current shapes)
@frontend/src/types/index.ts            # tokenUsage type ~L281-292 · PipelineRunState ~L535-546
@frontend/src/hooks/useWorkflow.ts      # agent_complete handler ~L288-318 · pipeline_complete handler ~L343-392
@frontend/src/components/workflow/TokenUsageSummary.tsx   # single-line render ~L33-69
@frontend/src/lib/api.ts                # normalizeWorkflowRun JSON.parse(token_usage) ~L284-289 (VERIFY no logic change)
</context>

<interface_contract>
Cache field names — use these EXACT keys (they are what the backend already emits / persists):

- WS `pipeline_complete` message + persisted `token_usage` JSON:
  - `total_cache_read_tokens?: number`
  - `total_cache_write_tokens?: number`
- `PipelineRunState` (camelCase, sibling of `totalInputTokens`):
  - `cacheReadTokens?: number`
  - `cacheWriteTokens?: number`

Derived display values (computed in TokenUsageSummary, NOT stored):
- `cacheRead = cacheReadTokens ?? 0`
- `cacheWrite = cacheWriteTokens ?? 0`
- `pct = Math.round(cacheRead / Math.max(1, input) * 100)`   // input = totalInputTokens ?? 0
</interface_contract>

<tasks>

<task type="auto" tdd="false">
  <name>Task 1: Thread cache fields through types + WS parse</name>
  <files>frontend/src/types/index.ts, frontend/src/hooks/useWorkflow.ts, frontend/src/lib/api.ts (verify-only, expect no edit)</files>
  <action>
    In `frontend/src/types/index.ts`:
    - On the `WorkflowRun.tokenUsage` inline object type (~L281-292), add two OPTIONAL fields next to `estimated_cost_usd`: `total_cache_read_tokens?: number;` and `total_cache_write_tokens?: number;`. This makes the already-parsed persisted/history keys type-visible (see interface_contract).
    - On `PipelineRunState` (~L542-546), add two OPTIONAL fields as siblings of `estimatedCostUsd`: `cacheReadTokens?: number;` and `cacheWriteTokens?: number;`.

    In `frontend/src/hooks/useWorkflow.ts`, thread the cache totals into `pipelineState` in BOTH token-writing handlers, using the SAME `|| prev.* || 0` fallback idiom already used by the sibling token fields:
    - `pipeline_complete` handler (the return object ~L385-388, where `totalInputTokens`/`estimatedCostUsd` are set): add `cacheReadTokens: (msg.total_cache_read_tokens as number) || prev.cacheReadTokens || 0,` and `cacheWriteTokens: (msg.total_cache_write_tokens as number) || prev.cacheWriteTokens || 0,`. This is the authoritative per-run source (backend emits run-level cache totals here).
    - `agent_complete` handler (the return object ~L310-317, where `totalInputTokens` is accumulated): add the same two lines with the identical `(msg.total_cache_read_tokens as number) || prev.cacheReadTokens || 0` fallback. `msg` here carries no run-level cache total, so this simply PRESERVES `prev` (harmless, keeps the value stable across mid-run events) — matching the description's "read in the WS handler(s)" intent.

    In `frontend/src/lib/api.ts`: VERIFY ONLY — `normalizeWorkflowRun` already does `tokenUsage = JSON.parse(raw.token_usage)` (~L287), which carries the cache keys verbatim; the Task-1 type change makes them visible. Do NOT add logic. No reopen path currently maps `tokenUsage` → `PipelineRunState`-shaped fields (confirmed: only `useWorkflow.ts` sets those pipelineState fields), so no additional mapping is required. If tsc surfaces a genuine need, add ONLY the field mapping — no behavior change.

    Do NOT touch `WorkflowHistory.tsx` (its inline token block is out of scope) or `AnalyticsPage.tsx` (deferred — see notes). Do NOT add any per-model rate or dollar-savings math (INV-12).
  </action>
  <verify>
    <automated>cd frontend && node_modules/.bin/vitest run useWorkflow && frontend_tsc() { :; }; ../frontend/node_modules/.bin/tsc -p tsconfig.json --noEmit 2>&1 | grep -v "e2e/fixtures/mockApi.ts" | grep -E "error TS" | grep -c . | grep -qx 0 && echo TSC_CLEAN</automated>
  </verify>
  <done>Both handlers set `cacheReadTokens`/`cacheWriteTokens` with the `|| prev.* || 0` fallback; types expose the optional cache fields; `vitest run useWorkflow` is green; tsc reports ZERO new errors (only the 2 pre-existing `e2e/fixtures/mockApi.ts` errors remain).</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Render conditional cached segment + rendered-DOM tests</name>
  <files>frontend/src/components/workflow/TokenUsageSummary.tsx, frontend/src/components/workflow/TokenUsageSummary.cache.test.tsx</files>
  <behavior>
    - cacheReadTokens=60000 with totalInputTokens=70000 → a segment containing text "cached" and "86%" and "60.0K" renders (pct = Math.round(60000/70000*100) = 86; formatTokens(60000) = "60.0K").
    - cacheReadTokens=0 → NO element containing "cached" renders; the input/output/total spans render exactly as today (zero regression).
    - cacheReadTokens undefined → NO "cached" segment (identical to the 0 case).
    - cacheWriteTokens>0 alongside cacheRead>0 → an additional "written" fragment renders; cacheWriteTokens=0 → no "written" fragment.
  </behavior>
  <action>
    In `frontend/src/components/workflow/TokenUsageSummary.tsx`:
    - Destructure `cacheReadTokens` and `cacheWriteTokens` from `pipelineState` alongside the existing token fields (~L34).
    - Compute `const cacheRead = cacheReadTokens ?? 0;`, `const cacheWrite = cacheWriteTokens ?? 0;`, and (only when rendering) `const pct = Math.round(cacheRead / Math.max(1, input) * 100);` where `input = totalInputTokens ?? 0` (already computed at ~L39).
    - Insert the cached segment INTO the existing flex row, positioned AFTER the input span (~L60-62) and BEFORE the output separator (~L63). Wrap it so it only renders when `cacheRead > 0`: a `·` separator span (matching the existing `text-[10px] text-gray-400` dividers), then a span reading `⚡ {formatTokens(cacheRead)} cached ({pct}%)` (use the existing `formatTokens` helper; style it as a subtle accent, e.g. `text-[10px] text-amber-600 flex-shrink-0`). Optionally, still inside the same `cacheRead > 0` block, when `cacheWrite > 0`, append ` · {formatTokens(cacheWrite)} written`.
    - The cost figure and every existing span stay UNCHANGED. When `cacheRead === 0` the component must render EXACTLY as today (the whole cached fragment is behind the `cacheRead > 0` gate — no separator, no span). Do NOT add dollar-savings text (INV-12).

    Create `frontend/src/components/workflow/TokenUsageSummary.cache.test.tsx`:
    - Use `@testing-library/react` `render` + `screen` (match the harness style of existing `*.test.tsx` in the repo; vitest + jsdom is already configured via `frontend/vitest.config.ts`).
    - Build a minimal valid `PipelineRunState` base (required fields: `isRunning`, `pipeline_type`, `agents: []`, `currentAgentIndex`, `totalDuration`, `completedCount`) and spread token fields per case; cast with `as PipelineRunState` if convenient. `motion/react` renders to a plain div in jsdom — no mock needed, but stub it if it complains.
    - Spec A (cached): `{ ...base, totalTokens: 100000, totalInputTokens: 70000, totalOutputTokens: 30000, cacheReadTokens: 60000 }` → assert the DOM text contains "cached", "86%", and "60.0K".
    - Spec B (no cache): `{ ...base, totalTokens: 100000, totalInputTokens: 70000, totalOutputTokens: 30000 }` (cacheReadTokens undefined) → assert `screen.queryByText(/cached/i)` is null AND input/output text still present (zero regression).
    - Spec C (write): add `cacheWriteTokens: 5000` to Spec A input → assert text contains "written"; and a variant with `cacheWriteTokens: 0` asserts no "written".
  </action>
  <verify>
    <automated>cd frontend && node_modules/.bin/vitest run TokenUsageSummary</automated>
  </verify>
  <done>`vitest run TokenUsageSummary` is green including the new `TokenUsageSummary.cache.test.tsx`; the cached segment renders only when `cacheRead > 0`; the no-cache render is unchanged from today.</done>
</task>

<task type="auto" tdd="false">
  <name>Task 3: Docs — FIX-037, ISS-034, STATE + quick doc</name>
  <files>.planning/FIX-REGISTER.md, .planning/ISSUES-REGISTER.md, .planning/STATE.md</files>
  <action>
    In `.planning/FIX-REGISTER.md`, add a new 8-column row (header: `Fix ID | Date | Description | Root Cause | Files Changed | Phase Involved | Invariants | Status`) directly after the FIX-036 row:
    - Fix ID: `FIX-037`; Date: `2026-07-04`.
    - Description: cache-token breakdown not shown in UI — backend (ISS-032/FIX-036) emits per-run `total_cache_read_tokens`/`total_cache_write_tokens` + already-discounted `estimated_cost_usd`, but `TokenUsageSummary` showed only total/input/output/cost.
    - Root Cause: FE never consumed the already-emitted cache fields (grep of `frontend/src` for cache tokens = nothing); no reopen path mapped them either.
    - Fix (FE-only): thread the cache fields (types + `useWorkflow` `pipeline_complete`/`agent_complete` parse + `api.ts` persisted keys type-visible, no logic change) + render a "⚡ N cached (X%)" segment when `cache_read > 0` (byte-identical render when 0); dollar-savings deferred (ISS-034).
    - Files Changed: `frontend/src/types/index.ts`, `frontend/src/hooks/useWorkflow.ts`, `frontend/src/components/workflow/TokenUsageSummary.tsx`, `frontend/src/components/workflow/TokenUsageSummary.cache.test.tsx`.
    - Phase Involved: `quick-260704-uvs`; Invariants: `INV-1/3/12 · SC-001 ✅`; Status: `Done`.

    In `.planning/ISSUES-REGISTER.md`, append a new 6-column row (header: `ID | Sev | Tag | Status | Title | Source / Evidence`) after ISS-033:
    - ID: `ISS-034`; Sev: `minor`; Tag: `product`; Status: `OPEN` (new follow-up).
    - Title: optional dollar-savings — surface cache $ saved. Backend would emit `estimated_cost_full_usd` (cost as-if-uncached) → FE shows "saved $Y (Z%)". Needs a backend add-on (per-model rates live backend-side per INV-12); explicitly NOT built in FIX-037 (which shows only the token count + %).
    - Source / Evidence: split out of quick-260704-uvs (FIX-037); companion to FIX-036/ISS-032.

    In `.planning/STATE.md`, record the quick item completion in the same style as recent quick entries (progress log / recent-fixes area): note quick-260704-uvs / FIX-037 done, FE-only cache-token surfacing, ISS-034 logged as the deferred dollar-savings follow-up. Follow the existing STATE.md format quirk — update the narrative/progress fields, do not rely on the `status:` enum.
  </action>
  <verify>
    <automated>grep -q "FIX-037" .planning/FIX-REGISTER.md && grep -q "ISS-034" .planning/ISSUES-REGISTER.md && grep -q "260704-uvs" .planning/STATE.md && echo DOCS_OK</automated>
  </verify>
  <done>FIX-037 row present in FIX-REGISTER (8 columns, after FIX-036); ISS-034 appended in ISSUES-REGISTER (after ISS-033, status OPEN); STATE.md records the quick-260704-uvs completion + ISS-034 follow-up.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| WS `pipeline_complete` message → pipelineState → UI render | Numeric token counts cross from the backend into the DOM. Already-trusted channel (same as existing token totals). |
| Persisted `workflow_runs.token_usage` JSON → `JSON.parse` → history/analytics | Already parsed today; this change only adds type visibility to existing keys. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-uvs-01 | Information disclosure | TokenUsageSummary render | accept | Displays only aggregate token counts already shown for input/output; no PII, no secrets, no new data source. |
| T-uvs-02 | Tampering | numeric cache fields | mitigate | All cache values coerced via `(x as number) \|\| … \|\| 0` / `?? 0` and clamped by `Math.max(1, input)`, so a missing/NaN/negative field degrades to the zero-cache (no-regression) render — never crashes or shows the segment spuriously. |
| T-uvs-SC | Tampering | npm/pip/cargo installs | accept | No package installs in this plan (FE consumes existing deps only) — no supply-chain surface added. |
</threat_model>

<verification>
- `cd frontend && node_modules/.bin/vitest run TokenUsageSummary useWorkflow` → all green including the new `TokenUsageSummary.cache.test.tsx` specs.
- tsc-identity: `frontend/node_modules/.bin/tsc -p frontend/tsconfig.json --noEmit` → ONLY the 2 pre-existing `e2e/fixtures/mockApi.ts` errors, ZERO new errors.
- Scope check: only `types/index.ts`, `useWorkflow.ts`, `TokenUsageSummary.tsx` (+ new `TokenUsageSummary.cache.test.tsx`) changed under `frontend/src` (api.ts untouched unless a real mapping is needed); docs limited to FIX-REGISTER / ISSUES-REGISTER / STATE.
- Zero-regression: no-cache render (`cacheReadTokens` 0/undefined) is unchanged from today — asserted by Spec B.
</verification>

<success_criteria>
- A completed cached run shows `⚡ {formatTokens(cacheRead)} cached ({pct}%)` after the input figure (optionally `· {formatTokens(cacheWrite)} written`).
- The no-cache case renders byte-identical to before (common case until a live cached run).
- Cache fields are threaded types → WS parse → render; persisted `tokenUsage` type carries the keys.
- Cost figure unchanged (already discounted); NO FE dollar/per-model math (INV-12).
- FIX-037 + ISS-034 + STATE recorded.
- No backend, golden, or `WorkflowHistory.tsx`/`AnalyticsPage.tsx` change (AnalyticsPage aggregation deferred).
- Atomic commits on branch `new-workflow-engine`; NO `Co-Authored-By` trailer; FE dev server NOT launched (vitest/tsc run standalone).
</success_criteria>

<output>
Create `.planning/quick/260704-uvs-show-prompt-cache-token-breakdown-in-ui/260704-uvs-SUMMARY.md` when done.
</output>
