# Quickstart: Applying Advisor Prompt Edits

The loop, end to end. Two of these three steps cost nothing.

---

## Preconditions

- A finished graded run in `backend/evals/grading/.runs/<workflow>/<dataset-run-id>/` whose
  `reports/` contains advice for the agent you want to change.
- Advice is generated automatically after every live run unless `--no-advise` was passed
  (`config.py:53`).
- A clean-ish working tree — these commands edit a tracked file (`AGENT.md`) and do not commit.

## Setup

Nothing to install or configure. No env vars, no database, no migration.

If your run predates the JSON sidecar, backfill it once (costs one judge-model call per stage,
no agent dispatches):

```bash
cd backend
./evals/grading/grade.sh advise 260730-173912
```

## Run / exercise the feature

### 1. Read the advice

```bash
cat evals/grading/.runs/prototype/260730-173912-prototype_small/reports/prompt_advice_prototype-build.md
```

### 2. Apply it — free, instant

```bash
./evals/grading/grade.sh apply-advice 260730-173912 --agent prototype-build
```

```
  saved old body  -> backend/agents/prompts/prototype-build/AGENT.v1.md
  applied 3 edits -> backend/agents/prompts/prototype-build/AGENT.md

  [1] add     "Step 2 — Analyze the request"
      + Re-read design.md before each task.
  [2] modify  "write_file"
      - write_file(...) — overwrite the entire file.
      + write_file(...) — create-only; use edit_file for changes.
  [3] remove  "you may skip design.md if unchanged"

  frontmatter unchanged (13 fields)

  revert with:  ./evals/grading/grade.sh revert prototype-build
```

### 3. Check what changed

```bash
git diff backend/agents/prompts/prototype-build/AGENT.md
```

The diff should be prose only. If a frontmatter line appears, that is a bug — report it, do not
commit.

### 4. Re-grade — live, costs tokens

**Run this yourself** — per standing project instruction, live eval invocations are the
developer's to execute.

```bash
./evals/grading/grade.sh small
./evals/grading/grade.sh compare 260730-173912 <new-run-id>
./evals/grading/grade.sh history prototype-build
```

`compare` carries a noise guard: a delta inside observed run-to-run variance is reported as
noise, and with no repeat runs the verdict is `unknown-variance`. Read the verdict, not the
number.

> Until [008-grading-calibration](../008-grading-calibration/spec.md) lands, treat the score as
> indicative rather than decisive — the harness currently grades a verified-good artifact at 80
> and a broken one at 89.5+.

## Validation scenarios

| # | Do this | Expect |
|---|---|---|
| V1 | `apply-advice` on a run with advice | Archive created, edits applied, diff printed, exit 0 |
| V2 | `git diff` after V1 | One file changed; only body lines |
| V3 | Run the pipeline after V1 | New prompt in effect; no restart flag, no config change |
| V4 | `apply-advice` twice | Second archive is `AGENT.v2.md`; `v1` untouched |
| V5 | Advice containing an edit whose `current_text` is no longer present | Exit 9, names the edit, **nothing written** — `git status` clean |
| V6 | Advice with an edit targeting a frontmatter field | Exit 10 for that edit, named; other edits still applied |
| V7 | `apply-advice` on a pre-sidecar run | Exit 2 telling you to run `grade.sh advise <run-id>` |
| V8 | With `AGENT.vN.md` files present, run the loader test | Agent count and every `PIPELINE_AGENTS` list unchanged |
| V9 | `revert` with no archive present | Exit 2, "nothing to revert to" |

## Rollback / cleanup

**Undo the last apply:**

```bash
./evals/grading/grade.sh revert prototype-build
```

Restores the highest-numbered archive into `AGENT.md` and deletes that archive, so repeated
reverts walk back through history.

**Undo everything, ignoring archives:**

```bash
git checkout backend/agents/prompts/prototype-build/AGENT.md
```

**Remove accumulated archives** (they are untracked-by-default clutter, not state — nothing
reads them but `revert`):

```bash
rm backend/agents/prompts/prototype-build/AGENT.v*.md
```

**Uninstall the feature**: delete `prompt_edits.py`, the two `grade.sh` arms and the JSON
sidecar write. Because no runtime file was ever touched, there is nothing else to unwind.
