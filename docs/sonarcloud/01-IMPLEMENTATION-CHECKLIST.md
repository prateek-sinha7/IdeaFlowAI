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
  - [ ] `coverage.xml` exists (Cobertura format)
  - [ ] `coverage-final.json` exists (v8 format)
  - [ ] `coverage.html/` directory exists

- [ ] **Validate XML format:**
  ```bash
  head -1 coverage/coverage.xml
  # Should output: <?xml version="1.0" ?>
  ```

### Steps (CI Verification - after first PR)
- [ ] **Trigger CI workflow:**
  - [ ] Create a test PR or push to a feature branch
  - [ ] Wait for GitHub Actions to run

- [ ] **Verify artifacts in CI:**
  - [ ] Go to your PR → **Checks** → **CI** workflow
  - [ ] Click the `frontend` job
  - [ ] Scroll down to **Artifacts** section
  - [ ] Verify `frontend-coverage-xml` artifact is listed and downloadable

---

## Phase 5: Test Coverage Consolidation Job (Task 4)

### Prerequisites
- [ ] CI workflow has the `prepare-sonarcloud` job (should be in `.github/workflows/ci.yml`)
- [ ] Test jobs are passing (backend pytest and frontend vitest)

### Steps (After first PR with changes)
- [ ] **Trigger CI workflow:**
  - [ ] Push to a feature branch or open a PR
  - [ ] Wait for all test jobs to complete

- [ ] **Verify prepare-sonarcloud job:**
  - [ ] Go to **Actions** tab in your repo
  - [ ] Click the workflow run
  - [ ] Find the `prepare-sonarcloud` job in the job list
  - [ ] Verify it shows **Status: ✓ Success** (green checkmark)

- [ ] **Verify coverage artifacts downloaded:**
  - [ ] In the `prepare-sonarcloud` job logs, look for:
    - [ ] `✓ Copied coverage-backend.xml`
    - [ ] `✓ Copied coverage-frontend.xml` (or similar)

- [ ] **Verify consolidated artifact uploaded:**
  - [ ] Scroll to **Artifacts** section
  - [ ] Verify `sonarcloud-coverage` artifact is listed
  - [ ] Download and verify it contains both XML files

---

## Phase 6: Test SonarScanner Integration (Task 5)

### Prerequisites
- [ ] SONAR_TOKEN is stored in GitHub Organization Secret
- [ ] prepare-sonarcloud job completes successfully
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

- [ ] **Set Quality Gate Conditions (Moderate Baseline):**
  - [ ] **Overall Code Coverage:** Add condition
    - [ ] Metric: `Coverage`
    - [ ] Operator: `is less than`
    - [ ] Value: `85%`
    - [ ] Error Message: "Coverage < 85%"
  
  - [ ] **Blocker Issues:** Add condition
    - [ ] Metric: `Blocker Issues`
    - [ ] Operator: `is greater than`
    - [ ] Value: `0`
    - [ ] Error Message: "Blocker issues found"
  
  - [ ] **Critical Issues:** Add condition
    - [ ] Metric: `Critical Issues`
    - [ ] Operator: `is greater than`
    - [ ] Value: `5`
    - [ ] Error Message: "Too many critical issues"
  
  - [ ] **Code Smells:** Add condition
    - [ ] Metric: `Code Smells`
    - [ ] Operator: `is greater than`
    - [ ] Value: `30`
    - [ ] Error Message: "Too many code smells"
  
  - [ ] **Duplications:** Add condition
    - [ ] Metric: `Duplicated Lines`
    - [ ] Operator: `is greater than`
    - [ ] Value: `3%`
    - [ ] Error Message: "Duplication > 3%"
  
  - [ ] **Maintainability Rating:** Add condition
    - [ ] Metric: `Maintainability Rating`
    - [ ] Operator: `is worse than`
    - [ ] Value: `A`
    - [ ] Error Message: "Maintainability rating < A"

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
- [ ] **Verify prepare-sonarcloud waits for test jobs:**
  - [ ] In `.github/workflows/ci.yml`, find `prepare-sonarcloud` job
  - [ ] Verify it has: `needs: [test-results, frontend]`
  - [ ] This ensures coverage artifacts are ready before consolidation

- [ ] **Verify sonarcloud-analysis waits for consolidation:**
  - [ ] In `.github/workflows/ci.yml`, find `sonarcloud-analysis` job
  - [ ] Verify it has: `needs: [prepare-sonarcloud]`
  - [ ] This ensures coverage is ready before analysis

- [ ] **Verify PR checks don't block each other:**
  - [ ] CI workflow should not have `sonarcloud-analysis` as a required check
  - [ ] If it is, enable "Allow merging without required status checks" or adjust settings

---

## Phase 10: Documentation & Runbook (Task 7)

### Prerequisites
- [ ] All previous phases complete
- [ ] Team is familiar with SonarCloud dashboard

### Steps
- [ ] **Review documentation:**
  - [ ] Read `docs/SONARCLOUD_INTEGRATION.md` (comprehensive guide)
  - [ ] Read `sonar-project.properties` (configuration reference)
  - [ ] Share with team

- [ ] **Create team guidelines:**
  - [ ] Add to team wiki or README:
    - [ ] When to check SonarCloud results
    - [ ] How to interpret quality gate failures
    - [ ] When to tighten/relax quality gate thresholds
    - [ ] SonarToken rotation schedule (yearly)

- [ ] **Test runbook tasks locally:**
  - [ ] Adjust quality gate thresholds (as described in `SONARCLOUD_INTEGRATION.md` Task 6)
  - [ ] View analysis results in SonarCloud dashboard
  - [ ] Verify PR check appears and correctly shows pass/fail status

---

## Troubleshooting

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
   - [ ] Check `prepare-sonarcloud` job
   - [ ] Download `sonarcloud-coverage` artifact
   - [ ] Verify it contains `coverage-backend.xml` and `coverage-frontend.xml`
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

### Issue: Frontend coverage shows 0% or is missing

**Solution:**
1. Verify frontend coverage XML is generated:
   - [ ] Run `npm run test` locally in `frontend/` directory
   - [ ] Check `coverage/coverage.xml` file exists
   - [ ] Is it valid XML? (starts with `<?xml`)
2. Verify artifact is uploaded in CI:
   - [ ] Check `frontend` job logs
   - [ ] Look for "Upload frontend coverage XML" step
   - [ ] Verify artifact `frontend-coverage-xml` is listed
3. Verify artifact is downloaded in consolidation:
   - [ ] Check `prepare-sonarcloud` job logs
   - [ ] Look for error about downloading `frontend-coverage-xml`
   - [ ] If not found, check artifact name matches in CI job

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
