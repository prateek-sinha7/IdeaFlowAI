# Feature Specification: Applying Advisor Prompt Edits

**Spec ID**: 007-prompt-versioning
**Created**: 2026-07-30
**Rewritten**: 2026-07-30 — the first draft designed a version-selection system (pinned
versions, an `ab` command, loader and factory changes). That was more than the job needs. This
version does one thing: **apply the advisor's suggested edits to a prompt, keeping the old one.**
See [`clarifications.md`](clarifications.md).
**Status**: **OBSOLETE (2026-08-10).** The status line above previously read "Specified — not
implemented", which was stale: all 68 tasks were in fact completed (see
[`build-summary.md`](build-summary.md)). They were completed against `backend/evals/grading/`,
which was then deleted by [007-minimal-eval](../007-minimal-eval/spec.md), so no live code
remains. Read for history only.
**Stack**: python 3.11 | no runtime changes | no frontend surface
**Depends on**: [005-prompt-eval-scoring](../005-prompt-eval-scoring/spec.md) (`evals/grading/`, built)

---

## 1. Problem

After a graded run, `prompt_advisor.py` writes `reports/prompt_advice_<agent>.md` containing
typed, structured edits — `PromptEdit{action, section, current_text, proposed_text, reason}`
(`model/prompt_advisor.py:34-68`). Acting on them means opening `AGENT.md` and retyping them by
hand.

That is slow, it is error-prone, and it destroys the old prompt — so "that made it worse, put it
back" is a git operation on a dirty tree rather than a command.

Everything else already works. Runs already record which prompt they used
(`system_prompt_hash`, `artifacts.py:115`), `grade.sh compare a b` already diffs two runs with a
noise guard, and `grade.sh history <agent>` already groups runs by prompt. The only missing
piece is the edit itself.

The model is not the variable — Haiku 4.5 without thinking is pinned
(`app/core/config.py:68,87,92`). The prompt body is the only thing being tuned.

## 2. What this adds

Two commands.

```
grade.sh apply-advice <run-id> --agent <id>     apply the advisor's edits
grade.sh revert <agent>                          put the previous prompt back
```

**Nothing else changes.** No new runtime behaviour, no version selection, no A/B command, no
changes to the loader, factory, engine or kernel.

## 3. How it works

`AGENT.md` is always the live prompt. Applying an edit archives the old body beside it:

```
BEFORE                          AFTER
prototype-build/                prototype-build/
  AGENT.md      <- live           AGENT.v1.md   <- the old body, kept
                                  AGENT.md      <- live, with edits applied
```

Apply again and the next archive is `AGENT.v2.md`. Higher number = more recent. `AGENT.md` is
always newer than every archive.

### Why this is safe

The engine reads `AGENT.md`, exactly as it always has. It never learns that archives exist:
`loader.load_agent_spec` opens `agent_dir / "AGENT.md"` by name (`loader.py:144`), and
`loader.list_agent_ids` — which is what builds `PIPELINE_AGENTS` at import time
(`registry.py:57-79`) — matches that filename exactly (`loader.py:201`). An `AGENT.vN.md` file
is invisible to it.

That is why **zero runtime files are touched by this spec.** The whole feature lives in the
evals CLI and writes files on disk.

The frontmatter is the engine's contract — `id`, `pipeline_type`, `order`, `produces`,
`consumes`, `tools`, `gate`, `injects`, `model`. Change it and you can break the registry, the
DAG validation, or the manifest/registry agreement the engine asserts at run entry. So:

- **`apply-advice` never touches frontmatter.** It reads `AGENT.md`, edits only the body below
  the closing `---`, and writes the frontmatter back byte-for-byte.
- **Archives are body-only.** No frontmatter, so an archive can't drift from the contract.

## 4. Requirements

- **R-01 — `AGENT.md` is always the live prompt.** Nothing is renamed; nothing needs to know
  about versions to run.
- **R-02 — Archives are body-only, numbered upward.** First archive is `AGENT.v1.md`, then
  `AGENT.v2.md`. Never overwritten, never renumbered.
- **R-03 — Frontmatter is preserved byte-for-byte** by every write to `AGENT.md`.
- **R-04 — An advisor edit that targets frontmatter is refused**, naming the field, and the
  remaining edits still apply.
- **R-05 — All proposed edits are applied.** No interactive picking. If the result is worse,
  `revert` costs one command.
- **R-06 — An edit whose `current_text` is missing, or appears more than once, is a hard
  error.** No fuzzy matching, no "closest match" — a silently misplaced edit is worse than a
  failed command. On such a failure nothing is written at all: `AGENT.md` and the archives are
  left exactly as they were.
- **R-07 — The command prints the diff** it applied, and the revert command to undo it.
- **R-08 — `revert <agent>` restores the highest-numbered archive** into `AGENT.md` (frontmatter
  preserved) and deletes that archive, so repeated reverts walk back through history.
- **R-09 — No git operations.** The commands write files. Committing is yours.
- **R-10 — Archives stay invisible to the runtime.** A test asserts the agent count and every
  `PIPELINE_AGENTS` list are unchanged with `AGENT.vN.md` files present on disk.

**Exit codes** — `0` ok · `2` usage/no advice found for that agent · `9` an edit could not be
applied (R-06) · `10` an edit targeted frontmatter and was refused (R-04).

## 5. Scenarios

### Story 1 — Apply the advice (P1)

1. **Given** a finished run with advice for `prototype-build`, **When** I run
   `grade.sh apply-advice 260730-173912 --agent prototype-build`, **Then** the old body is saved
   to `AGENT.v1.md`, the edits are applied to `AGENT.md`, and the diff is printed.
2. **Given** that command completed, **When** I run the pipeline, **Then** it uses the new
   prompt — no restart flag, no config change, nothing to remember.
3. **Given** an advisor edit targeting a frontmatter field, **Then** it is refused by name and
   the other edits still apply.
4. **Given** an edit whose `current_text` no longer appears in the prompt, **Then** the command
   fails, says which edit and why, and writes nothing.

### Story 2 — Put it back (P1)

1. **Given** `AGENT.v1.md` exists, **When** I run `grade.sh revert prototype-build`, **Then**
   `AGENT.md` returns to that body and `AGENT.v1.md` is removed.
2. **Given** no archive exists, **Then** revert exits 2 saying there is nothing to revert to.

### Story 3 — See whether it helped (P2)

No new command. Re-run the same graded config and use what already exists:

```
grade.sh small                    # run again with the new prompt
grade.sh compare <old> <new>      # existing, with its noise guard
grade.sh history prototype-build  # existing, grouped by prompt
```

## 6. Design

One new module, two CLI verbs, no runtime changes.

| File | Change |
|---|---|
| `evals/grading/model/prompt_edits.py` | **New.** Pure functions: split frontmatter/body, apply a `PromptEdit` list, pick the next archive number, revert. No model calls, no network — unit-testable offline. |
| `evals/grading/grade_runner.py` | Two subcommands wired to the above |
| `evals/grading/grade.sh` | `apply-advice`, `revert` |
| `evals/grading/docs/README.md` | Runbook entry |

Advice is read from the run folder the advisor already wrote (`reports/prompt_advice_<agent>.md`
and its structured source), so `apply-advice` needs no model call and costs nothing.

**Data model**: none. No database, no schema, no config. Prompts are files, and stay files.

## 7. Non-functional

| Requirement | Target | Measurement |
|---|---|---|
| Backward compatibility | Runtime behaviour bit-identical; no runtime file edited | `git diff` touches no file under `backend/agents/` or `backend/app/`; the 5 characterization goldens pass unmodified |
| Engine/kernel safety | `PIPELINE_AGENTS` unchanged with archives present | R-10 test |
| Cost | Zero tokens — `apply-advice` reads a file the run already wrote | No model call in the code path |
| Speed | One command, no interaction | Story 1 |
| Test coverage | All of `prompt_edits.py` covered offline | pytest, existing offline suite |

## 8. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| An edit lands in the wrong place | Medium | High | R-06 — exact unique match or hard failure, nothing written |
| Frontmatter corrupted, breaking the registry or DAG | Low | High | R-03/R-04 — frontmatter written back byte-for-byte; frontmatter edits refused |
| Archive files confuse the runtime | Low | High | R-10 — the loader matches `AGENT.md` by exact filename; asserted by test |
| Archives accumulate | Medium | Low | They are small text files; `grade.sh check` can warn past a threshold |
| Prompt change swept into a feature commit | Medium | Low | Not solved here (R-09, no git ops). Run artifacts still record which prompt was used via `system_prompt_hash` |
| The score can't yet tell a good prompt from a bad one | High until 008 lands | High | [008-grading-calibration](../008-grading-calibration/spec.md) fixes the rubric. This spec only *applies* edits — deciding whether one helped depends on 008 |

## 9. Out of scope

Version selection at runtime · an `ab` command · pinning a prompt for a run · a lock file ·
API or UI surface · DB-backed prompts · git operations · per-user prompt overrides
(`app/agents/prompt_overrides.py`, untouched) · versioning guardrails, skills or the
constitution.

## 10. Documents

| Document | Holds |
|---|---|
| `spec.md` (this file) | What it does and why |
| [`clarifications.md`](clarifications.md) | The decisions, including what was dropped from the first draft |
| [005-prompt-eval-scoring](../005-prompt-eval-scoring/spec.md) | The grading system this sits beside |
| [008-grading-calibration](../008-grading-calibration/spec.md) | Makes the score worth acting on |

**Execution note**: `apply-advice` and `revert` cost no tokens and are safe to run. Re-grading
(Story 3) is live — per standing instruction, the developer runs live eval commands.
