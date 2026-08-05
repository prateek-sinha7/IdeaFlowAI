# Integration Contracts: Grading Calibration

## Events, queues, jobs, webhooks

**None.**

No message bus, no queue, no scheduled job, no webhook, no cron. `evals/grading/` runs
synchronously from a terminal and exits. Nothing subscribes to it and it publishes nothing.

## Database

**None.** No table, no migration, no ORM model. All state is files under
`backend/evals/grading/`.

---

## External services

One, unchanged by this spec.

### Mistral — the judge model

| | |
|---|---|
| Service | Mistral API, `mistral-large-latest` |
| Called from | `judge.grade()` via `app.agents.model_factory.build_model(model, provider="mistral")` |
| Credential | `MISTRAL_API_KEY` (`app.core.config.settings`) |
| Pinned in | each `*_rubric.yaml` `judge:` block |
| Failure handling | **unchanged** — `RATE_LIMIT_RETRIES = 4` with exponential backoff + jitter on 429 only; every other failure returns an errored `JudgeVerdict` carrying its token cost rather than raising |
| Misconfiguration | **unchanged** — `resolve_judge_model` raises `JudgeConfigurationError` for an unhonourable provider, deliberately outside the `try`, so a bad config is a hard failure and not 12 rows of score 0 |

**What this spec changes**: only the prompt text and the expected response shape (see
`contracts/api-contract.md` §2). No change to the provider, the model id, the retry policy,
the credential, or the error semantics.

**New cost**: `grade.sh calibrate` adds roughly 6 briefs × 5 stages + 2 fail fixtures of
judge calls per invocation. It is user-triggered only and runs no more often than a rubric
edit — not on every run, not in CI.

**New dependency risk**: the run now depends on the judge emitting a three-value severity
enum inside a nested list. Mitigated by the legacy-shape fallback (untagged → `major`) and
surfaced by the `severity_fallbacks` counter and a >20% warning, so silent degradation is
visible rather than inferred.

---

## Internal integrations (in-process, same package)

| Consumer | Depends on | Effect of this change |
|---|---|---|
| `model_grader.run_workflow` | `judge.grade`, `code_grader.grade_run_folder` | Scores change; call signatures do not. Already passes `render=True, interactions=True` (`model/model_grader.py:198-199`), so the default flip is a no-op here. |
| `markdown_report.compute_overall` / `_top_report` / `_stage_report` | `code_grader.blended_score`, `<token>_grade.json` | Picks up the band automatically — the point of keeping the signature stable. Must render both `score_caps` shapes. |
| `grade.sh rejudge` | stored responses + `judge.grade` | Re-scoring an old run under the new scale is the intended way to compare. Auto-advise still fires afterwards, unchanged. |
| `grade.sh advise` | `recurring_weaknesses` from `scoring._cluster_texts` | Clusters `weaknesses` strings. Since `dimension_weaknesses` is retained as a derived view, clustering is unaffected — though severity would make it sharper later (not in scope). |
| `compare.py` | stored `score.json` across runs | Runs graded before and after this change are **not comparable**. Handled by the existing `rubric_hash` refusal, which is why baselines correctly read `REFUSED` until Phase 6. |
| `spec 007-prompt-versioning` | this harness's verdicts | Its A/B verdict trust is explicitly gated on 008 (see `specs/INDEX.md`). Landing this unblocks it. |

---

## Runtime dependency — Chromium / Playwright

| | |
|---|---|
| Used by | `code_grader._render_findings`, `_interaction_findings`, and `app.agents.render_check` |
| Optional | Yes. Absent Playwright or Chromium returns `{"available": false}` and `compute_code_score` subtracts nothing — the score stays a lower bound on brokenness, never a guess |
| Change here | `grade_run_folder`'s `render` / `interactions` defaults flip `False` → `True` |

**Consequence to watch**: any caller that relied on the old defaults for speed now launches
a browser. Known callers are `grade_runner.run_code_track` (already `True`) and
`model_grader` (already `True`), so no caller regresses — but the graceful-skip path is what
keeps a browserless CI green, and it must stay intact.

---

## CI / automation

No pipeline change is required by this spec.

Worth considering separately, and explicitly **not** included here: wiring
`grade.sh calibrate` into CI. It makes live paid model calls, so it would need a credential
in CI and a cost budget. The offline half — the `top/mission_control.verdict.json` replay in
`quickstart.md` V-1 — is free, deterministic and needs no network, so **that** is the piece
worth adding as a unit test (Phase 2's regression test), and it catches a cap-table
regression without spending anything.
