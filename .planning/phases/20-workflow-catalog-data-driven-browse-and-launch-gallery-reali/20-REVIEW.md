---
phase: 20-workflow-catalog-data-driven-browse-and-launch-gallery-reali
reviewed: 2026-06-14T00:00:00Z
depth: deep
files_reviewed: 18
files_reviewed_list:
  - backend/agents/workflows/manifest.py
  - backend/app/api/workflows.py
  - backend/agents/workflows/app_builder/workflow.yaml
  - backend/agents/workflows/custom/workflow.yaml
  - backend/agents/workflows/dotnet_to_azure/workflow.yaml
  - backend/agents/workflows/mulesoft_to_springboot/workflow.yaml
  - backend/agents/workflows/ppt/workflow.yaml
  - backend/agents/workflows/prototype/workflow.yaml
  - backend/agents/workflows/user_stories/workflow.yaml
  - backend/tests/agents/test_manifest.py
  - backend/tests/unit/test_workflows_api.py
  - frontend/src/lib/api.ts
  - frontend/src/components/catalog/WorkflowCatalog.tsx
  - frontend/src/components/catalog/WorkflowCatalog.test.tsx
  - frontend/src/components/layout/DashboardLayout.tsx
  - frontend/src/components/layout/AppHeader.tsx
  - frontend/e2e/tests/ts-z.catalog.spec.ts
findings:
  critical: 0
  warning: 2
  info: 3
  total: 5
status: issues_found
---

# Phase 20: Code Review Report

**Reviewed:** 2026-06-14
**Depth:** deep
**Files Reviewed:** 18
**Status:** issues_found

## Summary

Phase 20 is a clean, well-scoped additive change: five inert catalog fields on the
manifest schema, surfaced through the existing authenticated `GET /api/workflows`,
consumed by a new data-driven `WorkflowCatalog` that reuses the CreationHub row JSX +
AgentModelPicker fetch shell + entitlements gating.

The load-bearing invariants hold:

- **SC-001 — no hardcoded launchability list.** Both gates are data-driven: gate 1
  (`user_launchable`) is a declared manifest flag enumerated generically over
  `PIPELINE_AGENTS` (`workflows.py:187,229`; `WorkflowCatalog.tsx:69`), gate 2 is the
  pre-existing `canRunPipeline` tier check. The CreationHub `WORKFLOWS` module-const is
  genuinely absent from the catalog. A new manifest flipping `user_launchable: true`
  joins with zero FE/BE edit.
- **INV-3 parity.** The 5 new fields are read only by the read endpoint, never by the
  compiler/kernel; defaults are `False`/`None`, so the golden manifests parse unchanged.
- **INV-5.** `_ALLOWED_TOP_KEYS` widened only with presentation/visibility keys;
  `when/if/for/expr` stay rejected (`test_manifest.py:175-185` preserved).
- **Additive-only.** No new table, no migration; the endpoint is DB-free.
- **Security.** The flag rides the existing JWT-gated read endpoint; it does NOT
  authorize a run — launch still crosses the server-side `can_run_pipeline` gate. No new
  trust boundary, no `dangerouslySetInnerHTML`, `safe_load` only. No real exposure found.
- `_optional_bool` correctly rejects `user_launchable: 1` (the int-subclass trap is
  inverted vs `_optional_int`), proven by `test_manifest.py:143-154`. The `od_*` /
  `*_revision` / `reverse_engineer` / `chat` ids degrade to `user_launchable=False` (no
  flag in their YAML; `od_ppt`'s manifest load succeeds but carries no flag), so gate 1
  excludes them without any name-based filter.

Two warnings concern reuse fidelity / test coverage of the friendly-label path; the rest
are minor code-quality notes. No Critical issues.

## Warnings

### WR-01: Friendly-label fallback is dead against the real endpoint — catalog renders the title-cased raw id, the exact string the SPEC said not to show

**File:** `frontend/src/components/catalog/WorkflowCatalog.tsx:157` (with `backend/app/api/workflows.py:230-233`)

**Issue:** The catalog computes its label as `row.display_name ?? getWorkflowLabel(row.id)`.
The intent (SPEC §3.1 / §4) is that the friendly `WORKFLOW_LABELS` value is shown — e.g.
`mulesoft_to_springboot` → "Mulesoft Migration", `custom` → "Custom Workflow" — and that
the raw title-cased id ("Mulesoft To Springboot") is **never** rendered. But the backend
populates `display_name` with a guaranteed-truthy value:

```python
display_name=(
    (manifest.display_name if manifest else None)
    or _display_name(workflow_id)   # always returns e.g. "Mulesoft To Springboot"
),
```

None of the 7 launchable YAMLs declare `display_name`, so the response `display_name` is
always the title-cased raw id. Because it is never null/undefined, the FE `??` fallback to
`getWorkflowLabel` is unreachable in production. The catalog therefore renders
"Mulesoft To Springboot" / ".Net To Azure" / "Custom" — precisely the title-cased
`_display_name` the SPEC §3.1 said to avoid ("Do NOT render the raw API `name` — it is
just `_display_name` title-cased"). The friendly labels in `WORKFLOW_LABELS`
("Mulesoft Migration", ".NET Migration", "Custom Workflow") are dead for these rows.

This passes both test suites only because their fixtures set `display_name: null` for the
fallback row (`WorkflowCatalog.test.tsx:120`) and a hand-authored `display_name` for the
others — a payload shape the real endpoint never produces (real `display_name` is always
truthy). So the friendly-label contract is untested against the real backend output.

**Fix:** Decide which surface owns the friendly label and make the other inert. Either:
- (preferred, keeps SPEC intent) have the BE leave `display_name` as `None` when the
  manifest does not declare one, so the FE fallback to `getWorkflowLabel(id)` actually
  fires:
  ```python
  display_name=(manifest.display_name if manifest else None),  # may be None → FE falls back
  ```
  (and keep `name=_display_name(...)` for back-compat consumers); **or**
- author `display_name:` in each launchable `workflow.yaml` with the desired friendly
  string, and update the vitest fixture so at least one launchable row has a real
  (non-null) `display_name` mismatching `getWorkflowLabel(id)` to lock the precedence.

### WR-02: Neither test exercises a `display_name`-present row, so the label-precedence (`display_name` over `getWorkflowLabel`) is unverified

**File:** `frontend/src/components/catalog/WorkflowCatalog.test.tsx:68-124` and `frontend/e2e/tests/ts-z.catalog.spec.ts:21-66`

**Issue:** Both fixtures use `display_name` either as the *only* possible source
(user_stories/app_builder have a `display_name`, but it is never compared against what
`getWorkflowLabel("user_stories")` would return — which is "User Stories", a different
string) or as `null` (custom, to exercise the fallback). The vitest asserts "Custom
Workflow" (fallback) and "Generate product requirements" (display_name), but never asserts
that when BOTH a `display_name` and a `WORKFLOW_LABELS` entry exist, `display_name` wins.
Combined with WR-01, this means the production code path (always-truthy `display_name`
from the BE) is the one path neither test pins. The tests are non-vacuous for the two-gate
filter and the null-fallback, but the label-precedence branch is effectively untested.

**Fix:** Add an assertion against a row whose `display_name` differs from both its raw
`name` and its `getWorkflowLabel(id)` value — e.g. assert
`getByText("Generate product requirements")` is present AND `queryByText("User Stories")`
(the `getWorkflowLabel("user_stories")` value) is null — to prove `display_name` takes
precedence. Pair this with the WR-01 fix so the asserted shape matches real endpoint output.

## Info

### IN-01: Redundant hardcoded `prototype`/`ppt` wizard branches after the CHAIN_OPTIONS lookup (dead code)

**File:** `frontend/src/components/catalog/WorkflowCatalog.tsx:94-101`

**Issue:** `handleClick` first consults `CHAIN_OPTIONS` (which already contains `ppt` and
`prototype` with `requiresWizard: true` + a `wizardPath` — see `workflowChaining.ts:35-55`)
and routes via `opt.wizardPath`. The subsequent `if (type === "prototype")` /
`if (type === "ppt")` blocks therefore never execute for those types; they are dead
fallbacks. They are harmless (and mirror the literal SPEC §3.3 paths) but duplicate the
declarative table and reintroduce workflow-name literals the CHAIN_OPTIONS reuse was meant
to remove.

**Fix:** Drop the two `if` blocks and rely solely on the `CHAIN_OPTIONS` lookup, or keep
them only as a defensive guard with a comment that they are unreachable while CHAIN_OPTIONS
defines wizardPaths for both. Optional.

### IN-02: `launch_surface` is plumbed end-to-end but never consumed by the FE

**File:** `frontend/src/components/catalog/WorkflowCatalog.tsx` (consumer absent) / `frontend/src/lib/api.ts:548` / `backend/app/api/workflows.py:235`

**Issue:** `launch_surface` ("wizard") is declared in the prototype/ppt manifests, typed in
`WorkflowSummary` (BE + FE), and returned by the endpoint, but the catalog's wizard routing
keys off `CHAIN_OPTIONS` / hardcoded names (IN-01), not `row.launch_surface`. The field is
inert by design (SPEC labels it "optional metadata"), so this is not a bug — but it is
declared-but-unused data on the live path, which can drift (a manifest could set
`launch_surface: "wizard"` and still launch directly if it is not in CHAIN_OPTIONS).

**Fix:** Either consume `row.launch_surface === "wizard"` as the wizard-fork signal (making
the routing data-driven and removing IN-01's name literals), or add a short comment that
`launch_surface` is reserved/forward metadata not yet read by the FE. Optional.

### IN-03: `WorkflowSummary.icon` surfaced but never rendered

**File:** `frontend/src/components/catalog/WorkflowCatalog.tsx:157-183` / `frontend/src/lib/api.ts:547`

**Issue:** `icon` is added to the manifest, the BE summary, and the FE type, but the catalog
rows render no leading icon (a deliberate decision per 20-02-SUMMARY — "CreationHub rows
have none either"). The field is dead on the FE for now. Acceptable as forward metadata;
noting it so a future reviewer does not assume it is wired.

**Fix:** None required. Optionally document that `icon` is reserved for a future richer
(LibraryPage-style) catalog card.

---

_Reviewed: 2026-06-14_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
