# Phase 3: Token-Trim (measured change) [0C] - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-07
**Phase:** 3-token-trim-measured-change-0c
**Areas discussed:** Skeleton block framing, Token-gate test design (2 of 4 selected; the other 2 locked to recommendation)

---

## Gray-area selection (multiSelect)

| Option | Description | Selected |
|--------|-------------|----------|
| Skeleton block framing | How the skeleton is presented once it replaces the full-HTML block | ✓ |
| Token-gate test design | How the deterministic ≥50% gate + baseline are structured | ✓ |
| Parity assertion approach | How same-pages/routes + equal-or-better validation is asserted | (locked to rec) |
| Real-run evidence | Live-gated test vs manual procedure for the SUMMARY token delta | (locked to rec) |

**User's choice:** Skeleton block framing + Token-gate test design.
**Notes:** SPEC.md already locked the major calls (≥50% floor, deterministic CI gate + real evidence, re-baseline + pages/routes assertion, read_file access) via the spec-phase interview, so only the narrower HOW forks remained. Unselected areas locked to their stated recommendation.

---

## Skeleton block framing

| Option | Description | Selected |
|--------|-------------|----------|
| Skeleton-map marker + read_file pointer | New distinct marker `=== CURRENT PROTOTYPE (skeleton — read_file for full content) ===`; honest map framing + reinforces read_file at the injection site | ✓ |
| Reuse CURRENT HTML marker | Keep the existing marker name, skeleton inside; minimal prompt-shape change but risks the agent skipping read_file | |
| You decide | Take the recommendation | |

**User's choice:** Skeleton-map marker + read_file pointer (→ D-01).
**Notes:** Grounded by the finding that `prototype-build/AGENT.md` (lines 40, 78) already mandates `read_file('prototype.html')` + "NEVER rebuild from scratch" — so SPEC Req 7 is already satisfied by the existing prompt and no AGENT.md edit is needed; the inline full-HTML block was redundant with what the agent is already told to do.

---

## Token-gate test design

| Option | Description | Selected |
|--------|-------------|----------|
| Message-level vs reconstructed full-HTML | Build a task-2 context on the prototype.html golden fixture; assert skeleton `_build_context_message` ≤ 50% of the inline-computed full-HTML message; faithful to SPEC Req 2 wording | ✓ |
| Unit-level: helper vs raw HTML | Assert `len(_extract_html_skeleton(html)) ≤ 0.5 × len(html)`; simpler proxy, doesn't go through _build_context_message | |
| You decide | Take the recommendation | |

**User's choice:** Message-level vs reconstructed full-HTML (→ D-02, D-02a).
**Notes:** Baseline is computed inline in the test (the size the old full-HTML block would have injected, capped at 120k); fixture = the prototype.html golden for realism.

---

## Locked to recommendation (not separately discussed)

- **Parity assertion approach → D-03:** Re-baseline prototype/od_prototype deliverable goldens (`SNAPSHOT_UPDATE=1`) + hold the semantic event snapshot green + add a focused `data-page`/`routes` + equal-or-better-validation assertion. Only the two prototype goldens may change.
- **Real-run evidence → D-04:** Opt-in live-gated test (pattern of `test_deep_agent_runner_hitl_live.py`) logging input-token totals → copied into SUMMARY as COMPACT-03 evidence (not a CI gate). Manual-run fallback if no live model available.

## Claude's Discretion

- Exact skeleton marker wording/casing (must be distinct + carry a read_file pointer).
- Test file placement (new `test_phase3_*.py` vs extend a characterization module).
- Empty/error task-1 HTML edge case → keep today's guard (emit no skeleton block).
- Leave `_extract_html_skeleton` extraction logic as-is unless the parity assertion surfaces a gap.
- Keep the `=== TEMPLATE COMPLIANCE ===` reminder for task-2+.
- Plan-task granularity (03-01 wire+measure / 03-02 re-baseline+parity, or resplit).

## Deferred Ideas

- `html_skeleton` as a registered `CompactionStrategy` — Phase 7 / PARITY-04 (re-express 0C behind the capability + delete the inline helper, L13 grep → 0).
- `_current_task_block` → `TaskLoopStrategy` — Phase 7 (carried from 02-CONTEXT D-02).
- Compaction for non-build agents / additional tiers (Tier#2+) — new capability work, not this milestone's 0C.
