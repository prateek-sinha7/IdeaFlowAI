# Test Design and Coverage Selection

Load this reference when the request needs a test plan, new test cases, broad regression selection, or a reasoned choice of test layers.

## 1. Start with a testable scope

A testable scope contains six elements:

| Element | Question |
|---|---|
| Behavior | What must the user or caller be able to observe? |
| Oracle | What exact evidence separates correct from incorrect? |
| Boundary | Which component, API, persistence layer, provider, or browser boundary is crossed? |
| State | What state exists before, during, and after the action? |
| Risk | Who or what is harmed if the behavior fails? |
| Constraint | Which environments, permissions, tools, time, and cost limits apply? |

If the oracle is "the implementation looks right," the scope is not yet testable. Convert it to an output, state transition, contract, event sequence, persisted value, error, latency threshold, or user-visible behavior.

## 2. Risk scoring

Score impact and likelihood independently from 1 to 5.

### Impact

| Score | Meaning | Typical Flowin examples |
|---|---|---|
| 5 | Catastrophic | cross-workspace data exposure, secret leak, unrecoverable corruption, unauthorized cloud action |
| 4 | Major | authentication/authorization bypass, failed critical workflow, wrong durable output, broken cancellation or human gate |
| 3 | Moderate | important flow fails with workaround, incomplete output, stale catalogue state |
| 2 | Minor | localized UX problem, non-critical validation or metadata issue |
| 1 | Negligible | cosmetic/internal issue with no meaningful user impact |

### Likelihood

| Score | Meaning | Indicators |
|---|---|---|
| 5 | Frequent | high churn, concurrency, complex branching, no coverage, repeated incidents |
| 4 | Likely | substantial change, fragile provider/boundary, partial coverage, known debt |
| 3 | Possible | moderate complexity or prior related issue, ordinary coverage |
| 2 | Unlikely | stable, small change, strong nearby coverage |
| 1 | Rare | trivial stable path with deterministic comprehensive coverage |

Compute `risk = impact × likelihood`:

| Zone | Score | Required depth |
|---|---:|---|
| CRITICAL | 15–25 | lower-layer logic + real boundary + negative/security/concurrency + critical journey + monitoring/recovery evidence |
| HIGH | 10–14 | lower-layer logic + boundary integration + key negative/error paths + focused journey if user-visible |
| MEDIUM | 5–9 | happy path + important boundary/validation cases |
| LOW | 1–4 | focused check or documented manual observation; automate only when stable and valuable |

Risk is a prioritization tool, not a substitute for acceptance criteria. A low-risk acceptance criterion still needs an explicit disposition.

## 3. Layer-selection matrix

Choose the first layer that can prove the behavior, then add a higher boundary only when it detects a different class of failure.

| Change or behavior | Primary layer | Complementary evidence | Common mistakes |
|---|---|---|---|
| Pure calculation, parser, validator, state reducer | Unit/property | Type/lint; integration only if serialization differs | Browser test for pure logic; mirroring implementation in expected values |
| Domain/service orchestration | Unit with injected ports | Integration at each real boundary | Mocking every collaborator and proving only call choreography |
| Repository/query/persistence | PostgreSQL integration | Service/API test | SQLite substitute; asserting ORM internals instead of stored behavior |
| FastAPI request/response | API test with `httpx` | Service unit + schema/authorization checks | Calling router functions directly; testing only status 200 |
| External provider adapter | Adapter contract test with fake server/provider | Narrow approved sandbox check | Real provider in default CI; unbounded retries/cost |
| React component behavior | Vitest + React Testing Library | Accessibility checks; E2E only for cross-page journey | DOM structure assertions; CSS selectors; testing server state as local UI state |
| Navigation or multi-page user journey | Mocked Playwright | Component/API tests beneath it | E2E for every validation rule; fixed sleeps; shared test order |
| Authentication/authorization | Service/API negative tests | One critical browser journey | Happy path only; confusing client guard with security boundary |
| Database migration | Migration/integration against isolated PostgreSQL | Application compatibility and rollback/forward-fix analysis | Shared database; testing only model definitions |
| Streaming/SSE/cancellation | Service/event-sequence integration | Focused UI journey | Checking final text only; ignoring ordering, terminal state, disconnects |
| Workflow/agent orchestration | Deterministic engine/service tests | Mocked end-to-end run; approved eval if semantic quality matters | Letting an LLM choose control flow in tests; exact prose assertion |
| RAG/retrieval | Authorization-filter integration + grounding eval | API/agent journey | Post-generation access filtering; treating retrieved text as trusted instructions |
| Terraform/configuration | Format/validate/static security scan | Plan only when explicitly authorized and isolated | Accessing shared state; hardcoded credentials; treating scanner absence as pass |
| Release candidate | Risk-selected smoke + full blocking CI gates | Manual/exploratory and approved environment checks | Running every possible test without a release oracle; no rollback evidence |

### Avoid duplicate confidence

Two tests are complementary only if they catch different failure modes. A component test and E2E test that both assert the same static label may be duplicate maintenance. Keep the cheapest reliable layer unless the browser boundary itself is the risk.

## 4. Scenario design bank

Apply only relevant categories, but explicitly consider each before declaring a plan complete.

### Functional core

- primary successful path;
- alternate valid path;
- empty and initial state;
- minimum, maximum, just-inside, and just-outside boundaries;
- malformed type/shape/encoding;
- duplicate and idempotent request;
- persisted result after reload or new session;
- ordering, sorting, filtering, pagination, and limits;
- backward compatibility and default behavior.

### Failure and recovery

- dependency unavailable;
- timeout before and after a side effect;
- transient failure then retry;
- permanent failure and safe fallback;
- cancellation before start, mid-stream, and after terminal state;
- partial write or interrupted transaction;
- stale version/conflict;
- resume after disconnect/crash;
- duplicate callback/event delivery;
- resource or budget exhaustion.

### Security and isolation

- unauthenticated request;
- authenticated but wrong role/scope;
- user A attempts to access user B's resource;
- workspace/tenant isolation in query and mutation;
- invalid, expired, replayed, or mismatched token/session;
- unsafe URL/path/header/input handling;
- error response does not leak stack, SQL, filesystem, prompt, or secret material;
- logs and artifacts redact sensitive values.

### Concurrency and state

- double-click/double-submit;
- two writers update the same version;
- out-of-order events;
- retry after the first call committed but the response was lost;
- lock/transaction boundary;
- repeated worker/job delivery;
- cache invalidation and stale reads.

### UI and accessibility

- loading, success, empty, error, retry, disabled, and pending states;
- keyboard-only operation and visible focus;
- logical focus after modal/dialog/navigation changes;
- accessible name, role, state, and error association;
- responsive widths and content overflow;
- reduced-motion behavior;
- no unexpected console/page errors or failed requests.

### AI, RAG, and agent behavior

- valid structured output and invalid-output repair/rejection;
- required tool selected, prohibited tool not selected, typed arguments validated;
- tool timeout, transient error, permanent error, and malformed tool result;
- direct and indirect prompt injection;
- workspace authorization embedded in retrieval query;
- claim grounded in allowed sources with citations;
- no relevant context produces an honest abstention;
- loop, time, token, and cost limits;
- deterministic orchestration and human gate before high-impact action;
- checkpoint/resume does not repeat side effects;
- live semantic quality measured by an explicit rubric and pass rate, not exact wording.

## 5. Traceability matrices

### Compact plan

```markdown
| ID | Requirement / Risk | Layer | Scenario | Preconditions / Data | Oracle | Priority | Mandatory / Waiver | Status |
|----|--------------------|-------|----------|----------------------|--------|----------|--------------------|--------|
| T-01 | AC-1 / RISK-auth-01 | API | Owner reads own workflow | owner + workflow fixture | 200 and matching workspace/owner IDs | P0 | YES | Planned |
```

Mark every acceptance criterion and P0/P1 risk scenario `YES` by default. Use `NO` only for explicitly non-gating evidence. A waiver must name the accountable owner and reason, for example `WAIVED: <owner> — <reason>`; an unstated waiver cannot support an overall PASS.

### Coverage audit

```markdown
| Requirement | Existing evidence | Gap | Decision | Residual risk |
|-------------|-------------------|-----|----------|---------------|
| AC-1 | `test_x.py::test_owner_reads_workflow` | None | Keep | Low |
| AC-2 | No automated coverage | timeout path | Add integration test / defer | Medium until covered |
```

Allowed status values: `PLANNED`, `PASS`, `FAIL`, `FLAKY`, `BLOCKED`, `SKIPPED`, `BY DESIGN`, `NOT VERIFIABLE`, `DEFERRED`.

A GAP must become one of: cover now, accept risk with owner/reason, or defer with trigger/date. It may not disappear from the final report.

## 6. Test design by layer

### Unit

- Keep network, disk, database, clock, and random values controlled.
- Assert return values, emitted domain events, state transitions, and narrow collaborator contracts.
- Use a fake for a real in-memory implementation, a stub for canned input, a spy for an observable call, and a mock only when interaction itself is the contract.
- Use property-based tests for parsers, serialization round-trips, ordering, bounds, and state machines where examples leave a large input space.

### Integration

- Exercise the real boundary that carries risk: PostgreSQL, filesystem adapter, queue contract, HTTP serialization, or composition root.
- Isolate data by test and clean up even after failure.
- Verify transactions, constraints, ownership/workspace filters, idempotency, and error translation.
- Do not replace the boundary with a mock and still label the test integration.

### API/contract

For each material endpoint consider:

- status and typed schema;
- required/optional fields and backward compatibility;
- authentication and authorization matrix;
- ownership/workspace isolation;
- validation and generic error body;
- limits, pagination, ordering, and duplicate behavior;
- idempotency, timeout, and retry semantics;
- response headers and cache behavior where relevant.

### Frontend component

- Drive the component as a user: role, label, text, typing, clicking, keyboard.
- Model loading/error/empty/ready as distinct observable states.
- Assert callbacks and rendered behavior, not hook calls or internal state.
- Mock at the network/data boundary rather than mocking child internals.

### Browser/E2E

- Keep only critical journeys and browser-specific risks.
- Seed through APIs or fixtures; use the UI for the behavior under test.
- Prefer `getByRole`, then `getByLabel`, then stable test IDs; CSS is a last resort.
- Use web-first assertions and event/response waits, never arbitrary sleeping.
- Capture traces/screenshots on failure without leaking secrets.
- Make every test independent and safe to repeat.

### AI/evaluation

Select the assertion strategy before running:

| Output | Preferred oracle |
|---|---|
| Structured extraction/classification | JSON/Pydantic schema + allowed values + bounds |
| Tool use | exact allowed tool set + typed/semantic argument checks + side-effect evidence |
| Deterministic workflow state | exact events/state transitions with mocked model/provider |
| Open-ended grounded answer | required facts/citations + grounding/faithfulness rubric |
| Creative response | safety, format, length, and statistical rubric over N runs |
| Model judge | calibrated against human-labeled holdout data; record agreement threshold |

Do not use an LLM judge when a deterministic schema or predicate can decide correctness.

## 7. Test data and fixtures

- Use synthetic, minimal, deterministic data.
- Give every user/workspace/resource a unique stable identifier; never share mutable fixtures across parallel tests.
- Use factories for meaningful defaults and override only what the case needs.
- Freeze time and seed randomness when those values affect behavior.
- Never copy production data unless it is formally approved, minimized, anonymized, and isolated.
- Keep secrets in approved environment/config mechanisms; tests reference names, never secret values.
- Cleanup must be idempotent. Prefer transaction rollback or disposable resources to ad hoc deletion.
- For destructive migration/concurrency tests, use a disposable PostgreSQL database, never the developer's shared or production database.

## 8. Test quality review

Before keeping a test, ask:

- Would it fail if the intended behavior regressed?
- Can it fail for unrelated timing, ordering, data, or environment reasons?
- Does it assert a public contract rather than implementation detail?
- Does it duplicate cheaper existing coverage?
- Is the setup smaller than the behavior it proves?
- Is the failure message actionable?
- Can it run independently, repeatedly, and in parallel?
- Does it avoid sensitive data and uncontrolled side effects?
- Is its maintenance cost proportionate to risk?

A test that cannot answer the first question is false confidence and must be strengthened or removed from the plan.
