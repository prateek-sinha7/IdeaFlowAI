# Specification Quality Checklist: Conditional Gates — branching, looping, and cross-workflow triggering

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-08-20
**Feature**: [spec.md](../spec.md)

**Note on convention**: this repo's specs (see `013-reusable-custom-agents/spec.md`) are
implementation-grounded by design — they cite real file paths, line numbers, and code shapes
as verified evidence, not speculative design. The standard speckit "no implementation details"
criterion is adapted accordingly below: the bar is *grounded in verified fact*, not *free of
code references*.

## Content Quality

- [x] Implementation references are grounded, not speculative — every code path/line cited
      traces to `reports/conditional-gates.md`'s verified impact analysis, consistent with this
      repo's spec convention (013 precedent)
- [x] Focused on user value and business needs — §1/§2 frame the problem and behavior before
      any implementation detail
- [x] Written to be followable by a planner without re-reading the full brainstorming
      conversation — §8 decision log captures every resolved open item inline
- [x] All mandatory sections completed (Problem, What it does, Verified mechanics,
      Requirements, Out of scope, Acceptance criteria, Risks, Decision log)

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain — the one live ambiguity (dead `route:` config
      without `conditional` in `gates:`) was resolved via AskUserQuestion before this spec was
      written; resolution recorded as decision log #10 / R-03
- [x] Requirements are testable and unambiguous — each R-## maps to at least one AC-##
- [x] Success criteria (Acceptance Criteria, §6) are measurable — each AC states an observable
      compiled/runtime/UI outcome
- [x] Acceptance scenarios cover both v1-in-scope mechanics (branch, loop, divert) and the two
      compile-time rejection cases (AC-02, AC-06)
- [x] Edge cases identified: unresolvable route target (R-10), loop-cap breach (R-07/AC-03),
      trigger-depth breach (R-18/AC-06), dead route config (R-03/AC-02)
- [x] Scope is clearly bounded — §5 lists 7 explicitly deferred capabilities with the reason
      each was deferred, sourced directly from the brainstorming conversation
- [x] Dependencies and assumptions identified — §3 "Verified mechanics" states what already
      exists and is reused unmodified (parent_run_id, fanout precedent, gates: list shape)

## Feature Readiness

- [x] All functional requirements (R-01 through R-27) have a corresponding acceptance
      criterion or are covered by an existing AC
- [x] User/author scenarios cover the primary flows discussed: in-workflow branch, in-workflow
      loop, cross-workflow divert, canvas authoring of all three
- [x] Feature scope matches what was actually approved across the conversation — cross-checked
      against the resolution table and the two later concrete-example threads (C→D,E/C→X,Y,Z
      and the two-separate-workflows case)
- [x] No speculative implementation detail leaks in beyond what §3 verified and what the
      Decision Log resolved — the data model in §4.1 is presented as a requirement (what the
      shape must be), not as pre-written production code

## Notes

- This spec deliberately carries more implementation grounding than the generic speckit
  template calls for, matching this repository's own established convention. All such detail
  traces to either `reports/conditional-gates.md` (verified against live code) or an explicit
  decision recorded in §8.
- §6c's four gaps (found while building the reference fixtures, §6b) were all resolved during
  a follow-up review pass: GAP-01 and GAP-03 became new requirements R-26/R-27 (with AC-09/
  AC-10); GAP-02 and GAP-04 were verified NOT to be real gaps. Decision log rows 14–16 record
  the reasoning. §6c itself is left in place as a record, now marked RESOLVED throughout.
- All items pass. No outstanding items block `/speckit-plan`.
