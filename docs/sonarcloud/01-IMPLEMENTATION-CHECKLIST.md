# SonarCloud Integration — Implementation Checklist

This checklist guides you through completing the SonarCloud integration. The CI workflow changes have been implemented; this checklist covers the remaining manual setup and verification steps.

---

## Phase 1: SonarCloud Account & Project Setup (Task 1)

### Prerequisites
- [ ] GitHub organization account exists (e.g., `velocityai`)
- [ ] You have admin/owner access to the GitHub organization
- [ ] The `velocityai` repository is public or your org has private repo access in SonarCloud

### Steps
- [ ] **Create SonarCloud Account:** Go to https://sonarcloud.io and click **Sign up**
  - [ ] Select **GitHub** as DevOps platform
  - [ ] Authorize SonarCloud to access your GitHub organization
  - [ ] Confirm your GitHub organization name in SonarCloud (should auto-populate)

- [ ] **Create SonarCloud Organization:** During signup, SonarCloud prompts you to create an organization
  - [ ] Organization name: `velocityai` (matches your GitHub org)
  - [ ] Organization key: `velocityai` (auto-generated or set manually)
  - [ ] Select subscription plan: **Free** (sufficient for OSS; upgrade if needed)
  - [ ] Note the organization key for later use in CI

- [ ] **Import Repository:** After organization creation, SonarCloud prompts to import projects
  - [ ] Find and select `velocityai` repository
  - [ ] Click **Import** (SonarCloud creates a project automatically)
  - [ ] Note the **Project Key** (usually `velocityai`)
  - [ ] Verify **Main Branch** is set to `main`

- [ ] **Verify Project Created:** 
  - [ ] Navigate to https://sonarcloud.io/dashboard?id=velocityai
  - [ ] Confirm you see the SonarCloud project dashboard (analysis may be pending)

---

## Phase 2: Generate SONAR_TOKEN (Task 1 continued)

### Steps
- [ ] **Login to SonarCloud:** https://sonarcloud.io
- [ ] **Navigate to Security Token Generator:**
  - [ ] Click your avatar (top-right)
  - [ ] Select **My Account**
  - [ ] Click **Security** tab
  - [ ] Under **Generate Tokens**, enter name: `velocityai-ci`
  - [ ] Click **Generate**
  
- [ ] **Copy and Store Token:**
  - [ ] **IMMEDIATELY copy the token** (displayed once, then hidden)
  - [ ] Store in a secure location (password manager, 1Password, etc.)
  - [ ] Do NOT commit to git, do NOT send in chat
  - [ ] If you miss the copy, revoke and regenerate a new token

- [ ] **Find and click the old token (e.g., `velocityai-ci`)**
- [ ] **Record SonarCloud Details:**
  - [ ] Organization Key: `velocityai` (or your org name)
  - [ ] Project Key: `velocityai`
  - [ ] SONAR_TOKEN: `[securely stored]`

---

## Phase 3: Configure GitHub Organization Secret (Task 2)

### Prerequisites
- [ ] You have the SONAR_TOKEN from Phase 2
- [ ] You have admin access to your GitHub organization settings

### Steps
- [ ] **Navigate to GitHub Organization Secrets:**
  - [ ] Go to https://github.com/organizations/{your-org}/settings/secrets/actions
  - [ ] Replace `{your-org}` with your GitHub organization name (e.g., `velocityai`)

- [ ] **Create New Organization Secret:**
  - [ ] Click **New organization secret** (green button)
  - [ ] **Name:** `SONAR_TOKEN`
  - [ ] **Value:** Paste the token from Phase 2
  - [ ] **Repository access:** Select **All repositories** (or select specific repos)
  - [ ] Click **Add secret**

- [ ] **Verify Secret Created:**
  - [ ] Secret appears in the list as `SONAR_TOKEN`
  - [ ] (Value is hidden for security; you should not see the token after creation)

---

## Phase 4: Verify Frontend Coverage XML Export (Task 3)

### Prerequisites
- [ ] Frontend directory is available locally (or in CI logs)
- [ ] `npm` is available

### Steps (Local Verification)
- [ ] **Run frontend tests locally:**
  ```bash
  cd frontend
  npm ci
  npm run test
  ```

- [ ] **Verify coverage files are generated:**
  ```bash
  ls -la coverage/
  ```
  - [ ] `lcov.info` exists — **this is the file SonarCloud reads for JS/TS**
  - [ ] `coverage-final.json` exists (v8 format, used by Codecov)
  - [ ] `index.html` exists (browsable report)
  - [ ] There is **no** `coverage.xml` / `coverage-final.xml`, and there should
        not be. Sonar consumes LCOV for JavaScript/TypeScript. The `"xml"`
        entry that used to be in `vitest.config.ts`'s reporter list was not a
        valid coverage reporter: it failed to load its own module and made
        `npm run test` exit 1 *after* every test had already passed.

- [ ] **Validate the LCOV format:**
  ```bash
  head -2 coverage/lcov.info
  # Should output a TN: line followed by SF:<path>
  ```

- [ ] **Check the coverage thresholds are the ratchet floors, not 80:**
  `frontend/vitest.config.ts` holds floors at the measured baseline
  (statements 46 / branches 44 / functions 45 / lines 48). An 80% *overall*
  frontend gate is unreachable today and is deliberately not set here — the
  80% standard is enforced by SonarCloud on **new code** instead.

### Steps (CI Verification - after first PR)
- [ ] **Trigger CI workflow:**
  - [ ] Create a test PR or push to a feature branch
  - [ ] Wait for GitHub Actions to run

- [ ] **Verify artifacts in CI:**
  - [ ] Go to your PR → **Checks** → **CI** workflow
  - [ ] Click the `frontend` job
  - [ ] Scroll down to **Artifacts** section
  - [ ] Verify the `frontend-coverage-lcov` artifact is listed and downloadable
        (it is uploaded with `if-no-files-found: error`, so a missing report
        fails the job rather than passing quietly)

---

## Phase 5: Coverage artifacts reach the scanner

> **This phase replaces the old "Test Coverage Consolidation Job (Task 4)".**
> There is no longer a `prepare-sonarcloud` job — it was **deleted**, because it
> could not work. It downloaded the `backend-coverage-report` artifact (which
> contained only `htmlcov/`, never `coverage.xml`) and looked for
> `coverage-final.xml` in the frontend artifact (which vitest never wrote). Both
> of its `if [ -f ... ]` guards therefore always took the `else` branch, printed
> a warning to stderr, and the job still exited 0 — so SonarCloud received **zero
> coverage while every job reported success**.
>
> Each report is now uploaded by the job that produces it and downloaded
> directly to the path `sonar-project.properties` names. Nothing is consolidated.

### Prerequisites
- [ ] Test jobs are passing (backend pytest and frontend vitest)

### Steps (After first PR with changes)
- [ ] **Trigger CI workflow:**
  - [ ] Push to a feature branch or open a PR
  - [ ] Wait for all test jobs to complete

- [ ] **Verify the two coverage artifacts exist:**
  - [ ] `backend-coverage-xml` — produced by the `test-results` job, contains
        `backend/coverage.xml` (Cobertura, from `coverage xml` after
        `coverage combine` merges all four pytest shards)
  - [ ] `frontend-coverage-lcov` — produced by the `frontend` job, contains
        `frontend/coverage/lcov.info`
  - [ ] Both upload with `if-no-files-found: error`

- [ ] **Verify the path normalisation steps ran:**
  Sonar runs from the repo root, so both reports are rewritten to repo-relative
  paths first. Neither is optional — an unresolvable path makes Sonar report 0%
  for that file *without* failing.
  - [ ] `frontend` job → **"Normalise LCOV paths for SonarCloud"**: rewrites
        `SF:src/...` to `SF:frontend/src/...`
  - [ ] `test-results` job → **"Normalise coverage.xml source paths for
        SonarCloud"**: rewrites `<source>app</source>` to
        `<source>backend/app</source>`. `backend/pyproject.toml` sets
        `relative_files = true` so these roots are relative in the first place
        rather than absolute `/home/runner/work/...` paths from the shard runner.

---

## Phase 6: Test SonarScanner Integration (Task 5)

### Prerequisites
- [ ] SONAR_TOKEN is stored in GitHub Organization Secret
- [ ] The `test-results` and `frontend` jobs complete successfully
      (`sonarcloud-analysis` declares `needs: [test-results, frontend]`)
- [ ] CI workflow has the `sonarcloud-analysis` job

### Steps (First Run - Expect Initial Analysis)
- [ ] **Trigger workflow:**
  - [ ] Push to a feature branch or open a PR

- [ ] **Monitor sonarcloud-analysis job:**
  - [ ] Go to **Actions** → workflow → `sonarcloud-analysis` job
  - [ ] Watch logs for:
    - [ ] `SonarScanner downloaded` ✓
    - [ ] `SonarScanner installed successfully` ✓
    - [ ] `SonarScanner analysis completed` ✓ (may take 1-2 minutes)

- [ ] **Handle initial analysis:**
  - [ ] First analysis may report many issues (expected if starting from scratch)
  - [ ] Quality gate may fail (expected; project is new to SonarCloud)
  - [ ] This is **not a CI failure**; it's baseline analysis

- [ ] **Verify SonarCloud received analysis:**
  - [ ] Go to https://sonarcloud.io/dashboard?id=velocityai
  - [ ] Refresh the page a few times (analysis may take a minute to appear)
  - [ ] Verify you see:
    - [ ] **Coverage %** (should show combined backend + frontend coverage)
    - [ ] **Issues** count (bugs, vulnerabilities, code smells)
    - [ ] **Code Smells** count
    - [ ] Analysis timestamp (recent)

---

## Phase 7: Configure Quality Gate (Task 6)

### Prerequisites
- [ ] SonarCloud project exists and has received initial analysis
- [ ] You have access to SonarCloud project settings

### Steps
- [ ] **Create or Edit Quality Gate:**
  - [ ] Go to https://sonarcloud.io/dashboard?id=velocityai
  - [ ] Click **Project Settings** (gear icon, top-right)
  - [ ] Click **Quality Gates** in left sidebar

- [ ] **Create new Quality Gate (or edit existing):**
  - [ ] If creating new: Click **+ Create**, name it `VelocityAI Moderate`
  - [ ] If editing: Click on the existing gate (usually "Sonar way")

- [ ] **Set Quality Gate Conditions (Clean as You Code — New Code Only):**
  > **IMPORTANT:** All conditions below are set on **NEW CODE** only, not overall metrics.
  > This keeps PRs focused on their own changes rather than asking them to retroactively
  > cover legacy code. Overall regression is blocked separately by coverage ratchet floors.
  
  - [ ] **Coverage on New Code:** Add condition
    - [ ] Metric: `Coverage on New Code`
    - [ ] Operator: `is less than`
    - [ ] Value: `80%`
    - [ ] Error Message: "Coverage on new code < 80%"
  
  - [ ] **New Blocker Issues:** Add condition
    - [ ] Metric: `New Blocker Issues`
    - [ ] Operator: `is greater than`
    - [ ] Value: `0`
    - [ ] Error Message: "New blocker issues found"
  
  - [ ] **New Critical Issues:** Add condition
    - [ ] Metric: `New Critical Issues`
    - [ ] Operator: `is greater than`
    - [ ] Value: `0`
    - [ ] Error Message: "New critical issues found"
  
  - [ ] **Duplicated Lines on New Code:** Add condition
    - [ ] Metric: `Duplicated Lines on New Code`
    - [ ] Operator: `is greater than`
    - [ ] Value: `3%`
    - [ ] Error Message: "New code duplication > 3%"
  
  - [ ] **Maintainability Rating on New Code:** Add condition
    - [ ] Metric: `Maintainability Rating on New Code`
    - [ ] Operator: `is worse than`
    - [ ] Value: `A`
    - [ ] Error Message: "Maintainability rating on new code < A"
  
  - [ ] **Reliability Rating on New Code:** Add condition
    - [ ] Metric: `Reliability Rating on New Code`
    - [ ] Operator: `is worse than`
    - [ ] Value: `A`
    - [ ] Error Message: "Reliability rating on new code < A"
  
  - [ ] **Security Rating on New Code:** Add condition
    - [ ] Metric: `Security Rating on New Code`
    - [ ] Operator: `is worse than`
    - [ ] Value: `A`
    - [ ] Error Message: "Security rating on new code < A"

- [ ] **Save Quality Gate:**
  - [ ] Click **Save** or **Update** button
  - [ ] Quality gate is now created

- [ ] **Associate with Project:**
  - [ ] Make sure you're viewing the quality gate you just created/edited
  - [ ] Look for **Set as default for this project** or similar button
  - [ ] Click it to associate with `velocityai` project
  - [ ] Verify message confirms association

- [ ] **Enable PR Checks:**
  - [ ] Go to `velocityai` project → **Project Settings**
  - [ ] Ensure **PR Decoration** is enabled (should be by default)
  - [ ] This ensures SonarCloud posts quality gate checks to PRs

---

## Phase 8: Test PR Quality Gate (Task 5 + 6)

### Prerequisites
- [ ] Quality gate is configured and associated with project
- [ ] Previous test PR has completed sonarcloud-analysis job

### Steps
- [ ] **Open test PR:**
  - [ ] Create a test PR with a meaningful code change (or amend an existing one)
  - [ ] Wait for CI to complete (all jobs including `sonarcloud-analysis`)

- [ ] **Verify SonarCloud PR Check:**
  - [ ] Go to your test PR
  - [ ] Scroll to **Checks** section
  - [ ] Look for **SonarCloud Quality Gate** check
  - [ ] Verify it shows:
    - [ ] **Status:** Pass (✓) or Fail (✗)
    - [ ] **Details:** Summary of quality gate evaluation

- [ ] **If Quality Gate PASSES:**
  - [ ] ✓ Check shows green "PASSED"
  - [ ] Merge button shows green (no SonarCloud block)
  - [ ] This means your code meets all quality thresholds!

- [ ] **If Quality Gate FAILS:**
  - [ ] ✗ Check shows red "FAILED"
  - [ ] Merge button shows red (SonarCloud blocks merge)
  - [ ] Click **Details** to see which thresholds failed (e.g., "Coverage < 85%")
  - [ ] This is expected for initial analysis; review and adjust quality gate if needed

- [ ] **Review PR Comment:**
  - [ ] SonarCloud posts a comment with analysis summary
  - [ ] Comment shows:
    - [ ] Issues found
    - [ ] Coverage change (vs main branch)
    - [ ] Quality gate status
    - [ ] Link to full analysis

---

## Phase 9: Verify CI Job Dependencies (Optional, Advanced)

### Purpose
Ensure CI jobs are correctly ordered and don't run unnecessarily.

### Steps
- [ ] **Verify sonarcloud-analysis waits for both report producers:**
  - [ ] In `.github/workflows/ci.yml`, find the `sonarcloud-analysis` job
  - [ ] Verify it has: `needs: [test-results, frontend]`
  - [ ] There is no `prepare-sonarcloud` job to depend on — it was removed
        (see Phase 5)

- [ ] **Verify the scanner blocks on the gate verdict:**
  - [ ] The "Run SonarScanner analysis" step passes
        `-Dsonar.qualitygate.wait=true`
  - [ ] Without it the step reports success for *"the report uploaded"*, which
        is a different fact from *"the quality gate passed"*

- [ ] **Understand which checks gate a merge — this part is easy to get wrong:**
  - [ ] `sonarcloud-analysis` is **deliberately excluded** from `ci-required`,
        because SonarCloud is an external service and `ci-required` should not
        depend on its availability
  - [ ] Therefore the **SonarCloud quality gate must be its own required status
        check** in the repository ruleset, listed *alongside* `ci-required`
  - [ ] Until that ruleset entry exists, a failing quality gate does **not**
        block a merge, regardless of `sonar.qualitygate.wait`
  - [ ] Confirm both are required: `ci-required` **and** the SonarCloud check

---

## Phase 10: Documentation & Runbook (Task 7)

### Prerequisites
- [ ] All previous phases complete
- [ ] Team is familiar with SonarCloud dashboard

### Steps
- [ ] **Review documentation:**
  - [ ] Read `02-INTEGRATION-GUIDE.md` (comprehensive guide)
  - [ ] Read `sonar-project.properties` (configuration reference)
  - [ ] Share with team

- [ ] **Create team guidelines:**
  - [ ] Add to team wiki or README:
    - [ ] When to check SonarCloud results
    - [ ] How to interpret quality gate failures
    - [ ] When to tighten/relax quality gate thresholds
    - [ ] SonarToken rotation schedule (yearly)

- [ ] **Test runbook tasks locally:**
  - [ ] Adjust quality gate thresholds (as described in `02-INTEGRATION-GUIDE.md` Task 6)
  - [ ] View analysis results in SonarCloud dashboard
  - [ ] Verify PR check appears and correctly shows pass/fail status

---

### Issue: `SONAR_TOKEN not found` error in CI logs

**Solution:**
1. Verify GitHub Organization Secret exists:
   - [ ] Go to GitHub Org Settings → Secrets and variables → Actions
   - [ ] Search for `SONAR_TOKEN`
   - [ ] Confirm it's listed
2. Verify secret is accessible to this repo:
   - [ ] Secret should have "All repositories" access
   - [ ] Or explicitly include this repo in selected repositories
3. Wait a few minutes for secret to propagate (GitHub sometimes has delays)

### Issue: SonarCloud doesn't receive analysis (dashboard shows no data)

**Solution:**
1. Check `sonarcloud-analysis` job logs:
   - [ ] Click job → scroll through logs
   - [ ] Look for error messages (network, auth, file not found)
2. Verify coverage files exist:
   - [ ] In the `sonarcloud-analysis` job, read the **"Verify coverage reports
         are present and non-empty"** step — it hard-fails and names the missing
         file, so this is usually the fastest answer
   - [ ] Download the `backend-coverage-xml` artifact (from `test-results`) and
         the `frontend-coverage-lcov` artifact (from `frontend`)
3. Manually verify credentials:
   - [ ] Is SONAR_TOKEN correct? (regenerate if uncertain)
   - [ ] Is organization key correct? (`velocityai` or your org name)
   - [ ] Is project key correct? (`velocityai`)

### Issue: Quality gate always shows PASS but thresholds don't seem right

**Solution:**
1. Verify quality gate is associated with project:
   - [ ] Go to SonarCloud project → Project Settings → Quality Gates
   - [ ] Confirm the quality gate is marked as **Active** for this project
2. Verify rules are correctly configured:
   - [ ] Click on the quality gate to view its conditions
   - [ ] Confirm all thresholds are set (not missing or set to 0%)
3. Check if PR is against main branch:
   - [ ] Quality gate compares PR against main branch
   - [ ] If PR is from a feature branch to main, this is correct
   - [ ] If PR is to a different branch, gate may not apply

### Issue: Coverage shows 0% for a language, but the scanner succeeded

This is the single most likely SonarCloud failure in this repo, and it is
**silent**: an unresolvable path is not an error to Sonar. It drops the entry,
reports the file as uncovered, and the scanner still exits 0.

**Solution:**
1. Confirm the report reached the scanner at all:
   - [ ] `sonarcloud-analysis` → "Verify coverage reports are present and
         non-empty" (fails loudly if either is missing/empty)
2. Confirm the scanner is reading the right **property** per language.
   In `sonar-project.properties`:
   - [ ] `sonar.python.coverage.reportPaths=backend/coverage.xml`
   - [ ] `sonar.javascript.lcov.reportPaths=frontend/coverage/lcov.info`
   - [ ] There must be **no** `sonar.coverageReportPaths` entry. That property
         accepts only Sonar's own *Generic Test Data* XML schema — not
         Coverage.py's Cobertura output and not istanbul's. Pointing both
         reports at it (the previous configuration) parsed neither and produced
         0% for both languages.
3. Confirm **paths resolve from the repo root**, which is where the scanner runs:
   - [ ] Frontend: `grep -m1 '^SF:' frontend/coverage/lcov.info` must show
         `SF:frontend/src/...` — not `SF:src/...`
   - [ ] Backend: `grep -o '<source>[^<]*</source>' backend/coverage.xml` must
         show `backend/app` and `backend/agents` — not bare `app`/`agents`, and
         not an absolute `/home/runner/work/...` path
   - [ ] Both are produced by the two "Normalise ... paths for SonarCloud" steps.
         To check by hand, join each Cobertura `<source>` with a
         `<class filename="...">` and confirm the file exists.
4. Frontend only — confirm the report is generated locally:
   - [ ] `npm run test` in `frontend/`, then check `coverage/lcov.info` exists
   - [ ] There is intentionally no `coverage.xml`; Sonar reads LCOV for JS/TS

---

## Success Criteria — Project Complete

Once you've completed all phases and passed troubleshooting, your SonarCloud integration is complete. Verify:

- [ ] SonarCloud project exists at https://sonarcloud.io/dashboard?id=velocityai
- [ ] Dashboard shows coverage, issues, and other metrics
- [ ] Quality gate is configured and associated with project
- [ ] Test PR shows SonarCloud check (pass or fail)
- [ ] Merge is blocked if quality gate fails (on main branch PRs)
- [ ] Team understands how to read/interpret SonarCloud results
- [ ] Runbook and documentation are in place

**Congratulations!** Your SonarCloud integration is now live. 🎉

---

## Next Steps

1. **Monitor & Iterate:**
   - Review first few PRs and quality gate results
   - Adjust thresholds based on team feedback

2. **IDE Integration (Optional):**
   - Install [SonarQube for IDE](https://docs.sonarsource.com/sonarqube-for-ide/) in your editor
   - Get real-time feedback while coding

3. **Metrics Tracking:**
   - Create dashboard to track coverage/quality trends over time
   - Set quarterly goals for improvement

4. **Security Hotspots:**
   - Review security hotspots in SonarCloud regularly
   - Include in security review process

---

**Last Updated:** August 27, 2026  
**Maintainer:** DevOps / Platform Team
