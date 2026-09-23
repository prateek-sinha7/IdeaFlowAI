# Domain 5 — frontend·preview — run report

**Date:** 2026-09-01  
**Cards:** 7 scheduled (ISS-433, ISS-596, ISS-251, ISS-388, ISS-389, ISS-599, ISS-609)  
**Batches:** 2 (B1 round 1 · B2 round 5)  
**Outcome:** DONE — 7 closed, 0 reopened, 0 escalated

---

## Cards closed

| card | FIX | mode | test result |
|---|---|---|---|
| ISS-433 | FIX-446 | REPLICATE (FIX-378 shape) | tsc EXIT=0; manual — no e2e test exists yet |
| ISS-596 | FIX-447 | FULL (test-side fix) | vitest XPASS (it.fails strict) |
| ISS-388 | FIX-448 | ALREADY_FIXED (FIX-358) | PreviewPanel.degraded 11/11 |
| ISS-389 | FIX-448 | ALREADY_FIXED (FIX-358) | PreviewPanel.degraded 11/11 |
| ISS-251 | FIX-449 | FULL (refactor + mock) | PreviewPanel.test 19/19 |
| ISS-599 | FIX-449 | FULL (clipboard hook) | tsc EXIT=0; no dedicated unit test |
| ISS-609 | FIX-450 | FULL (one-prop change) | tsc EXIT=0; e2e needs live servers |

---

## What changed

### Batch 1 — round 1

**ISS-433 / FIX-446 — PrototypePreview.tsx**  
Added `flex-wrap` to the browser-chrome outer div (line ~500), replicating the
exact shape of FIX-378 on `PreviewPanel.tsx:1203`. At any width where controls fit
on one line the rendering is byte-identical to before; narrower viewports wrap the
action cluster to a second line rather than pushing it off-screen.

**ISS-596 / FIX-447 — PreviewPanel.appBuilderSearch.test.tsx**  
Changed the final assertion from `screen.getByText("app.js")` to
`screen.getAllByText("app.js").length > 0`. The old form threw
`TestingLibraryElementError: Found multiple elements` because `src/app.js` is
`files[0]` and `AppBuilderPreview`'s mount effect auto-opens it as an editor tab.
The `it.fails` marker and the substantive `queryByText("styles")` assertion are
unchanged. vitest now reports XPASS (the it.fails strict signal).

### Batch 2 — round 5

**ISS-388 + ISS-389 / FIX-448 — ALREADY_FIXED**  
Both confirmed cured by FIX-358. `PreviewPanel.tsx` carries
`showFailureAffordance || showDivertedAffordance` at the Preview tab render branch
(not just `showCancelledAffordance`). The `reopenTabFor` case for `run-preview-full`
is confirmed present (FIX-358 notes). No new code needed. Verified by
`PreviewPanel.degraded.test.tsx` 11/11.

**ISS-251 + ISS-599 / FIX-449 — PreviewPanel.tsx + PreviewPanel.test.tsx**  
- ISS-251: The ~60-line inline deliverable-resolution `try` block (duplicate of
  `resolveRunDeliverable` in `api.ts`) collapsed to a single `resolveRunDeliverable`
  call. The ISS-313 bundle path (`!declared → serve whole workspace ZIP`) is kept
  separately since `resolveRunDeliverable` returns null for no-declared. New import
  added: `resolveRunDeliverable` from `@/lib/api`. Test mock updated with an
  inline stub routing through `mockGetRunSandbox` — all 5 download tests pass
  unchanged.
- ISS-599: `handleHeaderShare` replaced `void navigator.clipboard?.writeText(link)`
  with `void copyToClipboard(link)` from `useClipboardCopy()` (new import). A
  clipboard-permission denial now propagates through the hook's error state rather
  than being silently swallowed.

**ISS-609 / FIX-450 — PreviewPanel.tsx**  
`AuditTab`'s `workflowRunId` prop changed from `effPipelineState?.pipelineRunId`
to `activeRunId ?? undefined`. `activeRunId = viewingVersion?.id ?? unpinnedRunId`
is already the single version-aware id that `FilesTab` and `SandboxTab` use. The
prior `effPipelineState?.pipelineRunId` indirection was inconsistent across
re-render orderings. This card was reopened 2026-08-31 after a premature close —
the root cause was confirmed by re-reading the card and the AuditTab fetches.

---

## Files changed

| file | cards |
|---|---|
| `frontend/src/components/preview/PrototypePreview.tsx` | ISS-433 |
| `frontend/src/components/preview/PreviewPanel.appBuilderSearch.test.tsx` | ISS-596 |
| `frontend/src/components/preview/PreviewPanel.tsx` | ISS-251, ISS-599, ISS-609 |
| `frontend/src/components/preview/PreviewPanel.test.tsx` | ISS-251 (mock update) |

---

## Knowledge rebuild

| stage | result |
|---|---|
| index (build_index.py) | SUCCESS — 32 related blocks updated, 1133 cards indexed (fix:463) |
| context (build_context.py) | FAILED — pre-existing UnicodeDecodeError cp1252 0x90 on one MOD-*.md card. Not ours, not retried. |
| dedup (dedup.py) | SUCCESS — 186 open cards (was 200+); 218 resolved. All 7 domain-5 ISS cards in ✅ Closed section. |

---

## Test summary

```
tsc --noEmit                                 EXIT=0  (all runs)
PreviewPanel.test.tsx                        19/19   PP_EXIT=0
PreviewPanel.degraded.test.tsx               11/11   DEGRADED_EXIT=0
PreviewPanel.appBuilderSearch.test.tsx       XPASS   SEARCH_EXIT=1 (it.fails signal)
```

---

## Ready to commit

Suggested commit messages per card:

```
fix(preview): add flex-wrap to PrototypePreview browser-chrome bar (ISS-433, FIX-446)

fix(preview): disambiguate appBuilderSearch test trailing getByText (ISS-596, FIX-447)

docs(knowledge): close ISS-388 + ISS-389 confirmed fixed by FIX-358 (FIX-448)

refactor(preview): collapse inline deliverable-resolve to resolveRunDeliverable;
  route share clipboard through useClipboardCopy (ISS-251+ISS-599, FIX-449)

fix(preview): AuditTab workflowRunId → activeRunId for version-pin correctness
  (ISS-609, FIX-450)
```

**Staged files (ready for operator `git commit`):**
- `.kiro/bug-fix-workflow/STATE.md`
- `.kiro/bug-fix-workflow/reports/20260901-1545-domain-05-frontend-preview.md`
- `.kiro/bug-fix-workflow/domains/05-frontend-preview.md`
- `.knowledge/INDEX.md`
- `.knowledge/state.yaml`
- `.knowledge/cards/20260901-1530-FIX-446.md`
- `.knowledge/cards/20260901-1530-FIX-447.md`
- `.knowledge/cards/20260901-1530-FIX-448.md`
- `.knowledge/cards/20260901-1530-FIX-449.md`
- `.knowledge/cards/20260901-1530-FIX-450.md`
- `.knowledge/cards/20260829-0040-ISS-433.md`
- `.knowledge/cards/20260829-0127-ISS-596.md`
- `.knowledge/cards/20260828-1846-ISS-251.md`
- `.knowledge/cards/20260828-2234-ISS-388.md`
- `.knowledge/cards/20260828-2234-ISS-389.md`
- `.knowledge/cards/20260829-0340-ISS-599.md`
- `.knowledge/cards/20260829-1420-ISS-609.md`
- `bug-hunter/OPEN-ISSUES-DEDUP.md`
- `frontend/src/components/preview/PrototypePreview.tsx`
- `frontend/src/components/preview/PreviewPanel.appBuilderSearch.test.tsx`
- `frontend/src/components/preview/PreviewPanel.tsx`
- `frontend/src/components/preview/PreviewPanel.test.tsx`

---

## Needs a human

**ISS-609 e2e test** — `tests/integration/e2e/suites/21_run_families_and_versions/test_iss_606_609_version_pin_ignored_by_agent_data.py` needs the live servers (frontend :3000 + backend :8000) and the e2e `.venv`. The unit tests cannot cover the AuditTab fetch interception. The 6-verifier should run this once servers are up.

**ISS-596 it.fails marker** — `PreviewPanel.appBuilderSearch.test.tsx` still carries `it.fails`. Per workflow protocol the 6-verifier removes it after independent confirmation.

**ISS-433 e2e coverage gap** — No automated narrow-viewport test exists for PrototypePreview chrome (ISS-433 had `verification.type: manual`). A test mirroring `test_iss314_preview_toolbar_fullscreen_offscreen.py` would be the proper follow-up.

---

## Pre-existing issues (not ours)

- `build_context.py` stage 2 UnicodeDecodeError on one MOD-*.md card with a non-UTF-8 byte (cp1252 0x90). Documented in STATE.md global notes. `CONTEXT.md` stays stale.
