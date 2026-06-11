---
phase: 13-live-verification-gap-closure
plan: 03
subsystem: agents
tags: [agent-prompts, app-builder, prompt-engineering, api-contracts]

# Dependency graph
requires:
  - phase: 12 (live verification milestone pass)
    provides: live-Bedrock UAT REPORT.md finding F5 (4 dead app_builder agents + cross-agent contract drift)
provides:
  - Greenfield re-templated AGENT.md bodies for app-code-compliance, app-test-compliance, app-sdlc-governance (zero Java/.NET/Maven/NuGet/legacy/parallel-run migration residue)
  - Hard filename:-block output contract section in app-devops (narration-only responses declared failed)
  - Anti-stall proceed-with-stated-assumptions rules in app-system-design and the 3 re-templated prompts
  - Contract-fidelity rule binding app-test-implementation to the implementation's exact exported surface from context
  - Stable-export-surface rule in app-feature-implementation
  - Single literal /api/v1 prefix mandated identically across app-api-design, app-infra-generator, app-devops
affects: [end-of-milestone live verification pass, app_builder pipeline, 13-04, 13-05, 13-06]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Anti-stall prompt rule: never ask the user which stack — read from context, state the assumption, proceed"
    - "Output contract section pattern: zero filename: blocks = failed response"
    - "Cross-agent contract threading: identical literal string (/api/v1) shared across producer + consumer prompts"

key-files:
  created: []
  modified:
    - backend/agents/prompts/app-code-compliance/AGENT.md
    - backend/agents/prompts/app-test-compliance/AGENT.md
    - backend/agents/prompts/app-sdlc-governance/AGENT.md
    - backend/agents/prompts/app-devops/AGENT.md
    - backend/agents/prompts/app-system-design/AGENT.md
    - backend/agents/prompts/app-api-design/AGENT.md
    - backend/agents/prompts/app-infra-generator/AGENT.md
    - backend/agents/prompts/app-test-implementation/AGENT.md
    - backend/agents/prompts/app-feature-implementation/AGENT.md

key-decisions:
  - "API prefix standardized on the literal /api/v1 across app-api-design, app-infra-generator and app-devops (resolves the live /api vs /api/v1 drift)"
  - "Stack derivation rule: compliance/test prompts read the stack from upstream context, defaulting to Node.js/TypeScript when unpinned (ESLint+typescript-eslint/Prettier/tsc --strict; Vitest/Jest+Playwright)"
  - "app-test-implementation's Java/.NET framework pins de-templated to derive-from-context (Rule 2 deviation) — they contradicted the new contract-fidelity rule"

patterns-established:
  - "Anti-stall rule: 'state the assumption' phrasing kept on a single line so grep gates stay verifiable"
  - "Output contract: narration about what you are 'about to' create is forbidden; emit the filename: block instead"

requirements-completed: [F5]

# Metrics
duration: ~9min
completed: 2026-06-12
---

# Phase 13 Plan 03: F5 app_builder Prompt Re-template & Cross-Agent Contracts Summary

**Re-templated 3 migration-flavored app_builder prompts to greenfield scope, hard filename:-block output contract on app-devops, anti-stall rules, and threaded cross-agent contracts (exact export surface + single /api/v1 prefix) across 9 AGENT.md bodies — frontmatter untouched, loader suite green**

## Performance

- **Duration:** ~9 min
- **Started:** 2026-06-11T22:48:06Z
- **Completed:** 2026-06-11T22:57:00Z
- **Tasks:** 3
- **Files modified:** 9

## Accomplishments

- The three stall-trigger prompts (app-code-compliance, app-test-compliance, app-sdlc-governance) are now greenfield app_builder prompts: zero `maven|nuget|parallel-run|legacy system` hits, stack derived from upstream context with Node/TS default, and an explicit never-ask/state-the-assumption/proceed rule in each
- app-devops carries a "## Output contract" section: every artefact MUST be a `filename:` fenced block, narration-only responses are declared failed, prose limited to a brief summary after the blocks
- app-system-design never asks clarifying questions — missing info becomes a conventional choice recorded in an "Assumptions" subsection
- app-test-implementation is contractually bound ("## Contract fidelity") to import EXACTLY the implementation's exported surface from context (module paths, class/function/method names, error classes, dependency packages — bcryptjs vs bcrypt); app-feature-implementation exports a stable named-export surface for it
- The literal `/api/v1` prefix is mandated identically in app-api-design (every route), app-infra-generator and app-devops (health checks, probes, ingress, smoke tests)

## Task Commits

Each task was committed atomically:

1. **Task 1: Re-template the three migration-flavored prompts for app_builder scope** - `d905059b` (fix)
2. **Task 2: app-devops output contract + app-system-design anti-stall** - `02c68cb0` (fix)
3. **Task 3: Cross-agent contracts — impl/test export surface + single /api/v1 prefix** - `070ace5a` (fix)

## Files Created/Modified

- `backend/agents/prompts/app-code-compliance/AGENT.md` - greenfield compliance prompt; ESLint/typescript-eslint/Prettier/tsc --strict for the Node/TS default with a context-substitution line; Java/Maven-vs-.NET/NuGet choice removed; anti-stall rule
- `backend/agents/prompts/app-test-compliance/AGENT.md` - test-strategy compliance over THIS pipeline's suites (Vitest/Jest coverage thresholds, CI failure reporting, flake policy); legacy parallel-run framing removed; anti-stall rule
- `backend/agents/prompts/app-sdlc-governance/AGENT.md` - greenfield SDLC governance (ADRs from context, branching+code-review, release gates/promotion, DoD); migration/decommission/hypercare language removed; filename:-block deliverable format kept (COMPLIANCE.md block replaced by GOVERNANCE.md); anti-stall rule
- `backend/agents/prompts/app-devops/AGENT.md` - "## Output contract" section (filename: blocks mandatory, narration forbidden) + /api/v1 in CD smoke tests/health checks
- `backend/agents/prompts/app-system-design/AGENT.md` - never-ask-clarifying-questions rule with Assumptions-subsection convention
- `backend/agents/prompts/app-api-design/AGENT.md` - hard rule: every REST route rooted at the literal /api/v1
- `backend/agents/prompts/app-infra-generator/AGENT.md` - /api/v1 mandated for health checks, route probes, ingress paths, smoke tests
- `backend/agents/prompts/app-test-implementation/AGENT.md` - "## Contract fidelity" exact-surface rule (never invent names; quote from context; non-compiling test = failed deliverable); migration-era Java/.NET framework pins de-templated to derive-from-context
- `backend/agents/prompts/app-feature-implementation/AGENT.md` - stable-export-surface paragraph (explicit named exports, naming consistent with API design context)

## Decisions Made

- **API prefix = literal `/api/v1`** (recorded in the plan as the drift resolution): identical string in app-api-design, app-infra-generator and app-devops
- **Node.js/TypeScript is the default stack** for compliance/test prompts when upstream context does not pin one, with an explicit substitution line for other stacks
- Anti-stall phrasing kept on single lines ("state the assumption") so the acceptance grep gates match reliably

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] De-templated app-test-implementation's Java/.NET migration framework pins**
- **Found during:** Task 3 (Contract fidelity rule)
- **Issue:** The body hard-pinned JUnit 5/Mockito/xUnit/NSubstitute, `<Story>Test.java`/`.cs` headers, Spring Cloud Contract, `dotnet-bench`, Azure SQL pools and "migration user-story acceptance criteria" — directly contradicting the new contract-fidelity rule (tests must be written in the implementation's actual stack, which is Node/TS on the live pipeline) and carrying the same F5 migration-template residue
- **Fix:** Re-framed the section tooling to derive from the implementation context (Vitest/Jest, Supertest, Pact, Playwright, k6 for the Node/TS default; "or the context stack's equivalent"), test-file headers to `*.test.ts`-style conventions, and removed the "migration" wording — section structure and role identity unchanged
- **Files modified:** backend/agents/prompts/app-test-implementation/AGENT.md
- **Verification:** loader suite green; contract-fidelity grep gates pass (never-invent, error-class, dependency-package surfaces named)
- **Committed in:** 070ace5a (Task 3 commit)

---

**Total deviations:** 1 auto-fixed (Rule 2)
**Impact on plan:** Required for internal consistency of the F5 fix — leaving Java/.NET pins would have re-created the exact tests-vs-implementation drift the contract rule closes. No scope creep beyond the file already in this task's files list.

## Issues Encountered

- The "state the assumption" anti-stall phrase initially wrapped across line breaks in two files, defeating the line-based grep acceptance gate — rewrapped to keep the phrase on one line in all three re-templated prompts
- Pre-existing working-tree drift (`.planning/config.json` `_auto_chain_active` flip by the orchestrator; untracked `.planning/_register-parts/`, `IMPLEMENTATION-REGISTER.md`) left untouched — not part of this plan

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- ROADMAP Phase 13 criterion 5 now holds at the prompt-contract level; the live 15-agent semantic re-audit is deferred to the end-of-milestone live pass (project convention)
- 13-04 through 13-06 remain; no blockers introduced — all changes confined to `backend/agents/prompts/` bodies, every agent still loads (44 loader tests green)

## Self-Check: PASSED

- All 9 modified AGENT.md files exist on disk
- Commits d905059b, 02c68cb0, 070ace5a present in git log
- `git diff` for this plan confined to backend/agents/prompts/

---
*Phase: 13-live-verification-gap-closure*
*Completed: 2026-06-12*
