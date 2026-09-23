# Specification Quality Checklist: A Playwright tool set agents can be granted

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-08-27
**Feature**: [spec.md](../spec.md)

## Content Quality

- [~] No implementation details (languages, frameworks, APIs) — **deliberate deviation**, see Notes
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders — *see Notes; audience here is the engineer*
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [~] Success criteria are technology-agnostic — **deliberate deviation**, see Notes
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [~] No implementation details leak into specification — **deliberate deviation**, see Notes

## Notes

**The two "deviations" are the house standard, not defects.** Every spec in `specs/` is an
engineering spec written for the engineer who will build it — 017 names `verify_layout.py`,
`_PPT_CODE_AGENT_IDS` and `ctx.last_streamed` in its own functional requirements. Rewriting 018 to
be technology-agnostic would strip out precisely the content that makes it actionable:

- **FR-003** is only meaningful as a file-level claim. "Granting the set must not remove an agent's
  filesystem tools" is abstract; the trap is a specific AND-accumulator in `_resolve_runner_tools`,
  and an implementer who does not know that will walk into it.
- **FR-008** exists *because* of a named prior defect (FIX-307). "Manage the browser lifecycle
  carefully" would not have prevented it. "Do not use `async with async_playwright()`" does.
- **SC-002** cites the characterization snapshots because they are the actual oracle.

Applying the generic rule here would produce a spec that passes this checklist and fails the build.
Recorded as a conscious deviation rather than silently ticked.

**Three clarifications were resolved with the user before writing** (URL policy, `playwright_evaluate`
inclusion, initial grant list) and are recorded in the spec's Clarifications section, so no
[NEEDS CLARIFICATION] markers were carried into the draft.

**One open item for `/speckit-plan`, not a spec gap:** FR-009 requires session release on every run
exit path. The exit paths were not enumerated during specification — `create_runner` builds the
sandbox but no teardown hook was identified in the reading done so far. Locating that hook (or
establishing that one must be added) is planning work, and the requirement is written to be
verifiable either way.
