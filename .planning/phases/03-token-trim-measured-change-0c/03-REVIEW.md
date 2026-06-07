---
phase: 03-token-trim-measured-change-0c
reviewed: 2026-06-07T00:00:00Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - backend/agents/execution_engine/engine.py
  - backend/tests/agents/test_phase3_compaction.py
  - backend/tests/agents/test_phase3_parity.py
  - backend/tests/agents/test_phase3_token_delta_live.py
findings:
  critical: 0
  warning: 5
  info: 3
  total: 8
status: issues_found
---

# Phase 3: Code Review Report

**Reviewed:** 2026-06-07
**Depth:** standard
**Files Reviewed:** 4
**Status:** issues_found

## Summary

The phase's single production change is the `is_build_task_2_plus` skeleton branch
in `ExecutionEngine._build_context_message` (`engine.py:2526-2552`), which swaps the
full `--- CURRENT HTML … ---` block (up to 120k chars) for the compact
`_extract_html_skeleton(current_html)` state-map behind a distinct `=== CURRENT
PROTOTYPE (skeleton …) ===` marker that points the sub-agent at
`read_file('prototype.html')`. The diff is +25/-9 lines and the branch wiring is
correct: the task-1 vs task-2+ split, the `[Error:`/empty guard, the marker
strings, and the upstream `_build_task_number` plumbing all line up with the tests.

No BLOCKERs were found in the production change. The branch itself is sound. The
findings below are: (1) one real correctness bug in the **opt-in live test** (a
monkeypatch signature mismatch that will raise `TypeError` the moment anyone runs
it live), (2) several robustness gaps in `_extract_html_skeleton` that are
pre-existing but newly load-bearing now that the skeleton is the agent's only view
of prior HTML, and (3) a test-vacuity concern where the offline parity test cannot
actually detect the failure mode it claims to guard. Plus dead code and minor
cleanliness items.

## Warnings

### WR-01: Live token-delta test will crash with TypeError on the compaction-OFF path

**File:** `backend/tests/agents/test_phase3_token_delta_live.py:169-191`
**Issue:** The monkeypatch replacement `_full_html_build_ctx` is declared with
**keyword-only** parameters (`def _full_html_build_ctx(*, spec, ordered_agents,
…)`) and is assigned as an instance attribute
(`engine._build_context_message = _full_html_build_ctx`). But the production caller
invokes it **positionally**:

```python
# engine.py:1174-1176
context_message = self._build_context_message(
    spec, ordered_agents, user_message, accumulated_outputs,
    planning_context, ectx,
)
```

Because the override is an instance attribute (a plain function, no `self`
binding), `self._build_context_message(spec, ordered_agents, …)` passes 6
positional args to a function that accepts **zero** positional args →
`TypeError: _full_html_build_ctx() takes 0 positional arguments but 6 were given`.
The compaction-OFF baseline run (`_drive_live(compaction_on=False)`) is the FIRST
call in `test_token_delta_live` (line 256), so the test fails before producing any
evidence. This is the entire point of the test — recording the pre-vs-post token
delta — and it cannot run. It is opt-in / non-CI so it is not a release blocker,
but the evidence test is broken.
**Fix:** Make the replacement accept positional args to mirror the real signature:
```python
def _full_html_build_ctx(spec, ordered_agents, user_message,
                         accumulated_outputs, planning_context, ectx):
    msg = _orig_build_ctx(
        spec, ordered_agents, user_message,
        accumulated_outputs, planning_context, ectx,
    )
    ...
```
(Note `_orig_build_ctx` is the *bound* method, so calling it positionally is fine;
the wrapper must just accept the same positional shape the engine uses.)

### WR-02: `_extract_html_skeleton` silently drops the final page when HTML has no closing `</body>`

**File:** `backend/agents/execution_engine/engine.py:2667-2670`
**Issue:** The section scan uses a non-greedy body match with a required lookahead
terminator:
```python
sections = _re.findall(
    r'<section[^>]+data-page=["\']([^"\']+)["\'][^>]*>([\s\S]*?)(?=<section|</body>)',
    html, _re.IGNORECASE
)
```
`[\s\S]*?` is non-greedy and the match only succeeds if it can reach a `<section`
or `</body>` terminator. If the current prototype HTML is malformed or truncated
(no `</body>` after the last `<section>`, e.g. the 120k truncation cap chopped the
tail, or an LLM emitted a fragment), the **last** `data-page` section produces no
match and is omitted from the "Pages already built / still empty" lines. The agent
then believes a page that already exists is missing and may rebuild or skip it.
This regex pre-dates the phase, but the change makes the skeleton the agent's ONLY
structural view of prior work on tasks 2+, so the failure mode is now
behavior-affecting rather than cosmetic.
**Fix:** Add an end-of-string alternative to the lookahead so the final section is
always captured:
```python
r'<section[^>]+data-page=["\']([^"\']+)["\'][^>]*>([\s\S]*?)(?=<section|</body>|\Z)'
```

### WR-03: Skeleton routes/`:root` extraction breaks on nested braces

**File:** `backend/agents/execution_engine/engine.py:2648, 2661`
**Issue:** Both the `:root` token extraction (`r":root\s*\{([^}]+)\}"`) and the
routes extraction (`r"const routes\s*=\s*\{([^}]+)\}"`) use `[^}]+`, which stops at
the FIRST `}`. A real prototype `:root` block is unlikely to nest braces, but a
`const routes` map frequently contains nested objects or methods
(e.g. `routes = { home: { path: "#home" }, … }`), in which case `[^}]+` captures
only up to the first inner `}` and the "Routes map" skeleton line is truncated to a
malformed fragment. The agent is then shown an incomplete/invalid route map. The
scripted golden and the test fixture both use flat single-level routes, so the
offline tests never exercise this — it only surfaces against real agent output.
**Fix:** Use a balanced-ish capture or cap by scanning to a matching brace. A
pragmatic improvement: capture greedily to the last `}` on the statement or accept
nested one level, e.g. `r"const routes\s*=\s*(\{[\s\S]*?\});"` anchored on the
trailing `;`, or document that only flat route maps are summarized and fall back to
listing route keys rather than the raw block.

### WR-04: Offline parity test cannot detect the failure mode it claims to guard (weak ratchet)

**File:** `backend/tests/agents/test_phase3_parity.py:118-172`
**Issue:** `test_prototype_pages_routes_parity` / `test_od_prototype_pages_routes_parity`
drive the pipeline with the **scripted** model, which writes a FIXED single-section
HTML regardless of the prompt (`_scripted_model.py:269-281`). The deliverable is
therefore identical whether or not the skeleton-compaction change exists — the
scripted agent never reads the skeleton, never edits based on it, and never
produces a multi-page document. The test's own docstring concedes the fixed-output
nature but still claims "a dropped/renamed section would diverge … the ratchet is
real, not vacuous." In practice the assertion `produced_pages == {"dashboard"}`
holds for ANY engine change to `_build_context_message`, including a bug that
corrupts the skeleton, because the scripted output is independent of the injected
context. The semantic risk introduced by this phase — that summarizing prior HTML
into a skeleton causes a REAL agent to drop/rename a section — is exercised only by
the SSO-gated live test (which is itself broken, WR-01). The offline suite thus
provides no real coverage of the change's semantic hazard.
**Fix:** Either (a) drive a scripted model whose task-2 output is *derived from the
injected skeleton* (so a corrupted skeleton produces a divergent deliverable), or
(b) unit-test `_extract_html_skeleton` directly against a multi-section fixture and
assert every `data-page` ID appears in the "Pages already built/empty" lines
(this would also have caught WR-02). At minimum, downgrade the docstring's
"ratchet is real" claim to reflect that the scripted run only proves
no-crash + output-preservation, not skeleton fidelity.

### WR-05: Skeleton's `read_file('prototype.html')` pointer is not enforced — silent dependency on agent compliance

**File:** `backend/agents/execution_engine/engine.py:2536-2543`
**Issue:** On tasks 2+ the agent is given only the skeleton plus an instruction to
`read_file('prototype.html')` before editing. Correctness of the whole compaction
hinges on the agent actually issuing that read. If a future prompt change, model
swap, or tool-set regression causes the agent to edit without reading (or to call
`write_file` instead of `edit_file`, which the deepagents backend refuses for an
existing file per backend/CLAUDE.md), the agent operates on a 1-3k char summary as
if it were the full document and can clobber or duplicate content. There is no
engine-side guard (e.g. verifying a `read_file` occurred, or that the post-task
HTML still contains the previously-built sections) before accepting the task
output back from disk at `engine.py:1592-1594`. The phase relies entirely on the
AGENT.md mandate. `test_build_task2_preserves_read_file_access` only asserts the
*tool is available* and the *pointer string is present* — not that it is used.
**Fix:** Out of scope to fully solve here, but consider a cheap post-task
invariant: after reading `prototype.html` back, assert the set of `data-page` IDs
did not shrink versus the prior task's skeleton, and log/flag a regression if it
did (the existing Both-validation fix-loop is the natural place). Track as
follow-up if deferred.

## Info

### IN-01: Dead helper `_fullhtml_baseline_len` is defined but never called

**File:** `backend/tests/agents/test_phase3_compaction.py:146-167`
**Issue:** `_fullhtml_baseline_len(task_message_prefix)` is never referenced
anywhere in the file (the 50%-gate test reconstructs the full-HTML baseline inline
at lines 193-207). It is dead code carrying a misleading docstring about how the
baseline is computed. Its parameter `task_message_prefix` is also unused inside the
body.
**Fix:** Delete the function, or wire the inline baseline reconstruction through it
to remove the duplication between this helper and lines 201-206.

### IN-02: Full-HTML baseline block is duplicated across three sites

**File:** `backend/tests/agents/test_phase3_compaction.py:161-167, 201-206`; `backend/tests/agents/test_phase3_token_delta_live.py:107-115`; `backend/agents/execution_engine/engine.py:2547-2552`
**Issue:** The exact `--- CURRENT HTML (modify this — do NOT rebuild from scratch)
---` / `...[truncated at 120k]` / `--- END CURRENT HTML ---` block (and the 120000
cap) is hand-copied in four places. If the production marker text or cap ever
changes, three tests silently keep asserting against stale strings and pass
vacuously (the markers wouldn't match but the negative assertions
`"--- CURRENT HTML (modify this" not in compacted` would still hold). The
skeleton-block string is likewise duplicated between the test and the engine.
**Fix:** Extract the full-HTML block and skeleton-block builders as importable
module-level helpers in `engine.py` and reuse them from the tests, so the tests
ratchet against the real strings rather than copies.

### IN-03: `current_task_block` / `_build_task_number` are mutated on shared dicts/state objects

**File:** `backend/agents/execution_engine/engine.py:1559-1566, 2515`
**Issue:** The build loop stores per-task scope by mutating the shared
`accumulated_outputs` dict (`_build_task_number`, `_build_task_total`) and the
shared `ectx.current_task_block`. These are read back in `_build_context_message`.
The `_filter_consumed_outputs` helper guards against the `_`-prefixed marker keys
(`engine.py:2342`), so they don't leak into consumed outputs — good — but storing
control state as magic string keys inside the data dict is fragile (any future
consumer that iterates `accumulated_outputs` without the `_`-prefix skip will pick
them up). Pre-existing, not introduced by this phase, but the skeleton branch now
also keys off `_build_task_number`, increasing the blast radius.
**Fix:** Track build-task number/total/block as typed fields on `ExecutionContext`
(alongside `current_task_block`) rather than as string keys in `accumulated_outputs`.
Defer if out of phase scope.

---

_Reviewed: 2026-06-07_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
