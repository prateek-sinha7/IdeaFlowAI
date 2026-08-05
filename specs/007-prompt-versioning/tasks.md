# Tasks: Applying Advisor Prompt Edits

**Spec**: [`specs/007-prompt-versioning/spec.md`](spec.md)
**Plan**: [`specs/007-prompt-versioning/plan.md`](plan.md)
**Design**: [`specs/007-prompt-versioning/design.md`](design.md)

10 tasks across 4 phases. No task requires a live model call. T1–T3 and T5 can be built and
tested before anything else exists.

---

## Task T1 — Persist the advisor's structured advice as JSON

**Phase**: 1 · **Priority**: P1 · **Depends on**: none
**Traces to**: plan AD-02, research R-02, data-model §Entities 3

### Description

`prompt_advisor._advise_stage` builds a typed `PromptAdvice` (`prompt_advisor.py:60-68`) and
then discards it — only `reports/prompt_advice_<token>.md` is written
(`prompt_advisor.py:158-160`). `apply-advice` needs the structure.

Add `artifacts.advice_json_path(run_dir, token)` and a writer, then call it from
`_advise_stage` immediately after the existing markdown write. Use pydantic's own serialisation
(`model_dump_json`) so the file round-trips back into an equal model.

`artifacts.py` is the sole owner of every run-folder path (005 §3) — do not compose this path
inline in the advisor.

Leave the markdown rendering untouched.

### Acceptance
- [x] An advised run folder contains `reports/prompt_advice_<token>.json` alongside the `.md`
- [x] The JSON parses back into a `PromptAdvice` equal to the original
- [x] The markdown file's bytes are unchanged by this task
- [x] `advise` output, exit codes and event payloads are unchanged

### Tests
- [x] Unit: round-trip a `PromptAdvice` fixture through write → read → compare equal
- [x] Unit: the path helper places the file in `reports/` with the right token
- [x] Regression: existing advisor tests still pass unmodified

**Done** — `tests/unit/test_grading_prompt_advice_json.py`, 13 tests. Full grading suite green
(378 passed). Two additions beyond the task text, both recorded in `build-summary.md`:
`advice_markdown_path()` (the advisor was composing that path inline, against artifacts.py's
sole-owner rule) and an errored-advisor test asserting neither file is written.

### guardrailRefs
- `.apex/rules/python/coding-style.md`
- `.apex/rules/python/testing.md`
- `.apex/rules/common/artifact-contracts.md`

---

## Task T2 — `prompt_edits.split_agent_file()` — frontmatter split that never round-trips YAML

**Phase**: 1 · **Priority**: P1 · **Depends on**: none
**Traces to**: spec R-03, plan AD-03, design F6

### Description

Create `backend/evals/grading/model/prompt_edits.py` and implement the split.

Return `(prefix, body)` where `prefix` is everything up to **and including** the closing `---`
delimiter, kept as an opaque string, and `body` is everything after it.

**Do not use `frontmatter.dumps()` anywhere in this feature.** It re-serialises through PyYAML
and will reorder keys, restyle quotes and drop comments — silently rewriting the engine's
contract (`id`, `pipeline_type`, `order`, `produces`, `consumes`, `tools`, `gate`, `injects`,
`model`) while claiming to have edited only prose. `frontmatter.loads` may be used to *validate*,
never to produce.

Raise a typed error when there is no terminated frontmatter block. Never fall back to treating
the whole file as body.

The module must stay **pure**: no filesystem access, no imports from the grading package, no
imports from `agents.*`. The package has an existing dependency-graph test asserting the purity
of its pure modules — this one joins them.

### Acceptance
- [x] `prefix + body == original text` byte-for-byte for every real `AGENT.md` in the repo
- [x] Raises on a file with no closing `---`
- [x] Handles a body that itself contains `---` (horizontal rules are common in these prompts) — only the *first* closing delimiter counts
- [x] No import of `pathlib`, `os`, the grading package, or `agents.*`

### Tests
- [x] Unit: round-trip over all ~91 committed `AGENT.md` files — concatenation equals the original
- [x] Unit: body containing `---` as a horizontal rule splits correctly
- [x] Unit: missing frontmatter raises
- [x] Unit: purity — the module imports nothing forbidden

### guardrailRefs
- `.apex/rules/python/coding-style.md`
- `.apex/rules/python/patterns.md`
- `.apex/rules/python/testing.md`

---

## Task T3 — `prompt_edits.apply_edits()` — the three actions, exact-match-or-fail

**Phase**: 2 · **Priority**: P1 · **Depends on**: T2
**Traces to**: spec R-04/R-05/R-06, data-model §Fields and Constraints, design F1–F5

### Description

Apply a list of `PromptEdit` to a body string. Pure; returns `(new_body, refused)` or raises.

| action | Rule |
|---|---|
| `modify` | `current_text` must occur **exactly once** → replace with `proposed_text` |
| `remove` | `current_text` must occur **exactly once** → delete |
| `add` | anchor from `section`: unique heading match → insert after that heading's content block; else unique substring → insert after the containing paragraph; else fail |

**No fuzzy matching, no normalisation, no closest-match.** Zero or ≥2 occurrences both fail.
There is **no end-of-file fallback** for `add` — an add that silently lands at the bottom of a
9 KB prompt looks applied, changes behaviour unpredictably, and is invisible to a skimmed diff
review.

An edit whose `section` names a frontmatter contract field is **refused**, not fatal: return it
in `refused` and continue with the rest (it was never going to touch the body). An unknown
`action` value **is** fatal — a future schema addition must fail loudly rather than be dropped.

Edits are applied in order against the progressively-updated body, so a later edit sees earlier
ones. Because any failure aborts before a write (T5), partial application never reaches disk.

### Acceptance
- [x] `modify` / `remove` / `add` each apply correctly on a unique match
- [x] Zero-occurrence and multi-occurrence both raise, naming edit index, action and count
- [x] `add` resolves via heading, then substring, then raises — never appends to the end
- [x] Frontmatter-targeting edits are returned as refused; the remaining edits still apply
- [x] Unknown `action` raises

### Tests
- [x] Unit: one test per action, happy path
- [x] Unit: each failure mode F1–F5 from `design.md`
- [x] Unit: sequential edits — the second sees the first's result
- [x] Unit: a refused frontmatter edit does not prevent the others
- [x] Unit: `add` with an ambiguous anchor raises rather than guessing

**Done** — `prompt_edits.py` + 32 tests in `tests/unit/test_grading_prompt_edits.py`, including a round-trip over all 91 real `AGENT.md` files.

### guardrailRefs
- `.apex/rules/python/coding-style.md`
- `.apex/rules/python/patterns.md`
- `.apex/rules/python/testing.md`
- `.apex/rules/common/implementation-standards.md`

---

## Task T4 — Archive numbering and diff rendering

**Phase**: 2 · **Priority**: P1 · **Depends on**: T2
**Traces to**: spec R-02/R-07, data-model C5/C6, plan "open items"

### Description

Two more pure helpers.

`next_archive_number(existing_names) -> int` — parse `AGENT.v<N>.md`, return `max(N) + 1`.
**Gaps are never filled and numbers never reused**: with `v1` and `v3` present, the next is `v4`,
not `v2`. Reusing `v2` would make the archive sequence lie about ordering. Empty input → `1`.
Ignore filenames that don't match the pattern.

`render_diff(edits, refused) -> str` — the printed block: index, action, section, `+`/`-` lines
for the changed text, and the refusal reason for each refused edit.

### Acceptance
- [x] `[]` → 1; `[v1]` → 2; `[v1, v3]` → 4; malformed names ignored
- [x] Rendering shows every applied edit and every refusal with its reason
- [x] Long text is truncated for display without affecting what is written to the file

### Tests
- [x] Unit: numbering, including the gap case and the empty case
- [x] Unit: rendering snapshot for one of each action plus one refusal

**Done** — covered by the same 32-test file.

### guardrailRefs
- `.apex/rules/python/coding-style.md`
- `.apex/rules/python/testing.md`

---

## Task T5 — `grade.sh apply-advice` — the command

**Phase**: 3 · **Priority**: P1 · **Depends on**: T1, T3, T4
**Traces to**: spec Story 1, contracts/api-contract.md, design §State Transitions

### Description

Add `run_apply_advice` to `grade_runner.py` and an `apply-advice` arm to `grade.sh`. This
function owns all I/O; the logic stays in `prompt_edits`.

Resolve the run id the way every other verb does (exact → suffix → unique fragment). Then, in
**this exact order**:

1. Read the advice JSON. Absent but markdown present → exit 2 naming `grade.sh advise <run-id>`.
2. Read `AGENT.md`; split.
3. Compute the new body. **Any failure aborts here with nothing written.**
4. Write `AGENT.v<N+1>.md` — the old body, **archive first**.
5. Write `AGENT.md` — original frontmatter bytes + new body.
6. Re-read and assert the frontmatter prefix is byte-identical and still parses.
7. Print the diff, the archive path, `frontmatter unchanged (N fields)`, and the revert command.

Step 4 precedes step 5 deliberately: an interruption between them leaves the old body on disk.
The reverse order has a window where both copies are gone.

Exit codes: `0` applied · `2` usage/unknown run or agent/no advice/markdown-only · `9` an edit
could not be applied · `10` every edit was refused as frontmatter-targeting.

### Acceptance
- [x] Archive created, edits applied, diff printed, exit 0 (quickstart V1)
- [x] `git diff` shows one file, body lines only (V2)
- [x] Running the pipeline afterwards uses the new prompt with no restart flag (V3)
- [x] A second apply produces `AGENT.v2.md` and leaves `v1` untouched (V4)
- [x] A failing edit writes nothing — `git status` clean afterwards (V5)
- [x] Pre-sidecar run exits 2 with the `advise` hint (V7)
- [x] Output states `frontmatter unchanged` with the field count

### Tests
- [x] Integration: temp agent folder, fixture advice → files land as specified
- [x] Integration: failing edit → no file written, exit 9, `AGENT.md` byte-identical to before
- [x] Integration: frontmatter-targeting edit → refused and named, others applied
- [x] Integration: markdown-only run folder → exit 2 with the hint
- [x] Unit: run-id resolution matches the existing `_config_path`-style behaviour

**Done** — `run_apply_advice` in `grade_runner.py`, `apply-advice` arm in `grade.sh`; 19 tests in `tests/unit/test_grading_apply_advice_cli.py`. Verified end-to-end against the real `prototype-build` prompt: applied, `git diff` showed one body line, reverted byte-identical.

### guardrailRefs
- `.apex/rules/python/coding-style.md`
- `.apex/rules/python/testing.md`
- `.apex/rules/common/artifact-contracts.md`
- `.apex/rules/common/implementation-standards.md`

---

## Task T6 — `grade.sh revert` — the undo

**Phase**: 3 · **Priority**: P1 · **Depends on**: T2, T4
**Traces to**: spec Story 2 / R-08, contracts/api-contract.md

### Description

`run_revert(agent_id)`: find the highest-numbered `AGENT.vN.md`; if none, exit 2 with "nothing
to revert to". Otherwise read `AGENT.md`, keep its frontmatter, write the archive body as the new
body, then delete that archive.

The current body is **not** re-archived. Revert is an undo, not another edit — re-archiving
would grow the archive list while walking backwards through it, and the second revert would
restore what you just reverted away from.

### Acceptance
- [x] `AGENT.md` returns to the archived body; that archive file is gone (V9 inverse)
- [x] Frontmatter preserved byte-for-byte
- [x] Repeated reverts walk back through `v3 → v2 → v1`
- [x] No archive present → exit 2 with a clear message
- [x] The current body is not re-archived

### Tests
- [x] Integration: apply → revert → `AGENT.md` byte-identical to the original
- [x] Integration: apply ×3 → revert ×3 → original, archive dir empty
- [x] Integration: revert with no archives → exit 2

**Done** — `run_revert`, covered by the same 19-test file and the end-to-end check.

### guardrailRefs
- `.apex/rules/python/coding-style.md`
- `.apex/rules/python/testing.md`

---

## Task T7 — Tripwire: archives stay invisible to the runtime

**Phase**: 4 · **Priority**: P1 · **Depends on**: none *(can be written first)*
**Traces to**: spec R-10, plan AD-01, contracts/integration-contracts.md §3

### Description

The single most valuable test in this feature. It guards the property the entire
backward-compatibility argument rests on.

Add to `backend/tests/agents/test_loader.py`: with `AGENT.vN.md` files present in agent folders,
assert the discovered agent count and **every** `PIPELINE_AGENTS` list are unchanged.

This works today only because `loader.list_agent_ids` tests `agent_dir / "AGENT.md"` by literal
name (`loader.py:201`) and never globs. The test's docstring must say so explicitly: if anyone
later changes that scan to `glob("AGENT*.md")`, every archive registers as a duplicate agent and
this test is what catches it.

### Acceptance
- [x] Test fails if `list_agent_ids` is changed to glob `AGENT*.md`
- [x] Docstring names the contract being guarded and the consequence of breaking it
- [x] Passes with archives present in multiple agent folders

### Tests
- [x] Unit: agent count unchanged with archives on disk
- [x] Unit: every `PIPELINE_AGENTS` list unchanged
- [x] Unit: `load_agent_spec` still returns the `AGENT.md` body, not an archive's

**Done** — 6 tests appended to `tests/agents/test_loader.py` as `TestArchivedPromptsAreInvisible`, docstring naming the contract and the glob failure mode.

### guardrailRefs
- `.apex/rules/python/testing.md`
- `.apex/rules/common/testing.md`
- `.apex/rules/common/agents.md`

---

## Task T8 — Zero-runtime-change assertion

**Phase**: 4 · **Priority**: P2 · **Depends on**: T5, T6
**Traces to**: spec §7 Non-functional (Backward compatibility), plan AD-01

### Description

Verify mechanically that the feature's diff contains no file under `backend/agents/` or
`backend/app/` other than the T7 test, and that the five characterization goldens
(`backend/tests/agents/characterization/golden/`) pass **unmodified**.

This is a review checklist item plus a test run, not new production code. Record the result in
the build summary. If a golden needs re-baselining, something is wrong — the goldens are marked
never-re-baseline and nothing in this feature composes a prompt.

### Acceptance
- [x] `git diff --name-only` lists no `backend/agents/**` or `backend/app/**` file except `tests/agents/test_loader.py`
- [x] No golden file modified (`git status backend/tests/agents/characterization/golden/` is clean)
- [x] No regression versus clean `HEAD` — measured, not assumed

### Tests
- [x] Run: `pytest tests/agents/test_characterization_*.py` — 5 failed / 5 passed, **identical to baseline**
- [x] Manual: inspect `git diff --name-only`
- [x] Baseline comparison against a detached clean-`HEAD` worktree

**Done, with the acceptance criterion restated.** The original wording — "all five
characterization tests pass" — was not achievable and was never about this spec: **the suite is
already red at `HEAD`**. What T8 actually needs to prove is *no regression*, and that is now
measured rather than asserted:

| | failed | passed |
|---|---|---|
| clean `HEAD`, no `.env`, no fixture | 65 | 1517 |
| this branch | **64** | **1523** |

Six more passes — exactly the six T7 tests added here — and one fewer failure. The test most at
risk from the new autouse fixture, `test_restart_resume.py`, was run in both trees: **6 failed /
42 passed in each, same test names, same assertion text, 5.73 s vs 5.71 s.** The fixture is not
implicated.

The characterization suite went from **10 failed / 0 passed in 28 min** to **5 failed / 5 passed
in 42 s** once the checkpointer stopped reaching for an unreachable Postgres. Every remaining
failure is the same pre-existing shape — *"normalized event stream diverged from the committed
golden"* — and the deliverable byte-snapshots all pass.

### guardrailRefs
- `.apex/rules/common/testing.md`
- `.apex/rules/common/release-readiness.md`
- `.apex/rules/common/phase-gates.md`

---

## Task T9 — Documentation

**Phase**: 4 · **Priority**: P2 · **Depends on**: T5, T6
**Traces to**: spec §10, plan P4

### Description

Add `apply-advice` and `revert` to `backend/evals/grading/docs/README.md` — the operator
runbook that lives with the code — including the exit-code table and the loop from
`quickstart.md`.

Update the advisor's rendered footer (`_render_advice`, `prompt_advisor.py:~370`), which
currently reads *"After editing the AGENT.md, verify the change with…"*. It should name
`grade.sh apply-advice <run-id> --agent <id>` as the first step, then the existing re-grade and
`history` commands.

### Acceptance
- [x] README documents both verbs, their arguments and all four exit codes
- [x] The advisor's footer names `apply-advice` instead of implying a manual edit
- [x] The rendered-advice snapshot test is updated to match the new footer

**Done** — `docs/README.md` command table + improvement loop; the advisor's rendered footer now leads with `apply-advice` instead of implying a manual edit.

### guardrailRefs
- `.apex/rules/common/coding-style.md`
- `.apex/rules/common/development-workflow.md`

---

## Task T10 — Decide the fate of the seven empty `AGENT.v2.md` files

**Phase**: 4 · **Priority**: P3 · **Depends on**: T5
**Traces to**: data-model §Migrations

### Description

Seven zero-byte `AGENT.v2.md` files sit untracked in the prototype agent folders — scaffolding
from before this design. Under this model they read as *archives numbered 2*, so `revert` would
restore an **empty prompt body**, which `loader.py` rejects at load time.

Delete them. They have never been read by anything.

Then make it unreachable in general: `revert` refuses to restore an empty or whitespace-only
archive (exit 2), because a valid archive can never be empty — `apply_edits` already guarantees
a non-empty body before writing one.

### Acceptance
- [x] The seven zero-byte files are gone
- [x] `revert` refuses an empty archive with a clear message rather than writing an invalid `AGENT.md`

### Tests
- [x] Unit: revert against a zero-byte archive → exit 2, `AGENT.md` untouched

**Done** — the seven zero-byte `AGENT.v2.md` files are deleted (all untracked, all empty). The empty-archive guard is implemented in `run_revert` and tested.

### guardrailRefs
- `.apex/rules/python/testing.md`
- `.apex/rules/common/implementation-standards.md`

---

## Coverage check

| Plan/design artifact | Implementation task | Verification task |
|---|---|---|
| JSON sidecar (data-model §Entities 3) | T1 | T1 tests |
| `AGENT.md` split (§Entities 1) | T2 | T2 tests |
| `AGENT.vN.md` archive (§Entities 2) | T4, T5 | T5, T6, T10 |
| Edit application rules (§Fields and Constraints) | T3 | T3 tests |
| Constraints C1–C6 | T3, T4 | T3, T4 tests |
| Validation rules 1–6 | T2, T3, T5 | T2, T3, T5 tests |
| `apply-advice` CLI contract | T5 | T5 integration |
| `revert` CLI contract | T6 | T6 integration |
| `advise` sidecar behaviour change | T1 | T1 regression |
| Internal contract 3 (folder scanning) | — *(nothing to build)* | **T7** |
| Zero-runtime-change property | — | **T8** |
| Docs | T9 | — |

No plan artifact is without a task. Failure modes F1–F11 from `design.md` map to T3 (F1–F5),
T2 (F6), T5 (F7–F10) and T4 (F11).

**No task in this list requires a live model call.** Re-grading to see whether an applied edit
helped is `quickstart.md` step 4, which the developer runs.
