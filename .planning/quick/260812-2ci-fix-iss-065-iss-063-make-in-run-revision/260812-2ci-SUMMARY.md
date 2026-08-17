---
quick_id: 260812-2ci
description: fix ISS-065 + ISS-063 — make in-run revisions visible
status: complete
date: 2026-08-12
commits: [6e9baff5, 2ab7c56b]
fixes: [FIX-221, FIX-222]
tests: [TEST-007]
closes: [ISS-063, ISS-065]
files: [ISS-075, ISS-076, ISS-077]
---

# Summary — ISS-063 + ISS-065 fixed as one change

Both rows are the same complaint: **a revision happened and the screen does not say so.**
They were deliberately not sequenced — ISS-063's own investigation identified sequencing
them as the path to a *third* dead counter in this family.

## The design decision: where "which revision cycle is this" comes from

Two live candidates:

- **(A)** derive from the event stream, inside the `setPipelineState` updater;
- **(B)** consume FIX-220's `revision_cycle` / `revision_in_flight` (commit `1b786e30`),
  additive on `review_gate_ready.data` and already threaded to the gate card.

**Chosen: (A).** Decided on measurement, from `backend/dev.db`, run `d5dbc9f2`:

| seq | time | event |
|---|---|---|
| 9283 | 20:54:20 | `review_gate_ready` (analyze) — cycle 0 |
| **9285** | **20:54:51** | `agent_start` prototype-specify — **revision cycle 1 begins** |
| **13353** | **20:56:25** | first `review_gate_ready` after the revision started |

1. **Coverage.** B rides only on gate events. There is a **94-second window** between the
   revision starting and the first gate frame that could carry a non-zero cycle. That
   window is the banner's entire job. A lights at seq 9285.
2. **Lifetime.** B's pair lives on `ReviewGateData` — per-firing, replaced by the next
   gate. The banner must persist for the rest of the run.
3. **Replay identity.** A is a pure function of accumulated frames: order-independent,
   idempotent under the event dedup, identical live / on the synchronous REST replay loop /
   on a reconnect that replays from seq 0. B depends on which gate frame was seen last.
4. **Not a duplicate.** FIX-220 is untouched and keeps its own, different job — telling
   apart three gate firings that share a `gate_key` *and* their output bytes. Two facts,
   two surfaces. **`specRevisionCount` has exactly one writer** (`useRunStateStore.handleFrame`).

## What was deleted (INV-12 exit gate)

`revisionCycleArmedRef` · `setSpecRevisionCountRef` · `pipelineAgentsRef` · the
`specRevisionCount` `useState` · the arm `useEffect` · the detector block — all from
`page.tsx`. A source-lock spec fails if any reappears. The value now lands in the
`specRevisionCount` field that had existed **dead** (declared, initialised, never written,
never read) at `useRunStateStore.ts:81/170`.

## Evidence

- **RED before / GREEN after**, one run each: `4 files failed · 18 failed | 1 passed (19)`
  → `4 files passed · 27 passed (27)`. (19→27 because `ArtifactVersionPicker.test.tsx`
  could not load before; the one green-at-red case is the no-regression guard.)
- **Full vitest, compared by failing ID:** 928→955 tests, 781→808 passed,
  **147 failed both sides, byte-identical failing-ID set — 0 new reds.**
- **Mocked Playwright, compared by failing ID** against a properly isolated baseline at
  `b13d5c33` (own server on `:3100`): 33 failed → 31 failed, after-set a strict **subset**,
  **0 new failures**.
- **Goldens 5 failed / 5 passed** and **lint-imports 3 kept / 1 broken** — identical to
  `b13d5c33`, re-measured after. No golden regenerated; zero backend files touched.
- `tsc --noEmit`: 2 errors, both pre-existing in files never opened here.
- Retired palette (`#1B2A4A` / `#2563eb` / `#f5f5f0`): 0 hits in changed files.

## Filed, not fixed

- **ISS-075** (major) — the trailing resume `pipeline_start` carries `resume_offset = 0`,
  so reopening a run should repaint the whole Steps trace as idle. Confirmed in code and
  data, **not observed on screen**; arguably more serious than the banner defect.
- **ISS-076** (major) — the mocked Playwright baseline on this branch is **33 red**, not the
  "132 green" the records claim. Includes the `reuseExistingServer: true` trap that nearly
  produced a false "pre-existing" verdict here.
- **ISS-077** (minor) — `ArtifactNode` declares `derived_from` / `children` / `task_id`
  wrongly; latent, nothing reads them today.

## Not done

- No new Playwright case and no `/artifacts` mock handler. The picker correctly renders
  nothing under the existing fixture, and the protected suite was verified unharmed instead.
- Live Bedrock acceptance deferred (end-of-milestone rule). The browser check is: reopen
  `d5dbc9f2`, expect "Spec Revision Cycle 2" on the Steps spine and a `spec · v3 of 3`
  picker in the Spec Writer detail.
