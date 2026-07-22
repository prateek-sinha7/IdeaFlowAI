---
phase: 260707-frv
plan: 01
type: execute
wave: 1
depends_on: []
autonomous: true
requirements: [T2.1, T2.2, T2.3, T2.4]
files_modified:
  - backend/agents/capabilities/model_catalog.py
  - backend/app/core/config.py
  - backend/app/api/websocket.py
  - backend/tests/agents/test_model_catalog.py
  - backend/tests/unit/test_image_ingress_validation.py
  - backend/tests/unit/test_image_ws_ingress.py
  - frontend/src/components/workflow/IdeaInputPage.tsx
  - frontend/src/components/workflow/IdeaInputPage.imageInput.test.tsx
  - frontend/src/hooks/useWorkflow.imagePayload.test.ts
  - frontend/src/app/workflow/ppt/templates/page.tsx
  - frontend/src/app/workflow/prototype/templates/page.tsx
  - frontend/src/app/dashboard/page.tsx
  - frontend/src/components/layout/DashboardLayout.tsx

must_haves:
  truths:
    - "A run_pipeline WS message carrying `images` reaches engine.execute(images=...) -> ExecutionContext.run_images (Wave-1 carrier)."
    - "A run_pipeline with images has WorkflowRun.input == the text brief only — NO base64 ever enters run.input (Phase 25 D3)."
    - "An image set violating a cap (bad mime, oversized single, >20 count, aggregate over ~8 MB) is REJECTED at ingress with code invalid_image_input — never silently dropped."
    - "IMAGE_INPUT_ENABLED=False -> images are not passed to execute (clean off-switch); the run still proceeds as text-only."
    - "Image input is rejected when the effective run-level model is not a vision-capable catalog entry (raw-config escape hatch closed)."
    - "The FE image picker captures images into attachedImages and ships them out-of-band as the `images` payload field; the brief text NEVER contains base64."
    - "The 5 characterization goldens stay byte/event-identical — the feature is DORMANT at the agent level (no injects:[images] on any AGENT.md, no input_providers: on any manifest)."
  artifacts:
    - path: "backend/agents/capabilities/model_catalog.py"
      provides: "ModelEntry.vision: bool field + vision=True on all 5 catalog entries"
      contains: "vision"
    - path: "backend/app/core/config.py"
      provides: "IMAGE_INPUT_ENABLED feature flag (default True)"
      contains: "IMAGE_INPUT_ENABLED"
    - path: "backend/app/api/websocket.py"
      provides: "_validate_images ingress caps + vision guard (error code invalid_image_input); images ingress param on run_pipeline -> _handle_workflow_execution -> engine.execute(images=)"
      contains: "_validate_images"
    - path: "frontend/src/components/workflow/IdeaInputPage.tsx"
      provides: "attachedImages state + isImageFile capture branch + image chips + images extraParams"
      contains: "attachedImages"
  key_links:
    - from: "backend/app/api/websocket.py (run_pipeline handler)"
      to: "_handle_workflow_execution(images=) -> _validate_images -> engine.execute(images=)"
      via: "message_data.get('images')"
      pattern: "images=validated_images"
    - from: "frontend/src/components/workflow/IdeaInputPage.tsx"
      to: "run_pipeline payload"
      via: "extraParams.images -> useWorkflow Object.assign(payload, context)"
      pattern: "images"
    - from: "backend/app/api/websocket.py (_validate_images vision guard)"
      to: "ModelCatalog().get(id).vision"
      via: "effective run-level model resolution"
      pattern: "vision"
---

<objective>
Image Input Wave 2 — wire the FE to capture images and the WS to carry them into the
Wave-1 carrier (`execute(images=)` -> `ExecutionContext.run_images`), with ingest caps, a
feature flag, and a run-level vision guard.

The feature STAYS DORMANT at the agent level: no workflow declares `input_providers:`
and no AGENT.md declares `injects:[images]` (that is Wave 3). Even though images now flow
to `ectx.run_images`, `_compose_input_blocks` returns `[]` for every agent => no image
reaches any model => the 5 characterization goldens stay byte-identical. Images are carried
TRANSIENTLY as base64 inside the existing `run_pipeline` WS payload — no HTTP upload
endpoint, no persistence, no new WS event type, no Alembic migration.

Purpose: close the ingress half of the image-input design (IMAGE-INPUT-PLAN §3 Layer 1 +
Layer 5, §4 Wave 2, §12 F3 aggregate cap) so a later Wave-3 opt-in has a fed carrier.
Output: `ModelEntry.vision`, `IMAGE_INPUT_ENABLED`, `_validate_images` (+ `invalid_image_input`
error code), the WS `images` ingress param, and the FE `attachedImages` state + `images`
payload field.
</objective>

<context>
@.planning/IMAGE-INPUT-PLAN.md
@.planning/quick/260707-edw-image-input-wave-1-backend-carrier-input/260707-edw-SUMMARY.md
@backend/app/api/websocket.py
@backend/agents/capabilities/model_catalog.py
@backend/app/core/config.py
@frontend/src/components/workflow/IdeaInputPage.tsx
@frontend/src/hooks/useWorkflow.ts
@frontend/src/components/layout/DashboardLayout.tsx
</context>

## Artifacts this phase produces (MANDATORY — do not omit any)

| Artifact | File | Task |
|----------|------|------|
| `ModelEntry.vision: bool` field (+ `vision=True` on all 5 entries) | `backend/agents/capabilities/model_catalog.py` | 1 |
| `IMAGE_INPUT_ENABLED: bool = True` setting | `backend/app/core/config.py` | 1 |
| `_validate_images(...)` helper + `invalid_image_input` error code | `backend/app/api/websocket.py` | 1 -> 2 |
| WS `images` ingress param (handler -> `_handle_workflow_execution` -> `engine.execute(images=)`) | `backend/app/api/websocket.py` | 2 |
| FE `attachedImages` state + `images` payload field | `IdeaInputPage.tsx` (+ 2 sibling pickers) | 3, 4 |

## NEGATIVE SPACE (must remain absent)

- NO `input_providers:` on any `agents/workflows/*/workflow.yaml`; NO `injects:[images]` on
  any `agents/prompts/*/AGENT.md` (that is Wave 3 — the feature is DORMANT at the agent level).
- Base64 image data NEVER in `WorkflowRun.input` / `pipeline_content` / the brief text (D3).
- NO new WS event type — images ride the existing `run_pipeline` message (D5).
- NO Alembic migration (transient carrier), NO new table/column.
- NO new model-id literal in `app/api` or `agents/capabilities` (keep `test_single_source_grep` green).
- NO commit trailer. NEVER push. NEVER main. Branch stays `new-workflow-engine`.

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: ModelEntry.vision + IMAGE_INPUT_ENABLED config + _validate_images helper (+ unit tests)</name>
  <files>backend/agents/capabilities/model_catalog.py, backend/app/core/config.py, backend/app/api/websocket.py, backend/tests/agents/test_model_catalog.py, backend/tests/unit/test_image_ingress_validation.py</files>
  <read_first>
    - backend/agents/capabilities/model_catalog.py (ModelEntry dataclass :47-59; the 5 entries :68-128; note `pricing` is the last no-default field and every entry uses keyword construction; ModelEntry is constructed ONLY here — grep confirmed no other call site).
    - backend/app/core/config.py:104-134 (the `BEDROCK_PROMPT_CACHE_ENABLED: bool = True` block to mirror; `BRIEF_MAX_CHARS`).
    - backend/app/api/websocket.py:107-167 (`_validate_model_overrides` — the str|None return contract + lazy `from agents.capabilities.model_catalog import ModelCatalog` import + type guards to mirror).
    - backend/tests/agents/test_model_catalog.py (`_FIELDS` set :33-42, `test_catalog_lists_five_fully_fielded_entries` :48-58, `test_single_source_grep` :163-181 — the grep scans `app/api` + `agents/capabilities` for `claude-(haiku|sonnet|opus)-4`; adding a bool field adds NO literal).
    - backend/tests/unit/test_run_pipeline_validation.py:521-546 (the `from app.api.websocket import _validate_model_overrides` unit-test import pattern to mirror for `_validate_images`).
  </read_first>
  <behavior>
    - `_validate_images([], effective_model_ids=...)` -> None (empty is a no-op, like _validate_model_overrides({})).
    - Non-dict image entry, or entry missing `mime_type`/`data`, or non-string mime/data -> returns an error string (reject).
    - mime not in {image/png, image/jpeg, image/webp, image/gif} -> reject naming the bad mime.
    - single image whose estimated raw bytes (`len(data)*3//4`) > 3.75*1024*1024 -> reject.
    - count > 20 -> reject.
    - aggregate estimated raw bytes across all images > 8*1024*1024 -> reject even when each individual image is under the per-image cap.
    - a fully valid set (<=20 images, valid mimes, under both caps) with a vision-capable `effective_model_ids` -> None.
    - vision guard: any id in `effective_model_ids` where `ModelCatalog().get(id)` is None OR `.vision` is False -> reject (raw-config / non-vision model). All ids present in the catalog with `vision=True` -> None.
    - ModelEntry gains `vision: bool`; all 5 catalog entries carry `vision=True`.
  </behavior>
  <action>
    In `model_catalog.py`: add a `vision: bool` field to the `ModelEntry` dataclass (:47-59),
    placed after `pricing`. Set `vision=True` on ALL 5 entries (:68-128) — every Claude
    4.5/4.6 model is vision-capable. Add a one-line comment that vision-capability gates
    image input at ingress (IMAGE-INPUT §3 Layer 5). Do NOT add any new model-id literal.
    Extend `test_model_catalog.py`: add `"vision"` to the `_FIELDS` set (:33-42) and assert in
    `test_catalog_lists_five_fully_fielded_entries` that every entry has `entry.vision is True`.

    In `config.py`: add `IMAGE_INPUT_ENABLED: bool = True` immediately after the
    `BEDROCK_PROMPT_CACHE_ENABLED`/`BEDROCK_PROMPT_CACHE_TTL` block (:110-111), with a
    docstring comment mirroring that block — feature flag for image-input ingress; when
    False the WS ingress ignores any `images` on the run_pipeline payload (clean off-switch).

    In `websocket.py`: add module-level cap constants near the other module constants —
    `_IMAGE_ALLOWED_MIMES = frozenset({"image/png", "image/jpeg", "image/webp", "image/gif"})`,
    `_IMAGE_MAX_BYTES_PER_IMAGE = int(3.75 * 1024 * 1024)`, `_IMAGE_MAX_COUNT = 20`,
    `_IMAGE_MAX_AGGREGATE_BYTES = 8 * 1024 * 1024`. Add a `_validate_images(images, *, effective_model_ids=None) -> str | None`
    helper modeled on `_validate_model_overrides` (:107-167): same str|None contract; lazy
    `from agents.capabilities.model_catalog import ModelCatalog` for the vision guard (app->kernel,
    import-clean). Enforce, in order: `images` must be a list (else reject); each entry a dict
    with string `mime_type` + string `data` (reject malformed — mirror the CR-01 type guard);
    mime in `_IMAGE_ALLOWED_MIMES`; per-image estimated raw bytes `len(data)*3//4 <= _IMAGE_MAX_BYTES_PER_IMAGE`;
    `len(images) <= _IMAGE_MAX_COUNT`; running aggregate raw bytes `<= _IMAGE_MAX_AGGREGATE_BYTES`
    (IMAGE-INPUT §12 F3 — the multimodal HumanMessage is checkpointed + re-sent on model-fallback
    retry). THEN the vision guard: when `effective_model_ids` is provided, for each id
    `entry = ModelCatalog().get(id)`; reject when `entry is None or not entry.vision` (closes the
    raw-config escape hatch). Return a human-readable message on the FIRST violation, else None.
    The caller (Task 2) emits `code="invalid_image_input"`. Do NOT wire the helper into the
    run path yet — that is Task 2.

    Create `backend/tests/unit/test_image_ingress_validation.py` importing
    `from app.api.websocket import _validate_images` (mirror the `_validate_model_overrides`
    import pattern). Cover every bullet in <behavior> above: empty->None; malformed dict; bad mime;
    oversized single; >20 count; aggregate-over-cap; valid set->None; vision-guard reject (a
    non-catalog id and a hypothetical vision=False id) and accept (a real catalog id, e.g.
    `eu.anthropic.claude-haiku-4-5-20251001-v1:0`, which is vision=True). Test-file model-id
    literals are fine — `tests/` is NOT scanned by `test_single_source_grep`.
  </action>
  <acceptance_criteria>
    - `python3.11 -m pytest tests/agents/test_model_catalog.py -q` GREEN incl. `test_single_source_grep` (no new model-id literal) and the extended field/vision assertions.
    - `python3.11 -m pytest tests/unit/test_image_ingress_validation.py -q` GREEN — every <behavior> bullet asserted (RED first if run before the helper exists, then GREEN).
    - `_validate_images` returns None for `[]`; returns a non-empty error string for each of: bad mime, oversized single (raw>3.75 MB), >20 images, aggregate>8 MB, a non-vision/non-catalog `effective_model_ids`.
    - `settings.IMAGE_INPUT_ENABLED is True` by default.
    - `ModelCatalog().get("eu.anthropic.claude-haiku-4-5-20251001-v1:0").vision is True` and all 5 entries `.vision is True`.
  </acceptance_criteria>
  <verify>
    <automated>cd backend && python3.11 -m pytest tests/agents/test_model_catalog.py tests/unit/test_image_ingress_validation.py -q</automated>
  </verify>
  <done>ModelEntry.vision (all 5 True), IMAGE_INPUT_ENABLED config, and _validate_images (caps + vision guard) exist with green unit tests; no new model-id literal; not yet wired into the run path.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: WS run_pipeline images ingress -> engine.execute(images=) with flag/caps/vision guard + D3 (+ integration tests)</name>
  <files>backend/app/api/websocket.py, backend/tests/unit/test_image_ws_ingress.py</files>
  <read_first>
    - backend/app/api/websocket.py:710-733 (the run_pipeline handler client-field reads — `pipeline_content` :711, `selections` :733 as the mirror for reading `images`).
    - backend/app/api/websocket.py:756-773 (the `_handle_workflow_execution(...)` call site — thread the new `images` arg here beside `selections`).
    - backend/app/api/websocket.py:1493-1513 (`_handle_workflow_execution` signature — add `images: list | None = None` param).
    - backend/app/api/websocket.py:1670-1704 (the `_validate_model_overrides` ingress block + selections re-validation — place the image-flag+validation block right after, before WorkflowRun creation; reuse the `{spec.id for spec in agents}` resolved agent set already in scope).
    - backend/app/api/websocket.py:1734-1756 (`WorkflowRun(... input=content ...)` — D3: images must NEVER touch `input`/`content`/`title`).
    - backend/app/api/websocket.py:1828-1856 (the `engine.execute(...)` call inside `_run_pipeline_to_queue` — add `images=validated_images` beside `od_context=od_context` :1845; `model_id=getattr(user,"preferred_model",None)` :1844 is the session model).
    - backend/agents/execution_engine/engine.py:799-855 (execute already accepts `images: list | None = None` :812 — Wave-1 carrier; :1018 `run_images=_normalize_run_images(images)`).
    - backend/tests/unit/test_ws_parent_link_ownership.py:64-161 (the offline WS harness — `_FakeWebSocket`, `monkeypatch.setattr(engine_mod, "get_execution_engine", ...)`, in-memory SQLite `_get_db`, `_seed_user`) to reuse for the integration tests.
  </read_first>
  <behavior>
    - A run_pipeline whose payload carries a valid `images` list (flag ON) -> `engine.execute` is called with `images=[{mime_type,data}, ...]` (the exact list forwarded).
    - The created `WorkflowRun.input` equals the text brief ONLY — no base64 substring anywhere in `input`/`title` (D3).
    - With `IMAGE_INPUT_ENABLED=False`, a run_pipeline carrying images -> `engine.execute` is called with `images=[]` (images ignored, run still proceeds as text-only).
    - An image set that violates a cap -> the handler emits a `{"type":"error", data:{code:"invalid_image_input"}}` event and does NOT call `engine.execute` / does NOT create a WorkflowRun.
    - Images + a non-vision effective run-level model (session `preferred_model`, or a `model_overrides` value, or a raw `BEDROCK_INFERENCE_PROFILE_ID` not in the catalog) -> rejected with `invalid_image_input`, no execute call.
    - A run_pipeline with NO images -> byte-identical to today (execute called with `images=[]`, no new behavior).
  </behavior>
  <action>
    In the run_pipeline handler, after :733, read `images = message_data.get("images") or []`
    (mirror the `selections` read) and thread it into the `_handle_workflow_execution(...)`
    call (:757-772) as `images=images`. Add `images: list | None = None` to the
    `_handle_workflow_execution` signature (:1493-1513, beside `selections`).

    Inside `_handle_workflow_execution`, immediately AFTER the `_validate_model_overrides`
    ingress block (ends :1687) and BEFORE WorkflowRun creation (:1734), add the image ingress
    gate: normalize `images = images or []`; set `validated_images: list = []`; then
    `if settings.IMAGE_INPUT_ENABLED and images:` compute the effective run-level model id set —
    `base_model = getattr(user, "preferred_model", None) or settings.BEDROCK_INFERENCE_PROFILE_ID`;
    `effective_model_ids = {base_model} | {m for m in model_overrides.values() if isinstance(m, str)}`
    — then `err = _validate_images(images, effective_model_ids=effective_model_ids)`; on non-None
    `err` send `{"type":"error","chunk":None,"section":None,"data":{"error":err,"code":"invalid_image_input","recoverable":False}}`
    and `return` (no WorkflowRun, no execute — mirror the model_overrides rejection at :1681-1687);
    else `validated_images = images`. When the flag is OFF, `validated_images` stays `[]`
    (clean off-switch) — do NOT reject, just ignore. Add a comment that when the flag is off or
    no images are supplied the run is byte-identical to today.

    At the `engine.execute(...)` call (:1828-1856) add `images=validated_images` beside
    `od_context=od_context` (:1845). Do NOT touch `content`, `WorkflowRun.input` (:1743),
    `title` (:1740), or `_generate_workflow_title` — base64 must never enter any of them (D3).
    No new WS event type (D5). No Alembic migration.

    Create `backend/tests/unit/test_image_ws_ingress.py` reusing the offline WS harness from
    `test_ws_parent_link_ownership.py` (fake websocket, stubbed `get_execution_engine` whose
    `async def execute(self, **kwargs)` records `kwargs` and yields one `pipeline_complete`,
    in-memory SQLite `_get_db`, seeded user, a real base pipeline_type such as `user_stories`).
    Assert: (a) a valid `images` list reaches the recorded `execute` kwargs as `images=[...]`;
    (b) the persisted `WorkflowRun.input` contains the brief and NO base64 substring (D3);
    (c) with `monkeypatch.setattr(ws_module.settings, "IMAGE_INPUT_ENABLED", False)` the recorded
    `execute` kwargs carry `images=[]`; (d) a rejecting image set (bad mime OR a non-vision
    effective model) produces an `invalid_image_input` error event on the fake websocket and the
    stub `execute` is never called.
  </action>
  <acceptance_criteria>
    - `python3.11 -m pytest tests/unit/test_image_ws_ingress.py -q` GREEN — all four assertions (images-reach-execute, D3, flag-off, reject-no-execute).
    - `grep -nE 'images=validated_images' backend/app/api/websocket.py` matches the engine.execute call; grep shows NO base64/images assignment into `WorkflowRun(...)` / `content` / `title`.
    - A no-images run_pipeline path is unchanged (execute receives `images=[]`).
    - 5 characterization goldens + oracle byte/event-identical (SNAPSHOT_UPDATE unset) — Wave 2 does not touch the golden `execute()` path.
    - `/opt/homebrew/bin/lint-imports` -> 4 kept / 0 broken.
    - `test_registry_capabilities.py` GREEN (drift-guard 65 unchanged — Wave 2 adds no capability).
  </acceptance_criteria>
  <verify>
    <automated>cd backend && python3.11 -m pytest tests/unit/test_image_ws_ingress.py tests/agents/test_characterization_prototype.py tests/agents/test_characterization_od_prototype.py tests/agents/test_characterization_prototype_revision.py tests/agents/test_characterization_od_ppt.py tests/agents/test_characterization_app_builder.py tests/agents/test_context_message_oracle.py tests/agents/test_registry_capabilities.py -q && /opt/homebrew/bin/lint-imports</automated>
  </verify>
  <done>run_pipeline images reach engine.execute(images=); WorkflowRun.input stays text-only (D3); flag-off ignores images; caps + vision guard reject with invalid_image_input; goldens byte-identical; lint-imports 4/0.</done>
</task>

<task type="auto">
  <name>Task 3: FE canonical image capture in IdeaInputPage + ship `images` via extraParams (+ vitest)</name>
  <files>frontend/src/components/workflow/IdeaInputPage.tsx, frontend/src/components/workflow/IdeaInputPage.imageInput.test.tsx, frontend/src/hooks/useWorkflow.imagePayload.test.ts</files>
  <read_first>
    - frontend/src/components/workflow/IdeaInputPage.tsx:190-193 (`attachedFiles` + `attachedFileContents` useState — add the new `attachedImages` state beside them); :341-376 (`handleRun`: the `=== Attached ===` brief compose :347-350 that images must NEVER enter; the `extraParams` build :367-375 + guard :368); :512-530 (attachment chip row to mirror); :536-591 (hidden file input `accept` :540 + `onChange` isTextFile/isBinaryFile branches :551-587).
    - frontend/src/hooks/useWorkflow.ts:38-108 (`startPipeline` — the `context` arg + `Object.assign(payload, context)` :104 that lands `images` in the run_pipeline payload); no signature change needed.
    - frontend/src/lib/constants.ts (`ATTACH_MAX_CHARS = 450000` — the cap that forces D3: images out-of-band, never inlined).
    - frontend/src/components/workflow/IdeaInputPage.modelOverrides.test.tsx (the vitest harness pattern — mock AgentsPopup/ReviewGatesSection/useSpeechRecognition, render with SkillsHooksProvider, assert `onRun.mock.calls[0]` extraParams).
  </read_first>
  <action>
    Add `const [attachedImages, setAttachedImages] = useState<{ name: string; mime_type: string; data: string }[]>([]);`
    beside `attachedFiles` (:190-193). In the picker `accept` (:540) append the 4 image mimes
    `image/png,image/jpeg,image/webp,image/gif`. In the `onChange` (:542-591) add an
    `isImageFile` branch — detect via `f.type` in the 4-mime allow-list (fallback filename
    `/\.(png|jpe?g|webp|gif)$/i`). For an image: read via `new FileReader().readAsDataURL(f)`;
    in `reader.onload` strip the `data:<mime>;base64,` prefix (`result.split(",")[1]` /
    `result.replace(/^data:[^;]+;base64,/, "")`) and `setAttachedImages((p) => [...p, { name: f.name, mime_type: f.type, data: <rawBase64> }])`.
    It MUST NOT call `setAttachedFileContents` and MUST NOT touch `setAttachedFiles`' text path —
    images must NEVER enter `attachedFileContents` (which is inlined into the brief at :347-350;
    one ~340KB image base64 ~= the whole ATTACH_MAX_CHARS cap). Render an image chip row like the
    `attachedFiles` chips (:512-530) driven by `attachedImages`, with a remove button that filters
    `attachedImages` by index — but do NOT inline the base64 anywhere in the brief text.
    In `handleRun` (:341-376): add `const hasImages = attachedImages.length > 0;`, include
    `...(hasImages ? { images: attachedImages } : {})` in the `extraParams` object (:369-373), and
    extend the guard (:368) to `touched || hasOverrides || hasSelections || hasImages` so an
    image-only run still ships `extraParams`. `finalMessage` (:350) is UNCHANGED — brief text only.

    Create `IdeaInputPage.imageInput.test.tsx` (mirror `IdeaInputPage.modelOverrides.test.tsx`):
    type a brief, upload a small image File to the hidden file input (mime image/png), `await`
    the async FileReader (waitFor the image chip / attachedImages), click Run, and assert
    `onRun.mock.calls[0]` -> `message === "<typed brief>"` (NO base64 substring) AND
    `extraParams.images` equals `[{ name, mime_type: "image/png", data: <base64> }]`. Add a
    second spec: no image + nothing touched -> `extraParams` is undefined (byte-identical, INV-3).

    Create `useWorkflow.imagePayload.test.ts` (mirror the existing useWorkflow specs): call
    `startPipeline("prototype", "brief", ["a"], undefined, undefined, { images: [{ name:"x.png", mime_type:"image/png", data:"AAAA" }] })`
    with a mock `websocketSend`; parse the sent JSON and assert `payload.images` equals that list
    AND `payload.message === "brief"` (proves the `Object.assign(payload, context)` merge lands
    `images` and the brief carries no base64). A no-context call sends no `images` key.
  </action>
  <acceptance_criteria>
    - `cd frontend && npx vitest run src/components/workflow/IdeaInputPage.imageInput.test.tsx src/hooks/useWorkflow.imagePayload.test.ts` GREEN.
    - The image-capture spec proves: `attachedImages` populated, `extraParams.images` shipped, and the Run `message` contains NO base64 (D3).
    - `cd frontend && npx tsc --noEmit` -> NO NEW errors vs the known pre-existing `e2e/fixtures/mockApi.ts` errors (verify by identity of the error list, not absolute count).
    - grep of IdeaInputPage.tsx shows the `isImageFile` branch calls `setAttachedImages` and NEVER `setAttachedFileContents`.
  </acceptance_criteria>
  <verify>
    <automated>cd frontend && npx vitest run src/components/workflow/IdeaInputPage.imageInput.test.tsx src/hooks/useWorkflow.imagePayload.test.ts && npx tsc --noEmit</automated>
  </verify>
  <done>IdeaInputPage captures images into attachedImages (never the brief), ships them as `images` via extraParams, and useWorkflow merges them into the run_pipeline payload; vitest + tsc-identity green.</done>
</task>

<task type="auto">
  <name>Task 4: FE sibling pickers (ppt + prototype templates) image capture + draft/dashboard threading</name>
  <files>frontend/src/app/workflow/ppt/templates/page.tsx, frontend/src/app/workflow/prototype/templates/page.tsx, frontend/src/app/dashboard/page.tsx, frontend/src/components/layout/DashboardLayout.tsx</files>
  <read_first>
    - frontend/src/app/workflow/ppt/templates/page.tsx:36-38 (`attachedFiles`/`attachedFileContents` state); :438 (picker `accept`) + :440-479 (`onChange` isTextFile/isBinaryFile — mirror the IdeaInputPage isImageFile branch from Task 3); :282-285 (`fileBlocks` brief compose — images must NOT enter it); :294-305 (the `sessionStorage.setItem(STORAGE_KEY, JSON.stringify({...}))` draft where `modelOverrides`/`selections` are stashed conditionally — add `images` the same way).
    - frontend/src/app/workflow/prototype/templates/page.tsx:42-44 (state); :473 (picker `accept`) + :309-310 (fileBlocks) + the analogous draft `sessionStorage.setItem` block.
    - frontend/src/app/dashboard/page.tsx:146-156 + :86-99 (the pending-param state type shapes) and :182-205 + :216-236 + :817-846 + :888+ (the `JSON.parse(...draft)` readers that build `pendingOdProtoParams`/`pendingOdPptParams` — thread `images` from draft into the pending params, mirroring `modelOverrides`).
    - frontend/src/components/layout/DashboardLayout.tsx:114-130 (the two `pendingOdProtoParams`/`pendingOdPptParams` prop type shapes — add `images?: { name: string; mime_type: string; data: string }[]`); :673-688 + :721-735 (the two `extraParams` builders — add `...(pending.images && pending.images.length > 0 ? { images: pending.images } : {})` mirroring the `modelOverrides` conditional at :686/:733).
  </read_first>
  <action>
    In BOTH `ppt/templates/page.tsx` and `prototype/templates/page.tsx`: add an `attachedImages`
    state `{ name; mime_type; data }[]` beside `attachedFiles`; append the 4 image mimes
    (`image/png,image/jpeg,image/webp,image/gif`) to the picker `accept`; add the same
    `isImageFile` capture branch as Task 3 (readAsDataURL -> strip prefix -> setAttachedImages),
    NEVER touching `setAttachedFileContents` (so the `fileBlocks` brief compose stays base64-free —
    D3); render an `attachedImages` chip row with per-index remove. In each page's draft
    `sessionStorage.setItem(...draft...)` object add `...(attachedImages.length > 0 ? { images: attachedImages } : {})`
    beside the existing conditional `modelOverrides`/`selections` stash.

    In `dashboard/page.tsx`: add `images?: { name: string; mime_type: string; data: string }[]` to the
    `pendingOdProtoParams`/`pendingOdPptParams` state type shapes and the draft-typed shapes; in each
    `JSON.parse(...draft)` reader that builds the pending params, carry `images: draft.images` (beside
    `modelOverrides: draft.modelOverrides`).

    In `DashboardLayout.tsx`: add the `images?` field to the two pending-param prop type shapes
    (:114-130); in each `extraParams` builder (:673-688 proto, :721-735 ppt) add
    `...(pendingOdProtoParams.images && pendingOdProtoParams.images.length > 0 ? { images: pendingOdProtoParams.images } : {})`
    (and the ppt analogue) so images ride the existing `onStartPipeline(..., extraParams)` ->
    `useWorkflow.startPipeline` -> `Object.assign(payload, context)` merge into the run_pipeline
    payload. No new prop, no new event, no brief inlining.
  </action>
  <acceptance_criteria>
    - `cd frontend && npx tsc --noEmit` -> NO NEW errors vs the known pre-existing `e2e/fixtures/mockApi.ts` errors (identity check).
    - grep of both `templates/page.tsx` shows the `isImageFile` branch calls `setAttachedImages` and NEVER `setAttachedFileContents`; the draft `setItem` stashes `images` only when `attachedImages.length > 0`.
    - grep of `DashboardLayout.tsx` shows `images` merged into BOTH the proto and ppt `extraParams` builders, guarded on `.length > 0` (byte-identical payload when empty).
    - `cd frontend && npx vitest run` for any existing DashboardLayout specs stays GREEN (no regression).
  </acceptance_criteria>
  <verify>
    <automated>cd frontend && npx tsc --noEmit && npx vitest run src/components/layout</automated>
  </verify>
  <done>Both sibling template pickers capture images (never the brief) and stash them in their draft; dashboard + DashboardLayout thread `images` into extraParams so they ride the run_pipeline payload; tsc-identity + DashboardLayout vitest green.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| browser -> WS `run_pipeline` | Untrusted base64 image bytes + declared mime cross here into the run payload. |
| WS ingress -> engine.execute | `_validate_images` is the chokepoint; only a validated list crosses into `ExecutionContext.run_images`. |
| run payload -> model dispatch | Images stay dormant (no `injects:[images]`) — they reach `ectx.run_images` but no `_compose_input_blocks` gate fires this wave. |

## STRIDE Threat Register (IMAGE-INPUT §6)

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-frv-01 | Denial of Service | oversized / count / decompression flood via `images` | mitigate | `_validate_images` caps: mime allow-list {png,jpeg,webp,gif}, per-image raw <= 3.75 MB, <= 20 images, aggregate raw <= 8 MB (§12 F3 — checkpointed + retry-amplified HumanMessage). Reject with `invalid_image_input`. |
| T-frv-02 | Tampering | smuggling a non-vision / non-catalog model to bypass vision safety | mitigate | vision guard in `_validate_images`: reject unless every effective run-level model id is a `ModelCatalog` entry with `vision=True`; `IMAGE_INPUT_ENABLED` off-switch. |
| T-frv-03 | Information Disclosure | base64 leaking into `run.input` / logs / history | mitigate | D3 — images never enter `content`/`WorkflowRun.input`/`title`/brief; forced by `ATTACH_MAX_CHARS=BRIEF_MAX_CHARS`; no base64 logged. |
| T-frv-04 | Elevation of Privilege | image content used as a new injection privilege | accept | Same trust boundary as the existing untrusted text brief; no new capability, `user_allowed=True`, no exec/network/secrets/spawn. |
| T-frv-05 | Information Disclosure | cross-owner / IDOR image read | accept | v1 transient — image lives only in the caller's own authenticated run payload; no cross-run read introduced (persistence deferred, would reuse ArtifactRef scoping). |

No npm/pip/cargo installs in this plan -> Package Legitimacy Gate not applicable.
</threat_model>

<verification>
Run the full HARD-GATE sweep after Task 4:

1. Backend goldens (SNAPSHOT_UPDATE unset) + registry + catalog:
   `cd backend && python3.11 -m pytest tests/agents/test_characterization_prototype.py tests/agents/test_characterization_od_prototype.py tests/agents/test_characterization_prototype_revision.py tests/agents/test_characterization_od_ppt.py tests/agents/test_characterization_app_builder.py tests/agents/test_context_message_oracle.py tests/agents/test_model_catalog.py tests/agents/test_registry_capabilities.py -q`
   Expect: byte/event-identical goldens; `test_single_source_grep` green; drift-guard 65 unchanged.
2. Backend new suites: `cd backend && python3.11 -m pytest tests/unit/test_image_ingress_validation.py tests/unit/test_image_ws_ingress.py -q`.
3. Import contract: `/opt/homebrew/bin/lint-imports` -> 4 kept / 0 broken.
4. FE: `cd frontend && npx tsc --noEmit` (NO NEW errors vs the pre-existing e2e/fixtures/mockApi.ts set — identity check) and `npx vitest run src/components/workflow/IdeaInputPage.imageInput.test.tsx src/hooks/useWorkflow.imagePayload.test.ts src/components/layout`.
5. DORMANT / NEGATIVE-SPACE greps:
   - `grep -rn 'input_providers:' backend/agents/workflows` -> NONE.
   - `grep -rn 'injects:.*images' backend/agents/prompts` -> NONE.
   - No new Alembic file in `backend/alembic/versions` (head stays 0023).
   - `grep -nE 'images=validated_images' backend/app/api/websocket.py` matches only the engine.execute call; no `images`/base64 into `WorkflowRun(...)`.

Pre-existing branch reds to leave UNTOUCHED (proven in Wave 1, do NOT claim to fix):
`test_manifest_parity::test_clarify_defaults_match_engine[*]` (7) + `test_manifest::test_display_name_*` (2).
</verification>

<success_criteria>
- `ModelEntry.vision` exists with `vision=True` on all 5 catalog entries; `test_single_source_grep` green (no new model-id literal).
- `IMAGE_INPUT_ENABLED` defaults True; when False, ingress passes `images=[]` to execute.
- `_validate_images` enforces mime allow-list + per-image (<=3.75 MB) + count (<=20) + aggregate (<=8 MB) caps and the vision guard, returning `invalid_image_input` on violation (never a silent drop).
- A `run_pipeline` carrying valid images reaches `engine.execute(images=...)`; `WorkflowRun.input` stays the text brief only (D3).
- FE `IdeaInputPage` + both sibling pickers capture images into `attachedImages` and ship them out-of-band as the `images` payload field; the brief text never contains base64.
- 5 characterization goldens + oracle byte/event-identical (SNAPSHOT_UPDATE unset); lint-imports 4/0; registry drift-guard 65.
- FE tsc-identity (no new errors) + affected vitest green.
- Dormant at the agent level (no `input_providers:` / `injects:[images]`); no migration; no new WS event type; no commit trailer; branch stays `new-workflow-engine`.
</success_criteria>

<output>
Commit each task atomically (no trailer), in order:
1. `feat(engine): ModelEntry.vision + IMAGE_INPUT_ENABLED + _validate_images ingress caps/vision guard (260707-frv T1)`
2. `feat(engine): run_pipeline images ingress -> execute(images=) with flag/caps/vision guard + D3 (260707-frv T2)`
3. `feat(engine): FE IdeaInputPage image capture + images extraParams payload (260707-frv T3)`
4. `feat(engine): FE sibling pickers + dashboard image threading (260707-frv T4)`

Then create `.planning/quick/260707-frv-image-input-wave-2-fe-image-capture-ws-i/260707-frv-SUMMARY.md` with the HARD-GATE evidence table, the dormant-confirmation greps, and the commit list. Never push; never main.
</output>
