# Reporting and FIX-TEST Registration

Load this reference when preparing the final QA result, writing a persistent QA report, documenting a defect, or registering a fix-linked test suite.

## 1. Verdict vocabulary

Use one overall verdict and preserve per-case detail.

| Verdict | Meaning |
|---|---|
| **PASS** | Every mandatory in-scope criterion ran and passed in the stated environment; no unresolved failure changes the conclusion |
| **FAIL** | At least one mandatory criterion produced a confirmed product or test failure that prevents success |
| **PARTIAL** | Useful evidence exists, but some planned/non-mandatory work did not run or remains unresolved |
| **BLOCKED** | Required permission, service, environment, data, credential, or tool prevented meaningful completion |
| **NOT RUN** | Planning/review only, or execution was intentionally not requested |

Per-case outcomes may be `PASS`, `FAIL`, `FLAKY`, `BLOCKED`, `SKIPPED`, `BY DESIGN`, `NOT VERIFIABLE`, `DEFERRED`, or `NOT RUN`. Classification explains the cause; outcome records the execution state. Use the classification `ENVIRONMENT/INFRASTRUCTURE` for unavailable or mismatched infrastructure and normally record its outcome as `BLOCKED`.

Rules:

- `PASS` is not compatible with an unresolved mandatory `FLAKY`, `BLOCKED`, `NOT VERIFIABLE`, or `DEFERRED` case.
- A build/lint/static pass cannot substitute for missing behavior evidence.
- A case that passed only after retry is `FLAKY`, not clean PASS.
- If a failure is a test defect and the product behavior was not independently proven, the product criterion remains unverified.

## 2. Results-first chat report

Use this compact order:

```markdown
## QA verdict: PASS | FAIL | PARTIAL | BLOCKED | NOT RUN

**Target:** <ticket/FIX/feature/files/revision>
**Mode / environment:** <verify|author|...> / <local|mocked E2E|staging|live>
**Scope:** <one paragraph>

### Results
| Area | Evidence | Outcome |
|------|----------|---------|
| ... | `<cwd> :: <command>` — <counts/duration> | PASS |

### Findings
| ID | Classification | Severity | Summary | Evidence |
|----|----------------|----------|---------|----------|
| ... | PRODUCT DEFECT | P1 | ... | ... |

### Coverage and gaps
- Covered: ...
- Not run / blocked / deferred / not verifiable: ...
- Residual risk: ...

### Artifacts and changes
- Test files: ...
- Reports/traces/screenshots: ...
- Register entry: ...

### Recommended next action
<one actionable next step; hand product defects to `velocity-fix` only if the user wants a fix>
```

Omit empty sections, but never omit gaps or residual risk.

## 3. Persistent QA report template

Create a persistent report only when the user requests it or an existing campaign/workflow requires one. Prefer the campaign's established location and format; do not create a parallel reporting system.

```markdown
# QA Report — <Target>

**Date:** YYYY-MM-DD
**Revision / working-tree basis:** <commit/branch/diff>
**Tester:** Kiro `/velocity-ai-test`
**Mode:** plan | verify | author | full | triage | explore | release
**Environment:** <local/mocked/staging/live plus relevant versions>
**Overall verdict:** PASS | FAIL | PARTIAL | BLOCKED | NOT RUN

## Objective and oracle
<What was tested and how correctness is decided.>

## Scope
### In scope
- ...

### Out of scope
- <item — reason and residual risk>

## Risk and traceability
| ID | Requirement / Risk | Score | Layer | Oracle | Mandatory / Waiver | Outcome |
|----|--------------------|------:|-------|--------|--------------------|---------|

## Execution evidence
| # | Working directory | Command / manual procedure | Exit | Result | Duration | Artifact |
|---|-------------------|----------------------------|------|--------|----------|----------|

## Findings
### <Finding ID> — <Title>
- Classification: PRODUCT DEFECT | TEST DEFECT | FLAKY/NONDETERMINISTIC | ENVIRONMENT/INFRASTRUCTURE | BY DESIGN | NOT VERIFIABLE | BLOCKED
- Severity: P0 | P1 | P2 | P3 | N/A
- Requirement/oracle: ...
- Expected: ...
- Actual: ...
- Evidence: ...
- Reproduction/frequency: ...
- Impact: ...
- Recommended next step: ...

## Coverage gaps and residual risk
- ...

## Files and artifacts
- ...

## Final assessment
<What is proven, what is not, and the next decision.>
```

## 4. Test-case table

Use stable IDs that remain meaningful when rows move. Do not use array position as identity.

```markdown
| Case ID | Requirement/Risk | Preconditions | Steps/Action | Expected | Layer | Mandatory/Waiver | Result | Evidence |
|---------|------------------|---------------|--------------|----------|-------|------------------|--------|----------|
```

For manual/exploratory campaigns, `BY DESIGN` and `NOT VERIFIABLE` are legitimate outcomes when supported by evidence. Keep them separate from `PASS`.

## 5. Defect handoff

A good QA finding lets `velocity-fix` begin without rediscovering the symptom.

```markdown
### <ID> — <Short observable failure>

**Classification:** PRODUCT DEFECT
**Severity:** P0 | P1 | P2 | P3
**Environment/revision:** ...
**Frequency:** deterministic | intermittent (<observed rate>)

#### Requirement / oracle
...

#### Preconditions
...

#### Minimal reproduction
1. ...
2. ...

#### Expected
...

#### Actual
...

#### Evidence
- Automated test: `<node id>`
- Command: `<cwd> :: <command>`
- Output/artifact: ...

#### Impact and blast radius
...

#### Suspected boundary
<Clearly label as suspected; do not claim root cause unless traced and proven.>

#### Regression coverage recommendation
<Lowest layer plus any distinct boundary layer.>
```

Never include a live token, auth header, connection string, customer content, secret-bearing URL, or unredacted PII.

## 6. When to update `.planning/FIX-TEST-REGISTER.md`

Update the register only when all are true:

1. The user explicitly requested new/updated test code or a full author-and-run workflow.
2. The test suite is linked to an existing `FIX-NNN` in `.planning/FIX-REGISTER.md`.
3. Test files were actually written or materially expanded.
4. The suite was executed, or the entry honestly records why execution is BLOCKED/FAIL.

Do not create a new TEST entry for:

- read-only test execution;
- a plan with no test code;
- generic feature QA with no FIX ID, unless the register format is deliberately changed by the user;
- an old suite rerun with no material new coverage;
- a product defect that has not entered the fix workflow.

If no FIX ID exists, do not invent one. Offer a standalone report or the appropriate issue/fix workflow.

## 7. Sequential TEST ID procedure

Immediately before editing:

1. Read the current `## Summary Table` and `## Detailed Test Entries`.
2. Find the highest numeric `TEST-NNN` across the entire file, not only the last visible row.
3. Choose the next integer, zero-padded to three digits.
4. Re-check that the ID does not already exist.
5. Preserve existing content and formatting; do not clean unrelated duplicate headings or old entries.
6. Add one summary row and one detailed entry with the same ID.

If another change lands between reading and writing, re-read and recalculate. Never renumber historical entries.

## 8. Summary row

Use the existing columns exactly:

```markdown
| TEST-NNN | FIX-NNN (ticket if any) | YYYY-MM-DD | `path/to/test_file.py`, `...` | <tests written> | <passed> | <failed> | PASS / FAIL / PARTIAL / BLOCKED |
```

`Tests Written` counts newly authored/materially added tests for this entry, not every test collected in a broad command. `Passed` and `Failed` refer to those tests when separable; explain mixed-suite counts in the detailed entry.

## 9. Detailed register entry

Append after the final existing detailed TEST entry under the last `## Detailed Test Entries` heading:

```markdown
### TEST-NNN — FIX-NNN (<Ticket>) — <Short title>

**Date:** YYYY-MM-DD
**Triggered by:** `/velocity-ai-test <original request or concise target>`
**Mode / environment:** author|full / local|mocked|staging|live

#### Fix Summary (from FIX-REGISTER)
- **Root cause:** <copy the factual summary; do not embellish>
- **Files fixed:** <paths>
- **Behavior changed:** <observable contract>

#### Coverage Rationale
| Requirement / Root-cause risk | Layer | Test case(s) | Why this layer |
|-------------------------------|-------|--------------|----------------|

#### Test Files Written
| File | Tests added | Framework |
|------|------------:|-----------|

#### Test Cases
| # | Test name | Requirement / purpose | Result |
|---|-----------|-----------------------|--------|

#### Run Evidence
Working directory: <cwd>
Command: <exact command>
Exit code: <n>
Result: <counts and duration>
<concise raw output with secrets/PII redacted>

#### Additional Gates
| Gate | Command | Result |
|------|---------|--------|

#### Verdict
- **Tests written:** <n>
- **Passed:** <n>
- **Failed:** <n>
- **Flaky/blocked/not run:** <n and explanation>
- **Status:** PASS | FAIL | PARTIAL | BLOCKED

#### Findings and Gaps
- <classification, evidence, and residual risk>

#### Notes
- <fixtures, mocks/fakes, environment, warnings, deferred layers>

#### Fix Confidence
- **High | Medium | Low** — <evidence-based reason; distinguish mocked/local/live proof>
```

Do not use "High" merely because all authored unit tests pass. Confidence reflects whether root-cause behavior, boundary risk, regression surface, and relevant gates were actually proven.

## 10. Release evidence record

For release mode, keep the human approval separate from the QA recommendation:

```markdown
## Release QA recommendation: GO | CONDITIONAL GO | NO-GO | BLOCKED

| Mandatory gate | Evidence | Outcome | Owner/waiver |
|----------------|----------|---------|--------------|

**Open P0/P1 defects:** ...
**Rollback/forward-fix evidence:** ...
**Monitoring/kill-switch evidence:** ...
**Residual risk:** ...
**Human approver required:** <role/name if known>
```

The agent recommends; an authorized human approves production deployment.

## 11. Report quality check

Before publishing:

- every PASS has current evidence;
- all commands include working directory and exit/result;
- counts distinguish authored tests from total collected tests;
- findings distinguish observation, suspected boundary, and confirmed root cause;
- no sensitive values appear;
- no gap is silently omitted;
- artifacts exist at the recorded paths;
- register IDs are sequential and unique;
- the overall verdict matches the worst mandatory unresolved outcome;
- the next action is specific and proportionate.
