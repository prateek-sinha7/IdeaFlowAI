# RUNUI-09 — Mocked e2e reconcile to the Phase-42 run screen (D-42-1)

Branch `feat/ui-2`. Frontend/e2e-only. **Result: `--project=mocked` is GREEN** —
132 passed / 0 failed / 42 skipped, stable across 2 consecutive full runs.
`npx tsc --noEmit` clean; vitest baseline unchanged (8 failed / 694 passed).

## 1. Pre-existing baseline (which of the 33 pre-date Phase 42)

Ran the mocked suite for the 14 failing spec files at commit **8c2f0b9d** (wave-1
tip, before any run-screen change) via a temporary `git worktree` (APFS
copy-on-write node_modules; removed after). Result there: **73 passed / 8 failed**.

The **8 that also fail at 8c2f0b9d are PRE-EXISTING (not Phase 42)** — all
non-run-screen composer/selection/saved-workflow surfaces:

| Test | Spec |
|------|------|
| TS-A-06 enterprise tier enables every workflow | ts-a.auth |
| TS-B-06 'Compose a custom workflow' opens custom input | ts-b.selection |
| TS-C-01 placeholder matches TYPE_CONFIG | ts-c.input-trigger |
| TS-C-02 Run-button disabled states | ts-c.input-trigger |
| TS-D-08 capabilities modal three sections | ts-d.composer |
| TS-G-04 pre-run review-gates hidden when no agents | ts-g.review-gates |
| TS-Z2-01 compose custom → Save persists POST | ts-z2.saved-workflows |
| TS-Z2-02 saved row appears / renames / launches | ts-z2.saved-workflows |

→ Each marked `test.fixme(true, "pre-existing feat/ui-2 red at 8c2f0b9d — not
Phase 42 (RUNUI-09 baseline)")`. Not chased (out of scope).

The remaining **25 of the 33 are Phase-42-caused** run-screen staleness (reconciled below).

## 2. Per-cluster: reconciled vs test.fixme

**Fixed shared page-object first:** `fixtures/dashboard.ts` — `stepsLiveBadge()`
re-pointed from the removed spine "Live" text pill to the running-row pulse
(`steps-agent-row` filtered by `span.animate-pulse`), preserving its "N agents
live" count semantics.

- **TS-N (review gate) ×9 → 8 reconciled + 1 fixme.** ReviewGatePanel DELETED →
  re-anchored onto the inline Steps gate `chat-gate-actions`: header, artifact
  plan-preview (`chat-gate-preview` via `artifactPreview`), Edit textarea,
  "Approve & build"/"Approve with edits & build" (`approve_review` approved:true,
  edited_content null/edited), "Request changes" → two-step "Reject & cancel" →
  "Yes, cancel" (`chat-gate-reject`, approved:false). **TS-N-06** (defensive
  empty-state) → `test.fixme`: the inline gate has no empty-state affordance.
- **TS-M (clarify) ×7 → 3 reconciled + 4 fixme.** QuestionnairePanel "Quick Setup"
  wizard DELETED → re-anchored onto inline `chat-clarify-actions`: TS-M-02 (chips
  render + single "Submit answers & start the build"), TS-M-03 (chip select →
  inverted `text-white`), TS-M-06 (submit → `submit_questionnaire` unchanged +
  `questionnaire_complete` dismiss). **TS-M-04** (hybrid free-text), **TS-M-05a/b/c**
  (per-answer-count "Run {label} Pipeline" / "Run with defaults" summary controls)
  → `test.fixme`: wizard-only flows genuinely removed, no inline equivalent.
- **TS-CHAT ×2 → reconciled.** Gate/clarify moved out of the lane (now a plain
  phase-hint composer) into the Steps spine → open Steps + seed a running agent so
  the spine leaves its empty "Pipeline trace" state; same testids/channels.
- **TS-I ×2 → reconciled via the fixture.** TS-I-01/02/03 + TS-I-09 count running
  agents through the new `stepsLiveBadge()` (running-row pulse).
- **TS-J-03 ×1 → reconciled.** "Live pill in the spine" → assert the running-row
  highlight (pill relocated to the L2 detail header).
- **TS-Q-02 / TS-X-08(failed) ×2 → reconciled.** DegradedRunAffordance RETIRED on
  the run screen → assert the new failed chrome: retired affordance absent,
  Audit auto-selected, Preview tab dropped, RunChatLane "What went wrong" card.
- **TS-R ×2 → reconciled.** TS-R-02 via the new `stepsLiveBadge()`; TS-R-03 opens
  the Preview tab for the neutral cancel empty-state (cancel leaves the panel on
  the auto-tabbed Steps).

**Also caught (not in the original 33 list, Phase-42 auto-tab staleness the
snapshot missed):**
- **TS-O-01** — deterministic fail: a building run auto-tabs to Steps, so the
  "Building your deliverable…" Preview chrome needs the Preview tab opened.
- **TS-J-04 (complete & failed)** — load-flaky race: completion auto-tabs Steps→
  Preview (failed→Audit), unmounting the Steps status line; re-open Steps after
  the terminal event before asserting "Run complete"/"Run failed".

## 3. Genuine src regressions found + fixed

**None.** Every red was spec staleness against intended Phase-42 behavior
(inline gate/clarify, spine "Live"-pill relocation, retired affordance, state-keyed
auto-tab). No `frontend/src` change was required. No backend/golden/manifest/
`useWorkflow`/`useRunStream`/transport files were touched.

## 4. Final `--project=mocked` numbers

**132 passed · 0 failed · 42 skipped** (stable ×2). Of the 42 skipped: 8
pre-existing `test.fixme` (baseline), 5 Phase-42 `test.fixme` (TS-N-06 + TS-M-04/
05a/05b/05c), and the pre-existing skipped/fixme set already in the suite.

## 5. Commits (feat/ui-2, no push)

| Hash | One-liner |
|------|-----------|
| cf2f971b | re-anchor stepsLiveBadge to the running-row pulse |
| 5abec1ca | reconcile TS-N/TS-M to the inline Steps gate & clarify |
| 6f91a2f8 | reconcile TS-CHAT-03/04 to the Steps gate/clarify surface |
| 23969905 | reconcile Steps auto-tab + retired-affordance run-screen specs |
| 18b8791d | test.fixme 8 pre-existing reds unrelated to Phase 42 |
