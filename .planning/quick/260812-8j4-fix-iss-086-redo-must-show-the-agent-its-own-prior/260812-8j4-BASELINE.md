# Quick 260812-8j4 — pre-change baseline + RED evidence (ISS-086 / FIX-228)

Measured on the **pre-change commit `742f0c6e`**, working tree clean, before any edit.
Every figure below is a re-measurement, not a remembered number.

Runtime: `python3.11 -m pytest` from `backend/` (no venv). `lint-imports` from `backend/`.

## Baseline

| Command | Result at `742f0c6e` |
|---|---|
| 10 characterization goldens | **`10 passed`** in 35.23s |
| `lint-imports` | **`Contracts: 4 kept, 0 broken`** (215 files, 525 dependencies) |
| `test_redo_gate_safety.py` + `test_spec_revision_context.py` + `test_spec_revision_cycles.py` + `test_update_specs_enforcement.py` | **`21 passed`** |
| `tests/unit/test_update_specs_ingress_fence.py` | `13 passed` |
| `tests/agents/test_gate_revision_discriminator.py` | `6 passed` |
| `tests/agents/test_cancel_stops_resumed_run.py` | `5 passed` |
| `tests/agents/test_restart_resume.py` | **`7 failed, 48 passed`** — ISS-078's territory, not touched |
| `python3 scripts/knowledge/check_ids.py` | exit **0** |

**One brief figure corrected.** The task brief quoted `test_gate_revision_discriminator.py`
as **29** tests; the file collects **6**. `29` is the sum of the other four suites named in
that same bullet (`update_specs_enforcement` 5 + `ingress_fence` 13 + `spec_revision_cycles`
5 + `gate_revision_discriminator` 6). Measured figures are used throughout.

## ID allocation — max across all four sources

`python3 scripts/knowledge/check_ids.py` at `742f0c6e`:

| Series | register rows | cards | commits | code+docs | max | **allocated** |
|---|---|---|---|---|---|---|
| `FIX-` | 227 | 227 | 227 | 227 | **227** | **FIX-228** |
| `TEST-` | 011 | 011 | 010 | 011 | **011** | **TEST-012** |
| `ISS-` | 089 | 089 | 088 | 089 | **089** | none needed (ISS-086 is closed, not re-filed) |

## Byte-identity anchor (INV-3)

The FIRST (non-redo) dispatch of three gated agents, dumped before any edit
(`scratchpad/dump_first_dispatch.py`, three agents concatenated):

```
sha256  9f84b82e3736f045bde1c243770de255782252315e11cafceedc1a876b5bd24c
bytes   813
```

The same dump is re-taken after the fix and `cmp`-ed. The goldens prove the *normal* path
is unmoved; they cannot prove this one, because they drive with `gate_agent_ids=[]`
(`_scripted_model.py:649`) so no gate ever opens and a redo is unreachable in a golden run.

## RED evidence — `tests/agents/test_redo_prompt_contract.py` at `742f0c6e`

`8 failed, 3 passed`. Every failure is an **assertion raised inside the test body** — zero
pytest errors, so none is a fixture or collection problem masquerading as a RED. (That
distinction is load-bearing here: `_run_agent` swallows a stub `TypeError` into an
`agent_error` event, so a misnamed gate-stub parameter yields ZERO gate firings rather than
an error. It cost one debugging cycle while writing the file.)

```
tests/agents/test_redo_prompt_contract.py:154: in test_redo_dispatch_carries_the_agents_own_prior_output
E   AssertionError: the redo dispatch for domain-analyst does NOT contain the agent's own prior output (delta first->redo = 101 chars, i.e. the instruction block alone)
tests/agents/test_redo_prompt_contract.py:154: in test_redo_dispatch_carries_the_agents_own_prior_output
E   AssertionError: the redo dispatch for epic-architect does NOT contain the agent's own prior output (delta first->redo = 101 chars, i.e. the instruction block alone)
tests/agents/test_redo_prompt_contract.py:154: in test_redo_dispatch_carries_the_agents_own_prior_output
E   AssertionError: the redo dispatch for prototype-plan does NOT contain the agent's own prior output (delta first->redo = 101 chars, i.e. the instruction block alone)
tests/agents/test_redo_prompt_contract.py:175: in test_redo_dispatch_renders_subject_before_instructions
E   AssertionError: assert ('=== PRIOR ARTIFACT UNDER REVISION ===' in '=== ORIGINAL USER REQUEST ===\n...\n=== ADDITIONAL INSTRUCTIONS (REVISE) ===\nadd 2 more pages to it\n=== END ADDITIONAL INSTRUCTIONS ===')
tests/agents/test_redo_prompt_contract.py:193: in test_redo_injects_the_version_actually_being_rejected
E   AssertionError: the FIRST redo must carry v1 — the draft it is rejecting
tests/agents/test_redo_prompt_contract.py:232: in test_redo_at_the_gate_reentry_site_carries_it_too
E   AssertionError: the re-entry redo consumer did not inject the persisted prior output
tests/agents/test_redo_prompt_contract.py:267: in test_redo_at_the_reopened_post_revision_gate_carries_it_too
E   AssertionError: the re-opened-gate redo consumer did not inject the prior output
tests/agents/test_redo_prompt_contract.py:304: in test_task_loop_redo_is_skipped_but_a_whole_artifact_redo_is_not
E   AssertionError: a whole-artifact redo MUST carry the prior output (the ISS-086 fix)

FAILED ...::test_redo_dispatch_carries_the_agents_own_prior_output[domain-analyst]
FAILED ...::test_redo_dispatch_carries_the_agents_own_prior_output[epic-architect]
FAILED ...::test_redo_dispatch_carries_the_agents_own_prior_output[prototype-plan]
FAILED ...::test_redo_dispatch_renders_subject_before_instructions
FAILED ...::test_redo_injects_the_version_actually_being_rejected
FAILED ...::test_redo_at_the_gate_reentry_site_carries_it_too
FAILED ...::test_redo_at_the_reopened_post_revision_gate_carries_it_too
FAILED ...::test_task_loop_redo_is_skipped_but_a_whole_artifact_redo_is_not
==================== 8 failed, 3 passed, 1 warning in 1.42s ====================
```

**The measured `delta first->redo = 101 chars` independently reproduces the analysis's
byte accounting**: `delta = 79 + len(instruction)` = `79 + 22` = `101`. The redo added the
instruction block and *nothing else* — no subject.

### The 3 that pass at baseline, and why that is correct

They are **dormancy guards**, declared as such in the file, not red-first properties:

| test | why it is green before AND after |
|---|---|
| `test_first_dispatch_carries_neither_block` | the fix is keyed on a redo-only loop local |
| `test_blank_redo_stays_a_regenerate` | blank ⇒ regenerate is the *retained* P23 semantics |
| `test_redo_subject_does_not_leak_to_the_next_agent` | consume-once already held for `redo_directive`; the new field must not weaken it |

A green-from-birth "the task-loop case does not inject" would have proved nothing (today
*nothing* injects), so that property is asserted as a **discriminating pair** on the same
agent — task-loop must NOT inject *while* whole-artifact MUST — which is why it appears in
the RED list above.

## Deferred: live Bedrock acceptance (end-of-milestone)

Per the standing rule, and per this task's hard money constraint (no run may be launched,
resumed or gate-approved). The behavioural recipe when it is run:

1. Launch an `od_prototype` build; at the **Task Planner** gate click *Request changes* and
   type `add 2 more pages to it`.
2. Pull versions from `GET /api/runs/{id}/artifacts` — **not** the UI, which wipes v1 on
   `agent_start` (FIX-039).
3. Assert on `task_list` v1 → v2: **every v1 `Task N:` heading still present in v2**, and
   two new ones added. The reported run had 7 → 1 with 0 kept.
4. Confirm `agent_input` for the redo dispatch contains `=== PRIOR ARTIFACT UNDER REVISION
   ===` **before** `=== ADDITIONAL INSTRUCTIONS (REVISE) ===`, and that the dispatch grew by
   roughly the size of the prior artifact rather than by `79 + len(instruction)`.
5. Repeat once with a **blank** instruction and confirm the block is ABSENT (regenerate).
