# Open issues — deduplicated by fix site

Every open/deferred card in `.knowledge/`, grouped by **where the fix goes** rather
than by what the user saw. Companion to [`OPEN-ISSUES.md`](OPEN-ISSUES.md), which is
the flat per-symptom register.

Generated from the card store — regenerate rather than editing rows by hand:

```
python3 bug-hunter/tools/dedup.py
```

**112 open cards → 106 units of work** (15 families + 91 singletons), schedulable as **22 work batches** — see [Work batches](#work-batches--how-to-actually-run-this) for the execution view. **289 closed** — see [Closed](#-closed--fix-landed).

A merge is proposed only where cards share a **fix site**, not merely a symptom
class. Two Escape-key bugs in unrelated components are one class and two diffs —
merging those would close a family while a member is still broken.

| tier | what it means | families | cards |
|---|---|---|---|
| A′ | root **already fixed**, siblings still open — replicate the landed diff | 9 | 11 |
| A | declared family, root and siblings both open — one line trip | 2 | 4 |
| B | same file **and** same defect class — proposed, needs review | 4 | 6 |
| C | no kin found — stays its own row | — | 91 |

---

## ✅ Closed — fix landed

289 defect card(s) now `status: resolved`. Kept here so this one file
shows every card's real status: the `→ FIX-NNN` column is the landed fix that
closed it, and *origin* is the root it was a sibling of (where it came from).
Generated from card frontmatter — a card drops out of the open backlog below and
appears here the moment its `status` flips to `resolved`.

| closed card | → fix | origin | what it was |
|---|---|---|---|
| [BUG-006-007-GROUNDED-CONTEXT](../.knowledge/cards/20260716-1520-BUG-006-007-GROUNDED-CONTEXT.md) | — | — | BUG-006: lane type chip read workflowType not effectiveReviseType, missing a third stale-label cons… |
| [BUG-008-011-GROUNDED-CONTEXT](../.knowledge/cards/20260716-1636-BUG-008-011-GROUNDED-CONTEXT.md) | — | — | BUG-008: reopened deliverables render empty since hasGenericDeliverable gates on stale workflowType… |
| [BUG-012-FOLLOWUP-LABEL-GROUNDED-CONTEXT](../.knowledge/cards/20260716-2036-BUG-012-FOLLOWUP-LABEL-GROUNDED-CONTEXT.md) | — | — | The BUG-006/012 binding was gated on !isPipelineRunning, so a non-terminal reopen still showed the … |
| [BUG-012-GROUNDED-CONTEXT](../.knowledge/cards/20260716-1725-BUG-012-GROUNDED-CONTEXT.md) | — | — | Reopened od_ppt/od_prototype runs render blank because PreviewPanel's detectedType short-circuits o… |
| [BUG-014-GROUNDED-CONTEXT](../.knowledge/cards/20260716-2156-BUG-014-GROUNDED-CONTEXT.md) | — | — | LaunchWizard read chain.source_run_id from sessionStorage unconditionally and never cleared it, so … |
| [BUG-019-020-GROUNDED-CONTEXT](../.knowledge/cards/20260717-2007-BUG-019-020-GROUNDED-CONTEXT.md) | — | — | recentRuns?.[0] leaked the previous run's title/type into a fresh launch header; fixed by falling b… |
| [BUG-030](../.knowledge/cards/20260826-1403-BUG-030.md) | [FIX-302](../.knowledge/cards/20260825-2115-FIX-302.md), [FIX-359](../.knowledge/cards/20260829-0014-FIX-359.md) | — | router.push on a tab click changed the [...view] params, remounting page.tsx onto PreviewPanel's Pr… |
| [BUG-031](../.knowledge/cards/20260827-BUG-031.md) | — | — | A commit ran the knowledge hook, which rebuilt .knowledge/ over the files pre-commit had stashed; t… |
| [BUG-DEF-44-12-4-GROUNDED-CONTEXT](../.knowledge/cards/20260716-0952-BUG-DEF-44-12-4-GROUNDED-CONTEXT.md) | — | — | Opened-from-history runs show an empty Steps trace and non-rendering Concierge reply because the re… |
| [ISS-072](../.knowledge/cards/20260812-0131-ISS-072.md) | [FIX-218](../.knowledge/cards/20260811-2246-FIX-218.md), [FIX-220](../.knowledge/cards/20260812-0131-FIX-220.md), [FIX-252](../.knowledge/cards/20260813-1300-FIX-252.md), [FIX-254](../.knowledge/cards/20260813-1300-FIX-254.md), [FIX-424](../.knowledge/cards/20260831-1652-FIX-424.md), [FIX-BUGFIX-NESTED-REVISION](../.knowledge/cards/20260811-2031-FIX-BUGFIX-NESTED-REVISION.md) | — | One 'Update the Specs' click still costs four approvals because the redundant in-pass analyze gate … |
| [ISS-073](../.knowledge/cards/20260812-0138-ISS-073.md) | — | — | InlineGateActions.test.tsx still asserts the update-specs button is hidden pre-click, but the compo… |
| [ISS-090](../.knowledge/cards/20260812-0632-ISS-090.md) | [FIX-228](../.knowledge/cards/20260812-0617-FIX-228.md), [FIX-425](../.knowledge/cards/20260831-1804-FIX-425.md), [FIX-427](../.knowledge/cards/20260831-1813-FIX-427.md) | — | Unlike update_specs_eligible, redoable=True is a hardcoded literal at all three gate sites, so any … |
| [ISS-095](../.knowledge/cards/20260812-1120-ISS-095.md) | [FIX-231](../.knowledge/cards/20260812-1120-FIX-231.md) | — | Three reds mislabeled as sqlite-FK environmental noise actually assert a declared gate never fired … |
| [ISS-098](../.knowledge/cards/20260812-1153-ISS-098.md) | [FIX-232](../.knowledge/cards/20260812-1153-FIX-232.md), [FIX-425](../.knowledge/cards/20260831-1804-FIX-425.md) | — | wave_scheduler catches except Exception to flip a wave row terminal, but CancelledError inherits Ba… |
| [ISS-101](../.knowledge/cards/20260812-1232-ISS-101.md) | [FIX-233](../.knowledge/cards/20260812-1232-FIX-233.md), [FIX-426](../.knowledge/cards/20260831-1806-FIX-426.md) | — | conversation.py calls unbounded read_events then filters in Python to build a 6-turn transcript, no… |
| [ISS-106](../.knowledge/cards/20260812-1315-ISS-106.md) | [FIX-234](../.knowledge/cards/20260812-1312-FIX-234.md), [FIX-428](../.knowledge/cards/20260831-1816-FIX-428.md) | — | close_checkpointer()'s pool.close() has no timeout, so a slow Postgres pool close can push teardown… |
| [ISS-108](../.knowledge/cards/20260812-1400-ISS-108.md) | [FIX-235](../.knowledge/cards/20260812-1400-FIX-235.md), [FIX-475](../.knowledge/cards/20260902-1200-FIX-475.md) | — | retainClarifyRound pushes clarification rounds with no identity key and no reset outside startPipel… |
| [ISS-110](../.knowledge/cards/20260812-1400-ISS-110.md) | [FIX-201](../.knowledge/cards/20260807-1633-FIX-201.md), [FIX-235](../.knowledge/cards/20260812-1400-FIX-235.md), [FIX-475](../.knowledge/cards/20260902-1200-FIX-475.md) | — | pipeline_start spreads ...prev without clearing hookRuns, so one run's hook rows can survive into t… |
| [ISS-114](../.knowledge/cards/20260812-1444-ISS-114.md) | [FIX-236](../.knowledge/cards/20260812-1444-FIX-236.md) | — | KAN-154 moved the deliverable card into an inline-render branch with no title text, so the LOCK-F '… |
| [ISS-117](../.knowledge/cards/20260812-1511-ISS-117.md) | [FIX-237](../.knowledge/cards/20260812-1511-FIX-237.md), [FIX-454](../.knowledge/cards/20260901-1600-FIX-454.md) | — | useRunStateStore's replay allowlist omits validator_result/gate_passed/gate_blocked, so no reopened… |
| [ISS-118](../.knowledge/cards/20260812-1612-ISS-118.md) | [FIX-238](../.knowledge/cards/20260812-1612-FIX-238.md), [FIX-429](../.knowledge/cards/20260831-1818-FIX-429.md) | — | Eight offline tests construct a real LLM provider client (five bypassing build_model) but never inv… |
| [ISS-120](../.knowledge/cards/20260812-1637-ISS-120.md) | [FIX-239](../.knowledge/cards/20260812-1637-FIX-239.md), [FIX-427](../.knowledge/cards/20260831-1813-FIX-427.md), [FIX-429](../.knowledge/cards/20260831-1818-FIX-429.md) | — | Bedrock prompt caching is one global switch with no per-workflow override; short runs that write ca… |
| [ISS-125](../.knowledge/cards/20260812-1852-ISS-125.md) | [FIX-240](../.knowledge/cards/20260812-1852-FIX-240.md), [FIX-426](../.knowledge/cards/20260831-1806-FIX-426.md) | — | _stamp_resume_marker reads the entire durable log just to compute the next seq and uses a non-retry… |
| [ISS-131](../.knowledge/cards/20260812-2116-ISS-131.md) | [FIX-242](../.knowledge/cards/20260812-2116-FIX-242.md), [FIX-424](../.knowledge/cards/20260831-1652-FIX-424.md), [FIX-425](../.knowledge/cards/20260831-1804-FIX-425.md) | — | After FIX-242, a fan-out step that both declares a human gate and has its agent ticked silently get… |
| [ISS-141](../.knowledge/cards/20260813-0005-ISS-141.md) | [FIX-245](../.knowledge/cards/20260813-0005-FIX-245.md), [FIX-474](../.knowledge/cards/20260902-1200-FIX-474.md) | — | Reopened terminal runs still show an actionable clarify chat card, because terminal auto-resolve on… |
| [ISS-143](../.knowledge/cards/20260813-0205-ISS-143.md) | [FIX-247](../.knowledge/cards/20260813-0205-FIX-247.md), [FIX-482](../.knowledge/cards/20260902-1530-FIX-482.md) | — | The header 'N Running' pill goes stale after a live cancel — no recentRuns refresh fires inside the… |
| [ISS-175](../.knowledge/cards/20260825-1115-ISS-175.md) | [FIX-297](../.knowledge/cards/20260825-1115-FIX-297.md), [FIX-473](../.knowledge/cards/20260902-1200-FIX-473.md) | — | Fixed — chain edges now added only where hasChainEdge holds instead of between every array neighbou… |
| [ISS-176](../.knowledge/cards/20260825-1115-ISS-176.md) | [FIX-297](../.knowledge/cards/20260825-1115-FIX-297.md) | — | Fixed — external nodes are EXTERNAL_NODE_W 190 against NODE_W 260 and shared the column left edge; … |
| [ISS-177](../.knowledge/cards/20260825-1115-ISS-177.md) | [FIX-297](../.knowledge/cards/20260825-1115-FIX-297.md) | — | Fixed — both tests now drive the ADR-0013 gate checkboxes, and the PALETTE fixture was missing the … |
| [ISS-178](../.knowledge/cards/20260825-1131-ISS-178.md) | [FIX-473](../.knowledge/cards/20260902-1200-FIX-473.md) | — | computeRootLayout derives edges from array adjacency plus route outcomes only, so a step whose sole… |
| [ISS-182](../.knowledge/cards/20260825-2115-ISS-182.md) | [FIX-306](../.knowledge/cards/20260825-2115-FIX-306.md), [FIX-438](../.knowledge/cards/20260831-1954-FIX-438.md) | — | The UI no longer offers the blank template, but rows already storing custom-agent:<id> are untouche… |
| [ISS-184](../.knowledge/cards/20260825-2115-ISS-184.md) | [FIX-314](../.knowledge/cards/20260826-0124-FIX-314.md) | — | The prototype override ran 2 steps with no build agent, so no prototype.html was written and the de… |
| [ISS-185](../.knowledge/cards/20260825-2115-ISS-185.md) | [FIX-431](../.knowledge/cards/20260831-1829-FIX-431.md) | — | The composer hunts for template files at the skill mount point while the real files sit at /referen… |
| [ISS-188](../.knowledge/cards/20260828-1300-ISS-188.md) | [FIX-100](../.knowledge/cards/20260722-1853-FIX-100.md), [FIX-324](../.knowledge/cards/20260828-1641-FIX-324.md) | — | CACHE_KEY_RECENTS ("vlc_home_recents_v1") is a single global sessionStorage key with no user id/tok… |
| [ISS-191](../.knowledge/cards/20260828-1330-ISS-191.md) | [FIX-323](../.knowledge/cards/20260828-1629-FIX-323.md) | — | login/page.tsx has no guard checking an existing valid auth_token before render, so a signed-in use… |
| [ISS-193](../.knowledge/cards/20260828-1554-ISS-193.md) | [FIX-323](../.knowledge/cards/20260828-1629-FIX-323.md) | — | register/page.tsx redirects to /login with no getToken() check, so it inherits ISS-191's missing gu… |
| [ISS-196](../.knowledge/cards/20260828-1555-ISS-196.md) | [FIX-325](../.knowledge/cards/20260828-1645-FIX-325.md), [FIX-352](../.knowledge/cards/20260828-2346-FIX-352.md) | — | Save as copy on the ppt built-in POSTs manifest:null because ComposerPage never seeds runConfig fro… |
| [ISS-198](../.knowledge/cards/20260828-1400-ISS-198.md) | [FIX-144](../.knowledge/cards/20260730-1252-FIX-144.md), [FIX-466](../.knowledge/cards/20260902-1100-FIX-466.md) | — | Run History renders the capped runs.length (50) instead of the totalRuns it already holds; handleLo… |
| [ISS-199](../.knowledge/cards/20260828-1600-ISS-199.md) | [FIX-316](../.knowledge/cards/20260827-0054-FIX-316.md), [FIX-318](../.knowledge/cards/20260827-0055-FIX-318.md), [FIX-327](../.knowledge/cards/20260828-1845-FIX-327.md) | — | Files tab hero sets pptContent from fullRun.output (last-streamed agent text) instead of reading th… |
| [ISS-200](../.knowledge/cards/20260828-1605-ISS-200.md) | [FIX-324](../.knowledge/cards/20260828-1641-FIX-324.md), [FIX-340](../.knowledge/cards/20260828-2230-FIX-340.md) | — | signedIn carries no prior-token check and the preload guard gates only on status, so a token swap w… |
| [ISS-201](../.knowledge/cards/20260828-1607-ISS-201.md) | [FIX-324](../.knowledge/cards/20260828-1641-FIX-324.md) | — | The same useState(() => readCache(...)) fallback paints the prior account's cached cards on every a… |
| [ISS-202](../.knowledge/cards/20260828-1409-ISS-202.md) | [FIX-326](../.knowledge/cards/20260828-1656-FIX-326.md) | — | AuditTab.tsx:568-584 forces category:"gate" on every hook_runs row incl. audit-logger step/tool mar… |
| [ISS-203](../.knowledge/cards/20260828-1610-ISS-203.md) | [FIX-325](../.knowledge/cards/20260828-1645-FIX-325.md) | — | The needsFullManifest/runConfig gate in ISS-206 is not ppt-specific: every built-in whose deliverab… |
| [ISS-204](../.knowledge/cards/20260828-1611-ISS-204.md) | [FIX-325](../.knowledge/cards/20260828-1645-FIX-325.md) | — | needsFullManifest(pipelineAgents) never checks runConfig, so ANY composer save with zero customized… |
| [ISS-205](../.knowledge/cards/20260828-1612-ISS-205.md) | [FIX-325](../.knowledge/cards/20260828-1645-FIX-325.md) | — | unmodifiedBuiltin (ComposerPage.tsx:841-845) only compares agent-id lists, so reordering/adding an … |
| [ISS-206](../.knowledge/cards/20260828-1609-ISS-206.md) | [FIX-325](../.knowledge/cards/20260828-1645-FIX-325.md) | — | Save omits `manifest` from the POST because needsFullManifest ignores runConfig; runConfig itself n… |
| [ISS-207](../.knowledge/cards/20260828-1617-ISS-207.md) | [FIX-466](../.knowledge/cards/20260902-1100-FIX-466.md) | — | matchesFilter (~L430) runs client-side over runs/families, which never exceeds the fetched 50 — a s… |
| [ISS-208](../.knowledge/cards/20260828-1617-ISS-208.md) | [FIX-466](../.knowledge/cards/20260902-1100-FIX-466.md) | — | bucketAndSortFamilies (~L950) sorts visibleFamilies, itself derived from the capped runs array — Lo… |
| [ISS-209](../.knowledge/cards/20260828-1617-ISS-209.md) | [FIX-466](../.knowledge/cards/20260902-1100-FIX-466.md), [FIX-467](../.knowledge/cards/20260902-1100-FIX-467.md) | — | handleDeleteConfirm (~L408-421) calls setRuns to drop the deleted row but never setTotalRuns, leavi… |
| [ISS-211](../.knowledge/cards/20260828-1429-ISS-211.md) | [FIX-326](../.knowledge/cards/20260828-1656-FIX-326.md) | — | exportAuditCSV/JSON (auditExporter.ts:83-99) serialize the same rows[] state ISS-202 shows is fabri… |
| [ISS-212](../.knowledge/cards/20260828-1428-ISS-212.md) | [FIX-326](../.knowledge/cards/20260828-1656-FIX-326.md) | — | AuditTab's fetch/merge effect keys only on workflowRunId (line 451), never isRunning, so ISS-202's … |
| [ISS-213](../.knowledge/cards/20260828-1618-ISS-213.md) | [FIX-466](../.knowledge/cards/20260902-1100-FIX-466.md) | — | typeCounts (~L952-958) tallies every filter chip from the same capped families array; a type with z… |
| [ISS-214](../.knowledge/cards/20260828-1633-ISS-214.md) | [FIX-327](../.knowledge/cards/20260828-1845-FIX-327.md), [FIX-449](../.knowledge/cards/20260901-1530-FIX-449.md) | — | WorkflowHistory.tsx:542 isPpt omits ppt_v2 (no renderType-style normalization), so its own Files ta… |
| [ISS-215](../.knowledge/cards/20260828-1633-ISS-215.md) | [FIX-327](../.knowledge/cards/20260828-1845-FIX-327.md), [FIX-449](../.knowledge/cards/20260901-1530-FIX-449.md) | — | FilesTab.tsx:436-440 feeds parentRun.type (raw, unnormalized) into deriveDeliverableFiles, so a ppt… |
| [ISS-216](../.knowledge/cards/20260828-1643-ISS-216.md) | [FIX-324](../.knowledge/cards/20260828-1641-FIX-324.md), [FIX-408](../.knowledge/cards/20260829-0447-FIX-408.md) | — | The only six `tsc --noEmit` errors in frontend/ outside .next/ are in these two files: five arity e… |
| [ISS-218](../.knowledge/cards/20260828-1700-ISS-218.md) | [FIX-125](../.knowledge/cards/20260727-1557-FIX-125.md), [FIX-331](../.knowledge/cards/20260828-2056-FIX-331.md) | — | handleEditBrief navigates to a blank /create/<type> composer with no brief prefill: router.push(cre… |
| [ISS-220](../.knowledge/cards/20260828-1712-ISS-220.md) | [FIX-105](../.knowledge/cards/20260723-FIX-105.md), [FIX-298](../.knowledge/cards/20260825-FIX-298.md), [FIX-330](../.knowledge/cards/20260828-2047-FIX-330.md) | — | Resume-triggered router.push remount races the SSE reattach against a ~3-4s pipeline_failed, freezi… |
| [ISS-221](../.knowledge/cards/20260828-1718-ISS-221.md) | [FIX-329](../.knowledge/cards/20260828-2045-FIX-329.md) | — | relaunch() helper (RunChatLane.tsx) omits the relaunchError block that only the cancelled/failed br… |
| [ISS-222](../.knowledge/cards/20260828-1534-ISS-222.md) | [FIX-333](../.knowledge/cards/20260828-2131-FIX-333.md) | — | Hook detail cards render as div.cursor-pointer.p-4 (Card + onClick only) with no tabindex/role/onKe… |
| [ISS-224](../.knowledge/cards/20260828-1735-ISS-224.md) | [FIX-332](../.knowledge/cards/20260828-1915-FIX-332.md), [FIX-370](../.knowledge/cards/20260829-0116-FIX-370.md) | — | GithubPATRequest.pat (max_length=512, settings.py:64) has no custom 422 handler so Pydantic's defau… |
| [ISS-225](../.knowledge/cards/20260828-1541-ISS-225.md) | [FIX-285](../.knowledge/cards/20260824-1621-FIX-285.md), [FIX-336](../.knowledge/cards/20260828-2201-FIX-336.md), [FIX-337](../.knowledge/cards/20260828-2210-FIX-337.md) | — | handleSaveAsOverride builds the save manifest from selectionsRef.current, which is only seeded from… |
| [ISS-226](../.knowledge/cards/20260828-1550-ISS-226.md) | [FIX-336](../.knowledge/cards/20260828-2201-FIX-336.md) | — | Save as my version on /create/ppt silently discards the brief and template: handleSaveAsOverride (L… |
| [ISS-227](../.knowledge/cards/20260828-1554-ISS-227.md) | [FIX-335](../.knowledge/cards/20260828-1959-FIX-335.md), [FIX-347](../.knowledge/cards/20260828-2318-FIX-347.md) | — | proxy.ts:10 builds `/create/${mode}` by string concat and hands it to `new URL()`, which resolves `… |
| [ISS-229](../.knowledge/cards/20260828-1601-ISS-229.md) | [FIX-339](../.knowledge/cards/20260828-2231-FIX-339.md) | — | ROOT CAUSE: AnalyticsPage.tsx derives KPI tiles/chart/success-rate/token-breakdown straight from th… |
| [ISS-230](../.knowledge/cards/20260828-1805-ISS-230.md) | [FIX-328](../.knowledge/cards/20260828-2014-FIX-328.md), [FIX-334](../.knowledge/cards/20260828-2149-FIX-334.md), [FIX-355](../.knowledge/cards/20260828-2358-FIX-355.md), [FIX-411](../.knowledge/cards/20260829-1646-FIX-411.md), [FIX-417](../.knowledge/cards/20260831-0110-FIX-417.md), [FIX-445](../.knowledge/cards/20260901-FIX-445.md) | — | handlePreviewPanelTabSelect (DashboardLayout.tsx:471-498) builds routeMap from contentSourceRunId o… |
| [ISS-231](../.knowledge/cards/20260828-1630-ISS-231.md) | [FIX-342](../.knowledge/cards/20260828-2238-FIX-342.md) | — | LibraryPage.tsx maps filteredAgents/activeSkills/filteredHooks with no length===0 branch, so a non-… |
| [ISS-232](../.knowledge/cards/20260828-1627-ISS-232.md) | [FIX-340](../.knowledge/cards/20260828-2230-FIX-340.md), [FIX-457](../.knowledge/cards/20260901-1900-FIX-457.md) | — | LibraryPage's cold-mount seed effect never fires setSelectedSkill for any id; only GET /api/skills/… |
| [ISS-233](../.knowledge/cards/20260828-1829-ISS-233.md) | [FIX-329](../.knowledge/cards/20260828-2045-FIX-329.md) | [ISS-221](../.knowledge/cards/20260828-1718-ISS-221.md) | relaunch() (RunChatLane.tsx:1694) backs the degraded branch (line 1865) too, so a resumeError on "R… |
| [ISS-234](../.knowledge/cards/20260828-1628-ISS-234.md) | [FIX-343](../.knowledge/cards/20260828-2039-FIX-343.md) | — | agent_ids=[] is falsy in run_commands.py:2695, so 0-agent Run once falls to get_pipeline_agents("cu… |
| [ISS-235](../.knowledge/cards/20260828-1830-ISS-235.md) | [FIX-331](../.knowledge/cards/20260828-2056-FIX-331.md) | — | handleEditBrief never reads or clears pendingHomeBrief, IdeaInputPage.initialInput's fallback sourc… |
| [ISS-236](../.knowledge/cards/20260828-1740-ISS-236.md) | [FIX-330](../.knowledge/cards/20260828-2047-FIX-330.md), [FIX-379](../.knowledge/cards/20260829-0210-FIX-379.md) | — | RunChatLane's failed-run "Reopen & fix" button calls the same onRelaunch=handleResumeRun as ISS-220… |
| [ISS-237](../.knowledge/cards/20260828-1741-ISS-237.md) | [FIX-330](../.knowledge/cards/20260828-2047-FIX-330.md) | — | RunChatLane's degraded-run "Run again" button calls the same onRelaunch=handleResumeRun as ISS-220'… |
| [ISS-238](../.knowledge/cards/20260828-1633-ISS-238.md) | [FIX-344](../.knowledge/cards/20260828-2046-FIX-344.md) | — | routes.ts:219 head==="register" matches ANY /register/* depth, but [...view]/page.tsx has no regist… |
| [ISS-244](../.knowledge/cards/20260828-1634-ISS-244.md) | [FIX-341](../.knowledge/cards/20260828-2236-FIX-341.md), [FIX-398](../.knowledge/cards/20260829-0352-FIX-398.md), [FIX-459](../.knowledge/cards/20260901-2100-FIX-459.md) | — | AccountSettings onChange handlers (L295, L306) never call setMessage(null), so the mismatch banner … |
| [ISS-245](../.knowledge/cards/20260828-1631-ISS-245.md) | [FIX-345](../.knowledge/cards/20260828-2250-FIX-345.md), [FIX-470](../.knowledge/cards/20260902-1200-FIX-470.md) | — | Login button disabled={isLoading} relies on a React state commit that has not landed by the time sy… |
| [ISS-246](../.knowledge/cards/20260828-1657-ISS-246.md) | [FIX-348](../.knowledge/cards/20260828-2321-FIX-348.md) | — | LaunchWizard never forwards onRunConfigChange/onCapabilitiesChange for built-in launches, so Canvas… |
| [ISS-247](../.knowledge/cards/20260828-1637-ISS-247.md) | [FIX-346](../.knowledge/cards/20260828-2314-FIX-346.md), [FIX-377](../.knowledge/cards/20260829-0158-FIX-377.md) | — | ReviewGatesSection writes gateAgentIds (sent as run-launch gate_agent_ids); CanvasConfigRail Gate c… |
| [ISS-250](../.knowledge/cards/20260828-1645-ISS-250.md) | [FIX-347](../.knowledge/cards/20260828-2318-FIX-347.md) | — | CreateRoute defaults raw=null/"" to LaunchWizard mode prototype in place with no router.replace, so… |
| [ISS-251](../.knowledge/cards/20260828-1846-ISS-251.md) | [FIX-327](../.knowledge/cards/20260828-1845-FIX-327.md), [FIX-449](../.knowledge/cards/20260901-1530-FIX-449.md) | — | PreviewPanel.tsx:844-910 duplicates the declared-name + listing + extension-keyed sibling rule now … |
| [ISS-252](../.knowledge/cards/20260828-1847-ISS-252.md) | [FIX-327](../.knowledge/cards/20260828-1845-FIX-327.md), [FIX-480](../.knowledge/cards/20260902-1530-FIX-480.md) | — | DashboardLayout.tsx:2347 and :2160 test effectiveReviseType against "ppt"/"ppt_revision" only, so a… |
| [ISS-254](../.knowledge/cards/20260828-1810-ISS-254.md) | [FIX-337](../.knowledge/cards/20260828-2210-FIX-337.md) | [ISS-225](../.knowledge/cards/20260828-1541-ISS-225.md) | INFERRED sibling of ISS-225: the same unseeded selectionsRef hits ex_A1_loop, ex_A2_branch, ex_A3_d… |
| [ISS-256](../.knowledge/cards/20260828-1816-ISS-256.md) | [FIX-332](../.knowledge/cards/20260828-1915-FIX-332.md) | — | ApiError's constructor (api.ts:77-79) reimplements authedJson's JSON.stringify(detail) fallback ind… |
| [ISS-257](../.knowledge/cards/20260828-1817-ISS-257.md) | [FIX-332](../.knowledge/cards/20260828-1915-FIX-332.md), [FIX-430](../.knowledge/cards/20260831-1827-FIX-430.md) | [ISS-224](../.knowledge/cards/20260828-1735-ISS-224.md) | RegisterRequest.password (min_length=8, schemas.py:16) has no custom 422 handler either (main.py re… |
| [ISS-264](../.knowledge/cards/20260828-1815-ISS-264.md) | [FIX-332](../.knowledge/cards/20260828-1915-FIX-332.md) | — | Same authedJson (api-handoff.ts:86-88) stringify fallback as ISS-224, triggerable via ApiKeyCreateR… |
| [ISS-270](../.knowledge/cards/20260828-1850-ISS-270.md) | [FIX-333](../.knowledge/cards/20260828-2131-FIX-333.md) | — | Agents tab cards (LibraryPage.tsx:740-757) are the same onClick Card with no tabindex/role/onKeyDow… |
| [ISS-271](../.knowledge/cards/20260828-1851-ISS-271.md) | [FIX-333](../.knowledge/cards/20260828-2131-FIX-333.md) | — | Skills tab active-skills cards (LibraryPage.tsx:821-826) share ISS-222's missing tabindex/role/onKe… |
| [ISS-272](../.knowledge/cards/20260828-1852-ISS-272.md) | [FIX-333](../.knowledge/cards/20260828-2131-FIX-333.md), [FIX-388](../.knowledge/cards/20260829-0053-FIX-388.md) | — | SkillDetailModal/HookDetailModal close only via a mouse-click scrim or Close button; grep finds zer… |
| [ISS-273](../.knowledge/cards/20260828-1653-ISS-273.md) | [FIX-355](../.knowledge/cards/20260828-2358-FIX-355.md) | — | CONFIRMED: [...view]/page.tsx's workflow-run cold-mount catch (page.tsx:3692-3707) sets workflowRun… |
| [ISS-274](../.knowledge/cards/20260828-1854-ISS-274.md) | [FIX-350](../.knowledge/cards/20260828-2340-FIX-350.md), [FIX-471](../.knowledge/cards/20260902-1200-FIX-471.md) | — | AgentRow.tsx reuses AdvancedExpander (Model/Validator/Gate/Retry only) not CanvasConfigRail, so Sim… |
| [ISS-275](../.knowledge/cards/20260828-1855-ISS-275.md) | [FIX-352](../.knowledge/cards/20260828-2346-FIX-352.md), [FIX-481](../.knowledge/cards/20260902-1530-FIX-481.md) | — | handleBackNav (DashboardLayout.tsx:1684) calls router.back()/router.push with no dirty check, so Co… |
| [ISS-276](../.knowledge/cards/20260828-1700-ISS-276.md) | [FIX-354](../.knowledge/cards/20260828-2357-FIX-354.md) | — | Header stuck reading "just now" on completed runs: LaneRunHeader:257 feeds formatRelativeAge a hydr… |
| [ISS-277](../.knowledge/cards/20260828-1659-ISS-277.md) | [FIX-358](../.knowledge/cards/20260829-0011-FIX-358.md), [FIX-359](../.knowledge/cards/20260829-0014-FIX-359.md), [FIX-455](../.knowledge/cards/20260901-1600-FIX-455.md) | — | reopenTabFor/requestOpenTab thread only the tab name from parseViewPath, dropping ParsedView.agentI… |
| [ISS-278](../.knowledge/cards/20260828-1700-ISS-278.md) | [FIX-353](../.knowledge/cards/20260828-2353-FIX-353.md) | — | TokenUsageSummary.tsx:56 shows uncached input, not full input, beside a full total, so input+output… |
| [ISS-279](../.knowledge/cards/20260828-1901-ISS-279.md) | [FIX-336](../.knowledge/cards/20260828-2201-FIX-336.md) | [ISS-226](../.knowledge/cards/20260828-1550-ISS-226.md) | INFERRED sibling of ISS-226: LaunchWizard.tsx has exactly one handleSaveAsOverride (line 727) share… |
| [ISS-280](../.knowledge/cards/20260828-1902-ISS-280.md) | [FIX-336](../.knowledge/cards/20260828-2201-FIX-336.md) | [ISS-226](../.knowledge/cards/20260828-1550-ISS-226.md) | INFERRED sibling of ISS-226 (and distinct facet of ISS-225's function): IdeaInputPage.tsx handleSav… |
| [ISS-281](../.knowledge/cards/20260828-1902-ISS-281.md) | [FIX-335](../.knowledge/cards/20260828-1959-FIX-335.md) | — | proxy.ts redirects any session to /admin via traversal with no auth check of its own; admin/page.ts… |
| [ISS-283](../.knowledge/cards/20260828-1905-ISS-283.md) | [FIX-338](../.knowledge/cards/20260828-2221-FIX-338.md) | [ISS-228](../.knowledge/cards/20260828-1758-ISS-228.md) | INFERRED sibling of ISS-228: handleLaunchSaved seeds the same {mode}.draft via /workflow/create, hi… |
| [ISS-285](../.knowledge/cards/20260828-1745-ISS-285.md) | [FIX-357](../.knowledge/cards/20260828-2210-FIX-357.md), [FIX-358](../.knowledge/cards/20260829-0011-FIX-358.md) | — | PreviewPanel's terminal-failed default-tab effect (line ~779) lands /preview/full on Audit with no … |
| [ISS-286](../.knowledge/cards/20260828-1712-ISS-286.md) | [FIX-328](../.knowledge/cards/20260828-2014-FIX-328.md) | — | parsed.version from /runs/{id}/versions/{v} is captured but never read; reopenedRunIdFor ignores it… |
| [ISS-288](../.knowledge/cards/20260828-1715-ISS-288.md) | [FIX-339](../.knowledge/cards/20260828-2231-FIX-339.md) | [ISS-229](../.knowledge/cards/20260828-1601-ISS-229.md) | INFERRED sibling of ISS-229: modelFilter is read only by the modelRows .filter() at AnalyticsPage.t… |
| [ISS-289](../.knowledge/cards/20260828-1715-ISS-289.md) | [FIX-339](../.knowledge/cards/20260828-2231-FIX-339.md) | [ISS-229](../.knowledge/cards/20260828-1601-ISS-229.md) | INFERRED sibling of ISS-229: pipelineRows filters only on pipelineFilter (AnalyticsPage.tsx:245) an… |
| [ISS-290](../.knowledge/cards/20260828-1720-ISS-290.md) | [FIX-360](../.knowledge/cards/20260829-0024-FIX-360.md) | — | HOOK.md frontmatter compatible_agents lists ids never present in GET /api/agents/library — stale se… |
| [ISS-291](../.knowledge/cards/20260828-1917-ISS-291.md) | [FIX-363](../.knowledge/cards/20260829-0043-FIX-363.md) | — | AccountSettings.tsx:454 renders <Button> for "Manage plan" with no onClick prop at all — pure no-op… |
| [ISS-292](../.knowledge/cards/20260828-1918-ISS-292.md) | [FIX-361](../.knowledge/cards/20260829-0029-FIX-361.md), [FIX-382](../.knowledge/cards/20260829-0223-FIX-382.md), [FIX-439](../.knowledge/cards/20260831-1959-FIX-439.md) | — | GET/PUT /api/settings/preferences apply no tier filter to available_models or preferred_model; Acco… |
| [ISS-293](../.knowledge/cards/20260828-1924-ISS-293.md) | [FIX-364](../.knowledge/cards/20260829-0041-FIX-364.md), [FIX-423](../.knowledge/cards/20260831-1650-FIX-423.md) | — | ConstitutionRequest.content max_length=1_048_576 (settings.py:355), textarea has no maxLength; 4000… |
| [ISS-294](../.knowledge/cards/20260828-1725-ISS-294.md) | [FIX-328](../.knowledge/cards/20260828-2014-FIX-328.md) | — | reopenedRunIdFor (page.tsx:182-196) returns only parsed.runId for run-version, dropping parsed.vers… |
| [ISS-295](../.knowledge/cards/20260828-1726-ISS-295.md) | [FIX-366](../.knowledge/cards/20260828-2254-FIX-366.md) | — | Create-User form gates "Create User" only on non-empty Email/Password (no format regex), and POST /… |
| [ISS-296](../.knowledge/cards/20260828-1724-ISS-296.md) | [FIX-328](../.knowledge/cards/20260828-2014-FIX-328.md), [FIX-334](../.knowledge/cards/20260828-2149-FIX-334.md), [FIX-417](../.knowledge/cards/20260831-0110-FIX-417.md) | — | handleSelectVersion (PreviewPanel.tsx:549-564) only calls setViewingVersion, never router.push — ro… |
| [ISS-298](../.knowledge/cards/20260828-1729-ISS-298.md) | [FIX-369](../.knowledge/cards/20260829-0114-FIX-369.md) | — | error===quota branch in preview-fullscreen/page.tsx useEffect returns before the sessionStorage.__a… |
| [ISS-299](../.knowledge/cards/20260828-1730-ISS-299.md) | [FIX-351](../.knowledge/cards/20260828-2347-FIX-351.md), [FIX-368](../.knowledge/cards/20260829-0106-FIX-368.md) | — | canvas seeds an empty manifest from a workflowId with no existence check, so a bad id renders a wor… |
| [ISS-300](../.knowledge/cards/20260828-1726-ISS-300.md) | [FIX-328](../.knowledge/cards/20260828-2014-FIX-328.md), [FIX-334](../.knowledge/cards/20260828-2149-FIX-334.md) | — | PreviewPanel passes raw userStoryContent/pptContent/prototypeContent, not effUserStoryContent etc, … |
| [ISS-301](../.knowledge/cards/20260828-1740-ISS-301.md) | [FIX-370](../.knowledge/cards/20260829-0116-FIX-370.md) | — | HandoffWorkflow.tsx:216 renders "Handoff not found" whenever loadError is set, with no branch for a… |
| [ISS-302](../.knowledge/cards/20260828-1734-ISS-302.md) | [FIX-372](../.knowledge/cards/20260829-0141-FIX-372.md), [FIX-467](../.knowledge/cards/20260902-1100-FIX-467.md) | — | Delete dialog on /workflows only tracks deleteConfirmId, never the row name, so heading/body text i… |
| [ISS-303](../.knowledge/cards/20260828-1935-ISS-303.md) | [FIX-371](../.knowledge/cards/20260829-0131-FIX-371.md) | — | LibraryPage.tsx:520-526 cold-mount URL-seed effect has no BETA_WORKFLOWS check, unlike the card onC… |
| [ISS-304](../.knowledge/cards/20260828-1600-ISS-304.md) | [FIX-373](../.knowledge/cards/20260829-0143-FIX-373.md) | — | pipeline_complete.total_tokens (17931) disagrees with the sum of its own agent_complete events (104… |
| [ISS-306](../.knowledge/cards/20260828-1745-ISS-306.md) | [FIX-377](../.knowledge/cards/20260829-0158-FIX-377.md) | — | Fresh /create/ex_A4_human_gate load: Pick Language step carries gates:[before-human,conditional] se… |
| [ISS-311](../.knowledge/cards/20260828-1740-ISS-311.md) | [FIX-376](../.knowledge/cards/20260829-0152-FIX-376.md), [FIX-477](../.knowledge/cards/20260902-1400-FIX-477.md) | — | AgentLibrary excludes existingAgentIds from filteredAgents; the default user_stories workflow alrea… |
| [ISS-312](../.knowledge/cards/20260828-1941-ISS-312.md) | [FIX-374](../.knowledge/cards/20260829-0146-FIX-374.md), [FIX-479](../.knowledge/cards/20260902-1400-FIX-479.md) | — | handleFiles() isTextFile branch does content.slice(0, ATTACH_MAX_CHARS) with no truncation note, un… |
| [ISS-313](../.knowledge/cards/20260828-1946-ISS-313.md) | [FIX-318](../.knowledge/cards/20260827-0055-FIX-318.md), [FIX-380](../.knowledge/cards/20260829-0212-FIX-380.md), [FIX-449](../.knowledge/cards/20260901-1530-FIX-449.md) | — | PreviewPanel toolbar Download stays disabled forever when WorkflowRun.deliverable_filename is null … |
| [ISS-314](../.knowledge/cards/20260828-1946-ISS-314.md) | [FIX-378](../.knowledge/cards/20260829-0207-FIX-378.md), [FIX-446](../.knowledge/cards/20260901-1530-FIX-446.md) | — | PreviewPanel L1450 toolbar wrapper is flex items-center gap-1.5 flex-shrink-0 with no wrap/overflow… |
| [ISS-315](../.knowledge/cards/20260828-1750-ISS-315.md) | [FIX-375](../.knowledge/cards/20260829-0151-FIX-375.md), [FIX-469](../.knowledge/cards/20260902-1200-FIX-469.md) | — | ComposerPage.tsx:1075-1082 blocks Save workflow on an empty name by only focusing the input and set… |
| [ISS-316](../.knowledge/cards/20260828-1952-ISS-316.md) | [FIX-105](../.knowledge/cards/20260723-FIX-105.md), [FIX-229](../.knowledge/cards/20260812-0653-FIX-229.md), [FIX-381](../.knowledge/cards/20260829-0220-FIX-381.md), [FIX-484](../.knowledge/cards/20260902-1600-FIX-484.md) | — | resume_supersedes only checks pipeline_complete seq > cancelled seq, so a resumed run that instead … |
| [ISS-317](../.knowledge/cards/20260828-1755-ISS-317.md) | [FIX-379](../.knowledge/cards/20260829-0210-FIX-379.md) | — | StepsOverviewSpine derives its status-summary label as `failed = pipelineState?.failed \|\| agents.… |
| [ISS-318](../.knowledge/cards/20260828-1956-ISS-318.md) | [FIX-383](../.knowledge/cards/20260829-0025-FIX-383.md) | — | LibraryPage passes onSkillsChange to AgentCapabilitiesModal, which forces AgentSkillsPicker readOnl… |
| [ISS-319](../.knowledge/cards/20260828-1804-ISS-319.md) | [FIX-361](../.knowledge/cards/20260829-0029-FIX-361.md), [FIX-382](../.knowledge/cards/20260829-0223-FIX-382.md), [FIX-439](../.knowledge/cards/20260831-1959-FIX-439.md), [FIX-441](../.knowledge/cards/20260831-2001-FIX-441.md) | — | update_preferences commits then db.refresh(user), so a concurrent commit lands between them and the… |
| [ISS-320](../.knowledge/cards/20260828-1802-ISS-320.md) | [FIX-385](../.knowledge/cards/20260829-0241-FIX-385.md), [FIX-386](../.knowledge/cards/20260831-1020-FIX-386.md), [FIX-442](../.knowledge/cards/20260901-FIX-442.md), [FIX-452](../.knowledge/cards/20260901-1600-FIX-452.md), [FIX-478](../.knowledge/cards/20260902-1400-FIX-478.md) | — | handleDelete (AccountSettings.tsx:537-553) fires DELETE /api/settings/constitution on click with ze… |
| [ISS-321](../.knowledge/cards/20260828-2002-ISS-321.md) | — | — | [...view]/page.tsx never calls can_run_pipeline before rendering LaunchWizard, so any tier reaches … |
| [ISS-322](../.knowledge/cards/20260828-2007-ISS-322.md) | [FIX-384](../.knowledge/cards/20260829-0232-FIX-384.md), [FIX-408](../.knowledge/cards/20260829-0447-FIX-408.md) | — | api.ts:147 sends window.location.href = routes.login({ expired: true }) with no redirect param, so … |
| [ISS-323](../.knowledge/cards/20260828-1810-ISS-323.md) | [FIX-380](../.knowledge/cards/20260829-0212-FIX-380.md), [FIX-389](../.knowledge/cards/20260829-0253-FIX-389.md) | — | headerRegex /###\s+([\w./\-@][^\n]*\.\w+)\s*\n```.../g in parseAppBuilderFilesForIDE matches any ##… |
| [ISS-324](../.knowledge/cards/20260828-1815-ISS-324.md) | [FIX-387](../.knowledge/cards/20260829-0249-FIX-387.md) | — | handleCreateUser (admin/page.tsx) catches the 409 ApiError and calls showToast, but the bottom-righ… |
| [ISS-326](../.knowledge/cards/20260828-ISS-326.md) | [FIX-388](../.knowledge/cards/20260829-0053-FIX-388.md), [FIX-472](../.knowledge/cards/20260902-1200-FIX-472.md) | — | WorkflowDialog declares role="dialog"/aria-modal but has zero Escape/onKeyDown handling; only the C… |
| [ISS-327](../.knowledge/cards/20260828-2033-ISS-327.md) | [FIX-390](../.knowledge/cards/20260829-0303-FIX-390.md), [FIX-418](../.knowledge/cards/20260831-0110-FIX-418.md) | — | WorkflowDetailView.tsx renders agentIds.map((id) => {id}) with no id-to-name lookup, unlike the Lib… |
| [ISS-328](../.knowledge/cards/20260828-1834-ISS-328.md) | [FIX-391](../.knowledge/cards/20260829-0305-FIX-391.md), [FIX-400](../.knowledge/cards/20260829-0402-FIX-400.md) | — | WorkflowView.tsx:473 gates Run Workflow on ideaInput.trim() only, ignoring pipelineAgents.length; h… |
| [ISS-329](../.knowledge/cards/20260828-1838-ISS-329.md) | [FIX-392](../.knowledge/cards/20260829-0119-FIX-392.md) | — | skills_catalog.py:112 defaults category to "" when SKILL.md frontmatter omits the field; html-deck-… |
| [ISS-330](../.knowledge/cards/20260828-2041-ISS-330.md) | [FIX-342](../.knowledge/cards/20260828-2238-FIX-342.md), [FIX-456](../.knowledge/cards/20260901-1900-FIX-456.md) | — | agentsStatus/skillsStatus/hooksStatus only branch on "loading" (LibraryPage.tsx:732,793,815,893,911… |
| [ISS-331](../.knowledge/cards/20260828-1840-ISS-331.md) | [FIX-395](../.knowledge/cards/20260829-0338-FIX-395.md), [FIX-453](../.knowledge/cards/20260901-1600-FIX-453.md) | — | CONFIRMED: HookDetailModal.handleCopy (LibraryPage.tsx:351-355) awaits writeText with no catch — an… |
| [ISS-332](../.knowledge/cards/20260828-2041-ISS-332.md) | [FIX-394](../.knowledge/cards/20260829-0127-FIX-394.md), [FIX-395](../.knowledge/cards/20260829-0338-FIX-395.md) | — | FileTreeNode filters only file nodes on searchQuery (folder branch has no match check) and the foot… |
| [ISS-333](../.knowledge/cards/20260828-2044-ISS-333.md) | [FIX-343](../.knowledge/cards/20260828-2039-FIX-343.md), [FIX-468](../.knowledge/cards/20260902-1200-FIX-468.md) | — | ComposerPage.handleRunOnce (ComposerPage.tsx:939) has no pipelineAgents.length===0 guard -- a fresh… |
| [ISS-335](../.knowledge/cards/20260828-2040-ISS-335.md) | [FIX-342](../.knowledge/cards/20260828-2238-FIX-342.md), [FIX-456](../.knowledge/cards/20260901-1900-FIX-456.md) | — | Same missing length===0 branch (LibraryPage.tsx:735/818/914) reachable via activeCategory/skillCate… |
| [ISS-336](../.knowledge/cards/20260828-1846-ISS-336.md) | [FIX-340](../.knowledge/cards/20260828-2230-FIX-340.md), [FIX-457](../.knowledge/cards/20260901-1900-FIX-457.md) | [ISS-232](../.knowledge/cards/20260828-1627-ISS-232.md) | INFERRED sibling of ISS-232: useHooksCatalog.ts returns an unmemoized array like useSkillsCatalog, … |
| [ISS-337](../.knowledge/cards/20260828-1900-ISS-337.md) | [FIX-393](../.knowledge/cards/20260829-0325-FIX-393.md), [FIX-398](../.knowledge/cards/20260829-0352-FIX-398.md) | — | Login error motion.div (page.tsx:261-268) has no role=alert/status or aria-live, and focus stays on… |
| [ISS-338](../.knowledge/cards/20260828-2050-ISS-338.md) | [FIX-398](../.knowledge/cards/20260829-0352-FIX-398.md) | — | AccountSettings.tsx wires a show/hide toggle to Current and New password (L98-99, L292-306) but nev… |
| [ISS-339](../.knowledge/cards/20260828-1850-ISS-339.md) | [FIX-397](../.knowledge/cards/20260829-0349-FIX-397.md) | — | routes.ts:401-403 parses bare /settings as unknown while next.config.ts:27-28 redirects it server-s… |
| [ISS-342](../.knowledge/cards/20260828-2059-ISS-342.md) | [FIX-341](../.knowledge/cards/20260828-2236-FIX-341.md), [FIX-459](../.knowledge/cards/20260901-2100-FIX-459.md) | [ISS-244](../.knowledge/cards/20260828-1634-ISS-244.md) | INFERRED sibling of ISS-244: login/page.tsx ChallengeForm (L453/469/495/514 onChanges) never clears… |
| [ISS-343](../.knowledge/cards/20260828-2059-ISS-343.md) | [FIX-396](../.knowledge/cards/20260829-0348-FIX-396.md) | — | GET /api/prototype/fetch-url 502s with detail = raw socket.gaierror text; CustomTemplateModal rende… |
| [ISS-345](../.knowledge/cards/20260828-1900-ISS-345.md) | [FIX-400](../.knowledge/cards/20260829-0402-FIX-400.md), [FIX-479](../.knowledge/cards/20260902-1400-FIX-479.md) | — | WorkflowView.tsx onClick={() => setAttachedFiles(...)} at the chip remove button (~line 388) only f… |
| [ISS-350](../.knowledge/cards/20260828-2102-ISS-350.md) | [FIX-344](../.knowledge/cards/20260828-2046-FIX-344.md), [FIX-462](../.knowledge/cards/20260901-2100-FIX-462.md) | [ISS-238](../.knowledge/cards/20260828-1633-ISS-238.md) | Sibling of ISS-238: routes.ts:418-420 head==="analytics" has the same missing depth guard, but init… |
| [ISS-351](../.knowledge/cards/20260828-2103-ISS-351.md) | [FIX-402](../.knowledge/cards/20260829-0414-FIX-402.md) | — | FilesTab.tsx feeds formatSize() the JS string .length (UTF-16 code units) at every call site instea… |
| [ISS-353](../.knowledge/cards/20260828-2102-ISS-353.md) | [FIX-345](../.knowledge/cards/20260828-2250-FIX-345.md), [FIX-470](../.knowledge/cards/20260902-1200-FIX-470.md) | [ISS-245](../.knowledge/cards/20260828-1631-ISS-245.md) | INFERRED sibling of ISS-245: ComposerPage.tsx Save button (disabled={saving} at L1083) gates handle… |
| [ISS-354](../.knowledge/cards/20260828-2103-ISS-354.md) | [FIX-345](../.knowledge/cards/20260828-2250-FIX-345.md) | [ISS-245](../.knowledge/cards/20260828-1631-ISS-245.md) | INFERRED sibling of ISS-245: SecuritySection.tsx email-MFA toggle (disabled={pending} at L317) gate… |
| [ISS-355](../.knowledge/cards/20260828-2105-ISS-355.md) | [FIX-399](../.knowledge/cards/20260829-0357-FIX-399.md) | — | AgentDetailPanel.tsx:412 does String(v) on tool-call args, so an array-of-objects value (e.g. write… |
| [ISS-356](../.knowledge/cards/20260828-1910-ISS-356.md) | [FIX-404](../.knowledge/cards/20260829-0418-FIX-404.md) | — | SandboxTab.tsx:1039-1043's "Workspace expired" empty state hardcodes "the deliverable is still on t… |
| [ISS-357](../.knowledge/cards/20260828-1915-ISS-357.md) | [FIX-332](../.knowledge/cards/20260828-1915-FIX-332.md), [FIX-430](../.knowledge/cards/20260831-1827-FIX-430.md) | — | The fixture builds its own FastAPI() and includes only auth_router, so app.main's RequestValidation… |
| [ISS-358](../.knowledge/cards/20260828-2118-ISS-358.md) | [FIX-354](../.knowledge/cards/20260828-2357-FIX-354.md), [FIX-406](../.knowledge/cards/20260829-0431-FIX-406.md) | — | useRunChat.ts upsertUserMessage/upsertNarratorMessage stamp createdAt with Date.now() on every even… |
| [ISS-359](../.knowledge/cards/20260828-1918-ISS-359.md) | [FIX-403](../.knowledge/cards/20260829-0216-FIX-403.md) | — | detailSkill.content renders in a <pre> tag with no markdown parser, while /library/skills/<id> uses… |
| [ISS-360](../.knowledge/cards/20260828-1917-ISS-360.md) | [FIX-407](../.knowledge/cards/20260829-0441-FIX-407.md) | — | Closing a hook/skill/agent detail view resets that tab search text and category filter — actually l… |
| [ISS-361](../.knowledge/cards/20260828-2120-ISS-361.md) | [FIX-346](../.knowledge/cards/20260828-2314-FIX-346.md) | [ISS-247](../.knowledge/cards/20260828-1637-ISS-247.md) | INFERRED sibling of ISS-247: LaunchWizard.tsx:1046/583-584/243 wires the same ReviewGatesSection to… |
| [ISS-363](../.knowledge/cards/20260828-2129-ISS-363.md) | [FIX-349](../.knowledge/cards/20260828-2324-FIX-349.md), [FIX-365](../.knowledge/cards/20260829-0045-FIX-365.md) | — | AgentsPopup never snapshots pipelineAgents at open; Cancel (onClick={onClose}) only hides the modal… |
| [ISS-364](../.knowledge/cards/20260828-2130-ISS-364.md) | [FIX-349](../.knowledge/cards/20260828-2324-FIX-349.md), [FIX-365](../.knowledge/cards/20260829-0045-FIX-365.md) | [ISS-363](../.knowledge/cards/20260828-2129-ISS-363.md) | INFERRED: ConfigLeversFlat.updateLever -> onSelectionsChange -> selectionsRef.current is the same l… |
| [ISS-365](../.knowledge/cards/20260828-2131-ISS-365.md) | [FIX-349](../.knowledge/cards/20260828-2324-FIX-349.md), [FIX-365](../.knowledge/cards/20260829-0045-FIX-365.md) | [ISS-363](../.knowledge/cards/20260828-2129-ISS-363.md) | INFERRED: handleAddAgent/handleRemoveAgent/handleReorderAgents write setPipelineAgents exactly like… |
| [ISS-366](../.knowledge/cards/20260828-2132-ISS-366.md) | [FIX-349](../.knowledge/cards/20260828-2324-FIX-349.md), [FIX-365](../.knowledge/cards/20260829-0045-FIX-365.md) | [ISS-363](../.knowledge/cards/20260828-2129-ISS-363.md) | INFERRED: LaunchWizard.tsx wires onClose/onReorder/onSelectionsChange to AgentsPopup identically to… |
| [ISS-368](../.knowledge/cards/20260828-1927-ISS-368.md) | [FIX-348](../.knowledge/cards/20260828-2321-FIX-348.md) | [ISS-246](../.knowledge/cards/20260828-1657-ISS-246.md) | The Advanced modal "Reset to default" button (CanvasView.tsx:2249) is also disabled via !onRunConfi… |
| [ISS-369](../.knowledge/cards/20260828-1933-ISS-369.md) | [FIX-405](../.knowledge/cards/20260829-0423-FIX-405.md) | — | Daily Activity chart's hover tooltip shows the raw unformatted token count: BarChart.tsx:85-89's de… |
| [ISS-370](../.knowledge/cards/20260828-2136-ISS-370.md) | [FIX-410](../.knowledge/cards/20260829-0249-FIX-410.md) | — | IntegrationsCard.tsx:147 uses `keyName \|\| "Default"`, a truthy whitespace string skips the fallba… |
| [ISS-374](../.knowledge/cards/20260828-2146-ISS-374.md) | [FIX-351](../.knowledge/cards/20260828-2347-FIX-351.md), [FIX-370](../.knowledge/cards/20260829-0116-FIX-370.md) | — | getWorkflowDetail 404 caught at IdeaInputPage.tsx:1172 clears manifestAgents; roster falls to empty… |
| [ISS-375](../.knowledge/cards/20260828-2147-ISS-375.md) | [FIX-351](../.knowledge/cards/20260828-2347-FIX-351.md) | — | IdeaInputPage.tsx:1172 catch never branches on ApiError.status; a real composed/custom workflow wit… |
| [ISS-376](../.knowledge/cards/20260828-2152-ISS-376.md) | [FIX-347](../.knowledge/cards/20260828-2318-FIX-347.md), [FIX-464](../.knowledge/cards/20260901-2100-FIX-464.md) | — | page.tsx CreateRoute() defaults any raw mode to prototype in place with zero fallback of its own; r… |
| [ISS-379](../.knowledge/cards/20260828-2209-ISS-379.md) | [FIX-355](../.knowledge/cards/20260828-2358-FIX-355.md) | [ISS-273](../.knowledge/cards/20260828-1653-ISS-273.md) | INFERRED sibling of ISS-273: workflowRunFailed (page.tsx:409) sets true on failure (:3706) but neve… |
| [ISS-380](../.knowledge/cards/20260828-2209-ISS-380.md) | [FIX-355](../.knowledge/cards/20260828-2358-FIX-355.md), [FIX-368](../.knowledge/cards/20260829-0106-FIX-368.md) | [ISS-273](../.knowledge/cards/20260828-1653-ISS-273.md) | INFERRED sibling of ISS-273: the workflow-run catch (page.tsx:3692-3707) treats ANY non-401 error a… |
| [ISS-382](../.knowledge/cards/20260828-2008-ISS-382.md) | [FIX-350](../.knowledge/cards/20260828-2340-FIX-350.md), [FIX-471](../.knowledge/cards/20260902-1200-FIX-471.md) | — | CanvasNode.tsx:763-802 chip row shows Validator/Gate/Retry only, no Tools chip — restriction invisi… |
| [ISS-383](../.knowledge/cards/20260828-2021-ISS-383.md) | [FIX-409](../.knowledge/cards/20260829-0449-FIX-409.md) | — | CodeView in SandboxTab.tsx never calls EditorState.readOnly/EditorView.editable despite its own doc… |
| [ISS-384](../.knowledge/cards/20260828-2221-ISS-384.md) | [FIX-338](../.knowledge/cards/20260828-2221-FIX-338.md), [FIX-479](../.knowledge/cards/20260902-1400-FIX-479.md) | — | savedName/savedDescription are restored into state at LaunchWizard.tsx:311-313 but only ever passed… |
| [ISS-385](../.knowledge/cards/20260828-2225-ISS-385.md) | [FIX-353](../.knowledge/cards/20260828-2353-FIX-353.md) | [ISS-278](../.knowledge/cards/20260828-1700-ISS-278.md) | INFERRED sibling of ISS-278: ChatTokenWidget.tsx:93-124 duplicates the identical uncachedInput-vs-t… |
| [ISS-386](../.knowledge/cards/20260828-2228-ISS-386.md) | [FIX-359](../.knowledge/cards/20260829-0014-FIX-359.md), [FIX-422](../.knowledge/cards/20260901-1100-FIX-422.md) | — | runStepsAgent(id, agentId) has no version param unlike runSteps/runFiles/runWorkspace/runAudit, tho… |
| [ISS-387](../.knowledge/cards/20260828-2228-ISS-387.md) | [FIX-359](../.knowledge/cards/20260829-0014-FIX-359.md) | — | setSelectedAgentId/setSelectedTaskIndex never push history, so Back after selecting an agent/task s… |
| [ISS-388](../.knowledge/cards/20260828-2234-ISS-388.md) | [FIX-358](../.knowledge/cards/20260829-0011-FIX-358.md), [FIX-448](../.knowledge/cards/20260901-1530-FIX-448.md) | [ISS-285](../.knowledge/cards/20260828-1745-ISS-285.md) | reopenTabFor has no run-preview-full case, so opening it on a BUILDING run lands on Steps (PreviewP… |
| [ISS-389](../.knowledge/cards/20260828-2234-ISS-389.md) | [FIX-358](../.knowledge/cards/20260829-0011-FIX-358.md), [FIX-448](../.knowledge/cards/20260901-1530-FIX-448.md) | — | A failed run with 0 hook_runs hits ISS-285's Audit substitution AND AuditTab.tsx:701's own "No audi… |
| [ISS-390](../.knowledge/cards/20260828-2048-ISS-390.md) | [FIX-357](../.knowledge/cards/20260828-2210-FIX-357.md), [FIX-358](../.knowledge/cards/20260829-0011-FIX-358.md) | — | page.tsx:3035 gates reopenedRunStatus to failed/cancelled/degraded only, so it is always undefined … |
| [ISS-391](../.knowledge/cards/20260828-2049-ISS-391.md) | [FIX-357](../.knowledge/cards/20260828-2210-FIX-357.md) | — | WorkflowHistory.tsx:593-596 tests only failed/cancelled/degraded like PreviewPanel did — a selected… |
| [ISS-395](../.knowledge/cards/20260828-2050-ISS-395.md) | [FIX-357](../.knowledge/cards/20260828-2210-FIX-357.md) | — | RunDetailPage.tsx:230-233 omits "diverted" from its failed/cancelled/degraded triad, so a diverted … |
| [ISS-397](../.knowledge/cards/20260828-2105-ISS-397.md) | [FIX-363](../.knowledge/cards/20260829-0043-FIX-363.md) | — | AppHeader.tsx:519-526 basic-tier Upgrade button only calls onNavigate("settings"); no upgrade UI ex… |
| [ISS-399](../.knowledge/cards/20260828-2308-ISS-399.md) | [FIX-360](../.knowledge/cards/20260829-0024-FIX-360.md), [FIX-476](../.knowledge/cards/20260902-1400-FIX-476.md) | [ISS-290](../.knowledge/cards/20260828-1720-ISS-290.md) | INFERRED sibling of ISS-290: same stale HOOK.md ids feed an exact .includes(agent.id) filter with n… |
| [ISS-401](../.knowledge/cards/20260828-2121-ISS-401.md) | [FIX-367](../.knowledge/cards/20260828-2256-FIX-367.md) | [ISS-404](../.knowledge/cards/20260828-2120-ISS-404.md) | INFERRED sibling of ISS-404: admin.py:561 reuses the same false "managed outside" claim for auth_pr… |
| [ISS-402](../.knowledge/cards/20260828-2121-ISS-402.md) | [FIX-364](../.knowledge/cards/20260829-0041-FIX-364.md), [FIX-423](../.knowledge/cards/20260831-1650-FIX-423.md) | [ISS-293](../.knowledge/cards/20260828-1924-ISS-293.md) | _inject_constitution (factory.py:673-699), called from _compose_system_prompt:586 every run, inject… |
| [ISS-404](../.knowledge/cards/20260828-2120-ISS-404.md) | [FIX-367](../.knowledge/cards/20260828-2256-FIX-367.md) | — | SecuritySection.tsx:236-239 falsely claims a break-glass/local account's credentials are managed ou… |
| [ISS-405](../.knowledge/cards/20260828-2324-ISS-405.md) | [FIX-366](../.knowledge/cards/20260828-2254-FIX-366.md), [FIX-465](../.knowledge/cards/20260901-2100-FIX-465.md) | — | CreateUserRequest.email (admin.py:131) has no EmailStr/min_length; an empty-string POST would persi… |
| [ISS-409](../.knowledge/cards/20260828-2148-ISS-409.md) | [FIX-370](../.knowledge/cards/20260829-0116-FIX-370.md) | [ISS-301](../.knowledge/cards/20260828-1740-ISS-301.md) | INFERRED sibling of ISS-301: IntegrationsCard.tsx:90's empty catch leaves patStatus/keys at their u… |
| [ISS-411](../.knowledge/cards/20260828-2147-ISS-411.md) | [FIX-370](../.knowledge/cards/20260829-0116-FIX-370.md) | [ISS-301](../.knowledge/cards/20260828-1740-ISS-301.md) | INFERRED sibling of ISS-301: loadError\|\|!session (HandoffWorkflow.tsx:216) fires on a failed post… |
| [ISS-413](../.knowledge/cards/20260828-2357-ISS-413.md) | [FIX-354](../.knowledge/cards/20260828-2357-FIX-354.md), [FIX-406](../.knowledge/cards/20260829-0431-FIX-406.md) | — | run_events.created_at exists on the row but get_run_events returns only seq/event_id/type/payload_j… |
| [ISS-414](../.knowledge/cards/20260828-2202-ISS-414.md) | [FIX-372](../.knowledge/cards/20260829-0141-FIX-372.md), [FIX-467](../.knowledge/cards/20260902-1100-FIX-467.md) | [ISS-302](../.knowledge/cards/20260828-1734-ISS-302.md) | WorkflowHistory DeleteModal (L1237) takes no name prop; deleteConfirmId (L179) stores only the run … |
| [ISS-415](../.knowledge/cards/20260828-2202-ISS-415.md) | [FIX-372](../.knowledge/cards/20260829-0141-FIX-372.md), [FIX-465](../.knowledge/cards/20260901-2100-FIX-465.md) | [ISS-302](../.knowledge/cards/20260828-1734-ISS-302.md) | admin/page.tsx deleteConfirm (L126) stores only user.id (L441); dialog (L525-556) has no user email… |
| [ISS-416](../.knowledge/cards/20260828-2210-ISS-416.md) | [FIX-371](../.knowledge/cards/20260829-0131-FIX-371.md) | — | LibraryPage.tsx:598-604 skills branch of the same cold-mount effect has no isBeta check; unreproduc… |
| [ISS-417](../.knowledge/cards/20260828-2230-ISS-417.md) | [FIX-373](../.knowledge/cards/20260829-0143-FIX-373.md) | [ISS-304](../.knowledge/cards/20260828-1600-ISS-304.md) | INFERRED sibling of ISS-304: TokenUsageSummary.tsx:19-28, mounted in the Steps tab, destructures th… |
| [ISS-418](../.knowledge/cards/20260828-2231-ISS-418.md) | [FIX-373](../.knowledge/cards/20260829-0143-FIX-373.md), [FIX-483](../.knowledge/cards/20260902-1600-FIX-483.md) | — | INFERRED inverse of ISS-304: analytics.py:189-195 sums only the persisted token_usage column, so pl… |
| [ISS-420](../.knowledge/cards/20260829-0021-ISS-420.md) | [FIX-376](../.knowledge/cards/20260829-0152-FIX-376.md), [FIX-477](../.knowledge/cards/20260902-1400-FIX-477.md) | [ISS-311](../.knowledge/cards/20260828-1740-ISS-311.md) | IdeaInputPage.tsx:1900-1902 leaves the Advanced button unguarded before a migration sub-pipeline is… |
| [ISS-421](../.knowledge/cards/20260829-0020-ISS-421.md) | [FIX-376](../.knowledge/cards/20260829-0152-FIX-376.md), [FIX-477](../.knowledge/cards/20260902-1400-FIX-477.md) | [ISS-311](../.knowledge/cards/20260828-1740-ISS-311.md) | IdeaInputPage.tsx:902 and LaunchWizard.tsx:147-148 both seed AgentLibrary existingAgentIds from 100… |
| [ISS-423](../.knowledge/cards/20260829-0026-ISS-423.md) | [FIX-374](../.knowledge/cards/20260829-0146-FIX-374.md), [FIX-479](../.knowledge/cards/20260902-1400-FIX-479.md) | [ISS-312](../.knowledge/cards/20260828-1941-ISS-312.md) | INFERRED: LaunchWizard.tsx onFilesPicked (:653-659) forks the same unflagged content.slice(0, ATTAC… |
| [ISS-429](../.knowledge/cards/20260829-0022-ISS-429.md) | [FIX-377](../.knowledge/cards/20260829-0158-FIX-377.md), [FIX-479](../.knowledge/cards/20260902-1400-FIX-479.md) | — | ReviewGatesSection at LaunchWizard.tsx:1072 and CanvasConfigRail's Prompt-User toggle share ISS-306… |
| [ISS-430](../.knowledge/cards/20260829-0029-ISS-430.md) | [FIX-361](../.knowledge/cards/20260829-0029-FIX-361.md), [FIX-421](../.knowledge/cards/20260831-FIX-421.md) | — | Deferred half of ISS-292: get_preferences now projects AVAILABLE_MODELS with an allowed flag per ti… |
| [ISS-431](../.knowledge/cards/20260829-0038-ISS-431.md) | [FIX-375](../.knowledge/cards/20260829-0151-FIX-375.md), [FIX-469](../.knowledge/cards/20260902-1200-FIX-469.md) | [ISS-315](../.knowledge/cards/20260828-1750-ISS-315.md) | INFERRED sibling of ISS-315: ComposerPage.tsx:1076-1090 Run once guard (briefText.trim().length<3) … |
| [ISS-433](../.knowledge/cards/20260829-0040-ISS-433.md) | [FIX-378](../.knowledge/cards/20260829-0207-FIX-378.md), [FIX-446](../.knowledge/cards/20260901-1530-FIX-446.md) | [ISS-314](../.knowledge/cards/20260828-1946-ISS-314.md) | PrototypePreview.tsx:502 browser-chrome bar (dots, URL pill, zoom x3, divider, Tweaks, Source, Open… |
| [ISS-435](../.knowledge/cards/20260828-2253-ISS-435.md) | [FIX-381](../.knowledge/cards/20260829-0220-FIX-381.md), [FIX-484](../.knowledge/cards/20260902-1600-FIX-484.md) | [ISS-316](../.knowledge/cards/20260828-1952-ISS-316.md) | INFERRED: complete_seqs excludes degraded pipeline_complete events, so resume_supersedes never fire… |
| [ISS-436](../.knowledge/cards/20260828-2253-ISS-436.md) | [FIX-381](../.knowledge/cards/20260829-0220-FIX-381.md), [FIX-484](../.knowledge/cards/20260902-1600-FIX-484.md) | [ISS-316](../.knowledge/cards/20260828-1952-ISS-316.md) | INFERRED: degraded = any(pipeline_complete degraded) over the WHOLE multi-attempt tail with no reat… |
| [ISS-437](../.knowledge/cards/20260828-2253-ISS-437.md) | [FIX-381](../.knowledge/cards/20260829-0220-FIX-381.md), [FIX-484](../.knowledge/cards/20260902-1600-FIX-484.md) | [ISS-316](../.knowledge/cards/20260828-1952-ISS-316.md) | INFERRED, inverse of ISS-316: failed = any(pipeline_failed) over the whole multi-attempt tail with … |
| [ISS-438](../.knowledge/cards/20260829-0056-ISS-438.md) | [FIX-379](../.knowledge/cards/20260829-0210-FIX-379.md) | — | RunChatLane.tsx:579 derives errored from the same stale pipelineState.agents[].status==="error" as … |
| [ISS-439](../.knowledge/cards/20260829-0057-ISS-439.md) | [FIX-379](../.knowledge/cards/20260829-0210-FIX-379.md) | — | AgentDetailPanel.tsx:947 derives isError from the same stale pipelineState.agents[].status==="error… |
| [ISS-440](../.knowledge/cards/20260829-0058-ISS-440.md) | [FIX-379](../.knowledge/cards/20260829-0210-FIX-379.md) | — | useWorkflow.ts:771-774 stamps status="error" on every degraded run's agents_failed id, so resuming … |
| [ISS-441](../.knowledge/cards/20260828-2257-ISS-441.md) | — | [ISS-318](../.knowledge/cards/20260828-1956-ISS-318.md) | AgentsPopup.tsx:531-532 shadows the propHooks/propAttachHook params with ctx.attachedHooks/ctx.atta… |
| [ISS-470](../.knowledge/cards/20260828-2310-ISS-470.md) | [FIX-382](../.knowledge/cards/20260829-0223-FIX-382.md), [FIX-439](../.knowledge/cards/20260831-1959-FIX-439.md), [FIX-441](../.knowledge/cards/20260831-2001-FIX-441.md) | — | Same commit-then-refresh(row) shape as ISS-319: a concurrent PUT could report the OTHER PATs github… |
| [ISS-471](../.knowledge/cards/20260828-2310-ISS-471.md) | [FIX-382](../.knowledge/cards/20260829-0223-FIX-382.md), [FIX-439](../.knowledge/cards/20260831-1959-FIX-439.md), [FIX-441](../.knowledge/cards/20260831-2001-FIX-441.md) | [ISS-319](../.knowledge/cards/20260828-1804-ISS-319.md) | Same race as ISS-319: _to_response(user, db) reads user.tier/is_admin post-refresh, so a concurrent… |
| [ISS-480](../.knowledge/cards/20260828-2320-ISS-480.md) | [FIX-385](../.knowledge/cards/20260829-0241-FIX-385.md), [FIX-452](../.knowledge/cards/20260901-1600-FIX-452.md), [FIX-478](../.knowledge/cards/20260902-1400-FIX-478.md) | [ISS-320](../.knowledge/cards/20260828-1802-ISS-320.md) | deleteSkill (SkillManager.tsx:99-114) wired to onClick:221 fires DELETE with zero confirm, same gap… |
| [ISS-481](../.knowledge/cards/20260828-2321-ISS-481.md) | [FIX-385](../.knowledge/cards/20260829-0241-FIX-385.md) | [ISS-320](../.knowledge/cards/20260828-1802-ISS-320.md) | handleDeletePat/handleRevoke (IntegrationsCard.tsx:123-139/161-176) wired to onClick with zero conf… |
| [ISS-482](../.knowledge/cards/20260828-2322-ISS-482.md) | [FIX-385](../.knowledge/cards/20260829-0241-FIX-385.md), [FIX-386](../.knowledge/cards/20260831-1020-FIX-386.md), [FIX-421](../.knowledge/cards/20260831-FIX-421.md) | — | Tabs onChange (AccountSettings.tsx:230-234) unmounts ConstitutionSection, losing its local content … |
| [ISS-483](../.knowledge/cards/20260829-0133-ISS-483.md) | [FIX-389](../.knowledge/cards/20260829-0253-FIX-389.md) | — | FilesTab.tsx:196-258 forks PreviewPanel's broken markdown-heading regex; Files-tab project.zip down… |
| [ISS-484](../.knowledge/cards/20260829-0133-ISS-484.md) | [FIX-389](../.knowledge/cards/20260829-0253-FIX-389.md) | — | WorkflowHistory.tsx:74-105 forks the same broken regex; reopened-run IDE preview also lists/downloa… |
| [ISS-485](../.knowledge/cards/20260829-0133-ISS-485.md) | [FIX-389](../.knowledge/cards/20260829-0253-FIX-389.md) | — | boldRegex Format 3 in all 3 forks shares headerRegex's unbounded span — a bolded term before a fenc… |
| [ISS-486](../.knowledge/cards/20260828-2335-ISS-486.md) | [FIX-384](../.knowledge/cards/20260829-0232-FIX-384.md) | — | A protected route's own query string (e.g. /analytics?range=&pipeline=) is untested by ISS-322's tw… |
| [ISS-487](../.knowledge/cards/20260829-0138-ISS-487.md) | [FIX-387](../.knowledge/cards/20260829-0249-FIX-387.md) | — | showToast (admin/page.tsx:141-144) never clearTimeouts its prior 3.5s dismiss timer, so a 2nd call … |
| [ISS-489](../.knowledge/cards/20260829-0150-ISS-489.md) | [FIX-388](../.knowledge/cards/20260829-0053-FIX-388.md), [FIX-472](../.knowledge/cards/20260902-1200-FIX-472.md) | [ISS-326](../.knowledge/cards/20260828-ISS-326.md) | AgentSkillsPicker skill-detail modal (AgentSkillsPicker.tsx:251-289) has role="dialog" but zero Esc… |
| [ISS-490](../.knowledge/cards/20260828-2351-ISS-490.md) | [FIX-390](../.knowledge/cards/20260829-0303-FIX-390.md) | — | custom-agent:<instance_id> ids resolve via workflow.manifest.steps[].name, not the agents/library c… |
| [ISS-491](../.knowledge/cards/20260829-0149-ISS-491.md) | [FIX-388](../.knowledge/cards/20260829-0053-FIX-388.md), [FIX-476](../.knowledge/cards/20260902-1400-FIX-476.md) | [ISS-326](../.knowledge/cards/20260828-ISS-326.md) | AgentCapabilitiesModal (AgentsPopup.tsx:605-642) has role="dialog" but zero Escape handling anywher… |
| [ISS-492](../.knowledge/cards/20260829-0150-ISS-492.md) | [FIX-391](../.knowledge/cards/20260829-0305-FIX-391.md), [FIX-461](../.knowledge/cards/20260901-2100-FIX-461.md) | [ISS-328](../.knowledge/cards/20260828-1834-ISS-328.md) | INFERRED sibling of ISS-328: app/workflow/page.tsx never passes pipelineState/onResetPipeline/onVie… |
| [ISS-500](../.knowledge/cards/20260829-0006-ISS-500.md) | [FIX-394](../.knowledge/cards/20260829-0127-FIX-394.md), [FIX-447](../.knowledge/cards/20260901-1530-FIX-447.md) | [ISS-332](../.knowledge/cards/20260828-2041-ISS-332.md) | INFERRED sibling of ISS-332: the same broken FileTreeNode/footer ships unmodified to PreviewPanel.t… |
| [ISS-501](../.knowledge/cards/20260829-0006-ISS-501.md) | [FIX-394](../.knowledge/cards/20260829-0127-FIX-394.md) | — | INFERRED inverse of ISS-332: expandedPaths never reacts to searchQuery, so a match inside a folder … |
| [ISS-502](../.knowledge/cards/20260829-0006-ISS-502.md) | [FIX-394](../.knowledge/cards/20260829-0127-FIX-394.md) | — | INFERRED boundary case of ISS-332: a zero-match query leaves every folder in the tree rendered empt… |
| [ISS-555](../.knowledge/cards/20260829-0208-ISS-555.md) | [FIX-395](../.knowledge/cards/20260829-0338-FIX-395.md), [FIX-453](../.knowledge/cards/20260901-1600-FIX-453.md) | — | SkillDetailModal.handleCopy (LibraryPage.tsx:201-205) has the identical unguarded await-writeText-n… |
| [ISS-556](../.knowledge/cards/20260829-0208-ISS-556.md) | [FIX-395](../.knowledge/cards/20260829-0338-FIX-395.md) | — | InputPromptSection.handleCopy (AgentDetailPanel.tsx:446-450) fires writeText unawaited and sets cop… |
| [ISS-557](../.knowledge/cards/20260829-0208-ISS-557.md) | [FIX-395](../.knowledge/cards/20260829-0338-FIX-395.md) | — | CodeViewer.handleCopy (AppBuilderPreview.tsx:240-246) fires writeText unawaited, setCopied(true) un… |
| [ISS-558](../.knowledge/cards/20260829-0208-ISS-558.md) | [FIX-395](../.knowledge/cards/20260829-0338-FIX-395.md) | — | MarkdownPreview.handleCopyAll (L49-53) and CodeBlock.handleCopy (L174-178) both fire writeText unaw… |
| [ISS-559](../.knowledge/cards/20260829-0208-ISS-559.md) | [FIX-395](../.knowledge/cards/20260829-0338-FIX-395.md) | [ISS-556](../.knowledge/cards/20260829-0208-ISS-556.md) | UserStoryPreview.handleCopy (UserStoryPreview.tsx:47-51) fires writeText unawaited, setCopied(true)… |
| [ISS-560](../.knowledge/cards/20260829-0208-ISS-560.md) | [FIX-395](../.knowledge/cards/20260829-0338-FIX-395.md) | — | PrototypePreview.handleCopySource (PrototypePreview.tsx:391-398) chains .then() with no .catch, ide… |
| [ISS-561](../.knowledge/cards/20260829-0208-ISS-561.md) | [FIX-395](../.knowledge/cards/20260829-0338-FIX-395.md), [FIX-453](../.knowledge/cards/20260901-1600-FIX-453.md) | — | handleCopyInstall (L73-78) and the API-key copy button (L316-323) both use .then() with no .catch; … |
| [ISS-570](../.knowledge/cards/20260829-0004-ISS-570.md) | [FIX-392](../.knowledge/cards/20260829-0119-FIX-392.md) | — | Same skills_catalog.py:112 empty-category default as ISS-329 makes html-deck-to-pptx unreachable vi… |
| [ISS-571](../.knowledge/cards/20260829-0004-ISS-571.md) | [FIX-392](../.knowledge/cards/20260829-0119-FIX-392.md) | — | hooks.py:33 filters {e.event for e in entries if e.event} exactly like skills.py:35; a HOOK.md even… |
| [ISS-572](../.knowledge/cards/20260829-0019-ISS-572.md) | [FIX-397](../.knowledge/cards/20260829-0349-FIX-397.md) | — | routes.ts:392-399 returns unknown for /library/agents\|skills\|hooks (2 segs, no slug) — same missi… |
| [ISS-574](../.knowledge/cards/20260829-0220-ISS-574.md) | [FIX-393](../.knowledge/cards/20260829-0325-FIX-393.md) | — | isExpired banner (page.tsx:261-269) has the same missing role=alert/aria-live as ISS-337's error ba… |
| [ISS-575](../.knowledge/cards/20260829-0220-ISS-575.md) | [FIX-393](../.knowledge/cards/20260829-0325-FIX-393.md) | — | ChallengeForm error div (page.tsx:446-450) has the same missing role=alert/aria-live as ISS-337's m… |
| [ISS-576](../.knowledge/cards/20260829-0218-ISS-576.md) | [FIX-398](../.knowledge/cards/20260829-0352-FIX-398.md) | — | login/page.tsx imports only Mail/Lock, never Eye/EyeOff; ChallengeForm New password (L455-470) and … |
| [ISS-577](../.knowledge/cards/20260829-0219-ISS-577.md) | [FIX-398](../.knowledge/cards/20260829-0352-FIX-398.md) | — | admin/page.tsx imports no Eye/EyeOff; the Create-User modal Password input (L494-499) is hardcoded … |
| [ISS-580](../.knowledge/cards/20260829-0236-ISS-580.md) | [FIX-401](../.knowledge/cards/20260829-0206-FIX-401.md) | [ISS-340](../.knowledge/cards/20260828-1856-ISS-340.md) | Same unconditional ComposerPage.tsx:478 deliverableLabel = PIPELINE_LABEL.custom also fires for a s… |
| [ISS-581](../.knowledge/cards/20260829-0241-ISS-581.md) | [FIX-385](../.knowledge/cards/20260829-0241-FIX-385.md), [FIX-421](../.knowledge/cards/20260831-FIX-421.md) | — | ConstitutionSection's mount GET fires twice and the late response overwrites typed content, so the … |
| [ISS-583](../.knowledge/cards/20260829-0234-ISS-583.md) | [FIX-400](../.knowledge/cards/20260829-0402-FIX-400.md), [FIX-479](../.knowledge/cards/20260902-1400-FIX-479.md) | [ISS-345](../.knowledge/cards/20260828-1900-ISS-345.md) | INFERRED sibling of ISS-345: attach (WorkflowView.tsx:340) appends a NEW marker block per event, jo… |
| [ISS-584](../.knowledge/cards/20260829-0243-ISS-584.md) | [FIX-396](../.knowledge/cards/20260829-0348-FIX-396.md) | [ISS-343](../.knowledge/cards/20260828-2059-ISS-343.md) | PPTTemplateGallery.tsx:88 imports and renders the same CustomTemplateModal as TemplateGallery.tsx, … |
| [ISS-585](../.knowledge/cards/20260829-0256-ISS-585.md) | [FIX-399](../.knowledge/cards/20260829-0357-FIX-399.md) | — | ToolCallsSection (AgentDetailPanel.tsx:1104) has no isRunning gate, so ISS-355's String(v) [object … |
| [ISS-586](../.knowledge/cards/20260829-0258-ISS-586.md) | [FIX-404](../.knowledge/cards/20260829-0418-FIX-404.md) | [ISS-356](../.knowledge/cards/20260828-1910-ISS-356.md) | INFERRED sibling of ISS-356: SandboxTab.tsx:842-849 gives the component no status/deliverable prop … |
| [ISS-587](../.knowledge/cards/20260829-0257-ISS-587.md) | [FIX-402](../.knowledge/cards/20260829-0414-FIX-402.md) | [ISS-351](../.knowledge/cards/20260828-2103-ISS-351.md) | PrototypePreview.tsx:570 labels renderedHtml.length/1024 as KB in the source view — UTF-16 char cou… |
| [ISS-588](../.knowledge/cards/20260829-0257-ISS-588.md) | [FIX-402](../.knowledge/cards/20260829-0414-FIX-402.md) | [ISS-351](../.knowledge/cards/20260828-2103-ISS-351.md) | AppBuilderPreview.tsx:556 sums f.content.length across files for "KB total" — UTF-16 char count, no… |
| [ISS-589](../.knowledge/cards/20260829-0257-ISS-589.md) | [FIX-402](../.knowledge/cards/20260829-0414-FIX-402.md) | [ISS-351](../.knowledge/cards/20260828-2103-ISS-351.md) | CustomTemplateModal.tsx:80 gates the 2MB cap on text.length and :232/:267 label it "KB" from .lengt… |
| [ISS-590](../.knowledge/cards/20260829-0113-ISS-590.md) | [FIX-403](../.knowledge/cards/20260829-0216-FIX-403.md) | — | Same AgentSkillsPicker.tsx:280-283 <pre> render is reachable via AgentRow.tsx:267 and AgentsPopup.t… |
| [ISS-591](../.knowledge/cards/20260829-0114-ISS-591.md) | [FIX-403](../.knowledge/cards/20260829-0216-FIX-403.md), [FIX-458](../.knowledge/cards/20260901-1900-FIX-458.md) | — | SkillDetailModal (LibraryPage.tsx:207-221,285-301) only splits #/##-prefixed lines and -/*/numbered… |
| [ISS-592](../.knowledge/cards/20260829-0117-ISS-592.md) | [FIX-407](../.knowledge/cards/20260829-0441-FIX-407.md), [FIX-442](../.knowledge/cards/20260901-FIX-442.md) | [ISS-360](../.knowledge/cards/20260828-1917-ISS-360.md) | routes.libraryAgent(slug) builds a bare /library/agents/<id> path with no query string; the router.… |
| [ISS-593](../.knowledge/cards/20260829-0117-ISS-593.md) | [FIX-407](../.knowledge/cards/20260829-0441-FIX-407.md), [FIX-442](../.knowledge/cards/20260901-FIX-442.md) | [ISS-360](../.knowledge/cards/20260828-1917-ISS-360.md) | routes.librarySkill(slug) builds a bare /library/skills/<id> path with no query string; the router.… |
| [ISS-594](../.knowledge/cards/20260829-0117-ISS-594.md) | [FIX-407](../.knowledge/cards/20260829-0441-FIX-407.md), [FIX-442](../.knowledge/cards/20260901-FIX-442.md) | — | T16 effect (LibraryPage.tsx:643-665) only clears selectedAgent/Skill/Hook on a URL change; it never… |
| [ISS-595](../.knowledge/cards/20260829-0120-ISS-595.md) | [FIX-406](../.knowledge/cards/20260829-0431-FIX-406.md) | — | handleSwitchToLiveRun (page.tsx:2635-2656) replays a still-running run's durable events through the… |
| [ISS-596](../.knowledge/cards/20260829-0127-ISS-596.md) | [FIX-394](../.knowledge/cards/20260829-0127-FIX-394.md), [FIX-447](../.knowledge/cards/20260901-1530-FIX-447.md) | — | Test-side defect, not app-side: src/app.js is files[0] in that fixture so it is auto-opened as an e… |
| [ISS-597](../.knowledge/cards/20260829-0135-ISS-597.md) | [FIX-409](../.knowledge/cards/20260829-0449-FIX-409.md) | [ISS-383](../.knowledge/cards/20260828-2021-ISS-383.md) | INFERRED sibling of ISS-383: SandboxTab.tsx:411 feeds every fenced code block in rendered Markdown … |
| [ISS-598](../.knowledge/cards/20260829-0136-ISS-598.md) | [FIX-409](../.knowledge/cards/20260829-0449-FIX-409.md) | [ISS-383](../.knowledge/cards/20260828-2021-ISS-383.md) | INFERRED sibling of ISS-383: PreviewPanel.tsx:753-755 shows the Workspace/CodeView tab for any run … |
| [ISS-599](../.knowledge/cards/20260829-0340-ISS-599.md) | [FIX-395](../.knowledge/cards/20260829-0338-FIX-395.md), [FIX-449](../.knowledge/cards/20260901-1530-FIX-449.md) | — | ArtifactCard/MessageBubble catch-and-console.error only, and artifactPreview.tsx:406 + PreviewPanel… |
| [ISS-600](../.knowledge/cards/20260829-0341-ISS-600.md) | [FIX-395](../.knowledge/cards/20260829-0338-FIX-395.md), [FIX-451](../.knowledge/cards/20260901-1600-FIX-451.md), [FIX-453](../.knowledge/cards/20260901-1600-FIX-453.md) | — | useParams: () => ({}) makes LibraryPage's T16 URL-sync effect close the detail modal before the Cop… |
| [ISS-601](../.knowledge/cards/20260829-0138-ISS-601.md) | [FIX-410](../.knowledge/cards/20260829-0249-FIX-410.md) | — | user_workflows.py never strips payload.name, unlike user_agents.py's create/update handlers -- ever… |
| [ISS-602](../.knowledge/cards/20260829-0353-ISS-602.md) | [FIX-398](../.knowledge/cards/20260829-0352-FIX-398.md), [FIX-460](../.knowledge/cards/20260901-2100-FIX-460.md) | — | login/page.tsx:303-317 keeps a hand-rolled type="password" input inside a Lock-icon relative wrappe… |
| [ISS-603](../.knowledge/cards/20260829-0402-ISS-603.md) | [FIX-400](../.knowledge/cards/20260829-0402-FIX-400.md), [FIX-479](../.knowledge/cards/20260902-1400-FIX-479.md) | — | Fixture defect, not a code defect: the case removes the ONLY attachment (brief becomes "") and moun… |
| [ISS-605](../.knowledge/cards/20260829-0216-ISS-605.md) | [FIX-403](../.knowledge/cards/20260829-0216-FIX-403.md), [FIX-458](../.knowledge/cards/20260901-1900-FIX-458.md) | — | Assertion 2 scans the whole [role=dialog], which always contains the modal's intentional raw SKILL.… |
| [ISS-606](../.knowledge/cards/20260829-1412-ISS-606.md) | [FIX-334](../.knowledge/cards/20260828-2149-FIX-334.md), [FIX-411](../.knowledge/cards/20260829-1646-FIX-411.md), [FIX-450](../.knowledge/cards/20260901-1530-FIX-450.md) | — | AgentThinkingTab (Steps tab) and FilesTab agent-outputs list get raw agentOutputs/agents/pipelineSt… |
| [ISS-607](../.knowledge/cards/20260829-1450-ISS-607.md) | [FIX-412](../.knowledge/cards/20260829-1703-FIX-412.md), [FIX-417](../.knowledge/cards/20260831-0110-FIX-417.md) | — | Version-switch no-op from base /steps: handleSelectVersion (PreviewPanel.tsx:579) treats the newest… |
| [ISS-608](../.knowledge/cards/20260829-1421-ISS-608.md) | [FIX-411](../.knowledge/cards/20260829-1646-FIX-411.md) | — | AppBuilderIDEPreview/GenericDeliverablePreview (PreviewPanel.tsx:1085,1160,1186) and SandboxTab age… |
| [ISS-609](../.knowledge/cards/20260829-1420-ISS-609.md) | [FIX-411](../.knowledge/cards/20260829-1646-FIX-411.md), [FIX-450](../.knowledge/cards/20260901-1530-FIX-450.md) | — | AuditTab gets workflowRunId=pipelineState?.pipelineRunId at PreviewPanel.tsx:1466, not activeRunId,… |
| [ISS-610](../.knowledge/cards/20260829-1631-ISS-610.md) | [FIX-412](../.knowledge/cards/20260829-1703-FIX-412.md) | — | handleSelectVersion (PreviewPanel.tsx:577-582) is generic over activeTab — the ISS-607 select-lates… |
| [ISS-611](../.knowledge/cards/20260829-1631-ISS-611.md) | [FIX-412](../.knowledge/cards/20260829-1703-FIX-412.md) | — | handleBackToLatest/handleSelectVersion send pin=null on a "latest" click, resolving activeRunId to … |
| [ISS-612](../.knowledge/cards/20260829-1631-ISS-612.md) | [FIX-412](../.knowledge/cards/20260829-1703-FIX-412.md) | — | DeepLinkTarget.anchor (types/index.ts:88, populated end-to-end by useRunChat.parseDeepLink from bac… |
| [ISS-613](../.knowledge/cards/20260829-1647-ISS-613.md) | [FIX-334](../.knowledge/cards/20260828-2149-FIX-334.md), [FIX-411](../.knowledge/cards/20260829-1646-FIX-411.md), [FIX-413](../.knowledge/cards/20260830-2044-FIX-413.md) | — | V2_SIZE="83.5 KB" is 85,529 chars/1024, but FilesTab renders formatSize(utf8Bytes(...)) = 85,624 B … |
| [ISS-614](../.knowledge/cards/20260829-1704-ISS-614.md) | [FIX-412](../.knowledge/cards/20260829-1703-FIX-412.md), [FIX-413](../.knowledge/cards/20260830-2044-FIX-413.md) | — | anchor is `deliverable:<filename>` for deliverable cards (chat_narrator.py:198-201), so it cannot c… |
| [ISS-615](../.knowledge/cards/20260829-1705-ISS-615.md) | [FIX-412](../.knowledge/cards/20260829-1703-FIX-412.md), [FIX-413](../.knowledge/cards/20260830-2044-FIX-413.md) | — | a bare GET /api/runs/{rootId} fires on ANY pin change because the root stays in the URL base segmen… |
| [ISS-616](../.knowledge/cards/20260831-0110-ISS-616.md) | [FIX-414](../.knowledge/cards/20260831-0110-FIX-414.md) | — | compile_for_run.cache_clear() AttributeError at the setup of 3734 tests — a bare assignment leaked … |
| [ISS-617](../.knowledge/cards/20260831-0110-ISS-617.md) | [FIX-323](../.knowledge/cards/20260828-1629-FIX-323.md), [FIX-415](../.knowledge/cards/20260831-0110-FIX-415.md), [FIX-436](../.knowledge/cards/20260831-1919-FIX-436.md) | — | the three gate tests leaned on inline `gate: Human_Gate` and manifest `gates: [human]`, both of whi… |
| [ISS-618](../.knowledge/cards/20260831-0110-ISS-618.md) | [FIX-416](../.knowledge/cards/20260831-0110-FIX-416.md) | — | the ISS-230 fixture (root 77f74563) is a genuine 2-member family, so the family-of-one premise is f… |
| [ISS-619](../.knowledge/cards/20260831-0110-ISS-619.md) | [FIX-334](../.knowledge/cards/20260828-2149-FIX-334.md), [FIX-417](../.knowledge/cards/20260831-0110-FIX-417.md) | — | handleSelectVersion keys its no-pin-needed shortcut on unpinnedRunId, which a pinned deep link sets… |
| [ISS-620](../.knowledge/cards/20260831-0110-ISS-620.md) | [FIX-323](../.knowledge/cards/20260828-1629-FIX-323.md), [FIX-418](../.knowledge/cards/20260831-0110-FIX-418.md) | — | S-18-05 assumed every id was chat_reply:, S-05-07 asserted the raw-id rendering ISS-327 identified … |
| [ISS-621](../.knowledge/cards/20260831-0110-ISS-621.md) | [FIX-419](../.knowledge/cards/20260831-0110-FIX-419.md), [FIX-435](../.knowledge/cards/20260831-1909-FIX-435.md) | — | playwright_smoke_test, claude-sonnet-5 and html-deck-to-pptx each moved a pin nobody bumped; separa… |
| [ISS-622](../.knowledge/cards/20260831-0115-ISS-622.md) | [FIX-481](../.knowledge/cards/20260902-1530-FIX-481.md) | — | window.confirm is back in AccountSettings, DashboardLayout (x2) and ComposerPage; feat/conditional-… |
| [ISS-624](../.knowledge/cards/20260831-0115-ISS-624.md) | [FIX-463](../.knowledge/cards/20260901-2100-FIX-463.md) | — | document.body.innerText.length is 0 on a cold load of /library?tab=hooks; the other four top-level … |
| [ISS-625](../.knowledge/cards/20260831-0115-ISS-625.md) | [FIX-443](../.knowledge/cards/20260901-FIX-443.md) | — | no family buckets to ppt so WorkflowHistory drops the chip entirely; whether the runs SHOULD be gon… |
| [ISS-626](../.knowledge/cards/20260831-0115-ISS-626.md) | [FIX-444](../.knowledge/cards/20260901-FIX-444.md) | — | test_a_last_streamed_built_in_refuses_an_append_after_final_step_slot times out on its locator; app… |
| [ISS-627](../.knowledge/cards/20260831-0115-ISS-627.md) | [FIX-442](../.knowledge/cards/20260901-FIX-442.md) | — | ISS-592/593/594/320 pass under xfail(strict) and the S-15-01 Escape pin now fails, so five guards a… |
| [ISS-631](../.knowledge/cards/20260831-0115-ISS-631.md) | [FIX-432](../.knowledge/cards/20260831-1842-FIX-432.md), [FIX-433](../.knowledge/cards/20260831-1859-FIX-433.md) | — | roster and compiled sequence diverge from the manifest for all three revision pipelines; 15 tests w… |
| [ISS-633](../.knowledge/cards/20260831-0115-ISS-633.md) | [FIX-432](../.knowledge/cards/20260831-1842-FIX-432.md) | — | four tests expect exactly one exact-kind revision ref and get another count; two FE-contract tests … |
| [ISS-635](../.knowledge/cards/20260831-0115-ISS-635.md) | [FIX-433](../.knowledge/cards/20260831-1859-FIX-433.md), [FIX-435](../.knowledge/cards/20260831-1909-FIX-435.md) | — | the spec-018 manifest declares planner: skip where parity requires run, and its clarify.defaults is… |
| [ISS-636](../.knowledge/cards/20260831-0115-ISS-636.md) | [FIX-433](../.knowledge/cards/20260831-1859-FIX-433.md), [FIX-436](../.knowledge/cards/20260831-1919-FIX-436.md) | [ISS-617](../.knowledge/cards/20260831-0110-ISS-617.md) | the agents API and the frontend-consistency check assert gate values FIX-323 deleted from AGENT.md … |
| [ISS-637](../.knowledge/cards/20260831-0115-ISS-637.md) | [FIX-434](../.knowledge/cards/20260831-1907-FIX-434.md) | — | test_upgrade_then_check_reports_no_drift raises AutogenerateDiffsDetected: the ORM metadata and the… |

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
| [ISS-190](../.knowledge/cards/20260828-1501-ISS-190.md) | **none found** | [ISS-195](../.knowledge/cards/20260828-1558-ISS-195.md), [ISS-197](../.knowledge/cards/20260828-1559-ISS-197.md) | INFERRED sibling of ISS-190: page.tsx:3701 gates ALL 34 screens on the same mount-once mounted/isAuthenticate… |
| [ISS-238](../.knowledge/cards/20260828-1633-ISS-238.md) | [FIX-344](../.knowledge/cards/20260828-2046-FIX-344.md) | [ISS-348](../.knowledge/cards/20260828-2102-ISS-348.md), [ISS-349](../.knowledge/cards/20260828-2102-ISS-349.md) | Sibling of ISS-238: routes.ts:224-229 head==="login" has the same missing depth guard; page.tsx has no login … |
| [ISS-097](../.knowledge/cards/20260812-1153-ISS-097.md) | [FIX-242](../.knowledge/cards/20260812-2116-FIX-242.md), [FIX-424](../.knowledge/cards/20260831-1652-FIX-424.md) | [ISS-132](../.knowledge/cards/20260812-2116-ISS-132.md) | task_loop.py never passes invocation_gated, so ticking a task-loop agent opens one sequential review gate per… |
| [ISS-225](../.knowledge/cards/20260828-1541-ISS-225.md) | [FIX-285](../.knowledge/cards/20260824-1621-FIX-285.md), [FIX-336](../.knowledge/cards/20260828-2201-FIX-336.md), [FIX-337](../.knowledge/cards/20260828-2210-FIX-337.md) | [ISS-263](../.knowledge/cards/20260828-1811-ISS-263.md) | INFERRED sibling of ISS-225: selections-only save skips R-03 entirely on empty selections, and synthesize_man… |
| [ISS-245](../.knowledge/cards/20260828-1631-ISS-245.md) | [FIX-345](../.knowledge/cards/20260828-2250-FIX-345.md), [FIX-470](../.knowledge/cards/20260902-1200-FIX-470.md) | [ISS-352](../.knowledge/cards/20260828-2101-ISS-352.md) | INFERRED sibling of ISS-245: login/page.tsx ChallengeForm Continue button (disabled={isLoading} at L525) gate… |
| [ISS-274](../.knowledge/cards/20260828-1854-ISS-274.md) | [FIX-350](../.knowledge/cards/20260828-2340-FIX-350.md), [FIX-471](../.knowledge/cards/20260902-1200-FIX-471.md) | [ISS-378](../.knowledge/cards/20260828-2006-ISS-378.md) | ConfigLeversFlat (AgentsPopup.tsx:1700-1771) also renders only Model/Validator/Gate/Retry, no Tools row — sam… |
| [ISS-292](../.knowledge/cards/20260828-1918-ISS-292.md) | [FIX-361](../.knowledge/cards/20260829-0029-FIX-361.md), [FIX-382](../.knowledge/cards/20260829-0223-FIX-382.md), [FIX-439](../.knowledge/cards/20260831-1959-FIX-439.md) | [ISS-398](../.knowledge/cards/20260828-2106-ISS-398.md) | _validate_model_overrides (run_engine.py:547-607) allow-lists model_id against ModelCatalog.ids() only, no ti… |
| [ISS-312](../.knowledge/cards/20260828-1941-ISS-312.md) | [FIX-374](../.knowledge/cards/20260829-0146-FIX-374.md), [FIX-479](../.knowledge/cards/20260902-1400-FIX-479.md) | [ISS-422](../.knowledge/cards/20260829-0027-ISS-422.md) | INFERRED: useChatAttachments.ts computes FileContentEntry.truncated correctly but ChatAttachments.tsx never r… |
| [ISS-315](../.knowledge/cards/20260828-1750-ISS-315.md) | [FIX-375](../.knowledge/cards/20260829-0151-FIX-375.md), [FIX-469](../.knowledge/cards/20260902-1200-FIX-469.md) | [ISS-432](../.knowledge/cards/20260829-0039-ISS-432.md) | INFERRED sibling of ISS-315: the same shared guard (ComposerPage.tsx:1108-1112) is reached from /workflows/{i… |

> **1 root(s) carry no FIX card**: ISS-190. The root is marked
> resolved but nothing records the diff — treat these siblings as tier C until that
> is explained, because there may be no landed change to replicate.

---

## Tier A — declared families, both ends still open

The cards name each other. One fix, one test, one verify closes the set.

### [ISS-228](../.knowledge/cards/20260828-1758-ISS-228.md) + 1 sibling(s)

Saved workflow's launch panel discards the override fetch — generic base-type wizard renders even though GET /api/user-workflows/{id} succeeds

| card | fix site | summary |
|---|---|---|
| [ISS-228](../.knowledge/cards/20260828-1758-ISS-228.md) | `frontend/src/components/workflow/LaunchWizard.tsx` | On /workflows/{id}/run, LaunchWizard.tsx fires GET /api/user-workflows/{id} and GET /api/workflows/{base_pipeline_type} in parall… |
| [ISS-284](../.knowledge/cards/20260828-1906-ISS-284.md) | `frontend/src/components/workflow/LaunchWizard.tsx` | INFERRED sibling of ISS-228: handleSave/handleSaveAsOverride (LaunchWizard.tsx:703,737) send pipelineAgents as agent_ids, so savi… |

### [ISS-392](../.knowledge/cards/20260828-2250-ISS-392.md) + 1 sibling(s)

Corrects ISS-287: LibraryPage DOES pass onSelectionsChange — the real defect is that AgentCapabilitiesModal has no backend persistence path at all for Config-tab overrides

| card | fix site | summary |
|---|---|---|
| [ISS-392](../.knowledge/cards/20260828-2250-ISS-392.md) | `frontend/src/components/library/LibraryPage.tsx`, `frontend/src/components/workflow/AgentsPopup.tsx` | AgentCapabilitiesModal Save agent has zero fetch/API calls anywhere in AgentsPopup.tsx; LibraryPage DOES wire onSelectionsChange … |
| [ISS-393](../.knowledge/cards/20260828-2251-ISS-393.md) | `frontend/src/app/workflow/page.tsx`, `frontend/src/components/workflow/AgentLibrary.tsx`, `frontend/src/components/workflow/AgentsPopup.tsx`, `frontend/src/components/workflow/WorkflowView.tsx`, `frontend/src/components/workflow/composer/ComposerPage.tsx` | AgentLibrary.tsx:332-338 mounts AgentCapabilitiesModal with onSkillsChange but no onSelectionsChange, so effectiveOnSelectionsCha… |

---

## Tier B — same file, same defect class (proposed — review before merging)

These share a file *and* a defect class, which is the strongest signal available
short of a card saying so. It is still a guess: confirm the two really collapse to
one diff before merging, and split them back out if they do not.

| fix site | class | cards | first card |
|---|---|---|---|
| `frontend/src/components/history/WorkflowHistory.tsx` | stale-state | [ISS-145](../.knowledge/cards/20260813-0205-ISS-145.md), [ISS-412](../.knowledge/cards/20260828-2343-ISS-412.md) | Vitest baseline is stale by ~10x: measured 147 failed/894 passed vs a documented '~8 known reds'; s… |
| `frontend/src/components/layout/DashboardLayout.tsx` | confirm-dialog | [ISS-371](../.knowledge/cards/20260828-2140-ISS-371.md), [ISS-372](../.knowledge/cards/20260828-2141-ISS-372.md) | IdeaInputPage.tsx:1577 wires onClick={onBack} to the same ungated handleBackNav (DashboardLayout.ts… |
| `frontend/src/components/library/LibraryPage.tsx` | silent-discard | [BUG-073](../.knowledge/cards/20260829-1508-BUG-073.md), [BUG-095](../.knowledge/cards/20260829-1508-BUG-095.md) | Agent config overrides in library detail have no server sink; changes silently discarded on reload. |
| `frontend/src/components/workflow/AgentsPopup.tsx` | silent-discard | [BUG-073](../.knowledge/cards/20260829-1508-BUG-073.md), [BUG-095](../.knowledge/cards/20260829-1508-BUG-095.md) | Agent config overrides in library detail have no server sink; changes silently discarded on reload. |

### Class campaigns (one sweep, many diffs — not one merge)

Same defect class across *different* files. These do **not** merge into one row, but
one engineer holding the pattern in their head can clear the set far faster than the
line can trip on each. Batch them onto one worker; keep the rows separate.

| class | cards |
|---|---|
| stale-state | 13: [BUG-021-GROUNDED-CONTEXT](../.knowledge/cards/20260717-2113-BUG-021-GROUNDED-CONTEXT.md), [ISS-076](../.knowledge/cards/20260812-0212-ISS-076.md), [ISS-079](../.knowledge/cards/20260812-0236-ISS-079.md), [ISS-096](../.knowledge/cards/20260812-1120-ISS-096.md), [ISS-104](../.knowledge/cards/20260812-1312-ISS-104.md), [ISS-145](../.knowledge/cards/20260813-0205-ISS-145.md), [ISS-180](../.knowledge/cards/20260825-2115-ISS-180.md), [ISS-347](../.knowledge/cards/20260828-2058-ISS-347.md), [ISS-412](../.knowledge/cards/20260828-2343-ISS-412.md), [ISS-630](../.knowledge/cards/20260831-0115-ISS-630.md), [ISS-632](../.knowledge/cards/20260831-0115-ISS-632.md), [ISS-638](../.knowledge/cards/20260831-0115-ISS-638.md), [ISS-642](../.knowledge/cards/20260831-1842-ISS-642.md) |
| silent-discard | 6: [BUG-036](../.knowledge/cards/20260829-1508-BUG-036.md), [BUG-073](../.knowledge/cards/20260829-1508-BUG-073.md), [BUG-095](../.knowledge/cards/20260829-1508-BUG-095.md), [BUG-106](../.knowledge/cards/20260829-1508-BUG-106.md), [BUG-CWF-002-custom-workflow](../.knowledge/cards/20260803-BUG-CWF-002-custom-workflow.md), [ISS-263](../.knowledge/cards/20260828-1811-ISS-263.md) |
| route-depth | 2: [ISS-348](../.knowledge/cards/20260828-2102-ISS-348.md), [ISS-349](../.knowledge/cards/20260828-2102-ISS-349.md) |
| confirm-dialog | 2: [ISS-371](../.knowledge/cards/20260828-2140-ISS-371.md), [ISS-372](../.knowledge/cards/20260828-2141-ISS-372.md) |
| double-submit | 1: [ISS-352](../.knowledge/cards/20260828-2101-ISS-352.md) |
| list-cap | 1: [BUG-037](../.knowledge/cards/20260829-1508-BUG-037.md) |
| keyboard-a11y | 1: [BUG-104](../.knowledge/cards/20260829-1508-BUG-104.md) |

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
| 1 | 11 — all concurrent | 48 |
| 2 | 5 — all concurrent | 31 |
| 3 | 3 — all concurrent | 20 |
| 4 | 2 — all concurrent | 12 |
| 5 | 1 — all concurrent | 1 |

**18 multi-card batches** carry 108 of the 112 cards.

### Domains — each block is one coherent area of the app

| domain | cards | batches | earliest round |
|---|---|---|---|
| [backend · api](#backend--api) | 18 | 4 | 1 |
| [frontend · unplaced](#frontend--unplaced) | 18 | 1 | 1 |
| [backend · other](#backend--other) | 17 | 3 | 1 |
| [frontend · composer](#frontend--composer) | 10 | 1 | 3 |
| [frontend · hooks](#frontend--hooks) | 10 | 2 | 1 |
| [frontend · workflow](#frontend--workflow) | 9 | 1 | 4 |
| [frontend · history](#frontend--history) | 7 | 1 | 3 |
| [frontend · layout](#frontend--layout) | 5 | 1 | 2 |
| [frontend · routes](#frontend--routes) | 5 | 1 | 1 |
| [frontend · library](#frontend--library) | 4 | 1 | 1 |
| [backend · unplaced](#backend--unplaced) | 3 | 1 | 1 |
| [frontend · components](#frontend--components) | 2 | 1 | 2 |
| [backend · engine](#backend--engine) | 1 | 1 | 1 |
| [docs · planning](#docs--planning) | 1 | 1 | 1 |
| [frontend · lib](#frontend--lib) | 1 | 1 | 5 |
| [tests · integration](#tests--integration) | 1 | 1 | 1 |

Every card carries a domain — there is no uncategorised bucket. A row marked
*fix site not recorded* is still domain-placed; what it lacks is a file, so it
cannot be collision-checked and must be triaged before it is scheduled.

#### backend · api

18 cards across 4 batch(es).

| round | fix site | cards | members |
|---|---|---|---|
| 1 | `backend/app/api/user_workflows.py` | 4 | [ISS-180](../.knowledge/cards/20260825-2115-ISS-180.md), [ISS-181](../.knowledge/cards/20260825-2115-ISS-181.md), [ISS-263](../.knowledge/cards/20260828-1811-ISS-263.md), [ISS-381](../.knowledge/cards/20260828-2210-ISS-381.md) |
| 1 | **backend · api** | 2 | [ISS-134](../.knowledge/cards/20260812-2140-ISS-134.md), [ISS-419](../.knowledge/cards/20260829-0022-ISS-419.md) |
| 2 | `backend/app/api/run_commands.py` | 9 | [ISS-100](../.knowledge/cards/20260812-1232-ISS-100.md), [ISS-104](../.knowledge/cards/20260812-1312-ISS-104.md), [ISS-119](../.knowledge/cards/20260812-1612-ISS-119.md), [ISS-127](../.knowledge/cards/20260812-2045-ISS-127.md), [ISS-128](../.knowledge/cards/20260812-2046-ISS-128.md), [ISS-154](../.knowledge/cards/20260813-0819-ISS-154.md), [ISS-161](../.knowledge/cards/20260813-1300-ISS-161.md), [ISS-398](../.knowledge/cards/20260828-2106-ISS-398.md), [ISS-422](../.knowledge/cards/20260829-0027-ISS-422.md) |
| 2 | `backend/app/api/run_stream.py` | 3 | [BUG-015-016-GROUNDED-CONTEXT](../.knowledge/cards/20260717-0057-BUG-015-016-GROUNDED-CONTEXT.md), [ISS-105](../.knowledge/cards/20260812-1312-ISS-105.md), [ISS-137](../.knowledge/cards/20260813-0005-ISS-137.md) |

#### frontend · unplaced

18 cards across 1 batch(es).

| round | fix site | cards | members |
|---|---|---|---|
| 1 | **frontend · unplaced — fix site not recorded** | 18 | [BUG-009-sse](../.knowledge/cards/20260803-BUG-009-sse.md), [BUG-010-sse](../.knowledge/cards/20260803-BUG-010-sse.md), [BUG-035](../.knowledge/cards/20260829-1508-BUG-035.md), [BUG-074](../.knowledge/cards/20260829-1508-BUG-074.md), [BUG-104](../.knowledge/cards/20260829-1508-BUG-104.md), [BUG-106](../.knowledge/cards/20260829-1508-BUG-106.md), [BUG-CWF-001-custom-workflow](../.knowledge/cards/20260803-BUG-CWF-001-custom-workflow.md), [BUG-CWF-002-custom-workflow](../.knowledge/cards/20260803-BUG-CWF-002-custom-workflow.md), [ISS-018](../.knowledge/cards/20260614-0619-ISS-018.md), [ISS-071](../.knowledge/cards/20260812-0107-ISS-071.md), [ISS-107](../.knowledge/cards/20260812-1400-ISS-107.md), [ISS-122](../.knowledge/cards/20260812-1804-ISS-122.md), [ISS-129](../.knowledge/cards/20260812-2116-ISS-129.md), [ISS-135](../.knowledge/cards/20260813-0005-ISS-135.md), [ISS-159](../.knowledge/cards/20260813-1300-ISS-159.md), [ISS-160](../.knowledge/cards/20260813-1300-ISS-160.md), [ISS-179](../.knowledge/cards/20260825-1600-ISS-179.md), [ISS-186](../.knowledge/cards/20260826-0124-ISS-186.md) |

#### backend · other

17 cards across 3 batch(es).

| round | fix site | cards | members |
|---|---|---|---|
| 1 | `backend/agents/workflows/ex_A3_divert/workflow.yaml` | 2 | [ISS-173](../.knowledge/cards/20260825-0955-ISS-173.md), [ISS-174](../.knowledge/cards/20260825-0956-ISS-174.md) |
| 2 | **backend · other** | 12 | [ISS-079](../.knowledge/cards/20260812-0236-ISS-079.md), [ISS-096](../.knowledge/cards/20260812-1120-ISS-096.md), [ISS-130](../.knowledge/cards/20260812-2116-ISS-130.md), [ISS-132](../.knowledge/cards/20260812-2116-ISS-132.md), [ISS-156](../.knowledge/cards/20260813-1300-ISS-156.md), [ISS-630](../.knowledge/cards/20260831-0115-ISS-630.md), [ISS-632](../.knowledge/cards/20260831-0115-ISS-632.md), [ISS-634](../.knowledge/cards/20260831-0115-ISS-634.md), [ISS-638](../.knowledge/cards/20260831-0115-ISS-638.md), [ISS-640](../.knowledge/cards/20260831-1814-ISS-640.md), [ISS-641](../.knowledge/cards/20260831-1818-ISS-641.md), [ISS-642](../.knowledge/cards/20260831-1842-ISS-642.md) |
| 3 | `backend/agents/execution_engine/engine.py` | 3 | [ADR-0002](../.knowledge/cards/20260811-ADR-0002.md), [ISS-094](../.knowledge/cards/20260812-1120-ISS-094.md), [ISS-639](../.knowledge/cards/20260831-1645-ISS-639.md) |

#### frontend · composer

10 cards across 1 batch(es).

| round | fix site | cards | members |
|---|---|---|---|
| 3 | `frontend/src/components/workflow/composer/ComposerPage.tsx` | 10 | [ISS-183](../.knowledge/cards/20260825-2115-ISS-183.md), [ISS-192](../.knowledge/cards/20260828-1345-ISS-192.md), [ISS-223](../.knowledge/cards/20260828-1735-ISS-223.md), [ISS-334](../.knowledge/cards/20260828-2045-ISS-334.md), [ISS-340](../.knowledge/cards/20260828-1856-ISS-340.md), [ISS-373](../.knowledge/cards/20260828-2142-ISS-373.md), [ISS-393](../.knowledge/cards/20260828-2251-ISS-393.md), [ISS-410](../.knowledge/cards/20260828-2344-ISS-410.md), [ISS-432](../.knowledge/cards/20260829-0039-ISS-432.md), [ISS-604](../.knowledge/cards/20260829-0207-ISS-604.md) |

#### frontend · hooks

10 cards across 2 batch(es).

| round | fix site | cards | members |
|---|---|---|---|
| 1 | `frontend/src/hooks/useWorkflow.ts` | 7 | [BUG-014-B-GROUNDED-CONTEXT](../.knowledge/cards/20260716-2339-BUG-014-B-GROUNDED-CONTEXT.md), [FIX-BUGFIX-SPEC-REVISION-CONTEXT](../.knowledge/cards/20260811-1630-FIX-BUGFIX-SPEC-REVISION-CONTEXT.md), [ISS-109](../.knowledge/cards/20260812-1400-ISS-109.md), [ISS-115](../.knowledge/cards/20260812-1511-ISS-115.md), [ISS-116](../.knowledge/cards/20260812-1511-ISS-116.md), [ISS-136](../.knowledge/cards/20260813-0005-ISS-136.md), [ISS-142](../.knowledge/cards/20260813-0005-ISS-142.md) |
| 4 | `frontend/src/hooks/useRunChat.ts` | 3 | [BUG-018-GROUNDED-CONTEXT](../.knowledge/cards/20260717-1903-BUG-018-GROUNDED-CONTEXT.md), [BUG-021-GROUNDED-CONTEXT](../.knowledge/cards/20260717-2113-BUG-021-GROUNDED-CONTEXT.md), [ISS-111](../.knowledge/cards/20260812-1444-ISS-111.md) |

#### frontend · workflow

9 cards across 1 batch(es).

| round | fix site | cards | members |
|---|---|---|---|
| 4 | `frontend/src/components/workflow/LaunchWizard.tsx` | 9 | [BUG-048](../.knowledge/cards/20260829-1508-BUG-048.md), [ISS-189](../.knowledge/cards/20260828-1457-ISS-189.md), [ISS-197](../.knowledge/cards/20260828-1559-ISS-197.md), [ISS-217](../.knowledge/cards/20260828-1649-ISS-217.md), [ISS-228](../.knowledge/cards/20260828-1758-ISS-228.md), [ISS-284](../.knowledge/cards/20260828-1906-ISS-284.md), [ISS-347](../.knowledge/cards/20260828-2058-ISS-347.md), [ISS-362](../.knowledge/cards/20260828-2121-ISS-362.md), [ISS-377](../.knowledge/cards/20260828-2202-ISS-377.md) |

#### frontend · history

7 cards across 1 batch(es).

| round | fix site | cards | members |
|---|---|---|---|
| 3 | `frontend/src/components/history/WorkflowHistory.tsx` | 7 | [ISS-077](../.knowledge/cards/20260812-0212-ISS-077.md), [ISS-113](../.knowledge/cards/20260812-1444-ISS-113.md), [ISS-145](../.knowledge/cards/20260813-0205-ISS-145.md), [ISS-219](../.knowledge/cards/20260828-1706-ISS-219.md), [ISS-325](../.knowledge/cards/20260828-2014-ISS-325.md), [ISS-412](../.knowledge/cards/20260828-2343-ISS-412.md), [ISS-629](../.knowledge/cards/20260831-0115-ISS-629.md) |

#### frontend · layout

5 cards across 1 batch(es).

| round | fix site | cards | members |
|---|---|---|---|
| 2 | `frontend/src/components/layout/DashboardLayout.tsx` | 5 | [ISS-346](../.knowledge/cards/20260828-2058-ISS-346.md), [ISS-348](../.knowledge/cards/20260828-2102-ISS-348.md), [ISS-349](../.knowledge/cards/20260828-2102-ISS-349.md), [ISS-371](../.knowledge/cards/20260828-2140-ISS-371.md), [ISS-372](../.knowledge/cards/20260828-2141-ISS-372.md) |

#### frontend · routes

5 cards across 1 batch(es).

| round | fix site | cards | members |
|---|---|---|---|
| 1 | **frontend · routes** | 5 | [ISS-195](../.knowledge/cards/20260828-1558-ISS-195.md), [ISS-352](../.knowledge/cards/20260828-2101-ISS-352.md), [ISS-407](../.knowledge/cards/20260828-2343-ISS-407.md), [ISS-442](../.knowledge/cards/20260829-0106-ISS-442.md), [ISS-579](../.knowledge/cards/20260829-0234-ISS-579.md) |

#### frontend · library

4 cards across 1 batch(es).

| round | fix site | cards | members |
|---|---|---|---|
| 1 | `frontend/src/components/library/LibraryPage.tsx` | 4 | [BUG-073](../.knowledge/cards/20260829-1508-BUG-073.md), [BUG-095](../.knowledge/cards/20260829-1508-BUG-095.md), [ISS-378](../.knowledge/cards/20260828-2006-ISS-378.md), [ISS-392](../.knowledge/cards/20260828-2250-ISS-392.md) |

#### backend · unplaced

3 cards across 1 batch(es).

| round | fix site | cards | members |
|---|---|---|---|
| 1 | **backend · unplaced — fix site not recorded** | 3 | [BUG-036](../.knowledge/cards/20260829-1508-BUG-036.md), [BUG-037](../.knowledge/cards/20260829-1508-BUG-037.md), [ISS-020](../.knowledge/cards/20260614-0619-ISS-020.md) |

#### frontend · components

2 cards across 1 batch(es).

| round | fix site | cards | members |
|---|---|---|---|
| 2 | **frontend · components** | 2 | [ISS-112](../.knowledge/cards/20260812-1444-ISS-112.md), [ISS-434](../.knowledge/cards/20260828-2240-ISS-434.md) |

#### backend · engine

1 cards across 1 batch(es).

| round | fix site | cards | members |
|---|---|---|---|
| 1 | **backend · engine** | 1 | [ISS-187](../.knowledge/cards/20260826-1547-ISS-187.md) |

#### docs · planning

1 cards across 1 batch(es).

| round | fix site | cards | members |
|---|---|---|---|
| 1 | **docs · planning** | 1 | [ISS-076](../.knowledge/cards/20260812-0212-ISS-076.md) |

#### frontend · lib

1 cards across 1 batch(es).

| round | fix site | cards | members |
|---|---|---|---|
| 5 | **frontend · lib** | 1 | [BUG-013-GROUNDED-CONTEXT](../.knowledge/cards/20260716-1935-BUG-013-GROUNDED-CONTEXT.md) |

#### tests · integration

1 cards across 1 batch(es).

| round | fix site | cards | members |
|---|---|---|---|
| 1 | **tests · integration** | 1 | [ISS-623](../.knowledge/cards/20260831-0115-ISS-623.md) |

## Tier C — no kin found

91 cards with no declared sibling and no same-file/same-class neighbour.
Each is its own unit of work.

| card | fix site | summary |
|---|---|---|
| [ADR-0002](../.knowledge/cards/20260811-ADR-0002.md) | `backend/CLAUDE.md`, `backend/agents/execution_engine/engine.py`, `backend/agents/loader.py`, `backend/agents/registry.py` | That `workflow` is the only vocabulary the system knows and `pipeline` is removed rather than deprecated, to achieve on… |
| [BUG-009-sse](../.knowledge/cards/20260803-BUG-009-sse.md) | — | od_ppt's deliverable resolver reads only the last agent's live stream, so a non-compliant validator re-emit discards an… |
| [BUG-010-sse](../.knowledge/cards/20260803-BUG-010-sse.md) | — | Investigated as a false alarm: `activePipelineRunId` is null while a run is actively building, so `trackedRunIdRef` res… |
| [BUG-013-GROUNDED-CONTEXT](../.knowledge/cards/20260716-1935-BUG-013-GROUNDED-CONTEXT.md) | `frontend/src/lib/api.ts`, `frontend/src/providers/RunConnectionProvider.tsx` | One EventSource per non-terminal run saturates the browser's ~6-connection-per-origin limit, hanging fetches; fix stops… |
| [BUG-014-B-GROUNDED-CONTEXT](../.knowledge/cards/20260716-2339-BUG-014-B-GROUNDED-CONTEXT.md) | `backend/app/api/run_stream.py`, `frontend/e2e/fixtures/mockSse.ts`, `frontend/src/hooks/useRunStream.ts`, `frontend/src/hooks/useWorkflow.ts`, `frontend/src/providers/RunConnectionProvider.tsx` | sse-starlette emits CRLF frame boundaries but useRunStream splits on LF-LF, so zero live SSE frames were parsed; fixed … |
| [BUG-015-016-GROUNDED-CONTEXT](../.knowledge/cards/20260717-0057-BUG-015-016-GROUNDED-CONTEXT.md) | `backend/app/api/run_stream.py`, `frontend/src/hooks/useRunStream.ts`, `frontend/src/providers/RunConnectionProvider.tsx` | BUG-015: a completed but focused run reconnects forever since useRunStream ignores prior stream_attached{live:false}; B… |
| [BUG-018-GROUNDED-CONTEXT](../.knowledge/cards/20260717-1903-BUG-018-GROUNDED-CONTEXT.md) | `frontend/src/components/chat/ArtifactCard.tsx`, `frontend/src/components/chat/ChatPanel.tsx`, `frontend/src/components/chat/RunChatLane.tsx`, `frontend/src/hooks/useRunChat.test.ts`, `frontend/src/hooks/useRunChat.ts`, `frontend/src/lib/api.ts` | getRunEvents dropped row.event_id so replies collided with the user turn's message_id and overwrote it; merging event_i… |
| [BUG-021-GROUNDED-CONTEXT](../.knowledge/cards/20260717-2113-BUG-021-GROUNDED-CONTEXT.md) | `frontend/src/hooks/useRunChat.ts` | useRunChat.messages was never cleared on a fresh non-revision launch, so the prior run's transcript bled through until … |
| [BUG-035](../.knowledge/cards/20260829-1508-BUG-035.md) | — | Landing on `/create/prototype` normally, then pressing the browser **Back** button (returns to `/dashboard`), then pres… |
| [BUG-036](../.knowledge/cards/20260829-1508-BUG-036.md) | — | The `ppt` built-in workflow's real manifest (`GET /api/workflows/ppt`) defines a specialized deliverable — `{"strategy"… |
| [BUG-037](../.knowledge/cards/20260829-1508-BUG-037.md) | — | The Run History page always requests `GET /api/runs?limit=50` and never issues a follow-up request with a higher `limit… |
| [BUG-048](../.knowledge/cards/20260829-1508-BUG-048.md) | `frontend/src/components/workflow/LaunchWizard.tsx` | A saved workflow's launch panel loses its override entirely and renders the generic base-type wizard, even though the o… |
| [BUG-074](../.knowledge/cards/20260829-1508-BUG-074.md) | — | Single-word skill IDs render correctly but reported as falling back to library listing (unreproducible). |
| [BUG-104](../.knowledge/cards/20260829-1508-BUG-104.md) | — | Escape key does not close "Workflow actions" dropdown menu on saved-workflow cards |
| [BUG-106](../.knowledge/cards/20260829-1508-BUG-106.md) | — | Run Workflow button enables with zero agents and silently no-ops on click |
| [BUG-CWF-001-custom-workflow](../.knowledge/cards/20260803-BUG-CWF-001-custom-workflow.md) | — | Composer let a consumer be ordered before its producer while execution ran topo order, so the resulting failure mislabe… |
| [BUG-CWF-002-custom-workflow](../.knowledge/cards/20260803-BUG-CWF-002-custom-workflow.md) | — | The resolved per-agent model was never emitted or persisted, so cost was always priced against the default profile; fix… |
| [FIX-BUGFIX-SPEC-REVISION-CONTEXT](../.knowledge/cards/20260811-1630-FIX-BUGFIX-SPEC-REVISION-CONTEXT.md) | `backend/agents/authz.py`, `backend/agents/capabilities/strategies/task_loop.py`, `backend/agents/execution_engine/clarify_engine.py`, `backend/agents/execution_engine/engine.py`, `backend/agents/execution_engine/kernel_services.py`, `backend/agents/factory.py`, `backend/agents/prompts/prototype-specify/AGENT.md`, `backend/app/agents/chat/concierge.py`, `backend/app/agents/deep_agent_runner.py`, `backend/tests/agents/_scripted_model.py`, `backend/tests/agents/test_restart_resume.py`, `frontend/src/hooks/useWorkflow.ts` | Diagnosed: update_specs never injects the prior spec into the revision prompt, and a resumed run rebuilds planning_cont… |
| [ISS-018](../.knowledge/cards/20260614-0619-ISS-018.md) | — | The hexaware-srini AWS profile lost Bedrock ConverseStream entitlement mid-session (not quota or expiry); campaign swit… |
| [ISS-020](../.knowledge/cards/20260614-0619-ISS-020.md) | — | The rewrite harness only changes the backend pipeline_type, not the FE's displayed workflow labels, for fixture scenari… |
| [ISS-071](../.knowledge/cards/20260812-0107-ISS-071.md) | — | The artifact-kind fallback maps any agent outside a 4-agent prototype list to 'summary', so every non-prototype workflo… |
| [ISS-076](../.knowledge/cards/20260812-0212-ISS-076.md) | `.planning/TEST-REGISTER.md`, `frontend/playwright.config.ts` | TEST-REGISTER's '123-132 green' Playwright figure is stale feat/ui-2 data; the real baseline on this branch is 33 faile… |
| [ISS-077](../.knowledge/cards/20260812-0212-ISS-077.md) | `backend/app/api/runs.py`, `frontend/src/components/history/WorkflowHistory.tsx`, `frontend/src/lib/api.ts` | api.ts declares derived_from/children as string arrays but the backend returns a nullable string and nested ArtifactNod… |
| [ISS-079](../.knowledge/cards/20260812-0236-ISS-079.md) | `backend/tests/agents/test_phase6_frontend_consistency.py` | A stale test hardcodes the pre-analyze 4-agent prototype id set after commit 5c947270 added prototype-analyze, making t… |
| [ISS-094](../.knowledge/cards/20260812-1120-ISS-094.md) | `backend/agents/execution_engine/engine.py`, `backend/tests/agents/test_gate_stub_signature_drift.py`, `backend/tests/agents/test_gates.py` | Hand-rolled test doubles are missing attributes the engine now reads, a drift class the FIX-231 signature guard cannot … |
| [ISS-096](../.knowledge/cards/20260812-1120-ISS-096.md) | `backend/tests/agents/live_harness.py`, `backend/tests/agents/test_live_contract.py`, `backend/tests/agents/test_phase3_token_delta_live.py`, `backend/tests/agents/test_prompt_contracts.py` | A prompt-contract test still asserts a sentence no longer present in the od-ppt-validator prompt; unclear whether the p… |
| [ISS-100](../.knowledge/cards/20260812-1232-ISS-100.md) | `backend/app/agents/handoff/coder.py`, `backend/app/agents/handoff/compliance_agent.py`, `backend/app/agents/handoff/test_agent.py`, `backend/app/api/run_commands.py`, `backend/app/api/websocket_handoff.py`, `backend/app/services/handoff_pipeline.py` | Three handoff call sites accept a usage_sink but are never given one, and handoff_sessions has no token column to even … |
| [ISS-104](../.knowledge/cards/20260812-1312-ISS-104.md) | `backend/agents/execution_engine/engine.py`, `backend/app/api/run_commands.py`, `backend/app/api/run_shutdown.py`, `backend/app/core/config.py` | Multiple in-code citations to shutdown-path line numbers had drifted from the code they described, misdirecting anyone … |
| [ISS-105](../.knowledge/cards/20260812-1312-ISS-105.md) | `backend/app/api/run_stream.py` | uvicorn cancels SSE tasks then calls lifespan.shutdown() without awaiting them, letting shutdown snapshot pipeline queu… |
| [ISS-107](../.knowledge/cards/20260812-1400-ISS-107.md) | — | dashboard/page.tsx dispatches the hook_run message but its payload never lands on state, so hookRuns' only consumer is … |
| [ISS-109](../.knowledge/cards/20260812-1400-ISS-109.md) | `backend/app/api/capabilities.py`, `frontend/src/components/results/AgentDetailPanel.tsx`, `frontend/src/hooks/useWorkflow.ts` | validator_result and gate_passed are never emitted in non-test backend code, so validationIssues may be structurally un… |
| [ISS-111](../.knowledge/cards/20260812-1444-ISS-111.md) | `.planning/IMPLEMENTATION-REGISTER.md`, `backend/app/agents/chat_narrator.py`, `backend/app/api/runs.py`, `backend/tests/unit/test_chat_narrator.py`, `frontend/src/hooks/useRunChat.ts` | chat_narrator's spec_revision branch checks first and outranks every other card kind, yet nothing ever writes the paylo… |
| [ISS-112](../.knowledge/cards/20260812-1444-ISS-112.md) | `frontend/src/components/results/AgentThinkingTab.tsx`, `frontend/src/components/results/StartingPointCard.test.tsx`, `frontend/src/components/results/StartingPointCard.tsx` | The sole production mount of StartingPointCard never passes attachmentRefs, so the 'image not retained' placeholder can… |
| [ISS-113](../.knowledge/cards/20260812-1444-ISS-113.md) | `frontend/src/components/history/WorkflowHistory.tsx`, `frontend/src/components/preview/PreviewPanel.tsx`, `frontend/src/components/results/AuditTab.tsx` | Neither mount of AuditTab passes runMeta, so the audit header's owner and workspace fields are permanently null. |
| [ISS-115](../.knowledge/cards/20260812-1511-ISS-115.md) | `frontend/src/components/results/AgentThinkingTab.tsx`, `frontend/src/components/results/artifactPreview.tsx`, `frontend/src/hooks/useWorkflow.ts` | useWorkflow.ts keeps its own line-anchored Task-N regex separate from FIX-237's extracted parser, and unifying them isn… |
| [ISS-116](../.knowledge/cards/20260812-1511-ISS-116.md) | `backend/agents/capabilities/gates/write.py`, `backend/app/api/capabilities.py`, `frontend/src/components/results/AgentDetailPanel.tsx`, `frontend/src/hooks/useWorkflow.ts` | gate_passed and validator_result have zero backend producers, so the green 'Passed' chip can never render and the amber… |
| [ISS-119](../.knowledge/cards/20260812-1612-ISS-119.md) | `backend/app/api/run_commands.py` | Two tests assert bare text routes to answers/gate channels, but the router now deliberately routes ambiguous text to Co… |
| [ISS-122](../.knowledge/cards/20260812-1804-ISS-122.md) | — | An unmetered-legacy spend window dilutes the real cache delta below the zero-suppression threshold, so the line renders… |
| [ISS-127](../.knowledge/cards/20260812-2045-ISS-127.md) | `backend/agents/execution_engine/engine.py`, `backend/app/api/run_commands.py`, `backend/app/api/run_engine.py` | GateCommand.analysis_report flows uncapped into the composed spec-revision prompt on every dispatch, a cost-amplificati… |
| [ISS-128](../.knowledge/cards/20260812-2046-ISS-128.md) | `backend/agents/capabilities/gates/human.py`, `backend/agents/execution_engine/engine.py`, `backend/app/api/run_commands.py` | The gate reject branch never passes action= to set_review_response, so the store's default stamps a false 'approve' on … |
| [ISS-129](../.knowledge/cards/20260812-2116-ISS-129.md) | — | fanout.py's worker loop forwards nothing but agent_complete token counts, so a worker's error, cancel or gate-ready eve… |
| [ISS-130](../.knowledge/cards/20260812-2116-ISS-130.md) | `backend/agents/execution_engine/kernel_services.py` | N parallel fan-out workers share one ExecutionContext's scratch fields, an unverified interleaving hazard masked only b… |
| [ISS-134](../.knowledge/cards/20260812-2140-ISS-134.md) | `backend/app/api/run_engine.py` | Cancel liveness is decided from process-local dicts, sound only while single-process; the locked ECS Fargate migration … |
| [ISS-135](../.knowledge/cards/20260813-0005-ISS-135.md) | — | payload_json.seq gets re-stamped after append_event_at_or_after returns, so the payload's seq can lag the row's real se… |
| [ISS-136](../.knowledge/cards/20260813-0005-ISS-136.md) | `backend/app/api/chat_router.py`, `frontend/src/components/layout/DashboardLayout.tsx`, `frontend/src/components/preview/PreviewPanel.tsx`, `frontend/src/hooks/useWorkflow.reconnect.test.ts`, `frontend/src/hooks/useWorkflow.ts` | Four FE terminal-status lists disagree (one is missing 'degraded'); FIX-245 already cut it to one canonical list, remai… |
| [ISS-137](../.knowledge/cards/20260813-0005-ISS-137.md) | `backend/app/api/run_stream.py`, `frontend/src/hooks/useWorkflow.reconnect.test.ts` | pipeline_reconnected is a dead frame — no backend path emits it since stream_attached replaced it — yet a live reducer … |
| [ISS-142](../.knowledge/cards/20260813-0005-ISS-142.md) | `.planning/IMPLEMENTATION-REGISTER.md`, `backend/app/api/run_stream.py`, `frontend/src/hooks/useWorkflow.ts` | SSE's stream_attached ack dropped the status field pipeline_reconnected used to carry (D-13); evaluated as an ISS-126 f… |
| [ISS-154](../.knowledge/cards/20260813-0819-ISS-154.md) | `backend/app/api/run_commands.py`, `frontend/src/components/preview/PreviewPanel.tsx` | Switching to an older revision whose .output is NULL (a pre-FIX-250 row) shows a blank 'Output will appear here' previe… |
| [ISS-156](../.knowledge/cards/20260813-1300-ISS-156.md) | `backend/tests/unit/test_run_commands_fix218.py`, `frontend/src/hooks/useChatAttachments.test.ts` | dev merged FIX-218 with 5 red tests: 2 assert a prompt string dev's code no longer emits, 2 more in useChatAttachments;… |
| [ISS-159](../.knowledge/cards/20260813-1300-ISS-159.md) | — | Chained runs record no lineage — chaining inlines the parent's context into the child's input text, but neither parent_… |
| [ISS-160](../.knowledge/cards/20260813-1300-ISS-160.md) | — | The Concierge is unreachable on a revision run — it returns pipeline_not_entitled while the identical question on the p… |
| [ISS-161](../.knowledge/cards/20260813-1300-ISS-161.md) | `backend/app/api/run_commands.py` | A pure question posted to a parent run over REST /messages was misclassified as a revision and minted a new run, which … |
| [ISS-173](../.knowledge/cards/20260825-0955-ISS-173.md) | `backend/agents/workflows/ex_A3_divert/workflow.yaml`, `backend/agents/workflows/ex_A4_human_gate/workflow.yaml`, `backend/tests/agents/test_conditional_divert_v4_validation.py`, `backend/tests/agents/test_conditional_human_gate_source_t26.py` | c9ec0149c renamed sample_conditional_* to ex_A*; two test files kept the old step ids (decide, revise-check) and target… |
| [ISS-174](../.knowledge/cards/20260825-0956-ISS-174.md) | `backend/agents/workflows/ex_A1_loop/workflow.yaml`, `backend/agents/workflows/ex_A2_branch/workflow.yaml`, `backend/agents/workflows/ex_A3_divert/workflow.yaml`, `backend/agents/workflows/ex_A4_human_gate/workflow.yaml`, `backend/tests/agents/test_id_alias_resolver.py`, `backend/tests/agents/test_manifest_parity.py` | ex_A* declare planner: skip and empty clarify.defaults; test_planner_run_everywhere and test_clarify_defaults_match_eng… |
| [ISS-179](../.knowledge/cards/20260825-1600-ISS-179.md) | — | 215b911e0 "removed screenshots" deleted 56 files including README.md, README.txt, docker-compose.yml, docker-compose.pr… |
| [ISS-180](../.knowledge/cards/20260825-2115-ISS-180.md) | `backend/app/api/user_workflows.py`, `backend/app/models/workflow_definition.py` | Migration 0039 stores the base manifest version at save time, but nothing compares it — an override keeps running its o… |
| [ISS-181](../.knowledge/cards/20260825-2115-ISS-181.md) | `backend/agents/execution_engine/overrides.py`, `backend/app/api/composition_order.py`, `backend/app/api/user_workflows.py` | An override can be saved, shown, and still be unlaunchable: the compiler accepts steps that presort_specs' produces/con… |
| [ISS-183](../.knowledge/cards/20260825-2115-ISS-183.md) | `frontend/src/components/workflow/composer/ComposerPage.tsx` | The hardcode is deliberate — workflowType is a shared mutable other screens set — but it means the full canvas cannot a… |
| [ISS-186](../.knowledge/cards/20260826-0124-ISS-186.md) | — | Commit 215b911e0 deleted docker-compose.yml, docker-compose.prod.yml, README.md and app.env.example alongside the scree… |
| [ISS-187](../.knowledge/cards/20260826-1547-ISS-187.md) | `backend/app/core/entitlements.py`, `frontend/src/lib/entitlements.ts` | All 7 spec-014 ex_A* gate fixtures declare user_launchable: true and sit in the enterprise tier on both sides, so QA fi… |
| [ISS-189](../.knowledge/cards/20260828-1457-ISS-189.md) | `frontend/src/components/workflow/LaunchWizard.tsx` | Investment Banking Pitch Book template shows "Pick a design system" pill with no picker UI; PPT mode never sets selecte… |
| [ISS-192](../.knowledge/cards/20260828-1345-ISS-192.md) | `frontend/src/components/workflow/composer/ComposerPage.tsx` | needsFullManifest(pipelineAgents) is false for an unmodified built-in copy, so ComposerPage.tsx:628-629 sends no manife… |
| [ISS-217](../.knowledge/cards/20260828-1649-ISS-217.md) | `frontend/src/app/[...view]/page.tsx`, `frontend/src/app/handoff/settings/page.tsx`, `frontend/src/app/login/page.tsx`, `frontend/src/components/workflow/LaunchWizard.tsx` | Measured: React never hydrates on a transferSize:0 back_forward replay, so page.tsx:3701's mount-once gate is not the c… |
| [ISS-219](../.knowledge/cards/20260828-1706-ISS-219.md) | `frontend/src/components/history/RevisionFamilyView.tsx`, `frontend/src/components/history/WorkflowHistory.tsx`, `tests/integration/e2e/suites/06_run_history/test_run_history.py`, `tests/integration/e2e/suites/06_run_history/test_run_history_pagination.py`, `tests/integration/screens/06-run-history.feature.md` | qa-admin holds 275 runs but only 232 family cards, so "All chip == header" (S-06-04) and "rows == chip" (S-06-05) canno… |
| [ISS-223](../.knowledge/cards/20260828-1735-ISS-223.md) | `backend/agents/capabilities/deliverables/ppt.py`, `backend/agents/workflows/compiler.py`, `backend/app/api/user_workflows.py`, `frontend/src/components/workflow/composer/ComposerPage.tsx` | `deliverable/ppt` is registered without user_allowed, so `_validated_manifest` compiles at trust="db" and 422s any save… |
| [ISS-325](../.knowledge/cards/20260828-2014-ISS-325.md) | `frontend/src/components/history/WorkflowHistory.tsx`, `tests/integration/e2e/suites/21_run_families_and_versions/test_run_families_and_versions.py` | RH.chip_count times out on `^Presentation\s*\d` at /runs; the test asserts named == rows == All, an equality its docstr… |
| [ISS-334](../.knowledge/cards/20260828-2045-ISS-334.md) | `frontend/src/app/[...view]/page.tsx`, `frontend/src/components/workflow/composer/ComposerPage.tsx` | page.tsx:494-496 catches ANY getWorkflowDetail failure, not just 404, so a transient error on a REAL workflow id reache… |
| [ISS-340](../.knowledge/cards/20260828-1856-ISS-340.md) | `frontend/src/components/workflow/composer/CanvasView.tsx`, `frontend/src/components/workflow/composer/ComposerPage.tsx`, `frontend/src/components/workflow/composer/IdentityCard.tsx` | PPT deliverable type: Simple hardcodes "Custom" (ComposerPage.tsx:478); Canvas derives it from runConfig (CanvasView.ts… |
| [ISS-346](../.knowledge/cards/20260828-2058-ISS-346.md) | `backend/app/api/runs.py`, `frontend/src/components/layout/DashboardLayout.tsx`, `frontend/src/lib/api.ts` | The list endpoint drops `input`, so normalizeWorkflowRun sets it undefined and `viewedRun?.input \|\| submittedBrief` a… |
| [ISS-347](../.knowledge/cards/20260828-2058-ISS-347.md) | `frontend/src/components/layout/DashboardLayout.tsx`, `frontend/src/components/workflow/LaunchWizard.tsx` | LaunchWizard's restore effect returns early on any `chain.brief` in sessionStorage before it reads `ppt.draft`/`prototy… |
| [ISS-362](../.knowledge/cards/20260828-2121-ISS-362.md) | `frontend/src/components/workflow/IdeaInputPage.tsx`, `frontend/src/components/workflow/LaunchWizard.tsx`, `frontend/src/components/workflow/ReviewGatesSection.tsx`, `frontend/src/components/workflow/composer/CanvasConfigRail.tsx` | INFERRED inverse of ISS-247: CanvasConfigRail.tsx:354-357 patch()/selectGate only calls onSelection(agent.id, next) on … |
| [ISS-373](../.knowledge/cards/20260828-2142-ISS-373.md) | `frontend/src/components/layout/DashboardLayout.tsx`, `frontend/src/components/workflow/composer/ComposerPage.tsx` | Same ComposerPage.tsx:979 onClick={onBack}/handleBackNav gap also fires on /workflows/{id}/edit, discarding edits to an… |
| [ISS-377](../.knowledge/cards/20260828-2202-ISS-377.md) | `backend/agents/workflows/manifest.py`, `backend/app/api/user_workflows.py`, `frontend/src/components/workflow/IdeaInputPage.tsx`, `frontend/src/components/workflow/LaunchWizard.tsx`, `frontend/src/types/index.ts` | deferred by FIX-336: an override row persists `manifest`, which `_reject_both` makes exclusive with `selections`, and `… |
| [ISS-381](../.knowledge/cards/20260828-2210-ISS-381.md) | `backend/agents/workflows/selections.py`, `backend/app/api/user_workflows.py`, `frontend/src/components/workflow/IdeaInputPage.tsx` | Save workflow on ex_A4_human_divert returns 422 "agent_ids not allowed for" from the roster check at user_workflows.py:… |
| [ISS-407](../.knowledge/cards/20260828-2343-ISS-407.md) | `frontend/src/app/preview-fullscreen/page.tsx` | page.tsx:58-72 three failure exits (no raw value, empty files, parse error) all go straight to router.replace(runHistor… |
| [ISS-410](../.knowledge/cards/20260828-2344-ISS-410.md) | `frontend/src/app/[...view]/page.tsx`, `frontend/src/components/workflow/composer/ComposerPage.tsx` | page.tsx:494-496 catches ANY getWorkflowDetail failure, not just 404, so a transient error on a REAL workflow id reache… |
| [ISS-419](../.knowledge/cards/20260829-0022-ISS-419.md) | `backend/app/api/workflows.py`, `frontend/src/components/workflow/ReviewGatesSection.tsx` | checkedIds seeds only from AgentDef.gate/initialGateIds, never a step's manifest gates array — any custom-agent gate va… |
| [ISS-434](../.knowledge/cards/20260828-2240-ISS-434.md) | `frontend/src/components/chat/RunChatLane.tsx` | RunChatLane.SettledSummaryStrip skips DeliverableCard when dFilename is falsy, same unfallback-ed deliverable_filename … |
| [ISS-442](../.knowledge/cards/20260829-0106-ISS-442.md) | `frontend/src/app/[...view]/workflowDetailCatch.source.test.ts` | the F7 source-lock counts occurrences of a shared idiom rather than asserting the T30 effect uses it, so ISS-380 and FI… |
| [ISS-579](../.knowledge/cards/20260829-0234-ISS-579.md) | `frontend/src/app/workflow/page.tsx`, `frontend/src/components/workflow/WorkflowView.tsx` | WorkflowView.tsx:165 passes ideaInput.trim() (can carry ISS-345's orphaned [Attached] marker) verbatim to onStartPipeli… |
| [ISS-604](../.knowledge/cards/20260829-0207-ISS-604.md) | `frontend/src/app/[...view]/page.tsx`, `frontend/src/components/workflow/composer/ComposerPage.tsx` | ComposerPage's seededRunConfig effect adopts initialRunConfig only after the GET /api/workflows/<type> fetch resolves, … |
| [ISS-623](../.knowledge/cards/20260831-0115-ISS-623.md) | `tests/integration/e2e/suites/04_composer_canvas/test_composer_canvas.py`, `tests/integration/e2e/suites/05_saved_workflows/test_saved_workflows.py` | da92b4a4 lost report-generator on 2026-08-29 and is the plain 3-agent ppt base now, so the saved roster no longer diffe… |
| [ISS-629](../.knowledge/cards/20260831-0115-ISS-629.md) | `frontend/src/components/history/RunDetailPage.tsx`, `frontend/src/components/history/WorkflowHistory.tsx`, `tests/integration/screens/21-run-families-and-versions.feature.md` | WorkflowHistory.handleSelectRun routes every tap to the shared run screen (BUG-002), so the timeline region S-21-07/08/… |
| [ISS-630](../.knowledge/cards/20260831-0115-ISS-630.md) | `backend/tests/integration/test_revision_analyzer_integration.py` | the 500 is the ISS-102 offline live-model guard firing on a build_model seam the test never stubs; stub that seam and t… |
| [ISS-632](../.knowledge/cards/20260831-0115-ISS-632.md) | `backend/tests/agents/test_engine_runner_error_arm.py`, `backend/tests/unit/test_pipeline_failure_semantics.py` | the harnesses slice get_pipeline_agents("user_stories")[:2], the ADR-0008 roster seam (engine.py:1720-1723) fills a str… |
| [ISS-634](../.knowledge/cards/20260831-0115-ISS-634.md) | `backend/tests/agents/test_chunk_sanitizer.py` | root cause DISPROVED by 5-fixer: the sanitizer passes all four cases through byte-identically; the harness _drive_singl… |
| [ISS-638](../.knowledge/cards/20260831-0115-ISS-638.md) | `backend/tests/agents/test_phase5_revision_validation.py`, `backend/tests/agents/test_phase8_live.py`, `backend/tests/agents/test_text_only_prompt_hygiene.py`, `backend/tests/agents/test_tool_grant_invariants.py`, `backend/tests/unit/test_workflows_api.py` | one each in tool_grant_invariants, text_only_prompt_hygiene, phase5 (x2), phase8_live and workflows_api; measured — 1 r… |
| [ISS-639](../.knowledge/cards/20260831-1645-ISS-639.md) | `backend/agents/execution_engine/engine.py` | resume_run and _replay_clarify_run seed the sink counter with read_events(after_seq=0) + max(seq)+1 — the same unbounde… |
| [ISS-640](../.knowledge/cards/20260831-1814-ISS-640.md) | `backend/app/agents/deep_agent_runner.py` | FIX-427 closed only the cached_invoke half of ISS-120; the middleware at deep_agent_runner.py:283 has one construction … |
| [ISS-641](../.knowledge/cards/20260831-1818-ISS-641.md) | `backend/tests/unit/test_shutdown_reachability.py` | Nothing asserts the shutdown budget fits the SIGKILL deadline any more; the helper that computes it is called only from… |
| [ISS-642](../.knowledge/cards/20260831-1842-ISS-642.md) | `backend/tests/agents/test_revision_gating.py`, `backend/tests/unit/test_concierge_proposal_channels.py` | both tests pin behaviour production deliberately replaced — tier classification and the parent-uploads seed — so greeni… |

