# Integration Contracts: Model-Graded Eval Branch (LLM-as-Judge + Report)

No message queues, webhooks, scheduled jobs, or third-party service integrations are added by
this spec beyond the LLM provider calls the harness already makes. Documented below for
completeness.

## Integration 1 — Agent-under-test invocation (existing mechanism, reused as-is)

- **What**: `agents/factory.py::create_runner(agent_id, ctx)` → `DeepAgentRunner.astream_events()`
  → real model call (Anthropic/Bedrock/Mistral via `build_model()`).
- **Direction**: this feature is a caller, not a provider. No changes to the runner/agent-factory
  contract itself.
- **Trigger**: only ever a human running `./tests/evals/model_graded/model-graded.sh graded ...` — never automatic, never
  triggered by another service or a scheduled job (spec NFR "Cost": "never auto-invoked by an
  agent, per standing project rule").
- **Failure mode**: `DeepAgentRunner` swallows its own exceptions and yields an `error` event
  (existing behavior, unchanged) — the new driver (`model_graded/driver.py`) must handle this
  the same way `common/live_scenario.py` already does: mark the run `errored`, do not run the
  pre-check against a partial/untouched response, and surface the infra failure distinctly from
  a real "the model tried and produced a bad response" outcome.

## Integration 2 — Judge model invocation (new call site, existing abstraction)

- **What**: `model_graded/judge.py::grade_run()` → `app/agents/model_factory.py::build_model()`
  → a second, independent real model call, requesting structured output (score + verdict +
  rationale).
- **Direction**: caller only, same as Integration 1. No new provider SDK — reuses whichever of
  Anthropic/Bedrock/Mistral `build_model()` already resolves.
- **Trigger**: only when `--judge` is explicitly passed on the CLI (spec Story 4 AC1) — never
  implied by a bare `graded <scenario-id>` call.
- **Contract with `build_model()`**: `grade_run()` calls it exactly as `common/live_scenario.py`
  already does for the agent-under-test call (`build_model(model, provider=provider)` when an
  override is given, or the bare fallback-chain default otherwise) — no new parameters or
  behavior are asked of `build_model()` itself; this integration is 100% consumer-side.
- **Failure mode**: network error or malformed/unparseable structured output →
  `JudgeVerdict(errored=True, error_reason=...)`. Must never raise out of `grade_run()` — the
  caller (`model_graded/cli.py`) always gets a `JudgeVerdict` back, even a failed one, per spec
  Story 2 AC2 ("grading failure never masks or blocks the existing deterministic result").

## Integration 3 — Local filesystem persistence (new files, no external service)

- **What**: `model_graded/report.py::append_entry()` writes to
  `backend/tests/evals/reports/eval_report.jsonl`; `model_graded/driver.py` writes per-run
  transcripts to `backend/tests/evals/model_graded/logs/<run_id>/`.
- **Direction**: local disk only. Not a database connection, not a remote store, not
  network-reachable.
- **Trigger**: every graded run (report) / every run regardless of grading (logs) — synchronous,
  in-process, no queueing.
- **Failure mode**: a write failure (disk full, permissions) should raise loudly at the CLI level
  — there is no silent-drop or retry-queue behavior specified; this is local dev tooling, not a
  service with uptime requirements.

## Explicitly not integrated

- No CI/CD pipeline hook — grading is never triggered by a build (spec §5 Out of Scope).
- No Slack/email/notification integration for report summaries.
- No external eval-platform integration (e.g. no Arize Phoenix, LangSmith, or similar SaaS
  wiring) — the report is a local, git-tracked file, not a call to a hosted eval product,
  despite those tools being cited as prior art for the *pattern* in `spec.md` §1.
