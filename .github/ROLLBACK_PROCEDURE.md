# CI Pipeline Remediation — Emergency Rollback Procedure

**Status:** APPROVED & REHEARSED  
**Recovery Time:** ~10 minutes (5 min unblock + 5 min restore)  
**Scope:** CI orchestration only; no product/runtime changes

---

## Rollback Decision Tree

```
Is ci-required failing on new code?
├─ YES → Check if it's a legitimate failure (see Triage section)
│  ├─ YES → Fix the code, not CI
│  └─ NO → Proceed to Phase 1: UNBLOCK
└─ NO → No rollback needed
```

---

## Phase 1: Immediate Unblock (5 minutes)

**Objective:** Stop the cascade; permit critical/emergency merges while investigating.

### 1.1 Remove ci-required from branch rulesets

**File:** `.github/rulesets/main.json`

```bash
# Step 1: In GitHub UI (Settings → Rules → Rulesets)
#  OR via API/CLI, edit the ruleset to remove the required status check

# Current requirement:
# "required_status_checks": {
#   "strict": true,
#   "checks": [
#     { "context": "ci-required" }
#   ]
# }

# After removal:
# "required_status_checks": null  OR  "checks": []
```

Do the same for `.github/rulesets/dev-staging.json`.

### 1.2 Verify unblock

```bash
# Create a test PR or attempt merge on current branch
# Should NOT require ci-required status anymore
```

**Time elapsed:** ~5 minutes

---

## Phase 2: Investigation & Root Cause Analysis (variable time)

**Objective:** Determine if failure is in CI code, product code, dependency, or external outage.

### 2.1 Check the actual CI failure

**Gather evidence:**

```bash
# In the failed run, check the ci-evidence job for details
# Look for which mandatory signal failed:
# - repo-static → Actions/shell syntax issue
# - backend-static → Ruff/Pyright/Bandit issue
# - backend-offline → Test failure / coverage issue
# - backend-postgres → PostgreSQL test / migration issue
# - frontend-static → TypeScript/lint/build issue
# - frontend-vitest → Vitest/coverage issue
# - frontend-e2e → Playwright test issue
# - security[*] → Gitleaks / audit / IaC / image scan issue
# - sonar-pr → Sonar analysis / quality gate issue
```

### 2.2 Root cause categories

| Category | Investigation | Fix Belongs In |
|---|---|---|
| **Product code bug** | Test failure in offline/postgres/frontend-e2e | Code fix in product branch |
| **Dependency vulnerability** | High/Critical finding from pip/npm/Trivy/Grype audit | Dependency update (separate PR) |
| **CI infrastructure bug** | ci-evidence logic error / artifact validation / manifest parsing | CI workflow fix |
| **External outage** | Sonar unavailable / advisory database timeout | Wait for service recovery |
| **Transient failure** | Network timeout / rate limit / race condition | Rerun (GitHub UI) |

### 2.3 Decision

**If the root cause is:**

- **Product code** → Roll back product code, not CI. CI is correct.
- **Dependency vuln** → Land dependency fix in separate focused PR, then re-enable CI.
- **CI infrastructure** → Proceed to Phase 3.
- **External outage** → Wait for service recovery; Phase 1 unblock buys time.
- **Transient** → Rerun the job via GitHub UI; may resolve without rollback.

---

## Phase 3: Fix Implementation (time depends on root cause)

**Objective:** Implement the fix for a validated CI infrastructure bug.

### 3.1 Create a fix branch

```bash
git checkout -b fix/ci-<issue-description> main
# Make targeted fix to workflow/supporting scripts only
# DO NOT:
#  - Change product code
#  - Change database schema
#  - Change workflow manifests
#  - Change deploy/provision topology
```

### 3.2 Validate the fix locally

```bash
# Run affected policy/contract tests
cd backend
uv run pytest tests/ci/test_<affected_policy>.py -q
# e.g., if evidence job failed:
uv run pytest tests/ci/test_evidence_properties.py -q
```

### 3.3 Test the fix on a shadow branch

```bash
# Push the fix branch to a test PR
# Let the CI run through with the fix applied
# Verify:
# - ci-evidence succeeds
# - ci-required-shadow succeeds
# - No regressions in characterization/invariant tests
```

### 3.4 Merge the fix

```bash
# After validation, merge the fix to main
# (This assumes you already have emergency merge capability
#  due to Phase 1 unblock)
```

---

## Phase 4: Restore Protection (5 minutes)

**Objective:** Re-activate branch protection with confidence that the fix works.

### 4.1 Re-apply ci-required requirement

**File:** `.github/rulesets/main.json`

```bash
# Restore:
# "required_status_checks": {
#   "strict": true,
#   "checks": [
#     { "context": "ci-required" }
#   ]
# }
```

Do the same for `.github/rulesets/dev-staging.json`.

### 4.2 Verify restoration

```bash
# Create a test PR or attempt merge
# Should now require ci-required status
# Observe that the status is emitted by the trusted finalizer
#   (ci-authoritative.yml for PRs)
#   (sonar-inline for trusted intents)
```

### 4.3 Confirm one clean post-fix evaluation

```bash
# Merge a test commit to main
# Verify that CI runs to completion
# Verify that the fix didn't introduce new issues
# Verify characterization/invariant tests remain green
```

**Time elapsed:** ~5 minutes

---

## Rollback Decision Examples

### Example 1: Playwright Test Flake

**Symptom:** frontend-e2e job fails on a stale selector; only on this PR.

**Investigation:** Check the test error; it's a selector that changed in product code.

**Fix Location:** Product code (not CI).

**Decision:** DO NOT rollback CI. Fix the product code or the test.

---

### Example 2: Sonar Token Expired

**Symptom:** sonar-pr job times out after 10 minutes; Sonar API returns 401 Unauthorized.

**Investigation:** Check Sonar status page; token renewal or Sonar outage.

**Fix Location:** Infrastructure (not CI workflow).

**Decision:** Phase 1 unblock allows merges while Sonar recovers. Once Sonar is healthy, re-enable protection. No CI code change needed.

---

### Example 3: Evidence Manifest Parser Bug

**Symptom:** ci-evidence fails because the evidence parser crashes on a valid artifact.

**Investigation:** New artifact format from a preceding task introduced a bug in the parser.

**Fix Location:** CI code (tests/ci/test_evidence_properties.py or the parser itself).

**Decision:** Proceed with Phase 3; fix the parser, validate locally, test on shadow branch, merge fix, restore protection in Phase 4.

---

## Rollback Atomicity

**CRITICAL:** Workflow and ruleset changes are ONE ATOMIC UNIT.

```bash
# DO NOT do this:
# 1. Roll back workflow
# 2. Keep rulesets requiring ci-required
#    ↳ This leaves an orphaned required context!

# CORRECT:
# 1. Edit both workflow AND rulesets together
# 2. Merge as one atomic commit
# 3. Verify both are in sync after merge
```

---

## Communication Checklist

When invoking rollback:

- [ ] Notify on-call engineer
- [ ] Post incident summary to #incidents
- [ ] Document root cause in a comment on the rollback PR
- [ ] After fix is deployed, post all-clear to #incidents
- [ ] Schedule retrospective to prevent recurrence

---

## Testing Rollback (Pre-Production)

Before depending on this procedure in production:

```bash
# 1. In a non-protected test branch:
git checkout -b test/rollback-rehearsal main

# 2. Temporarily remove ci-required from rulesets (Phase 1)
# 3. Verify you can merge without ci-required
# 4. Restore ci-required (Phase 4)
# 5. Verify ci-required is required again
# 6. Clean up: `git branch -D test/rollback-rehearsal`
```

---

## Emergency Contacts

| Role | Contact | Escalation |
|---|---|---|
| CI Infrastructure | [on-call] | [escalation contact] |
| DevOps | [on-call] | [escalation contact] |
| Security | [on-call] | [escalation contact] |

---

## Appendix: No Rollback Needed Cases

Do **NOT** use this rollback procedure if:

- ✅ A test is flaky but ci-evidence eventually succeeds
- ✅ A product code commit broke tests (fix product code)
- ✅ A dependency update introduced a vulnerability (land dependency fix separately)
- ✅ The failure is transient/race (rerun the job via GitHub UI)
- ✅ An external service is temporarily down (wait for recovery)

Use this procedure **ONLY** if:

- 🔴 The CI workflow/orchestration code itself has a bug
- 🔴 The bug prevents the entire ci-required pipeline from working
- 🔴 The bug cannot be worked around by fixing product/dependency code

---

## Success Criteria for Rollback

After Phase 4, verify:

- ✅ ci-required status is restored in both rulesets
- ✅ A new protected-branch PR requires the status
- ✅ ci-required is emitted by the expected publisher
- ✅ One clean evaluation post-fix completes successfully
- ✅ Characterization/invariant tests remain green
- ✅ No new test failures introduced by the fix

If all criteria pass, **rollback recovery is complete** and the pipeline is restored to a safe state.
