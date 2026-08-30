# WONTFIX candidates

Entries here are bugs that reproduced 3/3 but whose behaviour appears intentional per source
comments or design intent. A human rules on the final disposition — Status on the register entry
is left untouched pending that ruling.

---

## BUG-20260828-013500-runs-id-workspace

- **Symptom:** Workspace tab's "Code" file viewer (`SandboxTab.tsx`'s `CodeView`) is a live,
  freely-editable CodeMirror instance (`.cm-content` has `isContentEditable === true`) for a
  completed/immutable run, with no read-only indicator, no lock icon, no "editing" badge, and no
  Save/Discard affordance. Typed edits render live and are silently discarded on navigating away
  (confirmed 3/3 cold-start reproductions across three different files: `.browser/deck-styles.json`,
  `PLANNER.md`, `.agents/01-ppt-brief-analyst.md`).
- **Why it may be intentional:** `frontend/src/components/results/SandboxTab.tsx` lines 476-491
  and 687-690 carry an explicit source comment:
  > "⌘F opens Find AND Replace. Replace has to be able to write, so the doc is editable — but it
  > is a SCRATCHPAD: there is no save path for a run artifact, and Download always re-fetches the
  > server's bytes, so nothing you do here can alter what shipped."

  The component doc-comment at the top also explicitly labels it "Source, in a real editor" and
  describes the editability as a deliberate tradeoff to support CodeMirror's built-in
  Find-and-Replace panel (`search.search({ top: true })`), not an oversight. The lack of
  persistence was verified independently: no `PUT`/`POST`/`PATCH` request ever fires after typing
  (confirmed via `browser_network_requests` across all 3 repro cycles), and switching files
  re-fetches the original bytes from `GET /api/runs/{id}/sandbox/file`.
- **What's arguably still a real gap:** even if editability itself is by design (for
  Find&Replace), the UI gives the user zero signal that what looks like a passive "preview" pane
  accepts keystrokes, and silently discards them with no warning — a plausible UX bug independent
  of the "editable for search/replace" rationale. That narrower framing (missing affordance/
  warning, not "should be read-only") is the part a human should rule on.
- **Repro:** `/runs/b9feac1c-ec21-4531-8ba7-bb391786993e/workspace`, qa-admin, cold start x3,
  each on a different file — 3/3.
- **Evidence:** `bug-hunter/evidence/runs-id-workspace/_scratch/cycle1-editable.png`,
  `cycle2-planner-editable.png`, `cycle3-agents-md-editable.png`
- **Register entry:** `BUG-20260828-013500-runs-id-workspace` in `bug-hunter/ledger.md`

---

**UPDATE 2026-08-29 (run close):** This entry is now stale/superseded, not an open WONTFIX
candidate. A later card (ISS-383, filed during the same run) found the component's own
top-of-file doc comment claims the pane is "read-only," contradicting the inline comment a few
lines below that frames editability as deliberate (for CodeMirror's built-in Find-and-Replace)
— the doc comment, not the implementation, was the stale artifact. FIX-409 added a visible
"Read-only scratchpad — edits are not saved" indicator while leaving the CodeMirror doc
writable (Replace still needs to dispatch transactions). The bug is now **CLOSED** via
FIX-409/ISS-383, not WONTFIX. Left this original entry in place as a record of the earlier
finding rather than deleting it — a human may want to remove it now that the underlying
concern is resolved.
