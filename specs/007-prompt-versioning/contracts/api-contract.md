# API Contract: Applying Advisor Prompt Edits

## REST / RPC / WebSocket surface

**None.** This feature adds no HTTP endpoint, no WebSocket message, no FastAPI router and no
frontend surface. It is a developer CLI in `backend/evals/grading/`.

The existing prompt endpoints (`GET/PUT/DELETE /agents/{agent_id}/prompt`,
`app/api/agents.py:277,303,338`) back the per-user prompt override and are **untouched** — see
spec §9, Out of scope.

---

The contract this feature does have is its **command-line interface**, specified below.

## `grade.sh apply-advice <run-id> --agent <agent-id>`

Applies every edit the advisor proposed for one agent, archiving the current prompt body first.

**Arguments**

| Argument | Required | Meaning |
|---|---|---|
| `<run-id>` | yes | A run folder id, resolved the way every other `grade.sh` verb resolves it (exact, then suffix, then unique fragment) |
| `--agent <id>` | yes | The agent whose prompt to edit. Must have advice in that run |

**Preconditions**

- `reports/prompt_advice_<token>.json` exists in the run folder.
- `backend/agents/prompts/<agent-id>/AGENT.md` exists and has a terminated frontmatter block.

**Effects**, in this order:

1. Compute the fully-edited body in memory. Any failure here aborts with **nothing written**.
2. Write the current body to `AGENT.v<max+1>.md` (body only, no frontmatter).
3. Write `AGENT.md` — original frontmatter bytes + new body.
4. Re-read and assert the frontmatter prefix is byte-identical and still parses.

**Output** — per-edit lines (index, action, section, ± the changed text), a confirmation that
frontmatter is unchanged with its field count, and the exact `revert` command.

**Exit codes**

| Code | Meaning |
|---|---|
| 0 | Applied |
| 2 | Usage error; unknown run or agent; no advice for that agent; advice exists only as markdown (names `grade.sh advise <run-id>` as the fix) |
| 9 | An edit could not be applied — `current_text` absent or non-unique, or an `add` anchor unresolvable. Nothing written |
| 10 | Every proposed edit targeted frontmatter and was refused, so there was nothing to apply |

Note the asymmetry between 9 and 10: an unapplicable edit (9) aborts everything, because the
*other* edits may depend on text it would have changed. A refused frontmatter edit (10) is
skipped and the rest still apply, because it was never going to touch the body.

## `grade.sh revert <agent-id>`

Restores the most recent archived body.

**Effects**: reads the highest-numbered `AGENT.vN.md`, writes it as the body of `AGENT.md`
(frontmatter preserved byte-for-byte), deletes that archive file. Repeated invocations walk
back through history.

**Exit codes**: `0` reverted · `2` unknown agent, or no archive to revert to.

## `grade.sh advise <run-id>` *(existing — one behaviour change)*

Unchanged in interface. Now additionally writes `reports/prompt_advice_<token>.json` beside the
existing `prompt_advice_<token>.md`. No output or exit-code change.

## Compatibility

Both new verbs are additive. No existing `grade.sh` command changes its arguments, output
format or exit codes. Exit codes 9 and 10 are new and do not collide with the grading suite's
existing set (`0`, `2`, `3`, `4`, `5`, `6`).
