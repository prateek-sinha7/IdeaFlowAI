# Phase 12: Wave Scheduler + Durable Resume [6] - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-11
**Phase:** 12-wave-scheduler-durable-resume-6
**Areas discussed:** None individually — all four locked to Claude's recommendations at the user's direction

---

## Area selection

Four HOW gray areas were presented (requirements already locked by 12-SPEC.md, written earlier the same session — its interview locked json_tasks / auto-resume-in-process / backend-replay-plus-FE-wave-tree):

| Option | Description | Selected |
|--------|-------------|----------|
| Wave execution & merge cadence | Per-wave merge before next wave? Wave loop home (strategy vs kernel)? CP-SAT seam shape? wave_runs lifecycle? | — |
| Restart re-entry mechanics | Dedicated resume entry vs execute() re-entry? Step-status derivation source? Double-drive guard? | — |
| Retry wrapper & hash mechanics | What is hashed as input content_hash? Step-level vs per-worker? Backoff testability? | — |
| FE tree data sourcing | Events-only vs REST+events? Lifecycle statuses vs live worker chunks? | — |

**User's choice:** "none — lock your recommendations" (the established Phase 1–11 pattern; AskUserQuestion TUI returned empty twice, choice given via plain-text list).

**Notes:** All four areas locked to the plan-grounded recommendations, recorded as D-01…D-18 in 12-CONTEXT.md:

- **A — Wave execution:** wave loop inside the strategy; one `ctx.runner.run_fanout` call per wave; per-wave merge into base before the next wave; CP-SAT seam = pure `build_waves()` function (no new capability kind); wave_runs row per wave via a best-effort handle; `user_allowed=True` matching fanout_batch.
- **B — Restart re-entry:** dedicated `resume_run` entry re-entering the SAME dispatch loop at the first incomplete step; completeness derived from artifact_refs + run_events (+ wave_runs/subagent_runs mid-wave) — no new step-status table; three-way startup classification with WR-05 kept verbatim; checkpointer reuse where thread matches, else idempotent re-run.
- **C — Retry/hash:** one engine dispatch-loop wrapper (not strategies, not per-worker); input_hash = sha256 over consumed artifacts' content_hashes + resolved task/prompt input; reuse check before every (re-)execution serving both RESUME-02 and RESUME-04; `on=["transient"]` via the 06-03 classifier; patchable backoff sleep.
- **D — FE tree:** events-only data plane (durable replay covers history; no REST tree endpoint); lifecycle statuses only (no subagent_chunk); additive sibling panel in WorkflowComposer (08-08 D-11 pattern); FE sends after_seq + dedupes by event_id; human visual verification.

## Claude's Discretion

- Wave-builder function home/signature details; event payload schemas within the locked additive families; wave_runs index choices.
- Resume entry name/shape + resume-marker mechanism (semantics fixed by D-06/D-08).
- input_hash storage spot (ArtifactRef meta vs run_events payload) — researcher confirms.
- json_tasks tolerated input shapes; whether targets defaults conflict_keys when omitted.
- FE component naming/structure within the sibling-panel pattern; whether FE work rides plan 12-03 or a new 12-04.

## Deferred Ideas

- CP-SAT wave builder (seam only) · REST subagents/waves tree endpoint · subagent_chunk live streaming · per-worker retry in run_fanout · durable queue substrate (N8) · cross-node resume locks · prototype fragment-merge (MERGE-01 v2) · € price table · FE repo-diff viewer.
