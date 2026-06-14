# Phase 22: Capability Surfacing and User Empowerment — Universal Runtime UX Completeness - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-14
**Phase:** 22-capability-surfacing-and-user-empowerment-universal-runtime-
**Areas discussed:** Palette placement & shape, Per-step lever surface, Capability metadata source, Richer-selection persistence

> SPEC.md loaded (17 requirements locked) — discussion scoped to implementation HOW only. WHAT/WHY not re-asked.

---

## Gray-area selection

| Option | Description | Selected |
|--------|-------------|----------|
| Palette placement & shape | Where the live-registry palette lives + locked rendering (SURF-01/03, EMP-02) | ✓ |
| Per-step lever surface | How users attach per-step levers given a per-agent composer (EMP-01/04) | ✓ |
| Capability metadata source | How description + config_schema reach /api/capabilities (SURF-02) | ✓ |
| Richer-selection persistence | manifest_json reuse vs new column (EMP-03) | ✓ |

**User's choice:** All four areas selected for discussion.

---

## Palette placement & shape (SURF-01, SURF-03, EMP-02)

| Option | Description | Selected |
|--------|-------------|----------|
| Embedded in composer | ONE grouped palette panel inside AgentsPopup (reuse AgentModelPicker shell); every kind, locked rows for user_allowed=False; serves browse + attach in one surface (INV-12, reuse-first) | ✓ |
| Standalone reference + inline attach | Separate browse-only view (reuse WorkflowCatalog) + a lighter attach control; two surfaces to keep in sync | |
| Standalone reference only | Read-only browse view; defer rich inline attach (EMP-01 attach has no home) | |

**User's choice:** Embedded in composer (Recommended).
**Notes:** Single palette satisfies SURF-01 + SURF-03 + EMP-01; no separate standalone view this phase.

---

## Per-step lever surface (EMP-01, EMP-04)

| Option | Description | Selected |
|--------|-------------|----------|
| Per-agent Advanced expander | Expandable section per agent row (validator + gate + model + retry…); agent≈step; reuses relocated model-picker spot (P18); EMP-04 auto-attach inline | ✓ |
| Separate per-step inspector | Dedicated inspector panel keyed to the selected step; larger net-new surface | |
| Workflow-level lever set | Apply levers to the whole workflow, not per-step; loses per-step granularity the SPEC wants | |

**User's choice:** Per-agent Advanced expander (Recommended).
**Notes:** Treat agent ≈ step for a custom linear workflow; extend the existing per-agent composer rather than build a new inspector.

---

## Capability metadata source (SURF-02)

| Option | Description | Selected |
|--------|-------------|----------|
| Capability self-describes via registry | Optional description + config_schema on @register (or impl classattrs); surfaced by live _KNOWN enumeration; SC-001-aligned, auto-updates | ✓ |
| Static metadata map in API layer | {(kind,name): {description, schema}} dict in capabilities.py; second hardcoded source; new caps appear without metadata | |
| Hybrid | Registry for description; per-kind default schema in API; partial self-description | |

**User's choice:** Capability self-describes via registry (Recommended).
**Notes:** No second hardcoded source — preserves the SC-001 "no hardcoded list" guarantee. config_schema stays {} for no-config caps.

---

## Richer-selection persistence (EMP-03)

| Option | Description | Selected |
|--------|-------------|----------|
| Reuse dormant manifest_json column | Existing nullable JSON col on workflows; zero migration; INV-12 reuse-first (P21 precedent); compile selections trust=user at launch | ✓ |
| New additive JSON column | New capability_selections col via migration 0022 (P21-style); cleaner separation but adds a column when a dormant one fits | |

**User's choice:** Reuse dormant manifest_json column (Recommended).
**Notes:** Store a compact per-step selections map; owner-scoped, IDOR→404, re-validated trust=user at save + launch.

---

## Final gate

| Option | Description | Selected |
|--------|-------------|----------|
| Write CONTEXT.md | Lock the four decisions + dispositions (incl. WIRE-03 injects = materialize-and-consume w/ reject-loudly fallback) | ✓ |
| Adjust WIRE-03 injects | Switch to reject-loudly before writing | |
| Adjust something else | Revisit a locked area or another disposition | |

**User's choice:** Write CONTEXT.md.
**Notes:** All dispositions accepted as presented; no adjustments requested.

## Claude's Discretion

The smaller either/ors were flagged up front as Claude's to decide unless flagged; the user did not flag them, so the dispositions below were taken and recorded in CONTEXT.md:
- **WIRE-01 `model:` / WIRE-02 `retry:`** — mechanical compiler constructor pass-through.
- **WIRE-03 `injects:`** — materialize-and-consume (merge with AGENT.md injects at the factory seam); reject-loudly fallback only if INV-3 byte-identity can't be proven.
- **UXFIX-04 generic renderer** — generic mimetype-dispatch table as primary; first-party types become registered entries (no visual regression).
- **LIVE-01** — defer to milestone-end (default profile / Haiku 4.5); completion gates on offline evidence.
- **DECIDE-01/02** — record in REQUIREMENTS.md (ART-04 keep-by-default + reconcile 3 stale "confirm" labels; MODEL-05 premium-open-to-all + Haiku default/fallback); drop the AgentModelPicker tier filter.
- Sub-impl details (registry metadata mechanism, manifest_json JSON shape, config_schema representation, expander interaction) — settle in research/planning.

## Deferred Ideas

- Exhaustive per-capability compose+launch coverage (beyond representative-per-lever).
- ECS/container RuntimeEnvironment backend (designed-only).
- User-enabled exec / spawn_subagents / security gate (stays engineer-only / visible-but-locked).
- New capability kinds / registry entries.
- CTX-04 (`run_revision` retirement) — intentional VOID.
- Nyquist VALIDATION.md backfill.
- ISS-018 entitlement resolution (external IT).
- A standalone read-only "Capabilities" reference view (rejected this phase in favor of the embedded palette).
