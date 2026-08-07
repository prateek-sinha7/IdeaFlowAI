# Flowin Execution, Quality Gates, and Failure Triage

Load this reference before running commands, choosing validation breadth, or diagnosing a failure.

## 1. Execution invariants

- Platform is Windows with PowerShell.
- Never use `cd`; set the command working directory.
- Backend commands run with `cwd: backend/` and start with `uv run` unless installing the already-pinned requirements.
- Frontend commands run with `cwd: frontend/` and use `npm` only.
- Use single-pass commands. Never start dev servers, watchers, interactive tools, `uvicorn --reload`, `next dev`, or `next start`.
- Do not install a missing test/scanner dependency merely to complete a checklist. Report the missing prerequisite and ask before changing dependencies or downloading tooling.
- Do not expose values from `backend/.env`, state, logs, traces, screenshots, or test artifacts.

## 2. Command matrix

Choose the narrowest command that proves the target, then broaden according to risk and blast radius.

### Backend

| Purpose | Working directory | Command |
|---|---|---|
| One test | `backend/` | `uv run pytest tests/path/test_file.py::test_name -v` |
| One file | `backend/` | `uv run pytest tests/path/test_file.py -v` |
| Feature/folder | `backend/` | `uv run pytest tests/unit/ -v` or the relevant folder |
| Full backend suite | `backend/` | `uv run pytest tests/ -v` |
| Python syntax/import bytecode | `backend/` | `uv run python -m compileall -q app agents` |
| Ruff correctness | `backend/` | `uv run ruff check .` |
| Type/import resolution | `backend/` | `uv run pyright` |
| Architecture boundaries | `backend/` | `uv run lint-imports` |
| Dead-code check | `backend/` | `uv run vulture app/ agents/` |
| Apply migrations after schema change | `backend/` | `uv run alembic upgrade head` |

Migration commands must point only to the configured local/disposable development or test PostgreSQL database. Do not run migrations against shared or production databases without explicit approval. Inspect `app.env.example`, never reveal `backend/.env`.

### Frontend

| Purpose | Working directory | Command |
|---|---|---|
| One Vitest file/pattern | `frontend/` | `npm run test -- <test-path-or-pattern>` |
| Full unit/component suite | `frontend/` | `npm run test` |
| Lint | `frontend/` | `npm run lint` |
| Production build/type validation | `frontend/` | `npm run build` |
| Mocked Playwright E2E (frontend already running) | `frontend/` | `npm run e2e` |
| Live Playwright E2E (required services already running) | `frontend/` | `npm run e2e:live` |

`npm run test` is already single-pass (`vitest --run`). Before either E2E command, verify that `http://localhost:3000` already responds. `frontend/playwright.config.ts` otherwise auto-starts `npm run dev`, which automation is forbidden to launch. If the frontend is absent, tell the user to run `npm run dev` manually from `frontend/` and wait for confirmation; `reuseExistingServer` then lets the single-pass Playwright command use that server without starting it. The mocked Playwright project is the default. Run `e2e:live` only when the user explicitly authorizes live testing, confirms every required frontend/backend service is running, and accepts external side effects/cost.

### Terraform and repository security

Use the same scope, configuration, redaction, and failure thresholds as the repository gates. Set the listed working directory through the automation tool; never use `cd`.

| Purpose | Working directory | Command |
|---|---|---|
| Terraform formatting | `infra/terraform/` | `terraform fmt -check -recursive` |
| Terraform configuration validation | `infra/terraform/` | `terraform validate` |
| Terraform policy scan | repository root | `checkov -d infra/terraform --config-file .checkov.yaml` |
| IaC/config scan | repository root | `trivy config --exit-code 1 --severity HIGH,CRITICAL --ignorefile .trivyignore --skip-dirs "**/examples/**" --skip-dirs "**/localstack/**" infra/terraform` |
| Terraform lint | repository root | `$env:TFLINT_CONFIG_FILE = (Resolve-Path "infra/terraform/.tflint.hcl").Path; tflint --chdir=infra/terraform --recursive --minimum-failure-severity=error` |
| Secret scan | repository root | `gitleaks detect --no-git --redact --no-banner -v --config .gitleaks.toml --source .` |

Do not weaken scanner severity, skip paths, config files, or Gitleaks redaction. Never run `terraform apply` or access shared state for validation. If `terraform validate` requires initialization, stop and explain that a bounded `terraform init -backend=false` from `infra/terraform/` will download pinned providers without configuring the remote backend; run it only after approval, then rerun validation. If TFLint reports missing plugins, instruct the user to perform the one-time `tflint --chdir=infra/terraform --init`; do not silently download plugins during a QA run.

### Dependency audits

The current CI runs `pip-audit` and `npm audit` as warn-only checks. Capture findings, but do not describe them as blocking gates unless CI policy changes. Do not suppress or omit findings from the report.

## 3. Change-to-gate mapping

This table is the minimum starting point. Increase depth for high-risk or cross-cutting changes.

| Affected surface | Focused proof | Required adjacent gates | Broader proof when justified |
|---|---|---|---|
| Backend pure/domain logic | targeted pytest | ruff; pyright when types/interfaces changed | relevant folder or full pytest |
| FastAPI route/schema/auth | API tests | ruff, pyright, authorization negatives | integration suite + full pytest |
| Agent/engine/runner | targeted deterministic agent tests | ruff, pyright, lint-imports | agents + unit suites; golden parity where affected |
| Repository/model/migration | PostgreSQL integration/migration tests | ruff, pyright, migration upgrade | full backend suite; integrity/concurrency cases |
| Frontend component/hook | targeted Vitest/RTL | lint; build | full Vitest |
| Navigation/user journey | component/API tests beneath flow | lint, build | mocked Playwright critical path |
| Shared TypeScript/API contract | frontend tests + backend schema/API tests | lint/build + backend ruff/pyright | mocked E2E |
| Terraform | fmt + validate | Checkov, Trivy config, TFLint, Gitleaks | isolated plan only if explicitly approved |
| Prompt/model/AI behavior | mocked deterministic tests | guardrail/schema/tool tests | approved eval/live run with budgets |
| Release candidate | risk-selected smoke | all blocking CI jobs | approved environment checks + rollback evidence |

A command that is unavailable is `BLOCKED`, not PASS. A command that was intentionally not selected is `NOT RUN`, with the selection rationale.

## 4. Preflight checklist

Before execution:

- confirm the requested revision/diff and that uncommitted user changes will not be overwritten;
- identify the authoritative runner/config/package script;
- confirm required dependencies are already installed;
- verify the target environment is isolated and permitted;
- verify fixtures use synthetic data and cleanup is safe;
- identify timeouts and expected runtime;
- define the pass oracle and stop conditions;
- for live/costly tests, state the maximum requests, duration, spend, and side effects;
- for security/load/chaos tests, confirm target ownership and explicit authorization.

## 5. Evidence capture

Record each execution in this form:

```markdown
| # | Working directory | Command | Exit | Result | Duration | Evidence |
|---|-------------------|---------|------|--------|----------|----------|
| 1 | `backend/` | `uv run pytest ... -v` | 0 | 8 passed | 1.42s | terminal output |
```

Capture:

- exact commit/branch or working-tree basis when relevant;
- exact test count and status distribution;
- failure node IDs and first causal traceback/assertion, not pages of noise;
- relevant warnings/deprecations;
- artifact paths for reports, traces, screenshots, videos, coverage, or result JSON;
- whether evidence came from mocked, local, staging, live-model, or production behavior;
- any redaction performed.

Do not paste credentials, auth headers, `.env` contents, raw sensitive prompts, user PII, or secret-bearing URLs into evidence.

## 6. Narrow-to-broad execution algorithm

1. Run the smallest deterministic reproducer.
2. If it fails, stop broadening and classify the failure.
3. If it passes, run the feature/module suite to detect nearby regressions.
4. Run static/type/build/architecture gates relevant to changed interfaces.
5. Add boundary or mocked E2E only when it catches a distinct risk.
6. Run full package/release gates only when requested, required by the task, or justified by blast radius.
7. Compare the actual evidence to every planned case; mark unexecuted cases explicitly.

Do not run the full suite first when a focused failure can provide a faster, clearer signal. Do not stop at a focused pass when shared interfaces or release confidence require broader evidence.

## 7. Failure classification procedure

### A. Preserve the first failure

Record command, node/test name, environment, inputs, assertion/exception, timestamp, and artifact paths before rerunning. The first failure remains evidence even if a later run passes.

### B. Check the oracle

Ask:

- Is expected behavior supported by acceptance criteria, API/schema, invariant, design decision, or user-visible contract?
- Is the assertion too strict, too broad, stale, or tied to internals?
- Is the test exercising the intended layer and environment?

A wrong oracle is a TEST DEFECT, not a product regression.

### C. Check isolation and determinism

Inspect:

- shared database/account/files;
- execution order;
- clock/time zone/random seed;
- concurrency and asynchronous waits;
- provider/network dependence;
- leaked browser/session state;
- previous-run artifacts and caches;
- resource contention or rate limiting.

### D. Perform one controlled diagnostic rerun

Use the same revision, inputs, environment, and command. If practical, add observability without changing behavior. Interpret outcomes:

| Outcome | Classification direction |
|---|---|
| Same deterministic functional mismatch | PRODUCT DEFECT or TEST DEFECT depending on oracle |
| Passes with no relevant change | FLAKY/NONDETERMINISTIC until root-caused |
| Fails only when dependency/tool is unavailable | ENVIRONMENT/INFRASTRUCTURE |
| Fails only in shared state/order | TEST DEFECT or product concurrency defect; isolate further |
| Behavior intentionally documented | BY DESIGN |
| Required state/model/evidence cannot be observed | NOT VERIFIABLE |

Do not keep rerunning until green. Framework retries must remain visible in the result; "passed on retry" is a flake signal.

## 8. Product defect evidence packet

When behavior is genuinely defective, provide:

```markdown
### Finding: <short title>
- Classification: PRODUCT DEFECT
- Severity/Priority: P0 | P1 | P2 | P3
- Environment/revision: <where and what was tested>
- Requirement/oracle: <expected contract>
- Preconditions: <minimal data/state>
- Reproduction:
  1. ...
  2. ...
- Expected: ...
- Actual: ...
- Evidence: <test node, output, trace, screenshot, request/response with redaction>
- Frequency: deterministic | intermittent <rate>
- Blast radius: ...
- Suspected boundary (not asserted root cause): ...
- Recommended regression layer: ...
```

Use `P0` for active catastrophic security/data/availability impact, `P1` for critical user flows or major integrity/security issues, `P2` for important degraded behavior with workaround, and `P3` for minor/cosmetic impact. Severity must follow evidence, not frustration.

Do not claim a root cause from a failing black-box test alone. Distinguish observed cause, suspected boundary, and confirmed root cause.

## 9. Flake handling

A flaky test is a defect in the quality system or a signal of a race in the product.

Required response:

1. classify likely source: test timing, locator, data, environment, concurrency, provider, or product race;
2. quantify observed pass/fail pattern without manufacturing extra runs beyond an agreed diagnostic budget;
3. preserve trace/log/timing evidence;
4. fix the root cause only when authorized;
5. if quarantine is unavoidable, attach owner, issue, reason, date, expiry/review date, and non-blocking visibility;
6. never delete or skip silently.

Blanket retries, longer sleeps, weakened assertions, and `force` interactions are not fixes.

## 10. Stop conditions

Stop and report instead of improvising when:

- the requested target or oracle cannot be determined;
- a PreToolUse or environment policy denies the action;
- a required service/credential/tool is missing;
- the only available environment is shared/production and approval is absent;
- the test would create uncontrolled cost, traffic, or side effects;
- test data cannot be isolated or safely cleaned;
- a security/load/chaos target is not demonstrably authorized;
- continuing would overwrite user work or reveal sensitive data;
- the first failure proves the requested criterion cannot pass and broader execution adds no useful evidence.

A stopped run can still produce a high-quality PARTIAL or BLOCKED report.
