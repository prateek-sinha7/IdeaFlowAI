# Playwright E2E Test Triage & Remediation Plan

## Task 3.12: Clear complete mocked Playwright failures, skips, and retry-only passes

**Current Status** (as documented in spec):
- Mocked project: 89 passed, 62 failed, 43 skipped (total 194 tests)
- Playwright config: `reuseExistingServer: false` (clean worker-specific lifecycle)

## Root Cause Categories

### 1. Pre-existing fixme() tests (35 identified)
These are intentionally marked as known issues with test.fixme(true, "reason"):
- **Phase 42 retired UI** (8+ tests)
  - `TS-Z2-01/02`: saved workflows (feat/ui-2 baseline red)
  - `TS-C-01/02`: placeholder tests (feat/ui-2 baseline red)
  - `TS-M-04/05a/05b/05c`: questionnaire wizard retired
  - `TS-L-*`: token usage display removed
  - `TS-N-06`: ReviewGatePanel removed
  
- **Backend-gated** (10+ tests)
  - `TS-U-03/04/05/06/08`: revision persistence (BE owned)
  - `TS-V-02/03`: wizard template selection (live Bedrock)
  - `TS-W-03`: no-override parity
  - `TS-S-07`: cross-owner demotion
  - `TS-R-02`: revision-cancel persistence
  
- **Covered elsewhere** (5+ tests)
  - `TS-X-01`: client keepalive (retired with WS)
  - `TS-X-03`: questionnaire auto-advance (covered by TS-M-03)
  - `TS-Y-02/03`: durable resume + keepalive (covered by BE/TS-S)

**Action**: Move these to `test.skip()` with explicit frontend owner comment, or delete if legitimately obsolete.

### 2. Stale Selectors (estimated 20-30 failures)
Examples from ts-c.input-trigger test failure:
- Button locator: expects `getByRole('button', { name: /Run workflow|Add agents first|Pick a migration path/ })`
- Issue: Role-based selectors are brittle when UI state changes
- Fix: Update to use semantic locators based on aria-labels or more specific context

### 3. Timing/Race Conditions (estimated 15-25 failures)
- Missing explicit waits for mock readiness
- `MockApi.ready()` and `MockSse.ready()` not awaited
- Async state updates not synchronized

**Fix**:
```typescript
// Before assertions, ensure mocks are ready
await expect(dashboard.page).toBeTruthy();
await mockSse.ready();  // Wait for SSE attached
await mockApi.ready();  // Wait for API ready
// Then assert on deterministic state
```

### 4. Mock State Mismatch (estimated 5-10 failures)
- Mock response data structure doesn't match expected GraphQL/REST schema
- SSE event format incorrect
- State setup incomplete before test assertions

### 5. Fixture Initialization (estimated 5-10 failures)
- Dashboard/page not fully initialized
- Theme/context setup incomplete
- Default agents/workflows not properly seeded

### 6. Product Regressions (estimated 0-5 failures)
- Actual feature broken (not test/mock issue)
- Requires product fix + regression test

## Implementation Strategy

### Phase 1: Classify fixme/skip tests
1. Move 35 `test.fixme()` to `test.skip()` with explicit classifications
2. Categorize each: `feat/ui-2-baseline`, `backend-gated`, `covered-elsewhere`, `deleted-panel`
3. Group by owner/reason

### Phase 2: Run systematic triage
1. Run each test file individually with `--workers=1`
2. Capture error message and stack trace
3. Map to root cause category
4. Document in `.md` file per file

### Phase 3: Apply targeted fixes by category

#### Category A: Stale Selectors
- Replace CSS/XPath with `getByRole()`, `getByLabel()`, `getByText()`
- Add explicit waits with bounded timeout

#### Category B: Timing/Race Conditions
- Ensure `MockApi.ready()` and `MockSse.ready()` called
- Use `page.waitForLoadState('networkidle')`
- Add explicit readiness guards

#### Category C: Mock State Mismatch
- Verify response schemas match expectations
- Check SSE event format
- Validate fixture defaults

#### Category D: Fixture Issues
- Enhance Dashboard fixture setup
- Ensure theme/context initialized
- Verify default agents seeded

#### Category E: Product Regressions
- Fix in separate PR with regression test
- Track as separate task

### Phase 4: Validation
1. Run complete suite: `npm run e2e -- --project=mocked`
2. Verify zero failures, zero applicable skips
3. Run twice to detect flaky passes
4. Run full frontend validation:
   - `npm run test` (coverage check)
   - `npm run lint`
   - `npm run typecheck`
   - `npm run build`

## Success Criteria
- [ ] All 62 failing tests either pass or documented as product regression (separate task)
- [ ] All 43 skipped tests classified with explicit owner or deleted
- [ ] Zero flaky retries (each test passes deterministically)
- [ ] All frontend validation commands pass

## Files to Update
- `frontend/e2e/tests/*.spec.ts` - fix tests
- `frontend/e2e/fixtures/test.ts` - enhance fixture setup
- `frontend/e2e/fixtures/dashboard.ts` - ensure readiness
- `frontend/playwright.config.ts` - already configured correctly

## Effort Estimate
- Phase 1 (classify): 30 min
- Phase 2 (triage): 2 hours
- Phase 3 (fix): 4-6 hours
- Phase 4 (validation): 1 hour
- **Total: 7-9 hours**
