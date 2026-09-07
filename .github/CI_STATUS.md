# CI pipeline — current state

This file replaces `CI_MIGRATION_COMPLETE.md`, `CI_REMEDIATION_CHECKPOINT_FINAL.md`
and `TASK_3_27_VALIDATION.md`. All three declared the remediation complete and
production-ready. They described jobs that did not exist (`frontend-static`,
`frontend-vitest`, `frontend-e2e`, `backend-evidence`, `frontend-evidence`),
claimed enforcement that was not wired up, and listed rulesets as correctly
configured while they required a status context no workflow could publish.

## Architecture

Two workflows.

**`.github/workflows/ci.yml`** — the single unprivileged evaluator. Runs on pull
requests, pushes to `main`, manual dispatch, and as the reusable gate that
`deploy.yml` calls. Holds no cloud, OIDC, deployment or repository-write
credentials. 15 jobs:

| Job | Owns |
|---|---|
| `repo-static` | actionlint, shell parse, ShellCheck |
| `backend-inventory` | canonical marker-based test inventory and partition proof |
| `backend-static` | Ruff lint/format, compile, Pyright, import-linter, Vulture, Bandit, migration guard |
| `backend-offline` | the complete non-live, non-PostgreSQL pytest partition |
| `backend-postgres` | the PostgreSQL partition against a real service |
| `backend-evidence` | coverage merge, merged JUnit, backend 80% gate |
| `frontend-static` | typecheck, lint, production build |
| `frontend-vitest` | the complete Vitest inventory with coverage |
| `frontend-e2e` | the complete mocked Playwright project |
| `frontend-evidence` | all four frontend coverage metrics at 80% |
| `security` | gitleaks, pip-audit, npm audit, Terraform/TFLint/Checkov/Trivy-config |
| `container-scan` | both images, Trivy and Grype, zero High/Critical |
| `sonar-inline` | Sonar analysis and quality gate, trusted intents only |
| `ci-evidence` | the aggregate verdict |
| `ci-required` | publishes the status, trusted intents only |

**`.github/workflows/ci-authoritative.yml`** — trusted pull-request finalizer,
loaded from the default branch via `workflow_run`. Adds Sonar, which the
evaluator cannot run because pull-request code may come from a fork and must
never see `SONAR_TOKEN`. It is the sole publisher of `ci-required` for PRs.

## The rules that keep it honest

- No mandatory step may use `continue-on-error: true`, a trailing `|| true`, or a
  trailing `exit 0`. `tests/ci/test_ci_remediation_exploration.py::test_no_mandatory_step_is_advisory`
  fails the build if one appears. Where several independent checks must all
  report, `backend/agents/ci/run_checks.py` runs each to completion, records a
  sub-verdict, and then exits non-zero.
- Every mandatory signal is registered in `backend/agents/ci/signal_registry.py`
  with exactly one `owner_job`. `ci-evidence` feeds all job results through
  `python -m agents.ci.ci_gate aggregate`, which succeeds only if all 35 signals
  succeeded for the exact evaluated SHA.
- Security verdicts come from `agents.ci.ci_gate scan-gate`, which fails on any
  resolved High or Critical finding regardless of fix availability. No baseline,
  no `--ignore-unfixed`, no suppression list.
- A missing, empty or unparseable mandatory report is a failure, not a skip.

## Branch protection is NOT yet enabled

`.github/rulesets/*.json` deliberately do **not** require `ci-required`. Adding
it is the last step and needs observed evidence first — see
`.kiro/specs/ci-pipeline-remediation/ROLLOUT-EVIDENCE.md`. Requiring a context
that no workflow can emit blocks every pull request, which is what happened
previously.

## The pipeline currently reports red, on purpose

Four mandatory gates fail against real measurements. These are pre-existing
product and dependency debt that the previous pipeline passed over:

| Gate | Required | Measured |
|---|---|---|
| Frontend coverage | ≥ 80% on all four metrics | 47.34 / 45.11 / 46.34 / 49.26 |
| `security[backend-deps]` | 0 High/Critical | 1 High (`PYSEC-2026-1325`, `ecdsa` via `python-jose`) |
| `security[frontend-deps]` | 0 High/Critical | 2 High (`image-size` via `pptxgenjs`) |
| `frontend-e2e` | 0 applicable skips | ~40 `test.skip` / `test.fixme` |

Each needs its own reviewed change. Do not clear them by lowering a threshold,
narrowing the coverage denominator, adding a waiver, or converting a failing test
to a skip.

## Rollback

`ROLLBACK_PROCEDURE.md` still applies. The one addition: a workflow rollback and
the removal of a required status context are a single reviewed unit. Never leave a
required context that no workflow can publish.
