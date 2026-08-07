---
name: velocity-ai-test
description: >-
  Plan, design, execute, triage, and report comprehensive QA for VelocityAI/Flowin. Use when asked to test or verify a feature, fix, ticket, workflow, API, UI, migration, AI/agent behavior, or release; write tests; run regression, smoke, or E2E checks; create a test plan or coverage matrix; investigate failures or flaky tests; assess accessibility, security, performance, or release readiness; or invoke /velocity-ai-test. Test-code creation requires an explicit request. Product fixes always belong to velocity-fix; combined requests use this skill for QA and velocity-fix for product changes.
compatibility: Kiro workspace skill for the Flowin monorepo on Windows/PowerShell; backend uses Python 3.12, uv, pytest, FastAPI, and PostgreSQL; frontend uses Next.js, React, TypeScript, Vitest, React Testing Library, and Playwright.
metadata:
  origin: "VelocityAI; informed by petrkindlmann/qa-skills"
  version: "1.0"
  category: "quality-assurance"
---

# VelocityAI Comprehensive QA Protocol

## Objective

Produce trustworthy quality evidence for Flowin. Translate requirements and risks into a traceable test scope, select the lowest useful test layer, execute deterministic checks from the correct working directory, classify failures honestly, and report what is proven, unproven, blocked, or deferred.

If the skill is invoked with arguments, treat `$ARGUMENTS` as the target and requested outcome. If no target is supplied, ask for the feature, fix, ticket, file, behavior, or release to assess. Do not guess what should be tested.

## Ownership and boundaries

This skill owns:

- risk assessment and test scoping;
- test plans, scenario matrices, and requirement traceability;
- execution of existing automated checks;
- test-code authoring only when explicitly requested;
- structured exploratory, API, UI, E2E, database, accessibility, security, performance, AI/LLM/agent, and release testing;
- failure triage, flake analysis, evidence capture, and QA reporting;
- fix-linked test registration in `.planning/FIX-TEST-REGISTER.md` when a new suite is explicitly written.

This skill does not silently own:

- product-code fixes: confirm the defect, preserve evidence, then hand off to `velocity-fix`;
- feature implementation: use `velocity-feature`;
- generic PR review: use `code-review`;
- read-only architecture investigation unrelated to test execution: use `velocityai-analysis`;
- deployment, production mutation, destructive cleanup, real payments, or uncontrolled load.

A request such as "test this" authorizes planning and execution of existing safe checks. It does **not** authorize creating or changing tests. Write test code only when the user says to add, write, generate, update, or implement tests, or explicitly requests a complete author-and-run workflow.

## Non-negotiable rules

1. **Evidence over confidence.** Never report PASS from code inspection, a clean build alone, an old run, or an assumed environment. A check passes only when current evidence proves its stated oracle.
2. **Trace every check.** Every case maps to a requirement, acceptance criterion, risk, invariant, defect, or regression hypothesis. Delete or defer cases with no reason to exist.
3. **Use the lowest sufficient layer.** Put business rules in unit tests, boundary behavior in integration/contract tests, and only critical user journeys in E2E. Do not test everything through the browser.
4. **Behavior over implementation.** Assert observable outcomes and contracts. Avoid private state, source-text inspection, broad snapshots, and mocks that merely replay the implementation.
5. **Read-only unless authorized.** Do not change product code during QA. Do not change test code unless test authoring is explicit. Do not update planning artifacts unless this protocol requires a fix-linked register entry or the user requests persistent evidence.
6. **Safe execution.** Never start a dev server, watcher, `uvicorn --reload`, `next dev`, or `next start`. Use single-pass commands only. If a server is required, give the exact manual command and wait for the user to confirm it is ready.
7. **Gate external effects.** Obtain explicit approval before live-model calls, shared staging mutation, production checks, load or chaos tests, outbound email/SMS, payment-provider actions, destructive fixtures, cloud writes, or tests with material cost. Mocked/local testing is the default.
8. **Protect data.** Never place credentials, tokens, secrets, connection strings, real payment data, or unnecessary PII in tests, fixtures, snapshots, reports, logs, or screenshots. Use synthetic identities and redact evidence.
9. **Respect local authority.** Repository steering, test configuration, package scripts, CI, and established test patterns override generic advice. Never add a framework or dependency when the existing stack can express the test.
10. **No result laundering.** Retries are diagnostic, not a way to turn red into green. An inconsistent result is FLAKY until its cause is resolved. A skipped, blocked, or unverified case is not a pass.

## Operating modes

Infer the narrowest mode from the request. Ask one focused question only when the mode or target materially changes the work.

| Mode | Use when | Mutations allowed |
|---|---|---|
| **plan** | "Create a test plan/matrix/checklist" | Plan/report only if requested; no test or product code |
| **verify** | "Test/verify/check this" | Execute existing safe checks; no code changes; default mode |
| **author** | "Write/add/update tests" | Test code and required test fixtures/config only; no product fix |
| **full** | "Write and run comprehensive tests" | Plan, test code, execution, and required fix-test registration |
| **triage** | "Why is this test failing/flaky?" | Read and diagnose; change tests only if explicitly requested |
| **explore** | "Explore/manual QA/bug hunt" | Session notes/evidence if requested; no product code |
| **release** | "Is this ready to ship?" | Read-only evidence gathering; never deploy or approve production changes |

If the user asks for a plan only, stop after producing and checking the plan. If the user asks for execution only, do not opportunistically add missing tests; report the gap.

## End-to-end workflow

Complete the applicable steps in order. A narrow request may legitimately stop after a subset, but never skip evidence or reporting.

### Step 0 — Establish the QA contract

Capture:

- **Target:** ticket, FIX ID, feature, behavior, files, workflow, or release.
- **Requested mode:** plan, verify, author, full, triage, explore, or release.
- **Success oracle:** acceptance criteria or observable expected behavior.
- **Environment:** local, mocked E2E, isolated test DB, shared staging, live model, or production.
- **Permissions:** whether test code, reports, external calls, or mutable environments are authorized.
- **Output:** chat summary, test files, test plan, persistent report, register entry, or release verdict.

State assumptions when evidence is incomplete. Do not hide ambiguity inside a test case.

### Step 1 — Read ground truth and existing coverage

Read only what is relevant, but deeply enough to understand the behavior:

1. The user's request, ticket, specification, acceptance criteria, screenshots, logs, or reproduction steps.
2. The current diff or changed files when the request concerns a change.
3. The implementation path and its external boundaries.
4. Existing nearby tests, fixtures, factories, helpers, configuration, and naming conventions.
5. `.github/workflows/ci.yml` and the relevant steering when choosing gates.
6. `.planning/FIX-REGISTER.md` for a fix-linked target.
7. `.planning/FIX-TEST-REGISTER.md` before writing any fix-linked suite, to avoid duplicate coverage and reserve the next TEST ID only at write-back time.
8. Existing campaign sheets, bug logs, or verification reports when the request belongs to one of those campaigns.

Use repository evidence before asking discovery questions. If relevant files are unclear across the codebase, gather context once, then proceed without repeating the same searches.

Output a concise internal scope card: behavior, risk, affected boundaries, existing coverage, missing coverage, and constraints.

### Step 2 — Score risk and set depth

Score each material behavior:

- **Impact (1–5):** user harm, data integrity, security/privacy, revenue, compliance, availability, or recovery cost.
- **Likelihood (1–5):** change size, complexity, churn, concurrency, dependency fragility, prior incidents, and current coverage.
- **Risk = impact × likelihood.** Use CRITICAL 15–25, HIGH 10–14, MEDIUM 5–9, LOW 1–4.

Risk controls depth, not whether obvious acceptance criteria are tested. CRITICAL/HIGH behavior needs negative paths, boundary coverage, integration evidence, and a critical-journey check where appropriate. LOW-risk cosmetic behavior may need only focused component or exploratory evidence.

Open [test-design.md](references/test-design.md) for the selection matrix, scenario bank, traceability format, data rules, and test-double guidance.

### Step 3 — Build a traceable test plan

Create a matrix before authoring or executing a broad suite. At minimum record:

| ID | Requirement/risk | Layer | Scenario | Preconditions/data | Oracle | Priority | Mandatory/waiver | Status |
|---|---|---|---|---|---|---|---|---|

Mark each acceptance criterion and P0/P1 risk scenario mandatory by default. Any waiver must name the accountable owner and reason; an unstated waiver cannot support an overall PASS.

Cover applicable dimensions:

- happy path and primary user value;
- validation, boundaries, empty/null/oversized/malformed input;
- error, timeout, cancellation, retry, and fallback behavior;
- authentication, authorization, ownership, tenant/workspace isolation;
- state transitions, persistence, refresh/reload, and idempotency;
- concurrency, duplicate submission, ordering, race conditions;
- contracts across API, database, queue, filesystem, provider, and browser boundaries;
- observability and generic non-leaking errors;
- accessibility, security, performance, browser/responsive, and AI-specific risks;
- regression around the root cause, not merely the visible symptom.

Every out-of-scope or deferred case must state why and what risk remains. Use `NOT VERIFIABLE` when the system does not expose enough evidence; never convert that limitation to PASS.

### Step 4 — Author tests, only when explicitly requested

Match the existing project structure and framework. Prefer extending the nearest cohesive test file over creating a parallel convention.

For every new test:

1. Name the observable behavior and condition.
2. Arrange only the state the behavior needs.
3. Perform one meaningful action or transition.
4. Assert a clear externally observable oracle.
5. Clean up through fixtures/context managers so isolation survives failure.
6. Prove the test can fail for the intended reason when practical; a regression test should fail against the defective behavior before it proves the fix.
7. Keep external providers deterministic with ports/fakes/mocks; do not call real LLMs, payment providers, email services, or shared infrastructure in the default suite.
8. Avoid arbitrary sleeps, dynamic list indexes, order dependence, global mutable state, uncontrolled clocks/randomness, and exact prose assertions for nondeterministic AI output.

Framework rules:

- **Backend:** pytest/pytest-asyncio; `httpx` for API behavior; Hypothesis for pure parsers/state spaces when valuable; mock providers at defined ports; assert schemas, guardrails, and contracts.
- **Frontend:** Vitest + React Testing Library; query by role, label, and visible text; test user-visible state; use stable semantic keys; do not test component internals.
- **E2E:** Playwright mocked project by default; user-facing locators; web-first assertions; no `waitForTimeout`; API/fixtures for setup; independent tests.
- **AI/agent:** schema/property/statistical assertions according to output type; test tool selection and arguments, loop/time/budget bounds, human gates, grounding, authorization filters, injection resistance, and safe failure.
- **Golden tests:** preserve deterministic characterization outputs unless the requested change intentionally changes them; document intentional golden updates.

Do not add dependencies merely for convenience. If a new dependency is genuinely required, explain why and use an exact pinned version after approval.

### Step 5 — Execute from narrowest to broadest

Use this sequence:

1. Syntax/import/config preflight when relevant.
2. The single test or smallest file that exercises the behavior.
3. The affected feature/module suite.
4. Cross-boundary or mocked E2E coverage for critical paths.
5. Relevant lint, type, architecture, build, and security gates.
6. Full package or release suite only when requested or justified by blast radius.

For every command capture:

- exact command and working directory;
- exit code;
- pass/fail/skip/xpass/xfail counts when available;
- duration and timeout;
- failing test names and concise failure evidence;
- warnings that affect confidence;
- artifact paths such as traces, screenshots, coverage, or reports.

Use [execution-and-triage.md](references/execution-and-triage.md) for the Flowin command matrix, change-to-gate mapping, retry policy, and evidence requirements.

### Step 6 — Triage every failure before acting

Record a cause classification and an execution outcome separately.

Cause classification:

- **PRODUCT DEFECT:** observable behavior violates a requirement, contract, invariant, or defensible oracle.
- **TEST DEFECT:** wrong assertion, stale fixture, brittle locator, overmocking, leakage, or test-order dependency.
- **FLAKY/NONDETERMINISTIC:** same revision, inputs, and environment produce inconsistent outcomes.
- **ENVIRONMENT/INFRASTRUCTURE:** unavailable dependency, configuration mismatch, resource exhaustion, network/DNS, test DB, or missing tool.
- **BY DESIGN:** evidence confirms the behavior is intentional and documented.
- **NOT VERIFIABLE:** the required evidence is not exposed or the authorized environment cannot prove it.

Execution outcomes are `PASS`, `FAIL`, `FLAKY`, `BLOCKED`, `SKIPPED`, `BY DESIGN`, `NOT VERIFIABLE`, `DEFERRED`, or `NOT RUN`. Use `BLOCKED` when a prerequisite, permission, service, credential, or manual action is missing, and retain the underlying `ENVIRONMENT/INFRASTRUCTURE` classification when applicable.

A controlled rerun may distinguish determinism from flakiness; it may not erase the first failure. Do not weaken assertions, increase timeouts, add blanket retries, or rewrite expected values until the classification is supported by evidence.

For a product defect, preserve the minimal reproduction, expected versus actual behavior, environment, evidence, impact, suspected boundary, and regression-test recommendation. Do not edit product code. Offer or invoke `velocity-fix` only when the user requests the fix.

### Step 7 — Add specialized quality checks when risk requires them

Load [specialized-testing.md](references/specialized-testing.md) only for applicable concerns:

- accessibility and keyboard/assistive-technology behavior;
- authorization-focused and non-destructive security testing;
- performance budgets, load profiles, and capacity checks;
- migrations, data integrity, and concurrency;
- visual, responsive, and cross-browser behavior;
- exploratory sessions;
- AI/LLM, RAG, tools, streaming, guardrails, and agent orchestration;
- release smoke, rollback evidence, and post-deploy verification planning.

Specialized checks do not override the approval gates. In particular, never run load, chaos, red-team, live-model, shared-environment, or production tests without explicit authorization and a bounded plan.

### Step 8 — Run the appropriate quality gates

Select gates by affected surface and risk; do not run unrelated expensive checks merely to look comprehensive.

- Backend behavior: targeted pytest, then relevant ruff/pyright/import-boundary checks; broaden to compileall, vulture, and full pytest for package/release confidence.
- Frontend behavior: targeted Vitest, then lint and production build; add mocked Playwright for critical user flows.
- API/contracts: handler/service tests plus schema, auth, negative path, pagination/limits, and timeout behavior.
- Database/migrations: isolated PostgreSQL migration and integrity checks; never point destructive tests at shared data.
- Terraform/config: formatting, validation, and configured IaC/security scanners; never initialize or access shared state merely to validate syntax.
- AI/agent: deterministic mocked tests first; configured evals/live calls only with explicit permission and budgets.
- Release: mirror the blocking CI gates and record any unavailable gate. Treat `pip-audit` and `npm audit` as warn-only while CI does; do not claim they are blocking gates.

A build proves buildability, not behavioral correctness. A lint pass proves static conformance, not feature correctness. Report each gate for what it actually establishes.

### Step 9 — Report evidence and update the register when applicable

Always give the user a results-first summary containing:

1. verdict;
2. target, mode, environment, and revision/diff basis;
3. coverage completed versus planned;
4. commands and outcomes;
5. findings with classification and severity;
6. files/artifacts created or changed;
7. blocked, skipped, deferred, flaky, or not-verifiable cases;
8. residual risk and recommended next action.

Use [reporting-and-register.md](references/reporting-and-register.md) for canonical verdicts and templates.

When a new test suite is explicitly authored for an existing `FIX-NNN`:

1. Re-read `.planning/FIX-TEST-REGISTER.md` immediately before editing it.
2. Choose the next sequential `TEST-NNN` without reusing or renumbering IDs.
3. Add the summary row and detailed entry, including all new test files, named cases, purpose, exact run output, verdict, notes, and confidence.
4. Record failures honestly; registration is evidence, not a celebration log.
5. Do not invent a FIX ID. If no fix exists, ask whether the user wants a standalone report or an issue/fix workflow.

Execute-only runs do not create a new TEST entry unless the user asks for persistent evidence or an existing campaign requires it.

### Step 10 — Completion check

The QA task is complete only when all applicable statements are true:

- [ ] Target, mode, environment, permissions, and oracle are explicit.
- [ ] Existing coverage was checked before proposing or adding tests.
- [ ] Every executed or authored case traces to a requirement, risk, invariant, or defect.
- [ ] The selected layer is justified; browser tests are reserved for browser value.
- [ ] Test code was changed only with explicit authorization; product code was not silently changed.
- [ ] Commands ran from the required working directories in single-pass mode.
- [ ] Every result has current evidence and every failure is classified.
- [ ] Skipped, blocked, flaky, deferred, and not-verifiable work remains visible.
- [ ] Live, destructive, costly, or shared-environment actions were either approved and bounded or not run.
- [ ] The final verdict states residual risk and does not overclaim.
- [ ] A fix-linked authored suite has a complete, sequential TEST entry.

## Related workspace skills

- `velocity-fix` — investigate and repair a confirmed product defect.
- `velocity-feature` — implement a new product capability and its required validation.
- `code-review` — review a diff/branch/PR, including whether its test coverage is adequate.
- `velocityai-analysis` — perform read-only architecture or impact analysis without a QA execution workflow.

## References

- [Test design and coverage selection](references/test-design.md)
- [Flowin execution, gates, and failure triage](references/execution-and-triage.md)
- [Specialized quality testing](references/specialized-testing.md)
- [Reporting and FIX-TEST registration](references/reporting-and-register.md)
- [Sources and adaptation notes](references/sources.md)
