# Domain 14 — backend·api

29 cards, 4 batches.

| batch | round | fix site | cards | tier | phases | model |
|---|---|---|---|---|---|---|
| B1 | 1 | backend·api (mixed) | ISS-134, ISS-182, ISS-419, ISS-470, ISS-471 | A′ (ISS-471 sibling of ISS-319) + C | mixed | **sonnet** (backend core) |
| B2 | 2 | `backend/app/api/run_commands.py` | BUG-004, BUG-017, ISS-100, ISS-104, ISS-119, ISS-127, ISS-128, ISS-133, ISS-144, ISS-154, ISS-161, ISS-398, ISS-418, ISS-422, ISS-435, ISS-436, ISS-437 | A′ (ISS-398 sibling of ISS-292; ISS-422 sibling of ISS-312; ISS-435-437 sibling of ISS-316) + B (stale-state + silent-discard) + C | full; one read | **sonnet** (17 cards, load-bearing API file) |
| B3 | 5 | `backend/app/api/user_workflows.py` | ISS-180, ISS-181, ISS-263, ISS-381 | A′ (ISS-263 sibling of ISS-225) + C | mixed | **sonnet** |
| B4 | 5 | `backend/app/api/run_stream.py` | BUG-015-016, ISS-105, ISS-137 | C | full | **sonnet** (SSE transport surface) |

Notes:
- B2 `run_commands.py` is the **second-heaviest batch** (17 cards in one file). It is
  the REST up-channel: gate, answers, cancel, messages, revisions. Dominant defects:
  missing terminal-run guards (ISS-144), uncapped analysis_report in spec-revision
  prompts (ISS-127), false-approve on gate reject (ISS-128), stale line-number
  references (ISS-104). Tier-A′ siblings (ISS-398/422/435-437) replicate validated
  diffs — fast.
- B1: ISS-134 cancel-liveness process-local dict (architecture concern for ECS
  migration; may be escalate rather than fix). ISS-470/471 race on concurrent
  PUT/refresh. ISS-182 stale custom-agent:<id> rows.
- B4 `run_stream.py`: SSE transport. ISS-105 (uvicorn cancels SSE tasks, shutdown
  snapshot races), ISS-137 (pipeline_reconnected dead frame), BUG-015-016 (completed
  run reconnects forever). All correctness-critical SSE behaviour.
- All backend batches tagged sonnet — a wrong edit in any of these API files is a
  runtime regression.

Collision note: each batch owns ONE API file. Secondary globs into engine.py
(domain 15), frontend hooks (domain 11) — never edit those.
Status: NOT STARTED.
