---
phase: 15-live-pass-prompt-contract-closure
plan: 01
subsystem: prompts
tags: [agent-md, prompt-contracts, od-ppt, sdlc-governance, infra-generator, anti-fabrication]

# Dependency graph
requires:
  - phase: 13-live-verification-gap-closure
    provides: "13-03 prompt output-contract precedent (body-only edits, single-line grep-pinnable phrases, frontmatter frozen)"
  - phase: 07
    provides: "PptResolver + unwrap_artifact first-match semantics (READ-ONLY behavior anchor for the LV-02 contract wording)"
provides:
  - "od-ppt-validator deck re-emission contract: exactly ONE <artifact> block = the complete corrected HTML deck, top-of-body, old bottom contract deleted (LV-02 / D-01)"
  - "sdlc-governance family anti-fabrication contracts: no-tools + never-emit-tool-XML + begin-directly, byte-identical anti-tool-XML line, per-pipeline deliverable-start line (F4-residual / D-02)"
  - "app-infra-generator API PATH CONTRACT above OUTPUT FORMAT with healthcheck/nginx/smoke /api/v1 examples, 8 literal occurrences (F5-residual / D-03)"
affects: [15-02 prompt-contract pinning tests, 15-03 offline gate + live re-check]

# Tech tracking
tech-stack:
  added: []
  patterns: ["top-of-body NON-NEGOTIABLE output-contract blocks with single-line grep-pinnable bullets (extends 13-03 precedent)"]

key-files:
  created: []
  modified:
    - backend/agents/prompts/od-ppt-validator/AGENT.md
    - backend/agents/prompts/app-sdlc-governance/AGENT.md
    - backend/agents/prompts/dotnet-sdlc-governance/AGENT.md
    - backend/agents/prompts/mulesoft-sdlc-governance/AGENT.md
    - backend/agents/prompts/app-infra-generator/AGENT.md

key-decisions:
  - "LV-02 contract worded as exactly-ONE-artifact (never 'last/final artifact') to match unwrap_artifact first-match regex semantics (RESEARCH Pitfall 2)"
  - "sdlc anti-tool-XML line byte-identical across all three files; deliverable-start line tailored: app = first filename: fenced block, dotnet/mulesoft = first Markdown heading (Pitfall 5)"
  - "app-infra existing bottom RULES /api/v1 bullet kept verbatim as reinforcement (planner's-choice 'keep' option exercised)"

patterns-established:
  - "Contract bullets each on ONE physical line so 15-02 substring pins survive (13-03 wording lesson)"

requirements-completed: [LV-02, F4-residual, F5-residual]

# Metrics
duration: ~3min
completed: 2026-06-13
---

# Phase 15 Plan 01: Live-Pass Prompt Contracts Summary

**Five AGENT.md bodies now carry the three live-pass output contracts: od-ppt-validator must re-emit the complete deck as its single artifact, the sdlc-governance family must never fabricate tool-call XML, and app-infra-generator gets a forceful top-of-body /api/v1 contract — bodies only, frontmatter byte-untouched, zero engine edits.**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-06-13T00:20:45Z
- **Completed:** 2026-06-13T00:23:37Z
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments

- **LV-02 (D-01):** od-ppt-validator job statement rewritten from judgment/reporting to re-emission; new `## OUTPUT CONTRACT — NON-NEGOTIABLE (read first)` section inserted above the user-message description and `## VALIDATION CHECKLIST`; old bottom `## OUTPUT CONTRACT` (with fenced artifact example) deleted so exactly one contract heading exists; RULES no-defect line now demands full re-emission.
- **F4-residual (D-02):** all three sdlc-governance bodies open with `OUTPUT CONTRACT (non-negotiable):` directly after the role line — no-tools, never-emit-tool-XML, begin-directly. app-sdlc-governance's fabrication trigger defused ("Read the concrete choices ... from the provided context" → "Use the concrete choices ... already provided in full in this message"; ADR "(read them from context)" → "(from the context above)"). dotnet/mulesoft diffs are single-hunk contract insertions only — migration format untouched.
- **F5-residual (D-03):** `API PATH CONTRACT (non-negotiable — applies to EVERY file you output):` inserted above OUTPUT FORMAT with Dockerfile/compose healthcheck, nginx location, ingress, and CI/CD smoke-curl examples; existing RULES bullet kept verbatim; literal `/api/v1` count = 8 (gate >= 6).
- Loader suite (44 tests) green after every task; `git diff --stat` confined to `backend/agents/prompts/`; SC-001 fence clean (`git status --porcelain` on capabilities/execution_engine/factory.py/loader.py/registry.py empty).

## Task Commits

Each task was committed atomically:

1. **Task 1: od-ppt-validator deck re-emission contract (LV-02, D-01)** - `cf5fb56b` (fix)
2. **Task 2: sdlc-governance family anti-fabrication contracts (F4-residual, D-02)** - `3fff6879` (fix)
3. **Task 3: app-infra-generator top-of-body /api/v1 contract (F5-residual, D-03)** - `dbcd88c8` (fix)

## Files Created/Modified

- `backend/agents/prompts/od-ppt-validator/AGENT.md` - deck re-emission output contract (exactly ONE artifact = complete deck), top-of-body; old bottom contract removed
- `backend/agents/prompts/app-sdlc-governance/AGENT.md` - anti-fabrication contract (filename:-block start) + read_file-priming sentence defused
- `backend/agents/prompts/dotnet-sdlc-governance/AGENT.md` - anti-fabrication contract (Markdown-heading start), single-hunk insertion
- `backend/agents/prompts/mulesoft-sdlc-governance/AGENT.md` - anti-fabrication contract (Markdown-heading start), single-hunk insertion
- `backend/agents/prompts/app-infra-generator/AGENT.md` - API PATH CONTRACT block above OUTPUT FORMAT (6 new `/api/v1` literals)

## Exact Contract Wording (15-02 pins these tokens)

### od-ppt-validator — heading `## OUTPUT CONTRACT — NON-NEGOTIABLE (read first)`

Job statement: `Your job: a final QA pass on the HTML deck, then RE-EMIT THE COMPLETE DECK as your artifact — corrected if you found structural defects, byte-identical otherwise.`

- `Your response MUST contain exactly ONE <artifact> block — never a second artifact, never a partial artifact, never a status artifact.`
- `The artifact content MUST be the complete corrected HTML deck: the full <!DOCTYPE html> document with every <section class="slide"> element — even when you change nothing, re-emit the entire deck.`
- `The artifact is NEVER a QA report, summary, or status note. The artifact IS the deck.`
- `Never use the literal <artifact tag anywhere else in your response — your commentary must not contain it.`
- `At most two short sentences of commentary may precede the artifact. Nothing after </artifact>.`
- `Preserve the incoming artifact's identifier, type, and title attributes on your re-emitted <artifact> tag.`

RULES line: `If the artifact has no defects, re-emit it unchanged — in full.`

Pin tokens: `exactly ONE <artifact>` · `complete corrected HTML deck` · `even when you change nothing` · `anywhere else in your response` · count of `## OUTPUT CONTRACT` == 1 · contract index < `## VALIDATION CHECKLIST` index · no `EXACTLY as-is` · no `last artifact`/`final artifact`.

### sdlc-governance family — block after `You are an Engineering Operations & Governance Lead.`

Shared lines (byte-identical across all three):
- `OUTPUT CONTRACT (non-negotiable):`
- `- You have NO tools. Everything you need from the upstream agents is already included in this message as context.`
- `- Never emit tool-call syntax as text — no <function_calls>, no <invoke>, no write_todos. Not one line of it.`

Fourth line, app-sdlc-governance:
- `- Begin your response DIRECTLY with the first \`filename:\` fenced block — no preamble, no plan, no narration before it.`

Fourth line, dotnet-sdlc-governance AND mulesoft-sdlc-governance (byte-identical):
- `- Begin your response DIRECTLY with the deliverable content — the first Markdown heading. No preamble, no plan, no narration before it.`

app-sdlc trigger defusal: `Use the concrete choices the upstream` / `agents actually made — they are already provided in full in this` / `message; where something is unstated, NEVER ask the user — pick` (wrapped; `state the assumption, and proceed to the full deliverable.` kept on a single line — 13-03 pin preserved). ADR section: `(from the context above)`.

Pin tokens per file: `You have NO tools` · `<function_calls>` · `<invoke>` · `write_todos` · `Begin your response DIRECTLY with` (each exactly once per file); app-only `fenced block`; dotnet/mulesoft-only `the first Markdown heading` and NO `filename:`; app negative: `Read the concrete choices` absent.

### app-infra-generator — block between the produce-ALL line and `OUTPUT FORMAT`

- `API PATH CONTRACT (non-negotiable — applies to EVERY file you output):`
- `- Every reference to an application API endpoint uses the literal \`/api/v1\` prefix — no bare \`/health\`, no unversioned API path, anywhere.`
- `- Healthchecks: \`curl -f http://localhost:$PORT/api/v1/health\` — in the Dockerfile HEALTHCHECK, every compose healthcheck block, and any readiness probe.`
- `- Reverse proxy / ingress: nginx \`location /api/v1/\` blocks and ingress path rules target \`/api/v1\`.`
- `- CI/CD smoke tests: curl \`/api/v1\` endpoints (e.g. \`/api/v1/health\`) after deploy.`

Pin tokens: `API PATH CONTRACT` · `/api/v1/health` · `location /api/v1/` · total `/api/v1` count == 8 (>= 6 gate) · `API PATH CONTRACT` index < `OUTPUT FORMAT` index · existing RULES bullet `API paths: wherever health checks` still present.

## Decisions Made

- Exactly-ONE-artifact wording (never "last/final artifact") encodes `unwrap_artifact` first-match regex semantics — a small status artifact before the deck would otherwise win the unwrap and reproduce LV-02.
- Anti-tool-XML sentence byte-identical across the sdlc family; deliverable-start line tailored per output format so dotnet/mulesoft migration deliverables stay structured-Markdown (no filename-block contamination, Pitfall 5).
- Forbidden tokens named exactly once per file, tersely, no multi-line bad-example exemplars (Pitfall 7 — exemplars prime fabrication).
- app-infra bottom RULES bullet kept as reinforcement (RESEARCH planner's-choice exercised as "keep").
- app-sdlc trigger-defusal rewrap keeps `state the assumption, and proceed to the full deliverable.` intact on one line (13-03 pinned phrase preserved).

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## Known Stubs

None — prompt-body edits only; no code or data paths touched.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- 15-02 can pin the exact tokens recorded above in `tests/agents/test_prompt_contracts.py` (all single-line, substring-stable).
- Frontmatter byte-identical on all five files (verified per-task via git diff key-line greps); loader suite green — frontmatter-freeze pytest pin lands in 15-02 per threat register T-15-01.
- SC-001 fence held: zero edits under `backend/agents/capabilities/`, `backend/agents/execution_engine/`, `factory.py`, `loader.py`, `registry.py`.

## Self-Check: PASSED

All 5 modified files + SUMMARY exist on disk; commits cf5fb56b, 3fff6879, dbcd88c8 present in git log.

---
*Phase: 15-live-pass-prompt-contract-closure*
*Completed: 2026-06-13*
