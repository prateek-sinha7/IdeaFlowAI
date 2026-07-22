# Image Input (Multimodal) to Agent Prompts — Plan of Record (v1)

**Status:** PROPOSED (v1.1 — plan-checked, revised) — awaiting user approval to execute. Adversarial plan-check verdict: NEEDS-REVISION → all findings folded in (§12); the two consequential findings were independently re-verified against the code before acceptance.
**Branch:** `new-workflow-engine` (NEVER main). **Runtime:** python3.11, no venv; full backend pytest hangs offline → verify with the targeted parity/gate suite + `/opt/homebrew/bin/lint-imports`.
**Convention:** Standalone post-milestone plan-of-record (mirrors `REDO-GATE-PLAN.md` / `REVISION-FAMILY-AND-RUN-INPUTS-PLAN.md`); NOT a ROADMAP.md phase.
**Provenance:** Scoped by a full read of `.planning/IMPLEMENTATION-REGISTER.md` (all 26 phases) + 9 read-only investigation agents. Every seam below is verified at file:line.

---

## §0. Scope Lock

**v1 goal:** a user attaches image(s) with their prompt, and the image reaches the **main pipeline agents that run through the deep-agent runner** — the prototype **spec-writer** (`prototype-specify`) is the first + highest-value consumer (it must *see* the attached diagram). v1 carries the image **transiently** (in the run payload; no persistence).

**IN scope (v1):**
- FE image capture + out-of-band transport.
- Backend carrier (`ExecutionContext.run_images`) + a registered `run_images` input-capability gated by `injects`.
- Multimodal dispatch to the runner for opted-in agents.
- Config flag + ingest caps + vision-model guard.
- Opt-in the `prototype` workflow's spec-writer and prove end-to-end.

**DEFERRED (explicitly OUT — build later, note as follow-ups):**
- **(D-a) Clarify + Planner image support** — `SmartPlanner` (`smart_planner.py:386-389`, builds its own `ChatBedrockConverse`) and `ClarifyEngine` (`clarify_engine.py:489-493`, uses `build_model`) call `ainvoke([HumanMessage(content=<str>)])` directly, bypassing the runner (ISS-033). Reachable in ~1 line each, but they are the two heaviest *uncached* calls in a run (full ~150k-token brief) and an image there only shapes clarify questions / the plan, not a deliverable. Low value, high cost → defer.
- **(D-b) Per-task build agents — deferred by SCOPE, not by a technical wall (rationale corrected, plan-check Finding 4).** The deepagents `task` sub-agent tool IS text-only, but Flowin **excludes it** (`deep_agent_runner.py:97,352`) and never uses deepagents sub-agents; the prototype build tasks run through the engine's own `task_loop` strategy → `KernelServices.run_agent` → `_run_agent` — the **same** `:2645` compose + `:2880` dispatch seam every main agent uses. So a build step declaring `injects:[images]` *would* reach the per-task build agents through the standard seam with **no extra plumbing**. v1 still defers build-agent images to keep the first cut minimal (spec-writer only) and control token cost, but the Layer-3/4 mechanism covers them for free when we choose to opt them in.
- **(D-c) Durable persistence** — v1 is transient (image in the payload). History-reopen / `resume_run` won't re-show images and a backend-restart resume loses them. Durable option = reuse `ArtifactRef` (`owner_id`+`workspace_id` already present) later; no new table.

---

## §1. Locked Decisions (do not re-litigate)

1. **Canonical image block = base64 + mime_type:** `{"type":"image","source_type":"base64","mime_type":"image/png","data":"<b64>"}` — verified accepted by `ChatBedrockConverse` (langchain_aws 1.4.6, Shape A) AND surviving `deepagents` + the Postgres checkpointer + `ChatAnthropic`. LangChain decodes base64→bytes and boto3 handles the wire ⇒ **no raw-byte plumbing in our code.** The internal carrier (`ectx.run_images`) holds normalized `{name?, mime_type, data(base64)}`; the capability turns each into the block.
2. **New port, NOT a transport hardcode** for producing image blocks (§3 Layer 3). The existing `ContextProvider` port returns `dict[str,str]` (TEXT); image blocks are `list[dict]` — a different shape. A transport-level append would couple image sourcing into the kernel (the exact prototype-coupling this refactor dissolves) and would not be palette-composable.
3. **Split the two uses of the composed context** (§3 Layer 4). The `agent_input` event's `data.context_message` stays a **text str always** (golden-pinned + FE `string` cast); image blocks ride **only** into the model dispatch. This means **zero** golden re-baseline and **no** `input_prompt` extraction obligation.
4. **Opt-in via `injects`** (declared data), never a workflow name / `pipeline_type` / `spec.id` (SC-001/INV-1).
5. **Transient carrier for v1** (zero migration); persistence deferred (D-c).
6. **Images out-of-band, never in `run.input`** (Phase 25 D3) — forced by `ATTACH_MAX_CHARS = 450000 = BRIEF_MAX_CHARS`; one ~340 KB image's base64 ≈ the whole brief cap.
7. **No new WS event type** (Phase 25 D5) — images ride the existing `run_pipeline` message.

---

## §2. Current-State Grounding (verified file:line)

**Transport / dispatch (`agents/execution_engine/engine.py`, `app/agents/deep_agent_runner.py`):**
- `_compose_context_message` has ONE return: `engine.py:5914` `return "\n".join(parts)`. The engine does **zero** string ops on the composed value.
- The composed value is read in exactly two places: the `agent_input` emit `engine.py:2663` and the model dispatch `engine.py:2880` (`agent.astream_events(context_message)`).
- The per-agent `AgentContext` build reads `od_context=ectx.od_context` at `engine.py:2687` (the carrier→transport hand-off point).
- Context-provider loop already lives inside `_compose_context_message` at `engine.py:5787-5839`, gated on `spec.injects`, with a `_RAW_BLOCK_PREFIX` (`\x00RAW\x00`) verbatim-text mechanism; run-entry seed loop at `engine.py:5698-5711`; `ectx.compiled_context_providers` threaded at `engine.py:1671`.
- Runner: `astream_events(self, user_message: str)` at `deep_agent_runner.py:407`, `HumanMessage(content=user_message)` at `:476`; 3 wrapper hints at `:730/794/808`; `HumanMessage.content` natively accepts `str | list` (langchain_core 1.4.0); `_extract_text` already `isinstance(content, list)`-aware at `:829`. No wrapper does string ops on `user_message`.
- **The one FE-facing str consumer:** `websocket.py:1870` persists `input_prompt = data.get("context_message")` → FE casts `as string` at `useWorkflow.ts:576`, `WorkflowHistory.tsx:356`. (Sidestepped entirely by Locked Decision #3.)
- The validation fix-loop `fix_message` is a **separate** str dispatch at `engine.py:3719` — NOT in v1 scope.
- Golden fence: `context_message` is de-blinded/pinned (Phase 7) — `test_context_message_oracle.py` guards `isinstance(cm, str)` at `:171-172`/`:339-340`; `_normalize.py:109-117` keeps it in the goldens; `_VOLATILE_STRIP_KEYS` at `_normalize.py:101` (`:118` is the `context_sources` member).

**Carrier precedent (`od_context`):**
- `execute()` sig `engine.py:764-782` (`od_context` at `:776`) → `_execute_impl` `:841-862` (forward `:817`); `ExecutionContext(...)` construction `engine.py:975-983`; field `context.py:113` `od_context: dict | None = None`. NOTE: `od_context` is **server-loaded** (`websocket.py:1540-1580`), not payload-read — so the payload-read precedent for a **client-supplied** field is `selections`/`gate_agent_ids`/`model_overrides` (`websocket.py:711/720/726/733`).

**Ingress (FE + WS):**
- FE picker `IdeaInputPage.tsx:536-540` (accept), onChange `:542-591`, brief compose `:347-350`, extraParams `:367-375`; 3 sibling pickers (`app/workflow/ppt/templates/page.tsx:438`, `app/workflow/prototype/templates/page.tsx:473`, `WorkflowView.tsx:324` degenerate). `useWorkflow.ts` `startPipeline` merges extraParams via `Object.assign(payload, context)` `:104`.
- WS `run_pipeline`: reads `pipeline_content` `:711`; `WorkflowRun(input=content)` `:1734-1743`; `engine.execute(od_context=…)` `:1845`; `_handle_workflow_execution` sig `:1493-1513`, call `:757-772`.
- `POST /api/files/extract-text` (`file_extract.py`) returns text only, 415 on images; pypdf currently absent (separate defect, not in scope).

**Capability mechanism (`agents/capabilities/`, `agents/workflows/`):**
- `ContextProvider` Protocol `base.py:75-83` (returns `dict[str,str]`). `OpenDesignProvider` `opendesign.py:41-179` gates on `current_spec_injects` `:79`, reads `ctx.od_context`, imports only `registry`+stdlib.
- Manifest → compiled: `context_providers` in `_ALLOWED_TOP_KEYS` (`manifest.py:99`), generic parse `:199`, field `:61/:221`; compiler validation `compiler.py:207-211`, copy `:250`; `CompiledWorkflow.context_providers` `plan.py:409`; per-step `Step.injects` compiled `compiler.py:548`, threaded `engine.py:2707-2715`.
- Registry: `@register(kind,name,*,user_allowed,description,config_schema)` `registry.py:177-215`; `_KNOWN` literal `:80-145`; `discover()._builtin_modules` `:249-299`; kinds are free strings (no if/elif). Drift-guard `test_registry_capabilities.py`: `assert len(_KNOWN) == 63` `:154` + `_EXPECTED_NAMES` `:38-102`.
- `ARTIFACT_KINDS` advisory-warns but does not raise (`graph.py:141-155`); an out-of-vocab kind is silently unroutable. ⇒ images stay **run-level input**, NOT a graph artifact.

**Model / vision (`model_factory.py`, `model_catalog.py`, `model_policy.py`):**
- `build_model` `:104-121` needs no vision flag (native to Converse). All 5 `ModelCatalog` entries `:68-128` are Claude 4.5/4.6 (vision-capable); `ModelEntry` `:47-59` has NO `vision` field. Every `ModelResolver.resolve` tier is catalog-gated. Escape hatch: raw config (`BEDROCK_INFERENCE_PROFILE_ID`/`BEDROCK_MODEL_ID`/`ANTHROPIC_MODEL_ID`/`BEDROCK_CODING_MODEL_ID`) flows into `build_model` without a catalog check (all default to Haiku 4.5 → misconfig risk only).

---

## §3. End-to-End Design (5 layers)

**Layer 1 — Ingress (FE + WS).** FE: add `image/*` to the picker `accept` + an `isImageFile` branch capturing bytes into a NEW `attachedImages` state (`{name, mime_type, data}` via `readAsDataURL`) — MUST NOT call `setAttachedFileContents` (that array is inlined into the brief). Ship out-of-band via `extraParams`. WS: `images = message_data.get("images") or []` (mirror `selections`) → thread into `engine.execute(images=…)`. Ingest caps: mime allow-list `png/jpeg/webp/gif`, per-image ≤3.75 MB raw, ≤20 images, **plus a per-run AGGREGATE cap (≤~8 MB raw total, v1)** — because the multimodal `HumanMessage` is checkpointed per agent-invocation and re-sent on every model-fallback retry (`:2880` inside `while True:` at `:2860`), so 20×3.75 MB unbounded would balloon checkpoint rows + retry payloads (plan-check Finding 3). Config `IMAGE_INPUT_ENABLED` (mirror `BEDROCK_PROMPT_CACHE_ENABLED`).

**Layer 2 — Carrier.** Additive `images` param on `execute()`/`_execute_impl` → `run_images` field on `ExecutionContext` (`context.py:113`, beside `od_context`), mirroring `od_context` exactly. Default empty ⇒ dormant ⇒ INV-3 byte-identical.

**Layer 3 — Capability (SC-001-clean).** One-time: (i) `InputContentProvider(Protocol)` in `base.py` (`async load(ctx) -> list`, stdlib-typing only — sanctioned port evolution, precedent Phase 7 `context_provider` / Phase 8 ports); (ii) new `agents/capabilities/input_providers/run_images.py` — `@register("input_provider","run_images",user_allowed=True,…)`, `async load(ctx)` reads `getattr(ctx,"run_images",None)` and returns image content-blocks (or `[]` when empty); imports only `registry`+stdlib. **The capability does NOT self-gate on `ctx.current_spec_injects`** — that field is set once at `engine.py:5803` inside `if injects:` and never reset, so a non-opted agent running after an opted-in one would read a stale `{images}` and leak the image (BLOCKER, plan-check Finding 1). Gating is the caller's job (vii); (iii) registry lockstep (`_KNOWN` + `discover()` module + drift-guard 63→64 + `_EXPECTED_NAMES`); (iv) manifest `input_providers` top-key + field + parse; (v) compiler validation loop (mirror `compiler.py:208-211`, kind `input_provider`) + `CompiledWorkflow.input_providers` ctor arg; (vi) `plan.py:409` `input_providers: list[str] = field(default_factory=list)`; (vii) engine: thread `ectx.compiled_input_providers` (beside `:1671`) + a **sibling** `_compose_input_blocks(spec, ectx) -> list` that derives its gate **LOCALLY from the current `spec`** — `agent_injects = set(getattr(spec,"injects",[]) or []) | set(step_injects)` — resolves each declared `input_provider` ONLY when `"images" in agent_injects`, and returns `[]` otherwise. **The result is a per-agent LOCAL `input_blocks` in `_run_agent` (exactly like `context_message` is a local at `:2645`), passed straight to the `:2880` dispatch — there is NO shared `ectx.pending_input_blocks` field** (deleting it removes the stale-leak vector entirely). No `ARTIFACT_KIND` edit.

**Layer 4 — Transport (the split).** Keep `_compose_context_message` returning the text str; keep the `agent_input` event's `context_message` **text**. In `_run_agent`, compute the per-agent local `input_blocks = await _compose_input_blocks(spec, ectx)` (empty for non-opted agents). At dispatch `engine.py:2880`: if `input_blocks` is non-empty, dispatch `[{"type":"text","text": <composed str>}, *input_blocks]`; else the bare str. (The dispatch sits inside the model-fallback `while True:` retry loop at `:2860` — the same local is re-sent each retry; see Finding 3 on the aggregate cap.) Widen `astream_events(self, user_message: str | list)` + 3 wrapper hints (`deep_agent_runner.py:407/730/807`). For observability, emit `image_count` on the `agent_input` event **only when > 0** (omit for text-only runs so it never enters the blinded set) and also add it to `_VOLATILE_STRIP_KEYS` (`_normalize.py:101`) belt-and-suspenders.

**Layer 5 — Model.** `build_model` unchanged (vision native to Converse). HARDENING (v1): add `vision: bool` to `ModelEntry` (all 5 = True) + reject image input when the effective resolved model is not a vision-capable catalog entry (closes the raw-config escape hatch).

---

## §4. Task & Wave Breakdown

**Wave 1 — Backend spine (dormant; no behavior change until a workflow opts in).**
- T1.1 Carrier: `images` param on `execute()`/`_execute_impl`; `run_images: list | None = None` on `ExecutionContext`; normalize/validate to canonical `{mime_type, data}` at the seam.
- T1.2 Port: `InputContentProvider(Protocol)` in `base.py`.
- T1.3 Capability: `input_providers/run_images.py` (`@register`, injects-gated, returns blocks; empty `run_images` → `[]`).
- T1.4 Registry lockstep: `_KNOWN` + `discover()` module + `_EXPECTED_NAMES` + count 63→64.
- T1.5 Manifest/compiler/plan: `input_providers` top-key + field + generic validation loop + `CompiledWorkflow.input_providers`.
- T1.6 Engine wiring: `ectx.compiled_input_providers` + `_compose_input_blocks(spec, ectx)` sibling that gates **locally** on `set(spec.injects) | set(step_injects)` (NOT the stale `ectx.current_spec_injects`) → returns a **per-agent local** `input_blocks` (`[]` for non-opted); NO shared `ectx` field.
- T1.7 Transport: compute the `input_blocks` local in `_run_agent`, dispatch content-list wrap at `engine.py:2880` (text-only vs image run) + runner hint widening (`str | list`) + `image_count` on `agent_input` only-when-`>0` (and in `_VOLATILE_STRIP_KEYS`).
- **Gate:** 5 goldens byte/event-identical (`SNAPSHOT_UPDATE` unset) · `lint-imports` 4/0 · registry drift-guard green · unit tests for T1.3/T1.6/T1.7.

**Wave 2 — Ingress (FE + WS + ingest).**
- T2.1 FE `attachedImages` capture + `image/*` accept (all 4 picker copies) + out-of-band `extraParams`.
- T2.2 WS `images` field (mirror `selections`) → `execute(images=)`.
- T2.3 Image-ingest validation (mime/size/count caps) + `IMAGE_INPUT_ENABLED` flag.
- T2.4 Vision guard: `ModelEntry.vision` + ingress reject on non-vision resolved model.
- **Gate:** FE `tsc`/vitest green · WS unit test that `images` reaches `execute` · caps reject oversized/too-many/wrong-mime · D3 (nothing enters `run.input`) proven.

**Wave 3 — Opt-in + prove.**
- T3.1 `input_providers: [run_images]` on the `prototype` manifest + `injects: [images]` on `prototype-specify`.
- T3.2 Live Bedrock run: spec-writer receives the diagram (multimodal `HumanMessage`), text-only agents unchanged.
- T3.3 **Middleware/checkpointer proof gate (plan-check Findings 2+3).** Prove on a real image run that: (a) the on-by-default `SummarizationMiddleware` (`deep_agent_runner.py:346`) does not evict/drop the image on the spec-writer's first turn and its char-based token estimate does not spuriously trip summarization (base64 inflates the estimate — confirm the image still reaches the model and note the cost); (b) `_BedrockCachePointsMiddleware` (`:352`, operates on `request.model_settings`, not message content) passes list-content through intact; (c) the Postgres checkpointer row stays within limits at the aggregate cap. (Batch-1/2 investigation already found summarization is multimodal-aware and the cache middleware touches `model_settings` not content — this gate confirms it live.)
- **Gate:** live spec-writer-sees-image confirmation · middleware/checkpointer gate green · 5 goldens still byte-identical · FIX-REGISTER + IMPLEMENTATION-REGISTER updated.

---

## §5. Invariant & Locked-Decision Compliance

| Invariant | How this plan complies |
|---|---|
| **SC-001 / INV-1** | Capability keys on `injects`/declared data; a new image workflow = `input_providers:` + `injects:` in manifest/AGENT.md, **zero** engine/compiler/port edits. Banned-pattern grep stays 0 in `agents/execution_engine/`. |
| **INV-3** | Composed `context_message` stays str; `agent_input` event stays text; images absent on all 5 goldens ⇒ dispatch wrap never fires; `isinstance(cm,str)` oracle path unaffected; any new event key in `_VOLATILE_STRIP_KEYS`. **Zero re-baseline.** |
| **INV-12** | `run_images` = single carrier; `run_images` capability = single block-producer. No dual path. |
| **INV-13** | Multimodal `HumanMessage` native to `create_deep_agent` (main agents); no hand-rolled loop; `create_deep_agent` stays only in `deep_agent_runner.py`. |
| **Ports & Adapters** | New capability under `agents.capabilities`, imports only `registry`+stdlib, reaches bytes via `getattr(ctx,"run_images")`; `base.py` stdlib-only; engine→capability via registry.resolve. `lint-imports` stays 4/0. |
| **Phase 25 D3** | Images out-of-band; `run.input` stays text (forced by `ATTACH_MAX_CHARS=BRIEF_MAX_CHARS`). |
| **Phase 25 D5** | Images ride existing `run_pipeline` message; no new WS event type. |
| **Q3 (migrations)** | v1 = zero migration (transient). Persistence later = reuse `ArtifactRef`, never a new table. |
| **`prototype_revision` fence** | Untouched — revision agents declare no image injects ⇒ dormant. |
| **Security posture** | Image input is inbound user data, not `exec`/`network`/`secrets`/`spawn_subagents` ⇒ no `security` gate; `user_allowed=True`. |

---

## §6. Threat Model (STRIDE-lite)

- **Oversized / decompression / count DoS** → mitigated by ingest caps (≤3.75 MB/image, ≤20 images, mime allow-list `png/jpeg/webp/gif`); base64 kept out of `run.input` so `BRIEF_MAX_CHARS` is not exhausted.
- **Tampering / smuggling a non-vision or non-catalog model to reject-bypass** → the vision guard rejects image input unless the effective resolved model is a vision-capable catalog entry; `IMAGE_INPUT_ENABLED` off-switch.
- **Cross-owner / IDOR** → v1 is transient (image in the caller's own run payload, scoped to the authenticated run); no cross-run read introduced. (Persistence, deferred, would reuse `ArtifactRef`'s owner/workspace scoping.)
- **Prompt-injection via image content** → same trust boundary as the existing text brief; the image informs an agent that already consumes untrusted user text. No new privilege.
- **Info-disclosure via logs** → do not log base64 payloads; `agent_input` event carries only optional `image_count`, never image bytes.

---

## §7. Verification Gates (Definition of Done)

- 5 characterization goldens byte/event-identical with `SNAPSHOT_UPDATE` unset (change dormant until a workflow opts in AND an image is present); `test_context_message_oracle.py` unaffected — **zero re-baseline expected**.
- `/opt/homebrew/bin/lint-imports` → 4 kept / 0 broken.
- Registry drift-guard green (count 63→64 + `_EXPECTED_NAMES`).
- New tests: `run_images` capability unit (injects gate; empty `run_images` → `[]`; block shape); `input_provider` compile/registration path; dispatch content-list wrap (text-only vs image run, incl. text-only byte+chunk-identical); vision-guard reject; ingest caps.
- Live Bedrock: `prototype-specify` receives the multimodal `HumanMessage` (diagram visible); non-opted agents unchanged.
- `FIX-REGISTER.md` + `IMPLEMENTATION-REGISTER.md` updated per convention. No commit trailer. No push without explicit go-ahead.

---

## §8. Risks & Open Levers (recommendations baked in)

1. **Transient vs durable carrier** → *v1 transient* (zero migration); upgrade to `ArtifactRef` only if image runs must survive reopen/resume.
2. **Vision guard** → *include in v1* (cheap; closes the raw-config hole).
3. **Clarify/planner image support** → *defer* (ISS-033 direct calls, expensive, low value).
4. **Sub-agent images** → *defer* (deepagents `task` tool is text-only; needs custom plumbing).
5. **`run.input` no longer the complete submission record** — history/title derivation show text only for an image-heavy run. Accepted design note; revisit with persistence (D-c).

---

## §9. Compliance Matrix (mechanism → gate)

| Requirement | Mechanism | Proof gate |
|---|---|---|
| Image reaches spec-writer | `run_images` carrier → `run_images` capability (injects) → dispatch wrap | Live Bedrock run |
| No workflow-name coupling | injects/declared-data gating | banned-pattern grep = 0 |
| No golden regression | text-only `context_message` + dormant dispatch | goldens byte-identical, `SNAPSHOT_UPDATE` unset |
| Hexagonal preserved | new capability, registry.resolve, getattr-ctx seam | `lint-imports` 4/0 |
| No new storage/migration (v1) | transient payload carrier | no alembic file |
| Vision safety | `ModelEntry.vision` + ingress reject | vision-guard reject test |
| DoS safety | ingest caps | caps reject tests |

---

## §12. Plan-Check Revisions (v1.0 → v1.1)

Independent adversarial plan-check verdict: **NEEDS-REVISION**. Anchor check: ~95% exact (5 minor drifts, none load-bearing). Findings and dispositions (the two consequential ones re-verified against the code before acceptance):

- **F1 [BLOCKER] — stale-injects cross-agent leak. FIXED.** Re-verified: `ectx.current_spec_injects` is assigned once at `engine.py:5803` inside `if injects:` with **no reset** (grep confirms a single assignment). A capability self-gating on it would leak the image to every agent after the first opted-in one. Fix: the gate is derived **locally from the current `spec`** in `_compose_input_blocks`, the blocks are a **per-agent local** in `_run_agent`, and the shared `ectx.pending_input_blocks` field is deleted (Layer 3(vii), Layer 4, T1.6/T1.7). Also resolved the plan's internal union-vs-spec-only gate contradiction (gate = `spec.injects` ∪ `step.injects`, computed locally — the context-message path gates on `spec.injects`, not the factory `step_injects` seam at `2707-2715`).
- **F2 [MAJOR] — deepagents summarization / cache-point middleware vs list content. GATE ADDED (T3.3).** Prior investigation already found summarization is multimodal-aware (image survives, char-based estimate may inflate cost) and `_BedrockCachePointsMiddleware` operates on `model_settings` not content — T3.3 confirms this live before Wave 3 is "done."
- **F3 [MAJOR] — checkpointer/retry payload amplification. FIXED.** Re-verified the `:2880` dispatch is inside the `while True:` fallback loop (`:2860`). Added a per-run aggregate byte cap (≤~8 MB raw) to Layer 1 + threat model.
- **F4 [MINOR] — D-b rationale wrong. CORRECTED.** Re-verified: the deepagents `task` tool is excluded (`deep_agent_runner.py:97,352`), build tasks run through `_run_agent` (same seam). D-b now frames build-agent images as a scope choice, not a technical wall.
- **F5 [MINOR] — anchor drift. CORRECTED.** `_VOLATILE_STRIP_KEYS` → `_normalize.py:101`; runner `run` → `:807`; `model_catalog.py` under `agents/capabilities/`; `ARTIFACT_KINDS` under `agents/artifacts/graph.py`.
- **F6/F7 [MINOR] — port test coverage + `image_count` neutrality.** Optional `_PORTS` test add noted; `image_count` now emitted only-when-`>0` (and stripped).

**Confirmed by the check (do not weaken):** split-transport (event stays `str`, only `:2880` wraps) → zero re-baseline; carrier mirror (`run_images` ↔ `od_context`); compiler/manifest generic-ness (SC-001-clean at the declaration layer); registry lockstep completeness (count still `63`→64); import-linter 4/0. INV-3 zero-rebaseline holds **conditional on F1** (now fixed).

## References
`.planning/IMPLEMENTATION-REGISTER.md` — Phase 5 (artifacts/ScopedStore), Phase 7 (context-providers + `_compose_context_message` + oracle), Phase 8 (registry/ports/`@register`/`discover`), Phase 22 (selections/injects wiring), Phase 25 (run-inputs D3/D5 + `prototype_revision` fence), Phase 26 (ISS-033). Investigation: 9 read-only agents (Bedrock Converse, Anthropic Messages API, deepagents passthrough, ingestion path, dispatch/architecture, transport seam, capability placement, FE/WS carrier, ISS-033/vision) + 1 adversarial plan-check.
