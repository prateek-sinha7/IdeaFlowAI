# Open issues — deduplicated by fix site

Every open/deferred card in `.knowledge/`, grouped by **where the fix goes** rather
than by what the user saw. Companion to [`OPEN-ISSUES.md`](OPEN-ISSUES.md), which is
the flat per-symptom register.

Generated from the card store — regenerate rather than editing rows by hand:

```
python3 bug-hunter/tools/dedup.py
```

**227 open cards → 200 units of work** (46 families + 154 singletons), schedulable as **41 work batches** — see [Work batches](#work-batches--how-to-actually-run-this) for the execution view.

A merge is proposed only where cards share a **fix site**, not merely a symptom
class. Two Escape-key bugs in unrelated components are one class and two diffs —
merging those would close a family while a member is still broken.

| tier | what it means | families | cards |
|---|---|---|---|
| A′ | root **already fixed**, siblings still open — replicate the landed diff | 28 | 43 |
| A | declared family, root and siblings both open — one line trip | 3 | 7 |
| B | same file **and** same defect class — proposed, needs review | 15 | 23 |
| C | no kin found — stays its own row | — | 154 |

---

## Tier A′ — the fix already landed, the siblings were left open

**This is the finding that matters.** For each root below, the line fixed the call
site the bug report named, wrote a FIX card, and closed the root — while the sibling
cards naming the *other* call sites stayed open. The expensive phases are already
paid for: root cause is known, the diff exists, the pattern is proven.

These do not need validate or analyze. They need the named FIX card read and its
change applied at the sibling's line. Send them straight to **fix**.

| root (resolved) | landed fix | open siblings | what the siblings are |
|---|---|---|---|
| [ISS-238](../.knowledge/cards/20260828-1633-ISS-238.md) | [FIX-344](../.knowledge/cards/20260828-2046-FIX-344.md) | [ISS-348](../.knowledge/cards/20260828-2102-ISS-348.md), [ISS-349](../.knowledge/cards/20260828-2102-ISS-349.md), [ISS-350](../.knowledge/cards/20260828-2102-ISS-350.md) | Sibling of ISS-238: routes.ts:224-229 head==="login" has the same missing depth guard; page.tsx has no login … |
| [ISS-245](../.knowledge/cards/20260828-1631-ISS-245.md) | [FIX-345](../.knowledge/cards/20260828-2250-FIX-345.md) | [ISS-352](../.knowledge/cards/20260828-2101-ISS-352.md), [ISS-353](../.knowledge/cards/20260828-2102-ISS-353.md), [ISS-354](../.knowledge/cards/20260828-2103-ISS-354.md) | INFERRED sibling of ISS-245: login/page.tsx ChallengeForm Continue button (disabled={isLoading} at L525) gate… |
| [ISS-316](../.knowledge/cards/20260828-1952-ISS-316.md) | [FIX-105](../.knowledge/cards/20260723-FIX-105.md), [FIX-229](../.knowledge/cards/20260812-0653-FIX-229.md), [FIX-381](../.knowledge/cards/20260829-0220-FIX-381.md) | [ISS-435](../.knowledge/cards/20260828-2253-ISS-435.md), [ISS-436](../.knowledge/cards/20260828-2253-ISS-436.md), [ISS-437](../.knowledge/cards/20260828-2253-ISS-437.md) | INFERRED: complete_seqs excludes degraded pipeline_complete events, so resume_supersedes never fires for a ca… |
| [ISS-363](../.knowledge/cards/20260828-2129-ISS-363.md) | [FIX-349](../.knowledge/cards/20260828-2324-FIX-349.md), [FIX-365](../.knowledge/cards/20260829-0045-FIX-365.md) | [ISS-364](../.knowledge/cards/20260828-2130-ISS-364.md), [ISS-365](../.knowledge/cards/20260828-2131-ISS-365.md), [ISS-366](../.knowledge/cards/20260828-2132-ISS-366.md) | INFERRED: ConfigLeversFlat.updateLever -> onSelectionsChange -> selectionsRef.current is the same live-write,… |
| [ISS-190](../.knowledge/cards/20260828-1501-ISS-190.md) | **none found** | [ISS-195](../.knowledge/cards/20260828-1558-ISS-195.md), [ISS-197](../.knowledge/cards/20260828-1559-ISS-197.md) | INFERRED sibling of ISS-190: page.tsx:3701 gates ALL 34 screens on the same mount-once mounted/isAuthenticate… |
| [ISS-302](../.knowledge/cards/20260828-1734-ISS-302.md) | [FIX-372](../.knowledge/cards/20260829-0141-FIX-372.md) | [ISS-414](../.knowledge/cards/20260828-2202-ISS-414.md), [ISS-415](../.knowledge/cards/20260828-2202-ISS-415.md) | WorkflowHistory DeleteModal (L1237) takes no name prop; deleteConfirmId (L179) stores only the run id — same … |
| [ISS-311](../.knowledge/cards/20260828-1740-ISS-311.md) | [FIX-376](../.knowledge/cards/20260829-0152-FIX-376.md) | [ISS-420](../.knowledge/cards/20260829-0021-ISS-420.md), [ISS-421](../.knowledge/cards/20260829-0020-ISS-421.md) | IdeaInputPage.tsx:1900-1902 leaves the Advanced button unguarded before a migration sub-pipeline is chosen, s… |
| [ISS-312](../.knowledge/cards/20260828-1941-ISS-312.md) | [FIX-374](../.knowledge/cards/20260829-0146-FIX-374.md) | [ISS-422](../.knowledge/cards/20260829-0027-ISS-422.md), [ISS-423](../.knowledge/cards/20260829-0026-ISS-423.md) | INFERRED: useChatAttachments.ts computes FileContentEntry.truncated correctly but ChatAttachments.tsx never r… |
| [ISS-315](../.knowledge/cards/20260828-1750-ISS-315.md) | [FIX-375](../.knowledge/cards/20260829-0151-FIX-375.md) | [ISS-431](../.knowledge/cards/20260829-0038-ISS-431.md), [ISS-432](../.knowledge/cards/20260829-0039-ISS-432.md) | INFERRED sibling of ISS-315: ComposerPage.tsx:1076-1090 Run once guard (briefText.trim().length<3) blocks han… |
| [ISS-320](../.knowledge/cards/20260828-1802-ISS-320.md) | [FIX-385](../.knowledge/cards/20260829-0241-FIX-385.md) | [ISS-480](../.knowledge/cards/20260828-2320-ISS-480.md), [ISS-481](../.knowledge/cards/20260828-2321-ISS-481.md) | deleteSkill (SkillManager.tsx:99-114) wired to onClick:221 fires DELETE with zero confirm, same gap as ISS-320 |
| [ISS-326](../.knowledge/cards/20260828-ISS-326.md) | [FIX-388](../.knowledge/cards/20260829-0053-FIX-388.md) | [ISS-489](../.knowledge/cards/20260829-0150-ISS-489.md), [ISS-491](../.knowledge/cards/20260829-0149-ISS-491.md) | AgentSkillsPicker skill-detail modal (AgentSkillsPicker.tsx:251-289) has role="dialog" but zero Escape handli… |
| [ISS-097](../.knowledge/cards/20260812-1153-ISS-097.md) | [FIX-242](../.knowledge/cards/20260812-2116-FIX-242.md) | [ISS-132](../.knowledge/cards/20260812-2116-ISS-132.md) | task_loop.py never passes invocation_gated, so ticking a task-loop agent opens one sequential review gate per… |
| [ISS-225](../.knowledge/cards/20260828-1541-ISS-225.md) | [FIX-285](../.knowledge/cards/20260824-1621-FIX-285.md), [FIX-336](../.knowledge/cards/20260828-2201-FIX-336.md), [FIX-337](../.knowledge/cards/20260828-2210-FIX-337.md) | [ISS-263](../.knowledge/cards/20260828-1811-ISS-263.md) | INFERRED sibling of ISS-225: selections-only save skips R-03 entirely on empty selections, and synthesize_man… |
| [ISS-232](../.knowledge/cards/20260828-1627-ISS-232.md) | [FIX-340](../.knowledge/cards/20260828-2230-FIX-340.md) | [ISS-336](../.knowledge/cards/20260828-1846-ISS-336.md) | INFERRED sibling of ISS-232: useHooksCatalog.ts returns an unmemoized array like useSkillsCatalog, so the sha… |
| [ISS-244](../.knowledge/cards/20260828-1634-ISS-244.md) | [FIX-341](../.knowledge/cards/20260828-2236-FIX-341.md), [FIX-398](../.knowledge/cards/20260829-0352-FIX-398.md) | [ISS-342](../.knowledge/cards/20260828-2059-ISS-342.md) | INFERRED sibling of ISS-244: login/page.tsx ChallengeForm (L453/469/495/514 onChanges) never clears error set… |
| [ISS-246](../.knowledge/cards/20260828-1657-ISS-246.md) | [FIX-348](../.knowledge/cards/20260828-2321-FIX-348.md) | [ISS-368](../.knowledge/cards/20260828-1927-ISS-368.md) | The Advanced modal "Reset to default" button (CanvasView.tsx:2249) is also disabled via !onRunConfigChange/!o… |
| [ISS-247](../.knowledge/cards/20260828-1637-ISS-247.md) | [FIX-346](../.knowledge/cards/20260828-2314-FIX-346.md), [FIX-377](../.knowledge/cards/20260829-0158-FIX-377.md), [FIX-386](../.knowledge/cards/20260829-0242-FIX-386.md) | [ISS-361](../.knowledge/cards/20260828-2120-ISS-361.md) | INFERRED sibling of ISS-247: LaunchWizard.tsx:1046/583-584/243 wires the same ReviewGatesSection to its own g… |
| [ISS-274](../.knowledge/cards/20260828-1854-ISS-274.md) | [FIX-350](../.knowledge/cards/20260828-2340-FIX-350.md) | [ISS-378](../.knowledge/cards/20260828-2006-ISS-378.md) | ConfigLeversFlat (AgentsPopup.tsx:1700-1771) also renders only Model/Validator/Gate/Retry, no Tools row — sam… |
| [ISS-285](../.knowledge/cards/20260828-1745-ISS-285.md) | [FIX-357](../.knowledge/cards/20260828-2210-FIX-357.md), [FIX-358](../.knowledge/cards/20260829-0011-FIX-358.md) | [ISS-388](../.knowledge/cards/20260828-2234-ISS-388.md) | reopenTabFor has no run-preview-full case, so opening it on a BUILDING run lands on Steps (PreviewPanel.tsx:8… |
| [ISS-290](../.knowledge/cards/20260828-1720-ISS-290.md) | [FIX-360](../.knowledge/cards/20260829-0024-FIX-360.md) | [ISS-399](../.knowledge/cards/20260828-2308-ISS-399.md) | INFERRED sibling of ISS-290: same stale HOOK.md ids feed an exact .includes(agent.id) filter with no universa… |
| [ISS-292](../.knowledge/cards/20260828-1918-ISS-292.md) | [FIX-361](../.knowledge/cards/20260829-0029-FIX-361.md), [FIX-382](../.knowledge/cards/20260829-0223-FIX-382.md) | [ISS-398](../.knowledge/cards/20260828-2106-ISS-398.md) | _validate_model_overrides (run_engine.py:547-607) allow-lists model_id against ModelCatalog.ids() only, no ti… |
| [ISS-293](../.knowledge/cards/20260828-1924-ISS-293.md) | [FIX-364](../.knowledge/cards/20260829-0041-FIX-364.md) | [ISS-402](../.knowledge/cards/20260828-2121-ISS-402.md) | _inject_constitution (factory.py:673-699), called from _compose_system_prompt:586 every run, injects the full… |
| [ISS-301](../.knowledge/cards/20260828-1740-ISS-301.md) | [FIX-370](../.knowledge/cards/20260829-0116-FIX-370.md) | [ISS-409](../.knowledge/cards/20260828-2148-ISS-409.md) | INFERRED sibling of ISS-301: IntegrationsCard.tsx:90's empty catch leaves patStatus/keys at their unset defau… |
| [ISS-304](../.knowledge/cards/20260828-1600-ISS-304.md) | [FIX-373](../.knowledge/cards/20260829-0143-FIX-373.md) | [ISS-417](../.knowledge/cards/20260828-2230-ISS-417.md) | INFERRED sibling of ISS-304: TokenUsageSummary.tsx:19-28, mounted in the Steps tab, destructures the same cor… |
| [ISS-314](../.knowledge/cards/20260828-1946-ISS-314.md) | [FIX-378](../.knowledge/cards/20260829-0207-FIX-378.md) | [ISS-433](../.knowledge/cards/20260829-0040-ISS-433.md) | PrototypePreview.tsx:502 browser-chrome bar (dots, URL pill, zoom x3, divider, Tweaks, Source, Open) has no f… |
| [ISS-319](../.knowledge/cards/20260828-1804-ISS-319.md) | [FIX-361](../.knowledge/cards/20260829-0029-FIX-361.md), [FIX-382](../.knowledge/cards/20260829-0223-FIX-382.md) | [ISS-471](../.knowledge/cards/20260828-2310-ISS-471.md) | Same race as ISS-319: _to_response(user, db) reads user.tier/is_admin post-refresh, so a concurrent admin wri… |
| [ISS-328](../.knowledge/cards/20260828-1834-ISS-328.md) | [FIX-391](../.knowledge/cards/20260829-0305-FIX-391.md), [FIX-400](../.knowledge/cards/20260829-0402-FIX-400.md) | [ISS-492](../.knowledge/cards/20260829-0150-ISS-492.md) | INFERRED sibling of ISS-328: app/workflow/page.tsx never passes pipelineState/onResetPipeline/onViewResults e… |
| [ISS-617](../.knowledge/cards/20260831-0110-ISS-617.md) | [FIX-323](../.knowledge/cards/20260828-1629-FIX-323.md), [FIX-415](../.knowledge/cards/20260831-0110-FIX-415.md) | [ISS-636](../.knowledge/cards/20260831-0115-ISS-636.md) | the agents API and the frontend-consistency check assert gate values FIX-323 deleted from AGENT.md and workfl… |

> **1 root(s) carry no FIX card**: ISS-190. The root is marked
> resolved but nothing records the diff — treat these siblings as tier C until that
> is explained, because there may be no landed change to replicate.

---

## Tier A — declared families, both ends still open

The cards name each other. One fix, one test, one verify closes the set.

### [ISS-228](../.knowledge/cards/20260828-1758-ISS-228.md) + 2 sibling(s)

Saved workflow's launch panel discards the override fetch — generic base-type wizard renders even though GET /api/user-workflows/{id} succeeds

| card | fix site | summary |
|---|---|---|
| [ISS-228](../.knowledge/cards/20260828-1758-ISS-228.md) | `frontend/src/components/workflow/LaunchWizard.tsx` | On /workflows/{id}/run, LaunchWizard.tsx fires GET /api/user-workflows/{id} and GET /api/workflows/{base_pipeline_type} in parall… |
| [ISS-283](../.knowledge/cards/20260828-1905-ISS-283.md) | `frontend/src/components/layout/DashboardLayout.tsx`, `frontend/src/components/workflow/LaunchWizard.tsx` | INFERRED sibling of ISS-228: handleLaunchSaved seeds the same {mode}.draft via /workflow/create, hitting the identical pipelineAg… |
| [ISS-284](../.knowledge/cards/20260828-1906-ISS-284.md) | `frontend/src/components/workflow/LaunchWizard.tsx` | INFERRED sibling of ISS-228: handleSave/handleSaveAsOverride (LaunchWizard.tsx:703,737) send pipelineAgents as agent_ids, so savi… |

### [ISS-392](../.knowledge/cards/20260828-2250-ISS-392.md) + 1 sibling(s)

Corrects ISS-287: LibraryPage DOES pass onSelectionsChange — the real defect is that AgentCapabilitiesModal has no backend persistence path at all for Config-tab overrides

| card | fix site | summary |
|---|---|---|
| [ISS-392](../.knowledge/cards/20260828-2250-ISS-392.md) | `frontend/src/components/library/LibraryPage.tsx`, `frontend/src/components/workflow/AgentsPopup.tsx` | AgentCapabilitiesModal Save agent has zero fetch/API calls anywhere in AgentsPopup.tsx; LibraryPage DOES wire onSelectionsChange … |
| [ISS-393](../.knowledge/cards/20260828-2251-ISS-393.md) | `frontend/src/app/workflow/page.tsx`, `frontend/src/components/workflow/AgentLibrary.tsx`, `frontend/src/components/workflow/AgentsPopup.tsx`, `frontend/src/components/workflow/WorkflowView.tsx`, `frontend/src/components/workflow/composer/ComposerPage.tsx` | AgentLibrary.tsx:332-338 mounts AgentCapabilitiesModal with onSkillsChange but no onSelectionsChange, so effectiveOnSelectionsCha… |

### [ISS-318](../.knowledge/cards/20260828-1956-ISS-318.md) + 1 sibling(s)

Library agent detail Skills tab shows persistent-looking Add feedback but only mirrors into an in-memory ref, lost on reload

| card | fix site | summary |
|---|---|---|
| [ISS-318](../.knowledge/cards/20260828-1956-ISS-318.md) | `frontend/src/components/library/LibraryPage.tsx`, `frontend/src/components/workflow/AgentsPopup.tsx`, `frontend/src/components/workflow/composer/AgentSkillsPicker.tsx` | LibraryPage passes onSkillsChange to AgentCapabilitiesModal, which forces AgentSkillsPicker readOnly=false against its own doc co… |
| [ISS-441](../.knowledge/cards/20260828-2257-ISS-441.md) | `frontend/src/app/layout.tsx`, `frontend/src/components/library/LibraryPage.tsx`, `frontend/src/components/workflow/AgentsPopup.tsx`, `frontend/src/context/SkillsHooksContext.tsx` | AgentsPopup.tsx:531-532 shadows the propHooks/propAttachHook params with ctx.attachedHooks/ctx.attachHook unconditionally, so the… |

---

## Tier B — same file, same defect class (proposed — review before merging)

These share a file *and* a defect class, which is the strongest signal available
short of a card saying so. It is still a guess: confirm the two really collapse to
one diff before merging, and split them back out if they do not.

| fix site | class | cards | first card |
|---|---|---|---|
| `frontend/src/components/layout/DashboardLayout.tsx` | stale-state | [BUG-006-007-GROUNDED-CONTEXT](../.knowledge/cards/20260716-1520-BUG-006-007-GROUNDED-CONTEXT.md), [BUG-008-011-GROUNDED-CONTEXT](../.knowledge/cards/20260716-1636-BUG-008-011-GROUNDED-CONTEXT.md), [BUG-012-FOLLOWUP-LABEL-GROUNDED-CONTEXT](../.knowledge/cards/20260716-2036-BUG-012-FOLLOWUP-LABEL-GROUNDED-CONTEXT.md), [BUG-012-GROUNDED-CONTEXT](../.knowledge/cards/20260716-1725-BUG-012-GROUNDED-CONTEXT.md), [BUG-014-GROUNDED-CONTEXT](../.knowledge/cards/20260716-2156-BUG-014-GROUNDED-CONTEXT.md), [ISS-347](../.knowledge/cards/20260828-2058-ISS-347.md) | BUG-006: lane type chip read workflowType not effectiveReviseType, missing a third stale-label cons… |
| `frontend/src/components/preview/PreviewPanel.tsx` | stale-state | [BUG-008-011-GROUNDED-CONTEXT](../.knowledge/cards/20260716-1636-BUG-008-011-GROUNDED-CONTEXT.md), [BUG-012-FOLLOWUP-LABEL-GROUNDED-CONTEXT](../.knowledge/cards/20260716-2036-BUG-012-FOLLOWUP-LABEL-GROUNDED-CONTEXT.md), [BUG-012-GROUNDED-CONTEXT](../.knowledge/cards/20260716-1725-BUG-012-GROUNDED-CONTEXT.md), [ISS-412](../.knowledge/cards/20260828-2343-ISS-412.md) | BUG-008: reopened deliverables render empty since hasGenericDeliverable gates on stale workflowType… |
| `frontend/src/components/history/WorkflowHistory.tsx` | stale-state | [ISS-145](../.knowledge/cards/20260813-0205-ISS-145.md), [ISS-209](../.knowledge/cards/20260828-1617-ISS-209.md), [ISS-412](../.knowledge/cards/20260828-2343-ISS-412.md) | Vitest baseline is stale by ~10x: measured 147 failed/894 passed vs a documented '~8 known reds'; s… |
| `frontend/src/components/layout/DashboardLayout.tsx` | confirm-dialog | [ISS-371](../.knowledge/cards/20260828-2140-ISS-371.md), [ISS-372](../.knowledge/cards/20260828-2141-ISS-372.md), [ISS-622](../.knowledge/cards/20260831-0115-ISS-622.md) | IdeaInputPage.tsx:1577 wires onClick={onBack} to the same ungated handleBackNav (DashboardLayout.ts… |
| `frontend/src/components/settings/AccountSettings.tsx` | confirm-dialog | [ISS-372](../.knowledge/cards/20260828-2141-ISS-372.md), [ISS-482](../.knowledge/cards/20260828-2322-ISS-482.md), [ISS-622](../.knowledge/cards/20260831-0115-ISS-622.md) | AccountSettings.tsx:209 wires onClick={onBack} to the same ungated handleBackNav, discarding typed … |
| `frontend/src/hooks/useWorkflow.ts` | stale-state | [ISS-438](../.knowledge/cards/20260829-0056-ISS-438.md), [ISS-439](../.knowledge/cards/20260829-0057-ISS-439.md), [ISS-440](../.knowledge/cards/20260829-0058-ISS-440.md) | RunChatLane.tsx:579 derives errored from the same stale pipelineState.agents[].status==="error" as … |
| `.planning/SSE-QA-BUG-LOG.md` | stale-state | [BUG-006-007-GROUNDED-CONTEXT](../.knowledge/cards/20260716-1520-BUG-006-007-GROUNDED-CONTEXT.md), [BUG-008-011-GROUNDED-CONTEXT](../.knowledge/cards/20260716-1636-BUG-008-011-GROUNDED-CONTEXT.md) | BUG-006: lane type chip read workflowType not effectiveReviseType, missing a third stale-label cons… |
| `backend/agents/execution_engine/engine.py` | stale-state | [ISS-104](../.knowledge/cards/20260812-1312-ISS-104.md), [ISS-131](../.knowledge/cards/20260812-2116-ISS-131.md) | Multiple in-code citations to shutdown-path line numbers had drifted from the code they described, … |
| `backend/agents/execution_engine/engine.py` | silent-discard | [FIX-BUGFIX-NESTED-REVISION](../.knowledge/cards/20260811-2031-FIX-BUGFIX-NESTED-REVISION.md), [ISS-133](../.knowledge/cards/20260812-2148-ISS-133.md) | Two deferred defects: a second update_specs click at the re-opened gate silently no-ops, and nested… |
| `frontend/e2e/tests/ts-t.history.spec.ts` | stale-state | [BUG-008-011-GROUNDED-CONTEXT](../.knowledge/cards/20260716-1636-BUG-008-011-GROUNDED-CONTEXT.md), [BUG-012-GROUNDED-CONTEXT](../.knowledge/cards/20260716-1725-BUG-012-GROUNDED-CONTEXT.md) | BUG-008: reopened deliverables render empty since hasGenericDeliverable gates on stale workflowType… |
| `frontend/src/app/[...view]/contentSourceRunScope.source.test.ts` | stale-state | [BUG-012-GROUNDED-CONTEXT](../.knowledge/cards/20260716-1725-BUG-012-GROUNDED-CONTEXT.md), [ISS-145](../.knowledge/cards/20260813-0205-ISS-145.md) | Reopened od_ppt/od_prototype runs render blank because PreviewPanel's detectedType short-circuits o… |
| `frontend/src/components/layout/AppHeader.tsx` | stale-state | [BUG-012-FOLLOWUP-LABEL-GROUNDED-CONTEXT](../.knowledge/cards/20260716-2036-BUG-012-FOLLOWUP-LABEL-GROUNDED-CONTEXT.md), [ISS-143](../.knowledge/cards/20260813-0205-ISS-143.md) | The BUG-006/012 binding was gated on !isPipelineRunning, so a non-terminal reopen still showed the … |
| `frontend/src/components/library/LibraryPage.tsx` | silent-discard | [BUG-073](../.knowledge/cards/20260829-1508-BUG-073.md), [BUG-095](../.knowledge/cards/20260829-1508-BUG-095.md) | Agent config overrides in library detail have no server sink; changes silently discarded on reload. |
| `frontend/src/components/workflow/AgentsPopup.tsx` | silent-discard | [BUG-073](../.knowledge/cards/20260829-1508-BUG-073.md), [BUG-095](../.knowledge/cards/20260829-1508-BUG-095.md) | Agent config overrides in library detail have no server sink; changes silently discarded on reload. |
| `frontend/src/components/workflow/LaunchWizard.tsx` | stale-state | [BUG-014-GROUNDED-CONTEXT](../.knowledge/cards/20260716-2156-BUG-014-GROUNDED-CONTEXT.md), [ISS-347](../.knowledge/cards/20260828-2058-ISS-347.md) | LaunchWizard read chain.source_run_id from sessionStorage unconditionally and never cleared it, so … |

### Class campaigns (one sweep, many diffs — not one merge)

Same defect class across *different* files. These do **not** merge into one row, but
one engineer holding the pattern in their head can clear the set far faster than the
line can trip on each. Batch them onto one worker; keep the rows separate.

| class | cards |
|---|---|
| stale-state | 23: [BUG-006-007-GROUNDED-CONTEXT](../.knowledge/cards/20260716-1520-BUG-006-007-GROUNDED-CONTEXT.md), [BUG-008-011-GROUNDED-CONTEXT](../.knowledge/cards/20260716-1636-BUG-008-011-GROUNDED-CONTEXT.md), [BUG-012-FOLLOWUP-LABEL-GROUNDED-CONTEXT](../.knowledge/cards/20260716-2036-BUG-012-FOLLOWUP-LABEL-GROUNDED-CONTEXT.md), [BUG-012-GROUNDED-CONTEXT](../.knowledge/cards/20260716-1725-BUG-012-GROUNDED-CONTEXT.md), [BUG-014-GROUNDED-CONTEXT](../.knowledge/cards/20260716-2156-BUG-014-GROUNDED-CONTEXT.md), [BUG-021-GROUNDED-CONTEXT](../.knowledge/cards/20260717-2113-BUG-021-GROUNDED-CONTEXT.md), [ISS-073](../.knowledge/cards/20260812-0138-ISS-073.md), [ISS-076](../.knowledge/cards/20260812-0212-ISS-076.md), [ISS-079](../.knowledge/cards/20260812-0236-ISS-079.md), [ISS-096](../.knowledge/cards/20260812-1120-ISS-096.md), [ISS-104](../.knowledge/cards/20260812-1312-ISS-104.md), [ISS-131](../.knowledge/cards/20260812-2116-ISS-131.md), [ISS-143](../.knowledge/cards/20260813-0205-ISS-143.md), [ISS-145](../.knowledge/cards/20260813-0205-ISS-145.md), [ISS-180](../.knowledge/cards/20260825-2115-ISS-180.md), [ISS-209](../.knowledge/cards/20260828-1617-ISS-209.md), [ISS-342](../.knowledge/cards/20260828-2059-ISS-342.md), [ISS-347](../.knowledge/cards/20260828-2058-ISS-347.md), [ISS-399](../.knowledge/cards/20260828-2308-ISS-399.md), [ISS-412](../.knowledge/cards/20260828-2343-ISS-412.md), [ISS-438](../.knowledge/cards/20260829-0056-ISS-438.md), [ISS-439](../.knowledge/cards/20260829-0057-ISS-439.md), [ISS-440](../.knowledge/cards/20260829-0058-ISS-440.md) |
| silent-discard | 12: [BUG-036](../.knowledge/cards/20260829-1508-BUG-036.md), [BUG-073](../.knowledge/cards/20260829-1508-BUG-073.md), [BUG-095](../.knowledge/cards/20260829-1508-BUG-095.md), [BUG-106](../.knowledge/cards/20260829-1508-BUG-106.md), [BUG-CWF-002-custom-workflow](../.knowledge/cards/20260803-BUG-CWF-002-custom-workflow.md), [FIX-BUGFIX-NESTED-REVISION](../.knowledge/cards/20260811-2031-FIX-BUGFIX-NESTED-REVISION.md), [ISS-133](../.knowledge/cards/20260812-2148-ISS-133.md), [ISS-263](../.knowledge/cards/20260828-1811-ISS-263.md), [ISS-318](../.knowledge/cards/20260828-1956-ISS-318.md), [ISS-387](../.knowledge/cards/20260828-2228-ISS-387.md), [ISS-431](../.knowledge/cards/20260829-0038-ISS-431.md), [ISS-482](../.knowledge/cards/20260828-2322-ISS-482.md) |
| confirm-dialog | 8: [ISS-371](../.knowledge/cards/20260828-2140-ISS-371.md), [ISS-372](../.knowledge/cards/20260828-2141-ISS-372.md), [ISS-414](../.knowledge/cards/20260828-2202-ISS-414.md), [ISS-415](../.knowledge/cards/20260828-2202-ISS-415.md), [ISS-480](../.knowledge/cards/20260828-2320-ISS-480.md), [ISS-481](../.knowledge/cards/20260828-2321-ISS-481.md), [ISS-482](../.knowledge/cards/20260828-2322-ISS-482.md), [ISS-622](../.knowledge/cards/20260831-0115-ISS-622.md) |
| keyboard-a11y | 6: [BUG-104](../.knowledge/cards/20260829-1508-BUG-104.md), [ISS-431](../.knowledge/cards/20260829-0038-ISS-431.md), [ISS-489](../.knowledge/cards/20260829-0150-ISS-489.md), [ISS-491](../.knowledge/cards/20260829-0149-ISS-491.md), [ISS-605](../.knowledge/cards/20260829-0216-ISS-605.md), [ISS-627](../.knowledge/cards/20260831-0115-ISS-627.md) |
| route-depth | 4: [ISS-348](../.knowledge/cards/20260828-2102-ISS-348.md), [ISS-349](../.knowledge/cards/20260828-2102-ISS-349.md), [ISS-350](../.knowledge/cards/20260828-2102-ISS-350.md), [ISS-386](../.knowledge/cards/20260828-2228-ISS-386.md) |
| list-cap | 1: [BUG-037](../.knowledge/cards/20260829-1508-BUG-037.md) |
| double-submit | 1: [ISS-352](../.knowledge/cards/20260828-2101-ISS-352.md) |

---

## Work batches — how to actually run this

The tiers above say what *is* one defect. This says what to hand one worker.

A batch is **not** a merged fix — the cards in it stay separate defects with
separate tests. It is one worker opening one file once and clearing every open
card in it. That pays twice:

1. **Comprehension amortises.** `DashboardLayout.tsx` is ~2,400 lines. Reading it
   once for 11 cards beats reading it 11 times.
2. **One test run and one browser verify per batch**, not per card. Verify is the
   lane-bound phase, so this is what actually moves the runtime.

### Rounds — what may run at the same time

Batching by file is **not** on its own safe to parallelise. A card whose `globs`
name two files sits in one batch but writes both, so it collides with the batch
that owns the other — there are 20 such conflicts here. Merging every conflicting
pair instead collapses the frontend into a single 124-card blob.

So batches are coloured into **rounds**: two batches share a round only when the
files they write are disjoint. **Every batch in a round can run in parallel with
no possibility of collision. Rounds run one after another.**

| round | batches | cards |
|---|---|---|
| 1 | 17 — all concurrent | 96 |
| 2 | 11 — all concurrent | 46 |
| 3 | 4 — all concurrent | 42 |
| 4 | 5 — all concurrent | 27 |
| 5 | 3 — all concurrent | 12 |
| 6 | 1 — all concurrent | 4 |

**35 multi-card batches** carry 221 of the 227 cards.

### Domains — each block is one coherent area of the app

| domain | cards | batches | earliest round |
|---|---|---|---|
| [backend · other](#backend--other) | 31 | 4 | 1 |
| [backend · api](#backend--api) | 29 | 4 | 1 |
| [frontend · layout](#frontend--layout) | 23 | 2 | 1 |
| [frontend · workflow](#frontend--workflow) | 22 | 3 | 2 |
| [frontend · unplaced](#frontend--unplaced) | 18 | 1 | 1 |
| [frontend · hooks](#frontend--hooks) | 16 | 2 | 3 |
| [frontend · composer](#frontend--composer) | 14 | 2 | 4 |
| [frontend · history](#frontend--history) | 13 | 1 | 3 |
| [frontend · routes](#frontend--routes) | 13 | 5 | 1 |
| [frontend · library](#frontend--library) | 11 | 2 | 1 |
| [frontend · components](#frontend--components) | 10 | 3 | 1 |
| [frontend · preview](#frontend--preview) | 7 | 2 | 1 |
| [tests · integration](#tests--integration) | 5 | 2 | 1 |
| [frontend · settings](#frontend--settings) | 4 | 2 | 1 |
| [frontend · lib](#frontend--lib) | 4 | 2 | 3 |
| [backend · unplaced](#backend--unplaced) | 3 | 1 | 1 |
| [docs · planning](#docs--planning) | 2 | 1 | 1 |
| [backend · engine](#backend--engine) | 1 | 1 | 1 |
| [unclassified](#unclassified) | 1 | 1 | 1 |

Every card carries a domain — there is no uncategorised bucket. A row marked
*fix site not recorded* is still domain-placed; what it lacks is a file, so it
cannot be collision-checked and must be triaged before it is scheduled.

#### backend · other

31 cards across 4 batch(es).

| round | fix site | cards | members |
|---|---|---|---|
| 1 | **backend · other** | 19 | [ISS-096](../.knowledge/cards/20260812-1120-ISS-096.md), [ISS-098](../.knowledge/cards/20260812-1153-ISS-098.md), [ISS-101](../.knowledge/cards/20260812-1232-ISS-101.md), [ISS-106](../.knowledge/cards/20260812-1315-ISS-106.md), [ISS-118](../.knowledge/cards/20260812-1612-ISS-118.md), [ISS-120](../.knowledge/cards/20260812-1637-ISS-120.md), [ISS-130](../.knowledge/cards/20260812-2116-ISS-130.md), [ISS-132](../.knowledge/cards/20260812-2116-ISS-132.md), [ISS-156](../.knowledge/cards/20260813-1300-ISS-156.md), [ISS-185](../.knowledge/cards/20260825-2115-ISS-185.md), [ISS-357](../.knowledge/cards/20260828-1915-ISS-357.md), [ISS-630](../.knowledge/cards/20260831-0115-ISS-630.md), [ISS-631](../.knowledge/cards/20260831-0115-ISS-631.md), [ISS-632](../.knowledge/cards/20260831-0115-ISS-632.md), [ISS-633](../.knowledge/cards/20260831-0115-ISS-633.md), [ISS-634](../.knowledge/cards/20260831-0115-ISS-634.md), [ISS-635](../.knowledge/cards/20260831-0115-ISS-635.md), [ISS-637](../.knowledge/cards/20260831-0115-ISS-637.md), [ISS-638](../.knowledge/cards/20260831-0115-ISS-638.md) |
| 1 | `backend/tests/agents/test_phase6_frontend_consistency.py` | 2 | [ISS-079](../.knowledge/cards/20260812-0236-ISS-079.md), [ISS-636](../.knowledge/cards/20260831-0115-ISS-636.md) |
| 2 | `backend/agents/workflows/ex_A3_divert/workflow.yaml` | 2 | [ISS-173](../.knowledge/cards/20260825-0955-ISS-173.md), [ISS-174](../.knowledge/cards/20260825-0956-ISS-174.md) |
| 4 | `backend/agents/execution_engine/engine.py` | 8 | [ADR-0002](../.knowledge/cards/20260811-ADR-0002.md), [FIX-BUGFIX-NESTED-REVISION](../.knowledge/cards/20260811-2031-FIX-BUGFIX-NESTED-REVISION.md), [ISS-072](../.knowledge/cards/20260812-0131-ISS-072.md), [ISS-090](../.knowledge/cards/20260812-0632-ISS-090.md), [ISS-094](../.knowledge/cards/20260812-1120-ISS-094.md), [ISS-125](../.knowledge/cards/20260812-1852-ISS-125.md), [ISS-131](../.knowledge/cards/20260812-2116-ISS-131.md), [ISS-402](../.knowledge/cards/20260828-2121-ISS-402.md) |

#### backend · api

29 cards across 4 batch(es).

| round | fix site | cards | members |
|---|---|---|---|
| 1 | **backend · api** | 5 | [ISS-134](../.knowledge/cards/20260812-2140-ISS-134.md), [ISS-182](../.knowledge/cards/20260825-2115-ISS-182.md), [ISS-419](../.knowledge/cards/20260829-0022-ISS-419.md), [ISS-470](../.knowledge/cards/20260828-2310-ISS-470.md), [ISS-471](../.knowledge/cards/20260828-2310-ISS-471.md) |
| 2 | `backend/app/api/run_commands.py` | 17 | [BUG-004-GROUNDED-CONTEXT](../.knowledge/cards/20260716-1231-BUG-004-GROUNDED-CONTEXT.md), [BUG-017-GROUNDED-CONTEXT](../.knowledge/cards/20260717-1336-BUG-017-GROUNDED-CONTEXT.md), [ISS-100](../.knowledge/cards/20260812-1232-ISS-100.md), [ISS-104](../.knowledge/cards/20260812-1312-ISS-104.md), [ISS-119](../.knowledge/cards/20260812-1612-ISS-119.md), [ISS-127](../.knowledge/cards/20260812-2045-ISS-127.md), [ISS-128](../.knowledge/cards/20260812-2046-ISS-128.md), [ISS-133](../.knowledge/cards/20260812-2148-ISS-133.md), [ISS-144](../.knowledge/cards/20260813-0205-ISS-144.md), [ISS-154](../.knowledge/cards/20260813-0819-ISS-154.md), [ISS-161](../.knowledge/cards/20260813-1300-ISS-161.md), [ISS-398](../.knowledge/cards/20260828-2106-ISS-398.md), [ISS-418](../.knowledge/cards/20260828-2231-ISS-418.md), [ISS-422](../.knowledge/cards/20260829-0027-ISS-422.md), [ISS-435](../.knowledge/cards/20260828-2253-ISS-435.md), [ISS-436](../.knowledge/cards/20260828-2253-ISS-436.md), [ISS-437](../.knowledge/cards/20260828-2253-ISS-437.md) |
| 5 | `backend/app/api/user_workflows.py` | 4 | [ISS-180](../.knowledge/cards/20260825-2115-ISS-180.md), [ISS-181](../.knowledge/cards/20260825-2115-ISS-181.md), [ISS-263](../.knowledge/cards/20260828-1811-ISS-263.md), [ISS-381](../.knowledge/cards/20260828-2210-ISS-381.md) |
| 5 | `backend/app/api/run_stream.py` | 3 | [BUG-015-016-GROUNDED-CONTEXT](../.knowledge/cards/20260717-0057-BUG-015-016-GROUNDED-CONTEXT.md), [ISS-105](../.knowledge/cards/20260812-1312-ISS-105.md), [ISS-137](../.knowledge/cards/20260813-0005-ISS-137.md) |

#### frontend · layout

23 cards across 2 batch(es).

| round | fix site | cards | members |
|---|---|---|---|
| 1 | `frontend/src/components/layout/DashboardLayout.tsx` | 22 | [BUG-006-007-GROUNDED-CONTEXT](../.knowledge/cards/20260716-1520-BUG-006-007-GROUNDED-CONTEXT.md), [BUG-008-011-GROUNDED-CONTEXT](../.knowledge/cards/20260716-1636-BUG-008-011-GROUNDED-CONTEXT.md), [BUG-012-FOLLOWUP-LABEL-GROUNDED-CONTEXT](../.knowledge/cards/20260716-2036-BUG-012-FOLLOWUP-LABEL-GROUNDED-CONTEXT.md), [BUG-012-GROUNDED-CONTEXT](../.knowledge/cards/20260716-1725-BUG-012-GROUNDED-CONTEXT.md), [BUG-014-GROUNDED-CONTEXT](../.knowledge/cards/20260716-2156-BUG-014-GROUNDED-CONTEXT.md), [BUG-019-020-GROUNDED-CONTEXT](../.knowledge/cards/20260717-2007-BUG-019-020-GROUNDED-CONTEXT.md), [BUG-DEF-44-12-4-GROUNDED-CONTEXT](../.knowledge/cards/20260716-0952-BUG-DEF-44-12-4-GROUNDED-CONTEXT.md), [ISS-136](../.knowledge/cards/20260813-0005-ISS-136.md), [ISS-252](../.knowledge/cards/20260828-1847-ISS-252.md), [ISS-283](../.knowledge/cards/20260828-1905-ISS-283.md), [ISS-346](../.knowledge/cards/20260828-2058-ISS-346.md), [ISS-347](../.knowledge/cards/20260828-2058-ISS-347.md), [ISS-348](../.knowledge/cards/20260828-2102-ISS-348.md), [ISS-349](../.knowledge/cards/20260828-2102-ISS-349.md), [ISS-371](../.knowledge/cards/20260828-2140-ISS-371.md), [ISS-372](../.knowledge/cards/20260828-2141-ISS-372.md), [ISS-373](../.knowledge/cards/20260828-2142-ISS-373.md), [ISS-432](../.knowledge/cards/20260829-0039-ISS-432.md), [ISS-472](../.knowledge/cards/20260829-0110-ISS-472.md), [ISS-473](../.knowledge/cards/20260829-0111-ISS-473.md), [ISS-474](../.knowledge/cards/20260829-0112-ISS-474.md), [ISS-622](../.knowledge/cards/20260831-0115-ISS-622.md) |
| 2 | **frontend · layout** | 1 | [ISS-143](../.knowledge/cards/20260813-0205-ISS-143.md) |

#### frontend · workflow

22 cards across 3 batch(es).

| round | fix site | cards | members |
|---|---|---|---|
| 2 | `frontend/src/components/workflow/AgentsPopup.tsx` | 3 | [ISS-368](../.knowledge/cards/20260828-1927-ISS-368.md), [ISS-399](../.knowledge/cards/20260828-2308-ISS-399.md), [ISS-491](../.knowledge/cards/20260829-0149-ISS-491.md) |
| 2 | **frontend · workflow** | 3 | [ISS-420](../.knowledge/cards/20260829-0021-ISS-420.md), [ISS-480](../.knowledge/cards/20260828-2320-ISS-480.md), [ISS-603](../.knowledge/cards/20260829-0402-ISS-603.md) |
| 3 | `frontend/src/components/workflow/LaunchWizard.tsx` | 16 | [BUG-048](../.knowledge/cards/20260829-1508-BUG-048.md), [ISS-189](../.knowledge/cards/20260828-1457-ISS-189.md), [ISS-197](../.knowledge/cards/20260828-1559-ISS-197.md), [ISS-217](../.knowledge/cards/20260828-1649-ISS-217.md), [ISS-228](../.knowledge/cards/20260828-1758-ISS-228.md), [ISS-284](../.knowledge/cards/20260828-1906-ISS-284.md), [ISS-361](../.knowledge/cards/20260828-2120-ISS-361.md), [ISS-362](../.knowledge/cards/20260828-2121-ISS-362.md), [ISS-364](../.knowledge/cards/20260828-2130-ISS-364.md), [ISS-365](../.knowledge/cards/20260828-2131-ISS-365.md), [ISS-366](../.knowledge/cards/20260828-2132-ISS-366.md), [ISS-377](../.knowledge/cards/20260828-2202-ISS-377.md), [ISS-384](../.knowledge/cards/20260828-2221-ISS-384.md), [ISS-421](../.knowledge/cards/20260829-0020-ISS-421.md), [ISS-423](../.knowledge/cards/20260829-0026-ISS-423.md), [ISS-429](../.knowledge/cards/20260829-0022-ISS-429.md) |

#### frontend · unplaced

18 cards across 1 batch(es).

| round | fix site | cards | members |
|---|---|---|---|
| 1 | **frontend · unplaced — fix site not recorded** | 18 | [BUG-009-sse](../.knowledge/cards/20260803-BUG-009-sse.md), [BUG-010-sse](../.knowledge/cards/20260803-BUG-010-sse.md), [BUG-035](../.knowledge/cards/20260829-1508-BUG-035.md), [BUG-074](../.knowledge/cards/20260829-1508-BUG-074.md), [BUG-104](../.knowledge/cards/20260829-1508-BUG-104.md), [BUG-106](../.knowledge/cards/20260829-1508-BUG-106.md), [BUG-CWF-001-custom-workflow](../.knowledge/cards/20260803-BUG-CWF-001-custom-workflow.md), [BUG-CWF-002-custom-workflow](../.knowledge/cards/20260803-BUG-CWF-002-custom-workflow.md), [ISS-018](../.knowledge/cards/20260614-0619-ISS-018.md), [ISS-071](../.knowledge/cards/20260812-0107-ISS-071.md), [ISS-107](../.knowledge/cards/20260812-1400-ISS-107.md), [ISS-122](../.knowledge/cards/20260812-1804-ISS-122.md), [ISS-129](../.knowledge/cards/20260812-2116-ISS-129.md), [ISS-135](../.knowledge/cards/20260813-0005-ISS-135.md), [ISS-159](../.knowledge/cards/20260813-1300-ISS-159.md), [ISS-160](../.knowledge/cards/20260813-1300-ISS-160.md), [ISS-179](../.knowledge/cards/20260825-1600-ISS-179.md), [ISS-186](../.knowledge/cards/20260826-0124-ISS-186.md) |

#### frontend · hooks

16 cards across 2 batch(es).

| round | fix site | cards | members |
|---|---|---|---|
| 3 | `frontend/src/hooks/useWorkflow.ts` | 12 | [BUG-014-B-GROUNDED-CONTEXT](../.knowledge/cards/20260716-2339-BUG-014-B-GROUNDED-CONTEXT.md), [FIX-BUGFIX-SPEC-REVISION-CONTEXT](../.knowledge/cards/20260811-1630-FIX-BUGFIX-SPEC-REVISION-CONTEXT.md), [ISS-108](../.knowledge/cards/20260812-1400-ISS-108.md), [ISS-109](../.knowledge/cards/20260812-1400-ISS-109.md), [ISS-110](../.knowledge/cards/20260812-1400-ISS-110.md), [ISS-115](../.knowledge/cards/20260812-1511-ISS-115.md), [ISS-116](../.knowledge/cards/20260812-1511-ISS-116.md), [ISS-142](../.knowledge/cards/20260813-0005-ISS-142.md), [ISS-417](../.knowledge/cards/20260828-2230-ISS-417.md), [ISS-438](../.knowledge/cards/20260829-0056-ISS-438.md), [ISS-439](../.knowledge/cards/20260829-0057-ISS-439.md), [ISS-440](../.knowledge/cards/20260829-0058-ISS-440.md) |
| 6 | `frontend/src/hooks/useRunChat.ts` | 4 | [BUG-018-GROUNDED-CONTEXT](../.knowledge/cards/20260717-1903-BUG-018-GROUNDED-CONTEXT.md), [BUG-021-GROUNDED-CONTEXT](../.knowledge/cards/20260717-2113-BUG-021-GROUNDED-CONTEXT.md), [ISS-111](../.knowledge/cards/20260812-1444-ISS-111.md), [ISS-141](../.knowledge/cards/20260813-0005-ISS-141.md) |

#### frontend · composer

14 cards across 2 batch(es).

| round | fix site | cards | members |
|---|---|---|---|
| 4 | `frontend/src/components/workflow/composer/ComposerPage.tsx` | 11 | [ISS-183](../.knowledge/cards/20260825-2115-ISS-183.md), [ISS-192](../.knowledge/cards/20260828-1345-ISS-192.md), [ISS-223](../.knowledge/cards/20260828-1735-ISS-223.md), [ISS-333](../.knowledge/cards/20260828-2044-ISS-333.md), [ISS-334](../.knowledge/cards/20260828-2045-ISS-334.md), [ISS-340](../.knowledge/cards/20260828-1856-ISS-340.md), [ISS-353](../.knowledge/cards/20260828-2102-ISS-353.md), [ISS-393](../.knowledge/cards/20260828-2251-ISS-393.md), [ISS-410](../.knowledge/cards/20260828-2344-ISS-410.md), [ISS-431](../.knowledge/cards/20260829-0038-ISS-431.md), [ISS-604](../.knowledge/cards/20260829-0207-ISS-604.md) |
| 4 | **frontend · composer** | 3 | [ISS-178](../.knowledge/cards/20260825-1131-ISS-178.md), [ISS-382](../.knowledge/cards/20260828-2008-ISS-382.md), [ISS-489](../.knowledge/cards/20260829-0150-ISS-489.md) |

#### frontend · history

13 cards across 1 batch(es).

| round | fix site | cards | members |
|---|---|---|---|
| 3 | `frontend/src/components/history/WorkflowHistory.tsx` | 13 | [ISS-077](../.knowledge/cards/20260812-0212-ISS-077.md), [ISS-113](../.knowledge/cards/20260812-1444-ISS-113.md), [ISS-145](../.knowledge/cards/20260813-0205-ISS-145.md), [ISS-198](../.knowledge/cards/20260828-1400-ISS-198.md), [ISS-207](../.knowledge/cards/20260828-1617-ISS-207.md), [ISS-208](../.knowledge/cards/20260828-1617-ISS-208.md), [ISS-209](../.knowledge/cards/20260828-1617-ISS-209.md), [ISS-213](../.knowledge/cards/20260828-1618-ISS-213.md), [ISS-219](../.knowledge/cards/20260828-1706-ISS-219.md), [ISS-325](../.knowledge/cards/20260828-2014-ISS-325.md), [ISS-412](../.knowledge/cards/20260828-2343-ISS-412.md), [ISS-414](../.knowledge/cards/20260828-2202-ISS-414.md), [ISS-629](../.knowledge/cards/20260831-0115-ISS-629.md) |

#### frontend · routes

13 cards across 5 batch(es).

| round | fix site | cards | members |
|---|---|---|---|
| 1 | `frontend/src/app/login/page.tsx` | 3 | [ISS-342](../.knowledge/cards/20260828-2059-ISS-342.md), [ISS-352](../.knowledge/cards/20260828-2101-ISS-352.md), [ISS-602](../.knowledge/cards/20260829-0353-ISS-602.md) |
| 1 | `frontend/src/app/workflow/page.tsx` | 2 | [ISS-492](../.knowledge/cards/20260829-0150-ISS-492.md), [ISS-579](../.knowledge/cards/20260829-0234-ISS-579.md) |
| 2 | `frontend/src/app/[...view]/page.tsx` | 3 | [ISS-195](../.knowledge/cards/20260828-1558-ISS-195.md), [ISS-350](../.knowledge/cards/20260828-2102-ISS-350.md), [ISS-624](../.knowledge/cards/20260831-0115-ISS-624.md) |
| 2 | **frontend · routes** | 3 | [ISS-376](../.knowledge/cards/20260828-2152-ISS-376.md), [ISS-407](../.knowledge/cards/20260828-2343-ISS-407.md), [ISS-442](../.knowledge/cards/20260829-0106-ISS-442.md) |
| 2 | `frontend/src/app/admin/page.tsx` | 2 | [ISS-405](../.knowledge/cards/20260828-2324-ISS-405.md), [ISS-415](../.knowledge/cards/20260828-2202-ISS-415.md) |

#### frontend · library

11 cards across 2 batch(es).

| round | fix site | cards | members |
|---|---|---|---|
| 1 | `frontend/src/components/library/LibraryPage.tsx` | 10 | [BUG-073](../.knowledge/cards/20260829-1508-BUG-073.md), [BUG-095](../.knowledge/cards/20260829-1508-BUG-095.md), [ISS-318](../.knowledge/cards/20260828-1956-ISS-318.md), [ISS-330](../.knowledge/cards/20260828-2041-ISS-330.md), [ISS-335](../.knowledge/cards/20260828-2040-ISS-335.md), [ISS-336](../.knowledge/cards/20260828-1846-ISS-336.md), [ISS-378](../.knowledge/cards/20260828-2006-ISS-378.md), [ISS-392](../.knowledge/cards/20260828-2250-ISS-392.md), [ISS-441](../.knowledge/cards/20260828-2257-ISS-441.md), [ISS-591](../.knowledge/cards/20260829-0114-ISS-591.md) |
| 1 | **frontend · library** | 1 | [ISS-605](../.knowledge/cards/20260829-0216-ISS-605.md) |

#### frontend · components

10 cards across 3 batch(es).

| round | fix site | cards | members |
|---|---|---|---|
| 1 | `frontend/src/components/handoff/IntegrationsCard.tsx` | 2 | [ISS-409](../.knowledge/cards/20260828-2148-ISS-409.md), [ISS-481](../.knowledge/cards/20260828-2321-ISS-481.md) |
| 2 | **frontend · components** | 6 | [ISS-073](../.knowledge/cards/20260812-0138-ISS-073.md), [ISS-112](../.knowledge/cards/20260812-1444-ISS-112.md), [ISS-114](../.knowledge/cards/20260812-1444-ISS-114.md), [ISS-216](../.knowledge/cards/20260828-1643-ISS-216.md), [ISS-434](../.knowledge/cards/20260828-2240-ISS-434.md), [ISS-600](../.knowledge/cards/20260829-0341-ISS-600.md) |
| 4 | `frontend/src/components/results/AgentDetailPanel.tsx` | 2 | [ISS-117](../.knowledge/cards/20260812-1511-ISS-117.md), [ISS-387](../.knowledge/cards/20260828-2228-ISS-387.md) |

#### frontend · preview

7 cards across 2 batch(es).

| round | fix site | cards | members |
|---|---|---|---|
| 1 | **frontend · preview** | 2 | [ISS-433](../.knowledge/cards/20260829-0040-ISS-433.md), [ISS-596](../.knowledge/cards/20260829-0127-ISS-596.md) |
| 5 | `frontend/src/components/preview/PreviewPanel.tsx` | 5 | [ISS-251](../.knowledge/cards/20260828-1846-ISS-251.md), [ISS-388](../.knowledge/cards/20260828-2234-ISS-388.md), [ISS-389](../.knowledge/cards/20260828-2234-ISS-389.md), [ISS-599](../.knowledge/cards/20260829-0340-ISS-599.md), [ISS-609](../.knowledge/cards/20260829-1420-ISS-609.md) |

#### tests · integration

5 cards across 2 batch(es).

| round | fix site | cards | members |
|---|---|---|---|
| 1 | **tests · integration** | 2 | [ISS-625](../.knowledge/cards/20260831-0115-ISS-625.md), [ISS-627](../.knowledge/cards/20260831-0115-ISS-627.md) |
| 2 | `tests/integration/e2e/suites/04_composer_canvas/test_composer_canvas.py` | 3 | [ISS-623](../.knowledge/cards/20260831-0115-ISS-623.md), [ISS-626](../.knowledge/cards/20260831-0115-ISS-626.md), [ISS-628](../.knowledge/cards/20260831-0115-ISS-628.md) |

#### frontend · settings

4 cards across 2 batch(es).

| round | fix site | cards | members |
|---|---|---|---|
| 1 | **frontend · settings** | 1 | [ISS-354](../.knowledge/cards/20260828-2103-ISS-354.md) |
| 2 | `frontend/src/components/settings/AccountSettings.tsx` | 3 | [ISS-430](../.knowledge/cards/20260829-0029-ISS-430.md), [ISS-482](../.knowledge/cards/20260828-2322-ISS-482.md), [ISS-581](../.knowledge/cards/20260829-0241-ISS-581.md) |

#### frontend · lib

4 cards across 2 batch(es).

| round | fix site | cards | members |
|---|---|---|---|
| 3 | **frontend · lib** | 1 | [ISS-386](../.knowledge/cards/20260828-2228-ISS-386.md) |
| 4 | `frontend/src/lib/api.ts` | 3 | [BUG-013-GROUNDED-CONTEXT](../.knowledge/cards/20260716-1935-BUG-013-GROUNDED-CONTEXT.md), [ISS-413](../.knowledge/cards/20260828-2357-ISS-413.md), [ISS-486](../.knowledge/cards/20260828-2335-ISS-486.md) |

#### backend · unplaced

3 cards across 1 batch(es).

| round | fix site | cards | members |
|---|---|---|---|
| 1 | **backend · unplaced — fix site not recorded** | 3 | [BUG-036](../.knowledge/cards/20260829-1508-BUG-036.md), [BUG-037](../.knowledge/cards/20260829-1508-BUG-037.md), [ISS-020](../.knowledge/cards/20260614-0619-ISS-020.md) |

#### docs · planning

2 cards across 1 batch(es).

| round | fix site | cards | members |
|---|---|---|---|
| 1 | **docs · planning** | 2 | [ISS-076](../.knowledge/cards/20260812-0212-ISS-076.md), [ISS-095](../.knowledge/cards/20260812-1120-ISS-095.md) |

#### backend · engine

1 cards across 1 batch(es).

| round | fix site | cards | members |
|---|---|---|---|
| 1 | **backend · engine** | 1 | [ISS-187](../.knowledge/cards/20260826-1547-ISS-187.md) |

#### unclassified

1 cards across 1 batch(es).

| round | fix site | cards | members |
|---|---|---|---|
| 1 | **unclassified** | 1 | [BUG-031](../.knowledge/cards/20260827-BUG-031.md) |

## Tier C — no kin found

154 cards with no declared sibling and no same-file/same-class neighbour.
Each is its own unit of work.

| card | fix site | summary |
|---|---|---|
| [ADR-0002](../.knowledge/cards/20260811-ADR-0002.md) | `backend/CLAUDE.md`, `backend/agents/execution_engine/engine.py`, `backend/agents/loader.py`, `backend/agents/registry.py` | That `workflow` is the only vocabulary the system knows and `pipeline` is removed rather than deprecated, to achieve on… |
| [BUG-004-GROUNDED-CONTEXT](../.knowledge/cards/20260716-1231-BUG-004-GROUNDED-CONTEXT.md) | `.planning/SSE-QA-BUG-LOG.md`, `backend/agents/authz.py`, `backend/app/api/prototype_templates.py`, `backend/app/api/run_commands.py`, `backend/app/api/run_engine.py`, `backend/app/api/run_stream.py`, `backend/app/api/runs.py`, `backend/app/models/database.py`, `backend/tests/agents/test_wire_parity.py` | FastAPI tears down Depends(get_db) before the SSE generator body runs, so read_events opens a fresh pooled connection p… |
| [BUG-009-sse](../.knowledge/cards/20260803-BUG-009-sse.md) | — | od_ppt's deliverable resolver reads only the last agent's live stream, so a non-compliant validator re-emit discards an… |
| [BUG-010-sse](../.knowledge/cards/20260803-BUG-010-sse.md) | — | Investigated as a false alarm: `activePipelineRunId` is null while a run is actively building, so `trackedRunIdRef` res… |
| [BUG-013-GROUNDED-CONTEXT](../.knowledge/cards/20260716-1935-BUG-013-GROUNDED-CONTEXT.md) | `frontend/src/lib/api.ts`, `frontend/src/providers/RunConnectionProvider.tsx` | One EventSource per non-terminal run saturates the browser's ~6-connection-per-origin limit, hanging fetches; fix stops… |
| [BUG-014-B-GROUNDED-CONTEXT](../.knowledge/cards/20260716-2339-BUG-014-B-GROUNDED-CONTEXT.md) | `backend/app/api/run_stream.py`, `frontend/e2e/fixtures/mockSse.ts`, `frontend/src/hooks/useRunStream.ts`, `frontend/src/hooks/useWorkflow.ts`, `frontend/src/providers/RunConnectionProvider.tsx` | sse-starlette emits CRLF frame boundaries but useRunStream splits on LF-LF, so zero live SSE frames were parsed; fixed … |
| [BUG-015-016-GROUNDED-CONTEXT](../.knowledge/cards/20260717-0057-BUG-015-016-GROUNDED-CONTEXT.md) | `backend/app/api/run_stream.py`, `frontend/src/hooks/useRunStream.ts`, `frontend/src/providers/RunConnectionProvider.tsx` | BUG-015: a completed but focused run reconnects forever since useRunStream ignores prior stream_attached{live:false}; B… |
| [BUG-017-GROUNDED-CONTEXT](../.knowledge/cards/20260717-1336-BUG-017-GROUNDED-CONTEXT.md) | `backend/app/agents/chat/concierge.py`, `backend/app/api/run_commands.py`, `frontend/src/hooks/useRunChat.test.ts`, `frontend/src/hooks/useRunChat.ts`, `frontend/src/providers/RunConnectionProvider.tsx` | page.tsx voided the sendCommand promise so the re-fetch raced ahead of the persisted chat_reply; awaiting it fixed deli… |
| [BUG-018-GROUNDED-CONTEXT](../.knowledge/cards/20260717-1903-BUG-018-GROUNDED-CONTEXT.md) | `frontend/src/components/chat/ArtifactCard.tsx`, `frontend/src/components/chat/ChatPanel.tsx`, `frontend/src/components/chat/RunChatLane.tsx`, `frontend/src/hooks/useRunChat.test.ts`, `frontend/src/hooks/useRunChat.ts`, `frontend/src/lib/api.ts` | getRunEvents dropped row.event_id so replies collided with the user turn's message_id and overwrote it; merging event_i… |
| [BUG-019-020-GROUNDED-CONTEXT](../.knowledge/cards/20260717-2007-BUG-019-020-GROUNDED-CONTEXT.md) | `frontend/src/components/chat/LaneRunHeader.test.tsx`, `frontend/src/components/chat/LaneRunHeader.tsx`, `frontend/src/components/chat/RunChatLane.tsx`, `frontend/src/components/layout/DashboardLayout.laneTitle.test.tsx`, `frontend/src/components/layout/DashboardLayout.tsx` | recentRuns?.[0] leaked the previous run's title/type into a fresh launch header; fixed by falling back to undefined and… |
| [BUG-021-GROUNDED-CONTEXT](../.knowledge/cards/20260717-2113-BUG-021-GROUNDED-CONTEXT.md) | `frontend/src/hooks/useRunChat.ts` | useRunChat.messages was never cleared on a fresh non-revision launch, so the prior run's transcript bled through until … |
| [BUG-031](../.knowledge/cards/20260827-BUG-031.md) | `.pre-commit-config.yaml`, `tools/knowledge/rebuild_knowledge.py` | A commit ran the knowledge hook, which rebuilt .knowledge/ over the files pre-commit had stashed; the unstash then fail… |
| [BUG-035](../.knowledge/cards/20260829-1508-BUG-035.md) | — | Landing on `/create/prototype` normally, then pressing the browser **Back** button (returns to `/dashboard`), then pres… |
| [BUG-036](../.knowledge/cards/20260829-1508-BUG-036.md) | — | The `ppt` built-in workflow's real manifest (`GET /api/workflows/ppt`) defines a specialized deliverable — `{"strategy"… |
| [BUG-037](../.knowledge/cards/20260829-1508-BUG-037.md) | — | The Run History page always requests `GET /api/runs?limit=50` and never issues a follow-up request with a higher `limit… |
| [BUG-048](../.knowledge/cards/20260829-1508-BUG-048.md) | `frontend/src/components/workflow/LaunchWizard.tsx` | A saved workflow's launch panel loses its override entirely and renders the generic base-type wizard, even though the o… |
| [BUG-074](../.knowledge/cards/20260829-1508-BUG-074.md) | — | Single-word skill IDs render correctly but reported as falling back to library listing (unreproducible). |
| [BUG-104](../.knowledge/cards/20260829-1508-BUG-104.md) | — | Escape key does not close "Workflow actions" dropdown menu on saved-workflow cards |
| [BUG-106](../.knowledge/cards/20260829-1508-BUG-106.md) | — | Run Workflow button enables with zero agents and silently no-ops on click |
| [BUG-CWF-001-custom-workflow](../.knowledge/cards/20260803-BUG-CWF-001-custom-workflow.md) | — | Composer let a consumer be ordered before its producer while execution ran topo order, so the resulting failure mislabe… |
| [BUG-CWF-002-custom-workflow](../.knowledge/cards/20260803-BUG-CWF-002-custom-workflow.md) | — | The resolved per-agent model was never emitted or persisted, so cost was always priced against the default profile; fix… |
| [BUG-DEF-44-12-4-GROUNDED-CONTEXT](../.knowledge/cards/20260716-0952-BUG-DEF-44-12-4-GROUNDED-CONTEXT.md) | `backend/agents/authz.py`, `backend/agents/execution_engine/engine.py`, `backend/app/api/run_commands.py`, `backend/app/api/run_stream.py`, `backend/app/api/runs.py`, `frontend/e2e/fixtures/dashboard.ts`, `frontend/e2e/tests/ts-t.history.spec.ts`, `frontend/e2e/tests/ts-u.revisions.spec.ts`, `frontend/src/components/layout/DashboardLayout.tsx`, `frontend/src/components/results/AgentThinkingTab.tsx`, `frontend/src/hooks/useRunChat.test.ts`, `frontend/src/hooks/useRunChat.ts`, `frontend/src/hooks/useRunStream.ts`, `frontend/src/hooks/useWorkflow.ts`, `frontend/src/lib/api.ts`, `frontend/src/lib/wsReplayState.ts`, `frontend/src/providers/RunConnectionProvider.tsx` | Opened-from-history runs show an empty Steps trace and non-rendering Concierge reply because the reducer only seeds age… |
| [FIX-BUGFIX-SPEC-REVISION-CONTEXT](../.knowledge/cards/20260811-1630-FIX-BUGFIX-SPEC-REVISION-CONTEXT.md) | `backend/agents/authz.py`, `backend/agents/capabilities/strategies/task_loop.py`, `backend/agents/execution_engine/clarify_engine.py`, `backend/agents/execution_engine/engine.py`, `backend/agents/execution_engine/kernel_services.py`, `backend/agents/factory.py`, `backend/agents/prompts/prototype-specify/AGENT.md`, `backend/app/agents/chat/concierge.py`, `backend/app/agents/deep_agent_runner.py`, `backend/tests/agents/_scripted_model.py`, `backend/tests/agents/test_restart_resume.py`, `frontend/src/hooks/useWorkflow.ts` | Diagnosed: update_specs never injects the prior spec into the revision prompt, and a resumed run rebuilds planning_cont… |
| [ISS-018](../.knowledge/cards/20260614-0619-ISS-018.md) | — | The hexaware-srini AWS profile lost Bedrock ConverseStream entitlement mid-session (not quota or expiry); campaign swit… |
| [ISS-020](../.knowledge/cards/20260614-0619-ISS-020.md) | — | The rewrite harness only changes the backend pipeline_type, not the FE's displayed workflow labels, for fixture scenari… |
| [ISS-071](../.knowledge/cards/20260812-0107-ISS-071.md) | — | The artifact-kind fallback maps any agent outside a 4-agent prototype list to 'summary', so every non-prototype workflo… |
| [ISS-072](../.knowledge/cards/20260812-0131-ISS-072.md) | `backend/agents/execution_engine/engine.py`, `backend/tests/agents/test_spec_revision_cycles.py` | One 'Update the Specs' click still costs four approvals because the redundant in-pass analyze gate firing was identifie… |
| [ISS-073](../.knowledge/cards/20260812-0138-ISS-073.md) | `frontend/src/components/chat/InlineGateActions.test.tsx`, `frontend/src/components/chat/InlineGateActions.tsx` | InlineGateActions.test.tsx still asserts the update-specs button is hidden pre-click, but the component deliberately el… |
| [ISS-076](../.knowledge/cards/20260812-0212-ISS-076.md) | `.planning/TEST-REGISTER.md`, `frontend/playwright.config.ts` | TEST-REGISTER's '123-132 green' Playwright figure is stale feat/ui-2 data; the real baseline on this branch is 33 faile… |
| [ISS-077](../.knowledge/cards/20260812-0212-ISS-077.md) | `backend/app/api/runs.py`, `frontend/src/components/history/WorkflowHistory.tsx`, `frontend/src/lib/api.ts` | api.ts declares derived_from/children as string arrays but the backend returns a nullable string and nested ArtifactNod… |
| [ISS-079](../.knowledge/cards/20260812-0236-ISS-079.md) | `backend/tests/agents/test_phase6_frontend_consistency.py` | A stale test hardcodes the pre-analyze 4-agent prototype id set after commit 5c947270 added prototype-analyze, making t… |
| [ISS-090](../.knowledge/cards/20260812-0632-ISS-090.md) | `backend/agents/execution_engine/engine.py` | Unlike update_specs_eligible, redoable=True is a hardcoded literal at all three gate sites, so any gated agent gets a R… |
| [ISS-094](../.knowledge/cards/20260812-1120-ISS-094.md) | `backend/agents/execution_engine/engine.py`, `backend/tests/agents/test_gate_stub_signature_drift.py`, `backend/tests/agents/test_gates.py` | Hand-rolled test doubles are missing attributes the engine now reads, a drift class the FIX-231 signature guard cannot … |
| [ISS-095](../.knowledge/cards/20260812-1120-ISS-095.md) | `.planning/IMPLEMENTATION-REGISTER.md`, `backend/tests/agents/test_declared_gate_streaming.py` | Three reds mislabeled as sqlite-FK environmental noise actually assert a declared gate never fired and a rejection didn… |
| [ISS-096](../.knowledge/cards/20260812-1120-ISS-096.md) | `backend/tests/agents/live_harness.py`, `backend/tests/agents/test_live_contract.py`, `backend/tests/agents/test_phase3_token_delta_live.py`, `backend/tests/agents/test_prompt_contracts.py` | A prompt-contract test still asserts a sentence no longer present in the od-ppt-validator prompt; unclear whether the p… |
| [ISS-098](../.knowledge/cards/20260812-1153-ISS-098.md) | `backend/agents/capabilities/strategies/wave_scheduler.py` | wave_scheduler catches except Exception to flip a wave row terminal, but CancelledError inherits BaseException so a can… |
| [ISS-100](../.knowledge/cards/20260812-1232-ISS-100.md) | `backend/app/agents/handoff/coder.py`, `backend/app/agents/handoff/compliance_agent.py`, `backend/app/agents/handoff/test_agent.py`, `backend/app/api/run_commands.py`, `backend/app/api/websocket_handoff.py`, `backend/app/services/handoff_pipeline.py` | Three handoff call sites accept a usage_sink but are never given one, and handoff_sessions has no token column to even … |
| [ISS-101](../.knowledge/cards/20260812-1232-ISS-101.md) | `backend/agents/capabilities/context_providers/conversation.py` | conversation.py calls unbounded read_events then filters in Python to build a 6-turn transcript, now unconditional on e… |
| [ISS-105](../.knowledge/cards/20260812-1312-ISS-105.md) | `backend/app/api/run_stream.py` | uvicorn cancels SSE tasks then calls lifespan.shutdown() without awaiting them, letting shutdown snapshot pipeline queu… |
| [ISS-106](../.knowledge/cards/20260812-1315-ISS-106.md) | `backend/app/agents/checkpointer.py`, `backend/app/api/run_shutdown.py` | close_checkpointer()'s pool.close() has no timeout, so a slow Postgres pool close can push teardown past the SIGKILL de… |
| [ISS-107](../.knowledge/cards/20260812-1400-ISS-107.md) | — | dashboard/page.tsx dispatches the hook_run message but its payload never lands on state, so hookRuns' only consumer is … |
| [ISS-108](../.knowledge/cards/20260812-1400-ISS-108.md) | `frontend/src/hooks/useWorkflow.accumulators.test.ts`, `frontend/src/hooks/useWorkflow.ts` | retainClarifyRound pushes clarification rounds with no identity key and no reset outside startPipeline, risking carryov… |
| [ISS-109](../.knowledge/cards/20260812-1400-ISS-109.md) | `backend/app/api/capabilities.py`, `frontend/src/components/results/AgentDetailPanel.tsx`, `frontend/src/hooks/useWorkflow.ts` | validator_result and gate_passed are never emitted in non-test backend code, so validationIssues may be structurally un… |
| [ISS-110](../.knowledge/cards/20260812-1400-ISS-110.md) | `frontend/src/hooks/useWorkflow.ts` | pipeline_start spreads ...prev without clearing hookRuns, so one run's hook rows can survive into the next run's pipeli… |
| [ISS-111](../.knowledge/cards/20260812-1444-ISS-111.md) | `.planning/IMPLEMENTATION-REGISTER.md`, `backend/app/agents/chat_narrator.py`, `backend/app/api/runs.py`, `backend/tests/unit/test_chat_narrator.py`, `frontend/src/hooks/useRunChat.ts` | chat_narrator's spec_revision branch checks first and outranks every other card kind, yet nothing ever writes the paylo… |
| [ISS-112](../.knowledge/cards/20260812-1444-ISS-112.md) | `frontend/src/components/results/AgentThinkingTab.tsx`, `frontend/src/components/results/StartingPointCard.test.tsx`, `frontend/src/components/results/StartingPointCard.tsx` | The sole production mount of StartingPointCard never passes attachmentRefs, so the 'image not retained' placeholder can… |
| [ISS-113](../.knowledge/cards/20260812-1444-ISS-113.md) | `frontend/src/components/history/WorkflowHistory.tsx`, `frontend/src/components/preview/PreviewPanel.tsx`, `frontend/src/components/results/AuditTab.tsx` | Neither mount of AuditTab passes runMeta, so the audit header's owner and workspace fields are permanently null. |
| [ISS-114](../.knowledge/cards/20260812-1444-ISS-114.md) | `frontend/src/components/chat/ResultCard.test.tsx`, `frontend/src/components/chat/ResultCard.tsx` | KAN-154 moved the deliverable card into an inline-render branch with no title text, so the LOCK-F 'Deliverable' label a… |
| [ISS-115](../.knowledge/cards/20260812-1511-ISS-115.md) | `frontend/src/components/results/AgentThinkingTab.tsx`, `frontend/src/components/results/artifactPreview.tsx`, `frontend/src/hooks/useWorkflow.ts` | useWorkflow.ts keeps its own line-anchored Task-N regex separate from FIX-237's extracted parser, and unifying them isn… |
| [ISS-116](../.knowledge/cards/20260812-1511-ISS-116.md) | `backend/agents/capabilities/gates/write.py`, `backend/app/api/capabilities.py`, `frontend/src/components/results/AgentDetailPanel.tsx`, `frontend/src/hooks/useWorkflow.ts` | gate_passed and validator_result have zero backend producers, so the green 'Passed' chip can never render and the amber… |
| [ISS-117](../.knowledge/cards/20260812-1511-ISS-117.md) | `frontend/src/components/results/AgentDetailPanel.tsx`, `frontend/src/hooks/useRunStateStore.ts` | useRunStateStore's replay allowlist omits validator_result/gate_passed/gate_blocked, so no reopened run can ever show a… |
| [ISS-118](../.knowledge/cards/20260812-1612-ISS-118.md) | `backend/agents/planner/smart_planner.py`, `backend/tests/conftest.py` | Eight offline tests construct a real LLM provider client (five bypassing build_model) but never invoke it, so they're e… |
| [ISS-119](../.knowledge/cards/20260812-1612-ISS-119.md) | `backend/app/api/run_commands.py` | Two tests assert bare text routes to answers/gate channels, but the router now deliberately routes ambiguous text to Co… |
| [ISS-120](../.knowledge/cards/20260812-1637-ISS-120.md) | `backend/agents/capabilities/model_catalog.py`, `backend/app/agents/cached_invoke.py`, `backend/app/agents/deep_agent_runner.py`, `backend/app/core/config.py` | Bedrock prompt caching is one global switch with no per-workflow override; short runs that write cache never re-read pa… |
| [ISS-122](../.knowledge/cards/20260812-1804-ISS-122.md) | — | An unmetered-legacy spend window dilutes the real cache delta below the zero-suppression threshold, so the line renders… |
| [ISS-125](../.knowledge/cards/20260812-1852-ISS-125.md) | `backend/agents/execution_engine/engine.py` | _stamp_resume_marker reads the entire durable log just to compute the next seq and uses a non-retrying append, carrying… |
| [ISS-127](../.knowledge/cards/20260812-2045-ISS-127.md) | `backend/agents/execution_engine/engine.py`, `backend/app/api/run_commands.py`, `backend/app/api/run_engine.py` | GateCommand.analysis_report flows uncapped into the composed spec-revision prompt on every dispatch, a cost-amplificati… |
| [ISS-128](../.knowledge/cards/20260812-2046-ISS-128.md) | `backend/agents/capabilities/gates/human.py`, `backend/agents/execution_engine/engine.py`, `backend/app/api/run_commands.py` | The gate reject branch never passes action= to set_review_response, so the store's default stamps a false 'approve' on … |
| [ISS-129](../.knowledge/cards/20260812-2116-ISS-129.md) | — | fanout.py's worker loop forwards nothing but agent_complete token counts, so a worker's error, cancel or gate-ready eve… |
| [ISS-130](../.knowledge/cards/20260812-2116-ISS-130.md) | `backend/agents/execution_engine/kernel_services.py` | N parallel fan-out workers share one ExecutionContext's scratch fields, an unverified interleaving hazard masked only b… |
| [ISS-134](../.knowledge/cards/20260812-2140-ISS-134.md) | `backend/app/api/run_engine.py` | Cancel liveness is decided from process-local dicts, sound only while single-process; the locked ECS Fargate migration … |
| [ISS-135](../.knowledge/cards/20260813-0005-ISS-135.md) | — | payload_json.seq gets re-stamped after append_event_at_or_after returns, so the payload's seq can lag the row's real se… |
| [ISS-136](../.knowledge/cards/20260813-0005-ISS-136.md) | `backend/app/api/chat_router.py`, `frontend/src/components/layout/DashboardLayout.tsx`, `frontend/src/components/preview/PreviewPanel.tsx`, `frontend/src/hooks/useWorkflow.reconnect.test.ts`, `frontend/src/hooks/useWorkflow.ts` | Four FE terminal-status lists disagree (one is missing 'degraded'); FIX-245 already cut it to one canonical list, remai… |
| [ISS-137](../.knowledge/cards/20260813-0005-ISS-137.md) | `backend/app/api/run_stream.py`, `frontend/src/hooks/useWorkflow.reconnect.test.ts` | pipeline_reconnected is a dead frame — no backend path emits it since stream_attached replaced it — yet a live reducer … |
| [ISS-141](../.knowledge/cards/20260813-0005-ISS-141.md) | `frontend/src/hooks/useRunChat.ts` | Reopened terminal runs still show an actionable clarify chat card, because terminal auto-resolve only covers cardKind==… |
| [ISS-142](../.knowledge/cards/20260813-0005-ISS-142.md) | `.planning/IMPLEMENTATION-REGISTER.md`, `backend/app/api/run_stream.py`, `frontend/src/hooks/useWorkflow.ts` | SSE's stream_attached ack dropped the status field pipeline_reconnected used to carry (D-13); evaluated as an ISS-126 f… |
| [ISS-144](../.knowledge/cards/20260813-0205-ISS-144.md) | `backend/app/api/run_commands.py` | POST /answers has no terminal-run 409 guard unlike /gate, though the needed helper is already imported — a cancelled ru… |
| [ISS-154](../.knowledge/cards/20260813-0819-ISS-154.md) | `backend/app/api/run_commands.py`, `frontend/src/components/preview/PreviewPanel.tsx` | Switching to an older revision whose .output is NULL (a pre-FIX-250 row) shows a blank 'Output will appear here' previe… |
| [ISS-156](../.knowledge/cards/20260813-1300-ISS-156.md) | `backend/tests/unit/test_run_commands_fix218.py`, `frontend/src/hooks/useChatAttachments.test.ts` | dev merged FIX-218 with 5 red tests: 2 assert a prompt string dev's code no longer emits, 2 more in useChatAttachments;… |
| [ISS-159](../.knowledge/cards/20260813-1300-ISS-159.md) | — | Chained runs record no lineage — chaining inlines the parent's context into the child's input text, but neither parent_… |
| [ISS-160](../.knowledge/cards/20260813-1300-ISS-160.md) | — | The Concierge is unreachable on a revision run — it returns pipeline_not_entitled while the identical question on the p… |
| [ISS-161](../.knowledge/cards/20260813-1300-ISS-161.md) | `backend/app/api/run_commands.py` | A pure question posted to a parent run over REST /messages was misclassified as a revision and minted a new run, which … |
| [ISS-173](../.knowledge/cards/20260825-0955-ISS-173.md) | `backend/agents/workflows/ex_A3_divert/workflow.yaml`, `backend/agents/workflows/ex_A4_human_gate/workflow.yaml`, `backend/tests/agents/test_conditional_divert_v4_validation.py`, `backend/tests/agents/test_conditional_human_gate_source_t26.py` | c9ec0149c renamed sample_conditional_* to ex_A*; two test files kept the old step ids (decide, revise-check) and target… |
| [ISS-174](../.knowledge/cards/20260825-0956-ISS-174.md) | `backend/agents/workflows/ex_A1_loop/workflow.yaml`, `backend/agents/workflows/ex_A2_branch/workflow.yaml`, `backend/agents/workflows/ex_A3_divert/workflow.yaml`, `backend/agents/workflows/ex_A4_human_gate/workflow.yaml`, `backend/tests/agents/test_id_alias_resolver.py`, `backend/tests/agents/test_manifest_parity.py` | ex_A* declare planner: skip and empty clarify.defaults; test_planner_run_everywhere and test_clarify_defaults_match_eng… |
| [ISS-178](../.knowledge/cards/20260825-1131-ISS-178.md) | `frontend/src/components/workflow/composer/graphLayout.ts` | computeRootLayout derives edges from array adjacency plus route outcomes only, so a step whose sole real predecessor is… |
| [ISS-179](../.knowledge/cards/20260825-1600-ISS-179.md) | — | 215b911e0 "removed screenshots" deleted 56 files including README.md, README.txt, docker-compose.yml, docker-compose.pr… |
| [ISS-180](../.knowledge/cards/20260825-2115-ISS-180.md) | `backend/app/api/user_workflows.py`, `backend/app/models/workflow_definition.py` | Migration 0039 stores the base manifest version at save time, but nothing compares it — an override keeps running its o… |
| [ISS-181](../.knowledge/cards/20260825-2115-ISS-181.md) | `backend/agents/execution_engine/overrides.py`, `backend/app/api/composition_order.py`, `backend/app/api/user_workflows.py` | An override can be saved, shown, and still be unlaunchable: the compiler accepts steps that presort_specs' produces/con… |
| [ISS-182](../.knowledge/cards/20260825-2115-ISS-182.md) | `backend/app/api/_workflow_override.py` | The UI no longer offers the blank template, but rows already storing custom-agent:<id> are untouched and keep failing a… |
| [ISS-183](../.knowledge/cards/20260825-2115-ISS-183.md) | `frontend/src/components/workflow/composer/ComposerPage.tsx` | The hardcode is deliberate — workflowType is a shared mutable other screens set — but it means the full canvas cannot a… |
| [ISS-185](../.knowledge/cards/20260825-2115-ISS-185.md) | `backend/agents/workflows/ppt/workflow.yaml`, `backend/app/agents/skill_staging.py` | The composer hunts for template files at the skill mount point while the real files sit at /references/, burning turns;… |
| [ISS-186](../.knowledge/cards/20260826-0124-ISS-186.md) | — | Commit 215b911e0 deleted docker-compose.yml, docker-compose.prod.yml, README.md and app.env.example alongside the scree… |
| [ISS-187](../.knowledge/cards/20260826-1547-ISS-187.md) | `backend/app/core/entitlements.py`, `frontend/src/lib/entitlements.ts` | All 7 spec-014 ex_A* gate fixtures declare user_launchable: true and sit in the enterprise tier on both sides, so QA fi… |
| [ISS-189](../.knowledge/cards/20260828-1457-ISS-189.md) | `frontend/src/components/workflow/LaunchWizard.tsx` | Investment Banking Pitch Book template shows "Pick a design system" pill with no picker UI; PPT mode never sets selecte… |
| [ISS-192](../.knowledge/cards/20260828-1345-ISS-192.md) | `frontend/src/components/workflow/composer/ComposerPage.tsx` | needsFullManifest(pipelineAgents) is false for an unmodified built-in copy, so ComposerPage.tsx:628-629 sends no manife… |
| [ISS-198](../.knowledge/cards/20260828-1400-ISS-198.md) | `frontend/src/components/history/WorkflowHistory.tsx` | Run History renders the capped runs.length (50) instead of the totalRuns it already holds; handleLoadMore never fires, … |
| [ISS-207](../.knowledge/cards/20260828-1617-ISS-207.md) | `frontend/src/components/history/WorkflowHistory.tsx` | matchesFilter (~L430) runs client-side over runs/families, which never exceeds the fetched 50 — a search for an older r… |
| [ISS-208](../.knowledge/cards/20260828-1617-ISS-208.md) | `frontend/src/components/history/RevisionFamilyView.tsx`, `frontend/src/components/history/WorkflowHistory.tsx` | bucketAndSortFamilies (~L950) sorts visibleFamilies, itself derived from the capped runs array — Longest/Tokens sort si… |
| [ISS-213](../.knowledge/cards/20260828-1618-ISS-213.md) | `frontend/src/components/history/RevisionFamilyView.tsx`, `frontend/src/components/history/WorkflowHistory.tsx` | typeCounts (~L952-958) tallies every filter chip from the same capped families array; a type with zero hits in the load… |
| [ISS-216](../.knowledge/cards/20260828-1643-ISS-216.md) | `frontend/src/components/catalog/HomeLaunchGrid.crossAccountLeak.test.tsx`, `frontend/src/store/listenerMiddleware.test.ts` | The only six `tsc --noEmit` errors in frontend/ outside .next/ are in these two files: five arity errors on the mocked … |
| [ISS-217](../.knowledge/cards/20260828-1649-ISS-217.md) | `frontend/src/app/[...view]/page.tsx`, `frontend/src/app/handoff/settings/page.tsx`, `frontend/src/app/login/page.tsx`, `frontend/src/components/workflow/LaunchWizard.tsx` | Measured: React never hydrates on a transferSize:0 back_forward replay, so page.tsx:3701's mount-once gate is not the c… |
| [ISS-219](../.knowledge/cards/20260828-1706-ISS-219.md) | `frontend/src/components/history/RevisionFamilyView.tsx`, `frontend/src/components/history/WorkflowHistory.tsx`, `tests/integration/e2e/suites/06_run_history/test_run_history.py`, `tests/integration/e2e/suites/06_run_history/test_run_history_pagination.py`, `tests/integration/screens/06-run-history.feature.md` | qa-admin holds 275 runs but only 232 family cards, so "All chip == header" (S-06-04) and "rows == chip" (S-06-05) canno… |
| [ISS-223](../.knowledge/cards/20260828-1735-ISS-223.md) | `backend/agents/capabilities/deliverables/ppt.py`, `backend/agents/workflows/compiler.py`, `backend/app/api/user_workflows.py`, `frontend/src/components/workflow/composer/ComposerPage.tsx` | `deliverable/ppt` is registered without user_allowed, so `_validated_manifest` compiles at trust="db" and 422s any save… |
| [ISS-251](../.knowledge/cards/20260828-1846-ISS-251.md) | `frontend/src/components/preview/PreviewPanel.tsx`, `frontend/src/lib/api.ts` | PreviewPanel.tsx:844-910 duplicates the declared-name + listing + extension-keyed sibling rule now exported as resolveR… |
| [ISS-252](../.knowledge/cards/20260828-1847-ISS-252.md) | `frontend/src/components/layout/DashboardLayout.tsx` | DashboardLayout.tsx:2347 and :2160 test effectiveReviseType against "ppt"/"ppt_revision" only, so a ppt_v2 run reads us… |
| [ISS-325](../.knowledge/cards/20260828-2014-ISS-325.md) | `frontend/src/components/history/WorkflowHistory.tsx`, `tests/integration/e2e/suites/21_run_families_and_versions/test_run_families_and_versions.py` | RH.chip_count times out on `^Presentation\s*\d` at /runs; the test asserts named == rows == All, an equality its docstr… |
| [ISS-330](../.knowledge/cards/20260828-2041-ISS-330.md) | `frontend/src/components/library/LibraryPage.tsx`, `frontend/src/store/slices/agentsSlice.ts` | agentsStatus/skillsStatus/hooksStatus only branch on "loading" (LibraryPage.tsx:732,793,815,893,911); "failed" falls th… |
| [ISS-333](../.knowledge/cards/20260828-2044-ISS-333.md) | `frontend/src/components/home/CreationHub.tsx`, `frontend/src/components/workflow/composer/CanvasView.tsx`, `frontend/src/components/workflow/composer/ComposerPage.tsx` | ComposerPage.handleRunOnce (ComposerPage.tsx:939) has no pipelineAgents.length===0 guard -- a fresh custom canvas start… |
| [ISS-334](../.knowledge/cards/20260828-2045-ISS-334.md) | `frontend/src/app/[...view]/page.tsx`, `frontend/src/components/workflow/composer/ComposerPage.tsx` | page.tsx:494-496 catches ANY getWorkflowDetail failure, not just 404, so a transient error on a REAL workflow id reache… |
| [ISS-335](../.knowledge/cards/20260828-2040-ISS-335.md) | `frontend/src/components/library/LibraryPage.tsx` | Same missing length===0 branch (LibraryPage.tsx:735/818/914) reachable via activeCategory/skillCategory/hookEvent alone… |
| [ISS-340](../.knowledge/cards/20260828-1856-ISS-340.md) | `frontend/src/components/workflow/composer/CanvasView.tsx`, `frontend/src/components/workflow/composer/ComposerPage.tsx`, `frontend/src/components/workflow/composer/IdentityCard.tsx` | PPT deliverable type: Simple hardcodes "Custom" (ComposerPage.tsx:478); Canvas derives it from runConfig (CanvasView.ts… |
| [ISS-346](../.knowledge/cards/20260828-2058-ISS-346.md) | `backend/app/api/runs.py`, `frontend/src/components/layout/DashboardLayout.tsx`, `frontend/src/lib/api.ts` | The list endpoint drops `input`, so normalizeWorkflowRun sets it undefined and `viewedRun?.input \|\| submittedBrief` a… |
| [ISS-357](../.knowledge/cards/20260828-1915-ISS-357.md) | `backend/tests/unit/test_register_password_echo.py` | The fixture builds its own FastAPI() and includes only auth_router, so app.main's RequestValidationError handler never … |
| [ISS-362](../.knowledge/cards/20260828-2121-ISS-362.md) | `frontend/src/components/workflow/IdeaInputPage.tsx`, `frontend/src/components/workflow/LaunchWizard.tsx`, `frontend/src/components/workflow/ReviewGatesSection.tsx`, `frontend/src/components/workflow/composer/CanvasConfigRail.tsx` | INFERRED inverse of ISS-247: CanvasConfigRail.tsx:354-357 patch()/selectGate only calls onSelection(agent.id, next) on … |
| [ISS-373](../.knowledge/cards/20260828-2142-ISS-373.md) | `frontend/src/components/layout/DashboardLayout.tsx`, `frontend/src/components/workflow/composer/ComposerPage.tsx` | Same ComposerPage.tsx:979 onClick={onBack}/handleBackNav gap also fires on /workflows/{id}/edit, discarding edits to an… |
| [ISS-376](../.knowledge/cards/20260828-2152-ISS-376.md) | `frontend/src/app/workflow/create/page.tsx`, `frontend/src/proxy.ts` | page.tsx CreateRoute() defaults any raw mode to prototype in place with zero fallback of its own; relies entirely on pr… |
| [ISS-377](../.knowledge/cards/20260828-2202-ISS-377.md) | `backend/agents/workflows/manifest.py`, `backend/app/api/user_workflows.py`, `frontend/src/components/workflow/IdeaInputPage.tsx`, `frontend/src/components/workflow/LaunchWizard.tsx`, `frontend/src/types/index.ts` | deferred by FIX-336: an override row persists `manifest`, which `_reject_both` makes exclusive with `selections`, and `… |
| [ISS-381](../.knowledge/cards/20260828-2210-ISS-381.md) | `backend/agents/workflows/selections.py`, `backend/app/api/user_workflows.py`, `frontend/src/components/workflow/IdeaInputPage.tsx` | Save workflow on ex_A4_human_divert returns 422 "agent_ids not allowed for" from the roster check at user_workflows.py:… |
| [ISS-382](../.knowledge/cards/20260828-2008-ISS-382.md) | `frontend/src/components/workflow/composer/CanvasConfigRail.tsx`, `frontend/src/components/workflow/composer/CanvasNode.tsx` | CanvasNode.tsx:763-802 chip row shows Validator/Gate/Retry only, no Tools chip — restriction invisible until the rail T… |
| [ISS-384](../.knowledge/cards/20260828-2221-ISS-384.md) | `frontend/src/components/workflow/LaunchWizard.tsx` | savedName/savedDescription are restored into state at LaunchWizard.tsx:311-313 but only ever passed to the closed Agent… |
| [ISS-386](../.knowledge/cards/20260828-2228-ISS-386.md) | `frontend/src/lib/routes.ts` | runStepsAgent(id, agentId) has no version param unlike runSteps/runFiles/runWorkspace/runAudit, though parseViewPath al… |
| [ISS-387](../.knowledge/cards/20260828-2228-ISS-387.md) | `frontend/src/components/results/AgentDetailPanel.tsx`, `frontend/src/components/results/AgentThinkingTab.tsx`, `frontend/src/components/results/StepsOverviewSpine.tsx` | setSelectedAgentId/setSelectedTaskIndex never push history, so Back after selecting an agent/task skips the Steps list … |
| [ISS-389](../.knowledge/cards/20260828-2234-ISS-389.md) | `frontend/src/components/preview/PreviewPanel.tsx`, `frontend/src/components/results/AuditTab.tsx` | A failed run with 0 hook_runs hits ISS-285's Audit substitution AND AuditTab.tsx:701's own "No audit records yet" — a d… |
| [ISS-405](../.knowledge/cards/20260828-2324-ISS-405.md) | `backend/app/api/admin.py`, `backend/app/models/user.py`, `frontend/src/app/admin/page.tsx` | CreateUserRequest.email (admin.py:131) has no EmailStr/min_length; an empty-string POST would persist it, then page.tsx… |
| [ISS-407](../.knowledge/cards/20260828-2343-ISS-407.md) | `frontend/src/app/preview-fullscreen/page.tsx` | page.tsx:58-72 three failure exits (no raw value, empty files, parse error) all go straight to router.replace(runHistor… |
| [ISS-410](../.knowledge/cards/20260828-2344-ISS-410.md) | `frontend/src/app/[...view]/page.tsx`, `frontend/src/components/workflow/composer/ComposerPage.tsx` | page.tsx:494-496 catches ANY getWorkflowDetail failure, not just 404, so a transient error on a REAL workflow id reache… |
| [ISS-413](../.knowledge/cards/20260828-2357-ISS-413.md) | `backend/app/api/runs.py`, `frontend/src/components/chat/LaneRunHeader.tsx`, `frontend/src/lib/api.ts` | run_events.created_at exists on the row but get_run_events returns only seq/event_id/type/payload_json, so a pre-FIX-35… |
| [ISS-418](../.knowledge/cards/20260828-2231-ISS-418.md) | `backend/agents/execution_engine/engine.py`, `backend/app/api/analytics.py`, `backend/app/api/run_commands.py` | INFERRED inverse of ISS-304: analytics.py:189-195 sums only the persisted token_usage column, so planner/clarify/fix-lo… |
| [ISS-419](../.knowledge/cards/20260829-0022-ISS-419.md) | `backend/app/api/workflows.py`, `frontend/src/components/workflow/ReviewGatesSection.tsx` | checkedIds seeds only from AgentDef.gate/initialGateIds, never a step's manifest gates array — any custom-agent gate va… |
| [ISS-429](../.knowledge/cards/20260829-0022-ISS-429.md) | `frontend/src/components/workflow/LaunchWizard.tsx`, `frontend/src/components/workflow/ReviewGatesSection.tsx`, `frontend/src/components/workflow/composer/CanvasConfigRail.tsx`, `frontend/src/lib/manifestAgents.ts` | ReviewGatesSection at LaunchWizard.tsx:1072 and CanvasConfigRail's Prompt-User toggle share ISS-306's zero-interaction … |
| [ISS-430](../.knowledge/cards/20260829-0029-ISS-430.md) | `backend/app/api/settings.py`, `frontend/src/components/settings/AccountSettings.tsx` | Deferred half of ISS-292: get_preferences still returns the full catalog and the <select> renders every option ungated,… |
| [ISS-434](../.knowledge/cards/20260828-2240-ISS-434.md) | `frontend/src/components/chat/RunChatLane.tsx` | RunChatLane.SettledSummaryStrip skips DeliverableCard when dFilename is falsy, same unfallback-ed deliverable_filename … |
| [ISS-442](../.knowledge/cards/20260829-0106-ISS-442.md) | `frontend/src/app/[...view]/workflowDetailCatch.source.test.ts` | the F7 source-lock counts occurrences of a shared idiom rather than asserting the T30 effect uses it, so ISS-380 and FI… |
| [ISS-470](../.knowledge/cards/20260828-2310-ISS-470.md) | `backend/app/api/settings.py` | Same commit-then-refresh(row) shape as ISS-319: a concurrent PUT could report the OTHER PATs github_username/scopes as … |
| [ISS-472](../.knowledge/cards/20260829-0110-ISS-472.md) | `frontend/src/app/[...view]/page.tsx`, `frontend/src/components/layout/DashboardLayout.tsx`, `frontend/src/components/workflow/IdeaInputPage.tsx` | DashboardLayout.tsx:2910 renders IdeaInputPage with no userTier prop; only mainView==="home" (HomeLaunchGrid) ever read… |
| [ISS-473](../.knowledge/cards/20260829-0111-ISS-473.md) | `frontend/next.config.ts`, `frontend/src/app/workflow/create/page.tsx`, `frontend/src/components/home/CreationHub.tsx`, `frontend/src/components/layout/DashboardLayout.tsx` | app/workflow/create/page.tsx:24 renders LaunchWizard with no tier check; next.config.ts has no /workflow/create redirec… |
| [ISS-474](../.knowledge/cards/20260829-0112-ISS-474.md) | `frontend/src/app/[...view]/page.tsx`, `frontend/src/components/layout/DashboardLayout.tsx`, `frontend/src/components/workflow/composer/ComposerPage.tsx` | DashboardLayout.tsx:2946 renders ComposerPage for the built-in /workflows/{type}/canvas route with no userTier prop; Co… |
| [ISS-486](../.knowledge/cards/20260828-2335-ISS-486.md) | `frontend/src/components/analytics/AnalyticsPage.tsx`, `frontend/src/lib/api.ts`, `frontend/src/lib/routes.ts` | A protected route's own query string (e.g. /analytics?range=&pipeline=) is untested by ISS-322's two validated routes, … |
| [ISS-579](../.knowledge/cards/20260829-0234-ISS-579.md) | `frontend/src/app/workflow/page.tsx`, `frontend/src/components/workflow/WorkflowView.tsx` | WorkflowView.tsx:165 passes ideaInput.trim() (can carry ISS-345's orphaned [Attached] marker) verbatim to onStartPipeli… |
| [ISS-581](../.knowledge/cards/20260829-0241-ISS-581.md) | `frontend/src/components/settings/AccountSettings.tsx`, `tests/integration/e2e/conftest.py`, `tests/integration/e2e/suites/09_settings/test_settings.py` | ConstitutionSection's mount GET fires twice and the late response overwrites typed content, so the test saves the old v… |
| [ISS-591](../.knowledge/cards/20260829-0114-ISS-591.md) | `frontend/src/components/library/LibraryPage.tsx` | SkillDetailModal (LibraryPage.tsx:207-221,285-301) only splits #/##-prefixed lines and -/*/numbered bullets; bold/code/… |
| [ISS-596](../.knowledge/cards/20260829-0127-ISS-596.md) | `frontend/src/components/preview/PreviewPanel.appBuilderSearch.test.tsx` | Test-side defect, not app-side: src/app.js is files[0] in that fixture so it is auto-opened as an editor tab, making th… |
| [ISS-599](../.knowledge/cards/20260829-0340-ISS-599.md) | `frontend/src/components/chat/ArtifactCard.tsx`, `frontend/src/components/chat/MessageBubble.tsx`, `frontend/src/components/preview/PreviewPanel.tsx`, `frontend/src/components/results/artifactPreview.tsx` | ArtifactCard/MessageBubble catch-and-console.error only, and artifactPreview.tsx:406 + PreviewPanel.tsx:890 fire naviga… |
| [ISS-600](../.knowledge/cards/20260829-0341-ISS-600.md) | `frontend/src/components/handoff/IntegrationsCard.copyFeedback.test.tsx`, `frontend/src/components/library/LibraryPage.copyFeedback.test.tsx` | useParams: () => ({}) makes LibraryPage's T16 URL-sync effect close the detail modal before the Copy click lands (write… |
| [ISS-602](../.knowledge/cards/20260829-0353-ISS-602.md) | `frontend/src/app/login/page.tsx` | login/page.tsx:303-317 keeps a hand-rolled type="password" input inside a Lock-icon relative wrapper; it was left out o… |
| [ISS-603](../.knowledge/cards/20260829-0402-ISS-603.md) | `frontend/src/components/workflow/WorkflowView.attachmentRemove.test.tsx` | Fixture defect, not a code defect: the case removes the ONLY attachment (brief becomes "") and mounts with an empty age… |
| [ISS-604](../.knowledge/cards/20260829-0207-ISS-604.md) | `frontend/src/app/[...view]/page.tsx`, `frontend/src/components/workflow/composer/ComposerPage.tsx` | ComposerPage's seededRunConfig effect adopts initialRunConfig only after the GET /api/workflows/<type> fetch resolves, … |
| [ISS-605](../.knowledge/cards/20260829-0216-ISS-605.md) | `frontend/src/components/library/LibraryPage.skillMarkdown.test.tsx` | Assertion 2 scans the whole [role=dialog], which always contains the modal's intentional raw SKILL.md <pre>; scope it t… |
| [ISS-609](../.knowledge/cards/20260829-1420-ISS-609.md) | `frontend/src/components/preview/PreviewPanel.tsx`, `frontend/src/components/results/AuditTab.tsx` | AuditTab gets workflowRunId=pipelineState?.pipelineRunId at PreviewPanel.tsx:1466, not activeRunId, so its own gate/val… |
| [ISS-623](../.knowledge/cards/20260831-0115-ISS-623.md) | `tests/integration/e2e/suites/04_composer_canvas/test_composer_canvas.py`, `tests/integration/e2e/suites/05_saved_workflows/test_saved_workflows.py` | da92b4a4 lost report-generator on 2026-08-29 and is the plain 3-agent ppt base now, so the saved roster no longer diffe… |
| [ISS-624](../.knowledge/cards/20260831-0115-ISS-624.md) | `frontend/src/app/[...view]/page.tsx`, `tests/integration/e2e/suites/12_shell_nav/test_shell_nav.py` | document.body.innerText.length is 0 on a cold load of /library?tab=hooks; the other four top-level routes in the same t… |
| [ISS-625](../.knowledge/cards/20260831-0115-ISS-625.md) | `tests/integration/e2e/suites/06_run_history/test_run_history.py` | no family buckets to ppt so WorkflowHistory drops the chip entirely; whether the runs SHOULD be gone is unanswered and … |
| [ISS-626](../.knowledge/cards/20260831-0115-ISS-626.md) | `tests/integration/e2e/suites/04_composer_canvas/test_composer_canvas.py` | test_a_last_streamed_built_in_refuses_an_append_after_final_step_slot times out on its locator; app-versus-test not yet… |
| [ISS-627](../.knowledge/cards/20260831-0115-ISS-627.md) | `tests/integration/e2e/suites/08_library/test_iss592_agent_detail_close_preserves_filter.py`, `tests/integration/e2e/suites/08_library/test_iss593_skill_detail_close_preserves_filter.py`, `tests/integration/e2e/suites/08_library/test_iss594_hook_detail_back_button_loses_search.py`, `tests/integration/e2e/suites/09_settings/test_settings.py`, `tests/integration/e2e/suites/15_overlays/test_overlays.py` | ISS-592/593/594/320 pass under xfail(strict) and the S-15-01 Escape pin now fails, so five guards assert behaviour the … |
| [ISS-628](../.knowledge/cards/20260831-0115-ISS-628.md) | `tests/integration/e2e/suites/04_composer_canvas/test_composer_canvas.py`, `tests/integration/e2e/suites/06_run_history/test_run_history.py`, `tests/integration/e2e/suites/07_run_detail/test_run_detail.py`, `tests/integration/e2e/suites/13_errors/test_errors.py` | six tests break on the same collapse ISS-618 recorded: chips count families while the headline counts runs, and a famil… |
| [ISS-629](../.knowledge/cards/20260831-0115-ISS-629.md) | `frontend/src/components/history/RunDetailPage.tsx`, `frontend/src/components/history/WorkflowHistory.tsx`, `tests/integration/screens/21-run-families-and-versions.feature.md` | WorkflowHistory.handleSelectRun routes every tap to the shared run screen (BUG-002), so the timeline region S-21-07/08/… |
| [ISS-630](../.knowledge/cards/20260831-0115-ISS-630.md) | `backend/tests/integration/test_revision_analyzer_integration.py` | eleven assertions fail on 500 and the ten RuntimeError: This portal is not running entries are that failure's teardown … |
| [ISS-631](../.knowledge/cards/20260831-0115-ISS-631.md) | `backend/agents/workflows/prototype_revision/workflow.yaml`, `backend/tests/agents/test_manifest_coverage.py`, `backend/tests/agents/test_registry.py` | roster and compiled sequence diverge from the manifest for all three revision pipelines; 15 tests witness what looks li… |
| [ISS-632](../.knowledge/cards/20260831-0115-ISS-632.md) | `backend/tests/agents/test_engine_runner_error_arm.py`, `backend/tests/unit/test_pipeline_failure_semantics.py` | a workflow_v* event rides alongside the expected single pipeline_failed, and the degraded counts read 5 == 1 and 6 == 2… |
| [ISS-633](../.knowledge/cards/20260831-0115-ISS-633.md) | `backend/tests/agents/test_revision_gating.py`, `backend/tests/unit/test_concierge_proposal_channels.py`, `backend/tests/unit/test_revision_intelligence.py`, `backend/tests/unit/test_run_revision_fe_contract.py` | four tests expect exactly one exact-kind revision ref and get another count; two FE-contract tests surface list index o… |
| [ISS-634](../.knowledge/cards/20260831-0115-ISS-634.md) | `backend/tests/agents/test_chunk_sanitizer.py` | a tool-using stream, a clean tool-less stream, a lone < at a chunk boundary and a benign held tail are each altered on … |
| [ISS-635](../.knowledge/cards/20260831-0115-ISS-635.md) | `backend/agents/workflows/playwright_smoke_test/workflow.yaml`, `backend/tests/agents/test_id_alias_resolver.py`, `backend/tests/agents/test_manifest_parity.py` | the spec-018 manifest declares planner: skip where parity requires run, and its clarify.defaults is empty where the eng… |
| [ISS-637](../.knowledge/cards/20260831-0115-ISS-637.md) | `backend/tests/unit/test_alembic.py` | test_upgrade_then_check_reports_no_drift raises AutogenerateDiffsDetected: the ORM metadata and the migration chain hav… |
| [ISS-638](../.knowledge/cards/20260831-0115-ISS-638.md) | `backend/tests/agents/test_phase5_revision_validation.py`, `backend/tests/agents/test_phase8_live.py`, `backend/tests/agents/test_text_only_prompt_hygiene.py`, `backend/tests/agents/test_tool_grant_invariants.py`, `backend/tests/unit/test_workflows_api.py` | one each in tool_grant_invariants, text_only_prompt_hygiene, phase5 (x2), phase8_live and workflows_api; grouped only b… |

