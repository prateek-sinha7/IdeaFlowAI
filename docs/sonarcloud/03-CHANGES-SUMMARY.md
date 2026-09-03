# SonarCloud Integration — Changes Summary

> ## ⚠️ HISTORICAL RECORD — describes the ORIGINAL integration, which did not work
>
> This document describes the SonarCloud integration **as first written**. That
> version delivered **zero coverage to SonarCloud while reporting success on every
> job**, so several of the changes described below have since been removed or
> replaced. It is kept because the rationale is useful context, not because it
> describes the current pipeline.
>
> For the current design, read [README.md](./README.md) (correction notice) and
> [02-INTEGRATION-GUIDE.md](./02-INTEGRATION-GUIDE.md) (corrected flow diagram).
> `.github/workflows/ci.yml` and `sonar-project.properties` are authoritative.
>
> What has changed since, in brief:
>
> | Described below | Current reality |
> |---|---|
> | Frontend exports Cobertura XML via vitest's `"xml"` reporter | `"xml"` is not a valid coverage reporter — it crashed `npm run test` *after* all tests passed. Frontend emits **LCOV** (`coverage/lcov.info`). |
> | New `prepare-sonarcloud` job consolidates coverage | **Job deleted.** Both of its file lookups always failed and it exited 0 anyway. Each report is now downloaded straight to the path the properties file names. |
> | `sonar.coverageReportPaths` names both reports | Wrong property (Generic Test Data schema only). Now `sonar.python.coverage.reportPaths` + `sonar.javascript.lcov.reportPaths`. |
> | `sonar.sources=.` | Narrowed to `backend/app`, `backend/agents`, `frontend/src`, with `sonar.tests` declared. |
> | Quality gate: ≥85% overall coverage | Unreachable. Now ≥80% on **new code** (Clean as You Code) + ratchet floors in `vitest.config.ts`. |
> | `sonarcloud-analysis` needs `prepare-sonarcloud` | `needs: [test-results, frontend]`, and passes `-Dsonar.qualitygate.wait=true`. |

## Overview

The SonarCloud integration adds code quality and security analysis to your GitHub Actions workflow. Here's what changed:

```
Before:  Tests → Coverage → Security Scan → (No quality gates on PRs)
After:   Tests → Coverage → SonarCloud Analysis → Quality Gate Check → PR Decision
```

---

## Files Modified

### 1. `.github/workflows/ci.yml` (CI Workflow)

#### Change 1a: Frontend Coverage XML Export
**Location:** Frontend job, coverage upload section

**What changed (ORIGINAL — since replaced):**
- Added a step **"Upload frontend coverage XML (for SonarCloud)"** uploading
  `coverage/coverage-final.xml` as the `frontend-coverage-xml` artifact.

**Why it was wrong:** vitest never wrote that file. The `"xml"` entry added to
the reporter list is not a valid `@vitest/coverage-v8` reporter; it resolved to
istanbul's `xml` reporter, which failed to load its own `xml` module and made
`npm run test` exit **1 after all 1,111 tests had already passed**. The artifact
upload therefore had no source file.

**Current:** the step is **"Upload frontend coverage LCOV (for SonarCloud)"**,
uploading `coverage/lcov.info` as `frontend-coverage-lcov` with
`if-no-files-found: error`. Sonar consumes LCOV natively for JS/TS, so no XML was
ever needed. A preceding step rewrites `SF:` paths to be repo-root-relative.

#### Change 1b: New Job — `prepare-sonarcloud`  ❌ REMOVED
**Location (original):** After `test-results` and `frontend` jobs

**What it did:** downloaded the backend and frontend coverage artifacts, copied
them into a `sonarcloud-coverage/` directory, and uploaded that as one artifact.

**Why it was removed:** it could not work, and it hid its own failure. It
downloaded `backend-coverage-report` (which contains only `htmlcov/`, never
`coverage.xml`) and looked for `coverage-final.xml` in the frontend artifact
(never produced — see 1a). Both `if [ -f ... ]` guards always took the `else`
branch, printed `⚠ WARNING` to stderr, and the job **still exited 0**. So
SonarCloud received no coverage at all while every job reported green.

**Current:** no consolidation job exists. `test-results` uploads
`backend-coverage-xml` (`backend/coverage.xml`) and `frontend` uploads
`frontend-coverage-lcov`; `sonarcloud-analysis` downloads each directly to the
path `sonar-project.properties` already names, and **hard-fails** if either
report is missing or empty.

#### Change 1c: New Job — `sonarcloud-analysis`
**Location:** After the `test-results` and `frontend` jobs

**What does it do:**
1. Downloads the two coverage artifacts to their expected paths
2. Fails immediately if either report is missing or empty
3. Installs SonarScanner CLI (checksum-verified binary)
4. Runs SonarScanner with `-Dsonar.qualitygate.wait=true`, so the step's status
   reflects the **gate verdict**, not merely a successful upload
5. SonarCloud posts its own PR check and comment

**Why:**
- This is the core integration: connects your code to SonarCloud
- Quality gates are evaluated here
- PR checks are posted automatically

**Configuration (see Job Parameters below)**

**Dependencies:** `needs: [test-results, frontend]`

> This job is deliberately **not** part of `ci-required` (SonarCloud is an
> external service). The **SonarCloud quality gate must therefore be its own
> required status check** in the repository ruleset, alongside `ci-required`, or a
> failing gate will not block a merge.

---

### 2. `frontend/vitest.config.ts` (Frontend Test Configuration)

**What changed (ORIGINAL — since corrected):** the `coverage.reporter` array was
given an `"xml"` entry, described as "Cobertura format for SonarCloud":

```typescript
reporter: ["text", "text-summary", "html", "json", "json-summary", "xml", "lcov"],
```

**Why it was wrong:** `"xml"` is not a valid `@vitest/coverage-v8` reporter. The
list is passed through to istanbul-reports, whose `xml` reporter fails to load
its own `xml` module under this toolchain. The failure mode was nasty precisely
because it is not a test failure — all 133 files / 1,111 tests passed, the console
printed a full green summary, and *then* `npm run test` exited 1 while writing
reports. No `coverage-final.xml` was ever produced. (`"cobertura"` is the correct
name if XML is ever genuinely needed.)

**Current:**
```typescript
reporter: ["text", "text-summary", "html", "json", "json-summary", "lcov"],
```

- `npm run test` exits 0 and writes `coverage/lcov.info`
- Sonar reads that via `sonar.javascript.lcov.reportPaths` — LCOV is the native
  JS/TS coverage format for Sonar, so the XML was never required

**Also changed — thresholds.** They were `80` across the board, which never fired
because the broken reporter crashed the run first. Measured coverage is
statements 46.4% / branches 44.2% / functions 45.5% / lines 48.3%, so the
thresholds are now ratchet **floors** at that baseline (46/44/45/48). The 80%
standard moved to SonarCloud's new-code condition, which holds new work to the
real bar without failing every PR on pre-existing legacy code.

---

### 3. `sonar-project.properties` (New File)

**What is it:**
- SonarQube project configuration file
- Defines source paths, exclusions, coverage paths, language settings
- Serves as documentation for your SonarCloud setup

**Contains:**
- Project identity (org key, project key, name)
- Source/exclusion patterns
- Coverage report paths (backend + frontend)
- Language-specific settings (Python 3.12, JavaScript/TypeScript)
- Quality gate reference documentation

**Usage:**
- Can be used locally: `sonar-scanner -Dproject.settings=sonar-project.properties`
- Primarily used as reference; CI workflow sets parameters via command-line flags

---

### 4. `docs/SONARCLOUD_INTEGRATION.md` (New File — Comprehensive Guide)

**What is it:**
- Complete guide to SonarCloud integration
- Setup instructions (for initial manual configuration)
- Runbook for common tasks (rotate token, adjust thresholds, view results)
- Troubleshooting guide

**Sections:**
1. **Overview** — Why SonarCloud, key components
2. **Setup Instructions (Task 1)** — Create account, import repo, generate token
3. **GitHub Organization Secret (Task 2)** — Store SONAR_TOKEN securely
4. **Quality Gate Thresholds (Task 6)** — Moderate baseline metrics
5. **CI Integration Flow** — Step-by-step diagram
6. **Common Tasks (Runbook)** — Adjust thresholds, rotate token, view results, troubleshoot
7. **References** — Links to SonarCloud docs

**Read this when:** You need detailed explanations or operational procedures

---

### 5. `docs/SONARCLOUD_IMPLEMENTATION_CHECKLIST.md` (New File — Step-by-Step Checklist)

**What is it:**
- Phase-by-phase checklist for completing the integration
- Covers all 7 implementation tasks
- Verification steps for each phase

**Phases:**
1. SonarCloud Account & Project Setup (Task 1)
2. Generate SONAR_TOKEN (Task 1 continued)
3. Configure GitHub Organization Secret (Task 2)
4. Verify Frontend Coverage XML Export (Task 3)
5. Test Coverage Consolidation Job (Task 4)
6. Test SonarScanner Integration (Task 5)
7. Configure Quality Gate (Task 6)
8. Test PR Quality Gate (Task 5 + 6)
9. Verify CI Job Dependencies (Optional, Advanced)
10. Documentation & Runbook (Task 7)

**Plus troubleshooting section** for common issues

**Read this when:** You're implementing the integration step-by-step

---

### 6. `scripts/setup-sonarscanner-checksum.sh` (New File — Helper Script)

**What is it:**
- Bash script to download and verify SonarScanner binary checksum
- Generates the SHA256 checksum for use in CI

**How to use:**
```bash
# Download and verify latest version
./scripts/setup-sonarscanner-checksum.sh 8.0.1.6346

# Output shows version and checksum, ready to update CI workflow
SONAR_VERSION="8.0.1.6346"
SONAR_CHECKSUM="<computed-hash>"
```

**Why:**
- SonarScanner CI job installs binary directly (not via GitHub Action)
- Checksum verification ensures we get the exact version we expect
- This script saves time and prevents manual copy-paste errors

---

## Job Flow in CI Workflow

```
┌─────────────────────────────────────────────────────────────┐
│ GitHub Actions Triggered (push or PR)                       │
└────────────────┬────────────────────────────────────────────┘
                 │
    ┌────────────┴────────────┬──────────────┐
    │                         │              │
    ▼                         ▼              ▼
┌─────────────┐        ┌─────────────┐  ┌──────────────┐
│ pytest jobs │        │   vitest    │  │security-scan │
│ (sharded)   │        │  (frontend) │  │  (parallel)  │
└──────┬──────┘        └──────┬──────┘  └──────────────┘
       │                      │
       └──────────┬───────────┘
                  │
                  ▼
          ┌───────────────────────────┐
          │  test-results             │
          │  combine → report 80%     │
          │  → xml → normalise paths  │
          │  artifact:                │
          │    backend-coverage-xml   │
          └─────────┬─────────────────┘
                    │        ┌────────────────────────────┐
                    │        │ frontend                   │
                    │        │ vitest → lcov.info         │
                    │        │ → normalise SF: paths      │
                    │        │ artifact:                  │
                    │        │   frontend-coverage-lcov   │
                    │        └───────────┬────────────────┘
                    │                    │
                    └────────┬───────────┘
                             ▼
                 ┌──────────────────────────┐
                 │ sonarcloud-analysis      │
                 │ needs: [test-results,    │
                 │         frontend]        │
                 │ verify reports non-empty │
                 │ scanner + qualitygate.wait│
                 └────────┬─────────────────┘
         │
         ▼
    ┌─────────────┐
    │ SonarCloud  │
    │ Posts PR    │
    │ Check       │
    └─────────────┘
         │
    ┌────┴────┐
    │          │
    ▼          ▼
 PASS ✓      FAIL ✗
```

---

## Environment Variables & Secrets

### SONAR_TOKEN (GitHub Organization Secret)

**What it is:**
- SonarCloud project analysis token
- Grants CI the ability to publish analysis results to SonarCloud

**Where to set:**
- GitHub Org Settings → Secrets and variables → Actions
- Name: `SONAR_TOKEN`
- Value: Token from SonarCloud (Task 1, Step 3)

**Who needs it:**
- `sonarcloud-analysis` job (via `secrets.SONAR_TOKEN` in workflow)

**Security:**
- Never commit this token to git
- Rotate annually (see `SONARCLOUD_INTEGRATION.md` runbook)

---

## Backward Compatibility

✅ **All changes are additive** — no existing jobs were removed or substantially modified.

- **Test jobs** (pytest shards, vitest) — unchanged
- **Coverage artifacts** — additional XML artifacts added alongside existing JSON
- **Security scan job** — unchanged (runs in parallel)
- **No impact on existing CI logic** — new jobs depend on test jobs but don't block them

**Result:** Existing workflows continue to work; new SonarCloud analysis runs in parallel.

---

## Configuration Parameters (sonarcloud-analysis Job)

These parameters control SonarScanner behavior:

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `sonar.organization` | `velocityai` | SonarCloud organization key |
| `sonar.projectKey` | `velocityai` | SonarCloud project identifier |
| `sonar.projectName` | `VelocityAI` | Human-readable project name |
| `sonar.sources` | `backend/app,backend/agents,frontend/src` | Production source only. Was `.` (the whole repo), which analysed Terraform, shell, docs, `.planning/` and every test file as production code — inflating every coverage and duplication denominator. |
| `sonar.tests` / `sonar.test.inclusions` | `backend/tests`, `frontend/e2e`, `src/**/*.test.*` | Test code is *declared*, not excluded, so Sonar applies test-aware rules and attributes coverage correctly. |
| `sonar.exclusions` | `node_modules/**,__pycache__/**,...` | Exclude vendor/generated code |
| `sonar.coverage.exclusions` | `**/tests/**,**/*_test.py,...` | Exclude test files from coverage |
| `sonar.python.coverage.reportPaths` | `backend/coverage.xml` | Cobertura from `coverage xml`. Replaces the original `sonar.coverageReportPaths`, which accepts **only** Sonar's Generic Test Data schema and so parsed neither report. |
| `sonar.javascript.lcov.reportPaths` | `frontend/coverage/lcov.info` | LCOV from vitest's v8 provider — the native JS/TS coverage format for Sonar. |
| `SONAR_TOKEN` (env) | `${{ secrets.SONAR_TOKEN }}` | Authentication token |
| `SONAR_HOST_URL` (env) | `https://sonarcloud.io` | SonarCloud endpoint |

**Customize by:** Editing the `Run SonarScanner analysis` step in `.github/workflows/ci.yml`

---

## Quality Gate Thresholds (Moderate Baseline)

Set in SonarCloud UI (`Project Settings → Quality Gates`):

| Metric | Threshold | Rationale |
|--------|-----------|-----------|
| Coverage on **New Code** | ≥ 80% | Clean as You Code. Replaces the original "≥85% **overall**", which was unreachable — backend measures ~80% and frontend ~46%, so an overall gate fails every PR regardless of what it changed. Overall regression is instead prevented by ratchet floors in `frontend/vitest.config.ts` and `coverage report --fail-under=80` on merged backend coverage. |
| Blocker Issues | = 0 | No critical security/correctness issues |
| Critical Issues | ≤ 5 | Some non-critical issues allowed; reviewable before merge |
| Code Smells | ≤ 30 | Maintainability gate; prevents pure code rot |
| Duplications | ≤ 3% | Encourages code reuse; prevents copy-paste |
| Maintainability Rating | A | Excellent code health (SonarQube A/B/C/D/E scale) |
| Security Rating | A | Excellent security posture |

**Adjustment:** See `SONARCLOUD_INTEGRATION.md` → "Common Tasks" → "Adjust Quality Gate Thresholds"

---

## Testing the Integration

### Local Testing (Before Committing)

1. **Verify frontend coverage XML generates:**
   ```bash
   cd frontend
   npm ci
   npm run test
   ls -la coverage/lcov.info  # Should exist (NOT coverage-final.xml)
   ```

2. **Review vitest config:**
   ```bash
   cat frontend/vitest.config.ts | grep -A 5 "reporter:"
   # Should include "xml" in reporters
   ```

### CI Testing (After Committing)

1. **Push to feature branch or open PR**
2. **Monitor GitHub Actions:**
   - `test-results` and `frontend` should complete and publish their coverage artifacts
   - `sonarcloud-analysis` job should show "SonarScanner analysis completed"
3. **Check PR for SonarCloud check:**
   - After ~1 minute, check for "SonarCloud Quality Gate" check
   - Should show Pass or Fail (both are working; Fail just means threshold not met)
4. **Verify SonarCloud dashboard:**
   - Go to https://sonarcloud.io/dashboard?id=velocityai
   - Should show coverage, issues, and metrics

---

## Troubleshooting Quick Links

| Issue | See Section |
|-------|-------------|
| SonarScanner download fails | `sonarcloud-analysis` job logs → "Install SonarScanner" step |
| SONAR_TOKEN not found | `docs/SONARCLOUD_INTEGRATION.md` → "Troubleshooting" → "SONAR_TOKEN not found" |
| Coverage files missing | `docs/SONARCLOUD_IMPLEMENTATION_CHECKLIST.md` → "Troubleshooting" → "Frontend coverage shows 0%" |
| Quality gate always fails | `SONARCLOUD_IMPLEMENTATION_CHECKLIST.md` → "Troubleshooting" → "Quality gate always shows PASS..." |
| PR check doesn't appear | `SONARCLOUD_INTEGRATION.md` → "Troubleshooting" → "SonarCloud doesn't receive analysis" |

---

## Next Steps

1. **Complete Setup (Manual):**
   - Follow `docs/SONARCLOUD_IMPLEMENTATION_CHECKLIST.md` phases 1-7
   - Takes ~30 minutes

2. **Test Integration:**
   - Open test PR
   - Verify SonarCloud check appears and works

3. **Team Onboarding:**
   - Share `docs/SONARCLOUD_INTEGRATION.md` with team
   - Walkthrough SonarCloud dashboard and results

4. **Monitor & Iterate:**
   - Review first few PRs and quality gate decisions
   - Adjust thresholds if needed

---

## FAQ

**Q: Will SonarCloud analysis block my PR?**  
A: Yes, if the quality gate fails. You'll see a red "SonarCloud Quality Gate: FAILED ✗" check. You can review why it failed (coverage too low, too many code smells, etc.) and adjust code or thresholds.

**Q: What happened to the `prepare-sonarcloud` job?**  
A: It was removed. It existed to copy two coverage files into one directory, and it could not work — it looked for `coverage.xml` inside an HTML-only artifact and for a `coverage-final.xml` vitest never wrote, warned on both, and exited 0. `sonarcloud-analysis` now downloads each report directly to the path `sonar-project.properties` names and hard-fails if either is missing or empty, which is both simpler and no longer able to fail silently.

**Q: Can I run SonarScanner locally?**  
A: Yes! Install SonarScanner, then run: `sonar-scanner -Dproject.settings=sonar-project.properties`. See `sonar-project.properties` for configuration.

**Q: How often should I rotate SONAR_TOKEN?**  
A: At least annually. See `SONARCLOUD_INTEGRATION.md` runbook for rotation steps.

**Q: Can I use SonarQube (self-hosted) instead of SonarCloud?**  
A: Yes, but changes are needed: update `SONAR_HOST_URL` and infrastructure setup. Current implementation assumes SonarCloud.

---

**Document Version:** 1.0  
**Last Updated:** August 27, 2026  
**Maintainer:** DevOps / Platform Team
