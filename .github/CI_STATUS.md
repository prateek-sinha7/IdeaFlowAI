# CI pipeline — current state

**This is the single entry point for CI/CD in this repository.** It is kept in
step with the live workflow YAML, and `backend/tests/unit/tools/ci/test_ci_docs_contracts.py`
fails when a workflow file or a `ci.yml` job is missing from the tables below.
Where another document disagrees with the YAML, the YAML wins.

Where to look:

| Need | Read |
|---|---|
| Current workflows, jobs, pins | this file |
| Rolling back a deploy or a workflow change | [`ROLLBACK_PROCEDURE.md`](ROLLBACK_PROCEDURE.md) |
| Why a design decision was made | `docs/CICD-*.md` and `docs/GITHUB_*` are **historical design records**. Each carries a banner saying so; they may not match the live YAML |
| What shipped in a version | [`CHANGELOG.md`](../CHANGELOG.md) and the repository's Releases page |
| Build and deploy status at a glance | the CI and Deploy badges at the top of [`README.md`](../README.md) |

This file replaced `CI_MIGRATION_COMPLETE.md`, `CI_REMEDIATION_CHECKPOINT_FINAL.md`
and `TASK_3_27_VALIDATION.md`. Those declared the remediation complete and
production-ready while claiming enforcement that was not wired up, and listed
rulesets as correctly configured while they required a status context no workflow
could publish.

## Architecture

### Workflow index

| File | Name | Trigger | Purpose |
|---|---|---|---|
| `ci.yml` | CI | `pull_request`; push to `main`, `dev`, `staging`; `workflow_dispatch`; `workflow_call` | The single unprivileged evaluator, and the reusable gate `deploy.yml` calls |
| `ci-authoritative.yml` | CI Authoritative (PR Finalizer) | `workflow_run` of CI | Trusted pull-request finalizer; sole publisher of `ci-required` for PRs |
| `deploy.yml` | Deploy | push to `dev`, `staging`; push of `v*` tags; `workflow_dispatch` | Gate, resolve, build and deploy over SSM |
| `provision.yml` | Provision | `workflow_dispatch` | One-time bootstrap of a hand-created EC2 host over SSM |
| `cognito-reconcile.yml` | Cognito Reconcile | daily 03:00 UTC schedule; `workflow_dispatch` | Drift report and retry of pending Cognito deletions |
| `notify-failure.yml` | Notify Failure | `workflow_run` of CI, CI Authoritative, Deploy, Cognito Reconcile, Release | Opens an alarm issue when an unattended run fails |
| `release.yml` | Release | push of `v*` tags | Creates a GitHub Release with generated notes. Independent of Deploy; watched by Notify Failure. Accepts only `vMAJOR.MINOR.PATCH[-prerelease]`, the same grammar Deploy enforces |

Every job runs on the exact runner label `ubuntu-24.04` (never `ubuntu-latest`,
which floats). The label is recorded in `backend/tools/ci/pin_authority.py`
(`runner_image`) and `ci/toolchain-lock.json` (`runtime_pins.runner_image`), which
also lists what the workflows take from the runner image instead of installing
(`jq`, the AWS CLI v2, `gh`, Docker Compose). A runner bump is a reviewed change.

### `ci.yml`

The single unprivileged evaluator. Holds no cloud, OIDC, deployment or
repository-write credentials. Each job id below is the registry `owner_job` value
in `backend/tools/ci/signal_registry.py`; `ci-evidence` fails closed on a job that
owns no registered signal.

| Job | Owns |
|---|---|
| `changes` | the path filter: which areas a pull request touched. Pull requests only; push, dispatch and `workflow_call` always run everything |
| `repo-static` | actionlint, shell parse, ShellCheck (checksum-pinned binary, version asserted by `ci-shellcheck.sh`), compose config |
| `backend-inventory` | canonical marker-based test inventory and partition proof |
| `backend-static` | Ruff lint/format, compile, Pyright, import-linter, Vulture, Bandit, migration guard |
| `backend-offline` | the complete non-live, non-PostgreSQL pytest partition |
| `backend-postgres` | the PostgreSQL partition against a real service |
| `backend-evidence` | coverage merge, merged JUnit, backend 80% gate |
| `frontend-build` | the production build; uploads the standalone bundle that `frontend-e2e` serves |
| `frontend-static` | typecheck and lint only (the build moved to `frontend-build`) |
| `frontend-vitest` | the complete Vitest inventory with coverage |
| `frontend-e2e` | the complete mocked Playwright project, run against the production standalone server |
| `frontend-evidence` | all four frontend coverage metrics at 80% |
| `security` | matrix legs: gitleaks (full history), Terraform fmt/validate, TFLint, Checkov, Trivy-config |
| `container-scan` | both images with Trivy and Grype, plus `trivy fs` on `frontend/package-lock.json`; **temporarily advisory**: unaccepted High/Critical findings are reported as warnings and in the step summary and do not fail the job (TODO: restore blocking) |
| `ci-evidence` | the aggregate verdict |
| `ci-required` | publishes the status, trusted intents only |

Concurrency: pull requests and branch pushes cancel an older run of the same head.
A run with an explicit `inputs.intent_id` (manual dispatch, or the gate call from
`deploy.yml`) is keyed by that intent and is never cancelled.

### `ci-authoritative.yml`

Trusted pull-request finalizer, loaded from the default branch via `workflow_run`.
It runs no checks of its own: it attests that the evaluator run belongs to
`ci.yml`, is for the current head of an open PR, and produced a complete green
manifest. It is the sole publisher of `ci-required` for PRs, because a
fork-triggered `pull_request` token is read-only and cannot write a commit status
at all.

### Toolchain pins

- Runner `ubuntu-24.04`; Python 3.13; Node 24 (`pin_authority.node_runtime_version`
  holds the exact version).
- Directly downloaded tools (actionlint, gitleaks, Trivy, Grype, ShellCheck) go
  through `.github/actions/install-checksummed-tool` with a SHA-256 recorded in
  `ci/toolchain-lock.json`. ShellCheck publishes no checksums file, so its value
  is the GitHub release-asset digest cross-checked against a locally recomputed
  hash; the lock says so.
- Every third-party action is pinned to a full commit SHA with a version comment,
  and the complete set is recorded in `ci/toolchain-lock.json`
  (`external_actions`). A test fails when the workflows and the record disagree, so
  a Dependabot bump needs the lock updated in the same PR.
- Tooling-only jobs install with the `ci-tools` dependency mode.

## The rules that keep it honest

- No mandatory step may use `continue-on-error: true`, a trailing `|| true`, or a
  trailing `exit 0`. `backend/tests/unit/tools/ci/test_ci_remediation_exploration.py::test_no_mandatory_step_is_advisory`
  fails the build if one appears. Where several independent checks must all
  report, `backend/tools/ci/run_checks.py` runs each to completion, records a
  sub-verdict, and then exits non-zero.
- Every mandatory signal is registered in `backend/tools/ci/signal_registry.py`
  with exactly one `owner_job`. `ci-evidence` feeds all job results through
  `python -m tools.ci.ci_gate aggregate`, which succeeds only if every registered
  mandatory signal succeeded for the exact evaluated SHA. The aggregate step
  prints the registry-derived count in the `ci-evidence` log.
- Security verdicts come from `tools.ci.ci_gate scan-gate`, which fails on any
  resolved High or Critical finding regardless of fix availability. No baseline,
  no `--ignore-unfixed`, no `--ignorefile`.
- Every vulnerability verdict comes from Trivy or Grype. The only exceptions are
  the dated, per-package entries in `backend/tools/ci/scan_accepts.py`, applied
  to the report before the gate by `.github/scripts/ci-image-scan.sh` and
  `ci-lockfile-scan.sh`, in both `ci.yml` and `deploy.yml`'s post-push scan. An
  entry fails the build once it expires or stops matching anything (while the
  scans are advisory it produces a warning).
- A missing, empty or unparseable mandatory report is a failure, not a skip,
  except for the temporarily advisory vulnerability scans, where it is a warning
  and means no verdict for that run.
- TEMPORARY exception: `container-scan` and deploy's post-push scan run
  `scan-gate --mode warn` (`SCAN_GATE_MODE: warn`), so findings warn instead of
  fail. gitleaks, Terraform fmt/validate, TFLint, Checkov, Trivy-config and
  Bandit still block.

> **TODO(security): TEMPORARY** - vulnerability scans are WARN-ONLY (advisory) as of 2026-10-11.
> In future this must be changed back to BLOCKING, and the outstanding High/Critical
> vulnerabilities must be fixed (see `backend/tools/ci/scan_accepts.py` and scan reports).

## Vulnerability scanning: one tool family, one exceptions list

> **TODO(security): TEMPORARY** - vulnerability scans are WARN-ONLY (advisory) as of 2026-10-11.
> In future this must be changed back to BLOCKING, and the outstanding High/Critical
> vulnerabilities must be fixed (see `backend/tools/ci/scan_accepts.py` and scan reports).

Vulnerability scans are currently warn-only in every environment (PR, dev, stage,
prod). The four steps are `container-scan`'s image and lockfile scans in `ci.yml`
and the two post-push scans in `deploy.yml`; each sets `SCAN_GATE_MODE: warn`.
The scans still run and write reports. Findings appear as `::warning::`
annotations and in the step summary; the real verdict is in `*-verdict.json`
(`enforced: false`). Everything else still blocks. To revert: delete the 4
`SCAN_GATE_MODE: warn` env lines, restore `is_blocking=True` on the 5
`container-scan` registry signals, restore the step names (`blocking`), and flip
the tests marked TEMPORARY.

pip-audit (`security[backend-deps]`) and npm audit (`security[frontend-deps]`)
were retired:

- **Backend.** The image installs exactly `uv export --frozen --no-dev` from
  `backend/uv.lock`, so the Trivy and Grype image scans already see every
  production Python package. pip-audit only added the dev group, which never
  ships.
- **Frontend.** The image is a Next.js `output: "standalone"` build: most
  dependencies are compiled into `.next/` chunks with no `package.json`, which
  image scanners cannot see. `container-scan (frontend)` therefore also runs
  `trivy fs` on `frontend/package-lock.json`
  (`container-scan[frontend]/trivy-lockfile`). Trivy skips devDependencies by
  default.

Before this change the dependency audits carried their own exceptions
(`--ignore-vuln PYSEC-2026-1325`, `npm_audit_accepts.py`) while the image scans,
which report the same CVEs, accepted nothing, so those exceptions unblocked
nothing. They now live in one list:

| Finding | Scopes | Status |
|---|---|---|
| `zlib1g` CVE-2023-45853 | backend image, frontend image | accepted until 2026-12-31: MiniZip is not built into zlib1g; no bookworm fix |
| `ecdsa` CVE-2024-23342 | backend image | accepted until 2026-12-31: only RS256 is used, the EC signing path is unreachable; ends with the PyJWT migration |
| `image-size` CVE-2025-71329 / CVE-2025-71330 | backend image, frontend lockfile | accepted until 2026-12-31: no fix published; ends when pptxgenjs is removed |
| `setuptools` CVE-2025-47273 | backend image | **fixed**, not accepted: `backend/Dockerfile` upgrades the system interpreter's setuptools |

## Branch protection requires `ci-required`

`.github/rulesets/main.json` and `dev-staging.json` both require the
`ci-required` aggregate status check; `main.json` additionally applies the strict
up-to-date policy and a code-owner approval. `main.json` is the strict gate,
`dev-staging.json` is deliberately loose so routine iteration does not need a
rebase per upstream push.

Only the single aggregate is ever required. Shards, jobs and scanners are inputs
to it, so renaming one internally is not a branch-protection change.

For pull requests the context is published solely by the `publish-ci-required`
job in `ci-authoritative.yml`, which is triggered by `workflow_run` and therefore
runs default-branch code with a token that can write statuses. `ci.yml` runs
untrusted PR code and must never publish it.

Before adding a context to a ruleset, confirm a publisher exists and has been
seen succeeding: a required context that no workflow can emit blocks every pull
request, which is what happened previously.
`backend/tests/unit/tools/ci/test_ruleset_workflow_contract.py` enforces publisher
reachability and keeps these descriptions honest.

The committed `rulesets/*.json` files are the **intent**, not proof of
enforcement. No workflow compares them with the live rulesets and environments
(that check needs an Administration: Read token, which requires an org admin).
When last checked (F-11), the live rulesets did not carry the
`required_status_checks` rule the files declare, so verify the live rulesets in
repository Settings before relying on the merge gate.

An earlier revision of this section, and of both ruleset descriptions, claimed
`ci-required` was deliberately **not** required, and pointed at a rollout
evidence document under `.kiro/`. The requirement was added in `db2ddea7`; the
prose was not updated, and the cited path is gitignored and has never existed in
this repo. Both are corrected here.

## The pipeline currently reports red, on purpose

Mandatory gates fail against real measurements. Two of them are pre-existing
product debt that the previous pipeline passed over, and are the only two
signals `deploy.yml` downgrades to advisory for `dev`:

| Gate | Required | Measured |
|---|---|---|
| Frontend coverage | ≥ 80% on all four metrics | 47.34 / 45.11 / 46.34 / 49.26 |
| `frontend-e2e` | the complete mocked Playwright project passes | fails at the "Run the complete mocked project" step on run 37548247326 (not yet triaged) |

The earlier "~40 `test.skip` / `test.fixme`" figure no longer holds: the E2E
tree contains only a handful of environment-gated skips (live-only specs and
two opt-in capture specs). The failures are failing tests, not skips.

The two dependency-audit rows that used to be here were retired with their
signals; see "Vulnerability scanning" above.

Five mandatory jobs were red on CI run 37548247326 (the pull-request run of the
audited commit), not two:

| Job | Why it was red | Advisory for `dev`? |
|---|---|---|
| `container-scan[backend]` and `container-scan[frontend]` | scan findings, including the frontend lockfile scan | No (not advisory-eligible; vulnerability findings are TEMPORARILY warn-only everywhere since 2026-10-11, see above) |
| `frontend-e2e` | failing mocked E2E tests, as above | Yes |
| `frontend-evidence` | its producer check failed because E2E failed (it no longer waits for E2E: E2E now feeds `ci-evidence` directly); coverage is separately measured below 80% | Yes |
| `backend-evidence` | the producers' hidden `.coverage.*` files were dropped at artifact upload, so `coverage combine` failed (fixed by `include-hidden-files: true`) | No |

`ci-evidence`, and therefore `ci-required`, stays red while any of these is red.
`backend-evidence` is not advisory-eligible and `container-scan` blocks only on non-finding failures (for example a broken image build) while findings warn, so the Deploy
gate blocks `dev` as well as `stage` and `prod` until they are green.

Each needs its own reviewed change. Do not clear them by lowering a threshold,
narrowing the coverage denominator, adding a waiver, or converting a failing test
to a skip.

### `container-scan` was red for a different reason — a build misconfiguration

Not listed above because it was not a measurement at all. The build step passed
`context: .` (the repo root) while both Dockerfiles write every `COPY` relative to
their own directory, and it supplied no `opendesign` named build context although
`backend/Dockerfile` requires one. Both matrix legs therefore failed at the first
`COPY`, before any scanner ran — so the four image `container-scan[*]` signals had no
verdict rather than a bad one, and `docker-compose.yml` had been building these
images correctly all along.

Fixed: the step now uses `context: ./<component>` and, for backend,
`build-contexts: opendesign=./skills/opendesign`, matching compose exactly. The
scan verdicts are now genuinely measured for the first time, so treat any
High/Critical finding they report as new information rather than a regression.

## Rollback

`ROLLBACK_PROCEDURE.md` still applies. The one addition: a workflow rollback and
the removal of a required status context are a single reviewed unit. Never leave a
required context that no workflow can publish.
