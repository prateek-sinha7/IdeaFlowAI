# Build Summary — 007-prompt-versioning

Running log of what was actually built, with the evidence for each claim.

---

## T1 — Persist the advisor's structured advice as JSON ✅

**Completed**: 2026-07-30

### What was built

`prompt_advisor` produced a typed `PromptAdvice`, rendered it to markdown and dropped the
object. `apply-advice` (T5) needs the structure — an exact, unambiguous match of `current_text`
against a prompt body is only possible while the text is unrendered.

Added a JSON sidecar written from the same object as the markdown, so the two cannot disagree.

### Files changed

| File | Change |
|---|---|
| `backend/evals/grading/artifacts.py` | **+4 functions**: `advice_markdown_path`, `advice_json_path`, `write_advice_json`, `read_advice_json` |
| `backend/evals/grading/model/prompt_advisor.py` | `_advise_stage` writes the sidecar; markdown path now comes from `artifacts` instead of being composed inline |
| `backend/tests/unit/test_grading_prompt_advice_json.py` | **new** — 13 tests |

### Tests

`tests/unit/test_grading_prompt_advice_json.py` — 13 tests in 4 classes:

- **`TestAdviceJsonPath`** (3) — both files land in `reports/`, and the markdown filename is
  unchanged from what the advisor composed inline.
- **`TestRoundTrip`** (4) — a `PromptAdvice` survives write → read → compare equal. The fixture
  deliberately carries the awkward content: embedded double quotes, `\n\n`, backtick fences and
  non-ASCII. `current_text` is asserted byte-identical, which is the property the whole feature
  depends on.
- **`TestMissingAdvice`** (2) — a pre-sidecar run raises `FileNotFoundError` naming
  `grade.sh advise <run-id>`; an advisor that proposed zero edits round-trips as an empty list
  rather than reading as missing.
- **`TestAdvisorWritesBoth`** (4) — the wiring, with the judge model stubbed: both files land,
  the JSON equals the object the markdown rendered, `result["advice_path"]` still reports the
  markdown, and **an errored advisor writes neither file**.

### Commands run

```bash
cd backend
python3.11 -m pytest tests/unit/test_grading_prompt_advice_json.py -q   # 13 passed
python3.11 -m pytest tests/unit/ -q -k grading                          # 378 passed, 7 skipped
```

### Deviations from plan/design

Two, both additive:

1. **`advice_markdown_path()` was added as well as the JSON path.** The plan called for one path
   helper. The advisor was building the markdown path inline
   (`artifacts.reports_dir(run_dir) / f"prompt_advice_{token}.md"`), which contradicts
   `artifacts.py` being the sole owner of every run-folder path (005 §3). Moving it costs
   nothing and a test asserts the filename is unchanged.
2. **An errored-advisor test was added.** Not in the task's test list, but the failure mode is
   real — a half-written sidecar next to no markdown would make a failed advise look partially
   successful to T5.

### Notable implementation details

- `read_advice_json`'s error message names `grade.sh advise <run-id>` and states that it costs
  one judge call and no agent dispatches. A bare "file not found" would send someone to re-run
  a full graded run.
- `write_advice_json` goes through the module's existing `_write_json`, so the sidecar inherits
  `indent=2`, `ensure_ascii=False` and the trailing newline — consistent with every other JSON
  artifact, and readable when someone opens it.
- The advisor calls `artifacts.reports_dir(run_dir)` once before both writes; `_write_json`
  also creates parents, so the sidecar is safe independently.

### Blockers / follow-ups

- **Encountered and cleared**: `evals/grading/model/judge.py` was momentarily broken on disk
  (`Severity = Literal[...]` with `Literal` unimported), which blocked collection of *every*
  grading test. This was in-flight spec-008 work from a parallel session, not this task; it was
  fixed by that session while I was looking at it. No action taken here — flagged only because
  it means the two specs are being built concurrently in the same files' neighbourhood.
- **Note for T5**: the token, not the agent id, keys the report filenames —
  `_token("prototype-build") == "prototype_build"`. `apply-advice` takes `--agent
  prototype-build` and must convert before reading. This cost a test failure here; it will cost
  one in T5 too if not remembered.

---

## T2–T10 — the edit engine, the two commands, the tripwire ✅ (T8 partial)

**Completed**: 2026-07-30

### What was built

| Task | Delivered |
|---|---|
| T2 | `prompt_edits.split_agent_file()` — frontmatter/body split, no YAML round-trip |
| T3 | `prompt_edits.apply_edits()` — add/remove/modify, exact-match-or-fail |
| T4 | `next_archive_number()`, `archive_name()`, `render_diff()` |
| T5 | `grade.sh apply-advice <run-id> --agent <id>` |
| T6 | `grade.sh revert <agent>` |
| T7 | `TestArchivedPromptsAreInvisible` — the registry tripwire |
| T8 | Zero-runtime-change assertion (**mechanical half verified; characterization run pending**) |
| T9 | Runbook + advisor footer |
| T10 | Seven zero-byte `AGENT.v2.md` files deleted; empty-archive guard in `revert` |

### Files changed

| File | Change |
|---|---|
| `backend/evals/grading/model/prompt_edits.py` | **new**, ~230 lines, pure |
| `backend/evals/grading/grade_runner.py` | `run_apply_advice`, `run_revert`, two subparsers, dispatch, `EXIT_EDIT_FAILED=9` / `EXIT_ALL_REFUSED=10`, `AGENTS_PROMPTS_DIR` |
| `backend/evals/grading/grade.sh` | two command arms, usage block, exit-code table |
| `backend/evals/grading/model/prompt_advisor.py` | footer now leads with `apply-advice` |
| `backend/evals/grading/docs/README.md` | command table + improvement-loop step 3 |
| `backend/tests/unit/test_grading_prompt_edits.py` | **new**, 32 tests |
| `backend/tests/unit/test_grading_apply_advice_cli.py` | **new**, 19 tests |
| `backend/tests/agents/test_loader.py` | +6 tests (`TestArchivedPromptsAreInvisible`) |
| `backend/agents/prompts/*/AGENT.v2.md` ×7 | **deleted** (zero-byte, untracked) |

### Commands run

```bash
python3.11 -m pytest tests/unit/test_grading_prompt_edits.py -q         # 32 passed
python3.11 -m pytest tests/unit/test_grading_apply_advice_cli.py -q     # 19 passed
python3.11 -m pytest tests/agents/test_loader.py -q                     # 48 passed, 1 pre-existing failure
python3.11 -m pytest tests/unit/ -q -k grading                          # 456 passed, 3 failing in another session's files
```

**End-to-end against the real prompt** (not just fixtures) — a scratch run folder with a
hand-written sidecar, applied to `agents/prompts/prototype-build/AGENT.md`:

- old body archived to `AGENT.v1.md`; frontmatter reported unchanged (15 fields)
- a deliberately-included `order: 4 → 99` edit was **refused** by name; the body edit applied
- `git diff` showed **one file, one body line** — no frontmatter line
- `registry.PIPELINE_AGENTS['prototype']` still listed exactly 5 agents with the archive on disk
- `grade.sh revert prototype-build` restored the file **byte-identical** (`diff -q` clean,
  `git diff` empty, archive removed)

The pre-sidecar path was exercised against a real run folder too: `apply-advice
260730-173912-prototype_small --agent prototype-build` exits 2 naming `grade.sh advise`.

### Deviations from plan/design

1. **`apply_edits` takes the frontmatter block as well as the body.** The design signature was
   `apply_edits(body, edits)`. Refusing a frontmatter edit *by field name* turned out to be
   wrong: `## Tools` is a real body heading in several prompts while `tools:` is a real
   frontmatter key, so a name check would refuse legitimate edits. Refusal is now **by
   evidence** — the edit's text has to actually live in the frontmatter and nowhere in the body
   — which needs the prefix. A test pins the `## Tools` case.
2. **A heading section ends at the next heading *or* the next `---` rule.** Design said "next
   heading". Without the rule, an `add` anchored to a section that is followed by a horizontal
   rule lands on the far side of that rule, reading as part of the next section.
3. **T10's guard lives in `run_revert`, not `apply_edits`.** An empty archive can only be
   encountered on the way *out*, and `apply_edits` already guarantees a non-empty body before
   one is written.

### Blockers / follow-ups

- **T8 is not finished, and the characterization suite is RED.** The mechanical half is
  verified — no tracked file under `backend/agents/` or `backend/app/` was changed by this spec
  (the one modified `AGENT.md` in `git status` predates it), and the golden files are untouched.
  But the run finished **10 failed / 0 passed in 28 minutes**, with failures of the shape
  `pipeline_failed`, `UNDOCUMENTED event type`, and `run produced no pipeline_complete event
  (drove nothing / errored)`.

  **Evidence that this is not caused by this spec**, though not yet conclusive:
  - The characterization tests and their helpers (`characterization/_normalize.py`,
    `_sse_projection.py`) import **nothing** from `evals/` or the grading package — verified by
    grep. Every file this spec changed is inside `evals/grading/` except three test files.
  - `agents/execution_engine/`, `app/agents/`, `agents/factory.py`, `agents/loader.py` and
    `agents/registry.py` are **completely unmodified** in `git status` — the entire prompt
    composition and execution path is untouched.
  - The failure shape is wrong for a prompt-composition change. Editing a prompt would produce
    a *snapshot diff*; "drove nothing / errored" means the runs are failing outright.

  **Resolved — the cause is environmental, not either spec.** `backend/.env` sets
  `DATABASE_URL=postgresql://…@localhost:5432/flowin_local`, and **Postgres is not running**
  (`connection refused` on 5432). The characterization runs use the Postgres checkpointer, so
  each one burns a 30-second `psycopg_pool.PoolTimeout`, the run errors, and the suite reports
  `pipeline_failed` / "drove nothing". That is also why it took 28 minutes.

  Proven by a detached clean-`HEAD` worktree, which is gitignore-clean and therefore has **no
  `.env`**: it never reaches for Postgres and finishes the same file in **2.56 s** instead of
  482 s, with `test_app_builder_deliverable_byte_snapshot` **passing**.

  **T8 is therefore blocked on the environment, not on code.** Re-run it with Postgres up:

  ```bash
  cd backend && python3.11 -m pytest tests/agents/test_characterization_*.py -q
  ```

  **Fixed** — `tests/agents/conftest.py` gains an autouse fixture pinning the checkpointer to
  `InMemorySaver` for the agent suite, so it no longer depends on the developer's `.env`. See
  "Test hermeticity" below.

  **Two genuine findings, neither belonging to this spec:**

  1. **The `tests/agents` suite is already red at `HEAD`** — 65 failures on a clean detached
     worktree, before any of today's work. That is worth its own investigation; it is the reason
     T8's original "all five characterization tests pass" criterion was unachievable.
  2. **Ten event-stream goldens have diverged** — 5 characterization + 5 `test_wire_parity`, all
     reporting the same shape (*"normalized event stream diverged from the committed golden"* /
     *"WIRE PARITY DRIFT"*). Not a Postgres artifact: `test_wire_parity` derives `run_events`
     in-memory via `run_events_from_engine_events` and never reads the database. Something
     changed the event stream and the goldens were never re-pinned. They should be diffed, not
     re-baselined.

  Also worth noting: `test_sample_brownfield_workflow` fails with `AttributeError: 'dict' object
  has no attribute 'encode'`, which looks like a plain code bug unrelated to events or the DB.

---

## First real use — and the design gap it exposed

Ran the full loop live on a new `prototype_small` row (`field_dispatch`), 2026-07-30.

**`apply-advice` exited 9 and wrote nothing.** All four edits the advisor proposed for
`prototype-build` anchor into `agents/guardrails/html-prototype.md` — *"Content and Copy"*,
*"JavaScript"*, *"Navigation and Layout"* — none of which appear in `prototype-build/AGENT.md`.

The cause is structural, not a bug in the matcher: **the advisor reads the *composed* system
prompt** (`tool_availability + injects + guardrails + skills + hooks + constitution +
prompt_body`, `capabilities/prompt/policy.py:44`) and proposes edits anywhere in it, but
`apply-advice` edits only the `AGENT.md` body. For this agent the advisor targeted the guardrail
**4 times out of 4**.

R-06 behaved exactly as designed — refused to guess, wrote nothing, named the failing anchor —
which is why nothing was corrupted. But the feature is far less useful than the spec assumed:
§9 put "versioning guardrails, skills or the constitution" out of scope without anticipating
that the advisor would predominantly target them.

**Recommended follow-up**: route each edit to the file that actually contains its anchor. The
candidate set is knowable — `AGENT.md` plus the guardrail files the agent declares in
`spec.guardrails` — and `prompt_edits` already does all the work (guardrails carry no
frontmatter, so `prefix=""`). Two consequences to design for: a guardrail is **shared across
agents** (editing `html-prototype.md` changes 4 agents), and an edit ambiguous across two
candidate files must fail rather than pick one.

For this experiment the edit was applied through the same pure engine to the correct file, with
the same archive-first discipline (`agents/guardrails/html-prototype.v1.md`).

**Result**: the deterministic code score went **42 → 97** on both `prototype-build` and
`prototype-validate`, and the `Cannot access 'store' before initialization` page error the
advisor named is gone. Caveats in the session report — two variables moved, and run 4's judge
failed on two stages.

---

## Test hermeticity — `tests/agents` no longer needs a database

**Not in the original task list**; found while chasing T8, and it is what unblocked it.

`get_checkpointer()` (`app/agents/checkpointer.py`) selects purely on the `DATABASE_URL`
*scheme*, with a fallback for Windows' ProactorEventLoop but **none for "Postgres is configured
but unreachable"** — it opens a pool and blocks 30 seconds. Nothing in the test tree pinned
`DATABASE_URL`, so the agent suite silently bound to whatever `backend/.env` pointed at.

The consequence was worse than slowness: **these goldens were only ever verified on machines
that happened to have a database running.** Anywhere else they failed for a reason unrelated to
what they assert — the kind of noise that teaches people to ignore a red suite.

The characterization tests assert event streams and deliverable bytes; **not one asserts
anything about persistence**, so `InMemorySaver` is the correct dependency rather than a
compromise. The suite that genuinely needs durability, `test_phase8_resume.py`, already does it
properly: it starts its own docker `postgres:16`, skips when docker is absent, and does all its
Postgres work in **subprocesses** with `DATABASE_URL` in an explicit child env — so patching the
in-process `settings` singleton leaves it untouched. Verified nothing else in `tests/agents/`
uses the checkpointer in-parent.

**Effect, with Postgres still down**: one characterization file went from 482 s to 3.0 s; the
five-file set from 10 failed / 0 passed in 28 min to 5 failed / 5 passed in 42 s.

**Caveat**: the fixture is `autouse` across all of `tests/agents/`. A future test that genuinely
wants in-parent durable checkpointing will need an explicit opt-out.

  Two process notes worth keeping: an earlier `| tail -6` pipe masked pytest's exit code and
  made a red run look green (`exit code 0` is the *pipe's* status, not pytest's), and `timeout`
  does not exist on macOS — a run wrapped in it silently does nothing and exits 0. Both produced
  a false "passed" reading during this task.
- **Three failures in `tests/unit/test_grading_code_grader.py`** are the parallel 008 session's
  in-flight work (`code_grader.py` and its test were both modified minutes before, mid-edit).
  Not caused by anything here — this spec touches no file in the code track.
- **One pre-existing failure**, `test_all_agents_description_defaults_to_role` for
  `analyze-agent`: reproduces in isolation, and that `AGENT.md` is unmodified by this work.
- **Unexercised in anger**: no real advisor JSON exists yet, because every committed run predates
  the sidecar. The first real `apply-advice` will be the first test of how often the advisor's
  `current_text` matches verbatim. R-06 makes a mismatch a loud failure rather than a silent
  misplacement, which is the intended direction, but the hit rate is still unknown.
