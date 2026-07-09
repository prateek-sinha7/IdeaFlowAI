---
phase: quick-260707-gvq
status: passed
verified_by: orchestrator (independent gate re-run — goldens dormant-when-empty proof + pre-existing-red inspection)
date: 2026-07-07
---

# Verification — quick-260707-gvq (Image Input Wave 3 — prototype opt-in, OFFLINE)

**Status: passed (offline).** The `prototype` workflow now consumes user-supplied images at the order-1 spec-writer. Independently verified DORMANT-when-no-image (goldens byte-identical) and DELIVERS-when-image-present (wiring test). Wave 3 of 3. The LIVE Bedrock confirmation is deferred to a user-driven run (runbook provided separately).

## Independent evidence (orchestrator re-ran)
- **KEY GATE — goldens dormant:** the 5 characterization goldens + `test_context_message_oracle` are **byte/event-identical with `SNAPSHOT_UPDATE` UNSET** (in the 150 passed). Proof the opt-in is inert when `run_images` is empty: the golden harness passes no images → `run_images.load` returns `[]` → `_compose_input_blocks` returns `[]` → bare-str dispatch, no `image_count`; and `_compose_injection` ignores `images` → system prompt unchanged.
- **Wiring test (`test_prototype_image_optin.py`): 4 passed** — a populated `ectx.run_images` + the REAL opted-in `prototype-specify` spec + the REAL compiled `prototype` plan (`input_providers=[run_images]`) → exactly one `{"type":"image","source_type":"base64",…}` block; the non-opted `prototype-plan` → `[]` (the per-agent gate holds).
- **registry** drift-guard green (65); **loader** accepts the new `images` inject; **lint-imports** 4 kept / 0 broken; **INV-1** grep 0 (unchanged).

## Scope / invariant audit
- **2 atomic commits, trailer-free:** `6f41e0a9` (opt-in), `f13b4dbc` (wiring test); branch `new-workflow-engine`; nothing pushed.
- **Scope = EXACTLY 3 files:** `prototype/workflow.yaml` (+`input_providers: [run_images]`), `prototype-specify/AGENT.md` (+`images` inject), `test_prototype_image_optin.py` (new). **ZERO `.py` kernel/engine/capability/factory/loader/manifest/compiler/plan edit** — a workflow opts in by DECLARATION ONLY (SC-001). NO `SNAPSHOT_UPDATE`. No migration.
- **injects safety (verified in code BEFORE the edit):** the loader accepts `images` (generic string-list parse; the "subset of [template,design_system,craft]" at `loader.py:104` is a comment, not an allow-list); `_compose_injection` (`factory.py:656-739`) fires only on `template`/`design_system`/`craft` membership → silently ignores `images`; the `opendesign` provider gates on `design_system`/`template` only (`opendesign.py:126-127` documents "unknown inject values inject nothing") → the system prompt + context_message are byte-identical.

## Pre-existing reds — untouched (proven)
- `test_manifest.py::test_display_name_*` ×2 (`dotnet_to_azure`, `custom`) — the known pre-existing branch reds (proven pre-existing in Wave 1); they assert `display_name` on the `dotnet_to_azure`/`custom` manifests, unrelated to the `prototype` edit.
- `test_factory_injects.py` ×5 — proven pre-existing by **code inspection** (the suite uses synthetic `@dataclass _Spec` objects at `:29`, all cases `_Spec(injects=[...])`; it NEVER calls `load_agent_spec("prototype-specify")`, so the AGENT.md edit cannot affect it) **plus** the executor's `git stash` proof (identical `5 failed / 6 passed` on clean HEAD). Logged, NOT fixed (out of scope).

## DEFERRED — live confirmation (T-gvq-03, defer-live-verification convention)
Code-complete + offline-verified, but the LIVE proof needs interactive Bedrock SSO and is deferred to a user-driven run: (1) on a real prototype run WITH an attached image, the spec-writer's dispatched `HumanMessage` carries the image content-block and the model sees it; (2) the middleware/checkpointer image-payload gate (IMAGE-INPUT §12 F2/F3 — the on-by-default `SummarizationMiddleware` does not evict the image on the spec-writer's first turn, `_BedrockCachePointsMiddleware` passes list-content through, and the Postgres checkpointer row stays within limits at the aggregate cap). A runbook is provided by the orchestrator.

## Feature status
Image input (multimodal) is now **ON for the `prototype` workflow** — all 3 waves complete and offline-verified end-to-end (carrier + capability + transport → FE/WS ingress + caps + vision guard → prototype opt-in), pending the deferred live confirmation. See `.planning/IMAGE-INPUT-PLAN.md`.
