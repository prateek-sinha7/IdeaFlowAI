---
phase: quick-260812-sgu
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - backend/app/api/run_commands.py
  - backend/tests/unit/test_rest_gate_commands.py
autonomous: true
requirements: [ISS-070]
must_haves:
  truths:
    - "An unrecognised gate action on POST /api/runs/{id}/gate is REFUSED (400/422), never resolved as an approval."
    - "A refusal writes NOTHING to the store and leaves the review gate ARMED — the user can still decide."
    - "A refusal NEVER degrades to a reject: FIX-232 makes rejection terminal, so a typo must not destroy the run."
    - "The bare POST {\"gate_key\": ...} with NO action key still defaults to approve (test_attach_replay_matrix.py:551 contract + the published OpenAPI default)."
    - "The four known actions (approve / reject / redo / update_specs) write byte-identical store records to today."
    - "The if/elif chain in resolve_gate is NOT restructured — the grep-ratchet at test_rest_gate_commands.py:362 asserting the literal 'action == \"redo\"' stays green."
    - "The action vocabulary keeps exactly ONE authority: chat_router.GATE_ACTIONS. The schema Literal is pinned to it by a set-equality test (INV-12), not by a fifth hand-written copy."
    - "Characterization goldens stay 10 passed with 0 golden files modified; lint-imports stays 4 kept / 0 broken."
  artifacts:
    - path: "backend/app/api/run_commands.py"
      provides: "GateCommand.action constrained to the four-action Literal (default retained) + all three set_review_response ingresses fail closed on an unknown discriminator"
      contains: "unknown_gate_action"
    - path: "backend/tests/unit/test_rest_gate_commands.py"
      provides: "The RED proof — case/whitespace/typo variants of a DENIAL currently approve"
      contains: "test_case_and_whitespace_variants_of_reject_never_approve"
  key_links:
    - from: "backend/app/api/run_commands.py:GateCommand.action"
      to: "backend/app/api/chat_router.py:GATE_ACTIONS"
      via: "set-equality pinned in test_gate_action_literal_matches_the_single_vocabulary_authority"
      pattern: "GATE_ACTIONS"
---

<objective>
Stop `POST /api/runs/{run_id}/gate` silently APPROVING a human-in-the-loop review gate when
the client sends an action string it does not recognise (ISS-070).
</objective>

<context>

## The defect

`run_commands.py:268` is `elif action == "reject":` — an exact, case-sensitive, unstripped
string match. Everything that is not one of the three named actions falls to
`else:  # approve (default)` at `:272`, which sets `approved=True` and resolves the gate.

Every near-miss of a DENIAL therefore approves: `Reject`, `REJECT`, ` reject`, `reject\n`,
`rejct`, `no`, `deny`, `Redo`, `redo `, `update-specs`.

Two aggravators:

1. **The record is laundered.** The `else` does not pass `action=`, so `store.set_review_response`'s
   own default (`store.py:123`) writes `action="approve"`. A garbage action leaves no forensic
   trace, while `resolve_gate:278` echoes the garbage string back in the HTTP response — the
   response and the durable audit row disagree.
2. On the **declared**-gate path (`agents/capabilities/gates/human.py:104-141`) an unknown action
   emits none of `_gate_rejected` / `_gate_redo` / `_gate_update_specs`, so the step resolves as a
   formal `GATE_PASS` and writes an honest-looking audit row.

## Scope — one of three ingresses is defective

| Ingress | `else` | Status |
|---|---|---|
| `POST /{id}/gate` → `resolve_gate` | `run_commands.py:272` | **REAL — fix** |
| `POST /{id}/messages` → `CHANNEL_GATE` | `run_commands.py:1322` | Defended by `chat_router.py:234` (both `Dispatch(channel=CHANNEL_GATE)` sites require `turn.action in GATE_ACTIONS`) — latent hazard |
| Concierge confirm → `_dispose_concierge_proposal` | `run_commands.py:1101` | Defended by `concierge.py:350` normalisation + H1 (params are server-written, never client body) — latent hazard |

`chat_router.py` is **NOT** touched: its `:234` guard IS the ISS-119 routing contract.

## Not this fix

`GateCommand.analysis_report` has no length cap anywhere on its path
(`:115` → `:264` → `engine.py:5387` → injected at `engine.py:9096`). Different defect,
different fix — filed as ISS-127.

</context>

<tasks>

### Task 1 — the RED proof (tests first)

Add to `backend/tests/unit/test_rest_gate_commands.py` (15 passed at HEAD; the
`env` / `_seed_user` / `_seed_run` / `_arm_gate` / `_recorded` / `_post_gate` harness is
already in place, no new fixtures needed):

1. `test_unknown_gate_action_is_refused_not_approved` — `action="rejct"` → status in (400, 422),
   `_recorded(...) is None`, and `_resume_events["review:<gate_key>"].is_set() is False`.
2. `test_case_and_whitespace_variants_of_reject_never_approve` — parametrised over
   `["Reject", "REJECT", " reject", "reject\n", "rejct", "no", "deny", "Redo", "redo ", "update-specs"]`,
   same three assertions. **This is the headline RED**: ten `200 approved=True` at HEAD.
3. `test_bare_gate_post_still_defaults_to_approve` — POST `{"gate_key": ...}` with no `action`
   key → 200 + `approved is True`. GREEN before AND after; the regression pin for
   `test_attach_replay_matrix.py:551`.
4. `test_gate_action_literal_matches_the_single_vocabulary_authority` — set-equality between
   `get_args(GateCommand.model_fields["action"].annotation)` and `chat_router.GATE_ACTIONS`
   (INV-12 — one authority for what a gate action is).

Run them and record the verbatim RED output before touching the source.

### Task 2 — Layer A: constrain the domain at the schema boundary

`run_commands.py:111`

```
-    action: str = "approve"
+    action: Literal["approve", "reject", "redo", "update_specs"] = "approve"
```

`Literal` requires static values, so it cannot be spelled from the frozenset at runtime; the
set-equality test in Task 1 is what keeps `GATE_ACTIONS` the single authority.

**KEEP THE DEFAULT.** Making `action` required breaks `test_attach_replay_matrix.py:551` and
the published OpenAPI contract (`"default": "approve"`). Constrain the domain, keep the default.

### Task 3 — Layer B: make the dispatch fail closed

`run_commands.py:272-276` — change **only** the `else` clause; leave `:253` / `:257` / `:268`
byte-identical so the `test_rest_gate_commands.py:362` grep-ratchet stays green.

```
    elif action == "approve":
        approved = True if body.approved is None else bool(body.approved)
        await store.set_review_response(
            gate_key, approved=approved, action="approve",
            edited_content=body.edited_content,
        )
    else:
        raise _deny_unknown_gate_action(action)
```

`_deny_unknown_gate_action` is a new module-level helper beside `_deny_unknown_gate` /
`_deny_update_specs_not_offered` (the file's existing idiom): logs the refused action and
raises **400 `unknown_gate_action`, `recoverable: true`**.

It **must REFUSE, never degrade to a reject.** FIX-232 makes rejection terminal; turning a typo
into a rejection would destroy the run. Refusing the request and leaving the gate armed is the
only degrade that preserves every legitimate option — the same choice the engine already made
for an ineligible `update_specs` at `engine.py:5830-5838`.

Passing `action="approve"` explicitly on the approve branch removes the reliance on the store's
own `action="approve"` default (the laundering channel) while writing a byte-identical record.

### Task 4 — Layer C: same fail-closed shape at the two latent sites

`run_commands.py:1101` (Concierge confirm) and `:1322` (`/messages` CHANNEL_GATE): convert
`else:  # approve (default)` to `elif ... == "approve":` + `raise _deny_unknown_gate_action(...)`.

Verified safe: both `Dispatch(channel=CHANNEL_GATE)` construction sites (`chat_router.py:244`,
`:255`) require `turn.action in GATE_ACTIONS`, and the site-3 gate branch is reachable only with
`confirmed=True` (gate_action ∈ `_CONSEQUENTIAL_PROPOSAL_CHANNELS` is held otherwise), which is
the HTTP confirm handler at `:1412` where an `HTTPException` surfaces cleanly.

### Task 5 — mutation-prove each layer independently

- Revert Layer A only (restore `action: str`), keep B → tests 1-2 must still pass on the 400.
- Revert Layer B only (restore `else: # approve`), keep A → tests 1-2 must still pass on the 422.

### Task 6 — regression sweep

| Suite | Baseline at HEAD `e6b24ae5` |
|---|---|
| `tests/unit/test_rest_gate_commands.py` | 15 passed |
| `tests/unit/test_update_specs_ingress_fence.py` | 13 passed |
| `tests/unit/test_concierge_proposal_channels.py` | 1 failed / 18 passed (pre-existing) |
| `tests/agents/test_attach_replay_matrix.py` | 1 failed / 11 passed (pre-existing) |
| characterization goldens (5 files) | 10 passed, 0 golden files modified |
| `lint-imports` from `backend/` | 4 kept / 0 broken |
| frontend | 0 files changed |

</tasks>

<verification>
- The ten case/whitespace/typo variants are seen RED (200 + `approved=True`) before the fix and
  refused after it, with the store untouched and the gate still armed.
- The bare POST default is green before and after.
- `git diff` shows `:253` / `:257` / `:268` unchanged (grep-ratchet trap 2).
- `action` is still optional in the OpenAPI schema, now with an `enum` (trap 1).
- Every baseline above is re-measured after the change with the same pre-existing red ids.
</verification>
