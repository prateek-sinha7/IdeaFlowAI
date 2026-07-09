---
phase: 260707-edw
plan: 01
type: execute
wave: 1
depends_on: []
autonomous: true
requirements: [T1.1, T1.2, T1.3, T1.4, T1.5, T1.6, T1.7]
files_modified:
  - backend/agents/execution_engine/engine.py
  - backend/agents/execution_engine/context.py
  - backend/agents/capabilities/base.py
  - backend/agents/capabilities/input_providers/__init__.py
  - backend/agents/capabilities/input_providers/run_images.py
  - backend/agents/capabilities/registry.py
  - backend/agents/workflows/manifest.py
  - backend/agents/workflows/compiler.py
  - backend/agents/workflows/plan.py
  - backend/app/agents/deep_agent_runner.py
  - backend/tests/agents/characterization/_normalize.py
  - backend/tests/agents/test_registry_capabilities.py
  - backend/tests/agents/test_input_providers_run_images.py
  - backend/tests/agents/test_image_input_wiring.py

must_haves:
  truths:
    - "An image content-block CAN reach an opted-in agent's model dispatch, but no workflow opts in this wave, so the feature is DORMANT."
    - "All 5 characterization goldens are byte/event-identical with SNAPSHOT_UPDATE unset (4 fully green; od_ppt::test_od_ppt_event_snapshot fails IDENTICALLY before/after — a pre-existing branch red)."
    - "The run_images capability returns shaped {type:image,source_type:base64,mime_type,data} blocks when ctx.run_images is populated, and [] when empty."
    - "_compose_input_blocks gates LOCALLY on set(spec.injects) | set(step.injects) — an agent with no image inject gets [] even when ectx.current_spec_injects still holds {images} from a prior opted-in agent (no cross-agent leak)."
    - "The agent_input event's data.context_message stays a TEXT str always; image blocks ride only into the model dispatch content-list."
    - "The registry drift-guard is green: len(_KNOWN) == 65 and set(_KNOWN) == set(_EXPECTED_NAMES) (T1.4 also reconciles the pre-existing branch-red KAN-73 hook:audit_logger drift into _EXPECTED_NAMES so the sets equalize)."
    - "lint-imports stays 4 kept / 0 broken and the engine keys on injects/declared data, never a workflow name (INV-1 grep = 0)."
  artifacts:
    - path: "backend/agents/capabilities/base.py"
      provides: "InputContentProvider(Protocol) port — name:str + async def load(self, ctx) -> list"
      contains: "class InputContentProvider"
    - path: "backend/agents/capabilities/input_providers/run_images.py"
      provides: "run_images capability — @register('input_provider','run_images'), reads ctx.run_images, returns image content-blocks or []"
      contains: "@register("
      min_lines: 25
    - path: "backend/agents/capabilities/input_providers/__init__.py"
      provides: "input_providers capability package"
    - path: "backend/agents/execution_engine/context.py"
      provides: "ExecutionContext.run_images carrier field"
      contains: "run_images"
    - path: "backend/agents/execution_engine/engine.py"
      provides: "execute(images=)/_execute_impl(images=) carrier param, _normalize_run_images seam, _compose_input_blocks sibling, _dispatch_payload wrap, ectx.compiled_input_providers thread"
      contains: "_compose_input_blocks"
    - path: "backend/agents/workflows/manifest.py"
      provides: "WorkflowManifest.input_providers field + input_providers in _ALLOWED_TOP_KEYS + _optional_list parse"
      contains: "input_providers"
    - path: "backend/agents/workflows/compiler.py"
      provides: "input_provider validation loop + input_providers=list(manifest.input_providers) in CompiledWorkflow ctor"
      contains: "input_provider"
    - path: "backend/agents/workflows/plan.py"
      provides: "CompiledWorkflow.input_providers: list[str] = field(default_factory=list)"
      contains: "input_providers"
    - path: "backend/tests/agents/test_image_input_wiring.py"
      provides: "BLOCKER two-agent isolation test + dispatch-wrap test + runner str|list widening test"
      contains: "current_spec_injects"
  key_links:
    - from: "backend/agents/execution_engine/engine.py::_execute_impl"
      to: "ExecutionContext.run_images"
      via: "run_images=_normalize_run_images(images) at the ExecutionContext(...) construction"
      pattern: "run_images=_normalize_run_images\\(images\\)"
    - from: "backend/agents/execution_engine/engine.py::_run_agent"
      to: "_compose_input_blocks"
      via: "per-agent local input_blocks = await self._compose_input_blocks(spec, ectx)"
      pattern: "input_blocks = await self\\._compose_input_blocks\\(spec, ectx\\)"
    - from: "backend/agents/execution_engine/engine.py::_compose_input_blocks"
      to: "input_provider capability"
      via: "_CAPABILITY_REGISTRY.resolve('input_provider', name).load(ectx) gated on 'images' in local agent_injects"
      pattern: "resolve\\(\\s*['\\\"]input_provider['\\\"]"
    - from: "backend/agents/execution_engine/engine.py dispatch (:2880)"
      to: "agent.astream_events"
      via: "_dispatch_payload(context_message, input_blocks) — bare str when empty, [text-block, *input_blocks] when non-empty"
      pattern: "astream_events\\(_dispatch"
    - from: "backend/agents/capabilities/registry.py::discover"
      to: "agents.capabilities.input_providers.run_images"
      via: "_builtin_modules import tuple entry (registry lockstep)"
      pattern: "input_providers\\.run_images"
---

<objective>
Build the DORMANT backend spine so an image content-block CAN reach an agent — a carrier
(`ExecutionContext.run_images`), a registered `input_provider` capability (`run_images`), the
manifest/compiler/plan declaration surface, and the engine wiring + multimodal dispatch — WITHOUT
any workflow opting in this wave. Because no manifest declares `input_providers:` and no
AGENT.md declares `injects:[images]`, the dispatch-wrap NEVER fires and the change is
byte-identical BY CONSTRUCTION: all 5 characterization goldens stay byte/event-identical with
`SNAPSHOT_UPDATE` unset (Wave 1 gate, IMAGE-INPUT-PLAN §4).

Implements Locked Decisions #1 (base64+mime_type block), #2 (new port not a transport hardcode),
#3 (split-transport: `agent_input` stays str, only dispatch wraps → zero re-baseline), #4 (opt-in
via `injects`, never a workflow name), #5 (transient carrier, zero migration). Plan-check BLOCKER
F1 is designed out: the gate is derived LOCALLY per-agent from `spec.injects ∪ step.injects`, the
blocks are a per-agent LOCAL in `_run_agent`, and there is NO shared `ectx.pending_input_blocks`
field — so a non-opted agent running after an opted-in one can never inherit the stale
`ectx.current_spec_injects` and leak an image.

Purpose: satisfy SC-001 / INV-1 (image workflows compose by manifest + AGENT.md, zero engine
edits) and INV-3 (deterministic byte + semantic-event parity for the existing pipelines).
Output: carrier, port, capability + registry lockstep, declaration surface, engine wiring,
transport dispatch, runner widening, and the TDD test suite (incl. the mandatory BLOCKER
two-agent isolation regression).
</objective>

<execution_context>
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/.claude/gsd-core/workflows/execute-plan.md
</execution_context>

<context>
@.planning/IMAGE-INPUT-PLAN.md
@CLAUDE.md
@backend/CLAUDE.md
</context>

<artifacts_this_phase_produces>
New symbols / surfaces introduced by this plan (dormant until a later wave opts a workflow in):

| Symbol / surface | File | Kind |
|---|---|---|
| `InputContentProvider(Protocol)` | `backend/agents/capabilities/base.py` | new port (`name:str` + `async def load(self, ctx) -> list`) |
| `run_images` capability | `backend/agents/capabilities/input_providers/run_images.py` | new `@register("input_provider","run_images",...)` impl |
| `input_providers` package | `backend/agents/capabilities/input_providers/__init__.py` | new capability package |
| `input_provider` kind | `backend/agents/capabilities/registry.py` (`_KNOWN`) + `discover()._builtin_modules` | new registered `(kind,name)` pair |
| `WorkflowManifest.input_providers` | `backend/agents/workflows/manifest.py` | new manifest top-key + field + parse |
| `CompiledWorkflow.input_providers` | `backend/agents/workflows/plan.py` | new compiled field `list[str]` |
| `ExecutionContext.run_images` | `backend/agents/execution_engine/context.py` | new transient carrier field |
| `execute(images=)` / `_execute_impl(images=)` | `backend/agents/execution_engine/engine.py` | new additive carrier params |
| `_normalize_run_images(...)` | `backend/agents/execution_engine/engine.py` | new module-level seam helper `list -> list[{mime_type,data}]` |
| `_compose_input_blocks(self, spec, ectx)` | `backend/agents/execution_engine/engine.py` | new sibling method (locally-gated block producer) |
| `_dispatch_payload(...)` | `backend/agents/execution_engine/engine.py` | new module-level transport-wrap helper `(str, list) -> str \| list` |
| `ectx.compiled_input_providers` | `backend/agents/execution_engine/engine.py` (beside :1671) | new per-run dynamic-attr thread |
| `image_count` (agent_input, only-when->0) | `backend/agents/execution_engine/engine.py` + `_normalize.py` strip | new optional observability key |
</artifacts_this_phase_produces>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Carrier + port + run_images capability + registry lockstep (T1.1-T1.4)</name>
  <files>backend/agents/execution_engine/engine.py, backend/agents/execution_engine/context.py, backend/agents/capabilities/base.py, backend/agents/capabilities/input_providers/__init__.py, backend/agents/capabilities/input_providers/run_images.py, backend/agents/capabilities/registry.py, backend/tests/agents/test_registry_capabilities.py, backend/tests/agents/test_input_providers_run_images.py</files>
  <read_first>
    backend/agents/execution_engine/engine.py (execute() sig :764-782 with od_context :776; _execute_impl sig :841-859 with od_context :853; the forward call :806-824 with od_context=od_context :817; ExecutionContext(...) construction :975-983 with od_context=od_context :979)
    backend/agents/execution_engine/context.py (od_context field :113 — the carrier precedent to mirror)
    backend/agents/capabilities/base.py (the Protocol ports block :27-121 — the one-method-Protocol idiom, stdlib typing only)
    backend/agents/capabilities/context_providers/opendesign.py (the @register + name + async load provider pattern to mirror; imports ONLY registry + stdlib)
    backend/agents/capabilities/context_providers/__init__.py (the package docstring style to mirror for the new package)
    backend/agents/capabilities/registry.py (_KNOWN literal :80-145, incl. the pre-existing ('hook','audit_logger') / KAN-73 entry :129; register() decorator :177-215; discover()._builtin_modules tuple :249-299)
    backend/tests/agents/test_registry_capabilities.py (_EXPECTED_NAMES list :38-102; the count drift-guard assert len(_KNOWN) == 63 :154 — ALREADY RED on this branch: ('hook','audit_logger') / KAN-73 is in _KNOWN :129 but was never added to _EXPECTED_NAMES nor counted, so len(_KNOWN)==64 while the assert says 63 and set(_KNOWN)-set(_EXPECTED_NAMES)=={('hook','audit_logger')} (the set-equality assert :155 is masked only because the count assert trips first); T1.4 makes it == 65 + its tally comment :126-153)
  </read_first>
  <behavior>
    - run_images capability: given a ctx whose run_images == [{"mime_type":"image/png","data":"AAAA"}], load(ctx) returns [{"type":"image","source_type":"base64","mime_type":"image/png","data":"AAAA"}].
    - run_images capability: given ctx.run_images empty/None/absent, load(ctx) returns [].
    - run_images capability: multiple images map 1:1 in order.
    - _normalize_run_images: [{"name":"x.png","mime_type":"image/png","data":"AA"}] -> [{"mime_type":"image/png","data":"AA"}] (name dropped from carrier is acceptable; a malformed entry missing data OR mime_type is dropped); None/[] -> [].
    - registry: is_registered("input_provider","run_images") is True; resolve("input_provider","run_images") returns an impl whose .name == "run_images"; len(_KNOWN) == 65.
  </behavior>
  <action>
    T1.1 CARRIER. In `engine.py` add an additive keyword param `images: list | None = None` to
    `execute()` (beside `od_context: dict | None = None` at :776) AND to `_execute_impl()` (beside
    `od_context` at :853). In the `execute()` -> `_execute_impl(...)` forward call add
    `images=images` beside `od_context=od_context` (:817). Add a module-level pure helper
    `_normalize_run_images(images: list | None) -> list[dict]` mapping each incoming image dict to
    the canonical carrier shape `{"mime_type": <str>, "data": <base64 str>}` — read `mime_type`
    (accept a `mimeType` alias defensively) and `data`, DROP any entry missing either, return `[]`
    for None/empty (base64 passed through verbatim — no decode; Locked Decision #1). At the
    `ExecutionContext(...)` construction (:975-983) add `run_images=_normalize_run_images(images),`
    beside `od_context=od_context` (:979). Default empty ⇒ every existing caller passes nothing ⇒
    `run_images == []` ⇒ dormant (INV-3).

    In `context.py` add `run_images: list | None = None` beside `od_context` (:113), with a one-line
    comment mirroring od_context: transient per-run image carrier holding normalized
    `{mime_type, data(base64)}`, consumed by the `run_images` input_provider; default None ⇒ dormant.

    T1.2 PORT. In `base.py` add `InputContentProvider(Protocol)` after the `ContextProvider` block
    (:76-83), same `@runtime_checkable` one-method idiom: `name: str` + `async def load(self, ctx:
    Any) -> list: ...`. Stdlib typing ONLY (Any already imported) — no kernel/app import. Docstring:
    loads image/binary content-blocks (list, NOT the dict[str,str] ContextProvider shape) appended
    to the model dispatch. Do NOT add it to `test_registry_capabilities.py::_PORTS` (that hardcoded
    6-list is separate; a new base.py port does NOT auto-trip it).

    T1.3 CAPABILITY. Create `agents/capabilities/input_providers/__init__.py` (short docstring
    mirroring `context_providers/__init__.py`). Create
    `agents/capabilities/input_providers/run_images.py` importing ONLY `from
    agents.capabilities.registry import register` + stdlib `typing.Any`. Decorate the impl class
    with `@register("input_provider", "run_images", user_allowed=True, description="Attach the
    run's user-supplied images (base64) as multimodal content-blocks to the agent prompt.",
    config_schema={})`. Class has `name = "run_images"` and `async def load(self, ctx: Any) -> list`
    that reads `getattr(ctx, "run_images", None) or []` and returns one block per image
    `{"type":"image","source_type":"base64","mime_type":<img["mime_type"]>,"data":<img["data"]>}`,
    returning `[]` when empty. It MUST NOT read `ctx.current_spec_injects` (that stale field is the
    F1 leak vector — gating is the caller's job, Task 3). Satisfies the `InputContentProvider` port
    structurally.

    T1.4 REGISTRY LOCKSTEP (atomic with T1.3 or the drift-guard fails). PRECONDITION — READ THIS:
    the drift-guard `assert len(_KNOWN) == 63` (:154) is ALREADY RED on this branch. The pair
    `("hook", "audit_logger")` (KAN-73) sits in `_KNOWN` (:129) but was never added to
    `_EXPECTED_NAMES` nor counted, so on entry `len(_KNOWN) == 64` while the assert says 63 and
    `set(_KNOWN) - set(_EXPECTED_NAMES) == {("hook", "audit_logger")}` (the set-equality assert :155
    is masked only because the count assert trips first). Adding `run_images` alone therefore CANNOT
    green the guard — the sets would still differ by `audit_logger`. T1.4 MUST reconcile that
    pre-existing branch-red drift as a necessary precondition for a green drift-guard (this is
    in-scope: the set-equality assert cannot pass otherwise).

    In `registry.py` add `("input_provider", "run_images"),` to `_KNOWN` (:80-145) with comment
    `# 260707-edw — image-input Wave 1 (user_allowed=True)` — this is the ONLY `_KNOWN` change
    (`("hook", "audit_logger")` is already present at :129), and add an `# input_provider:
    run_images` line to the kinds tally comment (:66-79). Add
    `"agents.capabilities.input_providers.run_images",` to the `discover()._builtin_modules` tuple
    (:249-299). In `test_registry_capabilities.py` add BOTH `("hook", "audit_logger"),`
    (reconciling the KAN-73 drift so the sets equalize) AND `("input_provider", "run_images"),`
    (the new capability) to `_EXPECTED_NAMES` (:38-102), bump `assert len(_KNOWN) == 63` -> `== 65`
    (:154), and extend the tally comment (:126-153) with TWO clauses: `+1 KAN-73 hook:audit_logger =
    64` and `+1 260707-edw input_provider:run_images = 65`.

    Write `tests/agents/test_input_providers_run_images.py` implementing the `<behavior>` cases (a):
    shaped-block, empty/None, multi-image order, `_normalize_run_images` canonicalize/drop, and a
    registry resolve/is_registered/len==65 case (use the `_clean_registry` discover-snapshot idiom
    from the registry test if the impl must be discovered). RED first (import not-yet-written
    symbols → fail), then GREEN.
  </action>
  <verify>
    <automated>cd backend && python3.11 -m pytest tests/agents/test_input_providers_run_images.py tests/agents/test_registry_capabilities.py -q</automated>
  </verify>
  <done>
    - `run_images` capability + `input_providers/run_images.py` + `__init__.py` exist; `InputContentProvider` port in base.py.
    - `execute(images=)`/`_execute_impl(images=)` + `_normalize_run_images` + `ExecutionContext.run_images` landed; forward call threads `images=images`.
    - `("input_provider","run_images")` added to `_KNOWN` + `_EXPECTED_NAMES`, and `("hook","audit_logger")` added to `_EXPECTED_NAMES` (reconciling the pre-existing KAN-73 branch-red drift); `discover()` imports the module; `assert len(_KNOWN) == 65` green.
    - `test_registry_capabilities.py -q` green (set(_KNOWN) == set(_EXPECTED_NAMES)); new capability suite green.
    - Atomic commit (no trailer): `feat(engine): image-input carrier + run_images input_provider + registry lockstep (260707-edw T1.1-T1.4)`.
  </done>
</task>

<task type="auto">
  <name>Task 2: Manifest / compiler / plan declaration surface (T1.5)</name>
  <files>backend/agents/workflows/manifest.py, backend/agents/workflows/compiler.py, backend/agents/workflows/plan.py</files>
  <read_first>
    backend/agents/workflows/manifest.py (WorkflowManifest.context_providers field :61; _ALLOWED_TOP_KEYS frozenset :92-113; _optional_list parse of context_providers :199; the WorkflowManifest(...) ctor pass-through context_providers=context_providers :221; _optional_list helper :261-271)
    backend/agents/workflows/compiler.py (workflow-level context_provider validation loop :207-211 with is_registered + _check_trust; _check_trust signature :316-340; the CompiledWorkflow(...) ctor copy context_providers=list(manifest.context_providers) :250)
    backend/agents/workflows/plan.py (CompiledWorkflow.context_providers field :409)
  </read_first>
  <action>
    In `manifest.py`: add `"input_providers",` to `_ALLOWED_TOP_KEYS` (:92-113, beside
    `"context_providers"`). Add `input_providers: list = field(default_factory=list)` to the
    `WorkflowManifest` dataclass (beside `context_providers` :61). In parse add `input_providers =
    _optional_list(data, "input_providers", file_str)` mirroring :199 and pass
    `input_providers=input_providers` in the `WorkflowManifest(...)` construction (beside :221).
    Pure data (INV-5) — no control flow.

    In `compiler.py`: after the context_provider validation loop (:207-211) add a sibling loop over
    `manifest.input_providers` that raises `CompilerError(f"unknown input_provider '{ip}' in
    {where}")` when `not registry.is_registered("input_provider", ip)`, then calls
    `self._check_trust(registry, "input_provider", ip, trusted, where)` — mirroring the
    context_provider loop exactly (kind `"input_provider"`). In the `CompiledWorkflow(...)` return
    (:246-260) add `input_providers=list(getattr(manifest, "input_providers", []) or []),` beside
    `context_providers=list(manifest.context_providers)` (:250).

    In `plan.py`: add `input_providers: list[str] = field(default_factory=list)` to the
    `CompiledWorkflow` dataclass beside `context_providers` (:409), with a comment: carries the
    workflow's declared `input_provider` capability names (image-input Wave 1).

    NEGATIVE SPACE: do NOT add `input_providers:` to any existing `agents/workflows/*/workflow.yaml`
    this wave (dormant). Every existing manifest omits the key ⇒ `_optional_list` returns `[]` ⇒
    `CompiledWorkflow.input_providers == []` ⇒ the Task-3 gate never fires (INV-3).
  </action>
  <verify>
    <automated>cd backend && python3.11 -c "from agents.workflows.manifest import WorkflowManifest, _ALLOWED_TOP_KEYS; from agents.workflows.plan import CompiledWorkflow; assert 'input_providers' in _ALLOWED_TOP_KEYS; assert 'input_providers' in WorkflowManifest.__dataclass_fields__; assert 'input_providers' in CompiledWorkflow.__dataclass_fields__; print('SURFACE OK')" && python3.11 -m pytest tests/unit/test_manifest.py tests/unit/test_compiler.py -q</automated>
  </verify>
  <done>
    - `"input_providers"` in `_ALLOWED_TOP_KEYS`; `WorkflowManifest.input_providers` + `_optional_list` parse + ctor pass-through landed.
    - Compiler validation loop for `input_provider` (is_registered + _check_trust) present; `CompiledWorkflow(...)` ctor copies `input_providers`.
    - `CompiledWorkflow.input_providers: list[str]` field present, defaults `[]`.
    - Existing manifests unchanged (no `input_providers:` key added anywhere).
    - Atomic commit (no trailer): `feat(engine): manifest/compiler/plan input_providers declaration surface (260707-edw T1.5)`.
  </done>
</task>

<task type="auto">
  <name>Task 3: Engine wiring (_compose_input_blocks) + transport dispatch + runner widening (T1.6, T1.7)</name>
  <files>backend/agents/execution_engine/engine.py, backend/app/agents/deep_agent_runner.py, backend/tests/agents/characterization/_normalize.py</files>
  <read_first>
    backend/agents/execution_engine/engine.py (ectx.compiled_context_providers thread :1671; _run_agent def :2580; the context_message local compose :2645-2648; the redo/lineage resets :2649-2652; the agent_input emit :2657-2667 with context_message :2663; the AgentContext step_injects seam :2707-2715 reading getattr(getattr(ectx,"current_step",None),"injects",None); the attempt loop while True :2860 + dispatch :2880 astream_events(context_message); the _compose_context_message provider-resolve pattern + the STALE ectx.current_spec_injects assignment :5787-5811; module-level _CAPABILITY_REGISTRY :406)
    backend/app/agents/deep_agent_runner.py (astream_events sig :406-408 + HumanMessage(content=user_message) :476; wrapper astream_with_usage :729-731; astream :794; run :807)
    backend/tests/agents/characterization/_normalize.py (_VOLATILE_STRIP_KEYS frozenset :101)
  </read_first>
  <action>
    T1.6 ENGINE WIRING (CORRECTNESS-CRITICAL). In `engine.py` at :1671 add
    `ectx.compiled_input_providers = list(compiled.input_providers or [])` immediately after the
    `ectx.compiled_context_providers = ...` line (same dynamic-attr per-run thread). Add a NEW
    sibling method `async def _compose_input_blocks(self, spec, ectx) -> list` next to
    `_compose_context_message`. It derives its gate LOCALLY: `agent_injects = set(getattr(spec,
    "injects", []) or []) | set(getattr(getattr(ectx, "current_step", None), "injects", None) or
    [])` (the SAME spec.injects ∪ compiled Step.injects union the factory seam uses at :2713-2715).
    If `"images" not in agent_injects` return `[]` immediately. Otherwise iterate `list(getattr(ectx,
    "compiled_input_providers", []) or [])`, resolve each via
    `_CAPABILITY_REGISTRY.resolve("input_provider", name)` inside try/except (KeyError,
    RuntimeError): continue, call `await provider.load(ectx)` inside try/except that logs-and-skips
    on Exception but re-raises PermissionError (mirror the context_provider loop :5810-5816), and
    `extend` a `blocks` list with the return. Return `blocks`. It MUST NOT read
    `ectx.current_spec_injects` (F1: set once at :5803 inside `if injects:`, never reset — reading it
    would leak `{images}` to a later non-opted agent).

    Add a module-level pure helper `_dispatch_payload(context_message: str, input_blocks: list) ->
    "str | list"`: return `context_message` when `input_blocks` is falsy, else `[{"type": "text",
    "text": context_message}, *input_blocks]`.

    T1.7 TRANSPORT. In `_run_agent`, immediately after the `context_message` local is assigned
    (after :2648, alongside the redo resets — a per-agent LOCAL, NOT an ectx field) add
    `input_blocks = await self._compose_input_blocks(spec, ectx)`. At the dispatch (:2880) compute
    `_dispatch = _dispatch_payload(context_message, input_blocks)` and change the loop to `async for
    event in agent.astream_events(_dispatch):`. The dispatch sits inside the attempt `while True:`
    (:2860) so the same local is re-sent on each model-fallback retry (intended). Keep the
    `agent_input` event's `data.context_message` (:2663) a TEXT str ALWAYS — do NOT pass the wrapped
    payload there. For observability, add `image_count` to the `agent_input` `data` dict ONLY when
    `input_blocks` is non-empty (build the `data` dict then, guarded by `if input_blocks:`, set
    `data["image_count"] = len(input_blocks)`) — so a text-only run emits NO `image_count` key and
    the dormant goldens stay byte-identical. There is NO shared `ectx.pending_input_blocks` field.

    In `deep_agent_runner.py` widen the type hints to `str | list` on `astream_events` (:407),
    `astream_with_usage` (:730), `astream` (:794), and `run` (:807). No logic change —
    `HumanMessage(content=user_message)` (:476) accepts `str | list` natively (langchain_core); no
    wrapper does string ops on `user_message`.

    In `tests/agents/characterization/_normalize.py` add `"image_count",` to the
    `_VOLATILE_STRIP_KEYS` frozenset (:101) with a one-line comment (image-input Wave 1;
    belt-and-suspenders — only emitted when >0, never dormant).

    INV-1 GUARD: `_compose_input_blocks` and the dispatch wrap key ONLY on `injects`/declared data
    — no `pipeline_type ==` / `spec.id ==` / workflow-name literal.
  </action>
  <verify>
    <automated>cd backend && python3.11 -c "import agents.execution_engine.engine as e; assert hasattr(e.ExecutionEngine, '_compose_input_blocks'); assert e._dispatch_payload('cm', []) == 'cm'; w = e._dispatch_payload('cm', [{'type':'image'}]); assert isinstance(w, list) and w[0] == {'type':'text','text':'cm'} and w[1] == {'type':'image'}; print('DISPATCH OK')" && grep -q '"image_count"' tests/agents/characterization/_normalize.py && test "$(grep -rcE 'pipeline_type ==|spec\.id ==' agents/execution_engine/engine.py)" -eq 0 && echo "INV-1 grep 0 OK"</automated>
  </verify>
  <done>
    - `ectx.compiled_input_providers` threaded beside :1671; `_compose_input_blocks(self, spec, ectx)` gates LOCALLY on `set(spec.injects) | set(ectx.current_step.injects)`, never reads `ectx.current_spec_injects`.
    - `_dispatch_payload`: bare str when `input_blocks` empty, `[text-block, *input_blocks]` when non-empty (verified above).
    - `_run_agent` computes a per-agent LOCAL `input_blocks`; dispatch (:2880) sends `_dispatch_payload(...)`; `agent_input.context_message` stays a str; `image_count` only-when->0; NO `ectx.pending_input_blocks`.
    - Runner hints widened to `str | list` on the 4 methods; `HumanMessage(content=...)` unchanged.
    - `"image_count"` in `_VOLATILE_STRIP_KEYS`; INV-1 grep stays 0.
    - Atomic commit (no trailer): `feat(engine): locally-gated _compose_input_blocks + multimodal dispatch wrap + runner str|list widening (260707-edw T1.6-T1.7)`.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 4: TDD suite — BLOCKER two-agent isolation + dispatch wrap + runner widening + HARD GATES</name>
  <files>backend/tests/agents/test_image_input_wiring.py</files>
  <read_first>
    backend/agents/execution_engine/engine.py (_compose_input_blocks + _dispatch_payload from Task 3; module-level _CAPABILITY_REGISTRY :406; the stale ectx.current_spec_injects assignment :5803)
    backend/agents/execution_engine/context.py (ExecutionContext ctor + run_images / current_step / compiled_input_providers dynamic attrs)
    backend/app/agents/deep_agent_runner.py (astream_events HumanMessage(content=user_message) :476)
    backend/tests/agents/_scripted_model.py (the minimal BaseChatModel scripted-model helper the runner tests use; RUNS_ROOT monkeypatch recipe — see backend/CLAUDE.md "Test recipe notes")
    backend/tests/agents/test_input_providers_run_images.py (Task-1 discover/clean-registry idiom to reuse)
  </read_first>
  <behavior>
    - (b) BLOCKER two-agent isolation: one ExecutionContext with run_images populated and compiled_input_providers=["run_images"]. Agent A (spec/step whose injects include "images"): await engine._compose_input_blocks(specA, ectx) -> non-empty shaped image blocks. THEN, WITHOUT resetting ectx, SET ectx.current_spec_injects = {"images"} (simulate the stale leak) and agent B (spec/step with NO image inject): await engine._compose_input_blocks(specB, ectx) -> [] (per-agent-local gate ignores the stale field).
    - (c) dispatch wrap: _dispatch_payload(cm, []) is the bare str cm; _dispatch_payload(cm, [block]) is [{"type":"text","text":cm}, block] (list, text-first).
    - (d) runner widening: DeepAgentRunner.astream_events driven with LIST content ([{"type":"text","text":"hi"}, {"type":"image",...}]) streams the scripted text without raising and builds HumanMessage(content=<list>); the text-only str case builds HumanMessage(content=<str>) and streams identically.
  </behavior>
  <action>
    Write `tests/agents/test_image_input_wiring.py` (RED first — the Task-3 wiring symbols must exist
    to pass).

    (b) BLOCKER (MANDATORY). Construct an `ExecutionContext` via its real ctor; set dynamic attrs
    `run_images=[{"mime_type":"image/png","data":"AA"}]` and
    `compiled_input_providers=["run_images"]`; ensure the `run_images` capability is discovered
    (`registry.discover()` or the Task-1 clean-registry idiom). Build a stub `specA` with
    `injects=["images"]` (and a matching `ectx.current_step` if the union arm is exercised) and a
    stub `specB` with `injects=[]` plus an `ectx.current_step` whose `injects=[]`. Instantiate
    `ExecutionEngine()`; `await engine._compose_input_blocks(specA, ectx)` -> assert a non-empty list
    of shaped `{"type":"image",...}` blocks. THEN set `ectx.current_spec_injects = {"images"}` (the
    stale-field simulation) WITHOUT changing anything else, and `await
    engine._compose_input_blocks(specB, ectx)` -> assert `== []`. Pins F1.

    (c) dispatch wrap: import `_dispatch_payload`; assert the empty->str and non-empty->text-first
    list contracts from `<behavior>`.

    (d) runner widening: build a `DeepAgentRunner` over a scripted model (reuse
    `tests/agents/_scripted_model.py` + monkeypatch `RUNS_ROOT` to `tmp_path`). Drive
    `astream_events([{"type":"text","text":"hi"}, {"type":"image","source_type":"base64",
    "mime_type":"image/png","data":"AA"}])` and assert it streams the scripted text without raising
    (list content flows through intact). Drive the text-only `astream_events("hi")` and assert
    identical streamed text. (If the scripted-model list driver is impractical, at minimum assert
    `HumanMessage(content=<list>)` and `HumanMessage(content=<str>)` both construct and carry
    `content` verbatim — the runner does no string ops on `user_message`.)

    HARD GATES — run and record in the SUMMARY (these ARE the Definition of Done):
    1. Goldens byte/event-identical, SNAPSHOT_UPDATE UNSET:
       `python3.11 -m pytest tests/agents/test_characterization_prototype.py
       tests/agents/test_characterization_od_prototype.py
       tests/agents/test_characterization_prototype_revision.py
       tests/agents/test_characterization_od_ppt.py
       tests/agents/test_characterization_app_builder.py -q` — the 4 non-od_ppt goldens fully green;
       `test_characterization_od_ppt.py::test_od_ppt_event_snapshot` is a PRE-EXISTING branch red and
       MUST fail IDENTICALLY before/after (prove by `git stash` on the working tree, run the od_ppt
       node, capture the failure, `git stash pop`, re-run, diff — same assertion). Also
       `python3.11 -m pytest tests/agents/test_context_message_oracle.py -q` green.
    2. `/opt/homebrew/bin/lint-imports` -> 4 kept / 0 broken.
    3. `python3.11 -m pytest tests/agents/test_registry_capabilities.py -q` green (count 63->65
       (reconciling the pre-existing KAN-73 audit_logger drift) + `_EXPECTED_NAMES`).
    4. New TDD suites green: `test_input_providers_run_images.py` (a) + `test_image_input_wiring.py`
       (b/c/d, incl. the BLOCKER).
    5. INV-1 grep: `grep -rnE 'pipeline_type ==|spec\.id ==' agents/execution_engine/engine.py` -> 0.
  </action>
  <verify>
    <automated>cd backend && python3.11 -m pytest tests/agents/test_image_input_wiring.py tests/agents/test_input_providers_run_images.py -q && python3.11 -m pytest tests/agents/test_characterization_prototype.py tests/agents/test_characterization_od_prototype.py tests/agents/test_characterization_prototype_revision.py tests/agents/test_characterization_app_builder.py tests/agents/test_context_message_oracle.py tests/agents/test_registry_capabilities.py -q</automated>
  </verify>
  <done>
    - `test_image_input_wiring.py` exists; the MANDATORY BLOCKER two-agent isolation test passes (agent B gets `[]` despite `ectx.current_spec_injects == {"images"}`); dispatch-wrap (c) + runner-widening (d) tests pass.
    - HARD GATE 1: 4 non-od_ppt goldens + oracle green with SNAPSHOT_UPDATE unset; od_ppt event-snapshot fails IDENTICALLY before/after (stash-diff evidence in SUMMARY).
    - HARD GATE 2: `/opt/homebrew/bin/lint-imports` -> 4 kept / 0 broken (in SUMMARY). HARD GATE 3: registry green. HARD GATE 5: INV-1 grep = 0.
    - Atomic commit (no trailer): `test(agents): image-input wiring TDD suite incl. BLOCKER two-agent isolation (260707-edw T1.6/T1.7)`.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| capability → engine (`ctx.run_images`) | The `run_images` capability reads run-supplied base64 image bytes off the per-run `ExecutionContext` — inbound user data, the SAME trust boundary as the existing text brief. |
| engine → agent dispatch | The composed content-list (text + image blocks) is handed to `create_deep_agent`'s runner; native to Converse/deepagents (Locked Decision #1) — no raw-byte plumbing in Flowin code. |

## STRIDE Threat Register (Wave-1 relevant)

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-edw-01 | Information Disclosure | `_compose_input_blocks` cross-agent leak (stale `ectx.current_spec_injects`) | mitigate | Gate derived LOCALLY per-agent from `spec.injects ∪ step.injects`; per-agent LOCAL `input_blocks`; NO shared `ectx.pending_input_blocks`; capability never reads `ctx.current_spec_injects` — pinned by the MANDATORY BLOCKER test (Task 4b). |
| T-edw-02 | Tampering | untrusted (user/db) manifest referencing a privileged input_provider | mitigate | Compiler `_check_trust("input_provider", ip, trusted, where)` mirrors the context_provider path; `run_images` is `user_allowed=True` (inbound user data, low risk). |
| T-edw-03 | Denial of Service | oversized / count / retry-payload amplification of base64 images | transfer (Wave 2/3) | Ingest caps (mime allow-list, per-image ≤3.75 MB, ≤20, per-run aggregate ≤~8 MB) + checkpointer/retry proof gate are Wave 2 (T2.3) / Wave 3 (T3.3), IMAGE-INPUT-PLAN §3/§12 F3 — DORMANT this wave (no image flows). |
| T-edw-04 | Info-disclosure via logs | base64 payload in events/logs | mitigate | `agent_input` carries only optional `image_count` (never bytes); `image_count` added to `_VOLATILE_STRIP_KEYS`; no base64 logged. |

No package-manager installs (no legitimacy gate needed). No `exec`/`network`/`secrets`/`spawn_subagents` — no `security` gate. No Alembic migration (transient carrier, Locked Decision #5 / Q3).
</threat_model>

<verification>
Run from `backend/` with `python3.11` (no venv); full pytest HANGS offline — use the TARGETED suite only.

1. Goldens (INV-3, SNAPSHOT_UPDATE UNSET): the 4 non-od_ppt characterization files + `test_context_message_oracle.py` fully green; `test_characterization_od_ppt.py::test_od_ppt_event_snapshot` fails IDENTICALLY before/after (git-stash diff evidence).
2. `/opt/homebrew/bin/lint-imports` -> 4 kept / 0 broken.
3. `tests/agents/test_registry_capabilities.py -q` green (len(_KNOWN) == 65, set(_KNOWN) == set(_EXPECTED_NAMES); T1.4 reconciles the pre-existing KAN-73 hook:audit_logger drift into _EXPECTED_NAMES).
4. New TDD suites green: `test_input_providers_run_images.py` + `test_image_input_wiring.py` (incl. the MANDATORY BLOCKER two-agent isolation).
5. INV-1: `grep -rnE 'pipeline_type ==|spec\.id ==' agents/execution_engine/engine.py` -> 0 (no regression).

NEGATIVE SPACE (must hold): NO `input_providers:` on any `workflow.yaml`; NO `injects:[images]` on any AGENT.md; the `prototype_revision` golden + its pinned context bytes UNTOUCHED; NO shared `ectx.pending_input_blocks`; NO new WS event; NO Alembic migration; NO `ARTIFACT_KINDS` edit; NO new `create_deep_agent` (INV-13); import-linter stays 4/0. NO commit trailer. NEVER push, never main.
</verification>

<success_criteria>
- The DORMANT backend spine exists end-to-end: carrier (`ExecutionContext.run_images`) → capability (`run_images` `input_provider`) → declaration surface (manifest/compiler/plan `input_providers`) → engine wiring (`_compose_input_blocks`, locally gated) → transport (`_dispatch_payload` wrap) → runner (`str | list`).
- All 5 characterization goldens byte/event-identical with SNAPSHOT_UPDATE unset (4 green + od_ppt identical pre-existing red); oracle green.
- `lint-imports` 4/0; registry drift-guard green (65); INV-1 grep 0.
- The MANDATORY BLOCKER two-agent isolation test passes: agent B gets `[]` even with `ectx.current_spec_injects == {"images"}`.
- Every task committed atomically with NO commit trailer; branch `new-workflow-engine`; nothing pushed.
</success_criteria>

<output>
Create `.planning/quick/260707-edw-image-input-wave-1-backend-carrier-input/260707-edw-SUMMARY.md` when done, recording: the HARD-GATE evidence (goldens result + the od_ppt stash-diff proof, lint-imports 4/0, registry 65 incl. the KAN-73 audit_logger reconcile, INV-1 grep 0), the atomic commit SHAs, and confirmation the feature is DORMANT (no manifest/AGENT.md opt-in this wave). Update `.planning/IMPLEMENTATION-REGISTER.md` per convention (image-input Wave 1 pointer entry).
</output>
