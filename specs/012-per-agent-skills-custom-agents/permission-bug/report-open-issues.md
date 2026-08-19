# Open issues

**Date:** 2026-08-16
**Status of the work:** fix applied locally, **nothing committed**

---

## 1. The red baseline was never recorded

`test_tool_grant_invariants.py` was written before the fix but never run against unfixed
code. The green result (93 pass / 1 fail) is real, and no assertion was weakened afterwards
— the fleet asserts are byte-identical to as written — but that claim rests on inspection
rather than evidence.

**Recover it:**

```bash
cd backend
git stash push agents/factory.py agents/prompts/custom-agent/AGENT.md \
               agents/workflows/compiler.py app/agents/deep_agent_runner.py
../venv/bin/python -m pytest tests/agents/test_tool_grant_invariants.py -q
git stash pop
```

Expected red: **61 text-only failures + 1 ceiling failure = 62.** Any other number means
the tests don't pin what they claim, and that must be resolved before trusting the fix.

### What changed in the test file after the fix, for the record

| Change | Effect |
|---|---|
| Dropped `!= custom-agent` exclusion from the fleet lists | **Widens** coverage, 86 → 87 agents |
| Renamed `test_custom_agent_instance_keeps_the_filesystem` → `…inherits_the_template_declaration` | Docstring only; `assert` untouched |
| Added `test_custom_agent_template_declares_the_filesystem_it_needs` | New assertion |
| Deleted `test_built_in_agent_is_not_mistaken_for_a_custom_instance` | Tested the `CUSTOM_AGENT_PREFIX` mechanism, which the shipped fix does not use. Would still have passed. |

The deeper mistake: the tests were written describing a *mechanism* (prefix-based scoping)
before that mechanism was chosen, then the approach changed to declaration-based. Tests
should pin **behaviour** — "text-only agents get no filesystem, composed agents keep it" —
not implementation.

---

## 2. Six existing assertions still pin the removed grant

These assert R-22 behaviour and will now fail:

```
tests/agents/test_create_runner.py             4   (~317, 323, 594, 808)
tests/agents/test_mcp_client.py                1   (~119)
tests/agents/test_text_only_prompt_hygiene.py  1   (~54)
```

Left untouched deliberately — each needs a decision about what it should now prove, and
after the process problem in §1 it would be wrong to quietly rewrite assertions.

---

## 3. `test_step_declaring_write_files_is_granted_write` — deliberately red

```python
workflow_ceiling = ToolPermissions(exec=trusted, spawn_subagents=trusted)
#                                  write_files not passed → dataclass default False
effective = intersect(ceiling, ceiling, step_grant)   # False AND False AND True → False
```

A step declaring `write_files: true` resolves to `False`, **for every step in the system**,
composed workflows included.

**This is not a live bug.** The only consumers of `.write_files` in the entire codebase are
the three lines in the `tool_grant` compile trace added during this work. Nothing reads it,
so nothing is affected today. What it pins is that the Composer's "write files" checkbox is
compiled, validated, and discarded.

### Do not fix it with the one-liner

Adding `write_files=True` to the ceiling turns the test green and is side-effect-free (no
hook declares `required_permission="write_files"`). **But it would assert an enforcement
that still doesn't exist** — a green test claiming permissions are honoured when nothing
reads them. That is the same failure mode as editing a test to go green.

**Options:**

- **(a) `xfail(strict=True)`** — suite goes fully green, gap stays visible in the report,
  and it **fails loudly the day someone implements enforcement**, so it can't rot.
  *Recommended.*
- (b) Leave red — honest, but a permanently red suite trains people to ignore failures.

It turns green for the right reason at step 3 of the
[target design](report-target-design.md).

### Evidence

```
ceiling.write_files = False
step.write_files    = True
EFFECTIVE           = False
```

Comment context: the ceiling's comment block individually justifies `exec`,
`spawn_subagents`, `network` and `secrets` being closed. `write_files` and `git` are the
only permissions with **no stated rationale** — the signature of an omission, not a
decision.

---

## 4. Carried over from the composed-workflow signoff

- **No frontend Revise entry point for composed runs.** `DashboardLayout.tsx`'s revise
  dispatch (~line 1787) maps `ppt` / `user_stories` / `prototype` / `app_builder`; `custom`
  falls through to nothing. The backend path works (`custom_revision` is implemented and
  verified end-to-end); only the UI entry is missing.
- **`plan.md` leaks into composed revision output.** `_DELIVERABLE_EXCLUDE` in
  `app/agents/sandbox.py` is `frozenset({"PLANNER.md"})`. A temporary addition of
  `"plan.md"` was reverted at request, so the planner's working file appears in the
  revision bundle.
- **`backend/CLAUDE.md`'s Tool Sets table is stale** — still documents
  `[] → ([], exclude_builtin=True)`. That is correct again *as of this fix*, but it never
  described the shipped R-22 behaviour, so it should be checked rather than assumed.

---

## 5. Uncommitted state

```
M  agents/factory.py                          grant removed; trace + declared/why
M  agents/prompts/custom-agent/AGENT.md        tools: [workspace] declared
M  agents/workflows/compiler.py                + logger, + compile trace
M  app/agents/deep_agent_runner.py             + bind trace, staging narrowed to read
?? tests/agents/test_tool_grant_invariants.py  94 tests
?? specs/012-…/permission-bug/*.md             these reports
M  tools/api/runs/run.ppt.http                 unrelated, from earlier signoff work
```

Also outside the repo:

```
.vscode/settings.json                          interpreter + cwd fix, httpyac controller off
~/.vscode/extensions/                           littlefoxteam adapter parked as .disabled-*
```

Restore the extension with:

```bash
cd ~/.vscode/extensions && mv .disabled-littlefoxteam.vscode-python-test-adapter-0.8.2 \
                              littlefoxteam.vscode-python-test-adapter-0.8.2
```

---

## 6. Not investigated

- **Whether any run since the merge silently lost its deliverable in production.** Locally
  `RUNS_ROOT=./runs` so sandboxes survive; in production `RUNS_ROOT` defaults to `/app/runs`
  and orphaned files may already be gone. Worth checking whether any customer-facing run
  shipped narration instead of an artifact.
- **`git` permission** — closed in the ceiling with no rationale, same shape as
  `write_files`. Probably the same omission; not confirmed.
- **MCP bypass** — `prewarmed_mcp_tools` force `exclude_builtin=False` regardless of
  declaration. Under a "manifest is the only source of truth" rule this is a hole. Not
  addressed by the current fix.
