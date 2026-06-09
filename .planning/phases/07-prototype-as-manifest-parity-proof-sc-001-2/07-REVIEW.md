---
phase: 07-prototype-as-manifest-parity-proof-sc-001-2
reviewed: 2026-06-09T00:00:00Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - backend/agents/capabilities/context_providers/opendesign.py
  - backend/agents/execution_engine/engine.py
  - backend/tests/agents/test_context_providers.py
  - backend/tests/agents/characterization/_normalize.py
findings:
  critical: 1
  warning: 3
  info: 2
  total: 6
status: issues_found
adjudicated_critical: 0
adjudication: >-
  CR-01 (BLOCKER) REJECTED as false-positive. The is_builder example gate is the deliberate,
  documented pre-Phase-7 behavior (added Phase 4 / commit 218582d; rationale comment present at
  1d9234b^; defined as the CORRECT contract by 07-VERIFICATION.md CR-02). The reviewer traced the
  contract to the stale pre-Phase-4 commit 4889e3a, which predates the gate. The reviewer's fix (a)
  (drop the gate) would re-leak example.html to planning agents and REOPEN the original CR-02 — do
  NOT apply it. WR-01 is mitigated (the de-blinded characterization goldens now pin the full
  assembled context_message). WR-02/WR-03/IN-01 are valid, non-blocking optional follow-ups.
  See "Orchestrator Adjudication" below for the git evidence. Net blocking findings: 0.
---

# Phase 07 (07-06 gap-closure): Code Review Report

## Orchestrator Adjudication (added by execute-phase code_review_gate — advisory, non-blocking)

**CR-01 (Critical) — REJECTED as a false positive.** The reviewer concluded the legacy
contract had *no* tool gate on the TEMPLATE EXAMPLE block by reading commit `4889e3a`
(2026-06-02, the original feature commit). That is the wrong baseline. Git evidence:

| Ref | What it is | Example-block gate |
|-----|-----------|--------------------|
| `4889e3a` | original feature (Jun 2, pre-Phase-4) — **reviewer read this** | `engine.py:1479` — no tool gate |
| `030820b` | post-0C baseline (Phase 3 cutover) | `engine.py:1697` — no tool gate |
| `218582d` | **Phase 4** — prototype per-task sub-agents | gate ADDED here (deliberate) |
| `fb55699` | Jun 8, during Ph7, pre-deletion | `engine.py:3357` — `_is_builder` gate present (snapshot DOES contain it; reviewer's IN-01 claim that the snapshot lacks the contract is itself wrong) |
| **`1d9234b^`** | **last live L12, the true pre–Phase-7 baseline INV-3 must preserve** | `engine.py:3553` — `_is_builder` gate present |

The gate was a deliberate Phase-4 decision with this documented rationale (verbatim at `1d9234b^`):
*"Inject example.html ONLY for the BUILD agent... Planning agents (prototype-specify / prototype-plan,
tools=[]) must NOT see a full working HTML doc — it nudges them to copy/continue it instead of writing
the spec / decomposing into tasks."* INV-3 requires preserving *existing* (pre–Phase-7) behavior, which
HAS the gate. `context_message` was stripped from the post-0C characterization contract, so
"parity vs post-0C" never constrained the example gate. 07-06 correctly restored the gate; the new
tests pin the correct behavior. The reviewer's own fix (b) — "reclassify as intentional, tighten the
provenance docs" — is the accurate disposition.

**WR-01 — valid but mitigated.** The dedicated `test_context_message_parity_*` checks only the
provider block map, narrower than its name. But the full assembled `context_message` IS now pinned by
the de-blinded characterization goldens (verified: the DS preamble bytes appear inline in
`golden/prototype.events.json` and `golden/od_prototype.events.json`). Coverage exists at the
characterization layer; a test rename is a worthwhile optional cleanup.

**WR-02 — valid, accepted.** Parity-stability holds under the deterministic scripted-model
characterization fixtures (executor verified twice). A guard comment is a reasonable optional follow-up.

**WR-03 — valid, minor optional hardening.** `task_num_str = str(getattr(ctx, "build_task_number", "") or "")`.
Matches the legacy pattern and `build_task_number` is typed `str`, so not a live bug; cheap robustness.

**IN-01 — valid provenance nit.** The bytes are correct, but citing `fb55699` (a config commit) is
confusing; the canonical contract is `1d9234b^` (last live L12) / the Phase-4 origin. Worth tightening
the comments. **IN-02** (END-marker `: {id}` suffix) is a pre-existing 07-04 injector property, out of
07-06 scope.

**Disposition:** 0 net blocking findings. Phase proceeds to goal verification. The four valid nits
(WR-01 rename, WR-02 guard comment, WR-03 coercion, IN-01 provenance) are optional, non-blocking
follow-ups; none affect the byte-parity correctness of the gap closure.

---

# Phase 07 (07-06 gap-closure): Code Review Report

**Reviewed:** 2026-06-09
**Depth:** standard
**Files Reviewed:** 4
**Status:** issues_found

> Scope note: this artifact has been rewritten for the FOCUSED 07-06 gap-closure
> review (diff base `2a4335a^`, the four files listed in `files_reviewed_list`).
> It is not the earlier whole-phase review.

## Summary

Focused adversarial review of the 07-06 gap-closure diff (base `2a4335a^`), which
restores three OD context-injection branches in `OpenDesignProvider` to the
pre-refactor "L12" contract under the stated INV-3 byte-parity mandate. I traced the
claimed legacy ground truth to its real home — commit `4889e3a`
(`backend/agents/execution_engine/engine.py:1445-1510`, the `_build_context_message`
od/template/example branch) — because the cited ref `fb55699` does **not** contain
the preamble string or the L12 branch (it is a config-only commit). The diff's intent
context refers to `fb55699` as ground truth; the actual byte source is `4889e3a`. I
reviewed the three gates against that real legacy implementation.

Two of the three restored gates are byte-faithful (the DS preamble bytes, the task-2+
suppression of DS/template/example, and the `prototype_emit_only` seed-only filter all
match `4889e3a` exactly). **The third — the `is_builder` gate on the TEMPLATE EXAMPLE
block — introduces NEW suppression behavior that the legacy contract did not have**,
and the new tests pin that divergence as correct. This is the one Critical finding.
Secondary findings concern an over-claiming test name and a latent characterization
fragility introduced by de-blinding `context_message`.

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: `is_builder` example gate diverges from the legacy byte contract — planning agents lose the TEMPLATE EXAMPLE block

**File:** `backend/agents/capabilities/context_providers/opendesign.py:93-104`
**Issue:**
The diff adds an `is_builder` precondition to the TEMPLATE EXAMPLE block:

```python
if (
    is_builder
    and runner is not None
    and hasattr(runner, "template_example")
):
    example_html = runner.template_example(template_id)
```

The legacy contract this diff claims to restore (`4889e3a:.../engine.py:1466-1486`)
gates the example on **only** `"template" in injects and od.get("template_body") and
not is_build_task_2_plus` — there is **no tool/builder check** on the example:

```python
if "template" in injects and od.get("template_body"):
    if not is_build_task_2_plus:
        parts.append("=== ACTIVE TEMPLATE ... ===")
        example_html = self._load_template_example(template_id)   # NO tools gate
        if example_html:
            parts.append("=== TEMPLATE EXAMPLE (example.html) ... ===")
```

Both `prototype-specify` and `prototype-plan` declare `injects: [template,
design_system]` with `tools: []` (verified at
`4889e3a:.../prompts/prototype-specify/AGENT.md` and `prototype-plan/AGENT.md`). Under
the legacy branch they therefore **received the TEMPLATE EXAMPLE block** (template_body
present, task is "" → not task 2+, no tool gate). Under the new provider,
`current_spec_tools = set()` for these agents → `is_builder == False` → the example is
**suppressed**.

This is a behavioral regression against the exact byte contract the diff exists to
preserve (INV-3 / PARITY-09). It is the same class of context-injection regression
(CR-01/02/03) this gap-closure was opened to fix — re-introduced in the opposite
direction. The new tests (`test_opendesign_example_gated_on_builder_tools`,
`test_context_message_parity_build_task_1_vs_task_2`) assert the divergent behavior as
correct, so the suite will not catch it; it locks the regression in.

Note the in-code justification ("Planning agents ... must NOT see a full working HTML
doc — it nudges them to copy/continue it") is a *product* rationale, not a parity
rationale. If suppressing the example for planning agents is a deliberate, desired
product change, it must be declared as an intentional divergence from the legacy
contract (and the characterization goldens updated to reflect it) — not shipped under
the banner of byte parity, where it silently contradicts the stated INV-3 mandate.

**Fix:** Either (a) restore parity by dropping the `is_builder` precondition so the
example follows the legacy template-inject gate:

```python
example_html = None
if runner is not None and hasattr(runner, "template_example"):
    example_html = runner.template_example(template_id)
if example_html:
    truncated = example_html[:8000]
    if len(example_html) > 8000:
        truncated = truncated + "...[truncated]"
    blocks[f"TEMPLATE EXAMPLE (example.html): {template_id}"] = truncated
```

or (b) keep the builder gate but reclassify it explicitly as an *intentional* behavior
change from `4889e3a`, document the divergence in the plan/REVIEW trail, and update the
characterization goldens + the `test_opendesign_example_gated_on_builder_tools`
docstring to state it is a new product decision rather than "L12 parity". Do not leave
it presented as byte parity.

## Warnings

### WR-01: `test_context_message_parity_build_task_1_vs_task_2` does not test the context_message — it only tests the provider block map

**File:** `backend/tests/agents/test_context_providers.py:247-294`
**Issue:**
The test name, docstring ("Dedicated context_message parity assertion ... Pins the
EXACT ordered block-key sequence AND the byte content of the composed OD block map"),
and the de-blinding comment in `_normalize.py:116-117` all present this as the
"normalizer-independent context_message parity assertion". In fact it calls
`OpenDesignProvider().load(ctx)` and asserts on the returned `{block-name -> content}`
dict only. It never invokes `_compose_context_message`, so it does **not** pin:

- the injector wrapper format (`=== {name} ===\n{content}\n=== END {name} ===`),
- the `=== END ACTIVE DESIGN SYSTEM: {ds_id} ===` END-marker (which carries the
  `: {ds_id}` suffix the legacy `=== END ACTIVE DESIGN SYSTEM ===` did not — see IN-02),
- block ordering relative to ORIGINAL USER REQUEST / CURRENT TASK / consumed outputs,
- the assembled message bytes the engine actually sends.

A regression in the injector (engine.py:2949-2951) or in block-vs-other-part ordering
would pass this test untouched, defeating the stated purpose of closing the
characterization blind spot at the message level.

**Fix:** Either rename the test to `test_opendesign_block_map_parity_build_task_1_vs_task_2`
(truthful scope) and stop claiming context_message coverage, OR add a real assertion
that drives `_compose_context_message` (or an extracted pure helper) and pins the
assembled string bytes — including the wrapper and END-marker — for a scripted build
agent on task 1 and task 2.

### WR-02: De-blinding `context_message` pins a model-derived skeleton into the golden — latent characterization flakiness

**File:** `backend/tests/agents/characterization/_normalize.py:109-117`
**Issue:**
Removing `context_message` from `_VOLATILE_STRIP_KEYS` means the golden event snapshots
now pin the full assembled `context_message`. For build tasks 2+, that message embeds
the compacted prototype skeleton injected via the task_loop strategy's CURRENT TASK
block (engine.py:2960-2978), which is derived from the model-generated `prototype.html`.
The de-blinding comment asserts this is "parity-stable once run_id/timestamps are
already stripped" — that holds **only** for the scripted-model characterization
fixtures, where HTML output is deterministic. It is not generally true: any change to
the scripted model's emitted HTML, to the compaction logic, or any attempt to feed a
non-scripted run into the goldens will now perturb `context_message` and break the
snapshot, where before it was tolerated. The newly-pinned surface is much larger and
more drift-prone than the rest of the normalized event.

**Fix:** Add an explicit guard/comment that this pin is valid ONLY under the scripted
fixtures and document the regeneration trigger; alternatively normalize the embedded
CURRENT TASK HTML skeleton sub-block to `VOLATILE_SENTINEL` (keeping the OD blocks
pinned but not the model-derived skeleton), so the snapshot pins the parity-relevant OD
injection without coupling to model HTML output.

### WR-03: `build_task_number` comparison relies on an undocumented str invariant with no defensive coercion

**File:** `backend/agents/capabilities/context_providers/opendesign.py:58-60`
**Issue:**
`task_num_str not in ("", "1")` is correct only because
`ExecutionContext.build_task_number` is typed `str` and is always set via
`str(task_number)` (context.py:137, kernel_services.py:180). If any future caller
threads a raw int (e.g. `build_task_number = task_number`), then `1 not in ("", "1")`
evaluates `True` and **task 1 would be wrongly treated as task 2+**, silently
suppressing the DS/template/example blocks on the very first build task — a quiet parity
break with no test guarding the int path. The `getattr(..., "") or ""` default does not
coerce a non-empty int to str.

**Fix:** Coerce defensively at read time so the gate is type-robust:

```python
task_num_str = str(getattr(ctx, "build_task_number", "") or "")
```

## Info

### IN-01: Cited legacy ground-truth ref `fb55699` does not contain the L12 contract

**File:** `backend/agents/capabilities/context_providers/opendesign.py:54,68,76`
(comments) and `backend/tests/agents/test_context_providers.py:115-120`
**Issue:**
Multiple comments and the test pin the bytes to "git fb55699". `fb55699` is a
config-only commit (`chore(config): disable worktree isolation ...`) and contains
neither the preamble string nor the `_build_context_message` L12 branch. The real byte
source is `4889e3a:backend/agents/execution_engine/engine.py:1445-1510`. The preamble
bytes themselves DO match that real source (verified), so this is a provenance/citation
error, not a byte error — but it makes the parity claim unverifiable for the next
reader who checks out `fb55699`.

**Fix:** Update the comments and `_DS_PREAMBLE` provenance note to cite the actual
contract commit/line (`4889e3a` `_build_context_message`), or whatever canonical ref the
team designates, so the byte-parity claim is auditable.

### IN-02: Injector END-marker carries a `: {id}` suffix the legacy END marker lacked

**File:** `backend/agents/execution_engine/engine.py:2951`
**Issue:**
The generic injector emits `=== END {block_name} ===`, so the DS block closes with
`=== END ACTIVE DESIGN SYSTEM: midnight ===` whereas the legacy contract closed with
`=== END ACTIVE DESIGN SYSTEM ===` (no id) — likewise for ACTIVE TEMPLATE / TEMPLATE
EXAMPLE. This is a pre-existing 07-04 injector property, not introduced by this diff,
and is out of strict scope; but it is a real byte divergence from the legacy contract
that the de-blinded `context_message` golden now pins, and WR-01's missing
message-level test means it is unverified against legacy. Flagged for awareness, not as
a blocker for this diff.

**Fix:** Confirm intentionality of the `: {id}` END suffix against the legacy contract
during the message-level parity test added per WR-01; adjust the injector or document
the accepted divergence.

---

_Reviewed: 2026-06-09_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
