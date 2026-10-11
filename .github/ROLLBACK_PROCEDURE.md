# CI Pipeline Remediation — Emergency Rollback Procedure

**Status:** Approval and rehearsal are not recorded in this repository. Rehearse it with "Testing Rollback (Pre-Production)" below and record the date and the person here.  
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
# - changes → path-filter issue (pull requests only)
# - repo-static → actionlint / shell syntax / ShellCheck / compose config issue
# - backend-static → Ruff/Pyright/Bandit issue
# - backend-offline → Test failure / coverage issue
# - backend-postgres → PostgreSQL test / migration issue
# - frontend-build → Next.js production build / standalone bundle issue
# - frontend-static → TypeScript/lint issue
# - frontend-vitest → Vitest/coverage issue
# - frontend-e2e → Playwright test issue
# - security[*] → Gitleaks / audit / IaC / image scan issue
```

### 2.2 Root cause categories

| Category | Investigation | Fix Belongs In |
|---|---|---|
| **Product code bug** | Test failure in offline/postgres/frontend-e2e | Code fix in product branch |
| **Dependency vulnerability** | High/Critical finding from pip/npm/Trivy/Grype audit | Dependency update (separate PR) (TEMPORARILY warn-only: reported as a warning, does not block; see CI_STATUS.md) |
| **CI infrastructure bug** | ci-evidence logic error / artifact validation / manifest parsing | CI workflow fix |
| **External outage** | Advisory database timeout / registry or artifact-store unavailable | Wait for service recovery |
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
uv run pytest tests/unit/tools/ci/test_<affected_policy>.py -q
# e.g., if evidence job failed:
uv run pytest tests/unit/tools/ci/test_evidence_aggregation.py -q
```

### 3.3 Test the fix on a shadow branch

```bash
# Push the fix branch to a test PR
# Let the CI run through with the fix applied
# Verify:
# - ci-evidence succeeds
# - ci-required is published by the expected publisher (the ci-required job
#   in ci.yml for trusted intents, ci-authoritative.yml for PRs); the earlier
#   shadow-mode ci-required-shadow context no longer exists
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
#   (the ci-required job in ci.yml for trusted intents)
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

### Example 2: Advisory Database Outage

> **TODO(security): TEMPORARY** - vulnerability scans are WARN-ONLY (advisory) as of 2026-10-11.
> In future this must be changed back to BLOCKING, and the outstanding High/Critical
> vulnerabilities must be fixed (see `backend/tools/ci/scan_accepts.py` and scan reports).

While the scans are warn-only, an outage appears as a "could not be evaluated" warning and does not fail the run or the deploy. Rerun to obtain a real verdict before relying on the image.

**Symptom:** a `container-scan[*]` signal fails because Trivy or Grype could not download its vulnerability database (registry/CDN 5xx or rate limit) rather than because a vulnerability was found. The gate reports the report as missing or empty.

**Investigation:** Check the database provider's status page; confirm from the scan step log that the scanner died on the DB download, not that the gated report holds a High/Critical finding.

**Fix Location:** Infrastructure (not CI workflow).

**Decision:** Rerun once the service recovers. Do NOT add an entry to `backend/tools/ci/scan_accepts.py` or `|| true` to make the step pass — a scan that could not run is a failed gate by design, not a waiver.

---

### Example 3: Evidence Manifest Parser Bug

**Symptom:** ci-evidence fails because the evidence parser crashes on a valid artifact.

**Investigation:** New artifact format from a preceding task introduced a bug in the parser.

**Fix Location:** CI code (backend/tests/unit/tools/ci/test_evidence_aggregation.py or the parser itself).

**Decision:** Proceed with Phase 3; fix the parser, validate locally, test on shadow branch, merge fix, restore protection in Phase 4.

---

## Rebuilt Host With an Expired Image

ECR keeps only the last N images per `dev-`, `stage-` and `prod-` tag prefix
(`infra/terraform/modules/ecr`). If a rebuilt dev or stage host's recorded digest
has expired from ECR, recover by re-running the Deploy workflow for that
environment. Prod releases are not affected: `v*` release tags carry no expiry rule. Break-glass
builds are tagged `prod-<branch>-<commit>`, so they are counted under the `prod-`
prefix and never push `dev-` or `stage-` images out.

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

**TODO (needs user input):** no contacts are recorded for this repository, and none
are invented here. For each of CI Infrastructure, DevOps and Security, supply:

- the primary contact or a link to the on-call rota,
- the escalation contact,
- a paging channel, and
- the date the entry was last confirmed.

Until this is filled in, the Communication Checklist step "Notify on-call engineer"
has no addressee. Do not reuse the `@Hexaware-HnI/*` teams named in
`.github/CODEOWNERS`: `.github/dependabot.yml` records that they do not exist in
the organization.

| Role | Primary contact / rota | Escalation | Paging channel | Last confirmed |
|---|---|---|---|---|
| CI Infrastructure | _TODO_ | _TODO_ | _TODO_ | _TODO_ |
| DevOps | _TODO_ | _TODO_ | _TODO_ | _TODO_ |
| Security | _TODO_ | _TODO_ | _TODO_ | _TODO_ |

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
