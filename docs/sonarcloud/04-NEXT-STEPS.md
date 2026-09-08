# SonarCloud Integration — What To Do Next

## 🎯 Your Next Steps (In Order)

### 1️⃣ **Today** — Read the Overview (5 minutes)
```
📖 Read: README.md (in this directory)
📍 Location: Project root (this directory)
⏱️ Time: 5 minutes
✅ Outcome: Understand what was done and why
```

### 2️⃣ **This Hour** — Start Manual Setup (30-40 minutes)
```
📋 Follow: 01-IMPLEMENTATION-CHECKLIST.md
📍 Phases: 1, 2, 3 (account, token, GitHub secret)
⏱️ Time: ~15 minutes
✅ Outcome: SonarCloud ready to receive analysis
```

### 3️⃣ **Today/Tomorrow** — Test Integration (5 minutes)
```
🧪 Test: Open a test PR
🔍 Check: Verify SonarCloud job runs in CI
📊 Verify: SonarCloud check appears on PR
⏱️ Time: 5 minutes (+ CI runtime ~15 min)
✅ Outcome: Integration confirmed working
```

### 4️⃣ **This Week** — Review & Educate (20 minutes)
```
📚 Read: 02-INTEGRATION-GUIDE.md
📍 Sections: "Viewing Analysis Results" & "Common Tasks"
👥 Share: With your team
⏱️ Time: 20 minutes
✅ Outcome: Team understands how to use SonarCloud
```

### 5️⃣ **Optional** — Configure Quality Gate (10 minutes)
```
⚙️ Setup: Custom quality gate thresholds
📍 Location: SonarCloud UI → Project Settings
📋 Reference: 01-IMPLEMENTATION-CHECKLIST.md → Phase 6-7
⏱️ Time: 10 minutes
✅ Outcome: Custom quality standards enforced
```

---

## 📄 Documentation Map

```
You are here → 04-NEXT-STEPS.md
         ↓
   [Choose your path]
   ├─ 🎓 "I want to understand what happened"
   │  └─→ README.md (in this directory)
   │
   ├─ 🚀 "I want to get started NOW"
   │  └─→ 00-START-HERE.md (quick start)
   │     └─→ 01-IMPLEMENTATION-CHECKLIST.md (step-by-step)
   │
   ├─ 📖 "I want comprehensive documentation"
   │  └─→ 02-INTEGRATION-GUIDE.md (everything)
   │
   ├─ 🔧 "I want technical details"
   │  └─→ 03-CHANGES-SUMMARY.md
   │
   └─ ⚙️ "I want configuration reference"
      └─→ sonar-project.properties
```

---

## 🚦 The Critical Path (Fastest Route)

### Phase 1: Setup (Do This First)

```bash
# 1. Go to SonarCloud
open https://sonarcloud.io

# 2. Sign up with GitHub
# (Skip if you already have account)

# 3. Create/import project
# - Organization: velocityai
# - Project: velocityai

# 4. Generate token
# My Account → Security → Generate Token
# Copy the token (won't be shown again!)
```

### Phase 2: Store Token (Do This Second)

```bash
# 1. Go to GitHub Organization Secrets
open https://github.com/organizations/{org}/settings/secrets/actions

# 2. Create secret
# Name: SONAR_TOKEN
# Value: [paste token from above]
# Access: All repositories

# 3. Click "Add secret"
```

### Phase 3: Verify (Do This Third)

```bash
# 1. Push a test PR
git checkout -b test/sonarcloud-integration
git commit --allow-empty -m "test: verify SonarCloud integration"
git push origin test/sonarcloud-integration

# 2. Open PR on GitHub
# (GitHub will show PR creation link in terminal)

# 3. Wait for CI (~15 min)
# - Watch for "sonarcloud-analysis" job to complete

# 4. Verify check appears
# - PR should show SonarCloud Quality Gate check
# - Click "Details" to see results

# 5. Review dashboard
open https://sonarcloud.io/dashboard?id=velocityai
```

**Total Time:** ~30 minutes

---

## ⏱️ Time Breakdown

| Phase | Task | Time | Who |
|-------|------|------|-----|
| 1 | Create SonarCloud account | 5 min | Anyone |
| 2 | Import repository | 3 min | Anyone |
| 3 | Generate SONAR_TOKEN | 2 min | Anyone |
| 4 | Store in GitHub Secrets | 2 min | Org Admin |
| 5 | Open test PR | 2 min | Anyone |
| 6 | Wait for CI | 15 min | (automatic) |
| 7 | Verify check appears | 5 min | Anyone |
| **Total** | | **~35 min** | |

---

## ❓ Common Questions

### Q: What if I don't have SonarCloud account yet?
**A:** Go to https://sonarcloud.io and sign up. Takes 2 minutes with GitHub OAuth.

### Q: What if the setup fails?
**A:** See `02-INTEGRATION-GUIDE.md` → "Troubleshooting" section. Most issues are:
- SONAR_TOKEN not set → Check GitHub Organization Secrets
- Coverage not found → Read the "Verify coverage reports are present and non-empty" step in `sonarcloud-analysis`; the artifacts are `backend-coverage-xml` (from `test-results`) and `frontend-coverage-lcov` (from `frontend`)
- Coverage shows 0% but the scanner passed → a path that does not resolve from the repo root is dropped **silently**; see 02-INTEGRATION-GUIDE.md
- Check doesn't appear → Wait 2+ minutes and refresh

### Q: Can I undo this?
**A:** Yes. Comment out the `sonarcloud-analysis` job in `.github/workflows/ci.yml` and remove the SonarCloud quality gate from the repository ruleset's required checks. (There is no `prepare-sonarcloud` job — it was removed.) Note that the coverage artifacts themselves are still worth keeping: `backend-coverage-xml` and `frontend-coverage-lcov` are produced by the test jobs regardless.

### Q: Do I need to do anything locally?
**A:** No. The integration runs entirely in CI. The only local change is vitest now exports XML coverage (automatic).

### Q: Will this slow down my CI?
**A:** Yes, by ~2-3 minutes. But it runs in parallel, so total CI time only increases minimally.

### Q: Can I skip the optional quality gate setup?
**A:** Yes. SonarCloud will use its default "Sonar Way" gate (reasonable defaults). You can add custom thresholds later if needed.

---

## ✅ Success Criteria

You'll know it's working when:

- [ ] SonarCloud project exists: https://sonarcloud.io/dashboard?id=velocityai
- [ ] Dashboard shows code metrics (coverage %, issues, etc.)
- [ ] Test PR shows "SonarCloud Quality Gate" check (green ✓ or red ✗)
- [ ] Merge button shows green (SonarCloud allows merge)
- [ ] Team has access to view results

---

## 🤝 Next: Share with Your Team

Once setup is complete, share these documents with your team:

1. **Managers/Leads:**
   - `README.md` (overview)
   - `00-START-HERE.md` (quick reference)

2. **Developers:**
   - `02-INTEGRATION-GUIDE.md` (full guide)
   - `01-IMPLEMENTATION-CHECKLIST.md` (runbook)

3. **DevOps/Platform:**
   - `03-CHANGES-SUMMARY.md` (technical)
   - `sonar-project.properties` (configuration)

---

## 🎯 Future Improvements

After initial setup, consider:

1. **IDE Integration** (~15 min)
   - Install [SonarQube for IDE](https://docs.sonarsource.com/sonarqube-for-ide/)
   - Get real-time feedback while coding

2. **Tighter Quality Gates** (~10 min)
   - Set conditions on **new code**, not overall — start at ≥80% coverage on new
     code. Do **not** set an ≥85% *overall* coverage condition: measured coverage
     is ~80% backend and ~46% frontend, so an overall gate fails every PR
     regardless of what it changed.
   - Overall regression is already prevented elsewhere: ratchet floors in
     `frontend/vitest.config.ts` and `coverage report --fail-under=80` on merged
     backend coverage.
   - Raise the frontend floors as legacy areas gain tests; add custom rules as needed

3. **Team Dashboard** (~20 min)
   - Create custom SonarCloud dashboard
   - Track metrics over time
   - Set quarterly improvement goals

4. **Slack Integration** (~10 min)
   - SonarCloud can post to Slack on quality gate failures
   - Increases team awareness

---

## 📞 Need Help?

### Issue: [Specific Problem]

**1. Check Troubleshooting:**
```
02-INTEGRATION-GUIDE.md → "Troubleshooting" section
```

**2. Check CI Logs:**
```
GitHub → Actions → [Failed Workflow] → sonarcloud-analysis job
Look for error messages
```

**3. Common Issues:**
- ❌ SONAR_TOKEN not found → GitHub Organization Secret not set
- ❌ Coverage files missing → Check the `backend-coverage-xml` / `frontend-coverage-lcov` artifacts
- ❌ Check doesn't appear → Wait 2+ min, check SonarCloud dashboard
- ❌ Quality gate always fails → Too strict? See Phase 6 in checklist

**4. Advanced Issues:**
- See `03-CHANGES-SUMMARY.md` for job parameters
- See `sonar-project.properties` for configuration options

---

## 🎉 You're Ready!

Everything is set up. You now have:

✅ **Code Changes:** CI workflow with SonarCloud integration  
✅ **Documentation:** Comprehensive guides and checklists  
✅ **Helper Scripts:** Automation for common tasks  
✅ **Reference Files:** Configuration and examples  

**All that's left is 30 minutes of manual setup to complete the integration.**

---

## 👉 Ready to Start?

### Option A: Read Everything First (25 min)
1. Read `README.md`
2. Read `00-START-HERE.md`
3. Read `02-INTEGRATION-GUIDE.md`

### Option B: Jump Right In (30 min + test)
1. Follow the **Critical Path** above
2. Create SonarCloud account + project
3. Store SONAR_TOKEN in GitHub
4. Open test PR to verify

### Option C: Step-by-Step (40 min)
1. Follow `01-IMPLEMENTATION-CHECKLIST.md`
2. Complete all 10 phases (most are automatic verification)

---

**Pick your path and get started!**

---

**Last Updated:** August 27, 2026  
**Maintainer:** DevOps / Platform Team  
**Status:** ✅ Ready to Deploy
