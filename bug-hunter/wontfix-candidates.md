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

---

## ISS-119 — TestRouting clarify/gate routing (backend·api, domain 14)

- **Symptom (as filed):** two `TestRouting` unit tests asserting a superseded routing contract
  were failing.
- **Why it's a close-as-resolved candidate, not a live bug:** the two tests the card names by
  name (`test_clarify_waiting_routes_to_answers_seam`, `test_gate_paused_routes_to_gate_seam_approve`)
  no longer exist under those names — someone already reconciled them to
  `test_clarify_waiting_plain_text_routes_to_concierge` /
  `test_gate_paused_plain_text_routes_to_concierge`, both asserting `CHANNEL_CONCIERGE`, which
  matches the card's own stated preferred resolution. Whole-file run
  (`backend/tests/unit/test_chat_messages_endpoint.py`): 21 passed, 0 red. A candidate test
  written for the card's one remaining, genuine ask (structured clarify answer routes to
  `answers` at the endpoint level) passed on first run — not a defect proof, so it was not
  shipped as an xfail (would XPASS and fail for the wrong reason).
- **Proposed disposition:** close as already-resolved, or re-scope to a plain (non-xfail)
  coverage-addition task outside the bug-hunt pipeline.
- **Register entry:** ISS-119 row in `.kiro/bug-fix-workflow/domains/14-backend-api.md`
  (status: ESCALATED).
- **Run:** 2026-08-31T18:06:11Z, see `bug-hunter/reports/20260831T180611Z-all.md`.

---

## ISS-133 — `_stamp_resume_marker` collision-unsafe seq allocation (backend·api, domain 14)

- **Symptom (as filed):** `ExecutionEngine._stamp_resume_marker`'s seq allocation
  (`read_events → max+1 → append_event`) is collision-unsafe.
- **Why it's a close-as-duplicate candidate:** the fix is already shipped at HEAD.
  `engine.py:7694-7755` uses the collision-safe `store._max_event_seq(run_id)` +
  `append_event_at_or_after` pair, and its own docstring cites ISS-125 as the fix that landed
  it. ISS-125's existing regression test
  (`backend/tests/agents/test_resume_marker_seq_allocation.py`) already covers this exact call
  site and passes at HEAD (1 passed, ran offline). No red test can be written against ISS-133
  without XPASSing an `xfail(strict=True)` immediately.
- **Proposed disposition:** close as duplicate of the shipped ISS-125 fix.
- **Register entry:** ISS-133 row in `.kiro/bug-fix-workflow/domains/14-backend-api.md`
  (status: ESCALATED).
- **Run:** 2026-08-31T18:06:11Z, see `bug-hunter/reports/20260831T180611Z-all.md`.

## ADR-0002 — `pipeline`→`workflow` vocabulary rename (backend·other, domain 15, B4)

- **Symptom (as filed):** the grep gate `test_workflow_vocabulary_gate.py` is red
  (`4 xfailed`) because `pipeline` identifiers survive in the four governed files.
- **Why it's a HITL candidate, not a fix:** not implementable inside the governed globs.
  `pipeline_type` is a public wire key (93 frontend files consume it), an AGENT.md
  frontmatter field (94 files on disk), imported by 22-26 backend modules, and 3 DB
  columns carry the label — renaming those is a non-additive migration, which
  `.knowledge/CONTEXT.md` forbids. The card's own text names three mutually exclusive
  resolutions (execute the full coordinated rename; narrow the ADR's globs and re-scope
  the gate; supersede the ADR and keep `pipeline_type` on-disk/on-wire) and states none
  of them is a fixer's to pick alone.
- **Proposed disposition:** operator picks one of the three options above; card stays
  `status: deferred` until then.
- **Register entry:** ADR-0002 row in `.kiro/bug-fix-workflow/domains/15-backend-other.md`
  (status: ESCALATED).
- **Run:** 2026-08-31, domain 15 B4, see `bug-hunter/reports/`.

## ISS-094 — hand-rolled double-drift check in the engine (backend·other, domain 15, B4)

- **Symptom (as filed):** card status `open`, verification `passed` — the test already
  green without a fix applied, which is why the run escalated it rather than closing it.
- **Why it's a HITL candidate:** the card's own status/verification pair is inconsistent
  (open card, passing verification) and needs a human read of whether the fix already
  landed elsewhere or the verification is stale, before it can be marked resolved or
  re-queued for a real fix.
- **Proposed disposition:** operator reads `.knowledge/cards/*ISS-094*.md` directly and
  either closes it as already-fixed or clears the verification block to re-open it.
- **Register entry:** ISS-094 row in `.kiro/bug-fix-workflow/domains/15-backend-other.md`
  (status: ESCALATED).
- **Run:** 2026-08-31, domain 15 B4, see `bug-hunter/reports/`.
