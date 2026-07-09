---
phase: 260707-edw
plan: 01
subsystem: execution-engine / capabilities
tags: [image-input, input_provider, multimodal, dormant, INV-1, INV-3, SC-001]
wave: "1 of 3"
requires: []
provides:
  - "ExecutionContext.run_images carrier (transient, zero-migration)"
  - "InputContentProvider(Protocol) port (base.py)"
  - "run_images input_provider capability (@register, user_allowed=True)"
  - "WorkflowManifest/CompiledWorkflow input_providers declaration surface"
  - "engine _compose_input_blocks (locally-gated) + _dispatch_payload split-transport wrap"
  - "DeepAgentRunner str|list widening"
affects:
  - backend/agents/execution_engine/engine.py
  - backend/agents/execution_engine/context.py
  - backend/agents/capabilities/base.py
  - backend/agents/capabilities/input_providers/
  - backend/agents/capabilities/registry.py
  - backend/agents/workflows/{manifest,compiler,plan}.py
  - backend/app/agents/deep_agent_runner.py
tech_stack_added: []
key_files_created:
  - backend/agents/capabilities/input_providers/__init__.py
  - backend/agents/capabilities/input_providers/run_images.py
  - backend/tests/agents/test_input_providers_run_images.py
  - backend/tests/agents/test_image_input_wiring.py
key_files_modified:
  - backend/agents/execution_engine/engine.py
  - backend/agents/execution_engine/context.py
  - backend/agents/capabilities/base.py
  - backend/agents/capabilities/registry.py
  - backend/agents/workflows/manifest.py
  - backend/agents/workflows/compiler.py
  - backend/agents/workflows/plan.py
  - backend/app/agents/deep_agent_runner.py
  - backend/tests/agents/test_registry_capabilities.py
  - backend/tests/agents/characterization/_normalize.py
decisions:
  - "Image blocks are a per-agent LOCAL in _run_agent (like context_message) — NO shared ectx.pending_input_blocks field (F1 leak designed out)."
  - "_compose_input_blocks gates LOCALLY on set(spec.injects) | set(step.injects); NEVER reads the stale ectx.current_spec_injects."
  - "Split-transport: agent_input.context_message stays a TEXT str always; only the model dispatch wraps to [text, *blocks] — zero golden re-baseline."
  - "T1.4 reconciled the pre-existing KAN-73 hook:audit_logger drift into _EXPECTED_NAMES so the drift-guard sets equalize (count 63→65)."
metrics:
  duration_min: 13
  tasks: 4
  files: 14
  completed: 2026-07-07
---

# Phase 260707-edw Plan 01: Image Input Wave 1 — Backend Spine (DORMANT) Summary

DORMANT backend spine so an image content-block CAN reach an opted-in agent — carrier →
port → registered `run_images` capability → manifest/compiler/plan declaration surface →
locally-gated engine wiring → multimodal dispatch wrap → runner `str|list` widening —
with NO workflow opting in this wave, so the change is byte/event-identical BY
CONSTRUCTION. Wave 1 of 3.

## What Was Built

**Task 1 (T1.1-T1.4) — carrier + port + capability + registry lockstep** (commit `440d3658`)
- `ExecutionContext.run_images` transient carrier (context.py); `execute(images=)` /
  `_execute_impl(images=)` additive params; module-level `_normalize_run_images()` seam
  (canonicalize `{mime_type,data}`, drop malformed, `mimeType` alias accepted); wired at
  the `ExecutionContext(...)` construction (`run_images=_normalize_run_images(images)`).
- `InputContentProvider(Protocol)` port in `base.py` (`name` + `async load(ctx)->list`),
  stdlib-only.
- `agents/capabilities/input_providers/{__init__,run_images}.py` — the
  `@register("input_provider","run_images", user_allowed=True, ...)` impl; reads
  `ctx.run_images`, returns `{type:image,source_type:base64,mime_type,data}` blocks or `[]`;
  imports ONLY registry + stdlib; NEVER reads `ctx.current_spec_injects`.
- Registry lockstep: `_KNOWN += ("input_provider","run_images")`, `discover()` imports the
  module, kinds-tally comment extended.

**Task 2 (T1.5) — declaration surface** (commit `756cd630`)
- `manifest.py`: `"input_providers"` in `_ALLOWED_TOP_KEYS`; `WorkflowManifest.input_providers`
  field + `_optional_list` parse + ctor pass-through.
- `compiler.py`: sibling `input_provider` validation loop (`is_registered` + `_check_trust`);
  `CompiledWorkflow(... input_providers=list(...))`.
- `plan.py`: `CompiledWorkflow.input_providers: list[str] = field(default_factory=list)`.
- NEGATIVE SPACE held: NO `input_providers:` added to any `workflow.yaml`.

**Task 3 (T1.6-T1.7) — engine wiring + transport + runner widening** (commit `5e62edd9`)
- `ectx.compiled_input_providers = list(compiled.input_providers or [])` threaded beside
  `compiled_context_providers`.
- NEW `_compose_input_blocks(self, spec, ectx)` — gate = `set(spec.injects) ∪
  set(ectx.current_step.injects)`; `"images" not in gate → []`; else resolve each
  `input_provider` off `ectx.compiled_input_providers` (try/except KeyError,RuntimeError skip;
  load logs-and-skips on Exception but re-raises PermissionError). Does NOT read
  `ectx.current_spec_injects`.
- Module-level `_dispatch_payload(context_message, input_blocks)` — bare str when empty, else
  `[{type:text,text:cm}, *blocks]`.
- `_run_agent`: per-agent LOCAL `input_blocks = await self._compose_input_blocks(spec, ectx)`;
  `agent_input.context_message` stays a str; `image_count` added to the `data` dict ONLY when
  `input_blocks` non-empty; dispatch `astream_events(_dispatch_payload(context_message, input_blocks))`
  inside the attempt `while True:`. NO `ectx.pending_input_blocks`.
- `deep_agent_runner.py`: `str | list` hints on `astream_events`/`astream_with_usage`/
  `astream`/`run` (no logic change; `HumanMessage(content=...)` accepts both).
- `_normalize.py`: `"image_count"` added to `_VOLATILE_STRIP_KEYS` (belt-and-suspenders).

**Task 4 (T1.6/T1.7 TDD) — wiring test suite** (commit `0781a066`)
- `test_image_input_wiring.py`: the MANDATORY BLOCKER two-agent isolation test (agent B gets
  `[]` even with `ectx.current_spec_injects == {"images"}`), the step-injects-union arm, the
  no-providers-declared dormant arm, the `_dispatch_payload` wrap contracts, and the runner
  `str|list` widening (list + str content both stream the scripted text without raising;
  `HumanMessage` carries both verbatim).

## HARD-GATE Evidence

| Gate | Result |
|------|--------|
| **1. Goldens byte/event-identical** (SNAPSHOT_UPDATE unset) | **PASS** — all 5 characterization files (`prototype`, `od_prototype`, `prototype_revision`, `od_ppt`, `app_builder`) + `test_context_message_oracle` + registry ran together = **108 passed**. The 4 non-od_ppt goldens + oracle: **18 passed**. |
| **od_ppt stash-diff proof** | **Both od_ppt tests GREEN, identical before/after.** Ran `test_characterization_od_ppt.py` with the Task-3 diff (`2 passed`) then `git stash` (`2 passed`) then `git stash pop` — identical. The plan's anticipated pre-existing red (`test_od_ppt_event_snapshot`) did **not** reproduce here; both `test_od_ppt_deliverable_byte_snapshot` and `test_od_ppt_event_snapshot` pass. Stronger INV-3 outcome than required (no red at all). |
| **2. lint-imports** | **PASS** — `4 kept, 0 broken`. |
| **3. registry drift-guard** | **PASS (65)** — `test_registry_capabilities.py` green; `len(_KNOWN) == 65`, `set(_KNOWN) == set(_EXPECTED_NAMES)`; T1.4 reconciled the pre-existing KAN-73 `hook:audit_logger` drift (was `64 == 63` red on entry) → now `65`. |
| **4. new TDD suites** | **PASS** — `test_input_providers_run_images.py` (a) + `test_image_input_wiring.py` (b/c/d, incl. BLOCKER) = **16 passed**. |
| **5. INV-1 grep** | **PASS (0)** — `grep -rnE 'pipeline_type ==\|spec\.id ==' agents/execution_engine/engine.py` → 0. |

## DORMANT Confirmation

- NO `input_providers:` on any `agents/workflows/*/workflow.yaml` (`grep` → NONE).
- NO `injects:[images]` on any `agents/prompts/*/AGENT.md` (`grep` → NONE).
- Therefore `compiled_input_providers == []` and the `"images"` gate never fires for any
  agent → `_compose_input_blocks` returns `[]`, `_dispatch_payload` returns the bare str,
  `image_count` is never emitted → goldens byte/event-identical BY CONSTRUCTION (INV-3).
- Zero Alembic migration (transient carrier, Locked Decision #5). No new WS event. No
  `ARTIFACT_KINDS` edit. No new `create_deep_agent` (INV-13).

**Wave 1 of 3.** Ingest caps (mime allow-list, per-image/per-run size, count) + retry-payload
amplification proof + a workflow opt-in are Wave 2/3 (IMAGE-INPUT-PLAN §3/§12, T-edw-03).

## Deviations from Plan

None affecting scope. The plan anticipated `test_od_ppt_event_snapshot` as a standing
pre-existing branch red requiring a stash-diff "same failure" proof; in this environment it
is GREEN (proven identical before/after via stash), so the evidence is "byte/event-identical,
fully green" rather than "identical red". No code deviation.

## Out-of-Scope Pre-existing Reds (NOT fixed — see deferred-items.md)

Proven pre-existing via `git stash` (identical with/without the Wave-1 diff), unrelated to
`input_providers`:
- `test_manifest_parity.py::test_clarify_defaults_match_engine[*]` — 7 params (clarify.defaults
  parity drift).
- `test_manifest.py::test_display_name_*[dotnet_to_azure|custom]` — 2 (display_name/launchable
  catalog drift).

## Commits (no trailer)

| Task | Commit | Subject |
|------|--------|---------|
| 1 | `440d3658` | feat(engine): image-input carrier + run_images input_provider + registry lockstep (260707-edw T1.1-T1.4) |
| 2 | `756cd630` | feat(engine): manifest/compiler/plan input_providers declaration surface (260707-edw T1.5) |
| 3 | `5e62edd9` | feat(engine): locally-gated _compose_input_blocks + multimodal dispatch wrap + runner str\|list widening (260707-edw T1.6-T1.7) |
| 4 | `0781a066` | test(agents): image-input wiring TDD suite incl. BLOCKER two-agent isolation (260707-edw T1.6/T1.7) |

Branch `new-workflow-engine`; nothing pushed; no commit trailer.

## Self-Check: PASSED
- Files exist: `input_providers/run_images.py`, `input_providers/__init__.py`,
  `test_input_providers_run_images.py`, `test_image_input_wiring.py` — all present.
- Commits exist: `440d3658`, `756cd630`, `5e62edd9`, `0781a066` — all in `git log`.
