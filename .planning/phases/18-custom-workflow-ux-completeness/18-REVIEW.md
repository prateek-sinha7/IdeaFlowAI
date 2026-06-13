---
phase: 18-custom-workflow-ux-completeness
reviewed: 2026-06-13T00:00:00Z
depth: standard
files_reviewed: 20
files_reviewed_list:
  - backend/agents/capabilities/deliverables/_mimetype.py
  - backend/agents/capabilities/deliverables/single_file.py
  - backend/agents/capabilities/deliverables/serialized_sandbox.py
  - backend/agents/capabilities/deliverables/streamed_text.py
  - backend/agents/capabilities/deliverables/ppt.py
  - backend/agents/execution_engine/engine.py
  - backend/agents/workflows/compiler.py
  - backend/agents/workflows/plan.py
  - backend/tests/agents/characterization/_normalize.py
  - frontend/src/app/dashboard/page.tsx
  - frontend/src/components/history/WorkflowHistory.tsx
  - frontend/src/components/preview/PreviewPanel.tsx
  - frontend/src/components/results/FilesTab.tsx
  - frontend/src/components/layout/DashboardLayout.tsx
  - frontend/src/components/workflow/AgentsPopup.tsx
  - frontend/src/components/workflow/IdeaInputPage.tsx
  - frontend/src/hooks/useWorkflow.ts
  - frontend/src/types/index.ts
  - frontend/src/lib/api.ts
findings:
  critical: 1
  warning: 3
  info: 2
  total: 6
status: issues_found
---

# Phase 18: Code Review Report

**Reviewed:** 2026-06-13
**Depth:** standard
**Files Reviewed:** 20 (one of the 20 in scope, AgentModelPicker.tsx, also read as a relocation host)
**Status:** issues_found

## Summary

The BE half of ISS-021 is clean and provably parity-safe: the two new `pipeline_complete`
keys (`deliverable_mimetype`/`deliverable_filename`) are spelled identically in the emitter
(`engine.py:1927-1928`) and in `_VOLATILE_STRIP_KEYS` (`_normalize.py:139-140`); the 4
characterization goldens pass byte-identical (65 parity/golden tests green), `lint-imports`
stays 4 kept / 0 broken, the per-resolver `default_mimetype` logic matches the locked spec,
and the compiler stays a thin pass-through (INV-5 honored). ISS-014 is clean: WorkflowComposer
+ CapabilityPalette are deleted with zero dangling imports, AgentModelPicker is relocated into
the AgentsPopup Agents tab, `model_overrides` is threaded only when a non-default model is
picked (empty selection → byte-identical payload), and `tsc --noEmit` passes. ISS-019 is a
faithful CSS-only flex-budget with no logic change. Both HTML iframes (live + history) are
correctly `sandbox="allow-scripts"` with NO `allow-same-origin`.

**However, the headline ISS-021 FE fix is only half-implemented and the two deliverable
surfaces diverge.** The history-reopen surface correctly treats `custom` (and any unknown
type) as the structural "no known branch matched" generic path → sandboxed iframe for HTML.
The LIVE surface still hardcodes `custom` as a known branch that routes to `MarkdownPreview`
(escaped HTML) — exactly the root-cause bug the phase was meant to eliminate, and explicitly
on the REJECTED-hacks list. A custom workflow that produces an HTML deliverable therefore
renders as escaped text while running, but renders correctly once reopened from history. This
is a BLOCKER: the primary user-facing surface for the headline feature is broken, and the two
surfaces contradict each other (the CONTEXT required them to agree).

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: Live `custom` HTML deliverable renders as escaped text — generic renderer never reached on the live surface

**File:** `frontend/src/app/dashboard/page.tsx:398` (live routing); `frontend/src/components/preview/PreviewPanel.tsx:374,510-514` (known-set + custom→markdown branch)

**Issue:** The live `pipeline_complete` router keeps `custom` in the known-branch set:

```ts
// page.tsx:398
if (pipelineType === "user_stories" || ... || pipelineType === "custom") {
  setUserStoryContent(finalOutput);   // ← custom HTML lands here
} else { setGenericDeliverable({...}) }  // ← generic path never reached for custom
```

and `PreviewPanel` lists `"custom"` in `KNOWN_RENDER_TYPES` (line 374) and renders it through
`MarkdownPreview` (lines 510-514), which has no `rehype-raw` — so HTML is escaped to literal
text. `genericDeliverable` is never populated for a live `custom` run, so
`GenericDeliverablePreview` (the sandboxed-iframe path) is unreachable live.

This is the exact root cause the phase was chartered to fix ("even the `custom` branch routes
to `MarkdownPreview` … HTML renders as escaped text", 18-CONTEXT lines 27/36) and is on the
REJECTED-hacks list ("route unknown→the `custom` branch (markdown-not-HTML → escaped text)").
The history-reopen path was fixed correctly — `WorkflowHistory.tsx:277` and `page.tsx:1077-1089`
both compute a structural `isGeneric` that does NOT special-case `custom`, so the SAME run
renders correctly in a sandboxed iframe once reopened. The live and history surfaces now
disagree, which the CONTEXT explicitly forbade ("the two reopen surfaces cannot diverge";
SC-001: "a brand-new custom workflow renders with zero per-workflow FE code").

Because `custom` is the actual `pipeline_type` emitted by the live agent-composer
(`IdeaInputPage.tsx:238` passes `effectiveType` = `"custom"`; `useWorkflow.ts` sends it
verbatim), this breaks the headline feature on the surface users hit first.

**Fix:** Drop `custom` from the live known-branch set so a `custom` (or any unknown) HTML/zip
deliverable flows into the generic mimetype-dispatched channel, mirroring the reopen path.
The generic renderer already handles `text/markdown` via `MarkdownPreview`, so plain-markdown
custom output keeps its existing look while HTML now gets the sandboxed iframe:

```ts
// page.tsx — remove `|| pipelineType === "custom"` from the user_stories branch
if (pipelineType === "user_stories" || pipelineType === "user_stories_revision"
    || pipelineType === "app_builder" || pipelineType === "app_builder_revision") {
  setUserStoryContent(finalOutput);
} else if (/* ppt … */) { ... }
else if (/* prototype … */) { ... }
else {
  setGenericDeliverable({
    mimetype: (data.deliverable_mimetype as string | undefined)
      || deriveDeliverableMimetype(finalOutput),   // fallback if BE key missing
    filename: (data.deliverable_filename as string | undefined) || undefined,
    content: finalOutput,
  });
}
```

```ts
// PreviewPanel.tsx — remove "custom" from KNOWN_RENDER_TYPES and from the
// (renderType === "app_builder" || renderType === "custom") render branch.
const KNOWN_RENDER_TYPES = ["user_stories", "ppt", "prototype", "app_builder"] as const;
```

Note the live `deliverable_mimetype` is authoritative (BE emits it), so unlike reopen there is
no need to sniff — but keep `deriveDeliverableMimetype(finalOutput)` as a defensive fallback in
case the key is absent (older runs / forward-compat). Re-test a live custom run that declares
`mimetype: text/html` renders in the sandboxed iframe, and a markdown custom run still renders
via MarkdownPreview.

## Warnings

### WR-01: serialized_sandbox→streamed_text fallback emits a mimetype that contradicts the bytes

**File:** `backend/agents/execution_engine/engine.py:1841-1849,1916-1918`

**Issue:** When the declared resolver is `serialized_sandbox` but the sandbox holds 0
deliverable files, `resolve()` returns `None` and the engine falls back to the `streamed_text`
resolver (markdown bytes) at line 1847-1849. The emitted `deliverable_mimetype`, however, is
computed from `_deliverable_strategy` (= the DECLARED `"serialized_sandbox"`) →
`default_mimetype("serialized_sandbox", …)` → `"application/zip"` (line 1916-1918). So the
contract advertises `application/zip` while `final_output` is actually markdown text. On the FE
generic path that would route markdown bytes into the `application/zip` → AppBuilder bundle
view (`PreviewPanel.tsx:194-195`) and offer a `.zip` download of markdown
(`FilesTab.tsx:301-311`). Today this is masked only because the workflows declaring
`serialized_sandbox` (app_builder) are still a KNOWN FE branch that ignores the mimetype — but
it is a latent correctness bug the moment a custom workflow declares `serialized_sandbox`.

**Fix:** Derive the emitted mimetype from the resolver that actually produced the bytes, not the
declared strategy, when the fallback fires. Track the effective strategy:

```python
_effective_strategy = _deliverable_strategy
final_output = _resolver.resolve(ectx)
if final_output is None:
    _effective_strategy = "streamed_text"
    final_output = _CAPABILITY_REGISTRY.resolve("deliverable", "streamed_text").resolve(ectx)
...
_deliverable_mimetype = getattr(ectx.deliverable, "mimetype", None) or \
    _default_mimetype(_effective_strategy, _deliverable_name)
```

(Author-declared `mimetype` still wins; only the computed default switches to match the bytes.)

### WR-02: history-reopen of a non-markdown custom deliverable is mis-typed to markdown

**File:** `frontend/src/types/index.ts:328-334`; `frontend/src/components/history/WorkflowHistory.tsx:278-280`; `frontend/src/app/dashboard/page.tsx:1085`

**Issue:** `deriveDeliverableMimetype` only ever returns `text/html` (for an `<!doctype`/`<html`
prefix) or `text/markdown`. A custom workflow whose deliverable is a serialized-sandbox bundle
or any non-HTML binary-ish payload is therefore mis-routed to `MarkdownPreview` on reopen
(`isGenericMarkdown`, WorkflowHistory.tsx:280/576) and offered as a `.md` download. The live
path will (once CR-01 is fixed) carry the true `deliverable_mimetype`, so live vs. reopen will
disagree for non-HTML/non-markdown custom deliverables. The CONTEXT flags persisting the
mimetype as the proper fix ("add it as an additive field on the existing run row") and only
permits the derive-heuristic "where the declared mimetype was not persisted".

**Fix:** Persist `deliverable_mimetype`/`deliverable_filename` additively on the run row
(carries owner_id/workspace_id) and read it on reopen instead of re-deriving; fall back to
`deriveDeliverableMimetype` only when the field is absent (legacy rows). If persistence is
out of scope for this phase, record it explicitly as a known reopen limitation in the SUMMARY
so the live/reopen divergence for zip/binary custom deliverables is not silently shipped.

### WR-03: `GenericDeliverablePreview` HTML detection misses `<artifact>`-wrapped / fenced HTML the resolver may emit

**File:** `frontend/src/components/preview/PreviewPanel.tsx:173`; cross-ref `single_file.py:71-82`

**Issue:** The generic renderer dispatches HTML purely on `mimetype === "text/html"`. That is
correct when the BE declares the mimetype. But the `single_file` resolver can return content
that is HTML wrapped/seeded (it `unwrap_artifact`s in some branches and returns raw streamed
output in others), and `default_mimetype("single_file", name)` returns `text/html` ONLY when
the declared `name` ends in `.html`/`.htm` — a custom workflow that names its deliverable e.g.
`output.txt` but streams HTML would be typed `application/octet-stream` and fall through to the
download affordance instead of the iframe. This is acceptable (download is safe), but the
inverse is the risk: the iframe path trusts `mimetype` and never re-validates the content is
actually HTML, while the markdown branch's `MarkdownPreview` (with rehype-raw, if enabled)
could execute embedded HTML. Confirm `MarkdownPreview` does NOT render raw HTML for the
`text/markdown` generic branch (line 190) — otherwise a custom workflow mis-declaring
`text/markdown` for an HTML payload would get an UNsandboxed HTML render, defeating the iframe
sandbox (T-18-05).

**Fix:** Verify `MarkdownPreview` escapes raw HTML (no `rehype-raw`) on the generic
`text/markdown` path; if it does not, gate raw-HTML rendering behind the same sandbox the
iframe uses, or sniff the content and force the iframe path when markdown-declared content is
actually `<!doctype`/`<html`. Document the decision in the component.

## Info

### IN-01: `CapabilitiesPalette` doc comment still says "the composer renders"

**File:** `frontend/src/lib/api.ts:508`

**Issue:** The interface doc above `getCapabilities` was updated (lines 514-519), but the
adjacent `CapabilitiesPalette` interface comment still reads "The full palette payload the
composer renders." — the composer (WorkflowComposer) was deleted this phase.

**Fix:** Update to "…the AgentModelPicker model catalog renders" for accuracy.

### IN-02: `AgentModelPicker` header docstring references the deleted composer

**File:** `frontend/src/components/workflow/AgentModelPicker.tsx:3-14`

**Issue:** The relocated picker's docstring still says "populated from the capability palette's
model catalog" and "Additive sibling panel — it does not change the existing composer
behavior." The composer no longer exists; the picker is now the primary (not sibling) model
selection surface inside AgentsPopup.

**Fix:** Refresh the docstring to describe its new home (AgentsPopup Agents tab) so future
readers don't go looking for a composer.

---

_Reviewed: 2026-06-13_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
