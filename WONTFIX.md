# WONTFIX
<!-- STATE -->
| Bug | Ledger status | Updated | Evidence |
|---|---|---|---|
| QA-PS-006 | CLOSED | 2026-09-17 | n/a |
| QA-PS-009 | CLOSED | 2026-09-22 | n/a |
| QA-PS-007 | CLOSED | 2026-09-23 | n/a |
| QA-PS-021 | CLOSED | 2026-09-23 | n/a |
| QA-KB-032 | ESCALATED | 2026-10-01 | missing |
| QA-PS-026 | PARKED | 2026-09-17 | n/a |
| QA-KB-047 | PARKED | 2026-10-02 | n/a |
| QA-KB-055 | CLOSED | 2026-10-09 | n/a |
| QA-KB-112 | ANALYZED | 2026-10-12 | n/a |
| QA-KB-121 | CLOSED | 2026-10-12 | n/a |
| QA-KB-114 | ESCALATED | 2026-10-09 | ok |
| QA-KB-117 | CLOSED | 2026-10-12 | n/a |
Last synced: 2026-10-12T08:20:13Z
<!-- /STATE -->


Bugs from `BUGS.md` whose behaviour looks intentional. The line never decides these — a human
rules on each one: **fix it** (set the row back to `Open` / `CONFIRMED` with the decision noted
here) or **won't fix** (set the row to `PARKED`). One section per bug, heading = the bug id.

Current ledger status is the truth; a section here only says a ruling is wanted.


---

## QA-PS-006
> **Now CLOSED** (2026-09-17) — kept for the trace.

**Candidate:** QA-PS-006 — "Review required" messages in concierge chat show no agent name


- **Symptom (as filed):** every review-gate prompt in the concierge chat lane reads the
  literal string "Review required" with no agent/step name, so multiple gates in one run
  are word-for-word identical. Reproduced 3/3 (cold-start, fresh `ex_A4_human_gate` runs
  `3fcd25a9-8725-4b5d-b181-1a4d2e9fcba0`, `81bc416e-c137-4d49-82ff-f02f9f30cead`,
  `0ab2ba21-eb1b-42ee-bab2-e5b137ca4f8d`) — the chat card's title is a hardcoded literal,
  never populated from `message.content` or any agent field, so it is deterministic, not
  flaky.
- **Why it looks intentional, not a bug:** `frontend/src/components/chat/ResultCard.tsx`
  documents this as the "SC-001 invariant" in its own header comment: the card selects
  its label + tone purely from the generic `cardKind` (`clarify|gate|pipeline|deliverable|
  spec_revision`) and explicitly "NEVER a workflow/agent name" — an unrecognised kind
  degrades to an inert generic card rather than picking a name-driven renderer. The gate
  branch (lines 133-144) has an inline comment citing `FIX-178` as the change that
  deliberately hardcoded plain "Review required" / "Review approved — build continues"
  text, removing a second per-agent card that "caused a duplicate 'Approved' entry."
  Backend `chat_narrator.py::_classify` (`_GATE_EVENTS` branch) independently confirms
  this: it returns the hardcoded string `"Paused — needs approval"` for every
  `review_gate_ready` event regardless of `data.get("agent_id")`, citing the same
  SC-001/INV-1 generic-event-vocabulary rule.
- **Contrast with the Steps panel:** `FIX-123` (`.knowledge/cards/20260727-1259-FIX-123.md`)
  already fixed the *Steps panel's* `GateAwaitingCard` to show the human-readable agent
  name instead of a raw `run_id:agent_id` key — so the app is capable of, and does,
  surface the agent name elsewhere. The concierge chat lane omitting it is the one place
  that's architecturally locked to stay generic, not an oversight.
- **Proposed disposition:** if product wants the agent/step name in the chat-lane gate
  message too, that's a deliberate SC-001 exception to carve out (touching `ResultCard.tsx`
  and `chat_narrator.py::_classify`'s `_GATE_EVENTS` branch), not a regression fix — a
  human should decide whether to relax the invariant. Related: QA-PS-004 (same root
  cause, on the "Review approved" confirmation side) is Open in the register and covers
  the same design decision.
- **Evidence:** `evidence/runs-run-detail/_scratch/qa-ps-006-attempt1.png`,
  `evidence/runs-run-detail/_scratch/qa-ps-006-attempt3.png`.
- **Register entry:** QA-PS-006 row in `LEDGER.md` — a later validation CONFIRMED it (ISS-653), so the line is fixing it; rule here only if the behaviour is intentional.

---

## QA-PS-009
> **Now CLOSED** (2026-09-22) — kept for the trace.

**Candidate:** QA-PS-009 — Analytics Model Details card shows a "Thinking" row for Sonnet 5


- **Reproduced 3/3** from cold start (fresh login each cycle): `/analytics` default range,
  `/analytics` revisit, and `/analytics?range=7d` deep link. Every cycle: expanding the
  Sonnet 5 card in the Model Details panel shows `Tier / Input rate / Output rate /
  Cache read rate / Cache write rate / Context window / Thinking: Adaptive (effort: max)`.
- **Why it looks intentional, not a bug:** `backend/app/api/capabilities.py` computes
  `thinking_supported=any(frag in m.id for frag in _THINKING_FRAGMENTS)` where
  `_THINKING_FRAGMENTS = ("sonnet-5", "opus-5", "fable-5", "mythos-5", "opus-4")`. The
  model catalog entry the UI shows is `us.anthropic.claude-sonnet-5` /
  `eu.anthropic.claude-sonnet-5` (`backend/agents/capabilities/model_catalog.py`), both
  of which contain the `sonnet-5` fragment, so `thinking_supported=True` — the same flag
  the Model Details panel renders the Thinking row from.
  This mirrors `_ADAPTIVE_THINKING_MODEL_FRAGMENTS` in `backend/app/agents/model_factory.py`
  (identical tuple, `sonnet-5` included), which is the flag that actually turns on
  `effort="max"` adaptive thinking for real runs on this model. The two files are
  deliberately kept in sync (comment: "Mirrors the _ADAPTIVE_THINKING_MODEL_FRAGMENTS
  tuple in model_factory.py"). `.knowledge/cards/20260907-1239-FIX-491.md` — the card
  that built this exact panel — states as a locked constraint that model metadata (which
  includes `thinking_supported`) must come from the live `/api/capabilities` catalog,
  and documents `thinking_supported: True for sonnet-5/opus-4/opus-5 fragments` as the
  designed value, not a bug.
  So within this app's own (fictional) model catalog, "Claude Sonnet 5" is modeled as a
  thinking-capable model and the panel is faithfully reporting what the backend actually
  does for that model id at runtime — the reporter's expectation is based on the
  real-world Claude Sonnet 5, which this app's catalog does not claim to mirror.
- **Proposed disposition:** if product wants Sonnet 5 in this catalog to NOT be a
  thinking-capable model, that's a change to `_THINKING_FRAGMENTS` /
  `_ADAPTIVE_THINKING_MODEL_FRAGMENTS` (removing `"sonnet-5"` from both, in lockstep) —
  a product/model-catalog decision, not a display-layer defect fix. A human should rule
  on whether "Sonnet 5" in this catalog is meant to support adaptive thinking at all.
- **Evidence:** `evidence/analytics/_scratch/qa-ps-009-cycle1-sonnet5-thinking.png`,
  `evidence/analytics/_scratch/qa-ps-009-cycle2-sonnet5-thinking.png`,
  `evidence/analytics/_scratch/qa-ps-009-cycle3-sonnet5-thinking.png`.
- **Register entry:** QA-PS-009 row in `LEDGER.md` (Status `ESCALATED` by the orchestrator 2026-09-17 to stop a re-validation loop).
- **Re-validated 2026-09-17 (lane2):** independently reproduced 3/3 from cold start
  (`/analytics` default, `/dashboard`→`/analytics?range=7d` deep link, `/analytics` reload) —
  Sonnet 5's Model Details card still shows `Thinking: Adaptive (effort: max)`. Confirmed the
  code citations above are unchanged (`_THINKING_FRAGMENTS` in `capabilities.py:169` and
  `_ADAPTIVE_THINKING_MODEL_FRAGMENTS` in `model_factory.py:123` both still include
  `"sonnet-5"`). No new information; this stays a human product decision, not a re-open. Status
  in `LEDGER.md` left as `ESCALATED` — not touched, per the WONTFIX rule ("leave Status alone").
- **Analyzed 2026-09-17 (3-analyzer):** independently re-read every file:line above and confirms
  the same conclusion — see [ISS-667](.knowledge/cards/20260917-1320-ISS-667.md) for the full
  trace and `ESCALATIONS.md#qa-ps-009` for the decision + options this now hands to a human.
  Blast-radius grep of the same fragment tuples also found a genuinely fixable sibling defect
  that needs no product decision: [ISS-668](.knowledge/cards/20260917-1325-ISS-668.md) — the two
  tuples have drifted (`capabilities.py:169` carries an extra `"opus-4"` that
  `model_factory.py:123` does not), so Opus 4.5/4.6 show this same "Adaptive (effort: max)" row
  while their real thinking type is "enabled". LEDGER.md Status left as `ESCALATED`.

### Evidence trace (2026-09-17)

**1. Row source.** `frontend/src/components/analytics/AnalyticsPage.tsx:829` — `"Adaptive (effort: max)"`
is a **hardcoded literal string** in JSX (not computed), gated only by `entry.thinking_supported`
(line 826). That flag comes from `GET /api/capabilities` (`frontend/src/lib/api.ts:1676` →
`backend/app/api/capabilities.py:130` `list_capabilities`), computed at line 189:
`thinking_supported=any(frag in m.id for frag in _THINKING_FRAGMENTS)` (line 169). **Source type:
CODE CONSTANT** — no DB row involved in producing this row at all. The string "effort: max" does
not come from any config, catalog, or params object; it is typed directly into the component.

**2. Docs support (claude-api skill, Sonnet 5 row of its Thinking & Effort table):**
```
Sonnet 5 | {type:"adaptive"} is the only on-mode; {type:"disabled"} accepted | Runs adaptive
| Removed - 400 | Removed - 400 | low/medium/high/xhigh/max
```
`max` is a real effort value the API accepts for Sonnet 5 — docs support: **YES**, the *value*
exists. But default effort when omitted is `high`, not `max` ("default `high`, equivalent to
omitting it").

**3. Runtime evidence — is `effort` actually sent?** `grep -rn "effort" backend --include=*.py`
(excluding tests) returns **zero matches**. `backend/app/agents/model_factory.py:120-141`
(Anthropic) and `:186-200` (Bedrock) build the `thinking` field as `{"type": "adaptive"}` for any
model id containing `sonnet-5`/`opus-5`/`fable-5`/`mythos-5` — **no `effort` key is ever
constructed anywhere in this codebase.** Effort is never overridden, so every Sonnet 5 call
runs at the Anthropic API's default (`high`), not `max`.

Real DB usage (`workflow_runs.agent_outputs`, Postgres `flowin_local_pdf`, live backend's
`DATABASE_URL`), last 30 days, `model_id = 'eu.anthropic.claude-sonnet-5'` (Bedrock geo-prefixed
id — matches the "us./eu.anthropic.claude-sonnet-5" catalog entries in `model_catalog.py`):
```
7 runs, 8 agent-level sonnet-5 calls (mostly prototype-validate), e.g.:
  run 0333366f... agent=prototype-validate in=5,619,694 out=23,089 cache_r=5,532,290 cache_w=87,232
  run 4bb4bbcb... agent=prototype-validate in=2,308,371 out=15,147 cache_r=2,094,933 cache_w=213,366
  run 80b00eba... agent=prototype-validate in=5,467,017 out=29,025 cache_r=5,279,207 cache_w=187,668
sum(total_tokens) across the 8 calls = 36,128,309  ≈ 36.1M shown on the card (confirms real usage)
```
`thinking_text` on every one of these agent rows is empty (`len 0`) — consistent with Sonnet 5's
documented default `display: "omitted"` (thinking still runs, just not surfaced), so this does
NOT prove thinking was off, but it also gives no positive confirmation thinking ran, and there is
no stored `effort`/reasoning-token column anywhere in `workflow_runs` or `agent_outputs` to check
against. No backend log capture of the literal request body was available (read-only pass, no log
grep requested). **Runtime evidence found: YES for thinking type "adaptive" (code always sends
it for this model id, confirmed real Sonnet 5 usage in DB), NO for effort "max" specifically (no
`effort` param exists in the codebase at all — it is never sent, so the API runs at its own
default `high`).**

**Verdict: SUPPORTED-NOT-USED.** "Adaptive" thinking is real and confirmed used (Anthropic API
supports it for Sonnet 5, and the app's `model_factory.py` genuinely sends `{"type":"adaptive"}`
for every Sonnet 5 call, backed by real DB usage rows). "effort: max" is not — the app never sets
an `effort` parameter for this or any model, so real calls run at the API's default (`high`), not
`max`. The row overstates precision it does not configure; it is a hardcoded UI string, not a
reflection of any request parameter.

---

## QA-PS-007
> **Now CLOSED** (2026-09-23) — kept for the trace.

**Candidate:** [QA-PS-007](BUGS.md#qa-ps-007) — "PPT workflow final output file always named
presentation.html regardless of run topic." Cards: [ISS-651](.knowledge/cards/20260917-1200-ISS-651.md)
(root), [ISS-659](.knowledge/cards/20260917-1305-ISS-659.md) (prototype sibling),
[ISS-660](.knowledge/cards/20260917-1305-ISS-660.md) (base-version sibling),
[ISS-661](.knowledge/cards/20260917-1305-ISS-661.md) (header Download sibling — the one
[ESCALATIONS.md#qa-ps-007](ESCALATIONS.md#qa-ps-007) asked a decision on).

**Decision (user, 2026-09-22, recorded in `FIX-STATE.md`):** do not rename the deliverable.
Changing the `write_file` target in the ppt/prototype agent prompts risks breaking other
workflows that depend on that literal on-disk name. A generic on-disk name
(`presentation.html`) is acceptable **provided the bytes served to the user are correct** —
i.e. Download always serves the content that matches the version on screen, never stale or
cross-run content.

**Rationale:** ISS-651/659/660 are all naming-display defects (Files tab row label / base-
version label collapsing to the generic on-disk name instead of a topic-derived one) —
exactly the behaviour the decision accepts. ISS-661 is the header Download button's
independent duplicate of the same "raw on-disk name wins" mechanism; the decision resolves its
open question (options a/b in `ESCALATIONS.md#qa-ps-007`) in favour of (a): the on-disk/
declared name is the name of record, so the header button already does the right thing by
serving that name literally — no frontend fallback needed, and the pinned assertion at
`frontend/src/components/preview/PreviewPanel.test.tsx:269` stays correct as-is.

**The one thing not yet checked — byte correctness — was verified live:**

- Run `8754cc43-f0b6-4005-b2d1-34db2eb41ad1` ("Subsea Fibre Splice Operations", `ppt_revision`,
  9 revisions, `v8` HEAD), `qa-admin@flowinqa.com`, `:3000`.
- **v8 (latest):** header "Download the deliverable" button → downloaded `presentation.html`,
  sha256 `90d0a43f2ee9f35b1aaed19cec0df8ffc8ccfad6d40c51233b0200e2c49028d9`. Identical hash to
  (a) the preview iframe's `srcdoc` and (b) the on-disk sandbox file fetched via
  `GET /api/runs/{id}/sandbox/file?path=presentation.html`. Content shows `<title>Subsea Fibre
  Splice Operations</title>` and heading `SPLICE REVISION EIGHT`, matching the run's topic and
  its last chat instruction — not another run's deck, not a stale version.
- **v2 (pinned older version, via the version dropdown):** header Download → downloaded
  `presentation.html`, sha256 `4da73881641832a86cee5033de50ee2b602f5c9a3c31468ce6991601ca728f68` —
  different from the v8 hash, and identical to that version's own preview `srcdoc`. Heading
  reads `SPLICE REVISION TWO`, matching v2's own chat instruction. The version selector read
  "Viewing v2 (read-only)" throughout — no stuck/indefinite loading (the concern in
  [QA-PS-054](LEDGER.md)).
- No console errors on either page load (`browser_console_messages`, 0 errors / expected
  warnings only).
- Screenshots: `evidence/qa-ps-007/39-v8-header-download-correct-bytes.png`,
  `evidence/qa-ps-007/40-v2-pinned-header-download-correct-bytes.png`. Raw bytes and hashes:
  `evidence/qa-ps-007/downloaded-header-v8-presentation.html`,
  `evidence/qa-ps-007/downloaded-header-v2-presentation.html`,
  `evidence/qa-ps-007/workspace-file-presentation.html`,
  `evidence/qa-ps-007/preview-iframe-decoded.html`, `evidence/qa-ps-007/v2-preview-decoded.html`.

**Result:** naming stays generic by decision (won't fix), and the only open item — does
Download serve the correct bytes — is now proven yes, on both the latest and a pinned older
version. QA-PS-007 closes.

---

## QA-PS-021
> **Now CLOSED** (2026-09-23) — kept for the trace.

### ISS-734 won't fix (user decision 1a, recorded 2026-09-23 01:34)

This ruling covers one sibling card. The bug itself is **FIXED** by
[FIX-639](.knowledge/cards/20260923-0148-FIX-639.md) and its row stays on the line for
verification.

**Candidate:** [ISS-734](.knowledge/cards/20260922-1354-ISS-734.md).
`_build_validation_target` has no per-step "does this step's declared upstream artifact
exist" check. It affects the ten native pipelines that declare `gates: [validation]`.
The card was inferred and never reproduced.

**Decision:** won't fix. This is option (a) of decision 1 on
[ESCALATIONS.md#qa-ps-021](ESCALATIONS.md#qa-ps-021): "Nothing — retire ISS-734". The
card is set to `status: wontfix`.

**Rationale:** the run-level degraded signals already cover it. There are three of
them, all in the shared completion gate:

- [FIX-612](.knowledge/cards/20260922-1838-FIX-612.md): narration
- [FIX-615](.knowledge/cards/20260922-1854-FIX-615.md): silent section drop
- [FIX-634](.knowledge/cards/20260922-2235-FIX-634.md): a declared upstream that
  produced nothing

Each one degrades the run's `status`, `degraded_reason` and `published_status`. The
gate keeps validating the run-level deliverable. The alternative the original test
asked for, `_build_validation_target` returning `None`, is not viable.

**Evidence:**
- `backend/agents/capabilities/gates/validation.py:92` has the only production call,
  `target = _build_validation_target(`. Line `:100` is
  `issues = await validator.validate(target)`. A `None` target would reach every
  declared validator.
- `backend/agents/capabilities/deliverables/_coverage.py:113-121` is FIX-634's
  zero-coverage branch: `if not source.strip():` and then
  `if len(text) > _MIN_UNSOURCED_CHARS:` (2000, `:65`). It returns a reason, and that
  degrades the run.
- A test pins the decision:
  `backend/tests/agents/test_qa_ps_021_downstream_no_upstream_artifacts.py::test_missing_declared_upstream_is_caught_at_run_level_not_by_the_validation_gate`.
  It asserts that the gate keeps a real run-level target and that the zero-coverage
  signal fires.
  - Observed 2026-09-23 with
    `cd backend && python3.11 -m pytest tests/agents/test_qa_ps_021_downstream_no_upstream_artifacts.py -q -p no:randomly`:
    `[XPASS(strict)] ISS-734 unfixed`, with no code change.

**Accepted consequence, from the decision's own option text:** a validator can still
pass a step whose real input never arrived. The run carries the signal, not the gate.
For this case the run is flagged only when the compiling step declares `consumes`,
which is FIX-634's scope. The base `custom` manifest declares no `consumes`.

## QA-KB-032
> **Evidence missing** — claims below are unproven.

## QA-PS-026

**Candidate:** QA-PS-026 — Custom workflow validator runs on Sonnet 5 instead of Haiku 4.5

**Status:** PARKED — intentional model declaration.

**Title:** Custom workflow validator runs on Sonnet 5 instead of Haiku 4.5 — intentional model declaration, not a bug

**Rationale:** The custom workflow validator was declared to use Sonnet 5 as the reasoning model, not as a bug. This is an intentional product design decision.

## QA-KB-047
> **Section missing** — the worker did not write its trace.

## QA-KB-055
> **Now CLOSED** (2026-10-09) — kept for the trace.

## QA-KB-112
> **Now ANALYZED** (2026-10-12) — kept for the trace.

**Title:** Admin sees the MFA enrollment wall on /settings/security and gets a new TOTP secret on every visit · **Route:** /settings/security · **Stage:** validate · **Date:** 2026-10-09

### Why it looks intentional
Reproduced 3/3 from cold start (admin@velocity.ai): /settings/security renders the "Two-factor authentication" enrollment page instead of the Account Settings Security tab (no `tab-security` element), and each load shows a different setup key. This is what the code is written to do, and it was added deliberately by commit b2a621f84 ("Fix/cognito login (#8)").
- `frontend/src/app/settings/security/page.tsx:3-11` docstring: "This page exists because Cognito provides no enrolment UI without the hosted UI, and because `require_admin` refuses an admin who holds no second factor. It is the destination the backend names in that 403's `enroll_path`..."
- `page.tsx` `begin()` calls `associateTotp(token)` from a mount effect, so every visit mints a new secret; the page copy says "This key is shown once and is not stored. If you leave this page before finishing, start again."
- Nothing is enrolled until `verifyTotp` succeeds, so the repeated secrets are unverified associations, not account changes.
- The route is a bare page (`frontend/src/app/settings/` contains only `security/`), so it shadows the Security tab route listed in velocity.json (`/settings/security`, `tab-security`). `SecuritySection.tsx` is still used by `AccountSettings.tsx`.

### Evidence
- evidence/qa-kb-112/01-validate-attempt1-mfa-enrollment-wall-secret-XNAG.png (key XNAGDTGH...)
- evidence/qa-kb-112/02-validate-attempt2-mfa-enrollment-wall-new-secret.png (key 2QU32AL4...)
- evidence/qa-kb-112/03-validate-attempt3-mfa-enrollment-wall-third-secret.png (key AH2DMHYL...)
- Related open card: ISS-1018 (e2e specs for this tab broken by the same commit).

### Decision needed
Should /settings/security remain a pure TOTP enrollment page that always associates a new secret, or should it show the Account Settings Security tab and only enrol when the admin has no second factor?

### Options
- Keep as is: update velocity.json and the 09_settings e2e suite to the new behaviour (8 e2e failures become test fixes).
- Show the Security tab when MFA is already enabled, enrol only when not: changes the page and avoids minting a secret on each visit.
- Move the enrollment wall to a different route (e.g. /settings/security/enroll) and restore the tab at /settings/security.

### What happens after the decision
Keep: bug closed as WONTFIX, tests and velocity.json updated. Otherwise: re-enter analysis with the chosen behaviour.

## QA-KB-121
> **Now CLOSED** (2026-10-12) — kept for the trace.

**Title:** Launch preflight passes a Bedrock key that Bedrock rejects · **Route:** POST /api/runs · **Stage:** validate · **Date:** 2026-10-09

### Why it looks intentional
`preflight_check_provider` is documented as a no-network, expiry-only check. A token that decodes as unexpired but is revoked or invalid server-side can only be detected by a live Bedrock call, which the docstring deliberately declines to pay for on every launch. The reported behaviour (accepted at launch, then fails cleanly at the first model call) is the documented trade-off. No browser repro was run: the reporter's evidence is a direct converse call outside the app, and a live call with the shared credential is not something this phase should make.

### Evidence
- backend/app/agents/model_factory.py:119-120 `def preflight_check_provider() -> "tuple[bool, str | None]": """No-network check that the provider ``build_model()`` would select is usable right now.`
- backend/app/agents/model_factory.py:126 `Only the Bedrock bearer-token path has a check this cheap: its expiry is embedded in the token itself`; the same docstring says anything beyond expiry "would mean a live model call on every launch".
- Related: ISS-1133, ISS-1135 (other preflight gaps, expiry-based).

### Decision needed
Is expiry-only preflight acceptable, with a revoked-but-unexpired key failing cleanly at first model call, or should launch do a live cheap Bedrock probe?

### Options
- Keep as is: close WONTFIX, optionally improve the failure message for AccessDenied "API Key invalid".
- Add a cached live probe (for example one converse call per N minutes) to the preflight: costs a network call and tokens, needs a decision on the cache window.

### What happens after the decision
Keep: closed WONTFIX. Probe: re-enter analysis with the chosen design.

## QA-KB-114

**Title:** Composer shows the blank "Custom Agent" template while authoring an override · **Route:** /workflows/{id}/canvas · **Stage:** validate · **Date:** 2026-10-09

### Why it looks intentional
Reproduced 3/3 cold on :3000 (the Add agent panel lists "Custom Agent" under the All and Custom categories of /workflows/ppt/canvas; the default PPT category hides it). But the composer canvas offering the blank template is a recorded, locked design decision (FIX-306): the guard was applied only to the LaunchWizard, and the composer canvas was deliberately left out because it launches via USER_WORKFLOW_MANIFEST. The e2e scenario S-04-18 asserts the opposite for the composer's override editor, so the test and the card contradict each other.

### Evidence
- Screenshots: evidence/qa-kb-114/03-validate-attempt1-custom-category-lists-custom-agent.png, 05-validate-attempt2-custom-category-lists-custom-agent.png, 06-validate-attempt3-all-category-lists-custom-agent.png (default-category contrast: 04-validate-attempt2-add-agent-panel-open.png, 02-validate-attempt1-canvas-add-disabled.png)
- .knowledge/cards/20260825-2115-FIX-306.md locked_constraints: "The blank template stays available on the composer canvas, which launches via USER_WORKFLOW_MANIFEST and has no flat allow-list."
- Same card, Decision and fix: "`AgentLibrary` gained `allowCustomAgentTemplate`, default `true`, passed `false` from `LaunchWizard`. The composer canvas keeps the template — a user-defined step is the point there".
- frontend/src/components/workflow/AgentLibrary.tsx:37-49 (`allowCustomAgentTemplate?` default true; doc names only LaunchWizard); frontend/src/components/workflow/LaunchWizard.tsx:1559 `allowCustomAgentTemplate={false}`; frontend/src/components/workflow/composer/ComposerPage.tsx:1713 `<AgentLibrary` passes no such prop.
- tests/integration/e2e/suites/04_composer_canvas/test_composer_canvas.py:444-461 asserts `expect(page.get_by_text("Custom Agent", exact=True)).to_have_count(0)` on the composer override editor, and its docstring itself notes the template is "not offered on /workflows/new either".
- Related: ISS-182 (resolved), ISS-687 (resolved).

### Decision needed
Should the composer canvas withhold the blank Custom Agent template when it is editing/copying a built-in (S-04-18), or is the FIX-306 rule (offered on the composer canvas) correct and the e2e scenario wrong?

### Options
- Keep FIX-306 as is: close WONTFIX and correct e2e S-04-18 (it asserts something the card says is not the design).
- Withhold the template in the composer when the base is a built-in (pass allowCustomAgentTemplate=false from ComposerPage in canvas/override mode): reverses a locked constraint, and "Save as copy" of a built-in with a custom step stops being possible.

### What happens after the decision
Keep: closed WONTFIX plus a test-only fix of S-04-18. Withhold: re-enter analysis with ComposerPage.tsx as the target.

## QA-KB-117
> **Now CLOSED** (2026-10-12) — kept for the trace.

**Title:** Deliverable access hides "Branch on a decision" · **Route:** /settings/usage (deliverable access) · **Stage:** validate · **Date:** 2026-10-09

### Why escalated
The omission reproduces 3/3 from cold, but it looks intentional by construction and it is one face of an already-open product decision, [ISS-187](.knowledge/cards/20260826-1547-ISS-187.md) (status partially_resolved): the seven ex_A* engine-example fixtures are user-launchable and entitled to enterprise, so the home catalog offers them, while the Deliverable access grid is a fixed list of 8 base deliverable types that never includes them. Which of the two surfaces is "right" is the ISS-187 / D-04 decision, not a defect with one correct answer. The e2e scenario S-17-08 is tagged `@defect` and pins today's behaviour as "Deliverable Access does NOT mention it".

### Evidence
- Attempt 1/2/3 (admin, enterprise tier, cold navigations): `evidence/qa-kb-117/01-validate-attempt1-settings-usage-initial.png`, `02-validate-attempt1-dashboard-catalog.png`, `03-validate-attempt2-dashboard-catalog-full.png`, `04-validate-attempt2-usage-omits-branch.png`, `05-validate-attempt3-usage-omits-branch.png`. Catalog innerText includes "Branch on a decision" (under "Engine examples"); /settings/usage DELIVERABLE ACCESS lists exactly: Product Requirements, Presentation, Interactive Prototype, App Builder, Custom Workflow, Platform Workflows, Mulesoft Migration, .NET Migration.
- `frontend/src/components/settings/AccountSettings.tsx:65-74` `PIPELINE_DISPLAY` is a fixed 8-entry map; `:85-88` `getBasePipelines` = `TIER_PIPELINES[tier]` filtered by `.filter(p => PIPELINE_DISPLAY[p])`, so any pipeline without a display entry (all ex_A*) is dropped by design.
- `frontend/src/lib/entitlements.ts:79` and `backend/app/core/entitlements.py:78` both list `"ex_A2_branch"` ("Branch on a decision") for enterprise.
- `tests/integration/DEFECTS-OBSERVED.md:95-113` D-04; `tests/integration/e2e/suites/17_theme_and_tiers/test_theme_and_tiers.py:235-256` asserts the omission as today's behaviour.

### Decision needed
Should the engine-example fixtures be customer-visible deliverables at all?

### Options
1. Fixtures are QA-only: set `user_launchable: false` and de-entitle on both sides (ISS-187 option 2); the catalog and Deliverable access then agree, this report closes.
2. Fixtures are demos: keep them launchable and add them (or an "Engine examples" row) to PIPELINE_DISPLAY; update S-17-08.
3. Keep as is: Deliverable access lists deliverable types, not individual workflows; close as intended and retire the S-17-08 defect pin.

### What happens after the decision
Option 1/2 become a small FIX under ISS-187 plus a test update; option 3 closes the row as won't-fix.
