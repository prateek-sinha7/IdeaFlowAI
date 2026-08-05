---
id: FIX-050b
type: fix
date: 2026-07-09
status: done
area: [backend, sse, agents]
files:
  - backend/agents/prompts/prototype-revision-agent/AGENT.md
summary: >-
  Prototype revision agent AGENT.md restructured for task planning, mandatory
  design.md read, and incremental execution — AGENT.md "How to work" jumped directly
  from read_file to edit_file with no analysis, no write_todos planning
source: .planning/FIX-REGISTER.md#fix-050
collision_of: FIX-050
ticket: KAN-104
invariants: [INV-1, INV-3, INV-12, SC-001]
---

# FIX-050b

> **Reused id.** The register uses `FIX-050` for more than one unrelated
> fix. This card is one of them; the suffix exists only here, so that one card
> means one fix. The register itself is unchanged — see `source:`.

**Phase / trigger:** Phase 14 (revision) / KAN-104

<!-- verbatim from the register -->

### FIX-050 — KAN-104: Prototype Revision Agent task planning and mandatory DS awareness

**Date:** 2026-07-09
**Triggered by:** `/velocity-ai-fix https://velocityai-hex.atlassian.net/browse/KAN-104`

#### Root Cause
`backend/agents/prompts/prototype-revision-agent/AGENT.md` "How to work" section instructed the agent to jump directly from `read_file` to `edit_file` with no prior analysis or planning step. The `write_todos` native tool was technically available (workspace tool set returns `exclude_builtin=False` from `WorkspaceToolProvider.provide()` at `providers.py:74`) but was never referenced in the prompt. Additionally, the `design.md` read was marked "may" (optional), causing the agent to frequently skip template/DS context and invent CSS classes or color values inconsistent with the original design.

#### Phase Context
- **Phase(s) involved:** Phase 14 — run_revision real revision loop
- **Relevant register section:** Phase 14 §5 locked decision: `od_context=None` for revision dispatch; no `template`/`design_system` injects on revision agents (pinned by `test_run_revision_revision_agents_declare_no_template_injects`)
- **Deleted code verified (not resurrected):** No deleted code involved — AGENT.md prompt-only change
- **Locked decisions respected:** YAML frontmatter `injects:` stays empty — NO `template` or `design_system` added. The design context is accessed via `read_file("design.md")` from the sandbox (seeded by `previous_run` provider), which is the correct mechanism and does not require `od_context` injection. The test constraint is fully satisfied.

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `backend/agents/prompts/prototype-revision-agent/AGENT.md` | Restructured "Your workspace" section: added `write_todos` to tool list; changed `design.md` from optional "may" to MANDATORY with explicit constraint to use only defined CSS classes/tokens; added `spec.md` usage guidance. Replaced 4-step "How to work" with a 4-phase structured process: Step 1 (mandatory context read including ls + design.md + prototype.html), Step 2 (analyze + write_todos), Step 3 (execute one task at a time with per-task verification), Step 4 (final read + summary). | The agent was skipping design context, conflating all changes into a single pass, and producing inconsistent styles. The new structure forces planning before execution and uses write_todos for dependency-ordered task tracking. |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): Not affected — AGENT.md only
- **INV-3** (golden parity): Not affected — `prototype_revision` is not in any of the 5 characterization goldens
- **INV-12** (no duplication): Not affected — no code changes
- **SC-001** (zero engine edits): Not affected — AGENT.md prompt change only
- **Test constraint**: `test_run_revision_revision_agents_declare_no_template_injects` stays green — `injects:` frontmatter is unchanged (empty list), no `template` or `design_system` inject added

#### Verification
- AGENT.md reads cleanly; YAML frontmatter is byte-identical to HEAD except for the prompt body
- `write_todos` is available to the agent via `workspace` tool set (`exclude_builtin=False`) without any backend changes
- `design.md` is read via `read_file()` from the workspace sandbox (seeded by `previous_run` provider when the parent sandbox is alive within 48h) — no injection mechanism needed
- No backend restart needed — AGENT.md is read at agent dispatch time

#### Notes
- The backend `_compute_root_ids` is intentionally NOT changed — it correctly walks `parent_run_id` ownership for all runs; the family membership decision belongs at the FE display layer (POR D7).
- Multi-hop chains (prototype → user_stories → ppt) all share the original `root_run_id = prototype.id`. After this fix, each chained run in that chain emits as its own standalone entry since each has a different base type from the prototype root.
- Same-type chaining edge case (e.g. prototype → prototype via chain, not revision): both runs have `baseWorkflowType = "prototype"` so they would still group together. This is an acceptable edge case since same-type chaining is rare and the behavior (grouping two prototypes) is not technically wrong. A future enhancement could add a `relationship_type` field to `WorkflowRun` to distinguish chain vs revision at the data layer.

| FIX-053 | 2026-07-13 | KAN-106: Add delete option on individual revision version rows in expanded family list + reset stale version timeline after deletion | Child version rows in FamilyGroupCard rendered as plain `<button>` elements with no RowMenu; `handleDeleteConfirm` never reset `family` state leaving version timeline chips stale after deletion | `frontend/src/components/history/RevisionFamilyView.tsx`, `frontend/src/components/history/WorkflowHistory.tsx` | Phase 25 (B2 revision families) / KAN-106 | INV-1/3/12/SC-001 ✅ | Done |

---
