# Launch ledger — 27 per-issue investigation agents

Concurrency cap is 20 subagents. Wave 1 launched 20; wave 2 launches the remaining 7 as slots free.
Every agent's prompt = the common preamble below + its per-issue block. All agents inherit the
parent model (Opus 5, 1M context) so they can read both registers to EOF; "Effort: MAXIMUM" is
stated in-prompt.

## Common preamble (prepend verbatim to each per-issue block)

```
Effort: MAXIMUM. No shortcuts. You are the **<ID>** investigator.

FIRST, read this file completely and obey it exactly - it is your full operating contract
(non-negotiable to-EOF register reads, hard rules including "modify NO file except your own
output", output structure, return contract):
/Users/1000060523/Documents/Work/UKI/Flowin/flowin/.planning/dev-sse-infra-investigations/AGENT-BRIEF.md

Your issue: **<ID> - <title>** (dossier lines <range>).
Write your investigation to:
/Users/1000060523/Documents/Work/UKI/Flowin/flowin/.planning/dev-sse-infra-investigations/<ID>.md

Your domain for the blast-radius sweep (I4) - cover at minimum, with real commands and output:
<per-issue hints>
```

## Wave 1 — LAUNCHED (20)

A1, A2, A3, A4, A5, B1, B2, B3, B4, B5, B6, C1, D1, D2, D3, D4, D5, D6, D7, D8

## Wave 2 — PENDING (7)

D9, D10, D11, E1, E2, E3, E4 — per-issue hint blocks below.

---

### D9 — Boot re-launches every non-terminal run at once (dossier 1707-1732)

- `backend/agents/execution_engine/engine.py` `restore_non_terminal_runs` in full (~:5244 and
  surroundings): the query selecting resumable runs, per-run task creation, queue/task registration,
  error handling, whether anything already bounds it. Quote the loop.
- `backend/app/main.py` (~:164) and startup ordering: what runs before/after the restore, and whether
  the restore blocks readiness (does the app serve traffic while restoring? does a slow restore delay
  the health check and cause the deploy to fail or the container to be killed? — check the health
  check and `infra/buildspec.yml`; a ripple the dossier does not mention).
- **The resource that actually saturates.** Do not assume CPU: trace what a resumed run does
  immediately (Bedrock/LLM calls, DB sessions from a 20+40 pool, sandbox filesystem work, thread-pool
  offloads, deepagents construction). Identify which limit binds first and size the semaphore from
  THAT, not vCPU count. Check `backend/app/core/config.py` for an existing global admission limit and
  reuse it rather than adding a competing knob (INV-3).
- Correctness under queueing: a deferred run sits non-terminal longer. Verify what a user sees
  meanwhile (`live: true`? a dead SSE attach? a 409 on resume? — cross-ref A4's liveness predicate
  keyed on `_PIPELINE_TASKS`), and whether a queued-but-not-started run can be double-started by a
  user-initiated resume (`run_commands.py` overlap mutex ~:390). Specify the interlock.
- The resume tier's known fragility: read the register entries for the v3.0 resume milestone and the
  resume QA campaign (alias bug BUG-R01/R02, RESUME-* items) and say whether restoring N runs
  concurrently can hit any of them in a way one-at-a-time does not.
- Failure isolation: today one raising restore escapes into a bare `create_task` (see A4). With a
  semaphore and worker queue, one failure must not stall the queue — specify the error handling.
- Cross-issue and ordering: D8 first (verify that claim yourself), A4 (stale entries from failed
  restores), A2/A3 (queue and pump per restored run), D6 (sweep before restore — reconcile with D6's
  own analysis), D11/B1 (observability of the deferral count).
- Give the complete implementation, the setting and its default, and a complete test that seeds N
  non-terminal runs and asserts at most the cap run concurrently while all eventually complete.

---

### D10 — `SSE_STREAM_IDLE_TIMEOUT_SECONDS` defined and never read (dossier 1735-1754)

Preface: "Your issue is small; the discipline is not. A deletion must be proven safe across the whole
deployment surface, not just the Python source."

- `backend/app/core/config.py` around the setting (~:119-133): the whole comment block,
  `SSE_KEEPALIVE_PING_SECONDS`, and how `Settings` is defined (pydantic-settings? env prefix? `extra`
  behaviour). That last point matters: if the model forbids extra env vars, deleting the field while
  an environment still SETS it causes a **startup crash** — determine the actual behaviour, because
  it decides whether the deletion is safe to ship alone.
- Sweep for the name EVERYWHERE, not just `backend/`: `rg -uu 'SSE_STREAM_IDLE_TIMEOUT'` across the
  repo including `.env*`, `docker-compose*.y*ml`, `infra/` (Terraform SSM params, `envs/*`,
  `buildspec.yml`, `bootstrap-ec2.sh`, `user_data*`), `frontend/`, tests, docs/`.planning/`. Also
  `git grep 'SSE_STREAM_IDLE_TIMEOUT' origin/fix/infra-uki origin/feat/ui-2 origin/main` — an env var
  set in a branch about to merge would resurrect the problem.
- Whether any live SSM parameter or env file on dev sets it (read-only if possible; otherwise state
  the check the executor must run before deleting, and make it a gate in the plan).
- The comment content to fold into `SSE_KEEPALIVE_PING_SECONDS`: ping shorter than the ingress idle
  timeout, ingress must run `proxy_buffering off`. Verify both against the real nginx config
  (`bootstrap-ec2.sh` §13) and against A1's proposed new location block, then write the final comment
  text so it is accurate after A1 lands (`proxy_read_timeout` values, the 15s ping,
  `X-Accel-Buffering`). Cite `run_stream.py`'s actual ping wiring.
- Phase 44 IN-01: find the register entry that logged this and confirm the fix closes it; note any
  other IN-* item naming the same constant.
- Tests: which suites read `Settings` and would notice a removed field; run the targeted SSE suite
  for a before/after baseline and quote it. Confirm "grep returns zero occurrences" as an acceptance
  criterion with the exact command.
- Cross-issue: A1 (nginx timeouts referenced in the new comment), A2 (adds
  `SSE_SUBSCRIBER_QUEUE_MAXSIZE` next to it — same file region; state the merge), D11 and E1 (the
  observability story the comment should point at).

---

### D11 — `run_stream.py` has no logging at all (dossier 1757-1788)

- `backend/app/api/run_stream.py` in full (300 lines): every exit path from the generator and the
  endpoint, so the close-reason vocabulary is exhaustive and each reason is actually reachable. Prove
  the mapping exit-site -> reason.
- `backend/app/main.py` logging configuration: format string (~:39), levels, handlers,
  `uvicorn.access` pinned to WARNING. Then survey how the rest of the backend logs
  (`rg 'logging.getLogger' backend/app backend/agents | head -50`) and pick the matching idiom —
  INV-3 forbids a second logging convention. **The dossier says "emit as JSON" but the app's format
  is pipe-delimited text.** Resolve properly: JSON for this module only (justify the inconsistency and
  say how a metric filter parses a mixed stream), or an app-wide structured-logging change (scope it
  honestly as bigger than D11). Pick one, justify, state the cost.
- Volume and cost: lines/day at real dev traffic (two per stream plus reconnects — A1's 429 storm and
  A2's evictions each multiply attaches), CloudWatch ingestion cost after B1, and whether any field
  could contain user content or PII (run titles, briefs, gate payloads must NOT be logged — state the
  rule).
- What a metric filter needs from these lines to be useful (cross-ref E1's filters/alarms): name the
  specific filters the fields enable (streams-opened-per-minute, evictions, no-live-queue attaches).
  Design fields for those queries, not just human reading.
- Composition with A2: after A2 the four exits collapse into one wrapper `finally`, and the close
  reason must also cover `evicted`. State the dependency and give BOTH forms (pre-A2 four-site,
  post-A2 single-site) or declare a hard ordering. Also A4 (`no_live_queue` / self-healed stale), A5
  (attach cost worth logging — replay row count?), A1 (429s are nginx-side and invisible here).
- Tests: what asserts on log output today (caplog usage), and the complete test proving exactly one
  open and one close line with the right reason for client-disconnect, terminal-event and
  no-live-queue. Offline command and expected output.

---

### E1 — nginx log format captures no upstream variables (dossier 1795-1863)

Preface: "Your fix changes a log format AND the metric filters that parse it — they must land
together or monitoring goes dark."

- `infra/scripts/bootstrap-ec2.sh`: the `log_format` (~:712-715), every `access_log`/`error_log`
  directive and which format each uses, and whether any location overrides logging. Confirm the nginx
  version supports `escape=json` and `$request_id`.
- `infra/terraform/modules/monitoring/main.tf` in full for the log side: EVERY
  `aws_cloudwatch_log_metric_filter` and its pattern, every alarm bound to those metrics, plus any
  subscription filter, dashboard, or Insights query. **Enumerate all of them** — the dossier names one
  space-delimited filter; a missed second filter goes silently dead when the format changes. Give the
  exact replacement JSON pattern for each.
- **The multi-environment hazard.** The monitoring module is shared code applied per-environment.
  Establish exactly what a `dev` apply changes and prove no stage/prod resource moves (per-env state
  keys, `for_each`/`count` scoping, variable defaults). Constraint is DEV ONLY. Also state what
  happens to stage/prod when next applied with new module code while their boxes still emit the OLD
  format, with a recommendation.
- The transition window: old and new lines coexist in one log group. Say whether the JSON filters
  silently ignore old lines (and vice versa) and whether any alarm can false-fire or false-clear
  during the switch. Specify the ordering (format first or filters first?) and justify.
- `$request_id` end-to-end: does the proxy-headers snippet forward it (`X-Request-ID`), and does the
  backend log a correlation id (cross-ref D11)? If not, say what it would take, and keep it in or out
  of scope with a reason.
- The proposed new alarms: verify each threshold against the real config (`/api/` `120r/m` +
  `burst=20`), and verify the `AWS/Logs IncomingLogEvents` meta-alarm's dimensions and
  `treat_missing_data` are correct — that is the alarm that would have caught B1, so it must be right.
- Cost: measure/estimate the size delta honestly at dev volume; state the monthly figure with
  arithmetic.
- Cross-issue: A1 (new location must log; `upstream_addr = "-"` identifies a limit-rejected request),
  D3 (same nginx file), B1/B2/B3 (nothing ships until the agent works), B6 (subscription ordering),
  C1 (delivery), D11 (consistency).

---

### E2 — `PgDumpHeartbeat` alarm has no publisher (dossier 1866-1890)

- The alarm in `infra/terraform/modules/monitoring/main.tf` (~:733): namespace, metric name,
  dimensions, statistic, period, evaluation periods, `treat_missing_data`, actions. Quote it. Note
  precisely what metric name and dimension set a publisher must emit — a heartbeat published with
  different dimensions is still a dead alarm, the classic way this "fix" fails.
- The backup implementation in `infra/scripts/bootstrap-ec2.sh`: find the `velocityai-pg-dump`
  script/unit/timer in full, how it is scheduled, how it reports success/failure, whether it can
  partially succeed (dump written but upload failed), and where exactly a `put-metric-data` call must
  go so it can only fire on genuine end-to-end success. Read the heredoc quoting carefully — E3's
  whole defect is a literal that could not be templated inside a quoted heredoc, and this publisher
  sits in the same kind of block. Verify what expands when.
- IAM: does the instance role permit `cloudwatch:PutMetricData`, and is it restricted by a namespace
  condition that would reject `VelocityAI/Backups`? Read the policy documents and answer definitively.
- **Namespace derivation must be ONE mechanism shared with E3** (INV-3). Propose the single shared
  mechanism and say which of E2/E3 introduces it.
- Whether the alarm should be per-environment at all, what its dimensions should be (instance id?
  environment?), and whether the alarm definition needs a Terraform change too — if it does, that is
  a monitoring-module edit shared with E1/E3/B6, so state the merge and the dev-only apply scope.
- The rejected alternative (delete the alarm): argue it properly. Say what "good" looks like — does
  the heartbeat prove the dump is RESTORABLE, or only that a file was written? If the latter, name
  the gap rather than declaring victory.
- Cross-issue: B6 (part of the 41; do not subscribe before it is fixed), E3 (shared namespace),
  B1/B5 (agent + assertion patterns), C1 (delivery to the running box).

---

### E3 — stuck-workflows check hardcodes the prod namespace (dossier 1893-1918)

Preface: "Dev data is landing in prod's metric namespace, so this is both a dead dev signal and a
corrupted prod signal."

- The publisher in `infra/scripts/bootstrap-ec2.sh` (~:1105-1106) in full context: the whole heredoc,
  the quoting (quoted vs unquoted delimiter), every variable inside it and whether it expands at
  install time or run time, how the script is scheduled, and what SQL/HTTP it uses to count stuck
  workflows. Quote the block.
- **Audit the ENTIRE script for the same trap**: every heredoc, whether each delimiter is quoted, and
  every literal inside a quoted heredoc that looks environment-specific (namespaces, log groups,
  bucket names, URLs, regions, emails, ports, instance ids). Report the full list — the dossier found
  one instance; the class is the deliverable. Say for each whether it is a live defect or benign.
- Consumers of the metric: the `StuckRunningWorkflows` alarms in
  `infra/terraform/modules/monitoring/main.tf` per environment, their dimensions and
  `treat_missing_data`, and what happens when dev's data stops arriving in `VelocityAI/Prod` (prod's
  alarm behaviour changes — say exactly how, and whether prod's alarm has ever been meaningful given
  the contamination). Also: historical contaminated data in prod's namespace — you cannot delete
  CloudWatch datapoints; state the honest answer.
- **Namespace derivation must be ONE mechanism shared with E2** (INV-3). Propose the single
  derivation (`VelocityAI/${ENV_TITLE}` or similar), say where it is defined, how `ENVIRONMENT`
  reaches the script's execution context (the `ENVIRONMENT=<value>` before-the-heredoc technique, and
  the precedent in `infra/buildspec.yml` ~:228-232 — verify it), and how E2's heartbeat reuses it.
  Name which issue owns introducing it.
- Correctness of the check itself: is the stuck-workflow query right (what counts as stuck? does it
  agree with the app's status vocabulary and with D8/D9's shutdown/restore behaviour, which change
  how many runs sit non-terminal)? A wrong metric is not fixed by publishing it to the right
  namespace — but keep any semantic change clearly separated and justified.
- IAM `PutMetricData` permission and any namespace condition (cross-ref E2).
- Cross-issue: E2 (shared mechanism), B6 (among the 41; dev is INSUFFICIENT_DATA), B1/B5
  (silent-failure patterns), C1 (delivery), D8/D9 (what "stuck" will mean after they land).

---

### E4 — `logs:DescribeLogGroups` scoped to a resource ARN (dossier 1921-1942)

Preface: "It is latent: B1 prevents the agent from ever reaching the call, so it surfaces the moment
B1 is fixed."

- Find the actual policy in the repo: locate `velocityai-dev-cloudwatch-write` (and stage/prod
  siblings) in `infra/terraform/`, read the full policy document, quote every statement with its
  actions, resources, conditions. Do not work from the dossier's summary.
- **Audit every statement in that policy — and the other instance-role policies — for the same defect
  class**: actions that do not support resource-level permissions but are scoped to an ARN. Check each
  against documented IAM support (quote the source per action) and report the full list. Check
  specifically: `logs:DescribeLogGroups`, `logs:DescribeLogStreams`, `cloudwatch:PutMetricData`
  (namespace conditions rather than resources), `ec2:Describe*`, `ssm:DescribeInstanceInformation`.
  The class is the deliverable; the single fix is the minimum.
- **Whether the CloudWatch agent actually calls `DescribeLogGroups` at all.** The dossier tags this
  `[I]`. Resolve it as far as possible: read the installed agent's behaviour/docs, or reason from what
  it must do at startup (does it create groups, or only streams? Terraform pre-creates the groups). If
  the agent does NOT need the action, the correct fix may be to REMOVE the statement rather than widen
  it — least privilege. Present both options with evidence and recommend one; do not default to
  widening.
- The security consequence of `Resource: "*"` on that action: what it exposes (enumeration of all log
  group names in the account, including stage/prod and cloudtrail-audit groups), and whether a
  condition can narrow it. Say plainly whether that is acceptable for this instance role and why.
- Multi-environment scope: is the policy in a shared module applied per-env? Constraint is DEV ONLY —
  state exactly what a dev apply changes and prove no stage/prod resource moves. Note whether the fix
  is safe to leave un-applied on stage/prod.
- Verification without B1: the effect is unobservable until the agent runs, so specify both an
  IAM-level verification that works today (`aws iam simulate-principal-policy` shape, read-only) and
  the post-B1 behavioural check.
- Cross-issue ordering: B1 (prerequisite for behavioural proof), B2 (a running agent still needs read
  access), B6 (alarm noise), C1 (Terraform apply path — this is a Terraform change, not a host
  change, so say how it actually ships and whether the agent must be restarted to pick it up).
