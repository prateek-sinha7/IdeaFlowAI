---
id: 260812-1nz
title: fix ISS-052 — disambiguate the doubled analyze gate
status: complete
date: 2026-08-12
fix_id: FIX-220
test_id: TEST-006
issues_closed: [ISS-052 (disambiguation half only)]
issues_filed: [ISS-072, ISS-073, ISS-074]
code_commit: 1b786e30
baseline_sha: 28c0111c
---

# Quick 260812-1nz — SUMMARY

## Outcome

`review_gate_ready` now carries a **per-FIRING** discriminator, so the analyze gate opened
inside a spec-revision pass and the one re-opened after it returns are no longer identical
on the wire or on screen. **No gate was suppressed** — that half is ISS-072.

## The discriminator (what ISS-063 should consume)

```
review_gate_ready.data.revision_cycle      : int   # which cycle, 0 = none has run
review_gate_ready.data.revision_in_flight  : bool  # is the pass still on the stack
```

| firing | | `revision_cycle` | `revision_in_flight` | `update_specs_eligible` |
|---|---|---|---|---|
| `[0]` | outer first-pass gate | `0` | `False` | `True` |
| `[1]` | analyze re-run INSIDE the pass | `1` | `True` | `False` |
| `[2]` | gate re-opened after the pass | `1` | `False` | `True` |

The **pair** is the identifier. `revision_cycle` alone cannot separate `[1]` from `[2]`
(both cycle 1); `revision_in_flight` alone cannot separate `[0]` from `[2]`.

Frontend names: `revisionCycle` / `revisionInFlight`, carried on `ReviewGateReadyData` →
`gateData` (`dashboard/page.tsx`) → `ReviewGateData` (`useRunStateStore`) → `GateContext`
(`RunChatLane.tsx`) → `StepsOverviewSpine` → `InlineGateActions`.

`revision_cycle` is durable: it rides `run_events`, and the SSE attach path re-emits
`payload_json` verbatim (`run_stream.py:244`), so it survives a reconnect and a reopen.
**ISS-063 must read this rather than invent a third counter** — `dashboard/page.tsx:357`
currently holds `specRevisionCount` in `useState(0)`, incremented only from a live FE-armed
inference and never back-filled.

Deliberately **not** named `revision_index` / `spec_revision_attempt`:
`chat_narrator._revision_index` (`:106-118`) reads those two, and reusing either would have
silently turned every in-revision gate card into a "Revising spec — cycle N" card. Verified
by reading the narrator, not assumed.

## Files

**Backend** — `agents/execution_engine/engine.py`: `_run_review_gate` +2 params, stamped on
the event; new resolver `_revision_stamp(ectx) -> (int, bool)` (`:6692`) called at the three
inline gate sites (`:3363`, `:3487`, `:4385`). `tests/agents/characterization/_normalize.py`:
both keys into `_VOLATILE_STRIP_KEYS`.

**Frontend** — `types/index.ts`, `app/dashboard/page.tsx`, `hooks/useRunStateStore.ts`,
`components/layout/DashboardLayout.tsx` (map + the approve-label correction),
`components/chat/RunChatLane.tsx` (`GateContext`), `components/results/StepsOverviewSpine.tsx`
(pass-through), `components/chat/InlineGateActions.tsx` (props, the reset-effect dependency
array, and a `chat-gate-revision` badge).

**Tests** — `backend/tests/agents/test_gate_revision_discriminator.py` (new, 6);
`frontend/src/components/chat/InlineGateActions.test.tsx` (+2);
`backend/tests/agents/test_spec_revision_cycles.py` (harness records the two fields);
`backend/tests/agents/test_restart_resume.py` (`**kwargs` on three stubs).

## Fail-before / pass-after

Backend `test_gate_revision_discriminator.py`: **6 failed → 6 passed**. Each failed for its
own reason, not one shared import error — stamp vector `[(None,None)×3]`; cycle vector
`[None×5]`; `TypeError: unexpected keyword argument 'revision_cycle'`; "expected a 0 default;
got None"; "the discriminator never appears in engine.py"; `'revision_cycle' not in
_VOLATILE_STRIP_KEYS`.

Frontend `InlineGateActions.test.tsx`: **1 failed / 13 passed → 1 failed / 15 passed**. The
1 red is pre-existing and *proven* so — the same file measured 1 failed / 13 passed in a
detached worktree at `28c0111c` (filed as ISS-073). The load-bearing new case fails on the
pre-fix dependency array: approve at `[1]`, re-render with the same `output` and `gateKey`
and only the stamp moved, and the approve control must be live again.

## Baselines, all against `28c0111c`

| gate | baseline | after |
|---|---|---|
| goldens | 5 failed / 5 passed (same 5 ids) | **identical**, `golden/` git-clean, none regenerated |
| lint-imports (from `backend/`) | 3 kept / 1 broken | **identical** |
| ISS-053 set + `test_sc001_gate_flag` | 32 passed | **32 passed** |
| engine-adjacent (5 files) | 10 failed / 76 passed | **identical ids** |
| wider gate surface (11 files) | 8 failed / 92 passed | **identical ids** |
| full frontend vitest | 147 failed / 779 passed | 147 failed / **781** passed (+2 = the new cases) |
| `tsc --noEmit` | 2 pre-existing errors | **identical** |

INV-3 could **not** be argued from the goldens: all 10 golden files contain **zero**
`review_gate_ready` events (`gate_agent_ids=[]`, `_scripted_model.py:649`), so they are
structurally blind to any `_run_review_gate` change. Proven at test level instead.

## Mid-work regression, caught and closed

The first engine-adjacent sweep read **17 failed / 69 passed** (+7 vs baseline). Three
`_gate` stubs in `test_restart_resume.py` (`:1282/:1360/:1407`) have FIXED signatures and
raised `TypeError: unexpected keyword argument 'revision_cycle'`. Given `**kwargs` — the
idiom the sibling stubs in `test_spec_revision_cycles.py` and `test_redo_gate_safety.py`
already document — the sweep returned to the baseline 10 / 76. Test-only, no production diff.
This is the third time this stub family has rotted (FIX-218 repaired four, FIX-220 three);
a signature-drift guard would end it.

## Filed, not fixed

- **ISS-072** — suppress the IN-PASS firing `[1]` (the collapse half of ISS-052). Fix shape,
  cost and the four reasons it needs its own brief are on the row.
- **ISS-073** — a stale FE test asserting a layout the component abandoned; proven
  pre-existing at `28c0111c`.
- **ISS-074** — `live_harness.py:672`'s gate wrapper takes 4 positional params and cannot
  absorb the gate's own kwargs; broken since REDO-GATE, unverifiable offline.
- **Residual on ISS-052** — the chat-lane milestone card still reads "Paused — needs
  approval" for both firings (`chat_narrator.py:171-173`). The data to disambiguate it now
  rides the event, so it is a pure render follow-up.

Live Bedrock acceptance DEFERRED per the end-of-milestone rule. The check is one query: the
run's `review_gate_ready` rows must read `(0,f)/(N,t)/(N,f)`.
