# Coverage Quick Start — 5 Minutes

Get test coverage reports running right now.

## What Was Added

✅ **Backend:** pytest-cov collects coverage for `app/` and `agents/`  
✅ **Frontend:** Vitest + @vitest/coverage-v8 collects coverage for `src/`  
✅ **CI/CD:** Coverage uploaded to Codecov after every PR  
✅ **Reports:** HTML + JSON reports uploaded as CI artifacts  

---

## Run Coverage Locally (Right Now)

### Backend

```bash
cd backend
uv venv --python 3.12
uv pip install -r requirements.txt -r requirements-dev.txt
uv run pytest tests/ \
  --cov=app \
  --cov=agents \
  --cov-report=html \
  --cov-report=term-missing
```

**Open the report:**
```bash
# macOS
open htmlcov/index.html
# Linux
xdg-open htmlcov/index.html
# Windows PowerShell
start htmlcov/index.html
```

### Frontend

```bash
cd frontend
npm ci
npm run test
```

**Open the report:**
```bash
# macOS
open coverage/index.html
# Linux
xdg-open coverage/index.html
# Windows PowerShell
start coverage/index.html
```

---

## View CI Coverage Reports

After pushing a PR or commit:

1. **Go to GitHub Actions** → Your workflow run
2. **Scroll to "Artifacts"** section
3. **Download:**
   - `backend-coverage-report` — Backend HTML + JSON
   - `frontend-coverage-report` — Frontend HTML + LCOV
4. **Extract and open** `index.html` in a browser

### Alternative: Codecov Dashboard

1. **Go to** `https://codecov.io/gh/your-org/velocityai`
2. **View coverage trends** over time
3. **Compare PR vs main** branch
4. **See which files** regressed

---

## Understanding the Report

### Color Legend

| Color | Meaning |
|-------|---------|
| 🟢 Green | Code is tested (covered) |
| 🔴 Red | Code is NOT tested (gap) |
| 🟡 Yellow | Only some branches tested (partial) |

### Example: API Endpoint with 0% Coverage

```python
# app/api/analytics.py (shown in RED because 0% covered)
@router.get("/api/analytics/summary")
async def get_summary(owner_id: str):
    return { "tokens": 1000 }
```

**This means:** No test calls `GET /api/analytics/summary`

**To fix:** Add a test

```python
# backend/tests/integration/test_analytics.py
def test_analytics_summary():
    response = client.get("/api/analytics/summary?owner_id=123")
    assert response.status_code == 200
    assert response.json()["tokens"] > 0
```

---

## CI Artifact Access

### After Each PR Run

1. Go to your PR → **"Checks"** tab
2. Click **"CI"** workflow
3. Scroll down → **"Artifacts"** section
4. Download the report (valid for 30 days)

### Command Line (GitHub CLI)

```bash
# Download backend coverage report from latest run
gh run download --name backend-coverage-report

# Extract and open
unzip -q backend-coverage-report.zip
open index.html
```

---

## Codecov Integration (Optional)

Coverage is automatically uploaded to Codecov, which shows:

- **PR comments** with coverage changes
- **Codecov badge** for your README
- **Trend charts** over time
- **File-level comparisons**

Example Codecov badge:
```markdown
[![codecov](https://codecov.io/gh/your-org/velocityai/branch/main/graph/badge.svg)](https://codecov.io/gh/your-org/velocityai)
```

---

## What if Other Devs Don't Add Tests?

Currently: **No enforcement** — tests are optional, coverage is optional.

When ready to enforce:

### Option 1: Soft (Recommended Now)
- Coverage is visible in CI comments
- Developers see the impact
- No blocking, just awareness

### Option 2: Medium (In 2–4 weeks)
- Fail CI if coverage drops below previous
- Requires explanation if regressing

### Option 3: Hard (In 4–8 weeks)
- Require minimum coverage % (e.g., 50% overall)
- Require new code to be 70%+ covered
- Block merge if not met

---

## Quick Reference

| Goal | Command |
|------|---------|
| **Backend coverage locally** | `cd backend && uv run pytest tests/ --cov=app --cov=agents --cov-report=html` |
| **Frontend coverage locally** | `cd frontend && npm run test` |
| **Backend coverage report** | `open backend/htmlcov/index.html` |
| **Frontend coverage report** | `open frontend/coverage/index.html` |
| **Compare to main** | Go to Codecov dashboard (codecov.io) |
| **CI artifact download** | GitHub Actions → Workflow run → Artifacts |
| **Add new test file** | Create `backend/tests/test_*.py` or `frontend/src/**/*.test.ts` |

---

## Next Steps

1. **Right now:** Run coverage locally (see above) to see your baseline
2. **This week:** Open coverage reports for any new code you write
3. **Next week:** Add tests for any red files you find
4. **Review:** Discuss coverage strategy in team sync

---

## Need Help?

- **Full guide:** See `docs/COVERAGE_GUIDE.md`
- **CI config:** `.github/workflows/ci.yml`
- **Backend config:** `backend/pyproject.toml` (tool.coverage)
- **Frontend config:** `frontend/vitest.config.ts` (coverage section)
