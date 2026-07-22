---
slug: od-ppt-golden-divergence
status: resolved
trigger: |
  DATA_START
  test_characterization_od_ppt.py::test_od_ppt_event_snapshot fails — the od_ppt
  normalized event stream diverges from the committed golden at event index 3
  (agent_input / context_message for the first agent od-ppt-brief-analyst).
  Pre-existing INV-3 (byte/event-parity) violation, present at base commit
  16fa8338; NOT caused by quick-task 260703-d4v. The other 4 characterization
  goldens (prototype, od_prototype, prototype_revision, app_builder) pass
  byte/event-identical.
  DATA_END
created: 2026-07-03
updated: 2026-07-03
tdd_mode: false
goal: find_and_fix
classification: B-explicit (tighten gate on template_example inject; NOT regenerate-only, NOT design_system-coupled)
---

# Debug Session: od_ppt characterization golden divergence

## Symptoms

- **Expected:** `python3.11 -m pytest tests/agents/test_characterization_od_ppt.py -q`
  passes — the normalized od_ppt event stream is byte/event-identical to the
  committed golden (INV-3).
- **Actual:** FAILS — `test_od_ppt_event_snapshot` raises
  `AssertionError: od_ppt normalized event stream diverged from the committed golden`.
  The divergence is at **event index 3**: an `agent_input` / `context_message`
  for the FIRST agent **`od-ppt-brief-analyst`**.
- **Error message:** "od_ppt normalized event stream diverged from the committed golden".
- **Timeline:** pre-existing. Fails IDENTICALLY at base `16fa8338` and with the
  d4v change reverted (revert-and-reproduce). Introduced by an earlier commit on
  branch `new-workflow-engine`. Candidate commits touching brief/context handling:
  `2a274524 fix(engine): raise planner+clarify brief cap to BRIEF_MAX_CHARS (64k)`,
  `f351d446 feat(config): raise brief cap to 450k`.
- **Reproduction:** `cd backend && python3.11 -m pytest tests/agents/test_characterization_od_ppt.py -q`
  (python3.11, NO venv). Do NOT run the whole backend suite (hangs offline).

## Scope facts (established, do not re-derive)

- ONLY od_ppt is broken. The other 4 goldens pass byte/event-identical, so the
  cause is **od_ppt-specific first-agent context composition**, NOT a shared
  engine path (else od_prototype would also break).
- d4v only touched `RunRequest.brief` (API request model on `POST /api/prototype/run`);
  od_ppt drives the engine via `ndjson_adapter` and never constructs `RunRequest`.

## Current Focus

- **status:** RESOLVED. Classification approved (Option B / B-explicit) and fix applied +
  verified + committed.
- **root cause:** Commit `b5f5885e` (KAN-63, Jun 15 2026) intentionally extended the
  `opendesign` context-provider example.html gate from `is_builder` to
  `(is_builder or "workspace" in spec_tools)`. That `"workspace" in spec_tools` proxy was
  too broad — it swept in the planner-shaped od-ppt-brief-analyst (order-1 strategy agent
  that happens to declare `tools: [workspace]`), leaking example.html to a planner and
  violating the Phase-7 "planners must not see a full working HTML doc" rule. The od_ppt
  golden (last regenerated Jun 9, commit `0b7ada2b`) was never regenerated → INV-3 divergence.
- **fix (B-explicit):** Re-key the example gate on a DECLARED inject instead of the tool set:
  `(is_builder or "workspace" in spec_tools)` → `(is_builder or "template_example" in injects)`,
  and add `template_example` to od-ppt-composer's AGENT.md `injects` (composer only). The
  composer now opts in explicitly; the brief-analyst (which declares only `injects: [template]`)
  stays example-free. Golden regenerated so ONLY the composer (idx 7) gains the block.
- **next_action:** DONE. No further action.

## Constraints

- Backend-only. Branch `new-workflow-engine`, never `main`. INV-3, additive
  migrations (Q3), deepagents runtime mandate (INV-13). The other 4 goldens MUST
  stay passing after any fix (re-run all 5). Consult
  `.planning/IMPLEMENTATION-REGISTER.md` + `backend/CLAUDE.md` for locked decisions.

## Evidence

- timestamp: 2026-07-03
  checked: Reproduced `python3.11 -m pytest tests/agents/test_characterization_od_ppt.py -q`.
  found: `test_od_ppt_event_snapshot` FAILS at index 3 (`agent_input` /
    `context_message` for od-ppt-brief-analyst). `test_od_ppt_deliverable_byte_snapshot`
    PASSES (deliverable bytes unchanged) — only the event/context stream diverges.
  implication: Divergence is confined to composed `context_message`, not the deck output.

- timestamp: 2026-07-03
  checked: Dumped + diffed normalized `context_message` (golden vs live) for ALL 19 events.
  found: EXACTLY 2 divergent events, both purely `context_message`, event count identical
    (19==19, nothing dropped/reordered): idx 3 (od-ppt-brief-analyst) and idx 7
    (od-ppt-composer). idx 3: golden is a strict PREFIX of live; appended remainder is
    EXACTLY one `=== TEMPLATE EXAMPLE (example.html): web-prototype === ... === END
    TEMPLATE EXAMPLE ===` block. idx 7: same block inserted mid-message (+84 lines, -0);
    stripping the block makes live == golden byte-identical.
  implication: The ONLY change is the ADDITIVE injection of the web-prototype template's
    example.html into the two od_ppt agents that declare `tools: [workspace]`. No
    collateral byte changes.

- timestamp: 2026-07-03
  checked: `grep` for the block producer → `agents/capabilities/context_providers/opendesign.py`
    lines 111-133; read the example.html gate.
  found: The block is emitted when `"template" in injects` AND `not is_build_task_2_plus`
    AND example_html available AND `(is_builder or "workspace" in spec_tools)`, where
    `is_builder = spec_tools & {"prototype_emit_only","prototype"}`. od-ppt-brief-analyst
    AND od-ppt-composer both declare `injects: [template]` + `tools: [workspace]`, so the
    `"workspace" in spec_tools` clause fires for BOTH.
  implication: The gate's `"workspace"` clause is exactly what feeds example.html to these
    agents.

- timestamp: 2026-07-03
  checked: `git log -S 'workspace" in spec_tools' -- opendesign.py`; `git show b5f5885e`.
  found: Introducing commit `b5f5885e` "fix(agent): fix PPT preview ... [KAN-63]"
    (Jun 15 2026) changed the gate from `is_builder` → `(is_builder or "workspace" in
    spec_tools)`. Commit body: "opendesign provider is_builder gate excluded the workspace
    tool set so example.html was never injected into the PPT composer; extended the gate to
    include workspace." It touched opendesign.py + od-ppt-composer/validator AGENT.md +
    frontend — but NOT `tests/agents/characterization/golden/od_ppt.events.json`.
  implication: Deliberate, Jira-tracked, reviewed product behavior change; golden regen
    was missed.

- timestamp: 2026-07-03
  checked: Golden git history + ancestry.
  found: `od_ppt.events.json` last regenerated Jun 9 2026 (commit `0b7ada2b`, "regen goldens
    to oracle") — BEFORE `b5f5885e` (Jun 15). `b5f5885e` is an ancestor of HEAD.
  implication: Timeline confirms golden predates the intended gate change → classification (a).

## Eliminated

- hypothesis: The brief-cap commits `2a274524` / `f351d446` (shared `brief[:BRIEF_MAX_CHARS]`
    truncation path) caused the divergence.
  evidence: The divergent bytes are the ADDITIVE `TEMPLATE EXAMPLE (example.html)` block from
    the od_ppt-specific `opendesign` provider gate (commit b5f5885e), not any brief-cap
    truncation change. The user brief text in the message is unchanged between golden and live.
    Consistent with the scope fact that the other 4 goldens (incl. od_prototype) pass.
  timestamp: 2026-07-03

## Resolution

- root_cause: Commit `b5f5885e` (KAN-63) intentionally extended the `opendesign` provider's
  example.html gate to `(is_builder or "workspace" in spec_tools)`, injecting the
  web-prototype template's example.html into the two od_ppt agents declaring
  `tools: [workspace]` (od-ppt-brief-analyst idx 3, od-ppt-composer idx 7). The `"workspace"
  in spec_tools` clause was too broad: it fired for the planner-shaped od-ppt-brief-analyst
  (an order-1 strategy agent), leaking a full working HTML doc to a planner (violates the
  Phase-7 rule) AND the od_ppt golden (last regenerated Jun 9, 0b7ada2b) was never
  regenerated → INV-3 byte-parity divergence.
- fix: CLASSIFICATION = Option B / B-explicit (tighten the gate on a DECLARED inject, NOT
  regenerate-only; NOT design_system-coupled — that would re-leak to prototype-specify/plan).
  Exact edits:
    1. backend/agents/capabilities/context_providers/opendesign.py (~L123): example gate
       `(is_builder or "workspace" in spec_tools)` → `(is_builder or "template_example" in injects)`;
       updated the EXTENDED comment block (~L117-121) to explain the composer opts in via the
       declared `template_example` inject (consumed ONLY by this gate — factory._compose_injection
       ignores unknown inject values). `is_builder` KEPT as first disjunct (prototype oracle path).
    2. backend/agents/prompts/od-ppt-composer/AGENT.md frontmatter: `injects: [template,
       design_system]` → `[template, design_system, template_example]` (composer ONLY; body /
       tools untouched).
    3. backend/tests/agents/test_context_providers.py: appended 2 regression tests
       (`test_opendesign_example_gate_is_builder_or_template_example_inject`,
       `test_od_ppt_agents_template_example_inject_wiring`).
    4. Regenerated ONLY backend/tests/agents/characterization/golden/od_ppt.events.json via
       `SNAPSHOT_UPDATE=1 ... test_od_ppt_event_snapshot`. Delta: idx 7 (od-ppt-composer)
       gains the ~4266-byte `=== TEMPLATE EXAMPLE (example.html): web-prototype ===` block
       (no `...[truncated]`, <8k); od-ppt-brief-analyst unchanged (example-free); event count
       stays 19; deliverable golden od_ppt.html unchanged.
- verification:
    * tests/agents/test_context_providers.py → 19 passed (incl. the 2 new).
    * All 5 characterization goldens (NO SNAPSHOT_UPDATE): prototype, od_prototype,
      prototype_revision, app_builder, od_ppt → 10 passed (od_ppt now green; other 4
      byte-identical).
    * tests/agents/test_context_message_oracle.py → 10 passed.
    * /opt/homebrew/bin/lint-imports → 4 kept / 0 broken.
    * git status scope: ONLY opendesign.py, od-ppt-composer/AGENT.md, test_context_providers.py,
      od_ppt.events.json.
- files_changed:
    - backend/agents/capabilities/context_providers/opendesign.py
    - backend/agents/prompts/od-ppt-composer/AGENT.md
    - backend/tests/agents/test_context_providers.py
    - backend/tests/agents/characterization/golden/od_ppt.events.json
