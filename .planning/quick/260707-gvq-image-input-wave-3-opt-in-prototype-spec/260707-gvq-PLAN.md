---
phase: 260707-gvq
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - backend/agents/workflows/prototype/workflow.yaml
  - backend/agents/prompts/prototype-specify/AGENT.md
  - backend/tests/agents/test_prototype_image_optin.py
autonomous: true
requirements: [T3.1a, T3.1b, T3.2, T3.3]
must_haves:
  truths:
    - "The prototype manifest declares input_providers: [run_images]; a compiled prototype run threads ectx.compiled_input_providers == ['run_images']."
    - "prototype-specify declares injects: [template, design_system, images], opting the order-1 spec-writer into image content-blocks."
    - "With NO image attached (the golden harness), the 5 characterization goldens + the context_message oracle stay byte/event-identical (SNAPSHOT_UPDATE unset)."
    - "With ectx.run_images populated, _compose_input_blocks returns exactly one base64 image block for the REAL prototype-specify spec, and [] for a non-opted agent (prototype-plan)."
    - "SC-001 holds: the opt-in is DATA-ONLY (manifest + AGENT.md) — zero kernel/engine/capability edit; INV-1 grep in engine.py unchanged."
  artifacts:
    - path: "backend/agents/workflows/prototype/workflow.yaml"
      provides: "top-level input_providers: [run_images] declaration"
      contains: "input_providers"
    - path: "backend/agents/prompts/prototype-specify/AGENT.md"
      provides: "images appended to the injects frontmatter list"
      contains: "images"
    - path: "backend/tests/agents/test_prototype_image_optin.py"
      provides: "end-to-end opt-in delivery proof via the REAL compiled plan + REAL specs"
      min_lines: 40
  key_links:
    - from: "backend/agents/workflows/prototype/workflow.yaml"
      to: "ectx.compiled_input_providers"
      via: "manifest input_providers → compiler → CompiledWorkflow.input_providers → engine thread"
      pattern: "input_providers"
    - from: "backend/agents/prompts/prototype-specify/AGENT.md"
      to: "engine._compose_input_blocks gate"
      via: "loader spec.injects → 'images' in set(spec.injects) ∪ set(step.injects)"
      pattern: "images"
    - from: "agents/capabilities/input_providers/run_images.py"
      to: "multimodal image block"
      via: "provider.load(ctx.run_images) → {type:image,source_type:base64,...}"
      pattern: "source_type.*base64"
---

<objective>
Flip the `prototype` workflow's image-input capability from DORMANT (Wave 1) to ON for the
order-1, highest-value consumer — the spec-writer (`prototype-specify`) — with TWO data-only
declaration edits, then PROVE (a) the opt-in stays byte/event-identical when no image is
attached (the load-bearing golden-safety gate) and (b) it DELIVERS an image content-block when
an image IS present.

Purpose: Turn the Wave-1 backend spine (carrier → port → `run_images` capability → locally-gated
engine wiring) into a live, opted-in feature for `prototype` — proving SC-001: a workflow opts
into a registered capability by DECLARATION ALONE (manifest + AGENT.md), with zero kernel edit.

Output:
- `input_providers: [run_images]` on the prototype manifest.
- `images` appended to `prototype-specify`'s `injects`.
- A new wiring test proving the opt-in delivers (spec-writer → image block; non-opted → []).

NEGATIVE SPACE — this is DATA-ONLY. NO engine/kernel/capability edit (SC-001). NO
`SNAPSHOT_UPDATE`. NO migration. NO commit trailer. NEVER push, NEVER main. The LIVE Bedrock
proof (spec-writer actually SEES the diagram) + the middleware/checkpointer gate (IMAGE-INPUT
§12 F2/F3) are DEFERRED to a user-driven run — do NOT attempt a live Bedrock run.
</objective>

<execution_context>
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/.claude/gsd-core/workflows/execute-plan.md
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/IMAGE-INPUT-PLAN.md
@.planning/quick/260707-edw-image-input-wave-1-backend-carrier-input/260707-edw-SUMMARY.md
@CLAUDE.md
@backend/CLAUDE.md

# The two declaration surfaces this plan edits
@backend/agents/workflows/prototype/workflow.yaml
@backend/agents/prompts/prototype-specify/AGENT.md

# The already-landed Wave-1 wiring this opt-in activates (READ, do NOT edit)
@backend/agents/capabilities/input_providers/run_images.py
@backend/tests/agents/test_image_input_wiring.py
</context>

<key_facts>
Verified during planning — the executor can rely on these without re-deriving:

- **Manifest surface already exists (Wave 1).** `input_providers` is in `manifest.py`
  `_ALLOWED_TOP_KEYS` (:103), parsed at `:204` (`_optional_list`), compiled at
  `compiler.py:215`/`:258`, lands on `CompiledWorkflow.input_providers` (`plan.py:412`), and is
  threaded to `ectx.compiled_input_providers` by the engine. Adding the manifest key requires
  NO parser/compiler edit.
- **`images` is accepted by the loader with NO allow-list.** `loader.py:348` parses `injects`
  with a generic string-list parser; the `# subset of [template, design_system, craft]` note at
  `loader.py:104` is a COMMENT, not an allow-list. `images` loads onto `spec.injects` verbatim.
- **`images` is INERT in BOTH prompt paths** (this is why goldens stay byte-identical):
  - `factory._compose_injection` (`factory.py:656-739`) fires ONLY on `"template"` /
    `"design_system"` / `"craft"` membership → an unknown `images` inject is silently ignored →
    system prompt UNCHANGED.
  - The `opendesign` context provider gates its context_message blocks on `"design_system" in
    injects` (`opendesign.py:91`) and `"template" in injects` (`:107`) ONLY → `images` matches
    neither → context_message UNCHANGED. This is documented verbatim at `opendesign.py:126-127`
    ("factory._compose_injection silently ignores unknown inject values, so declaring it injects
    nothing on its own").
- **The engine gate that `images` DOES flip** is `_compose_input_blocks` (`engine.py:5978-6016`):
  `agent_injects = set(spec.injects) ∪ set(ectx.current_step.injects)`; `"images" not in gate →
  []`; else resolve each `ectx.compiled_input_providers` name and extend with `provider.load(ectx)`.
- **Goldens are dormant BY CONSTRUCTION.** The golden harness `_drive("prototype")`
  (`tests/agents/_scripted_model.py:495/647`) calls `engine.execute(**kwargs)` with NO `images=`
  kwarg → `ectx.run_images == []`. So for `prototype-specify` the gate is now TRUE, the engine
  resolves `run_images`, calls `.load(ectx)` which reads the EMPTY carrier and returns `[]` →
  `input_blocks == []` → `_dispatch_payload(cm, [])` returns the BARE str → byte-identical
  dispatch; `image_count` is added to the event `data` ONLY when `input_blocks` is non-empty →
  NOT emitted → event golden UNCHANGED.
- **The oracle (`test_context_message_oracle.py`) is safe.** Its byte-equality tests compare only
  `prototype-build` messages (`_build_agent_context_messages` filters `agent_id ==
  "prototype-build"`, whose injects are UNCHANGED). Its stability tests call `build_oracle_message`
  which reads the oracle's OWN hardcoded `_CLASS_INPUTS` dict — never the real `prototype-specify`
  spec. Adding `images` to the real AGENT.md touches neither.
- **No test pins the REAL `prototype-specify` injects.** `test_loader_new_fields.py` and
  `test_factory_injects.py` use synthetic metadata dicts / `_Spec` dataclasses, not
  `load_agent_spec("prototype-specify")`. So NO existing test is expected to trip. (If gate 2
  DOES surface a real-spec injects pin, updating it to include `images` is a legitimate
  declaration change, NOT a golden change — see T3.2.)
- **`run_images` block shape** (`input_providers/run_images.py:42-49`):
  `{"type":"image","source_type":"base64","mime_type":img["mime_type"],"data":img["data"]}`.
- **`compile_for_run` lives at `engine.py:460`**; `load_agent_spec` in `agents/loader.py`.
</key_facts>

<tasks>

<task type="auto">
  <name>Task 1: Data-only opt-in (manifest + AGENT.md) + golden-safety dormancy proof (T3.1a + T3.1b + T3.2)</name>
  <read_first>
    - backend/agents/workflows/prototype/workflow.yaml (:33 `context_providers: [opendesign]`)
    - backend/agents/prompts/prototype-specify/AGENT.md (:9-11 `injects:` list)
    - backend/agents/execution_engine/engine.py:5978-6016 (`_compose_input_blocks` gate)
    - backend/agents/capabilities/context_providers/opendesign.py:79-134 (per-injects gate + :126-127 note)
    - backend/agents/execution_engine/engine.py:460 (`compile_for_run`) — read-only context
  </read_first>
  <files>backend/agents/workflows/prototype/workflow.yaml, backend/agents/prompts/prototype-specify/AGENT.md</files>
  <action>
    T3.1a MANIFEST OPT-IN (per T3.1a) — Edit `backend/agents/workflows/prototype/workflow.yaml`:
    add a NEW top-level key `input_providers: [run_images]` immediately after the existing
    `context_providers: [opendesign]` line (:33), at the SAME top-level indentation (sibling of
    `context_providers`, NOT nested under a step). This top-level key is already in the manifest
    `_ALLOWED_TOP_KEYS` (manifest.py:103) → parses (:204) → compiles (compiler.py:215/258) →
    `CompiledWorkflow.input_providers` (plan.py:412) → `ectx.compiled_input_providers`. Do NOT
    add any per-step `input_providers`.

    T3.1b AGENT OPT-IN (per T3.1b) — Edit `backend/agents/prompts/prototype-specify/AGENT.md`:
    append `- images` to the `injects:` YAML block (:9-11) so the effective list is
    `[template, design_system, images]` (add the new item AFTER `- design_system`, same list
    indentation). VERIFIED SAFE (see <key_facts>): loader accepts it (no allow-list); factory
    `_compose_injection` and the opendesign provider both ignore unknown injects → the composed
    system prompt AND context_message are UNCHANGED. This makes the engine `_compose_input_blocks`
    gate (`"images" in set(spec.injects) ∪ set(step.injects)`) TRUE for the spec-writer.

    T3.2 GOLDEN SAFETY (per T3.2, the load-bearing gate) — Run the verify gates below with
    `SNAPSHOT_UPDATE` UNSET. WHY they hold: the golden harness drives `execute()` with NO images
    → `ectx.run_images == []` → `run_images.load` returns `[]` → `_compose_input_blocks` returns
    `[]` → bare-str dispatch → byte-identical, no `image_count`; and `_compose_injection` +
    opendesign ignore `images` → prompt/context_message unchanged. If ANY golden or the oracle
    DIVERGES, STOP and diagnose the root cause — do NOT `SNAPSHOT_UPDATE` and do NOT proceed.
    Only IF gate 2 surfaces a test that pins `prototype-specify`'s EXACT injects
    (`test_loader_new_fields.py` / `test_factory_injects.py` — NOT expected to trip per
    <key_facts>), update that pin to include `images`; that is a legitimate declaration change,
    NOT a golden change.

    NEGATIVE SPACE: do NOT edit any file under `agents/execution_engine/`,
    `agents/capabilities/`, `agents/factory.py`, `agents/loader.py`, or any `*.py` kernel module
    (SC-001 — data-only opt-in). No migration. No commit trailer.
  </action>
  <acceptance_criteria>
    - `input_providers: [run_images]` present as a top-level key in the prototype manifest.
    - `images` present in `prototype-specify`'s `injects` list.
    - Gate 1: the 5 characterization goldens + the context_message oracle are byte/event-identical
      (SNAPSHOT_UPDATE unset).
    - Gate 2: manifest parses/compiles `input_providers`, loader accepts the new inject, registry
      drift-guard len == 65 — with ONLY the 2 pre-existing reds unchanged
      (`test_display_name[dotnet_to_azure|custom]`; do NOT fix them). The 7 pre-existing
      `test_clarify_defaults_match_engine` reds live in `test_manifest_parity.py` (not in gate 2's
      command) — leave them alone.
    - Gate 3: `/opt/homebrew/bin/lint-imports` → 4 kept / 0 broken.
    - Gate 5 (INV-1): `grep -rnE 'pipeline_type ==|spec\.id ==' backend/agents/execution_engine/engine.py`
      returns the SAME set as before this plan (no new workflow-name/id branch → SC-001).
  </acceptance_criteria>
  <verify>
    <automated>cd backend && python3.11 -m pytest tests/agents/test_characterization_prototype.py tests/agents/test_characterization_od_prototype.py tests/agents/test_characterization_prototype_revision.py tests/agents/test_characterization_od_ppt.py tests/agents/test_characterization_app_builder.py tests/agents/test_context_message_oracle.py -q</automated>
    <automated>cd backend && python3.11 -m pytest tests/agents/test_manifest.py tests/agents/test_registry_capabilities.py tests/unit/test_loader_new_fields.py tests/unit/test_factory_injects.py -q</automated>
    <automated>/opt/homebrew/bin/lint-imports</automated>
    <automated>cd backend && grep -rnE 'pipeline_type ==|spec\.id ==' agents/execution_engine/engine.py | wc -l</automated>
  </verify>
  <done>
    The prototype manifest carries `input_providers: [run_images]`, `prototype-specify` carries
    `images` in `injects`, gate 1 is fully byte/event-identical (SNAPSHOT_UPDATE unset), gate 2
    shows drift-guard 65 with only the 2 known `test_display_name` reds remaining, gate 3 is
    4 kept / 0 broken, and gate 5 (INV-1 grep count) is unchanged from HEAD.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Wiring test — the opt-in DELIVERS via the REAL compiled plan + REAL specs (T3.3)</name>
  <read_first>
    - backend/tests/agents/test_image_input_wiring.py (the ExecutionContext + registry.discover harness pattern to mirror)
    - backend/agents/capabilities/input_providers/run_images.py (:42-49 exact block shape)
    - backend/agents/execution_engine/engine.py:460 (`compile_for_run`) + :5978-6016 (`_compose_input_blocks`)
    - backend/agents/loader.py (`load_agent_spec`)
  </read_first>
  <files>backend/tests/agents/test_prototype_image_optin.py</files>
  <behavior>
    - Declaration pins: `compile_for_run("prototype").input_providers == ["run_images"]`, and
      `"images" in load_agent_spec("prototype-specify").injects`.
    - DELIVERS (opted-in): with `ectx.run_images == [{"mime_type":"image/png","data":"<base64>"}]`,
      `ectx.compiled_input_providers = compile_for_run("prototype").input_providers`,
      `ectx.current_step = SimpleNamespace(injects=[])`, and the REAL
      `load_agent_spec("prototype-specify")` spec →
      `await ExecutionEngine()._compose_input_blocks(spec, ectx)` returns EXACTLY one block
      `{"type":"image","source_type":"base64","mime_type":"image/png","data":"<base64>"}`.
    - DORMANT for a non-opted agent (control): the SAME `ectx` but the REAL
      `load_agent_spec("prototype-plan")` spec (no `images` inject) →
      `_compose_input_blocks(spec, ectx)` returns `[]`.
  </behavior>
  <action>
    Author `backend/tests/agents/test_prototype_image_optin.py` — the end-to-end opt-in proof
    using the REAL manifest/AGENT.md (NOT a mock/`SimpleNamespace` spec for the two opt-in arms).
    Mirror the harness in `test_image_input_wiring.py`: call `registry_mod.discover()` to bind the
    `run_images` impl; build `ExecutionContext(run_id=..., owner_id=...)`; set `run_images` +
    `compiled_input_providers` (sourced from `compile_for_run("prototype").input_providers`, NOT a
    literal) + `current_step = SimpleNamespace(injects=[])`; resolve the specs via
    `load_agent_spec("prototype-specify")` / `load_agent_spec("prototype-plan")`; call the
    async `ExecutionEngine()._compose_input_blocks(spec, ectx)` (use `@pytest.mark.asyncio` like
    the existing wiring suite). Assert the opted-in arm returns the single image block and the
    non-opted control returns `[]`, plus the two declaration-pin assertions.

    Record the DEFERRED live-verification item in the plan SUMMARY (project convention,
    defer-live-verification-to-milestone-end): "LIVE Bedrock proof — the spec-writer actually
    receives/reads the attached diagram — + the middleware/checkpointer image-payload gate
    (IMAGE-INPUT §12 F2/F3) are DEFERRED to a user-driven run; the orchestrator will produce the
    runbook. Do NOT attempt a live Bedrock run in this plan."
  </action>
  <acceptance_criteria>
    - The new test file exists and asserts: declaration pins (input_providers + specify injects),
      opted-in delivery (exactly one base64 image block off the REAL prototype-specify spec), and
      the non-opted control (`prototype-plan` → `[]`).
    - The test uses the REAL compiled plan + REAL loaded specs (not a hand-built mock spec) for
      the two opt-in arms.
    - The SUMMARY records the deferred live-verification item.
  </acceptance_criteria>
  <verify>
    <automated>cd backend && python3.11 -m pytest tests/agents/test_prototype_image_optin.py -q</automated>
  </verify>
  <done>
    `test_prototype_image_optin.py` is green: the real prototype-specify spec + real compiled
    prototype plan + a populated `ectx.run_images` yield exactly one
    `{"type":"image","source_type":"base64",...}` block, the real prototype-plan spec yields `[]`,
    and the two declaration pins hold. The deferred live item is recorded in the SUMMARY.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| user-supplied image → model prompt | A base64 image on the run carrier (`ectx.run_images`) now reaches the `prototype-specify` model dispatch for the first time (Wave-3 opt-in flips consumption ON). |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-gvq-01 | Denial of Service | oversized / high-count image payloads reaching the model via `run_images` | transfer | Ingest caps (mime allow-list, per-image/per-run size, count) live at the Wave-2 carrier normalization (`_normalize_run_images`, IMAGE-INPUT §3/§12) — NOT re-implemented here. This wave only flips one agent's opt-in; it adds no new ingest path. |
| T-gvq-02 | Information Disclosure | image content-block leaking to a NON-opted downstream agent | mitigate | The Wave-1 BLOCKER isolation test pins the per-agent-local gate (`_compose_input_blocks` reads `set(spec.injects) ∪ set(step.injects)`, NEVER the stale `ectx.current_spec_injects`); T3.3's non-opted `prototype-plan → []` control re-proves the boundary holds after this opt-in. |
| T-gvq-03 | Tampering | image-payload amplification across retry / checkpointer replay (IMAGE-INPUT §12 F2/F3) | accept (deferred) | The middleware/checkpointer image-payload gate is DEFERRED to the user-driven live run (runbook produced by the orchestrator). Recorded as a standing deferred live-verification item; out of scope for this offline data-only opt-in. |
| T-gvq-SC | Tampering | npm/pip/cargo installs | accept | No package installs in this wave (data-only manifest/AGENT.md edit + one test file) → no supply-chain surface. |
</threat_model>

<verification>
Hard gates (ALL must pass; the 2 pre-existing `test_display_name` reds stay identically red — do
NOT fix):

1. `cd backend && python3.11 -m pytest tests/agents/test_characterization_prototype.py tests/agents/test_characterization_od_prototype.py tests/agents/test_characterization_prototype_revision.py tests/agents/test_characterization_od_ppt.py tests/agents/test_characterization_app_builder.py tests/agents/test_context_message_oracle.py -q` — 5 goldens + oracle byte/event-identical (SNAPSHOT_UPDATE UNSET; od_ppt event snapshot stays GREEN).
2. `cd backend && python3.11 -m pytest tests/agents/test_manifest.py tests/agents/test_registry_capabilities.py tests/unit/test_loader_new_fields.py tests/unit/test_factory_injects.py -q` — manifest parses/compiles `input_providers`, loader accepts `images`, drift-guard 65; only the 2 known `test_display_name` reds remain.
3. `/opt/homebrew/bin/lint-imports` — 4 kept / 0 broken.
4. `cd backend && python3.11 -m pytest tests/agents/test_prototype_image_optin.py -q` — the T3.3 wiring test green (opted-in spec → image block; non-opted → []).
5. INV-1 / SC-001: `cd backend && grep -rnE 'pipeline_type ==|spec\.id ==' agents/execution_engine/engine.py | wc -l` — unchanged from HEAD (no workflow-name branch added; this wave touches only manifest + AGENT.md data).

DEFERRED (do NOT run here): the LIVE Bedrock proof (spec-writer sees the diagram) + the
middleware/checkpointer image-payload gate (IMAGE-INPUT §12 F2/F3) — user-driven run, runbook
produced by the orchestrator.
</verification>

<success_criteria>
- Prototype manifest declares `input_providers: [run_images]`; `prototype-specify` declares
  `injects: [template, design_system, images]`.
- Gates 1-5 pass as specified (goldens/oracle byte-identical with SNAPSHOT_UPDATE unset;
  manifest/loader/registry green with only the 2 known display_name reds; lint-imports 4/0;
  wiring test green; INV-1 grep unchanged).
- Zero kernel/engine/capability `*.py` edit (SC-001); zero migration; zero `SNAPSHOT_UPDATE`.
- The deferred live-verification item (live Bedrock proof + §12 F2/F3 gate) is recorded in the
  SUMMARY; no live Bedrock run attempted.
- Committed to `new-workflow-engine` (NEVER main, NEVER push), no commit trailer.
</success_criteria>

<output>
Create `.planning/quick/260707-gvq-image-input-wave-3-opt-in-prototype-spec/260707-gvq-SUMMARY.md`
when done, including the DEFERRED live-verification item.
</output>
