# SonarCloud Integration — Quick Start

> ⚠️ **Parts of this file are out of date.** The `prepare-sonarcloud` job it
> describes has been removed, and the frontend Cobertura-XML step it describes
> never worked (coverage reached SonarCloud as 0% while every job reported
> success). See the **Correction notice** in [README.md](./README.md) for the
> current coverage flow before following any step here.

**Status:** ⚠️ Coverage plumbing repaired; SonarCloud UI configuration still manual

This directory contains complete documentation and implementation for SonarCloud integration into your CI/CD pipeline.

---

## What's New?

Your GitHub Actions CI workflow now includes SonarCloud code quality analysis. Here's what happens on every PR:

1. **Tests run** (backend pytest + frontend vitest)
2. **Coverage reports merge** (backend + frontend → single report)
3. **SonarScanner analyzes** code + coverage
4. **SonarCloud evaluates** quality gate thresholds
5. **PR check appears** — green ✓ if passed, red ✗ if failed
6. **Merge is blocked** if quality gate fails

---

## Files in This Directory

| File | Purpose |
|------|---------|
| **SONARCLOUD_INTEGRATION.md** | 📖 **Start here** — Comprehensive guide with setup instructions, runbook, troubleshooting |
| **SONARCLOUD_IMPLEMENTATION_CHECKLIST.md** | ✅ **Step-by-step checklist** — Phases 1-10 to complete integration |
| **SONARCLOUD_CHANGES_SUMMARY.md** | 📝 Technical summary of all code changes |
| **SONARCLOUD_README.md** | 👋 This file — Quick reference |

**Also see:**
- `sonar-project.properties` — SonarCloud configuration reference (project root)
- `scripts/setup-sonarscanner-checksum.sh` — Helper to fetch/verify SonarScanner checksum

---

## What You Need To Do (Manual Steps)

### 1. Create SonarCloud Account & Project
- Go to https://sonarcloud.io
- Sign up with GitHub
- Import the `velocityai` repository
- Generate a `SONAR_TOKEN`

**Time:** ~10 minutes

**Details:** See `SONARCLOUD_INTEGRATION.md` → "Setup Instructions"

### 2. Store Token in GitHub Secrets
- GitHub Org Settings → Secrets and variables → Actions
- Create secret: `SONAR_TOKEN = [your-token]`

**Time:** ~2 minutes

**Details:** See `SONARCLOUD_INTEGRATION.md` → "GitHub Organization Secret"

### 3. Configure Quality Gate (Optional)
- SonarCloud UI → Project Settings → Quality Gates
- Create gate with thresholds: Coverage ≥85%, Blockers = 0, Code Smells ≤30, etc.

**Time:** ~10 minutes

**Default:** If skipped, SonarCloud uses "Sonar Way" gate (also reasonable)

**Details:** See `SONARCLOUD_INTEGRATION.md` → "Quality Gate Thresholds"

### 4. Test on a PR
- Open a test PR
- Wait for CI to complete (including `sonarcloud-analysis` job)
- Verify SonarCloud check appears
- Review analysis in https://sonarcloud.io/dashboard?id=velocityai

**Time:** ~5 minutes + CI runtime

---

## What Was Already Done (Code Changes)

### ✅ CI Workflow Updated (`.github/workflows/ci.yml`)
- ✅ Frontend job exports coverage as **LCOV** (`coverage/lcov.info`) — the native
  JS/TS coverage format for Sonar. (Originally Cobertura XML; that never worked.)
- ✅ `test-results` publishes `backend/coverage.xml` as the `backend-coverage-xml`
  artifact after `coverage combine` merges all four pytest shards
- ✅ Both reports are rewritten to repo-root-relative paths before upload
- ✅ `sonarcloud-analysis` downloads both directly, hard-fails if either is
  missing/empty, and runs the scanner with `-Dsonar.qualitygate.wait=true`
- ❌ There is **no** `prepare-sonarcloud` consolidation job — it was removed

### ✅ Configuration Files Created
- ✅ `sonar-project.properties` — SonarCloud configuration reference, using the
  language-specific `sonar.python.coverage.reportPaths` and
  `sonar.javascript.lcov.reportPaths` properties
- ✅ Frontend vitest config emits LCOV, with coverage thresholds set as ratchet
  floors at the measured baseline (46/44/45/48) rather than an unreachable 80
- ✅ Helper script for SonarScanner checksum verification

### ✅ Documentation Created
- ✅ Comprehensive integration guide
- ✅ Step-by-step implementation checklist
- ✅ Technical change summary
- ✅ This quick-start guide

---

## Quick Links

| Need | Link |
|------|------|
| Full setup guide | `docs/SONARCLOUD_INTEGRATION.md` |
| Step-by-step checklist | `docs/SONARCLOUD_IMPLEMENTATION_CHECKLIST.md` |
| Technical details | `docs/SONARCLOUD_CHANGES_SUMMARY.md` |
| Configuration reference | `sonar-project.properties` |
| SonarCloud dashboard | https://sonarcloud.io/dashboard?id=velocityai (after setup) |

---

## FAQ

**Q: Do I need to install anything locally?**  
A: No. The integration runs entirely in CI. Optionally, install [SonarQube for IDE](https://docs.sonarsource.com/sonarqube-for-ide/) in your editor for real-time feedback.

**Q: What if a PR fails the quality gate?**  
A: The PR check will show red ✗. Click "Details" to see which thresholds failed (e.g., "Coverage < 85%"). Either improve the code/tests or request exception. Merge is blocked until pass.

**Q: Can I adjust quality gate thresholds later?**  
A: Yes! SonarCloud UI → Project Settings → Quality Gates → Edit. Changes take effect on next PR.

**Q: How do I view analysis results?**  
A: Dashboard: https://sonarcloud.io/dashboard?id=velocityai (after initial analysis)  
PR Comment: SonarCloud posts a comment on each PR with summary  
GitHub Check: Shows pass/fail status in PR checks section

**Q: What's the overhead on CI time?**  
A: ~2-3 minutes per PR (SonarScanner analysis). Runs in parallel with other jobs, so total CI time increases minimally.

---

## Support

### If Setup Fails
1. Check `SONARCLOUD_INTEGRATION.md` → "Troubleshooting" section
2. Review CI logs: GitHub Actions → workflow → `sonarcloud-analysis` job
3. Common issues:
   - SONAR_TOKEN not found → Verify GitHub Organization Secret
   - Coverage files missing → Read the "Verify coverage reports are present and
     non-empty" step in `sonarcloud-analysis`; artifacts are
     `backend-coverage-xml` and `frontend-coverage-lcov`
   - Analysis doesn't appear → Wait 1-2 minutes for SonarCloud to process

### If PR Check Never Appears
1. Verify `sonarcloud-analysis` job completed successfully
2. Verify SONAR_TOKEN is set in GitHub Organization Secrets
3. Check CI logs for errors (SONAR_TOKEN, network, etc.)

### Team Questions
- Direct to `SONARCLOUD_INTEGRATION.md` for operational procedures
- Direct to `SONARCLOUD_CHANGES_SUMMARY.md` for technical details

---

## Implementation Checklist (High Level)

- [ ] **Phase 1-2:** Create SonarCloud account, project, generate token (~10 min)
- [ ] **Phase 3:** Store SONAR_TOKEN in GitHub Org Secret (~2 min)
- [ ] **Phase 4:** Verify frontend coverage XML exports (~5 min)
- [ ] **Phase 5:** Test coverage consolidation (automatic, verify in CI)
- [ ] **Phase 6:** Test SonarScanner integration (automatic, verify in CI)
- [ ] **Phase 7:** Configure quality gate (optional, ~10 min)
- [ ] **Phase 8:** Test PR quality gate (open test PR, verify ~5 min)

**Total Time:** ~30-40 minutes

**Full Checklist:** See `SONARCLOUD_IMPLEMENTATION_CHECKLIST.md`

---

## Architecture

```
Developer Push
       ↓
GitHub Actions Triggers
       ├─ pytest shards (backend)
       ├─ vitest (frontend) → coverage/lcov.info
       └─ (other jobs in parallel)
       ↓
test-results job
├─ coverage combine (4 shards) → report --fail-under=80 → coverage xml
└─ normalise <source> roots → artifact: backend-coverage-xml
       ↓                       frontend job
       │                       └─ normalise SF: paths
       │                          → artifact: frontend-coverage-lcov
       └───────────┬───────────────────────┘
                   ↓
sonarcloud-analysis job    needs: [test-results, frontend]
├─ Download both reports to the paths sonar-project.properties names
├─ HARD-FAIL if either is missing or empty
├─ Install SonarScanner (checksum-verified)
└─ Run analysis with -Dsonar.qualitygate.wait=true
       ↓
SonarCloud Processes
├─ Evaluate quality gate (conditions on NEW code)
└─ Post its own PR check + comment
       ↓
PR Check (Pass ✓ or Fail ✗)
   ⚠ blocks the merge only if the SonarCloud quality gate is listed as a
     REQUIRED status check in the repository ruleset — sonarcloud-analysis is
     deliberately not part of ci-required
```

---

## Configuration Parameters

**Project Identity (set in SonarCloud UI):**
- Organization Key: `velocityai`
- Project Key: `velocityai`
- Project Name: `VelocityAI`

**Quality Gate Thresholds — conditions on NEW code (set in SonarCloud UI):**
- Coverage on New Code: ≥ 80%
- Duplicated Lines on New Code: ≤ 3%
- New Blocker / Critical Issues: = 0
- Maintainability / Reliability / Security Rating on New Code: A

> Do **not** set an "overall coverage ≥ 85%" condition. Measured coverage is ~80%
> backend and ~46% frontend, so an overall gate fails every PR regardless of what
> it changed. Overall regression is prevented separately: ratchet floors in
> `frontend/vitest.config.ts` and `coverage report --fail-under=80` on merged
> backend coverage.

**SonarScanner Parameters (in CI workflow):**
- See `sonarcloud-analysis` job in `.github/workflows/ci.yml`
- Customizable via `-Dsonar.*` flags

---

## Next Steps

### Immediate (This Week)
1. Follow `SONARCLOUD_INTEGRATION.md` Phases 1-3 (account + secret setup)
2. Open test PR to verify integration works
3. Review first analysis in SonarCloud dashboard

### Short Term (This Month)
1. Configure quality gate (Phase 7 in checklist)
2. Team walkthrough of SonarCloud dashboard and results
3. Establish policy on quality gate failures (fix code vs. adjust thresholds)

### Long Term (Ongoing)
1. Monitor quality metrics dashboard
2. Rotate SONAR_TOKEN annually
3. Adjust quality gate thresholds as codebase improves
4. Integrate SonarQube for IDE (optional team enhancement)

---

## Files Modified/Created

### Modified
- ✏️ `.github/workflows/ci.yml` — Added SonarCloud jobs + frontend XML export
- ✏️ `frontend/vitest.config.ts` — Enhanced coverage reporters

### Created
- 📄 `docs/SONARCLOUD_INTEGRATION.md` — Comprehensive guide
- 📄 `docs/SONARCLOUD_IMPLEMENTATION_CHECKLIST.md` — Step-by-step checklist
- 📄 `docs/SONARCLOUD_CHANGES_SUMMARY.md` — Technical details
- 📄 `docs/SONARCLOUD_README.md` — This file
- 📄 `sonar-project.properties` — Configuration reference
- 📄 `scripts/setup-sonarscanner-checksum.sh` — Helper script

---

## Security & Privacy

✅ **SONAR_TOKEN is secure:**
- Stored as GitHub Organization Secret (encrypted by GitHub)
- Never logged or exposed in CI output
- Should be rotated annually

✅ **Code analysis is private:**
- SonarCloud project is private (matches repo privacy)
- Only organization members can view analysis

✅ **No data leaves your org:**
- Analysis stays within SonarCloud (SaaS)
- No personal data collected
- Compliant with standard privacy practices

---

## Support & Resources

- **SonarCloud Docs:** https://docs.sonarcloud.io/
- **SonarCloud GitHub Integration:** https://docs.sonarcloud.io/github-integration/
- **This Project's Guides:**
  - Setup: `SONARCLOUD_INTEGRATION.md`
  - Implementation: `SONARCLOUD_IMPLEMENTATION_CHECKLIST.md`
  - Technical: `SONARCLOUD_CHANGES_SUMMARY.md`

---

**Ready to integrate?** Start with Phase 1 in `SONARCLOUD_IMPLEMENTATION_CHECKLIST.md` or dive deep into `SONARCLOUD_INTEGRATION.md`.

**Questions?** Check the FAQ section above or search for your issue in the Troubleshooting guides.

---

**Last Updated:** August 27, 2026  
**Maintainer:** DevOps / Platform Team  
**Status:** ✅ Code Implementation Complete | ⏳ Awaiting Manual SonarCloud Setup
