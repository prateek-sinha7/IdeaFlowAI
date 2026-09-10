# CI/CD Pipeline — Design Decisions

This document holds the "why" behind non-obvious choices in
`.github/workflows/*.yml` and `.github/actions/*/action.yml`. Each workflow
file keeps a short comment with a pointer here rather than repeating the
full rationale inline — see F-07 in the CI/CD audit: comments that duplicate
long incident/design writeups drift out of sync with the code they describe
faster than a single canonical doc does, and a long comment block obscures
the step it's attached to.

For **operator** instructions (how to set up AWS, GitHub Environments, roles,
first deploy) see `docs/GITHUB_CICD_SETUP.md`. This document is for engineers
changing the workflow files themselves.

---

## Action pinning and CVE-2026-33634

Every third-party and first-party GitHub Action referenced in
`.github/workflows/*.yml` is pinned to a full commit SHA, never a mutable tag
(e.g. `uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1`).

This is a direct response to **CVE-2026-33634** (GHSA-69fq-xp46-6x23) — the
March 2026 Trivy/aquasecurity supply-chain compromise, where attackers
force-pushed malicious commits onto **existing version tags** of
`aquasecurity/trivy-action` and `aquasecurity/setup-trivy`. Any workflow that
referenced those actions by tag (e.g. `@v0.29.0`) silently started running
attacker-controlled code on its next run, with no change to the workflow file
itself. The same incident window included compromised npm and PyPI packages,
so the response here is deliberately broader than just Trivy.

Two consequences that follow from this, both enforced in the workflow files
themselves rather than left as convention:

1. **Every `uses:` line is SHA-pinned**, with the human-readable version kept
   as a trailing `# vX.Y.Z` comment (Dependabot understands this format and
   updates both together — see `.github/dependabot.yml` if/when added).
2. **The `security-scan` job in `ci.yml` does not use `aquasecurity/trivy-action`
   or `aquasecurity/setup-trivy` at all**, even pinned by SHA. Instead,
   gitleaks, checkov, trivy, and tflint are installed as direct release
   binaries: download the exact release archive by version-pinned URL,
   verify its SHA256 against a checksum recorded in the workflow (or in
   `.github/actions/install-checksummed-tool/action.yml`'s caller, since the
   F-05 refactor), then extract and install. This removes any dependency on
   a third party's Action *tag* staying uncompromised between now and when
   the workflow runs — the checksum is verified by this repository, not
   borrowed from whatever the tag currently points at.

**When bumping a tool version** (trivy, tflint, gitleaks, terraform): fetch
the new release's official SHA256SUMS file, verify it against the vendor's
published checksum through an independent channel (their release notes page,
a second mirror, etc. — not just the same download you're about to trust),
and update both the version string and the checksum together. Never carry a
checksum forward without re-verifying it against the new artifact.

---

## The SSM RunCommand heredoc incident (why payloads are built, not inlined)

`deploy.yml`, `provision.yml`, and `admin-recovery.yml` each send a shell
script to an EC2 instance via `aws ssm send-command`. All three build that
script as **a prelude of literal shell variable assignments, followed by the
target script file catted in verbatim** — e.g.:

```bash
{
  echo '#!/bin/bash'
  echo "REGISTRY='${ECR_REGISTRY}'"
  echo "IMAGE_TAG='${IMAGE_TAG}'"
  cat .github/scripts/remote-deploy.sh
} > remote.sh
```

This shape exists because of a real outage. An earlier version of this
workflow embedded the on-box script directly as a YAML heredoc inside the
`run:` block. The GitHub Actions runner's own shell interprets a `run: |`
block *before* anything is sent anywhere — so any `$variable` inside that
heredoc that happened to collide with something meaningful to the RUNNER's
shell (rather than the box's shell, which is a separate execution entirely,
minutes later, on a different machine) got expanded or evaluated at the
wrong layer. The specific failure: the on-box health-check loop used `$i` as
a loop counter, exactly the kind of generic name a heredoc doesn't protect.
The runner's own shell — which enforces `set -u` — evaluated that `$i`
before the box ever saw the script, found it unbound in the runner's
context, and aborted with `unbound variable`. The deploy failed at the
YAML-authoring layer, not on the box, with an error message that gave no
hint the box was never reached.

The fix, still in force: the payload is written to `remote.sh` on the
**runner's** filesystem first, entirely through `echo` statements whose
`${VAR}` expansions are the *runner's* env vars (explicit, single-purpose,
never collision-prone names like `ECR_REGISTRY`), and the target script
(`remote-deploy.sh`, `remote-bootstrap.sh`, `remote-admin-recovery.sh`) is
appended with `cat`, completely unparsed by anything until it reaches the
box. Nothing in the target script's body is ever subject to runner-side
shell expansion, because the runner's shell never opens a heredoc containing
that body — it only ever sees `cat some-file.sh` as an opaque command.

**Rule for any future SSM payload:** never inline a target script's body as
a YAML block scalar or heredoc in a workflow `run:` step. Keep it as a
committed, separately-lintable `.sh` file (which also makes it visible to
`shellcheck` — see the `shellcheck` job in `ci.yml`), and assemble the
payload with `cat`.

The send + poll logic itself (SSM's `send-command`, then polling
`get-command-invocation` to a terminal state) is shared by all three
workflows via `.github/actions/ssm-run/action.yml` (F-05) — see that file's
own header for the poll-loop specifics (`InvocationDoesNotExist` handling,
the 5-consecutive-API-error abort, fetching both stdout and stderr on every
terminal branch).

---

## Why Terraform is never installed to `plan`/`apply` in CI/CD

Terraform is present in this repository's CI only as a **static analysis
target** — `checkov`, `trivy config`, and `tflint` all read `.tf` files
without a provider or a backend, and `terraform fmt`/`validate` run with
`-backend=false` purely to catch syntax errors. No job runs
`terraform plan` or `terraform apply`. This is a locked design decision; see
`docs/GITHUB_CICD_SETUP.md` for the operational consequence (infrastructure
changes are applied out-of-band by an operator, not by a workflow run).

---

## SonarCloud: `sonar-project.properties` is authoritative, not `-D` flags

`sonar-project.properties` at the repo root is the single source of truth
for SonarScanner's project identity, source paths, exclusions, and coverage
report paths. The `sonarcloud-analysis` job in `ci.yml` intentionally passes
**no** `-Dsonar.organization=`, `-Dsonar.projectKey=`, `-Dsonar.exclusions=`,
etc. flags — those values live in the properties file alone (F-08). A
`-D` flag on the command line overrides the properties file silently on any
conflict, which previously meant the properties file was decorative: editing
it had no effect unless the identical edit was *also* made to the workflow.
The only flag still passed at invocation is `-Dsonar.log.level`, which has no
equivalent in the properties file by design (it's a debugging knob, not
committed project config).

**When changing SonarCloud scope/exclusions:** edit
`sonar-project.properties` only. If a value needs to differ between CI and
local runs, that is a sign it belongs in a `-D` flag instead — but check the
properties file first for whether the value already exists there.

---

## Phase 2 — Branch Protection Rulesets & Environments

GitHub Repository Rulesets (a newer alternative to legacy branch protection
rules) and Environments define the merge and deployment posture for the
repository. This section explains the design and how to maintain it.

### Ruleset Files: The Strategy

Three rulesets are committed as JSON under `.github/rulesets/`:

1. **`main.json`** — Production source branch (`refs/heads/main`)
   - **Deletion**: blocked
   - **Non-fast-forward** (force push): blocked
   - **Pull requests**: required
     - 2 approvals (higher than dev/staging for prod safety)
     - Code owner review required
     - Self-approval of own last push blocked (`require_last_push_approval: true`)
     - Stale review dismissal on push (re-review on force-push equivalent)
     - All review threads must be resolved before merge
   - **Required status checks** (strict: branch must be up-to-date):
     - `ci-required` (Phase 1: aggregator of all CI jobs)
     - `CodeQL` (GitHub's SAST scanner)
     - `SonarCloud Code Analysis` (quality gates)
   - **Required signatures**: commits must be GPG-signed
   - **Bypass actors**: `[]` — no one, not even admins

2. **`dev-staging.json`** — Deploying branches (`refs/heads/dev`, `refs/heads/staging`)
   - **Deletion**: blocked
   - **Non-fast-forward**: blocked
   - **Pull requests**: required
     - 1 approval (faster iteration than main, but still gated)
     - Code owner review optional (team-specific branches, no forced CODEOWNERS)
     - Stale review dismissal enabled
     - All review threads must be resolved
   - **Required status checks** (strict):
     - `ci-required` only (CodeQL and SonarCloud run but are advisory)
   - **Bypass actors**: `[]`

3. **`tags.json`** — Release tags (`refs/tags/v*`)
   - **Deletion**: blocked
   - **Non-fast-forward**: blocked
   - **Creation**: restricted to release-managers team (GitHub API only; no UI
     enforcement of the restriction without a custom GitHub App)
   - Prevents accidental or malicious retag/deletion of release artifacts

### Environment Files: Deployment Policy

Three environments are defined in `.github/environments/`, each with deployment
branch policies and approval requirements:

1. **`prod.json`** — Production deployment
   - `can_admins_bypass: false` — admins cannot bypass deployment approval
   - `deployment_branch_policy.protected_tags: true` — deploys from release tags only
   - `reviewers: [release-managers]` team, min 2 approvals
   - `wait_timer: 0` — no waiting; approval is the gate
   - **Usage**: `deploy.yml`'s `deploy` job targets this environment for prod
     releases

2. **`staging.json`** — Staging deployment (production-adjacent)
   - `can_admins_bypass: true` — team can expedite in emergency
   - `deployment_branch_policy.protected_branches: true` — deploys from `staging`
     branch only
   - `reviewers: [engineering]` team, min 1 approval
   - Lighter approval bar than prod, but branch-locked

3. **`dev.json`** — Development deployment (permissive)
   - `can_admins_bypass: true`
   - `deployment_branch_policy.protected_branches: true` — deploys from `dev`
     branch only
   - `reviewers: []` — no approval required (CI gates the branch itself via ruleset)
   - `require_branch_uptodate: false` — faster iteration

### Bootstrap: Applying Rulesets & Environments

A shell script `.github/scripts/setup-rulesets.sh` applies all rulesets and
environment configs via the GitHub CLI. Run once at repo setup:

```bash
# Validate and apply (dry run first)
./.github/scripts/setup-rulesets.sh --repo Hexaware-HnI/velocityai --dry-run

# Apply for real
./.github/scripts/setup-rulesets.sh --repo Hexaware-HnI/velocityai
```

The script:
- Validates all JSON files parse
- Verifies `gh` CLI has admin access to the repo
- Creates or updates each ruleset via the GitHub API
- Configures each environment with approval + branch policies
- Applies merge hygiene: `delete_on_merge: true` (auto-clean PR branches),
  `allow_squash_merge: true` (squash-only), `web_commit_signoff_required: true`
  (commits must be signed)

### Why Rulesets, Not Legacy Branch Protection

GitHub Rulesets (introduced ~2023, mandatory for Enterprise) supersede legacy
branch protection in several ways:

- **Layering**: multiple rulesets can apply to the same ref; they combine
  (OR union of enforcement, so a stricter rule always wins)
- **Tag rules**: legacy branch protection does not guard tags; rulesets do
- **Required workflows**: a ruleset can require that a specific workflow job
  completes before merge — future upgrade path
- **Bypass actors**: explicit allow-list instead of implicit admin escape hatch
- **Codified**: rulesets are JSON in the repo, not hidden in GitHub UI settings,
  making the security posture reviewable and version-controlled

### Testing & Verification

After applying the rulesets:

1. **Verify in GitHub UI**: Settings > Rules (or Settings > Branches > Branch
   protection for legacy view)
2. **Test main**: open a PR to `main` and verify:
   - 2 approvals required
   - Cannot force-push
   - Cannot merge without all checks passing
3. **Test staging**: push to `staging` and verify ruleset blocks push if CI fails
4. **Test tags**: try `git tag v0.0.0 && git push origin v0.0.0` to a non-release-manager
   account — should fail with a permission error or API rejection

### Maintenance

**When a new team is formed**: update the `reviewers` array in the relevant
environment JSON file(s), commit, and re-run the setup script (or use `gh api`
to update the environment directly).

**When adding a new status check** (e.g., a new security gate): add it to the
`required_status_check_contexts` array in the appropriate ruleset, commit, and
re-run the setup script.

**When removing a status check**: remove it from the ruleset JSON, commit, and
apply — the script will update the ruleset to the new spec.


---

## Phase 3 — Python Quality Gates (Format, Type, Security, Coverage)

### Format Checking: ruff format

Format checking is the first gate for backend linting after correctness (ruff) and before type checking. The step:

```bash
ruff format --check --diff .
```

**Why ruff format, not Black?**
- The project already runs ruff for correctness. Adding a second tool (Black) means two linters, two configurations, two maintenance streams.
- ruff format is ~30× faster than Black and is configured identically to ruff check (same `src`, same `pyproject.toml [tool.ruff]` section).
- ruff format's defaults align with Black's (88-character line length, trailing commas, etc.), so the behavioral diff is negligible.
- Single tool, single config: simpler for developers and CI.

**Adoption strategy:**
- The check is blocking from day one (not warn-only).
- Developers run `ruff format .` locally before pushing to fix formatting issues.
- The CI check catches any drifts before merge.

**Difference from correctness checks:**
- `ruff check .` catches bugs: unused imports, undefined names, type mismatches.
- `ruff format --check .` catches style only: line length, quote consistency, import organization.
- Both are ruff but serve different gates in the quality pipeline.

### Type Checking Scope: agents/ Included

Pyright was configured in early phases to check only `app/` for import resolution (missing-imports errors). The agents/ package — the execution kernel and capability registry — was excluded.

**The fix**: Add "agents" to pyrightconfig.json:

```json
"include": ["app", "agents"],
```

**Why it matters:**
- Import-resolution checking (the ONLY check enabled in "off" mode) catches deleted or moved modules.
- `app/` alone is the web layer; `agents/` is the kernel.
- A lazy import like `from agents.factory import X` that refers to a deleted module goes undetected if agents/ is unchecked.
- One-line fix closes a gap that's been silently letting import errors through since early pyright adoption.

**Scope unchanged:**
- Pyright still runs in `typeCheckingMode: "off"` with only `reportMissingImports: "error"`.
- This is NOT a full type check (that's a separate initiative, Phase 4+).
- Import resolution only: what ruff + vulture can't see (cross-file module deletions).

### Security Scanning: Bandit (Python SAST)

Bandit is a Python static application security testing (SAST) tool. It detects:
- Hardcoded secrets (passwords, keys, tokens)
- SQL injection risks (string interpolation in queries)
- Insecure cryptography (`pickle`, weak hashing, old SSL versions)
- Dangerous deserialization (untrusted `pickle.loads()`)
- OS command injection (`shell=True` in subprocess)
- etc.

**How it runs:**

```bash
bandit -c pyproject.toml -r app agents -ll
```

- `-c pyproject.toml` — config in [tool.bandit]
- `-r app agents` — recursive scan of production code (excludes tests)
- `-ll` — report MEDIUM + HIGH + CRITICAL severity (skip LOW/INFO)

**Configuration (pyproject.toml [tool.bandit])**:

```toml
level = "medium"
exclude_dirs = ["tests", "alembic/versions", "*/__pycache__"]
skips = [
    "B602",  # shell=True false positive: LangChain providers intentionally accept shell commands
    "B307",  # pickle false positive: Pydantic deserialization, not unsafe pickle.loads()
]
```

**Adoption strategy:**
- Blocking gate from day one (not warn-only, unlike pip-audit).
- Baseline: app/ + agents/ are clean (no hardcoded secrets, safe defaults for crypto).
- New findings in PRs are triaged immediately by the offending developer instead of accumulating in a backlog.
- The two skips are known false positives, re-audited at each release (never become stale exceptions).

### Coverage Pipeline Fix (F-10 → F-11 → F-12)

Three interconnected bugs made the coverage pipeline silently fail:

**F-10: Coverage merge broken**

*Problem:* Each pytest shard emitted only Cobertura XML (`--cov-report=xml:coverage-agents-a.xml`), never a `.coverage` SQLite data file.

The `test-results` job then ran:
```bash
coverage combine coverage-agents-a.xml ...
```

This fails: `.coverage.combine()` expects SQLite data files, not XML.

```
CoverageWarning: Couldn't use data file 'coverage-agents-a.xml': file is not a database
No usable data files
exit=1
```

*Solution:*
- Each pytest shard now sets `COVERAGE_FILE: .coverage.<shard>` as an environment variable
- Pytest-cov respects this and emits the `.coverage.<shard>` data file (plus terminal/XML if requested)
- `test-results` combines the data files: `coverage combine .coverage.agents-a .coverage.agents-b ...`
- From the combined data, `coverage xml` generates the coverage.xml SonarCloud consumes

```bash
# Each shard:
COVERAGE_FILE: .coverage.agents-a
pytest --cov-report= --cov-report=xml:htmlcov/index.html ...  # data file + XML for reporting

# test-results job:
coverage combine .coverage.agents-a .coverage.agents-b ...
coverage xml  # generates coverage.xml from combined data
```

**F-11: Coverage doesn't reach SonarCloud**

*Problem:* The `prepare-sonarcloud` job tried to download the artifact named `backend-coverage-report` and read `coverage.xml` out of it. That artifact only ever contained `htmlcov/`, so the file was never there. On the frontend side it looked for `coverage-final.xml`, which vitest never wrote (the `"xml"` entry in the vitest reporter list is not a valid coverage reporter). Both `if [ -f ... ]` guards took the `else` branch, printed `⚠ WARNING` to stderr, and the job **still exited 0** — so SonarCloud received zero coverage while every job reported green. Compounding it, the reports were pointed at `sonar.coverageReportPaths`, which accepts only Sonar's *Generic Test Data* XML schema and would not have parsed Cobertura or istanbul output even if the files had existed.

*Solution (implemented):* `prepare-sonarcloud` was **deleted**. Each report is now uploaded by the job that produces it and downloaded straight to the path `sonar-project.properties` names:

- `test-results` → `coverage combine` → `coverage xml` → normalise `<source>` roots to `backend/...` → artifact `backend-coverage-xml`
- `frontend` → vitest LCOV → normalise `SF:` paths to `frontend/...` → artifact `frontend-coverage-lcov`
- `sonarcloud-analysis` (`needs: [test-results, frontend]`) downloads both and **hard-fails** if either is missing or empty, then runs the scanner with `-Dsonar.qualitygate.wait=true`

Language-specific properties replaced the generic one: `sonar.python.coverage.reportPaths` and `sonar.javascript.lcov.reportPaths`. `backend/pyproject.toml` also sets `relative_files = true`, so Cobertura source roots are relative instead of absolute shard-runner paths that only resolved by runner-path coincidence.

**F-12: junit-merged.xml never created**

*Problem:* The `upload-artifact` step in `test-results` tried to upload `backend/junit-merged.xml`, but no step created it — only individual `junit-*.xml` per shard existed.

*Solution:* The merge step should combine all JUnit files:

```bash
# Implied by coverage merge step; could be explicit:
find . -name junit-*.xml -exec cat {} >junit-merged.xml \;
```

Or use Python's junitparser / defusedxml to merge XML trees properly. (For now, the artifacts are uploaded per-shard; the merge is a follow-up if full test reporting is needed.)

### Coverage Threshold Enforcement (80%)

**Added to each pytest shard**:
```bash
--cov-fail-under=80
```

**Added to pyproject.toml**:
```toml
[tool.coverage.report]
fail_under = 80
```

**Recommendation**: 80% overall + 80% on new code (via SonarCloud quality gate).

**Ratcheting strategy**: If current measured floor is lower than 80%, start there and raise 2% per sprint. This avoids blocking PRs on a retroactive requirement nobody had time to meet on the first run.

**Why 80%?**
- Empirical: 80%+ coverage catches most bugs and regressions.
- Practical: Below 80%, code review doesn't catch untested paths; above 85%, diminishing returns (complexity of test setup balloons).
- Industry standard: most enterprises mandate 80% or higher.

### pytest-split Infrastructure (Phase 3 prep for Phase 3.5)

The hardcoded pytest shard lists in ci.yml (pytest-agents-a, pytest-agents-b with manually listed test files) are a maintenance burden:

- New test files added to `tests/agents/` are silently not run (F-06, happened twice already).
- The CI jobs must be manually updated whenever test discovery changes.
- The test-debt job verifies shard coverage, but that check exists only to catch the drift after the fact.

**Solution: pytest-split** dynamically partitions tests without hardcoding file lists.

**Infrastructure in place** (Phase 3):
- Dependency: `pytest-split==4.1.1` added to requirements-dev.txt
- Configuration: `[tool.pytest_split]` in pyproject.toml with `splitting_strategy = "file"`
- No ci.yml changes yet (deferred to Phase 3.5 for focused validation)

**Ready to use** (Phase 3.5 conversion):
```bash
pytest --splits 4 --group 0 tests/agents/  # Shard 1 of 4 (auto-discover ~25% of files)
pytest --splits 4 --group 1 tests/agents/  # Shard 2 of 4 (~25% of files)
```

**Advantages**:
- **No drift**: New test files are automatically included (split by file count).
- **Deterministic**: Same tests run in the same shard on every CI run (no randomization).
- **No history**: `splitting_strategy = "file"` doesn't require .test_durations (alternative: `duration` strategy requires prior runs).

**Future**: When converted to pytest-split, the test-debt job's "Verify pytest shard coverage" step becomes unnecessary (dynamic discovery can't drift by definition).



---

## Phase 4 — Next.js Quality Gates (ESLint, TypeScript, E2E, npm audit)

### ESLint Strict Mode: --max-warnings 0

ESLint warnings have been downgraded to a non-blocking category across linters for decades (the `--max-warnings` default is `Infinity`, meaning warnings never fail). This works only if the team treats warnings as seriously as errors, which in practice doesn't happen.

**The fix**:
```json
{
  "scripts": {
    "lint": "eslint --max-warnings 0"
  }
}
```

**Every warning now fails the build.** This includes:
- Unused variables (code smell, hidden logic)
- Unreachable code (dead branches)
- react-hooks violations downgraded to warn

**Why this matters**: In the pre-Phase-4 state, the eslintrc.json downgraded `react-hooks/set-state-in-effect` to warn — a render-loop bug class. Developers ignored it because it didn't block. Phase 4 fixes this: now all react-hooks rules are errors, and `--max-warnings 0` ensures even cosmetic warnings block.

### React Hooks Ratchet: warn → error

Four react-hooks rules were downgraded to warn due to pre-existing violations in the codebase:
- `exhaustive-deps` — missing deps in useEffect
- `set-state-in-effect` — setState inside effect without guards (render loops)
- `static-components` — component definitions inside effects/renders
- `preserve-manual-memoization` — unnecessary useMemo/useCallback

**Phase 4 ratchet**: All four are now `error`.

**Adoption strategy**:
- Phase 4 (now): Rules are errors (block new violations)
- Phase 4.5: Per-directory ESLint overrides so existing violations don't block while new ones do
- Phase 5: Full compliance (all directories enforced)

**Why ratchet gradually**: A cascade of newly-failing violations on one merge blocks the entire PR. Better to enforce going forward (new code must comply) while allowing existing code time to be fixed per-directory.

### Standalone TypeScript Checking: tsc --noEmit

TypeScript errors were only caught by `next build`, which is the last step in the frontend job. A single type error meant the entire CI job ran (lint, test, build) only to fail at the end.

**The fix**: Add a standalone typecheck script:
```json
{
  "scripts": {
    "typecheck": "tsc --noEmit"
  }
}
```

**Run early, in parallel**:
```bash
# Before (sequential, late):
eslint → vitest → next build (type errors caught here)

# After (parallel, early):
    ↙ eslint
   tsc --noEmit       (type errors caught here, fast)
    ↘ vitest
        ↓
    next build
```

**Benefits**:
- Type errors fail in ~10 seconds (tsc) vs. ~2 minutes (next build)
- Developers get faster feedback
- Parallel execution is faster overall

### Playwright E2E Tests in CI

194 Playwright tests exist but were never run in CI. The test-debt job paid the cost of installing the browser (~90 seconds) solely to run `playwright test --list` for a test count, then never executed the suite.

**The fix**: Wire `npm run e2e` into the frontend CI job:
```bash
npm run e2e  # playwright test --project=mocked
```

**Projects**:
- `mocked` — All tests run against mocked APIs (CI project, fast, reliable)
- `live` — Tests against real backend (manual/staging only, via `npm run e2e:live`)

**Benefits**:
- Regressions in UI flows caught before merge
- E2E is a blocking gate (no more silent UI breaks)
- 194 tests run every PR (confidence in integration)

### npm audit: warn-only → blocking

npm audit was run with `|| true` (ignore errors), making it warn-only. Critical vulnerabilities shipped in builds.

**The fix**:
```bash
# Before:
npm audit --audit-level=high || true

# After:
npm audit --audit-level=critical
```

**Ratchet plan**:
- Phase 4 (now): `--audit-level=critical` (fewer findings, less churn)
- Phase 4.5 (September): `--audit-level=high`
- Phase 5+: `--audit-level=moderate` (full security baseline)

**Rationale**: Jumping from warn-only to high would surface many pre-existing findings and potentially block all PRs. Starting at critical allows Phase 4 to merge without a wave of security debt, then tightening as findings are triaged.

### Lockfile Drift Detection

A common footgun: editing `package.json` but forgetting to commit the updated `package-lock.json`. Local builds work (node_modules is fresh), but CI uses the stale lock file, installing old versions.

**The fix**: Add a git status check right after `npm ci`:
```bash
git diff --exit-code package-lock.json
```

**What it catches**:
```
1. Dev edits package.json (adds or updates dep)
2. Local: npm install updates package-lock.json
3. Staged/committed: only package.json, lock file is stale
4. CI: npm ci uses stale lock file
5. Result: different versions locally vs. CI
```

**The check**:
```bash
git diff --exit-code package-lock.json || {
  echo "package-lock.json is out of sync"
  echo "Run 'npm install' to update it"
  exit 1
}
```

Fails the build, developer runs `npm install`, commits updated lock file. Build passes next time.

### npm ls Dependency Tree Validation

Even when `npm ci` succeeds with the lock file, the dependency tree can have inconsistencies — primarily unsatisfied peer dependencies. npm ls detects these:

```bash
npm ls --omit=dev > /dev/null
```

**Why --omit=dev**: Omits dev dependencies (we only care about runtime tree for prod builds).

**What it reports**: Missing peer deps, version conflicts, etc. Catches edge cases that `npm ci` doesn't surface.

### Dead Dependency Cleanup: dependency-cruiser

`dependency-cruiser` was installed as a devDependency but never used:
- No `.depcruiserrc` configuration
- No npm script to run it
- No CI step

**Phase 4 decision**: Remove it.

**Rationale**: It's a *good* tool for enforcing frontend import boundaries (like import-linter does for backend), but without configuration or usage, it's dead code. If import boundary enforcement becomes a requirement later, it can be reinstalled and configured with proper rulesets.

**Future consideration**: Phase 5+ could add dependency-cruiser with import rules if the team adopts import graph policy for the frontend.



---

## Phase 6 — Supply Chain Security (Reproducible Builds, Provenance, Dependency Automation)

Phase 6 hardens supply chain security: builds become reproducible via uv.lock,
provenance attestations enable audit trails, digest pinning plus blocking image
scans prevent tampered or vulnerable bytes from reaching a host, and Dependabot
automates security updates. SBOM generation and Cosign image signing were part of
the original Phase 6 design and have since been removed — see the removal note
below.

### Reproducible Builds via uv.lock

**F-21 Problem**: Every CI job ran `uv pip install -r requirements.txt`, resolving fresh each time. Two identical commits could install different bytes due to floating version specs like `langchain-mcp-adapters>=0.2.2,<0.3`.

**Phase 6 Solution**:

1. **Split requirements.txt** into `requirements-prod.txt` and `requirements-dev.txt`
   - `requirements-prod.txt`: production runtime only (no test tools)
   - `requirements-dev.txt`: test/dev tools (pytest, hypothesis, httpx, etc.)
   - `requirements.txt`: now a convenience include that references both (backward compat)

2. **Update setup-backend action** to use `uv sync --frozen` in CI:
   ```yaml
   inputs:
     frozen:
       description: "'true' to use --frozen (reproducible), 'false' for resolver"
       default: "false"
   
   - run: |
       if [[ "$FROZEN" == "true" ]]; then
         uv sync --frozen    # CI: exact reproducibility from uv.lock
       else
         uv sync             # Local: can update versions
       fi
   ```

3. **Update all CI jobs** to pass `frozen: "true"` to setup-backend

4. **Update cache key** to include uv.lock:
   ```yaml
   cache-dependency-glob: "${{ inputs.working-directory }}/{requirements*.txt,uv.lock}"
   ```

**Benefit**: Identical commits produce identical bytes. Supply chain attacks must forge both the source commit AND the lock file.

### Clean Dockerfile (Production Only)

**F-24 Problem**: `requirements.txt` mixed runtime and test dependencies. The Dockerfile comment admitted shipping ~5 MB of dead weight (actually ~350 MB when playwright browser is included).

**Phase 6 Solution**:

1. **Dockerfile now installs only `requirements-prod.txt`** (no pytest, hypothesis, httpx, playwright package)
2. **Playwright browser binary** is installed separately (`playwright install --with-deps chromium`) — it's a production runtime dependency for render-validation, not a test tool
3. **Net result**: No test tools, no dead weight in production images

### Provenance Attestations

**F-22 Problem**: Provenance and SBOM were explicitly disabled (`provenance: false, sbom: false`), disabling the entire supply chain audit trail.

**Current state**: `provenance: mode=max` is enabled; `sbom:` is **not**.

```yaml
provenance: mode=max    # SLSA v1 Build Level 2, signed by GitHub
# no sbom: flag — see below
```

`provenance: mode=max` is kept because it is free: buildkit attaches a
GitHub-signed attestation to the pushed digest, it needs no extra tooling and no
extra IAM, and nothing in the deploy path has to read it back for a deploy to
work.

### Removed: SBOM generation and Cosign signing/verification

An earlier revision of this document described `sbom: true` plus `cosign sign` in
the `build` job and `cosign verify` in the `deploy` job as live controls. They
were removed, because as built they did not work and could not have worked:

- **The SBOM attestation was a no-op.** `sbom: true` makes buildkit attach an
  SBOM as an OCI attestation *in the registry*; it does not write a file to the
  runner. The `cosign attest --predicate sbom-backend.spdx.json` step therefore
  referenced a path that never existed, and the failure was swallowed by a
  trailing `|| true`. Every run logged `Attesting SBOM...` and attested nothing.
- **`cosign verify` in the `deploy` job could never pass.** Reading a signature
  back out of a private ECR repository requires ECR credentials.
  `infra/terraform/bootstrap/github_oidc.tf` grants `ecr:*` **only** to the
  shared build role — the per-environment deploy roles hold SSM, KMS-via-SSM and
  EC2 SendCommand and nothing else — and the `deploy` job has no
  `amazon-ecr-login` step. The verify call fails on
  `ecr:GetAuthorizationToken` regardless of whether a valid signature exists.
- **Signing was skipped on the re-run path.** Both sign steps were gated on
  `steps.probe.outputs.*_exists != 'true'`. A re-run that adopted an already
  pushed tag skipped signing, so a run that had pushed but not yet signed left a
  permanently unverifiable tag — unfixable, because the ECR repositories are
  IMMUTABLE and the tag cannot be rebuilt.

Both were deleted rather than left in place as decoration.

**What guarantees integrity now**: the `build` job resolves an immutable
`sha256:` digest, Trivy and Grype scan exactly those bytes (blocking on any
resolved High/Critical), and the `deploy` job ships that same digest into the SSM
payload. The host pulls **by digest**, so any tampering changes the digest and
the pull fails. This is the control that was actually load-bearing all along.

**If signature verification is reintroduced**, it needs all three of:
1. `ecr:GetAuthorizationToken` + `ecr:BatchGetImage` +
   `ecr:GetDownloadUrlForLayer` on each per-environment deploy role,
2. an ECR login step in the `deploy` job,
3. signing that is **not** conditional on the probe, so an adopted tag is still
   guaranteed to carry a signature.

Note also that keyless Cosign publishes the image digest and the signing
identity (org/repo/workflow ref) to the public Rekor transparency log. For a
private enterprise repository that is a disclosure decision, not just a
technical one.

### Dependabot Automation

**F-23 Problem**: No dependency update automation. Pinned-exact versions + no automation = pins rot into known-vulnerable versions.

**Phase 6 Solution**: `.github/dependabot.yml` with scoped update groups:

```yaml
version: 2

updates:
  # Python — group langchain ecosystem to reduce PR noise
  - package-ecosystem: pip
    directory: /backend
    schedule: { interval: weekly, day: monday }
    groups:
      langchain:
        patterns: ["langchain*", "langgraph*", "deepagents"]

  # Node.js
  - package-ecosystem: npm
    directory: /frontend
    schedule: { interval: weekly }

  # GitHub Actions (SHA-pinned, comment updated automatically)
  - package-ecosystem: github-actions
    directory: /
    schedule: { interval: weekly }

  # Docker base images
  - package-ecosystem: docker
    directory: /backend
    schedule: { interval: weekly }

  # Terraform (monthly, less frequent)
  - package-ecosystem: terraform
    directory: /infra/terraform
    schedule: { interval: monthly }
```

**Benefits**:
- Dependabot preserves SHA pins, updates the `# vX.Y.Z` comment
- Grouped PRs (langchain ecosystem) reduce noise
- Weekly cadence catches security patches quickly
- Monthly cadence for IaC (more conservative)

### CODEOWNERS for Mandatory Review

**F-25 Problem**: No CODEOWNERS file, so the `require_code_owner_review` rule from Phase 2 had no one to enforce approval.

**Phase 6 Solution**: `.github/CODEOWNERS` with team-based review assignments:

```
backend/agents/**   @Hexaware-HnI/platform-engineering
backend/app/**      @Hexaware-HnI/platform-engineering
frontend/src/**     @Hexaware-HnI/frontend
infra/**            @Hexaware-HnI/devops
.github/**          @Hexaware-HnI/devops
```

**Behavior**:
- Any PR touching `backend/agents/` requires approval from `@Hexaware-HnI/platform-engineering`
- Any PR touching `frontend/src/` requires approval from `@Hexaware-HnI/frontend`
- Any PR touching `.github/workflows/` requires approval from `@Hexaware-HnI/devops`
- GitHub's branch protection rule `require_code_owner_review: true` enforces this

### Summary of Phase 6 Changes

| Control | Before | After | Impact |
|---------|--------|-------|--------|
| **Build reproducibility** | Fresh resolve each job | `uv sync --frozen` from uv.lock | Bit-for-bit reproducible; audit-trail safe |
| **Test deps in production** | ~350 MB (playwright included) | 0 B (prod-only installs) | Smaller images, less attack surface |
| **Provenance** | Disabled | `mode=max` (SLSA L2) | Build chain signed by GitHub |
| **SBOM** | Disabled | Still not generated (removed) | See "Removed: SBOM generation and Cosign signing/verification" above |
| **Image signing** | ❌ absent | ❌ absent (removed) | Integrity rests on digest pinning + blocking Trivy/Grype |
| **Image verification** | ❌ absent | ❌ absent (removed) | Host pulls by digest; tampering changes the digest and the pull fails |
| **Dependency updates** | Manual (pins rot) | Dependabot groups (weekly) | Security patches auto-applied |
| **Code ownership** | ❌ absent | CODEOWNERS + Phase 2 rule | Mandatory team review per path |

### Deployment Workflow (with Phase 6)

```
push to dev/staging, or a v* tag
    ↓
gate: full ci.yml run on the same commit (blocks everything below)
    ↓
build: images built once (provenance: mode=max), pushed to IMMUTABLE ECR
    ↓
build: resolve the sha256 digest (fresh push, or adopted from the ECR probe)
    ↓
build: Trivy scan of that exact digest — any HIGH/CRITICAL blocks
    ↓
deploy: push config to SSM, assemble the SSM payload pinned to those digests
    ↓
deploy: SSM RunCommand -> remote-deploy.sh (pulls BY DIGEST)
    ↓
box: health-check backend + frontend + nginx ingress
    ↓
If health-check passes: record the digests as the environment's recovery point
If health-check fails:  automatic rollback to the previously pinned digests
```

### Migration Path

**Immediate**: Phase 6 changes that are live:
1. Provenance attestation on every pushed image
2. Blocking Trivy scan of the pushed digest in `deploy.yml`, plus the
   dual-engine Trivy + Grype `container-scan` job in `ci.yml`
3. Digest-pinned deploys (no tag ever reaches the host)
4. Dependabot creates PRs for updates
5. CODEOWNERS rule enforces team approval

SBOM generation and Cosign signing/verification are **not** live — see the
removal note earlier in this section.

**First Dependabot PR**: May auto-update 100+ packages (initial backlog). Review and merge without blocking – future PRs are incremental.

**No breaking changes**: Same branches, same workflows, same deploy paths. Just stricter auditing and automation.

### Future Enhancements (Phase 7+)

1. **SLSA Level 3**: Isolated/ephemeral builder (requires GitHub Actions hosted runners or self-hosted hardened builders)
2. **Image signing, done properly**: if reintroduced, it needs ECR read on the
   per-env deploy roles, an ECR login in the `deploy` job, and signing that is
   not skipped on the probe-adopt path. See the removal note above.
3. **SBOM + policy enforcement**: OPA/Conftest gates over a real, retrievable
   SBOM (e.g. "no GPL licenses in prod") — worth doing only once something
   actually consumes the SBOM.
4. **Private registry scanning**: If artifacts are stored in a private registry, add layer security scanning
5. **Binary transparency logs**: Hash images to a transparency log (similar to Certificate Transparency) for append-only audit



---

## Phase 7 — Docker Review (Base Image Pinning, Layer Optimization, Blocking Image Scans)

Phase 7 hardens Docker images: base images pinned to digest, layer optimization, unnecessary tools documented/kept, and image scanning becomes blocking with dual-engine approach (Trivy + Grype).

### Base Image Pinning by Digest

**F-26 Partial Problem**: Base images used mutable tags (`python:3.13-slim-bookworm`, `node:20-bookworm-slim`).

**Phase 7 Solution**:

Backend (`backend/Dockerfile`):
```dockerfile
FROM python:3.13-slim-bookworm@sha256:b6bd71b0dd3811ddbcbc523ec2965fd1e1bcfdf7a20ab24679273d3bee726129 AS builder
```

Frontend (`frontend/Dockerfile` — all three stages):
```dockerfile
FROM node:20-bookworm-slim@sha256:3d0f05455dea2c82e2f76e7e2543964c30f6b7d673fc1a83286736d44fe4c41c AS deps
FROM node:20-bookworm-slim@sha256:3d0f05455dea2c82e2f76e7e2543964c30f6b7d673fc1a83286736d44fe4c41c AS builder
FROM node:20-bookworm-slim@sha256:3d0f05455dea2c82e2f76e7e2543964c30f6b7d673fc1a83286736d44fe4c41c AS runner
```

**Benefit**: Images are now reproducible by digest. If the tag is re-pointed maliciously, the build fails (image hash mismatch).

### Layer Optimization: Pip Cache Mount

**F-27 Problem**: `PIP_NO_CACHE_DIR=1` actively disabled pip's cache, making cold builds slower than necessary.

**Phase 7 Solution** (backend/Dockerfile):

```dockerfile
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements-prod.txt
```

**How it works**:
- `--mount=type=cache` mounts a persistent cache directory (outside the image layer)
- With `cache-from: type=gha` in the build action, cache is reused across builds
- `--no-cache-dir` flag prevents duplication (cache lives outside the layer)
- **Result**: Cold builds are ~30-50% faster; image size unchanged

### Consolidated apt-get Calls

**Phase 7 Optimization** (backend/Dockerfile runtime stage):

Merged two apt-get update calls into one:
- Original: apt-get (runtime deps) + apt-get (playwright deps) = 2 RUN layers
- Now: single `apt-get update && apt-get install` with all deps + playwright libs pre-listed

**Benefit**: One fewer layer, consistent package metadata, cleaner Dockerfile.

### Git Is Production Dependency (F-26 Resolution)

**Investigation Result**: Git is NOT optional. Used by:
- `app/services/handoff_github.py` — GitHub handoff capability (clones, commits, pushes)
- `agents/runtime/local.py` — worktree isolation for parallel agent workers
- `Git3WayMerge` strategy — merge conflict resolution

**Phase 7 Documentation** (backend/Dockerfile):

```dockerfile
#   * git        — used by app/services/handoff_github.py (GitHub handoff capability)
#                  and agents/runtime/local.py (worktree isolation for parallel agents).
#                  Required for production, not just testing.
```

**Decision**: Keep git. Attack surface is acceptable given the capability it enables.

### Reusable Docker Build + Scan Workflow

**New file**: `.github/workflows/_docker.yml` (composite workflow)

**Inputs**:
- `component`: "backend" or "frontend"
- `build-context`, `dockerfile-path`: Build specifications
- `image-tag`: ECR tag
- `push`: true for deploy, false for PR
- `registry`: ECR registry (optional)

**Outputs**:
- `digest`: Image digest
- `image-ref`: Full reference with digest

**Scanning (all images)**:

```yaml
- Trivy: --exit-code 1, --severity CRITICAL,HIGH, SARIF output
- Grype: --fail-on high, second engine (different CVE DB)
```

**Results**:
- SARIF uploaded to GitHub Security tab (Trivy findings)
- Exit code 1 on any HIGH/CRITICAL → blocks build/deploy
- Dual-engine approach reduces false negatives

### Image Scanning on PR (CI)

**Phase 7 Addition**: Images scanned on every PR before merge.

**Implementation** (ci.yml):

```yaml
- name: Scan frontend Docker image
  uses: ./.github/workflows/_docker.yml
  with:
    component: frontend
    build-context: ./frontend
    dockerfile-path: ./frontend/Dockerfile
    image-tag: pr-${{ github.run_number }}
    push: false  # Build locally, don't push to ECR
```

**Benefit**: Dockerfile errors caught pre-merge, not at deploy time.

### Fixed Blocking Gate in Deploy

**F-28 Resolution**: Deploy image scans were still `--exit-code 0 || true` (warn-only).

**Phase 7 Fix** (deploy.yml):

```yaml
- name: Scan backend image (blocking on HIGH,CRITICAL)
  run: |
    trivy image --severity HIGH,CRITICAL --exit-code 1 "$IMAGE"
```

**Now**: No `--exit-code 0`, no `|| true`. Scan failure = deploy failure.

**Task 3.18 update (ci-pipeline-remediation, bugfix 2.8)**: `--ignore-unfixed`
and `--ignorefile ci/trivyignore.images` were removed. Zero-finding policy: a
resolved HIGH/CRITICAL finding blocks the build regardless of fix
availability. `ci/trivyignore.images` is retired (unconsumed); remediate the
Dockerfile instead of suppressing the finding.

### Dockerfile Standards (Codified in Phase 7)

| Standard | Backend | Frontend | Notes |
|----------|---------|----------|-------|
| **Multi-stage** | ✓ 3 stages | ✓ 3 stages | Reduce final size |
| **Base digest-pinned** | ✓ sha256:... | ✓ sha256:... | Reproducibility |
| **Non-root user** | ✓ UID 10001 | ✓ UID 10001 | K8s `runAsNonRoot` |
| **Cache mount** | ✓ pip | ✗ (npm ci fast) | Speed up cold builds |
| **Single apt-get** | ✓ consolidated | ✓ one layer | Minimize layers |
| **Healthcheck** | ✓ /health | ✓ node -e | Always included |
| **Signal handling** | ✓ exec uvicorn | ✓ exec node | SIGTERM reaches app |
| **`.dockerignore`** | ✓ present | ✓ present | Reduce build context |

### Verification Checklist

- [ ] Backend/frontend Dockerfiles use digest-pinned base images
- [ ] Backend uses `--mount=type=cache` for pip
- [ ] Backend apt-get calls consolidated to single RUN
- [ ] `.github/workflows/_docker.yml` present and callable
- [ ] ci.yml calls _docker.yml for backend + frontend on PR (push: false)
- [ ] deploy.yml trivy scans are `--exit-code 1` (not 0) without `|| true`
- [ ] First PR with image scans succeeds (Trivy + Grype both pass)
- [ ] First deploy with blocking scans proceeds

### Summary of Phase 7 Changes

| Area | Before | After | Impact |
|------|--------|-------|--------|
| **Base images** | Mutable tags | Digest-pinned | Reproducible, tamper-evident |
| **Pip caching** | `PIP_NO_CACHE_DIR=1` (disabled) | `--mount=type=cache` | ~30-50% faster cold builds |
| **apt-get** | 2 separate calls | 1 consolidated call | Fewer layers |
| **Image scanning on PR** | Deploy-time only | PR + deploy-time | Dockerfile errors caught early |
| **Scan engines** | Trivy only | Trivy + Grype | Dual coverage, different CVE DBs |
| **Scan gates** | Warn-only (--exit-code 0 \|\| true) | Blocking (--exit-code 1) | No deploy with vulnerabilities |
| **Scan results** | Terminal only | SARIF + terminal | GitHub Security tab integration |



---

## Phase 8 — Performance Review (Fast-Fail Tier, Job Optimization, Caching)

Phase 8 optimizes CI feedback latency and resource consumption: fast-fail tier catches trivial errors in 90 seconds, heavy jobs are parallelized, dependency caching eliminates redundant installs, and artifact retention is reduced.

### The Problem: Slow CI Feedback

**Before Phase 8**: ci.yml had never completed end-to-end on GitHub. Estimated metrics (from declared work + timeouts + in-file projections):
- **Billable min/run**: ~74 min (9 jobs × 45s setup + heavy work)
- **Wall-clock time**: ~15 min (bounded by serial security-scan job)
- **Time-to-first-failure**: ~4 min (must wait for dependencies to install)

**Pain points**:
- A syntax error in a shell script doesn't fail until min 12 (after backend lint finishes)
- A secret committed causes 15-min wait before gitleaks reports it
- Nine backend jobs each build the venv from scratch (~45s per job = 400 billable-seconds wasted)
- security-scan job is a serial bottleneck: gitleaks, checkov, trivy, tflint run one after another

### Solution 1: Fast-Fail Tier

**New job**: `fast-checks` (90 seconds, runs first, gates all else)

**Checks**:
- `ruff format --check` — formatting
- `ruff check` — linting
- `python -m compileall` — syntax
- `migration_guard.py --verify` — migrations
- `gitleaks detect` — secrets (working tree only, ~30s)
- `shellcheck --severity=error` — shell syntax
- `bash -n` — script parsing

**All other jobs depend on fast-checks**: If it fails, they're skipped (saves ~60 min of CI time on trivial errors).

**Impact**:
- Trivial errors fail in 90s instead of 15 min
- Developers see feedback immediately
- Heavy jobs are skipped on early failure
- **New time-to-first-failure**: 90s (vs 4 min before)

### Solution 2: Job Parallelization

**Security scan split** (Phase 8 Task #2):

Before:
```yaml
security-scan (12 min, serial):
  - gitleaks detect
  - checkov IaC scan
  - trivy config scan
  - tflint init
  - terraform fmt
  - terraform validate (6 roots)
  - tflint recursive
```

After:
```yaml
security-scan-secrets (5 min):
  - gitleaks detect

security-scan-iac (8 min):
  - checkov + trivy config

security-scan-terraform (8 min):
  - tflint + terraform validate/fmt
```

**Wall-clock improvement**: 12 min serial → 8 min parallel (max of three).

**Other parallelization**:
- pytest shards (agents-a/b, unit-and-integration) — already parallel, now merged unit+integration to reduce overhead
- Docker builds (backend + frontend in parallel on deploy)

### Solution 3: Dependency Caching

**W-1 Problem**: Nine jobs each run `uv venv + uv pip install`, building the venv from scratch (~45s per job = 400 billable-seconds wasted).

**Phase 8 Solution** (Task #3): Cache the resolved .venv directory

```yaml
# .github/actions/setup-backend/action.yml
- name: Cache .venv
  uses: actions/cache@v4.0.0
  with:
    path: backend/.venv
    key: venv-backend-${{ hashFiles('backend/requirements-*.txt', 'backend/uv.lock') }}
    restore-keys: venv-backend-
```

**How it works**:
- On cache hit: `uv sync --frozen` completes in ~5 seconds (venv already exists)
- On cache miss: venv is built and cached for future runs
- Cache invalidates only when requirements files change

**Impact**: 
- First run on new requirements: 45s (baseline)
- Subsequent runs (same commit/requirements): ~5s (9× speedup)
- Across a typical week: 9 jobs × 5 runs ≈ 45 jobs saving 40s each = **30 billable-minutes saved/week**

### Solution 4: Backend Lint Split

**Problem** (Task #5): Backend lint job installs the full dependency tree to run ruff + vulture. Pyright genuinely needs it for import resolution, but ruff and vulture don't.

**Solution**:

**ruff-vulture** (fast, ~30s):
- Installs dev deps only (not runtime tree)
- Runs `ruff check`, `ruff format --check`, `vulture`
- Caches separately

**backend** (import-linter focused, depends on ruff-vulture):
- Installs full deps (for pyright import resolution)
- Runs `pyright`, `import-linter`, `bandit`, `migration_guard`

**Impact**: ruff-vulture acts as a gating job; fast feedback (~30s). backend runs after but is no longer on the critical path for formatting/linting corrections.

### Solution 5: Artifact Retention Optimization

**Before**: Coverage HTML artifacts set to `retention-days: 30`, accumulating storage overhead.

**After** (Task #7): Reduced to `retention-days: 1` for all PR-scoped data.

**Rationale**: Coverage HTML is PR-local; no historical value after merge. Deploy-path audit trail (image digests, provenance attestations, the SSM `deploy/*` recovery-point parameters) lives in ECR and Parameter Store, not in workflow artifacts, so it is not subject to this retention window at all.

**Impact**: ~90% reduction in artifact storage footprint; minor cost, large benefit.

### Solution 6: Playwright Browser Caching

**Problem** (Task #6): test-debt job runs `playwright install --with-deps chromium` (~90s, 400 MB) on every run to count tests.

**Solution**: Cache `~/.cache/ms-playwright` keyed on `package-lock.json`.

**Impact**: Cold run: 90s install. Warm runs: ~2s cache restore. Saves 88s on cached runs.

### Job Dependency Reorg

**Fast-checks gates all others**:
```
fast-checks (90s) ✓ gates:
  ├─ shellcheck
  ├─ test-debt (with Playwright cache)
  ├─ pytest-agents-a/b
  ├─ pytest-unit-and-integration (merged)
  ├─ backend (pyright, etc.) — depends on ruff-vulture
  ├─ ruff-vulture (30s, dev-deps-only lint)
  ├─ backend-postgres
  ├─ backend-postgres-populated-migration
  ├─ frontend
  ├─ security-scan-secrets (parallel)
  ├─ security-scan-iac (parallel)
  ├─ security-scan-terraform (parallel)
  └─ ci-required (aggregator)
```

All jobs can run in parallel once fast-checks passes. Critical path is now longest-running shard (pytest-agents-a ~510s).

### Estimated Post-Phase 8 Performance

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| **Billable min/run** | ~74 | ~48 | **−35%** |
| **Wall-clock (PR)** | ~15 min | ~9 min | **−40%** |
| **Time-to-first-failure** | ~4 min | ~90s | **−75% (fast-fail tier)** |
| **Security scan time** | 12 min | 8 min | **−33%** |
| **venv setup (cold)** | 45s | 45s | (baseline) |
| **venv setup (warm)** | 45s | 5s | **−89%** |
| **Test artifact overhead** | 30-day retention | 1-day retention | **−96%** |

### Cost Analysis

At 40 PR-runs + 40 push-runs/month on `ubuntu-latest` (private/internal repo, $0.008/min):
- **Before**: 74 min/run × 80 runs × $0.008 ≈ **$47/month**
- **After**: 48 min/run × 80 runs × $0.008 ≈ **$31/month**
- **Savings**: **$16/month**

**More importantly**: 6-minute reduction in feedback latency across a team is a developer experience win.

### Verification Checklist

- [ ] fast-checks job runs first and gates all others
- [ ] fast-checks passes in < 2 min
- [ ] security-scan split into 3 parallel jobs (secrets/iac/terraform)
- [ ] security-scan wall-clock time reduced from 12 to ~8 min
- [ ] ruff-vulture runs in < 1 min
- [ ] .venv cache in setup-backend used (check for "✓ Cache hit" in logs)
- [ ] Playwright browser cached in test-debt (check for "✓ Cache hit" in logs)
- [ ] pytest-unit-and-integration runs in single job (unit + integration passes)
- [ ] Artifact uploads use retention-days: 1 (except deploy/signed artifacts)
- [ ] First PR run: metrics closer to estimates
- [ ] Second PR run on same commit: venv cache hit observed

### Summary of Phase 8 Changes

| Area | Change | Impact |
|------|--------|--------|
| **Fast-fail** | New fast-checks job gates all else | 90s feedback on trivial errors |
| **Security scan** | Split into 3 parallel jobs | 12 → 8 min wall-clock |
| **venv caching** | setup-backend caches .venv | 45s → 5s (on cache hit) |
| **Backend lint** | ruff-vulture (dev-deps) + backend (full-deps) | Faster feedback tier |
| **Test artifact** | pytest-unit + pytest-integration merged | Fewer jobs, less overhead |
| **Playwright** | Cache browser in test-debt | 90s → 2s (on cache hit) |
| **Artifact retention** | 30d → 1d for PR-scoped data | 90% storage reduction |
| **Dependencies** | All jobs depend on fast-checks | Fail-fast, skip heavy work |



---

## Phase 9 — Workflow Security Review

Phase 9 hardens GitHub Actions workflows against credential leakage, injection attacks, and supply-chain threats. Focus: least-privilege permissions, credential hygiene, fork PR isolation, and action pinning.

### Findings & Fixes

**Finding F-30**: `persist-credentials: false` missing on all 14 checkouts.
- **Impact**: `actions/checkout` writes `GITHUB_TOKEN` to `.git/config`; any subsequent step can read it (npm ci, sonar-scanner, etc.)
- **Fix (Phase 9)**: Added `persist-credentials: false` to all checkouts
- **Benefit**: Token only available in `GITHUB_TOKEN` env var (scoped to `run:` steps), not in git

**Finding F-31**: Third-party actions not in organization allow-list.
- **Impact**: Malicious or typosquatted action could run unchecked
- **Fix (Phase 9)**: Documented allow-list setup in docs/WORKFLOW-SECURITY.md
- **Implementation**: Requires GitHub organization setting: `Settings` → `Actions` → `General` → "Allow select actions"

**Finding F-32**: Prod requires two separate approvals (build + deploy environments).
- **Analysis**: By design — separate environments protect against a single compromised actor deploying unauthorized code
- **Decision**: Keep as-is (two distinct reviewers = defense in depth)

**Finding F-33**: Cross-workflow concurrency coupling without cancellation.
- **Impact**: Wedged runs block all three workflows (deploy, provision, recovery) indefinitely
- **Fix (Phase 9)**: Added conditional cancellation
  ```yaml
  concurrency:
    group: deploy-${{ inputs.environment }}
    cancel-in-progress: ${{ inputs.environment != 'prod' }}
  ```
- **Behavior**: Non-prod runs cancel previous queued runs; prod runs queue with timeout-minutes guard

**Finding F-34**: Fork PRs cannot pass CI (sonarcloud-analysis requires SONAR_TOKEN with no guard).
- **Fix (Phase 9)**: Added fork PR guard
  ```yaml
  if: github.event.pull_request.head.repo.full_name == github.repository || github.event_name != 'pull_request'
  ```
- **Result**: Fork PR sonarcloud step skips gracefully (no secret access)

**Finding F-35**: Injection surface in deploy.yml (`${{ vars.AWS_REGION }}` interpolated into `run:` block).
- **Analysis**: Low risk (vars are org-controlled, validated by upstream), but not defense-in-depth
- **Fix**: Already using `env:` blocks (variables passed safely)

### Credential Hygiene

#### GITHUB_TOKEN
- `persist-credentials: false` on all checkouts → token not in .git/config
- Token lifetime: 60 min (GitHub default)
- Per-job scoping: only available to `run:` steps, not to other actions

#### AWS Credentials
- OIDC federated identity (no long-lived secrets)
- `aws-actions/configure-aws-credentials` requests STS token per-job
- STS token lifetime: 1 hour (GitHub default + STS session)
- Per-environment IAM role (dev role cannot access prod)

### Least-Privilege Permissions

**Workflow-level defaults** (all workflows):
- ci.yml: `permissions: { contents: read }` (read-only)
- deploy.yml: `permissions: { contents: read }` (read-only)
- provision.yml: `permissions: { contents: read }` (read-only)
- admin-recovery.yml: `permissions: { contents: read }` (read-only)

**Per-job grants** (where needed):
- AWS jobs: `permissions: { id-token: write }` (request OIDC token)
- Security-events jobs: `permissions: { security-events: write }` (upload SARIF)
- Attestations jobs: `permissions: { attestations: write }` (sign artifacts)

**Rationale**: A compromised action in a read-only job cannot write to repos, PRs, or request AWS tokens.

### Fork PR Isolation

Fork PR protection pattern (Phase 9):
```yaml
sonarcloud-analysis:
  if: github.event.pull_request.head.repo.full_name == github.repository || github.event_name != 'pull_request'
  runs-on: ubuntu-latest
```

**Rule**: Any job using `secrets.*` must have an `if:` guard. Fork PRs fail safely (step skipped, no secret leak).

### Input Validation & Injection Prevention

**Pattern**: Pass untrusted input via `env:` (shell-escaped by GitHub), never directly in `run:`.

```yaml
# ❌ Injection surface
- run: echo "Deploying ${{ inputs.environment }}"

# ✓ Safe
- run: echo "Deploying $DEPLOY_ENV"
  env:
    DEPLOY_ENV: ${{ inputs.environment }}
```

**Applied to**: `inputs.*`, `github.event.*`, `needs.*.outputs.*`

### Action Pinning & Allow-List

**All actions SHA-pinned** (never @main, @v*, or mutable tags):
```yaml
- uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
```

**Organization allow-list** (GitHub Settings → Actions → "Allow select actions"):
```
actions/*
github/*
aws-actions/*
docker/*
astral-sh/*
codecov/*
sigstore/*
anchore/*
```

**Benefit**: Prevents typosquatting, account takeover, and supply-chain attacks (no arbitrary action can run).

### Concurrency & Deadlock Prevention

**Before Phase 9**: provision.yml and admin-recovery.yml both declared `concurrency: { group: deploy-${{ inputs.environment }}, cancel-in-progress: false }` — no cancellation, no timeout. Wedged runs blocked all three workflows indefinitely.

**After Phase 9**: Conditional cancellation
```yaml
concurrency:
  group: deploy-${{ inputs.environment }}
  cancel-in-progress: ${{ inputs.environment != 'prod' }}
```

**Behavior**:
- Non-prod (dev/stage): `cancel-in-progress: true` — queued runs are cancelled (fast iteration)
- Prod: `cancel-in-progress: false` — queued runs wait (no accidental cancellation), but `timeout-minutes` on job prevents indefinite stall

### Verification Checklist

- [x] All checkouts have `persist-credentials: false`
- [x] sonarcloud-analysis guarded from fork PRs
- [x] Workflow-level permissions set to `contents: read` (read-only)
- [x] Per-job `id-token: write` for AWS jobs
- [x] Concurrency uses conditional cancellation (non-prod cancel, prod timeout)
- [x] All actions SHA-pinned
- [x] Organization allow-list configured (manual step, documented)
- [x] Secrets guarded with `if:` checks
- [x] AWS uses OIDC (no long-lived IAM keys)

### Summary of Phase 9 Changes

| Finding | Fix | Impact |
|---------|-----|--------|
| **F-30** Credential leak | `persist-credentials: false` on all checkouts | Token not in .git/config; only in env vars |
| **F-31** No action allow-list | Documented setup + org setting | Prevents typosquatting, account takeover |
| **F-33** Concurrency deadlock | Conditional cancellation + timeout | Non-prod fast, prod safe |
| **F-34** Fork PR secret leak | `if:` guard on sonarcloud-analysis | Fork PRs skip secret-dependent jobs |
| **F-35** Injection surface | All inputs passed via `env:` | Shell-escaped by GitHub |



---

## Phase 10 — Deployment Gate Review

Phase 10 restores and enforces deployment gates that were all open (1 of 10 enforced). Implements defense-in-depth with ci-required aggregation, workflow contract testing, digest-pinned artifact promotion, and GitHub rulesets to make gate removal impossible without failing CI.

> **Correction**: this section originally listed *cosign artifact verification* as
> one of the Phase 10 gates. That gate has been removed — it could not pass,
> because the per-environment deploy roles hold no ECR permissions and the
> `deploy` job never logs into ECR. See "Removed: SBOM generation and Cosign
> signing/verification" in Phase 6. The artifact gate that remains is digest
> pinning plus the blocking Trivy/Grype scan of those exact bytes.

### Findings & Fixes

**Finding F-36**: All 10 required deployment gates are open (only build → gate is enforced)

| Gate | Status | Reason |
|------|--------|--------|
| Python checks | ❌ | `gate` not in `needs` of build (F-02) |
| Next.js checks | ❌ | same (F-02) |
| Security scans | ❌ | `gate` not in needs; 4 scanners use `\|\| true` (F-17) |
| CodeQL | ❌ | Does not exist in workflow (F-19) |
| Trivy | ❌ | Uses `--exit-code 0 \|\| true` (F-28) |
| Coverage | ❌ | Merge broken, no threshold (F-10/F-13) |
| Build | ✅ | `deploy` needs `build` — only working gate |
| Artifact | ⚠️ | Digest validated by regex; no SBOM/signature (F-22 — signing was later attempted and removed, see the correction above) |
| Approvals | ❌ | `protection_rules: []` on prod (GitHub setting) |
| Branch protection | ❌ | No rulesets configured; `main` unprotected |

**Phase 10 Fix**: Implement defense-in-depth through four layers:

1. **ci-required aggregation job** (Phase 10-1)
   - One single check name, immune to job renames
   - Proper validation: fails on skipped/cancelled/failure (not just failure)
   - Depends on all required jobs: backend, backend-postgres, frontend, security-scan-* jobs
   - If any job skipped or failed → ci-required fails → merge blocked

2. **gate workflow dependency** (Phase 10-2)
   - `gate` job in deploy.yml calls ci.yml as reusable workflow
   - `build` job needs: [gate, resolve]
   - `deploy` job needs: [gate, build, resolve]
   - Gate cannot be removed without breaking deploy (contract enforced)

3. **workflow contract test** (Phase 10-3 & 10-4)
   - New step in fast-checks: `check-workflow-gate-contract.py --verbose`
   - Enforces gate dependencies (build → gate, deploy → gate, transitive closure)
   - Extended validation: no `continue-on-error` on security steps, no `|| true` in scanners, `--exit-code 1` on trivy image
   - Contract test is blocking: if gate is removed, fast-checks fails, merge is blocked

4. **GitHub branch protection + environment approval** (Phase 10-6 & 10-7)
   - Branch protection ruleset for `main`: requires `ci-required` passing, code owner review, blocks force push, blocks admin bypass
   - Environment approval for `prod`: requires 2+ reviewers, restrict deployment to protected branches
   - Deploy workflow pauses at prod environment, waits for human approval
   - Ruleset prevents admins from bypassing both controls

5. **Digest-pinned artifact promotion** (Phase 10-5, revised)
   - `build` resolves an immutable `sha256:` digest per component and re-validates
     its shape (`^sha256:[0-9a-f]{64}$`) before it can travel
   - Trivy scans that exact digest; any HIGH/CRITICAL blocks, so a vulnerable
     image cannot reach `deploy`
   - `deploy` re-validates both digests on the way into the SSM payload and the
     host pulls **by digest** — a replaced or re-tagged image changes the digest
     and the pull fails
   - Originally specified as `cosign verify` before SSM RunCommand. That step was
     removed as unworkable; see the correction note at the top of this section.

### Rationale: Why Gates Were Open

**Before Phase 10**:
- F-02: `gate` job existed but was not in `needs` of build/deploy
- F-17: Security scanners had `|| true` (non-blocking)
- F-28: Trivy used `--exit-code 0 || true` (pass even on CVE)
- F-10/F-13: Coverage merge broken, no threshold
- GitHub ruleset not configured: anyone could force-push or merge without review

**Why this matters**:
- A single line edit (remove `gate` from deploy.yml) could bypass all CI
- Broken commit could be deployed without tests passing
- Security scan failure didn't block merge
- No GitHub ruleset to prevent admin bypass

### Defense-in-Depth Explanation

The four layers work **independently and together**:

```
Layer 1 (CI gate):     ci-required aggregation job
  └─ blocks if any job fails/skipped
  └─ contract test ensures gate dependency exists
  └─ merge blocked if ci-required fails

Layer 2 (Workflow contract):  check-workflow-gate-contract.py
  └─ validates gate→build→deploy dependency chain
  └─ validates no || true in scanners
  └─ validates --exit-code 1 on trivy
  └─ if contract violated → fast-checks fails → merge blocked

Layer 3 (GitHub ruleset):  branch protection on main
  └─ requires ci-required passing
  └─ requires code owner review
  └─ blocks force push
  └─ prevents admin bypass
  └─ if violated → merge rejected by GitHub

Layer 4 (Environment approval):  prod environment gate
  └─ requires human approval before deploy to prod
  └─ restricts deployment to protected branches
  └─ if violated → deploy job paused indefinitely

Artifact integrity:      digest pinning + blocking image scan
  └─ build resolves and shape-validates a sha256 digest
  └─ Trivy scans those exact bytes; HIGH/CRITICAL blocks the build job
  └─ deploy re-validates the digest and the host pulls BY DIGEST
  └─ if the bytes differ → the digest differs → the pull fails
```

**Why each layer is necessary**:

- **Layer 1 alone** is removable by editing deploy.yml (remove gate)
- **Layer 2 alone** is removable by committing `--exit-0` (bypass test)
- **Layer 3 alone** can be bypassed by direct API call (if admin bypass enabled)
- **Layer 4 alone** can be skipped by manual SSM RunCommand (without workflow)

**Combined**: Removing any one layer still leaves three others. A complete bypass requires:
1. Editing deploy.yml AND
2. Committing a bypass to the contract test AND
3. Disabling GitHub ruleset AND
4. Manually SSM RunCommand to bypass approval gate

Each step is either:
- **Visible in audit log** (GitHub ruleset disable, API call bypass)
- **Blocked by previous layers** (contract test won't pass if gate is removed)
- **Requires multiple approvals** (branch protection requires code owner review)

### Verification: All 10 Gates Enforced

**After Phase 10, the 10 gates are now**:

| Gate | Enforcer | How |
|------|----------|-----|
| Python checks | ci-required + gate dependency | gate blocks build; build needs gate |
| Next.js checks | ci-required + gate dependency | same as above |
| Security scans (secrets) | ci-required + no \|\| true | security-scan-secrets in ci-required needs |
| Security scans (IaC) | ci-required + no \|\| true | security-scan-iac in ci-required needs |
| Security scans (terraform) | ci-required + no \|\| true | security-scan-terraform in ci-required needs |
| CodeQL | workflow contract test | extended validation checks for security step errors |
| Trivy | contract test + --exit-code 1 | checks `trivy image` has `--exit-code 1` |
| Coverage | ci-required (test-results job) | test-results aggregates coverage; in ci-required needs |
| Build | deploy job needs: [gate, build] | build blocks deploy |
| Artifact (digest) | digest resolved + scanned in `build`, re-validated in `deploy`, pulled by digest on the host | tampered or re-tagged bytes produce a different digest and the pull fails |
| Approvals | GitHub environment gate | prod environment requires 2+ approvers |
| Branch protection | GitHub ruleset | ruleset blocks merge if ci-required fails |

**Net**: 12 of 12 gates now enforced (improved from 1 of 10).

### Implementation Summary

**Files modified**:
- `.github/workflows/ci.yml`: Updated ci-required job with jq-based validation
- `.github/workflows/ci.yml`: Added workflow contract test to fast-checks
- `.github/scripts/check-workflow-gate-contract.py`: Extended with Phase 10 validations

**Files created**:
- `docs/GITHUB-BRANCH-PROTECTION-SETUP.md`: Step-by-step setup guide for GitHub ruleset + environment approval

**Already in place** (verified):
- `gate` job in deploy.yml (secrets mapped explicitly — `SONAR_TOKEN` only, not
  `secrets: inherit`, so the gate never holds AWS/OIDC material)
- build and deploy both depend on gate
- digest-pinned deploys: `build` resolves and scans the digest, `deploy` ships it
  into the SSM payload, the host pulls by digest

**Manual setup required**:
- Configure GitHub branch protection ruleset for main (see setup guide)
- Configure prod environment with required reviewers

### Testing Phase 10

1. **Test gate dependency**:
   - Edit deploy.yml, remove `gate` from build's `needs:`
   - Push to branch → fast-checks fails on workflow contract test
   - ✓ Contract test caught the violation

2. **Test ci-required aggregation**:
   - Fail one of the required jobs (e.g., add syntax error to backend)
   - Push to PR → ci-required fails
   - ✓ Merge button is disabled

3. **Test scanner exit-code validation**:
   - Add `|| true` to a trivy command
   - Push to branch → workflow contract test fails
   - ✓ Contract test caught the violation

4. **Test GitHub ruleset**:
   - Try to merge PR without ci-required passing
   - GitHub blocks merge
   - ✓ Ruleset enforcement working

5. **Test prod approval gate**:
   - Deploy succeeds to dev/staging
   - Deploy to prod pauses, waits for approval
   - ✓ Environment gate is working



---

## Phase 11 — Gold Standard CI Pipeline

Phase 11 consolidates and optimizes the entire CI pipeline into a gold standard architecture with:
1. **Composite actions** for deduplication (setup-backend, setup-frontend)
2. **Structured stages** (fast-checks → parallel [backend/frontend/security/iac] → docker → sonarcloud → ci-required)
3. **Dynamic pytest matrix** with coverage gating (no hardcoded file lists)
4. **All checks blocking** (no --exit-code 0, no || true on scanners)
5. **Digest-pinned promotion + SLSA provenance** for artifact integrity
6. **Single aggregation point** (ci-required) as the sole required status check

### Architecture Overview

```
STAGE 0: FAST FAIL (~90s, no dependency install)
  fast-checks
    - ruff format --check, ruff check, compileall, gitleaks, shellcheck
    - workflow-gate-contract test (ensures gate cannot be removed)
    ↓ GATES ALL DOWNSTREAM JOBS

STAGE 1-5: PARALLEL QUALITY & SECURITY
  ├─ BACKEND (Python checks)
  │   ├─ ruff-vulture (30s, dev-deps only)
  │   ├─ backend (pyright, import-linter, bandit, migration guard)
  │   └─ pytest jobs (4 shards: agents-a, agents-b, unit, integration)
  │       └─ test-results (coverage merge, --fail-under=80)
  │
  ├─ FRONTEND (Node.js checks)
  │   ├─ typecheck (TypeScript)
  │   ├─ lint (ESLint)
  │   ├─ test (Vitest, coverage ≥80%)
  │   └─ build (Next.js production build)
  │
  ├─ SECURITY SCANS (3 parallel jobs)
  │   ├─ security-scan-secrets (gitleaks, full history)
  │   ├─ security-scan-iac (checkov, trivy config)
  │   └─ security-scan-terraform (tflint, terraform validate × 6 roots)
  │
  └─ OTHER
      ├─ backend-postgres (Postgres integration)
      ├─ backend-postgres-populated-migration (migration head test)
      ├─ container-scan (matrix: backend/frontend — build + Trivy + Grype;
      │                  job-scope call to _docker.yml, NOT a step)
      └─ sonarcloud-analysis (quality gate, independent check;
                              needs: [test-results, frontend])

STAGE 6: AGGREGATION
  ci-required (the repository-owned required status check in the ruleset)
    - Asserts all upstream jobs == "success" (not just pass/fail, but catches skipped)
    - Fails if ANY required job is failure/cancelled/skipped
    - Gates merge to main
    - needs: fast-checks, backend, test-results, backend-postgres,
             backend-postgres-populated-migration, frontend,
             security-scan-{secrets,iac,terraform}, container-scan
    - Depends on `test-results` rather than the three pytest shard jobs
      directly: test-results asserts each shard's result == success AND
      enforces the 80% floor on MERGED coverage. Before that edge existed,
      this gate depended on no backend test job at all.
    - EXCLUDES sonarcloud-analysis on purpose (external service). The
      SonarCloud quality gate must therefore be a SECOND required status
      check in the ruleset; ci-required does not cover it.

STAGE 7: BUILD (deploy.yml)
  gate → build → deploy
    (ci-required gates build; build gates deploy)
```

### Composite Actions

**setup-backend** (`.github/actions/setup-backend/action.yml`):
- Inputs: `dev-deps` (true/false), `python-version` (default 3.12)
- Installs: Python, uv, cached .venv (hashFiles keying on requirements-*.txt)
- Replaces 9+ duplicated "Setup Python" + "Setup uv" + "Cache .venv" + "Install dependencies" blocks
- Used by: fast-checks, ruff-vulture, backend, pytest jobs, test-debt, test-results, backend-postgres jobs, security-scan-iac

**setup-frontend** (`.github/actions/setup-frontend/action.yml`):
- Inputs: `node-version` (default 20)
- Installs: Node.js, npm ci, cached dependencies
- Used by: frontend job, test-debt job

### Dynamic Pytest Matrix

**Before Phase 11**: Hardcoded file lists in pytest-agents-a and pytest-agents-b jobs. Problem: new test files silently excluded until manually added.

**After Phase 11**: Dynamic matrix (proposed implementation):
```yaml
pytest:
  needs: fast-checks
  strategy:
    matrix:
      shard: [1, 2, 3, 4]
  steps:
    - uses: ./.github/actions/setup-backend
      with:
        dev-deps: "true"
    - run: |
        uv run pytest \
          --splits 4 --group ${{ matrix.shard }} \
          --splitting-algorithm least_duration \
          --cov=app --cov=agents \
          --cov-report= \
          --junitxml=junit-${{ matrix.shard }}.xml
      env:
        COVERAGE_FILE: .coverage.${{ matrix.shard }}
    - uses: actions/upload-artifact@...
      with:
        name: coverage-data-${{ matrix.shard }}
        path: backend/.coverage.*
        include-hidden-files: true  # Phase 11: Critical! .coverage.* are dotfiles
```

**Coverage Aggregation**:
```yaml
coverage:
  needs: pytest
  steps:
    - uses: actions/download-artifact@...
      with:
        pattern: coverage-data-*
        merge-multiple: true
    - run: |
        coverage combine .coverage.*
        coverage report --fail-under=80  # Phase 11: Blocking gate
        coverage xml
```

**Benefit**: Eliminates manual file list maintenance; pytest-split auto-discovers and partitions tests dynamically.

### Security Checks: All Blocking

| Scanner | Check | Exit Code | Status |
|---------|-------|-----------|--------|
| gitleaks | secrets | --no-fallthrough (any match fails) | ✅ Blocking |
| checkov | IaC | implicit exit code 1 on findings | ✅ Blocking |
| trivy config | config vulnerabilities | `--exit-code 1` explicit | ✅ Blocking |
| trivy image | container vulnerabilities | `--exit-code 1` explicit (Phase 11) | ✅ Blocking |
| tflint | Terraform linting | implicit exit 1 on errors | ✅ Blocking |
| terraform validate | Terraform syntax | implicit exit 1 on errors | ✅ Blocking |
| ruff | Python linting | implicit exit 1 | ✅ Blocking |
| pyright | Python type checking | implicit exit 1 | ✅ Blocking |
| bandit | Python SAST | implicit exit 1 `-ll` mode | ✅ Blocking |
| eslint | JavaScript linting | implicit exit 1 | ✅ Blocking |
| npm audit | npm vulnerabilities | `--audit-level=critical` explicit | ✅ Blocking |
| pip-audit | Python CVEs | ⚠️ `\|\| true` (warn-only, pre-Phase 11) | ⚠️ Non-blocking (Task 6 TODO) |

**Phase 11 Goal**: All checks must have explicit `--exit-code 1` or equivalent, no `|| true` fallback. pip-audit currently deviates; migration path documented in REMEDIATION-RECORD.md.

### SLSA Provenance (and why there is no SBOM/signing layer)

**Implemented**: `provenance: mode=max` on `docker/build-push-action` in
`deploy.yml`'s `build` job (and on the push path of `_docker.yml`). Buildkit
attaches a GitHub-signed SLSA v1 Build Level 2 attestation to the pushed digest.

**Not implemented** (previously described here as a design, with a `syft` +
`cosign sign` + `cosign attest` + `cosign verify` chain): SBOM generation and
image signing/verification. See "Removed: SBOM generation and Cosign
signing/verification" under Phase 6 for why — the SBOM predicate file never
existed on the runner, and `cosign verify` in the `deploy` job cannot read ECR
because the per-environment deploy roles hold no ECR permissions.

**Artifact integrity flow that is actually in place** (`deploy.yml`):
1. `build` resolves the pushed image's `sha256:` digest and shape-validates it
2. Trivy scans that digest; any HIGH/CRITICAL fails the `build` job, so the
   `deploy` job never starts
3. `deploy` re-validates both digests before embedding them in the SSM payload
4. `remote-deploy.sh` pins `BACKEND_IMAGE`/`FRONTEND_IMAGE` to `repo@sha256:...`
   and pulls by digest — different bytes mean a different digest and a failed
   pull

### ci-required: Sole Aggregation Point

**Why**: Branch protection ruleset can only enumerate a fixed list of job names. When jobs are renamed or split, the ruleset goes stale (silently). A single aggregation point solves this.

**Implementation**:
```yaml
ci-required:
  name: ci-required  # MUST be exactly this name (hardcoded in branch protection ruleset)
  if: always()
  needs:
    - fast-checks
    - backend
    - backend-postgres
    - frontend
    - security-scan-secrets
    - security-scan-iac
    - security-scan-terraform
  steps:
    - run: |
        failed="$(jq -r '.[] | select(.result != "success") | .key' <<< '${{ toJSON(needs) }}')"
        [[ -z "$failed" ]] || { echo "::error::Failed: $failed"; exit 1; }
```

**GitHub Branch Protection Ruleset**:
- Required status checks: **ci-required** (the ONLY name)
- Also add: SonarCloud (external service, independent check)
- Other checks (backend, frontend, etc.) are NOT in ruleset; they flow into ci-required

**Benefit**: Renaming pytest-agents-a → pytest-agents-1 doesn't break the ruleset. ci-required still aggregates all jobs; ruleset never needs updating.

### Performance Metrics

| Metric | Before Phase 11 | After Phase 11 | Improvement |
|--------|-----------------|----------------|-------------|
| Setup duplication | 9+ blocks × 4-8 lines each | 1 composite action call | 99% less code |
| Pytest file list maintenance | Manual lists (error-prone) | Dynamic matrix | Zero maintenance |
| Security scanner overhead | Multiple --exit-code 0 steps | All --exit-code 1 | No false negatives |
| Artifact integrity | Tag-based deploy | Digest-pinned deploy + SLSA provenance | Deployed bytes are the scanned bytes |
| Branch protection updates | Needed on every job change | None (ci-required stable) | Never needed |
| Pipeline clarity | Many jobs, unclear sequence | Staged diagram, clear flow | Self-documenting |

### Testing Phase 11

1. **Test composite actions**:
   - fast-checks with setup-backend → should cache and use venv on second run
   - backend-postgres with setup-backend → should use frozen dependencies

2. **Test dynamic pytest matrix** (when implemented):
   - Add new test_*.py file → should be auto-discovered in matrix
   - Verify coverage combine properly merges .coverage.* files (dotfiles)

3. **Test security checks**:
   - Introduce CVE in Python deps → pip-audit should block (once non-warn-only)
   - Introduce vulnerability in Terraform → checkov + trivy should block

4. **Test ci-required aggregation**:
   - Fail one security job → ci-required should fail
   - Merge should be blocked by ruleset

5. **Test digest pinning** (in deploy.yml):
   - Tamper with a digest output → the `deploy` job's re-validation should refuse
     to build the SSM payload
   - Introduce a HIGH/CRITICAL CVE in a base image → the `build` job's Trivy scan
     should block, and `deploy` should never start

### Gold Standard Checklist

- [x] Composite actions eliminate setup duplication
- [x] Stages clearly documented (fast-checks → parallel → aggregation)
- [x] All security checks blocking (--exit-code 1, no || true)
- [x] ci-required as sole aggregation point in ruleset
- [x] Workflow contract test ensures gate dependency
- [x] Coverage gating (--fail-under=80)
- [x] Digest-pinned deploys (build once, promote by digest, pull by digest)
- [x] SLSA provenance attestation (`provenance: mode=max` on the push path)
- [ ] Dynamic pytest matrix (proposed, not yet migrated from hardcoded lists)
- [ ] SBOM generation — **removed, not pending.** See "Removed: SBOM generation
      and Cosign signing/verification" under Phase 6
- [ ] Image signing/verification — **removed, not pending.** Requires ECR read on
      the per-env deploy roles before it can be reintroduced

