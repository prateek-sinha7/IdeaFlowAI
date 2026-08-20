# VelocityAI/Flowin Testing and Defect-Prevention Plan

> Audit baseline: `fix/testcases` at `0520e2f44c1af724b112f1fde99837b32cebf393`, captured 2026-08-19. This is an implementation plan, not a claim that the current repository is green. `[x]` means audit evidence was verified at the baseline commit; `[ ]` means future implementation or verification work remains.

## 1. Executive summary

[x] The repository was audited across compiler/runtime, persistence, API/SSE, frontend, browser automation, AI evaluation, security, Terraform, deployment, reliability, and observability.

The release path is not currently trustworthy. The highest-risk gaps are: deployment can bypass CI; image scans cannot block; PostgreSQL behavior is mostly represented by SQLite; resume sequence allocation and fan-out share concurrency hazards; terminal state transitions are not consistently fenced; graceful shutdown can block indefinitely; SSE terminal/reconnect contracts are incomplete; SC-001 is not proven through public discovery and launch; Terraform is not validated in CI; and both the frontend quality gates and mocked browser baseline are red.

Measured status is not “tests pass”: backend default Windows collection fails; the UTF-8 experiment produced 71 failures and 4 errors; Vitest has one timezone-fixture failure; ESLint has 44 errors; the Next build has a TypeScript error; and mocked Playwright has 60 failures. Most backend failures are portability/harness defects, but eight expose a real Windows path-confinement defect. Most browser failures are fixture, locator, and readiness debt, but sub-agent flattening is evidenced product behavior and 15 reconnect/settling cases remain unresolved.

Release recommendation: **NO-GO** until Phase 0 restores truthful gates and all P0 controls in Sections 7 and 10 are implemented and green in the target Linux/PostgreSQL environment.

## 2. Audit metadata and evidence

| Item | Verified evidence |
|---|---|
| Repository | `c:\Users\2000189855\projects\velocityai` |
| Baseline | branch `fix/testcases`; SHA `0520e2f44c1af724b112f1fde99837b32cebf393`; initially clean single worktree |
| Host | Windows NT `10.0.26200.0`; PowerShell `5.1.26100.8875` |
| Runtime | project Python `3.12.2`; pytest `8.3.4`; Node `24.15.0`; npm `11.16.0`; Terraform `1.15.6`; PostgreSQL client `16.2` |
| Installed app stack | FastAPI `0.115.6`, SQLAlchemy `2.0.36`, Alembic `1.14.0`, `deepagents==0.6.7`, LangChain `1.3.4`, LangGraph `1.2.4`, Playwright Python `1.60.0` |
| Local services | `localhost:5432` accepted connections; Docker unavailable; port 3000 was free before Playwright |
| Credentials | `AWS_PROFILE`, `AWS_BEARER_TOKEN_BEDROCK`, `ANTHROPIC_API_KEY`, and `MISTRAL_API_KEY` absent |
| Knowledge base | 482 cards and 36 architecture cards; source coverage `865/870` and commits-since-sync stale; no rebuild because only `task.md` may change |
| Migration chain | live repository head is `0032`; references to head `0026` are stale |
| Golden safety | `SNAPSHOT_UPDATE` unset; no golden update; final golden status checked clean before writing this plan |
| Unavailable local tools | Docker, TFLint, Checkov, Trivy, Gitleaks, pre-commit, Ruff, Pyright, import-linter, Vulture |
| Coverage measurement at baseline | **none** — no `--cov` flag, no `coverage` dependency, no Vitest `coverage` block, no coverage artifact or upload in `ci.yml`; therefore no measured line/branch number exists for any layer at `0520e2f` |

Evidence precedence: executable behavior and source at the recorded SHA override stale cards, comments, registers, and runbooks. The project-index instruction names `scripts/knowledge/ctx.py`, but that file does not exist; `.claude/skills/velocity/cli.md` confirms only the current `tools/knowledge/*` commands. This is recorded as documentation drift, not worked around by inventing a command.

**Post-baseline amendment (coverage instrumentation).** After the audit was written, coverage instrumentation was added to the working tree on request: `--cov` flags plus artifact/Codecov steps in `.github/workflows/ci.yml`, `[tool.coverage.*]` in `backend/pyproject.toml`, `coverage[toml]==7.6.1` in `backend/requirements-dev.txt`, a `coverage` block in `frontend/vitest.config.ts`, `@vitest/coverage-v8` plus a `--coverage` test script in `frontend/package.json`, ignore rules in `.gitignore`, and two guides under `docs/`. These edits are **uncommitted and unexecuted**: no coverage run has been performed, so every percentage in this plan remains an unverified estimate until COV-001 produces the first measured baseline. The earlier statement that only `task.md` would change no longer holds and is corrected here rather than left implied.

## 3. Architecture and critical-flow map

```text
workflow.yaml + AGENT.md
  -> manifest loader/compiler (typed CompiledWorkflow; registry membership)
  -> ExecutionEngine (name-free kernel)
  -> strategy/gate/context/deliverable/validator capabilities
  -> RunSandbox + ArtifactGraph + scoped durable store/checkpointer
  -> run_events (owner_id, workspace_id, run_id, event_id, seq)
  -> GET /api/runs/{id}/events/stream (SSE down-channel)
  -> RunConnectionProvider/useRunStream/useRunStateStore
  -> run screen/chat/gates/deliverables/history

REST up-channel:
  POST /api/runs/{id}/{gate|answers|cancel|messages|revisions}
  -> authz scoped store -> terminal/transition fence -> driver/checkpointer

Delivery:
  PR -> CI gate -> image build -> blocking image scan -> approved deploy
  Terraform bootstrap -> shared -> foundation -> app/velocityai-alb
  Remote encrypted state and per-environment identity are required.
```

Critical flows and failure boundaries:

| Flow | Required invariant | Primary evidence surface |
|---|---|---|
| Compile/discover/launch custom workflow | SC-001; no workflow names in kernel; registry two-surface discipline | `backend/agents/workflows`, compiler, registry, `engine.py` |
| Execute/retry/cancel/fan-out | one terminal outcome; no success after terminal; isolated child context | `engine.py`, `fanout.py`, strategies |
| Persist/replay/resume | unique monotonic sequence; idempotent replay; scoped access | run-event migrations/models/store/checkpointer |
| Gate/answer/cancel commands | owner/workspace authorization and terminal fence | `authz.py`, `run_commands.py` |
| Stream/reconnect | SSE-only down-channel, REST up-channel, exact-once reduction | `run_stream.py`, `useRunStream.ts`, provider/store |
| Shutdown/restart | bounded drain, reachable lifespan cleanup, resumable live runs | `run_shutdown.py`, checkpointer, entrypoint |
| Build/deploy | tested SHA only; blocking scans; approval for production | `.github/workflows/*.yml`, Terraform roots |

## 4. Existing test, tool, and CI inventory

| Surface | Asset/command | Scope and oracle | Dependencies/data | Current CI | Baseline/gap |
|---|---|---|---|---|---|
| Backend unit/integration | `backend/tests`, pytest markers | compiler, kernel, API, models, migrations, characterization | SQLite default; narrow PostgreSQL; optional providers | CI runs offline pytest | Large suite, but platform assumptions and SQLite dominance hide production semantics |
| Characterization | `tests/agents/test_characterization_*.py` + byte goldens | four workflows/eight primary tests; event/deliverable compatibility | deterministic scripted models; raw-byte goldens | included in pytest | one CRLF checkout failure; normalizer sorts events and cannot prove semantic event order |
| SC-001/banned patterns | SC-001 and migration-ledger grep tests | exact banned strings and patched loader/compiler seams | Unix commands assumed | included in pytest | does not prove public drop-in discovery; regex misses `match`, mappings, helpers, `in`, `!=` |
| Property tests | Hypothesis in sandbox/deliverable tests | serialization and path cases | filesystem/newline semantics | included in pytest | Windows newline/path failures need portable or OS-specific contracts |
| Frontend unit/component | Vitest/jsdom, 390 suites/1075 tests | reducers, hooks, components, API clients | mocked browser APIs | CI frontend test | one local-calendar fixture defect |
| Frontend static/build | ESLint, Next build/TypeScript | React/compiler rules and production bundle | Node modules | CI runs lint/build | both red locally; no trustworthy merge gate while baseline is red |
| Browser mocked | Playwright project `mocked` | mounted app with mocked REST/SSE | Next dev server at fixed port 3000 | not in CI | 194 tests; 91 pass, 60 fail, 43 skip; fixed-port `reuseExistingServer` contamination risk |
| Browser live | Playwright project `live` | real backend and provider workflows | PostgreSQL/backend/provider credentials; billable | not in CI | 11 tests; not authorized or run |
| AI evaluation | `backend/evals/minimal` | one-row smoke and ten-row workflow/PPT configs | live Mistral default; billable | not in CI | no schema, calibration, budget, injection, deterministic PPT, or visual-quality gates |
| Python static | compileall; Ruff/Pyright/import-linter/Vulture configs/intent | syntax, types, boundaries, dead code | tools absent locally | partial/unclear | compileall passed; other controls not executable in existing venv |
| Coverage measurement | none at baseline; instrumentation staged post-baseline (`pytest --cov`, Vitest v8 provider) | which production lines/branches any suite actually executes | `coverage[toml]`, `@vitest/coverage-v8`; CI artifact store | none at baseline; staged uncommitted | no measured baseline for `app/`, `agents/`, or `frontend/src`; no ratchet, no per-PR signal, no untested-module inventory |
| Security | Gitleaks, Checkov, Trivy/tfsec, TFLint configs/workflow steps | secrets, IaC, images, dependencies | tools/container registry | scans exist but some warn-only | image Trivy uses `--exit-code 0 ... || true`; Gitleaks allowlists all tests/e2e |
| Terraform | six roots + modules/policies | fmt, init, validate, plan, policy | providers/modules, remote backend, cloud identity | no Terraform binary/validation in CI | fmt passed; validate blocked before semantic validation because init/cache absent |
| Database | Alembic tests, bootstrap PostgreSQL marker | upgrade/downgrade/schema behavior | Docker or PostgreSQL DB | no PostgreSQL service in CI | comments claim a full PostgreSQL run that CI does not provide |
| Reliability | shutdown/replay/cancel tests | signal, drain, resume, terminal behavior | production-like Linux process and PostgreSQL | fragmented | Windows SIGTERM test invalid; unbounded checkpointer close remains |
| Accessibility/performance | no active axe, k6, Locust, or budgets | none | none | none | explicit coverage gap |
| Supply chain | npm/pip audit, image scan | known vulnerable packages/images | registries/advisories | audits warn-only in places | no SBOM/signing/provenance gate observed |

## 5. Measured baseline

### 5.1 Backend

[x] Default Windows command with live/provider markers excluded failed collection after 29.06s: `3443 items / 1 error / 1 deselected`; `test_migration_ledger.py:121` uses `read_text()` without encoding and cp1252 cannot decode byte `0x90`.

[x] Controlled `PYTHONUTF8=1` experiment (not a substitute for the default defect): `3473 collected / 1 deselected / 3472 selected`; **3318 passed, 79 skipped, 71 failed, 4 errors** in 932.23s.

| Root-cause group | Count | Classification | Required disposition |
|---|---:|---|---|
| Separator-sensitive `api_prefix` confinement excludes all files on Windows | 8 | product portability defect | use structural `Path.relative_to`/`is_relative_to`; retain cross-OS tests |
| Unix commands, `preexec_fn`, `resource`, `fcntl`, POSIX signal/permission assumptions, and path separators | 54 | platform/harness/setup | split portable tests from Linux-production tests; add Windows guards/implementations where Windows is supported |
| CRLF/newline materialization in one byte golden, eight sandbox outputs, two prompt baselines | 11 | environment/EOL contract | pin byte goldens `-text`; make text serialization newline-explicit; never normalize golden assertions silently |
| Strict XPASS after migration 0024 was intentionally made defensive | 2 | stale xfail metadata | remove xfail decorators; keep assertions as regressions |
| Total | **75** | eight product failures; 67 test/environment failures | all must be made explicit; no blanket skip or golden update |

Other verified backend controls: `python -m compileall -q app agents` passed. Warning debt includes undeclared `requires_postgres` marker.

### 5.2 Frontend

[x] Vitest: 390 suites (388 passed, 2 failed-file accounting), 1075 tests (**1074 passed, 1 failed**), snapshots unchanged. `WorkflowHistory.grouping.test.tsx:115` uses UTC fixtures against deliberate local-calendar semantics; on UTC+05:30 the rows correctly belong to Earlier. Fix the fixture with local constructors and pin Date in rendered tests; do not change product semantics to UTC.

[x] ESLint: **44 errors, 246 warnings across 79 files**. Error groups: `react/no-unescaped-entities` 17, `react-hooks/refs` 14, `react-hooks/immutability` 10, `rules-of-hooks` 1, `prefer-const` 1, `react-hooks/purity` 1. High-risk examples include hook-ordering/closure errors in admin/dashboard/handoff code and render-time ref access.

[x] Next build compiled then failed TypeScript at `frontend/src/test/renderWithProviders.tsx:49`: reducer type incompatible with Redux `UnknownAction` initializer signature.

[x] Playwright discovery: **205 tests in 41 files** = 194 mocked + 11 live. Mocked run: **91 passed, 60 failed, 43 skipped in 6.1m**. Live tests were not run.

| Mocked Playwright cluster | Evidenced count | Classification |
|---|---:|---|
| Incomplete five-entry agent library vs workflow lineups | at least 4; contributes to 20+ | fixture contract defect |
| Canvas default/copy/generated-ID/strict locator drift | at least 11 | stale E2E assertions |
| Direct SSE injection does not await attachment/execution view | 7 | harness readiness race |
| Reconnecting/terminal/typed-renderer settling cluster | 15 | unresolved harness/product split; isolate before assignment |
| Selected sub-agent renders as a second root | 2 | confirmed product behavior defect |
| Remaining cases | unresolved individually | must be triaged, not bulk re-baselined |

### 5.3 Terraform/security

[x] `terraform fmt -check -recursive` passed.

[x] `terraform validate -no-color` was attempted in `bootstrap`, `shared`, `foundation`, `app`, `velocityai-alb`, and `localstack`. None reached semantic validation: bootstrap lacked cached AWS provider 5.100.0; the other roots had uninstalled modules. No `terraform init`, provider download, plan, or apply was run.

[ ] Run initialized validation and security scans in an ephemeral Linux CI workspace with no local shared-environment state.

## 6. Failure and flakiness classification policy

Every red result must receive one owner and one of these labels before suppression: `PRODUCT_DEFECT`, `TEST_DEFECT`, `HARNESS_SETUP`, `STALE_ASSERTION`, `ENVIRONMENT_CONTAMINATION`, `TIMING_RACE`, `MISSING_INFRA`, `INTENTIONAL_CHANGE`, or `UNKNOWN`. `UNKNOWN` is time-boxed and release-blocking for P0 paths.

Rules:
- [ ] Never convert a failure to skip/xfail without an issue, expiry date, owner, and unaffected control.
- [ ] Never update snapshots/goldens to make a suite green; review the semantic/raw-byte diff and require explicit approval.
- [ ] Quarantine may isolate non-P0 flaky tests for at most 14 days; it must retain artifacts and run nightly.
- [ ] Track pass-on-retry, failure signature, platform, seed, duration, and first/last bad SHA.
- [ ] Use event/state barriers, fake clocks, deterministic IDs, and fault injection; do not add sleeps.
- [ ] A platform-specific production test (PostgreSQL, Linux SIGTERM, file locking) runs on that platform rather than being weakened to a portable mock.

## 7. Risk register

Scale: probability (P), impact (I), detectability difficulty (D), each 1–5. Score = P×I×D. Blast radius states the maximum credible effect.

| Risk | Pri | P/I/D score | Evidence and blast radius | Preventive control | Detective test/monitor | Owner | Status |
|---|---|---:|---|---|---|---|---|
| R-01 Deploy bypasses CI gate | P0 | 4/5/4 = 80 | `deploy.yml` build needs only resolve; deploy needs resolve+build. Untested SHA can reach all environments | require successful immutable CI workflow/check-run and bind image digest to source SHA; production approval | CICD-001 plus deployment audit alert when gate SHA/digest differs | DevSecOps | [ ] |
| R-02 Resume marker allocates `max+1` with plain append and swallows collisions | P0 | 4/5/4 = 80 | `engine.py::_stamp_resume_marker`; duplicate seq/lost resume affects all durable runs | database-allocated/transactional sequence with unique constraint and retry; never swallow exhausted collision | DB-001/KRN-003; metric `run_event_seq_conflict_total` and sequence-gap alert | Runtime+DB | [ ] |
| R-03 Fan-out suppresses terminal/error events and shares mutable context scratch | P0 | 4/5/4 = 80 | `fanout.py`; child failure can appear successful or contaminate siblings | per-child immutable/derived context; mandatory typed event sink; structured concurrency cancellation | KRN-004/KRN-005; child/parent terminal reconciliation metric | Runtime | [ ] |
| R-04 Engine emits `step_completed` after terminal strategy return | P0 | 3/5/4 = 60 | `_dispatch_step_with_retry`; false success corrupts UI, persistence, and retries | terminal outcome type/fence checked before completion emission | KRN-006 characterization and impossible-transition monitor | Runtime | [ ] |
| R-05 `/answers` accepts terminal runs | P0 | 3/5/3 = 45 | `run_commands.py::submit_answers`; terminal mutation/restart risk | shared atomic non-terminal transition guard for every command | API-001 matrix; rejected-terminal-command counter | API | [ ] |
| R-06 SQLite-dominant tests do not prove PostgreSQL migrations/concurrency | P0 | 4/5/3 = 60 | no PostgreSQL CI service; Docker unavailable; comments overclaim | mandatory PostgreSQL service job with migration head 0032 and concurrency tests | DB-002/DB-003; schema-head startup metric | DB/Platform | [ ] |
| R-07 SSE terminal/reconnect contract is incomplete | P0 | 4/5/4 = 80 | FE terminal list omits `pipeline_complete`; CRLF chunk split/final flush untested; 15 browser settling failures | one shared event schema/reducer; streaming parser state machine; explicit readiness barriers | SSE-001..004 + E2E-002; duplicate/gap/reconnect SLOs | API+Frontend | [ ] |
| R-08 Checkpointer close is unbounded | P1 | 3/5/4 = 60 | `close_checkpointer` awaits pool.close indefinitely; shutdown can exceed grace | timeout, cancellation/escalation, structured shutdown budget | REL-001/REL-002; shutdown-stage duration/hang alert | Runtime/SRE | [ ] |
| R-09 SC-001 proof patches internal seams and name scan is narrow | P1 | 4/4/4 = 64 | no public drop-in discovery/launch proof; banned regex catches only exact equality forms | public fixture workflow copied at test runtime; AST-based kernel policy | CMP-001/KRN-001/E2E-001 | Compiler/Runtime | [ ] |
| R-10 Security scans/audits cannot block | P0 | 4/5/2 = 40 | image Trivy uses exit 0 and `|| true`; dependency audits warn-only | severity policy with approved time-bound exceptions; no shell masking | SEC-001/SEC-002; scanner-result attestation required by deploy | DevSecOps | [ ] |
| R-11 Terraform is not validated/planned in CI | P0 | 4/5/3 = 60 | CI has no Terraform binary/stages; six roots not initialized locally | pinned Terraform/providers; remote encrypted state; fmt→init→validate→plan→scan; prod approval | IAC-001..003; drift detection and plan artifact review | Platform | [ ] |
| R-12 AI/eval has no deterministic contract, budget, calibration, or injection tier | P1 | 4/4/4 = 64 | live-by-default minimal harness, no CI tier or hard limits | offline schema/fixture tier; opt-in live tier with allowlist, budget, timeout, redaction | EVAL-001..004 and cost/latency/quality dashboards | AI Eval | [ ] |
| R-13 Frontend lint/build are red | P1 | 5/4/1 = 20 | 44 lint errors; build TS failure | zero-new-debt then zero-baseline policy; build required before browser | FE-001/FE-002 required checks | Frontend | [ ] |
| R-14 Browser tests are not a reliable release signal | P1 | 5/4/2 = 40 | 60 mocked failures; fixed port reuse; incomplete fixtures; no CI | canonical fixtures, dynamic server port, no reuse in CI, readiness API, artifact retention | E2E-003/E2E-004; flake and retry dashboards | Frontend QA | [ ] |
| R-15 Sub-agent composition can flatten hierarchy | P1 | 3/4/2 = 24 | Playwright artifact shows child as second root; persistence may lose intent | normalize tree at state boundary; reject duplicate/root-child ambiguity | FE-003/E2E-005 round trip | Frontend+Compiler | [ ] |
| R-16 Workspace/owner isolation regression | P0 | 2/5/4 = 40 | scoped store is the IDOR gate; every new table must carry both scopes | repository/service APIs require scope object; DB constraints/RLS where applicable | SEC-003/API-002 cross-tenant matrix and denied-access audit alert | Security+API | [ ] |
| R-17 Observability cannot prove transition/recovery correctness | P1 | 4/4/4 = 64 | no unified SLOs for gaps, duplicates, illegal transitions, shutdown, or eval budgets | structured schema with run/workspace/event IDs; bounded-cardinality metrics and runbooks | OBS-001..004 and synthetic canary | SRE | [ ] |
| R-18 Untested code is invisible, so coverage can silently decay | P1 | 5/4/2 = 40 | baseline `ci.yml` runs `pytest tests/ -v` and `npm run test` with no `--cov`/coverage provider, no artifact, no upload; a PR adding untested modules passes every gate. Blast radius: whole-repo quality drift, with untested REST/persistence/UI reaching production unnoticed | collect coverage on every PR for `app`, `agents`, and `frontend/src`; publish artifact + per-PR delta; ratchet the floor upward per layer; require tests with new behavior in review | COV-001 (instrumentation + ratchet), COV-002 (regression gate), COV-004 (assertion-quality probe); coverage trend dashboard | QA lead + Backend/Frontend leads | [ ] |

All P0/P1 risks above have both a preventive and a detective control. A risk may close only when both are implemented and linked to evidence.

## 8. Requirement and invariant traceability

| Requirement/invariant | Preventive implementation | Detective coverage | Current state |
|---|---|---|---|
| SC-001: new workflow by manifest+AGENT.md, zero engine edits | compiler/registry discovery only; name-free kernel | CMP-001, KRN-001, E2E-001 | [ ] patched-seam tests only |
| INV-3: characterization compatibility | explicit event contracts; raw-byte goldens; `_VOLATILE_STRIP_KEYS` review | KRN-002 plus clean golden diff check | [ ] CRLF checkout contamination |
| LOCK-B: SSE down, REST up; no retired WS run frames | one transport client and banned AST rule | SSE-001..004, KRN-001 | [ ] parser/terminal gaps |
| Capability two-surface discipline (INV-12) | generate/validate `_KNOWN` and discovery bindings together | CMP-002 registry drift/runtime binding test | [ ] count-only guard insufficient alone |
| One terminal outcome; no completion after terminal | typed outcome + atomic transition fence | KRN-006, API-001, OBS-001 | [ ] known gaps |
| Monotonic unique event identity | DB transaction/sequence and uniqueness | DB-001, SSE-002, OBS-002 | [ ] race exists |
| Owner/workspace isolation | mandatory scoped APIs/columns and least privilege | SEC-003, API-002, IAC-003 | [ ] broad negative matrix needed |
| Production secrets/state protected | secret manager/OIDC; encrypted remote backend; no local shared state | SEC-001, IAC-002, drift/access logs | [ ] CI proof missing |
| Production approval and tested artifact | CI gate + digest promotion | CICD-001/CICD-002 | [ ] deploy bypass exists |
| Graceful bounded shutdown/recovery | bounded stage timeouts and durable resume | REL-001..003, synthetic restart | [ ] unbounded pool close |

## 9. Domain strategies

### Compiler and kernel
- [ ] Test public manifest discovery, compilation, registration, and launch without monkeypatching loader/compiler seams.
- [ ] Replace regex name scans with AST/import-boundary policies that catch comparisons, mappings, membership, helper aliases, and match statements.
- [ ] Model step results as `Succeeded | Failed | Cancelled | Paused`; only `Succeeded` may emit `step_completed`.
- [ ] Use deterministic model doubles and assert semantic event order before canonicalized snapshots.

### Persistence and API
- [ ] Add PostgreSQL transactional/concurrency tests for sequence allocation, resume, idempotency, locking, migration head, upgrade/downgrade, and owner/workspace scope.
- [ ] Centralize atomic transition guards used by gate, answers, cancel, messages, and revisions.
- [ ] Test disconnect/retry after commit but before response to prove idempotency.

### SSE and frontend
- [ ] Publish a shared event schema/fixture catalog; assert every documented type has parser, reducer, persistence, and UI behavior.
- [ ] Feed parser arbitrary byte boundaries including split `\r\n`, split UTF-8, multiple events, comments, empty chunks, and decoder final flush.
- [ ] Make mocked SSE expose attachment/event-state barriers and unique per-test run IDs.
- [ ] Test run switching, replay, duplicate IDs, out-of-order/gap policy, terminal convergence, and cross-run contamination.

### Browser and UX
- [ ] Derive mock catalog fixtures from canonical workflow/agent data or contract-check them at startup.
- [ ] Use dynamic isolated web-server ports and `reuseExistingServer: false` in CI.
- [ ] Prefer accessible roles scoped to stable regions; use test IDs only for semantic surfaces without stable accessible names.
- [ ] Add axe checks for login, dashboard, execution, gate, history, and composer; add only high-value visual snapshots with reviewed masks/fonts/viewports.

### AI and evaluation
- [ ] Separate deterministic offline contract tests from explicitly authorized live evaluations.
- [ ] Validate dataset/rubric schemas, stable IDs, expected workflow, judge prompt/version, and malformed/adversarial rows before any provider call.
- [ ] Enforce per-case and run-level token/cost/latency budgets with cancellation; redact prompts/outputs in artifacts.
- [ ] Calibrate judges against human-labeled anchors; report agreement and confidence, not only mean score.
- [ ] Add prompt-injection, data-exfiltration, tool-authorization, malformed-output, and deterministic PPT structure/render checks. Do not add RAG tests because the repository has no semantic/vector RAG.

### Security, IaC, reliability, observability
- [ ] Make secret, dependency, IaC, and image policies blocking with expiring exception files.
- [ ] Validate every Terraform root in an ephemeral workspace; use encrypted remote state for shared environments and never local state.
- [ ] Exercise Linux SIGTERM with a live SSE connection, PostgreSQL checkpointer, and bounded stop budget.
- [ ] Emit structured transition/shutdown/replay metrics without prompt, secret, token, or deliverable content.

## 10. Prioritized concrete test cases

Every P0/P1 case contains evidence, objective, level, prerequisites, steps/fault, oracle, preventive control, detective placement, owner, dependencies, and status.

### P0 cases

#### [ ] CICD-001 — Deploy requires the exact successful CI SHA and image digest
- **Risk/evidence:** R-01; deploy currently bypasses `gate`.
- **Objective/level:** workflow-policy test; prove no environment deploys an untested artifact.
- **Prerequisites:** synthetic workflow event matrix; no cloud credentials.
- **Steps/fault:** evaluate success, failed, skipped, and missing CI checks; mutate source SHA and image digest after build.
- **Oracle:** deploy job is unreachable unless gate succeeded for the same SHA and signed digest; production additionally requires approval.
- **Preventive control:** explicit `needs: gate`, protected environment, digest-only promotion.
- **Detective placement:** PR workflow-lint plus release attestation check.
- **Owner/dependencies:** DevSecOps; depends on workflow permissions and artifact metadata.

#### [ ] DB-001 — Concurrent resume event allocation is unique and gap policy is explicit
- **Risk/evidence:** R-02; read-max+1 append in `_stamp_resume_marker`.
- **Objective/level:** PostgreSQL integration/concurrency.
- **Prerequisites:** migrated PostgreSQL head 0032; one scoped run; N independent transactions.
- **Steps/fault:** synchronize 20 resume writers at a barrier; inject serialization/unique conflicts and retry exhaustion.
- **Oracle:** one unique monotonic seq/event ID per committed row, no swallowed write, deterministic retry or surfaced terminal error.
- **Preventive control:** DB sequence/atomic allocator and bounded retry.
- **Detective placement:** required PostgreSQL CI; conflict/gap metrics in production.
- **Owner/dependencies:** Runtime+DB; schema and store change.

#### [ ] KRN-004 — Fan-out child failure propagates exactly one parent failure
- **Risk/evidence:** R-03; optional queue suppresses child terminal/error events.
- **Objective/level:** deterministic kernel integration.
- **Prerequisites:** three scripted children, event recorder.
- **Steps/fault:** child B fails before/after siblings complete; omit optional queue path.
- **Oracle:** child failure is observable, parent has one terminal outcome, no later `step_completed`/pipeline success.
- **Preventive control:** mandatory typed event sink and structured task group.
- **Detective placement:** Linux offline PR suite and characterization event-order assertion.
- **Owner/dependencies:** Runtime; event protocol.

#### [ ] KRN-005 — Fan-out children cannot mutate sibling context
- **Risk/evidence:** R-03; shared `ExecutionContext.scratch`.
- **Objective/level:** race/property integration.
- **Prerequisites:** unique child keys and synchronized writes.
- **Steps/fault:** interleave writes/reads across 50 seeded schedules.
- **Oracle:** each child sees parent snapshot plus its own mutations only; merge is explicit/deterministic.
- **Preventive control:** immutable parent and child-local context.
- **Detective placement:** PR property test; race seed retained on failure.
- **Owner/dependencies:** Runtime; context API redesign.

#### [ ] KRN-006 — Terminal strategy result cannot emit `step_completed`
- **Risk/evidence:** R-04; engine emits completion after terminal return.
- **Objective/level:** engine unit/characterization.
- **Prerequisites:** scripted cancel and failure strategies.
- **Steps/fault:** yield terminal event then return normally; repeat during retry.
- **Oracle:** no completion event, retry, gate, or pipeline success after terminal; terminal appears once.
- **Preventive control:** typed outcome and transition fence.
- **Detective placement:** required backend PR suite plus illegal-transition monitor.
- **Owner/dependencies:** Runtime; event contract update.

#### [ ] API-001 — Every mutating command rejects every terminal status atomically
- **Risk/evidence:** R-05; `/answers` lacks terminal fence.
- **Objective/level:** API+PostgreSQL matrix.
- **Prerequisites:** owner-scoped runs in completed, failed, cancelled and each non-terminal state.
- **Steps/fault:** POST gate/answers/cancel/messages/revisions concurrently with terminal commit.
- **Oracle:** terminal runs return stable 409/no mutation; exactly one transition wins; non-terminal behavior remains valid.
- **Preventive control:** shared store-level compare-and-transition guard.
- **Detective placement:** required API integration; rejected command metric.
- **Owner/dependencies:** API+DB; transition service.

#### [ ] DB-002 — PostgreSQL migration chain and model schema agree at head 0032
- **Risk/evidence:** R-06; SQLite-dominant suite and stale xfails.
- **Objective/level:** real PostgreSQL migration integration.
- **Prerequisites:** disposable DB, least-privilege migration identity.
- **Steps/fault:** upgrade base→head, compare tables/columns/indexes/constraints, downgrade supported boundary, re-upgrade; test repaired 0024/0029 path.
- **Oracle:** head `0032`, expected scopes/constraints exist, no drift or duplicate-drop failure.
- **Preventive control:** additive migrations and immutable applied revisions.
- **Detective placement:** required Linux PostgreSQL CI.
- **Owner/dependencies:** DB; PostgreSQL service.

#### [ ] SSE-001 — Streaming parser survives arbitrary transport chunking
- **Risk/evidence:** R-07; split CRLF and decoder flush untested.
- **Objective/level:** frontend property/unit.
- **Prerequisites:** canonical SSE byte stream with Unicode, comments, IDs, multiline data.
- **Steps/fault:** split at every byte boundary and randomized partitions; terminate with pending decoder bytes.
- **Oracle:** same ordered frames and IDs as unsplit input; no truncation/duplication; final decoder flush occurs.
- **Preventive control:** incremental decoder/parser state machine.
- **Detective placement:** required Vitest property suite.
- **Owner/dependencies:** Frontend; parser seam.

#### [ ] SSE-002 — Replay/reconnect is exact-once across persisted and live tails
- **Risk/evidence:** R-02/R-07; duplicate/gap and 15 settling failures.
- **Objective/level:** PostgreSQL+API+mounted frontend integration.
- **Prerequisites:** persisted events, live writer, Last-Event-ID cursor.
- **Steps/fault:** disconnect before/after commit, reconnect with stale/current/future cursor, overlap REST backfill and SSE tail.
- **Oracle:** each event identity reduced once in semantic order; explicit error/recovery for gaps; terminal convergence.
- **Preventive control:** authoritative ID merge and idempotent reducer.
- **Detective placement:** integration CI and duplicate/gap SLOs.
- **Owner/dependencies:** API+Frontend+DB.

#### [ ] SSE-003 — `pipeline_complete` is terminal in every client path
- **Risk/evidence:** R-07; terminal list omission.
- **Objective/level:** hook/provider/component test.
- **Prerequisites:** live run store and complete event with/without deliverable.
- **Steps/fault:** send complete during normal stream, replay, run switch, and reconnect.
- **Oracle:** stream ownership settles, spinner stops, actions disable, status persists completed, no reconnect loop.
- **Preventive control:** one shared terminal-event predicate/schema.
- **Detective placement:** Vitest + mocked browser + stuck-running monitor.
- **Owner/dependencies:** Frontend/API; shared event types.

#### [ ] SEC-001 — Security findings block build/deploy without shell masking
- **Risk/evidence:** R-10; Trivy exit 0/`|| true`, warn-only audits.
- **Objective/level:** CI policy test.
- **Prerequisites:** synthetic HIGH image/IaC finding and allowlisted-expiring exception.
- **Steps/fault:** run each scanner with finding, tool crash, missing report, valid exception, expired exception.
- **Oracle:** finding/crash/missing report blocks; only valid scoped exception permits; deploy consumes attestations.
- **Preventive control:** central severity policy and exception schema.
- **Detective placement:** every PR/image and deploy precondition.
- **Owner/dependencies:** DevSecOps; scanner availability.

#### [ ] SEC-003 — Cross-owner/workspace access is denied on every run endpoint
- **Risk/evidence:** R-16; scoped store is the IDOR gate.
- **Objective/level:** API authorization matrix.
- **Prerequisites:** two owners × two workspaces; runs/events/files/artifacts/checkpoints.
- **Steps/fault:** enumerate GET/stream and all REST commands with foreign IDs, guessed IDs, and mixed scope claims.
- **Oracle:** uniform non-disclosing denial, zero state mutation/stream bytes, audit event without sensitive payload.
- **Preventive control:** mandatory scope object and scoped repository methods.
- **Detective placement:** required security integration; denied-access anomaly alert.
- **Owner/dependencies:** Security+API+DB.

#### [ ] IAC-001 — Every Terraform root initializes and validates reproducibly
- **Risk/evidence:** R-11; no CI Terraform and local roots uninitialized.
- **Objective/level:** IaC static integration.
- **Prerequisites:** pinned Terraform/provider cache, committed lockfiles, ephemeral workspace, no cloud credentials.
- **Steps/fault:** for six roots run fmt, `init -backend=false`, validate, TFLint, Checkov/Trivy config.
- **Oracle:** all roots validate; no public/open-network/unencrypted/untagged violations; no lockfile drift.
- **Preventive control:** reusable secure modules, version pins, validations.
- **Detective placement:** required PR IaC job.
- **Owner/dependencies:** Platform; provider cache/network.

#### [ ] CICD-002 — Production provision cannot mutate from an unapproved ref
- **Risk/evidence:** R-01/R-11; manual production-capable provision path lacks source-ref/CI enforcement.
- **Objective/level:** workflow policy/negative test.
- **Prerequisites:** event/ref/environment matrix.
- **Steps/fault:** invoke from feature branch, tag without CI, fork, stale SHA, approved protected ref.
- **Oracle:** only protected tested SHA plus environment approval reaches plan/apply; plan digest is the applied digest.
- **Preventive control:** reusable gated workflow, OIDC, protected environment.
- **Detective placement:** workflow policy test and cloud audit alert.
- **Owner/dependencies:** DevSecOps+Platform.

### P1 cases

#### [ ] CMP-001 — True drop-in workflow proves SC-001 through public APIs
- **Risk/evidence:** R-09; existing tests patch seams.
- **Objective/level:** compiler/runtime integration.
- **Prerequisites:** temporary brand-new workflow directory containing only manifest+AGENT.md and registered generic capabilities.
- **Steps/fault:** discover, compile, list, launch, execute, produce deliverable; use an unseen workflow ID.
- **Oracle:** zero source edits/patches, no name branch, expected events/deliverable, public catalog visibility.
- **Preventive control:** manifest-driven discovery and capability metadata.
- **Detective placement:** required Linux backend and one mounted E2E.
- **Owner/dependencies:** Compiler+Runtime; fixture installation seam.

#### [ ] KRN-001 — AST policy forbids workflow identity coupling and retired transports
- **Risk/evidence:** R-09 and LOCK-B; regex is narrow.
- **Objective/level:** static architecture test.
- **Prerequisites:** AST parser and import-boundary rules.
- **Steps/fault:** mutation fixtures using equality, inequality, membership, dict lookup, match, alias helper, and retired WS tokens.
- **Oracle:** every semantic identity coupling is rejected; benign logging/typed metadata is handled by explicit policy.
- **Preventive control:** kernel API excludes workflow identity decisions.
- **Detective placement:** fast PR architecture job.
- **Owner/dependencies:** Runtime Architecture.

#### [ ] KRN-002 — Characterization preserves semantic event order and raw bytes
- **Risk/evidence:** INV-3; current normalizer canonical-sorts; CRLF checkout contamination.
- **Objective/level:** deterministic characterization.
- **Prerequisites:** LF/blob-identical byte goldens and scripted models.
- **Steps/fault:** reorder two semantically dependent events; alter one output byte; add documented volatile field.
- **Oracle:** order and byte mutations fail; permitted volatile field does not; golden directory remains unchanged by normal run.
- **Preventive control:** event-aware normalizer and `-text` golden attributes.
- **Detective placement:** required backend job plus golden git-diff guard.
- **Owner/dependencies:** Runtime QA.

#### [ ] REL-001 — Linux SIGTERM reaches and completes bounded shutdown with live SSE
- **Risk/evidence:** R-08; Windows signal test invalid; production is Linux.
- **Objective/level:** production-like process integration.
- **Prerequisites:** Linux container, live SSE socket, PostgreSQL pool/checkpointer.
- **Steps/fault:** SIGTERM during stream; stall each shutdown stage including pool close.
- **Oracle:** lifespan shutdown entered, each stage times out/escalates as designed, process exits before stop grace, run remains resumable.
- **Preventive control:** bounded stage deadlines and cancellation.
- **Detective placement:** nightly/release reliability job; shutdown histograms.
- **Owner/dependencies:** SRE+Runtime; container/PostgreSQL.

#### [ ] EVAL-001 — Eval input/rubric contract rejects unsafe or malformed rows offline
- **Risk/evidence:** R-12; no schema or injection tier.
- **Objective/level:** offline eval unit/contract.
- **Prerequisites:** JSON schema and adversarial fixture corpus.
- **Steps/fault:** missing IDs, unknown workflow, oversized prompts, prompt injection, secret-like data, malformed expected artifacts.
- **Oracle:** deterministic preflight rejection before provider construction/call; reason is redacted and actionable.
- **Preventive control:** strict schemas, allowlists, size/redaction policy.
- **Detective placement:** fast backend PR tier.
- **Owner/dependencies:** AI Eval+Security.

#### [ ] EVAL-002 — Live eval enforces hard cost, token, latency, and concurrency budgets
- **Risk/evidence:** R-12; harness is billable/live by default.
- **Objective/level:** explicitly authorized live canary.
- **Prerequisites:** approved provider, exact model allowlist, run budget, owner, kill switch.
- **Steps/fault:** approach/exceed per-case and run budgets; timeout and provider error.
- **Oracle:** no call without opt-in; cancellation before overrun; total cost/latency reported; artifacts redacted.
- **Preventive control:** default-off live mode and budget controller.
- **Detective placement:** scheduled/manual protected job only.
- **Owner/dependencies:** AI Eval+FinOps; credentials and written cost limit.

#### [ ] AI-001 — Untrusted prompt content cannot override tool, scope, or secret policy
- **Risk/evidence:** R-12/R-16; workflows consume user/uploaded/context text while privileged capabilities and scoped data require independent enforcement.
- **Objective/level:** offline adversarial agent/tool-policy integration.
- **Prerequisites:** deterministic model double, malicious prompt/upload corpus, two workspace scopes, fake canary secret, denied privileged tool.
- **Steps/fault:** inject instructions to reveal system/context data, cross workspace boundaries, invoke `spawn_subagents`/privileged gates, alter workflow policy, and exfiltrate the canary through output or logs.
- **Oracle:** policy and scope checks remain authoritative; denied calls do not execute; no canary or foreign content appears in events, output, traces, or logs; safe workflow behavior continues or fails closed.
- **Preventive control:** capability authorization outside model text, scoped stores, input/output size/redaction policy, and least-privilege tool exposure.
- **Detective placement:** offline PR adversarial corpus plus denied-tool/data-loss metrics in protected live canaries.
- **Owner/dependencies:** AI Security+Runtime; deterministic tool harness and redaction assertions.

#### [ ] FE-001 — Frontend lint and production build are zero-error required checks
- **Risk/evidence:** R-13; 44 errors and TypeScript build failure.
- **Objective/level:** static/build.
- **Prerequisites:** pinned Node/npm lock install.
- **Steps/fault:** run lint and build; mutation samples hook-order/ref/purity/type errors.
- **Oracle:** zero errors and successful bundle/typecheck; warnings have ratchet budget.
- **Preventive control:** typed hook patterns and no test helpers in production type surface where inappropriate.
- **Detective placement:** required PR checks.
- **Owner/dependencies:** Frontend.

#### [ ] E2E-003 — Mock fixture catalog matches canonical workflow agent declarations
- **Risk/evidence:** R-14; five-entry fixture causes false failures.
- **Objective/level:** fixture contract.
- **Prerequisites:** exported canonical catalog or generated fixture artifact.
- **Steps/fault:** compare every launchable workflow's agent IDs/count/order and capability references.
- **Oracle:** no missing/orphan IDs; expected user-story and migration lineups resolve before browser launch.
- **Preventive control:** generated/shared fixture source.
- **Detective placement:** fast Playwright setup contract.
- **Owner/dependencies:** Frontend QA+Compiler.

#### [ ] E2E-002 — Mock SSE start barrier proves attachment before UI assertions
- **Risk/evidence:** R-07/R-14; seven run-chat setup failures.
- **Objective/level:** harness integration.
- **Prerequisites:** `startAttachedRun` helper with unique run ID.
- **Steps/fault:** delay live-run refresh, stream attach, and first frame independently.
- **Oracle:** helper resolves only after attach and execution-view reduction; no sleep; timeout reports exact stage.
- **Preventive control:** explicit readiness API and per-test store reset.
- **Detective placement:** mocked browser PR tier.
- **Owner/dependencies:** Frontend QA.

#### [ ] E2E-005 — Sub-agent hierarchy survives add, save, reload, compile, and launch
- **Risk/evidence:** R-15; child flattened as root.
- **Objective/level:** component + browser contract.
- **Prerequisites:** one root and one child with deterministic semantic IDs.
- **Steps/fault:** add via child action, inspect tree, save, reload, compile, launch payload.
- **Oracle:** exactly one root/one child at every boundary; no duplicate root; child configuration preserved.
- **Preventive control:** normalized tree state and schema validation.
- **Detective placement:** focused component test plus mocked E2E.
- **Owner/dependencies:** Frontend+Compiler.

#### [ ] OBS-001 — Illegal run transitions page the owning service with useful context
- **Risk/evidence:** R-17; false terminal/completion paths lack unified detection.
- **Objective/level:** telemetry contract/synthetic.
- **Prerequisites:** structured event schema and test exporter.
- **Steps/fault:** emit completion-after-terminal, duplicate terminal, backward status, and cross-run event.
- **Oracle:** counter increments once with run/event/workspace hash and code location; no prompt/output/secret; alert links runbook.
- **Preventive control:** transition state machine.
- **Detective placement:** unit telemetry test and production alert.
- **Owner/dependencies:** SRE+Runtime.

#### [ ] COV-001 — Coverage is measured, published, and ratcheted for backend and frontend
- **Risk/evidence:** R-18; baseline `ci.yml` runs `pytest tests/ -v` and `npm run test` with no coverage collection, so no measured number exists for `app/`, `agents/`, or `frontend/src`.
- **Objective/level:** CI instrumentation and policy control, not a product test.
- **Prerequisites:** `coverage[toml]` in backend dev requirements; `@vitest/coverage-v8` in frontend dev dependencies; `[tool.coverage.*]` source/omit/exclude rules; Vitest `coverage` block excluding test files and generated output; artifact retention configured.
- **Steps/fault:** run both suites with coverage on a PR; publish HTML/XML/JSON artifacts and the per-PR delta; then inject three faults — delete a covered test, add an untested module, and break the coverage step itself.
- **Oracle:** a measured percentage is produced per layer and per file with uncovered line numbers; deleting a test lowers the reported number; a new untested module appears at 0% in the report; a broken or missing coverage step fails the job rather than silently reporting nothing. Characterization goldens and generated code are excluded from the percentage but still run.
- **Preventive control:** coverage configuration lives in `pyproject.toml` and `vitest.config.ts` (not ad-hoc CLI flags) so local and CI numbers match; floors are declared per layer and only ever raised.
- **Detective placement:** required PR job for backend and frontend, with artifact upload on `always()` so a failed suite still yields a report; trend dashboard for history.
- **Owner/dependencies:** QA lead + Backend/Frontend leads; depends on the staged post-baseline edits being committed and on Phase 0 producing a green suite, because a red suite yields a misleading number.

### P2 follow-up catalog

- [ ] CMP-002 test every `_KNOWN` capability has one discovered implementation and matching metadata.
- [ ] API-002 fuzz malformed IDs, oversized commands, duplicate idempotency keys, and content-type errors.
- [ ] DB-003 test migration/transaction deadlock retry and pool exhaustion against PostgreSQL.
- [ ] SSE-004 test run switching and foreign-run frames cannot clear/overwrite viewed state.
- [ ] FE-002 fix/pin local-calendar tests at midnight/DST boundaries with Date-only fake timers.
- [ ] FE-003 component-test sub-agent state transition before browser round trip.
- [ ] E2E-004 run mocked browser tests on Chromium/Firefox with isolated dynamic ports and zero retries first.
- [ ] EVAL-003 calibrate judge agreement against human anchors and version judge prompts/models.
- [ ] EVAL-004 deterministic PPT package/schema/font/overflow/render checks at fixed viewport.
- [ ] SEC-002 verify SBOM, provenance/signature, dependency audit policy, and test-fixture secret allowlist boundaries.
- [ ] COV-002 fail a PR when total or per-layer coverage falls below the committed floor, and when a file touched by the PR drops in coverage; require a written exception with owner and expiry to override.
- [ ] COV-003 publish an untested-module inventory (every production file at 0%) from the coverage JSON and keep it shrinking release over release.
- [ ] COV-004 probe assertion quality on P0 modules with targeted mutation or fault injection so a high percentage cannot be earned by executing lines without asserting behavior.
- [ ] COV-005 report browser-tier coverage separately (or explicitly declare it out of scope) so mocked Playwright execution is never counted as unit coverage of untested modules.
- [ ] PERF-001 define and load-test SSE concurrent connections, replay latency, and DB pool saturation.
- [ ] REL-002 fault-inject checkpointer/pump/concierge shutdown stages and verify bounded escalation.
- [ ] REL-003 restart during each run phase and prove deterministic resume or explicit terminal failure.
- [ ] IAC-002 test remote backend encryption, versioning, lock, public-access block, least privilege, and per-env keys.
- [ ] IAC-003 policy-test private networking, TLS, encryption, diagnostics, mandatory tags, and no `0.0.0.0/0`.
- [ ] OBS-002 monitor seq gaps/duplicates/replay age; OBS-003 monitor stuck run/gate age; OBS-004 monitor eval cost/latency/quality.

### Coverage uplift backlog (per-layer)

Targets are directional and become binding only after COV-001 publishes the first measured baseline. The "estimated now" column is an **unmeasured** structural estimate from test-to-source inspection at `0520e2f`, not a coverage run; replace it with real numbers before treating any floor as a gate. Order the work by risk, not by percentage distance.

| Layer | Estimated now (unmeasured) | Interim floor | Target | Highest-value work | Depends on |
|---|---|---|---|---|---|
| [ ] Backend kernel + capability ports | high | hold, no regression | hold | keep characterization and port contracts green while KRN-004..006 land | Phase 1 |
| [ ] Backend REST API (`app/api`) | low | rises with API-001/SEC-003 | high | status/authorization/error responses per endpoint, not just happy path | API-001, SEC-003 |
| [ ] Backend persistence and migrations | low | rises with DB-001/DB-002 | high | scope columns, constraints, upgrade/downgrade, concurrent sequence allocation | PostgreSQL CI |
| [ ] Backend concrete capabilities | mixed | no regression, then rise | medium-high | context providers, compaction, deliverable resolvers, merge strategies and their failure paths | Phase 1 |
| [ ] Frontend hooks, store, transport | medium | no regression, then rise | high | reducer identity/terminal/reconnect paths pinned by SSE-001..004 | Phase 2 |
| [ ] Frontend components and forms | low | rises with FE-001 green | medium-high | gate, clarify, deliverable, composer surfaces plus validation states | Phase 2 |
| [ ] Error and recovery paths (cross-layer) | low | tracked separately from line % | explicit case list | budget exceeded, provider failure, cancel during fan-out, replay gap | Phases 1–3, 5 |

Uplift rules:
- [ ] Add tests with the behavior change in the same PR; do not schedule coverage as a later cleanup pass.
- [ ] Spend effort on the risk-ranked list above before chasing a repository-wide number.
- [ ] Never raise a percentage by asserting less, deleting a failing test, loosening a golden, or testing generated code.
- [ ] Record any deliberately untestable line with a reason next to its exclusion pragma, and review those exclusions each release.
- [ ] Re-read the floors after Phase 0, because a red suite cannot produce a trustworthy baseline.

## 11. Target CI matrix and dependency graph

| Tier | Trigger | Environment | Required jobs and exit policy | Target budget |
|---|---|---|---|---|
| T0 preflight | every PR | Linux | lock integrity, compileall, frontend type/lint, Terraform fmt, workflow policy, secret scan; all blocking | ≤5 min |
| T1 deterministic | every PR | Linux + Windows portability shard | offline pytest excluding live/eval, Vitest, architecture/import policies, characterization with `SNAPSHOT_UPDATE` unset; backend and frontend coverage collected, published as artifacts, and checked against the committed floor | ≤12 min |
| T2 integration | every PR affecting backend/DB/transport | Linux + PostgreSQL | migration head 0032, API/authz, sequence concurrency, SSE replay, shutdown unit budgets | ≤15 min |
| T3 browser mocked | every PR affecting FE/API contracts | isolated Linux Chromium | canonical fixtures, dynamic port, 194 mocked tests after triage; no `reuseExistingServer`; retain failure trace/video | ≤15 min |
| T4 security/IaC | every PR/image | Linux | init/validate all Terraform roots, TFLint, Checkov/Trivy config, dependency audits, image Trivy, Gitleaks; blocking | ≤15 min parallel |
| T5 nightly | schedule | Linux + PostgreSQL; multi-browser | race/property seeds, restart/SIGTERM, long SSE, Firefox, performance smoke, quarantined tests | ≤60 min |
| T6 live eval | protected manual/schedule | approved provider | small canary only; default-off; hard cost/latency/token limit; redacted artifacts | explicit budget |
| T7 release | approved tag/SHA | production-like | all required checks, migration rehearsal, signed digest/SBOM, rollback verification, approval | blocking |

```text
T0 ─┬─> T1 backend ─┬─> T2 PostgreSQL/SSE ─┐
    ├─> T1 frontend ─┴─> T3 mocked browser ├─> release gate ─> build digest
    └─> T4 security/IaC ────────────────────┘                    │
                                                     image scan/sign/attest
                                                                │
                                               environment approval -> deploy
```

- [ ] Configure branch protection so every arrow into release gate is required, not advisory.
- [ ] Cancel superseded PR runs, but never cancel release/security evidence after artifact creation.
- [ ] Upload JUnit/JSON, traces only on failure, scanner SARIF, Terraform plan, SBOM, digest attestations, and backend/frontend coverage reports with retention and no secrets.
- [ ] Upload coverage on `always()` so a failing suite still yields a report, and fail the job when the coverage step itself errors rather than reporting nothing.
- [ ] Split tests by historical duration; do not hide failures with automatic retries. One diagnostic retry may measure flakiness but original status remains red.

## 12. Security and AI evaluation

Security exit controls:
- [ ] No hardcoded credentials, state, key material, or secret-bearing tfvars are tracked; scan shipping code plus deliberately fake test fixtures.
- [ ] Revisit broad Gitleaks allowlists for `backend/tests/**` and `frontend/e2e/**`; replace with narrow fingerprint/path rules so real leaked secrets in tests still fail.
- [ ] Require SAST/dependency/image/IaC results and expiring exceptions before deploy.
- [ ] Add API abuse tests for IDOR, JWT expiry, replay, oversized upload/message, content type, path traversal/symlink escape, iframe sandbox/XSS, and command authorization.
- [ ] Store no prompts, outputs, uploaded contents, tokens, connection strings, or secrets in logs/traces by default.

AI evaluation ladder:
1. [ ] Offline preflight: schema, deterministic fixtures, prompt template snapshots, tool-policy, injection corpus, output parser, PPT structural checks.
2. [ ] Recorded/stubbed provider contract: streaming/tool/error/timeout/rate-limit shapes without network.
3. [ ] Protected live smoke: one row/model, explicit authorization and maximum cost.
4. [ ] Nightly benchmark: versioned dataset/rubric/judge, confidence intervals, regression thresholds, latency/cost budgets.
5. [ ] Human calibration: blind sample review, inter-rater agreement, judge drift investigation.

No live LLM/provider call is permitted until the job records approver, exact model, dataset size, maximum spend, timeout, concurrency, artifact redaction, and kill switch.

## 13. Infrastructure and deployment

- [ ] Pin Terraform CLI/provider versions and commit `.terraform.lock.hcl` for every root.
- [ ] Use encrypted, TLS-protected remote state with lock, versioning/soft-delete, audit logging, network restriction, per-environment key, and least-privilege OIDC identity. Never use local state for shared dev/test/stage/prod.
- [ ] Pipeline order: fmt → init → validate → test/policy → plan → security scan → plan approval → apply. Never run `apply` in PR or this audit.
- [ ] Ensure reusable modules have typed/described/validated inputs, secure defaults, mandatory merged tags, diagnostics, private access, TLS/encryption, and no embedded environment IDs/secrets.
- [ ] Make production provision/deploy accept only a reviewed plan/digest from the same protected SHA.
- [ ] Rehearse migration and application rollback separately; database rollback defaults to forward-fix when destructive downgrade would risk data.
- [ ] Add scheduled drift detection with read-only identity and alert on unmanaged/public/security-sensitive changes.

## 14. Observability, rollback, and recovery

Required SLOs (final thresholds must be approved from production baselines):

| Signal | Initial objective | Alert/runbook action |
|---|---|---|
| Illegal/duplicate terminal transitions | 0 | page Runtime; fence run and preserve event ledger |
| Duplicate event IDs or committed seq collisions | 0 | page DB/Runtime; stop affected resume path |
| SSE replay duplicate/gap rate | <0.01% sessions; zero silent gaps | investigate cursor/store, force bounded resync |
| Reconnect convergence | 99.9% within 30s | check stream/provider/store health |
| Stuck non-terminal run | none beyond workflow SLO + grace | inspect driver/checkpoint; cancel/resume runbook |
| Graceful shutdown | p99 below stop grace with ≥10s margin | block rollout; retain old tasks; inspect stage spans |
| Eval spend/latency | within approved run budget | kill live job and revoke provider concurrency |
| Deploy rollback | service restored within approved RTO | promote prior signed digest; forward-fix DB |

- [ ] Emit spans for compile, each step/attempt/gate, event persist, replay, command transition, and shutdown stage using hashed scoped IDs.
- [ ] Correlate deployment SHA/digest, migration head, workflow manifest version, model ID, and evaluator version.
- [ ] Create runbooks for stuck run, replay gap, DB pool exhaustion, provider outage, failed migration, scanner outage, and rollback.
- [ ] Synthetic canary: launch deterministic workflow, stream, disconnect/reconnect, gate/cancel, verify terminal ledger, then delete under scope.
- [ ] Recovery drill quarterly: restore remote state/database backup in isolated account, validate checksums/scopes, and measure RPO/RTO.

## 15. Tooling rationale

Use existing tools first: pytest/pytest-asyncio/Hypothesis for backend contracts and races; Vitest/Testing Library for reducers/hooks/components; Playwright for mounted-app/browser boundaries; PostgreSQL for production semantics; Ruff/Pyright/import-linter for fast Python quality; ESLint/TypeScript/Next build for frontend; Terraform validate/test plus TFLint and Checkov/Trivy config for IaC; Gitleaks and dependency/image scanners for supply chain.

Do not add a new framework merely to duplicate an existing layer. Add axe only for automated accessibility smoke, a load tool only after PERF-001 defines a reproducible workload, and SBOM/signing tooling only as part of the release-attestation control. Pin any added dependency exactly, review provenance, and make its failure policy explicit.

Coverage is risk/flow based, not a blanket line-percentage target. Line/branch coverage may prevent regression of touched critical modules, but release decisions use invariant coverage, mutation/fault sensitivity, escaped defects, flake rate, and production SLOs.

## 16. Gap analysis

| Gap | Current evidence | Target | Roadmap |
|---|---|---|---|
| Truthful baseline | multiple red suites and platform ambiguity | zero unexplained failures; explicit platform shards | Phase 0 |
| Production DB | SQLite dominant | PostgreSQL required integration | Phase 1 |
| Kernel concurrency/terminal | known sequence/fan-out/terminal risks | atomic allocator, isolated contexts, typed transitions | Phase 1 |
| Transport | parser/terminal/readiness gaps | exact-once replay and convergent UI | Phase 2 |
| Browser | 60 failures, no CI | canonical deterministic green mocked tier | Phase 2 |
| AI quality/safety | live minimal harness only | offline contracts + budgeted calibrated eval | Phase 3 |
| Security/IaC | warn-only/bypassed/unvalidated | blocking attestations and validated plans | Phase 4 |
| Reliability/ops | unbounded close, no unified SLO | bounded shutdown, drills, alerts/runbooks | Phase 5 |
| Coverage visibility | not measured at baseline; instrumentation staged, uncommitted, unexecuted | measured per layer, published per PR, floors ratcheted upward | Phase 0 instrument, Phases 1–2 uplift |

## 17. Phases 0–5 roadmap

### Phase 0 — Restore truthful gates (1–2 weeks)
- [ ] Fix default UTF-8 reads/platform collection, declare markers, pin golden EOL without changing golden content.
- [ ] Remove stale strict xfails; classify/own every remaining backend failure.
- [ ] Fix Vitest local-date fixtures, frontend build error, and all lint errors; establish warning ratchet.
- [ ] Repair browser fixtures/locators/readiness; isolate the 15 unknown settling failures; no bulk skip/update.
- [ ] Wire deploy to CI gate and make current scanners blocking.
- [ ] Commit and execute the staged coverage instrumentation (COV-001), then record the first measured backend and frontend baseline in this document, replacing every estimate.
- [ ] Publish the untested-module inventory (COV-003) and set interim per-layer floors from the measured baseline — floors only, no repository-wide target yet.

### Phase 1 — Kernel, PostgreSQL, and authorization (2–4 weeks; depends on Phase 0)
- [ ] Implement DB-001, DB-002, KRN-004..006, API-001, and SEC-003.
- [ ] Add Linux PostgreSQL CI and migration head assertion.
- [ ] Fix API-prefix path confinement and cross-platform tests.
- [ ] Raise REST API and persistence coverage as a by-product of the cases above; enable the COV-002 regression gate for touched files once the floors hold for a full week.

### Phase 2 — SSE/frontend/browser contracts (2–3 weeks; depends on Phase 1 event contract)
- [ ] Implement SSE-001..004 and shared terminal predicate/schema.
- [ ] Introduce explicit MockSse barriers, dynamic isolated server, canonical fixtures.
- [ ] Fix sub-agent hierarchy and round-trip coverage; make mocked browser tier required.
- [ ] Raise frontend hook, store, component, and form coverage toward the Section 10 targets; keep browser-tier coverage reported separately (COV-005).

### Phase 3 — AI evaluation and product quality (2–3 weeks; can begin after Phase 0)
- [ ] Implement EVAL-001/003/004 offline.
- [ ] Define versioned benchmark, rubric, human anchors, regression and cost/latency thresholds.
- [ ] Enable EVAL-002 only after written authorization and budget.

### Phase 4 — IaC and supply-chain enforcement (2–3 weeks; can run parallel after Phase 0)
- [ ] Implement IAC-001..003, SEC-001/002, SBOM/signing/provenance, and protected plan/apply.
- [ ] Validate all roots with remote-state/environment isolation policies.

### Phase 5 — Reliability and operations (ongoing; release-blocking subset 2–3 weeks)
- [ ] Bound checkpointer close; implement REL-001..003.
- [ ] Implement OBS-001..004, SLO dashboards, alerts, synthetic canary, rollback/restore drills.
- [ ] Add performance baselines and capacity thresholds after workload approval.
- [ ] Add COV-004 assertion-quality probes on P0 modules and review coverage exclusions each release so the number keeps meaning something.

## 18. Ownership, effort, and dependencies

| Workstream | DRI | Estimate | Dependencies |
|---|---|---:|---|
| Phase 0 baseline | QA lead + Backend/Frontend leads | 10–15 engineer-days | none |
| Coverage instrumentation + ratchet | QA lead | 2–4 days | green suite from Phase 0; artifact retention policy |
| Coverage uplift (risk-ranked) | owning layer DRIs | continuous alongside Phases 1–2 | measured baseline and floors |
| Kernel/sequence/fan-out | Runtime lead | 15–25 days | PostgreSQL CI, event decision |
| API/authz/migrations | API+DB lead | 10–15 days | scoped transition service |
| SSE/frontend | Frontend+API lead | 12–18 days | shared event schema |
| Browser harness | Frontend QA | 8–12 days | canonical fixtures, SSE barriers |
| AI evaluation | AI Eval lead + Security | 10–15 days offline | dataset/rubric approval; live budget later |
| IaC/security/release | Platform+DevSecOps | 12–20 days | OIDC, remote state, environment protection |
| Reliability/observability | SRE+Runtime | 12–20 days | metrics backend, production-like staging |

Estimates are implementation effort ranges, not dates. Each checkbox becomes an issue containing risk ID, test ID, DRI, reviewer, dependency, and evidence link. P0 work cannot be closed by a test-only change if the preventive control remains absent.

## 19. Definition of done and release exit criteria

- [ ] All P0 risk preventive controls and detective tests are implemented and green.
- [ ] No unexplained/quarantined P0/P1 failure; `UNKNOWN` count is zero on critical flows.
- [ ] Backend offline Linux and Windows portability shards pass; characterization goldens unchanged unless separately approved.
- [ ] PostgreSQL migrations/concurrency/authz pass at head 0032.
- [ ] Frontend lint, type/build, Vitest, and mocked Playwright pass without retries.
- [ ] Backend and frontend coverage are measured and published for the release commit, no layer sits below its committed floor, and the untested-module inventory has not grown since the previous release.
- [ ] Required security/IaC/image/dependency/secret checks pass or have approved unexpired exceptions.
- [ ] Release artifact is signed/attested, digest-bound to tested SHA, and production approval is recorded.
- [ ] Rollback, restore, graceful shutdown, and resume drills meet agreed RTO/RPO/SLO.
- [ ] Live eval, if required, meets approved quality/cost/latency thresholds; otherwise release evidence explicitly states it was not run.
- [ ] `git status --porcelain tests/agents/characterization/golden/` is empty.

## 20. Open questions and external verification

- [ ] Is native Windows a supported runtime or only a developer platform? This decides implementation vs skip boundaries for process isolation/resource limits.
- [ ] What PostgreSQL version/configuration and connection-pool topology exactly match production?
- [ ] What are approved RTO/RPO, stop grace, max SSE reconnect window, and stuck-run threshold?
- [ ] Which Terraform roots map to each environment/account, and where are remote backend controls enforced outside this repository?
- [ ] Which branch protections/environment approvals and organization-level scanners exist but are not visible in repository YAML?
- [ ] Is migration downgrade supported in production, or is forward-fix the only data-safe policy?
- [ ] Which 15 mocked browser settling failures are product defects after serial isolated reruns with barriers?
- [ ] What live-eval models, dataset, quality threshold, maximum spend, and artifact-retention policy are authorized?
- [ ] Are accessibility conformance level and performance/capacity targets contractually defined?

External systems (GitHub protection settings, cloud IAM/state backend, registry policies, production telemetry/backups) were not accessible and must be verified by their owners.

## 21. Reproduction and target commands

### PowerShell (Windows developer verification)

```powershell
# Backend offline; run from the backend root and keep live/golden mutation disabled.
Push-Location backend
try {
  Remove-Item Env:SNAPSHOT_UPDATE -ErrorAction SilentlyContinue
  Remove-Item Env:RUN_LIVE_BEDROCK -ErrorAction SilentlyContinue
  $env:PYTHONUTF8 = '1'
  & '.venv/Scripts/python.exe' -m pytest tests -m 'not requires_api_key and not eval' -q
  & '.venv/Scripts/python.exe' -m compileall -q app agents
  # Coverage (COV-001). Report only; treat the number as provisional until the
  # suite is green, because failing tests skew what gets executed.
  & '.venv/Scripts/python.exe' -m pytest tests -m 'not requires_api_key and not eval' -q `
      --cov=app --cov=agents --cov-report=term-missing --cov-report=html
} finally {
  Pop-Location
}

# Frontend deterministic tiers; Playwright must start with port 3000 free because
# the current configuration uses reuseExistingServer=true.
Push-Location frontend
try {
  npm run lint
  npm run test -- --run
  npm run test -- --run --coverage   # COV-001 report; see frontend/coverage/index.html
  npm run build
  if (Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue) { throw 'Port 3000 occupied' }
  npx playwright test --project=mocked
} finally {
  Pop-Location
}

# IaC static format only is currently initialization-free.
terraform fmt -check -recursive
```

### Linux CI target

```bash
unset SNAPSHOT_UPDATE RUN_LIVE_BEDROCK
cd backend
.venv/bin/python -m pytest tests -m 'not requires_api_key and not eval' -q --junitxml=pytest.xml \
  --cov=app --cov=agents --cov-report=term-missing --cov-report=xml --cov-report=json
.venv/bin/python -m compileall -q app agents
cd ../frontend
npm ci
npm run lint
npm run test -- --run --coverage
npm run build
npx playwright test --project=mocked
cd ../infra/terraform
terraform fmt -check -recursive
for root in bootstrap shared foundation app velocityai-alb localstack; do
  terraform -chdir="$root" init -backend=false -input=false -lockfile=readonly
  terraform -chdir="$root" validate -no-color
done
tflint --recursive
checkov -d .
trivy config .
cd ../..
gitleaks detect --source .
```

Shared-environment plans/applies must use the configured encrypted remote backend and protected CI identity; never copy the `-backend=false` validation pattern into an apply job. No `terraform apply` belongs in this audit command set.

## 22. Audit-scope confirmation

> "Coverage" here means audit scope, not test coverage. Measured test coverage is R-18, COV-001..005, and the Section 10 uplift backlog.


[x] Audited architecture, critical flows, test assets, CI/CD, security, AI eval, Terraform, reliability, and observability surfaces.
[x] Recorded commands/results only when actually run at SHA `0520e2f`; no suite is described as passing unless its command succeeded.
[x] Preserved `SNAPSHOT_UPDATE` unset and did not update characterization goldens or snapshots.
[x] Included checkbox traceability, measured baseline, root-cause classification, P/I/D/blast-radius risk register, invariant mapping, domain strategies, concrete P0/P1 tests, CI graph, roadmap, ownership, commands, DoD, and open questions.
[x] Mapped every P0/P1 risk to at least one preventive and one detective control.
[x] Did not run live provider/eval calls, Terraform apply, cloud mutation, dependency installation, or unapproved network scans.
[ ] Docker/PostgreSQL-container suites and container scans were not verified because Docker is unavailable.
[ ] Ruff, Pyright, import-linter, Vulture, TFLint, Checkov, Trivy, Gitleaks, and pre-commit were not locally executable in the existing environment.
[ ] Terraform semantic validation/plan was not verified because providers/modules were not initialized; only fmt passed.
[ ] No test-coverage percentage was measured for any layer: the baseline commit collected none, and the staged instrumentation has not been executed. Every percentage or "estimated now" value in this plan is a structural estimate pending COV-001.
[ ] Live Playwright/eval tests were not run because credentials, explicit authorization, and a cost limit were absent.
[ ] External branch protection, cloud IAM/state, production telemetry, backup/restore, and registry enforcement remain owner attestations.

This plan intentionally leaves all future work unchecked. Audit-only facts are checked. Approval of this plan should create tracked implementation issues; it should not be interpreted as approval to regenerate baselines, weaken tests, make cloud changes, or spend on live models.
