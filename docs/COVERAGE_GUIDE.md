# Test Coverage Guide — VelocityAI

This document explains how test coverage is collected, reported, and enforced in VelocityAI's CI/CD pipeline.

## Overview

Coverage is collected for both **backend Python** (`app/` + `agents/`) and **frontend TypeScript/React** (`frontend/src/`). Reports are generated in CI and uploaded to Codecov for visibility.

| Layer | Tool | Config | Reports | CI Artifact |
|-------|------|--------|---------|-------------|
| **Backend** | `pytest-cov` (coverage.py) | `backend/pyproject.toml` | HTML + XML + JSON | `backend-coverage-report` |
| **Frontend** | `vitest` + `@vitest/coverage-v8` | `frontend/vitest.config.ts` | HTML + LCOV + JSON | `frontend-coverage-report` |

---

## Local Coverage (Developer Machine)

### Backend

**Run tests with coverage:**

```bash
cd backend
uv venv --python 3.12
uv pip install -r requirements.txt -r requirements-dev.txt
# Run all tests with coverage
uv run pytest tests/ \
  --cov=app \
  --cov=agents \
  --cov-report=html \
  --cov-report=term-missing
```

**View the HTML report:**
```bash
# Opens in your browser
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
start htmlcov/index.html  # Windows
```

**View summary in terminal:**
```bash
uv run coverage report
```

**Example output:**
```
Name                          Stmts   Miss  Cover   Missing
─────────────────────────────────────────────────────
app/__init__.py                   2      0   100%
app/api/runs.py                 245     84    66%   45-50, 78-92, ...
app/api/auth.py                 125    125      0%   1-125
agents/execution_engine.py      156     12    92%   203-205, 290-301
agents/capabilities/base.py      87      3    97%   120-122
─────────────────────────────────────────────────────
TOTAL                          3521    982    72%
```

### Frontend

**Run tests with coverage:**

```bash
cd frontend
npm ci
# Run all tests with coverage
npm run test
```

**View the HTML report:**
```bash
# Opens in your browser
open coverage/index.html  # macOS
xdg-open coverage/index.html  # Linux
start coverage/index.html  # Windows
```

**Run tests without coverage (faster):**
```bash
npm run test:no-coverage
```

---

## CI/CD Coverage Reports

### During Pull Requests

1. **Backend coverage** is collected and uploaded to Codecov
2. **Frontend coverage** is collected and uploaded to Codecov
3. PR comment appears with:
   - Overall coverage %
   - Lines added/removed coverage impact
   - Link to detailed report

### Downloading Coverage Reports

After a CI run completes:

1. Go to the GitHub Actions workflow run
2. Scroll to "Artifacts" section
3. Download either:
   - `backend-coverage-report` (HTML + JSON)
   - `frontend-coverage-report` (HTML + LCOV)
4. Extract and open `index.html` in your browser

### Codecov Dashboard

Coverage is also uploaded to [Codecov](https://codecov.io) for historical tracking:

1. Go to the repository Codecov page
2. View coverage trends over time
3. Compare coverage on the PR vs main branch
4. See which files regressed

**Example badge for README:**
```markdown
[![codecov](https://codecov.io/gh/your-org/velocityai/branch/main/graph/badge.svg)](https://codecov.io/gh/your-org/velocityai)
```

---

## Coverage Configuration

### Backend (Python)

**File:** `backend/pyproject.toml`

```toml
[tool.coverage.run]
source = ["app", "agents"]
omit = [
    "*/tests/*",
    "*/test_*.py",
    "*/__pycache__/*",
]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "raise NotImplementedError",
    "if TYPE_CHECKING:",
    "@abstractmethod",
]
precision = 2
show_missing = true
```

**Key settings:**
- `source` — which packages to measure (app + agents)
- `omit` — which files to skip (tests, cache)
- `exclude_lines` — lines that don't need coverage (type guards, abstracts)
- `show_missing` — display uncovered line numbers

### Frontend (TypeScript/React)

**File:** `frontend/vitest.config.ts`

```typescript
coverage: {
  provider: "v8",
  reporter: ["text", "text-summary", "html", "json", "xml", "lcov"],
  exclude: [
    "node_modules/",
    "src/**/*.test.{ts,tsx}",
    "src/**/*.spec.{ts,tsx}",
  ],
  lines: 80,
  functions: 80,
  branches: 80,
  statements: 80,
  all: true,  // Report all files, even those with no tests
}
```

**Key settings:**
- `provider` — use V8 engine (built into Node.js)
- `reporter` — output formats (HTML, JSON, XML, LCOV)
- `exclude` — exclude test files themselves
- `lines/functions/branches/statements` — thresholds (currently advisory)
- `all: true` — report untested files (highlights gaps)

---

## Reading Coverage Reports

### HTML Report Structure

Both backend and frontend HTML reports show:

1. **Summary page** — overall % by category (lines, functions, branches, statements)
2. **File tree** — browse coverage by directory
3. **File details** — click a file to see:
   - Line-by-line coverage (green = covered, red = uncovered, yellow = partial)
   - Line numbers and hit count
   - Branches (if/else) coverage

### Interpreting Colors

| Color | Meaning |
|-------|---------|
| 🟢 **Green** | Line is executed by at least one test |
| 🔴 **Red** | Line is NOT executed by any test (gap) |
| 🟡 **Yellow** | Line is partially covered (only some branches executed) |
| ⚪ **Gray** | Excluded (pragma: no cover, abstract method, type-only) |

### Common Gaps

**Red files indicate:**
- No tests exist for that module
- Only happy path is tested (error cases missing)
- New code added without corresponding tests
- Dead code (ruff + vulture should catch this)

**Example: uncovered API endpoint**

```python
# app/api/analytics.py (0% coverage — red)
@router.get("/api/analytics/summary")
async def get_summary(owner_id: str):  # ← Never called in tests
    return { "tokens": 1000 }
```

---

## Enforcing Coverage in CI

### Current State (Non-blocking)

Coverage is collected but does NOT block merges. All PRs pass even if coverage drops.

### Recommended Path to Enforcement

**Phase 1 (Now):** Make coverage visible
- ✅ Collect and report coverage
- ✅ Comment on PRs with impact
- ✅ Upload to Codecov dashboard

**Phase 2 (2–4 weeks):** Warn on regression
- Add script to fail if coverage drops below previous baseline
- Example: main is 55%, PR is 54% → fail

**Phase 3 (4–8 weeks):** Enforce minimum
- Fail CI if overall coverage < 50% (gradually increase to 70%)
- Per-file threshold for new code: >= 70%

### How to Add Enforcement

**Option A: Fail if overall coverage drops**

```yaml
# In .github/workflows/ci.yml backend job
- name: pytest (fail if coverage drops)
  run: |
    uv run pytest tests/ \
      --cov=app --cov=agents \
      --cov-report=term-missing \
      --cov-report=json
    # Compare coverage.json to baseline on main
    python scripts/check_coverage_regression.py
```

**Option B: Require minimum coverage per file**

```yaml
- name: pytest (fail if new code < 70% covered)
  run: |
    uv run pytest tests/ \
      --cov=app --cov=agents \
      --cov-report=json
    python scripts/enforce_new_code_coverage.py --min=70
```

---

## What to Do When Coverage Is Low

### 1. Identify the Gap

Open the HTML report and find uncovered lines (red):

```
app/api/analytics.py — 0% (40 lines, 0 covered)
app/api/admin.py — 15% (60 lines, 9 covered)
frontend/src/components/GatePanel.tsx — 25% (120 lines, 30 covered)
```

### 2. Classify the Gap

- **NEW CODE?** Developer should add tests (PR requirement)
- **EXISTING CODE?** Create an issue to backfill coverage
- **HARD TO TEST?** (e.g., error path, race condition) Add comment and docstring explaining why

### 3. Create Tests

**Example: Missing analytics test**

```python
# backend/tests/integration/test_analytics.py
def test_analytics_summary():
    """Test GET /api/analytics/summary aggregates tokens correctly."""
    # Create runs with known token counts
    # Call the endpoint
    # Assert aggregation is correct
    pass

def test_analytics_summary_date_range():
    """Test date range filtering in analytics."""
    pass

def test_analytics_summary_error_handling():
    """Test malformed date ranges."""
    pass
```

**Example: Missing component test**

```typescript
// frontend/src/components/GatePanel.test.tsx
describe("GatePanel", () => {
  test("renders approve button", () => {
    render(<GatePanel gate={mockGate} onApprove={jest.fn()} />);
    expect(screen.getByRole("button", { name: /approve/i })).toBeInTheDocument();
  });

  test("disables button when gate is completed", () => {
    render(<GatePanel gate={{ ...mockGate, status: "approved" }} />);
    expect(screen.getByRole("button")).toBeDisabled();
  });
});
```

### 4. Re-run Coverage

```bash
cd backend
uv run pytest tests/ --cov=app --cov=agents --cov-report=html
open htmlcov/index.html
```

---

## Glossary

| Term | Definition |
|------|-----------|
| **Line coverage** | % of code lines executed by tests |
| **Branch coverage** | % of if/else/ternary branches taken |
| **Function coverage** | % of functions called by tests |
| **Statement coverage** | % of executable statements run |
| **Uncovered** | Code never executed (red in report) |
| **Partial** | Only some branches of a decision executed (yellow) |
| **Excluded** | Lines marked `pragma: no cover` (gray, intentional) |
| **Regression** | Coverage % dropped compared to previous commit |
| **Golden files** | Byte-identical characterization outputs (exempt from % gates) |

---

## Troubleshooting

### Coverage Report Shows 0% for a file

**Cause:** The file isn't imported during test runs.

**Fix:**
- Ensure the module is actually tested
- Check `exclude` settings in config
- Verify test file names match (`test_*.py` or `*.test.ts`)

### Coverage shows 100% but tests are weak

**Cause:** All lines execute but test assertions are missing or too loose.

**Fix:**
- Add assertions that verify behavior, not just "no exception"
- Test error cases, not just happy path
- Use code review to spot weak tests

### CI coverage different from local

**Cause:** Different Python version, environment variables, or excluded markers.

**Fix:**
- Run with `PYTHONUTF8=1` locally (Windows)
- Check `.github/workflows/ci.yml` for pytest flags
- Run `pytest tests/ -m 'not requires_api_key'` to skip live tests

### Coverage dropped after merge

**Cause:** New code added without tests, or existing tests deleted.

**Fix:**
- Run `git diff main HEAD -- frontend/src` to see what changed
- Check coverage report for newly red files
- Add tests or revert the change

---

## Links

- [Coverage.py documentation](https://coverage.readthedocs.io/)
- [Vitest coverage docs](https://vitest.dev/config/#coverage)
- [Codecov integration guide](https://docs.codecov.io/docs)
- [Best practices for test coverage](https://testing-library.com/docs/queries/about/#priority)

---

## Questions?

Ask in `#engineering` Slack or open an issue with the `[testing]` label.
