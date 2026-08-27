# SonarCloud Integration Guide

## Overview

SonarCloud is a cloud-based code quality and security analysis platform integrated into our CI/CD pipeline. It continuously analyzes code pushed to the repository and enforces quality gates on pull requests, helping the team maintain high standards for code quality, security, and maintainability.

### Why SonarCloud?

- **Unified Analysis:** Single dashboard for backend (Python) and frontend (TypeScript/React) code quality
- **Security-First:** Detects vulnerabilities, code smells, and potential bugs before they reach production
- **PR Integration:** Automatically decorates pull requests with quality gate results
- **Merge Blocking:** Prevents PRs from merging if they fail quality gates, ensuring all code meets standards
- **SaaS Simplicity:** No infrastructure overhead; scales automatically with your needs

### Key Components

1. **SonarCloud Project:** Hosted analysis dashboard at https://sonarcloud.io
2. **SonarScanner:** CLI tool that runs in CI, scans code, and publishes results to SonarCloud
3. **Quality Gate:** Policy defining code quality thresholds (coverage, issues, code smells, etc.)
4. **Coverage Reports:** XML files from backend (pytest) and frontend (vitest) combined for unified analysis

---

## Setup Instructions (Task 1)

### Step 1: Create SonarCloud Account & Organization

1. Go to https://sonarcloud.io
2. Click **Sign up** (you can use your GitHub account for quick signup)
3. Select **GitHub** as your DevOps platform
4. Authorize SonarCloud to access your GitHub organization
5. Create a new SonarCloud organization (it mirrors your GitHub org, e.g., "velocityai")

### Step 2: Import Your Repository

1. In SonarCloud, go to **Create project**
2. Select your GitHub organization
3. Find and select the `velocityai` repository
4. Click **Import** (SonarCloud creates a project automatically)
5. Note the **Project Key** (usually `velocityai`) and **Organization Key** (e.g., `velocityai`)

### Step 3: Generate SONAR_TOKEN

1. Log into SonarCloud and navigate to **My Account** (top-right menu)
2. Go to **Security** tab
3. Under **Generate Tokens**, click **Generate**
4. Name the token: `velocityai-ci` (or similar)
5. Select scope: **Execute analysis** (or the default)
6. Click **Generate**
7. **Copy the token immediately** (it won't be shown again)
8. Store it in a secure location (you'll add it to GitHub Secrets in Task 2)

### Step 4: Verify Project Settings

1. In SonarCloud, navigate to your `velocityai` project
2. Go to **Project Settings** → **General**
3. Confirm:
   - **Project Key:** `velocityai`
   - **Main Branch:** `main`
   - **Visibility:** Private (if your repo is private)
4. Go to **Project Settings** → **New Code Definition**
   - Set to **Previous version** (compares against last release tag or default branch)
   - This focuses analysis on new/changed code in PRs

---

## GitHub Organization Secret (Task 2)

### Storing SONAR_TOKEN

To allow CI workflows to authenticate with SonarCloud, store the token as a GitHub Organization Secret:

1. Go to your GitHub organization settings: https://github.com/organizations/{org}/settings
2. In the left sidebar, click **Secrets and variables** → **Actions**
3. Click **New organization secret**
4. **Name:** `SONAR_TOKEN`
5. **Value:** Paste the token from Step 3 above
6. **Access:** Select **All repositories** (or restrict to specific repos)
7. Click **Add secret**

### Verification

The secret is now accessible to all workflows in the organization as `secrets.SONAR_TOKEN`. The CI pipeline uses this in the `sonarcloud-analysis` job to authenticate with SonarCloud.

---

## Quality Gate Thresholds (Task 6 - Initial Config)

The following thresholds are the **moderate baseline** for the initial quality gate. These are intentionally achievable but enforce meaningful standards. Over time, you can tighten these as the codebase improves.

### Current Quality Gate Policy

| Metric | Threshold | Rationale |
|--------|-----------|-----------|
| **Overall Line Coverage** | ≥ 85% | Encourages comprehensive test coverage while allowing reasonable exclusions (e.g., error paths, UI edge cases) |
| **Blocker Issues** | = 0 | Critical security/correctness issues must never be merged |
| **Critical Issues** | ≤ 5 | Allows some non-critical issues to be addressed in follow-ups, avoiding false PR blocks |
| **Code Smells** | ≤ 30 | Maintainability gate; reviewable code is easier to maintain and test |
| **Duplications** | ≤ 3% | Prevents code duplication; encourages reusable components and functions |
| **Maintainability Rating** | A | SonarCloud A/B/C/D/E scale; A = excellent, E = poor |
| **Security Rating** | A | Same scale; A = no vulnerabilities |
| **Security Hotspots** | Review required | Flagged but doesn't fail; security team reviews as part of PR process |

### Adjusting Thresholds

If PRs frequently fail on specific metrics, you can adjust thresholds in **Project Settings** → **Quality Gates** (see Task 6 for instructions). Common adjustments:

- **Coverage too strict?** Reduce from 85% to 80% or exclude test-heavy modules
- **Too many code smells?** Increase from 30 to 50 and plan a refactoring sprint
- **Duplications spike?** Review for copy-paste code; may indicate need for shared utility functions

---

## CI Integration Flow

The integration works in the following sequence:

```
Developer Push
       ↓
GitHub Actions Triggers CI Workflow
       ↓
[Test Jobs: pytest shards + vitest]
       ├─ pytest (agents-a, agents-b, unit, integration)
       │  └─ Produces: coverage-agents-a.xml, coverage-agents-b.xml, coverage-unit.xml, coverage-integration.xml
       │
       ├─ vitest (frontend tests + coverage)
       │  └─ Produces: coverage-final.json + coverage.xml (Cobertura)
       │
       └─ test-results job merges backend coverage
          └─ Produces: backend/coverage.xml
       ↓
[prepare-sonarcloud Job]
       ├─ Downloads backend/coverage.xml
       ├─ Downloads frontend/coverage.xml
       └─ Uploads sonarcloud-coverage/ artifact
       ↓
[sonarcloud-analysis Job]
       ├─ Installs SonarScanner CLI
       ├─ Runs analysis with coverage files
       ├─ Publishes results to SonarCloud
       └─ SonarCloud posts PR check + comment
       ↓
Quality Gate Evaluation
       ├─ Pass → PR check ✓ (can merge)
       └─ Fail → PR check ✗ (merge blocked)
```

---

## Viewing Analysis Results

### SonarCloud Dashboard

**Project Overview:** https://sonarcloud.io/dashboard?id=velocityai

View:
- **Coverage:** Overall and per-file line/branch/function coverage
- **Issues:** Bugs, vulnerabilities, code smells (searchable/filterable)
- **Hotspots:** Security-sensitive areas requiring review
- **Duplications:** Duplicate code blocks by percentage

### Pull Request Checks

When a PR is opened:
1. SonarCloud runs analysis on the PR branch
2. A check comment is posted to the PR (e.g., "SonarCloud Quality Gate: PASSED ✓" or "FAILED ✗")
3. The PR check status appears next to the merge button (green = pass, red = fail)
4. Clicking the check shows details: which thresholds failed, specific violations, etc.

### GitHub Actions Logs

For troubleshooting CI issues:
1. Go to your repo: **Actions** tab
2. Click the failing workflow run
3. Click **sonarcloud-analysis** job
4. View logs for:
   - Coverage file discovery (did SonarScanner find the XML files?)
   - Analysis completion (did SonarCloud receive the analysis?)
   - PR decoration (did SonarCloud post the check?)

---

## Common Tasks (Runbook)

### Task: Adjust Quality Gate Thresholds

**Scenario:** Your team decides 85% coverage is too strict; you want to lower it to 80%.

**Steps:**
1. Log into SonarCloud: https://sonarcloud.io
2. Navigate to your `velocityai` project
3. Click **Project Settings** (gear icon, top-right)
4. Click **Quality Gates** in the left sidebar
5. Find and click the active quality gate (e.g., "SonarQube Way")
6. Edit the **Coverage** condition: change 85% to 80%
7. Click **Update**
8. Verify: Next PR should use the new threshold

**Note:** Changes take effect immediately for new PRs; existing PR checks won't update.

### Task: Rotate SONAR_TOKEN

**Scenario:** Your security policy requires token rotation every 6 months.

**Steps:**
1. In SonarCloud: **My Account** → **Security**
2. Find the old token (e.g., `velocityai-ci`)
3. Click **Revoke** (it cannot be recovered; you'll generate a new one)
4. Click **Generate** to create a new token
5. Copy the new token
6. In GitHub: Organization Settings → **Secrets and variables** → **Actions**
7. Click on `SONAR_TOKEN` secret
8. Click **Update**
9. Paste the new token
10. Click **Update secret**
11. Verify: Next CI run should succeed with the new token

**Note:** Old token is immediately invalidated; you have a brief window to update GitHub before CI starts failing.

### Task: View Analysis Results

**Scenario:** You want to see what SonarCloud found in the `velocityai` project.

**Steps:**
1. Go to https://sonarcloud.io/dashboard?id=velocityai
2. Explore:
   - **Overview:** Summary of coverage, issues, ratings
   - **Issues:** Search/filter by type (bug, vulnerability, code smell), severity, language
   - **Coverage:** View coverage by file; identify under-tested areas
   - **Hotspots:** Security-sensitive code requiring review
   - **Code Duplications:** See which files have duplicate code

**Pro tip:** Use filters to focus on recent changes. In **Issues**, filter by **Created in last 7 days** to see what new problems were introduced.

### Task: Troubleshoot PR Check Failure

**Scenario:** A PR shows a failed SonarCloud check, but you want to understand why.

**Steps:**
1. On the GitHub PR, scroll down to **Checks**
2. Find **SonarCloud Quality Gate** check
3. Click **Details** to see the check output
4. The output shows:
   - Which thresholds failed (e.g., "Coverage 75% < 85%")
   - Specific violations (e.g., list of new issues)
5. For more detail, click the **SonarCloud** link in the check output
6. This takes you to the PR-specific analysis in SonarCloud

**If analysis isn't visible:**
- Check GitHub Actions logs (**Actions** tab → workflow run → **sonarcloud-analysis** job)
- Look for errors like:
  - `SONAR_TOKEN not found` → Check GitHub Organization Secret is set
  - `Coverage files not found` → Check frontend/backend coverage artifacts exist
  - `Analysis failed` → Check SonarCloud project key matches workflow configuration

---

## Troubleshooting

### Problem: "SONAR_TOKEN not found" in CI logs

**Cause:** GitHub Organization Secret is not set or not accessible.

**Solution:**
1. Verify secret exists: GitHub Org Settings → **Secrets and variables** → **Actions** → Search for `SONAR_TOKEN`
2. Verify access: If secret is restricted to specific repos, ensure this repo is included
3. If using a new org, allow time (a few minutes) for secret to propagate

### Problem: SonarCloud doesn't receive analysis

**Cause:** SonarScanner job failed or coverage files weren't found.

**Solution:**
1. Check SonarScanner logs in GitHub Actions: **Actions** → workflow → **sonarcloud-analysis** job
2. Look for error messages indicating:
   - Coverage XML files not found (verify paths in `sonarcloud-analysis` job)
   - Network error (rare; check SonarCloud status page)
3. Verify coverage artifacts exist: **Actions** → workflow → **prepare-sonarcloud** job → check artifact listing

### Problem: Quality Gate always fails despite high coverage

**Cause:** SonarCloud may not be parsing coverage reports correctly.

**Solution:**
1. Verify coverage files are valid XML:
   - Download from artifact in **prepare-sonarcloud** job
   - Open in text editor; should start with `<?xml`
2. Check SonarCloud analysis logs: In **SonarCloud dashboard** → **Issues** → look for parser warnings
3. If XML format is incorrect, check frontend vitest config exports XML in Cobertura format

### Problem: Frontend coverage not included in overall project coverage

**Cause:** Frontend coverage.xml path is incorrect or not referenced in SonarScanner parameters.

**Solution:**
1. Verify frontend coverage.xml exists in **prepare-sonarcloud** artifact download
2. Check `sonarcloud-analysis` job in `.github/workflows/ci.yml`
3. Verify the `-Dsonar.coverageReportPaths=...` parameter includes both:
   - `sonarcloud-coverage/coverage-backend.xml`
   - `sonarcloud-coverage/coverage-frontend.xml`
4. If path is wrong, update the workflow and re-run

### Problem: PR check is advisory (yellow) instead of failing (red)

**Cause:** Quality Gate is not associated with the project or is set to "advisory mode."

**Solution:**
1. In SonarCloud: **Project Settings** → **Quality Gates**
2. Verify the quality gate is marked as **Active** (associated with this project)
3. If not, click **Set as default for this project**
4. Verify quality gate rules are correctly configured (not just advisories)

---

## Next Steps & Future Improvements

1. **IDE Integration:** Install [SonarQube for IDE](https://docs.sonarsource.com/sonarqube-for-ide/) extension in your editor for real-time feedback
2. **Tighter Thresholds:** As coverage improves, gradually increase thresholds (e.g., 85% → 90%)
3. **Language-Specific Profiles:** Create separate quality profiles for Python and TypeScript
4. **Custom Rules:** Add organization-specific coding standards as custom SonarQube rules
5. **Notifications:** Set up Slack/Teams integration for quality gate failures
6. **Metrics Dashboard:** Create custom dashboards in SonarCloud to track metrics over time

---

## References

- [SonarCloud Documentation](https://docs.sonarcloud.io/)
- [SonarCloud GitHub Integration](https://docs.sonarcloud.io/github-integration/)
- [SonarScanner CLI](https://docs.sonarcloud.io/advanced-setup/ci-based-analysis/)
- [Quality Gates & Profiles](https://docs.sonarcloud.io/quality-profiles-and-gates/)

---

**Last Updated:** August 27, 2026  
**Maintainer:** DevOps / Platform Team  
**Review Cycle:** Annually or when thresholds change
