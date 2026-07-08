---
phase: 30-uploads-multimodal-a2
reviewed: 2026-07-08T00:00:00Z
depth: deep
files_reviewed: 22
files_reviewed_list:
  - backend/app/api/run_files.py
  - backend/app/api/file_extract.py
  - backend/app/agents/sandbox.py
  - backend/app/main.py
  - backend/app/api/run_commands.py
  - backend/app/api/chat_router.py
  - backend/agents/execution_engine/engine.py
  - backend/agents/execution_engine/context.py
  - backend/agents/capabilities/context_providers/uploaded_files.py
  - backend/agents/capabilities/registry.py
  - backend/tests/agents/test_input_providers_run_images.py
  - backend/tests/agents/test_registry_capabilities.py
  - backend/tests/agents/test_uploaded_files_provider.py
  - backend/tests/unit/test_mechanical_router.py
  - backend/tests/unit/test_run_files_upload.py
  - backend/tests/unit/test_run_message_images.py
  - frontend/src/components/results/StartingPointCard.tsx
  - frontend/src/components/results/StartingPointCard.test.tsx
  - frontend/src/components/workflow/IdeaInputPage.tsx
  - frontend/src/components/workflow/IdeaInputPage.imageInput.test.tsx
  - frontend/src/lib/resizeImage.ts
  - frontend/src/lib/resizeImage.test.ts
findings:
  critical: 1
  warning: 4
  info: 2
  total: 7
status: issues_found
---

# Phase 30: Code Review Report (Uploads & Multimodal)

**Reviewed:** 2026-07-08
**Depth:** deep (cross-file trace of the per-turn image seam, the upload endpoint's
disk write path, and the manifest contract shared between `run_files.py` and
`uploaded_files.py`)
**Files Reviewed:** 22
**Status:** issues_found (1 HIGH, 4 MEDIUM, 2 LOW/INFO — no CRITICAL)

## Summary

Reviewed the full 15-commit phase diff (`e6b821db..HEAD`): the new owner-scoped
document-upload endpoint (`run_files.py`), the shared extraction helper refactor
(`file_extract.py`), the `.uploads/` sandbox exclusion, the new kernel-pure
`uploaded_files` context provider, the per-turn image carrier threaded through
`run_commands.py` → `chat_router.py` → `engine.py`/`context.py`, and the frontend
client-side image resize + "not retained" placeholder.

The phase-critical security invariants hold up under direct testing and static
trace:

- **IDOR → 404 (never 403)**: verified both layers (ORM `user_id` filter, then
  `ScopedStore.get_run` default-deny) in `run_files.py` return 404 on both the
  cross-owner and store-denied paths, mirroring `run_commands.post_message`
  exactly. Confirmed by `TestOwnership` in `test_run_files_upload.py` and by
  direct read of `run_files.py:95-119`.
- **Caps before write**: ext/mime, per-file, count, and aggregate caps are all
  checked in the `validated` accumulation loop before the disk-write loop begins
  (`run_files.py:121-215`). Confirmed by `TestCaps`.
- **Traversal-proof writes**: every write resolves through `RunSandbox.path_for`
  (`run_files.py:236-240`, `sandbox.py:130-136`), which is separator-aware and
  rejects escapes; filenames are additionally reduced to a single safe segment via
  `os.path.basename` + `_safe_segment` before ever reaching a path.
- **SC-001 kernel purity**: `uploaded_files.py` imports only the registry
  decorator + stdlib (`json`, `logging`, `typing`) — confirmed by inspection and
  by the phase's own `test_sc001_engine_has_zero_reference_to_the_capability`
  test, and by a clean `lint-imports` run (4 contracts kept, 0 broken).
- **ND-10 non-persistence**: per-turn image bytes are never written to the
  `chat_message` row (only `{"kind":"image","retained":false}` refs, no `data`
  field) — confirmed by direct read and by `TestNoPersistenceLock`.
- **Degrade-not-crash**: `uploaded_files.py`'s manifest/sidecar reads and
  `resizeImage.ts`'s decode/canvas path both degrade to `{}` / the original file
  on any error, never raising. Confirmed by test and by code trace (all disk
  reads and canvas operations are wrapped in `try/except`/`try/catch`).

However, deep cross-file tracing surfaced one **functional-correctness bug in the
new per-turn image carrier** that violates the phase's own stated "consume-once /
next-dispatch-only" contract, and is **empirically reproducible today** because
the pipeline it targets (`prototype-specify`, `injects:[images]` +
`input_providers:[run_images]`, both pre-existing and already shipped) is live,
not dormant. Additionally, the new upload endpoint has two data-integrity gaps
(filename-collision overwrite, and an unguarded manifest read-modify-write race)
and a memory/availability soft spot (full-body read before the size cap fires).
None of these rise to CRITICAL — no security bypass, no cross-owner disclosure —
but the HIGH finding should be fixed before the per-turn image feature is
considered complete, since it silently pollutes future, unrelated model
dispatches with stale image content.

## High

### HI-01: Per-turn images are never cleared from `ectx.run_images` — the "consume-once / next dispatch only" contract is broken, and this is reachable in the currently-shipped configuration, not dormant

**File:** `backend/agents/execution_engine/engine.py:431-447` (also documented,
identically incorrectly, at `backend/agents/execution_engine/context.py:269-287`
and `backend/app/api/chat_router.py:319-349`, and asserted in
`.planning/phases/30-uploads-multimodal-a2/30-03-PLAN.md:116-117` /
`30-03-SUMMARY.md:67`)

**Issue:** `_drain_turn_images` moves images off the one-shot
`ectx.pending_turn_images` queue by **appending them permanently** onto
`ectx.run_images`:

```python
ectx.run_images = (ectx.run_images or []) + list(pending)
ectx.pending_turn_images = []
```

Only the staging queue (`pending_turn_images`) is cleared. `ectx.run_images` —
the list `RunImagesProvider.load()` actually reads on every dispatch
(`agents/capabilities/input_providers/run_images.py:41`) — is **never** reset,
filtered, or capped after being rendered once. The docstring and the phase plan
both explicitly claim this mirrors the `steering_notes` "consume-once" pattern
("drain-then-clear at the next dispatch... each attached image reaches exactly
the NEXT dispatch's HumanMessage"), but the sibling `steering_notes` seam
(`engine.py:6308-6325`) actually does the clear (`ectx.steering_notes = [n for n
in steering_notes if n.get("sticky")]`) — `_drain_turn_images` has no analogous
step. The result: once one image is drained, it is re-attached to **every**
subsequent dispatch of **every** `injects:[images]` agent for the rest of the
run, and more images just keep accumulating on top (unbounded growth, no cap
re-applied at the drain).

This is **not a hypothetical/dormant scenario**: `agents/prompts/prototype-specify/AGENT.md`
already declares `injects: [template, design_system, images]` and
`agents/workflows/prototype/workflow.yaml` already declares
`input_providers: [run_images]` — both pre-date this phase (no diff against
`e6b821db`) and `IMAGE_INPUT_ENABLED` defaults to `True`
(`app/core/config.py:143`). `prototype-specify` is a `gate: Human_Gate` step that
re-dispatches on every gate "redo" (the `while True:` loop at `engine.py:2686`).
Concretely: a user attaches an image on gate-redo #1 (via `POST
/messages` steering or via the original launch payload); that image is
correctly shown on redo #1. If the user then does redo #2 with **no** new image
and different instructions, the **stale image from redo #1 is still attached**
— because nothing ever removes it from `run_images`. Every further redo (with or
without a fresh image) keeps compounding the same list, silently feeding
increasingly stale/irrelevant image content into the model and inflating token
cost.

Empirically reproduced (drove the exact engine seam twice in sequence):

```
dispatch #1 blocks: [{'type': 'image', ..., 'data': 'AAAA'}]
dispatch #2 blocks (should be [] per "consume-once/next dispatch only"): [{'type': 'image', ..., 'data': 'AAAA'}]
```

No test in `test_run_message_images.py` or `test_input_providers_run_images.py`
drives two sequential dispatches, so this gap is untested.

**Fix:** Give `_drain_turn_images` (or `RunImagesProvider`) an actual
consume-once carrier distinct from the sticky launch-time `run_images`, e.g.:

```python
def _drain_turn_images(ectx) -> None:
    pending = getattr(ectx, "pending_turn_images", None)
    if not pending:
        ectx.turn_images_once = []   # nothing pending this dispatch
        return
    ectx.turn_images_once = list(pending)   # rendered ONCE, then dropped
    ectx.pending_turn_images = []
```

and have `RunImagesProvider.load()` compose `ctx.run_images + getattr(ctx,
"turn_images_once", [])`, with the engine resetting `ectx.turn_images_once = []`
immediately after `_compose_input_blocks` returns for that dispatch (mirroring
the `steering_notes` read-then-clear-non-sticky idiom exactly). Alternatively,
if per-turn images attached during a gate-redo are *intended* to persist across
that agent's own subsequent redos (arguably reasonable for `prototype-specify`
specifically), that should be an explicit, documented, tested design decision —
not an accidental byproduct of forgetting to clear a shared list.

## Medium

### WR-01: Filename-sanitization collisions in `POST /api/runs/{id}/files` silently overwrite a prior file in the same request, while the response reports both as successful

**File:** `backend/app/api/run_files.py:176-209`

**Issue:** Each validated file is written under `safe =
_safe_segment(os.path.basename(name), fallback="upload")`
(`sandbox.py:_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")`). Two distinct original
filenames that sanitize to the same segment (e.g. `invoice#1.txt` and
`invoice@1.txt` both → `invoice_1.txt`) cause the second file's write to
silently clobber the first's raw bytes + `.txt` sidecar, and the manifest
dict-merge (`manifest[safe] = {...}`) overwrites the first entry too — yet
`results.append(...)` still appends **both** entries to the response, each with
its own (misleading) `bytes`/`extracted_chars`.

Empirically reproduced in a single request:

```
POST /api/runs/{id}/files  files=[invoice#1.txt="FIRST FILE CONTENTS",
                                   invoice@1.txt="SECOND FILE CONTENTS - OVERWRITES"]
→ 200 {"files": [{"name": "invoice_1.txt", "bytes": 19, ...},
                  {"name": "invoice_1.txt", "bytes": 33, ...}]}
on disk .uploads/invoice_1.txt == b"SECOND FILE CONTENTS - OVERWRITES"
```

The caller receives a 200 claiming both files were stored; the first file's
content is gone with no error, warning, or distinguishing suffix.

**Fix:** Detect a within-batch collision on the sanitized `safe` name before
writing and disambiguate (`invoice_1.txt`, `invoice_1-2.txt`, …), or reject the
batch with a 409/400 naming the collision so the caller can rename and retry.

### WR-02: Unguarded manifest read-modify-write race across concurrent uploads to the same run

**File:** `backend/app/api/run_files.py:172-209` (`_read_manifest` → mutate
`dict` → `_write_bytes(manifest_rel, ...)`)

**Issue:** The manifest is loaded, merged with the new entries in memory, and
written back with a single non-atomic read-then-write. Two concurrent `POST
/api/runs/{id}/files` requests for the same run (e.g. two browser tabs, or a
client retry racing the original request) can both read the same manifest
snapshot, each append their own entries, and whichever write lands last wins —
the other request's raw file + `.txt` sidecar still land on disk, but its
manifest entry is lost. Since `uploaded_files.py`'s context provider drives
*entirely* off the manifest (not a directory listing), that document's
extracted text silently never reaches any agent, even though the endpoint
returned 200 for that request. There is no per-run lock or optimistic-concurrency
guard (e.g. compare-and-swap on a version/etag) anywhere in the write path.

**Fix:** Serialize manifest updates per run (an `asyncio.Lock` keyed on
`run_id`, or a file-lock on `manifest.json`), or make the update a true
read-merge-write retry loop that re-reads and re-merges on a detected
conflict.

### WR-03: Per-file/aggregate size caps are enforced only after the entire multipart part is buffered into memory

**File:** `backend/app/api/run_files.py:147-156`

**Issue:** `data = await upload.read()` reads the **entire** file into memory
with no length bound; only *after* the full read does the code check `len(data)
> _MAX_FILE_BYTES` and reject with 413. There is no streaming/chunked read with
an early-abort once the cap is exceeded. A caller can force the server to fully
materialize an arbitrarily large multipart part (bounded only by the ASGI
server / reverse proxy, if any) before the rejection fires. This is the same
pattern `file_extract.py` already had, but this new endpoint accepts up to 20
files per request, multiplying the exposure. This doesn't defeat any cap on
what's *accepted*, only widens the window for memory pressure from what's
*read*.

**Fix:** Read in bounded chunks (e.g. `while True: chunk = await
upload.read(64 * 1024); ...`) and abort with 413 as soon as the running size
exceeds `_MAX_FILE_BYTES`, instead of reading the whole body unconditionally
first.

### WR-04: Mid-run (`CHANNEL_STEERING`) per-turn images are validated, accepted, and durably logged, then silently dropped with a misleading 200 response

**File:** `backend/app/api/run_commands.py:350-362, 474-489, 559-575`

**Issue:** `_live_ectx_for_run(run_id)` unconditionally `return None`s (the
DEF-29-09-1 deferred wiring), so `apply_turn_images(_live_ectx_for_run(run_id),
validated_turn_images)` (line 575) is **always** a no-op for any image attached
to a turn on an already-`running` pipeline: `getattr(None,
"pending_turn_images", None)` is `None`, so `apply_turn_images` returns
immediately. The image never reaches the live engine. Yet:

- The image was already cap/vision-validated (real work, real 400s on bad
  input).
- The turn is durably persisted with a `{"kind":"image","retained":false}` ref.
- The endpoint returns `200 {"channel": "steering", ...}` — indistinguishable
  from a turn whose image *was* actually delivered.

A caller has no signal that their attached image was accepted-and-discarded
rather than delivered. This is explicitly documented as deferred in code
comments, but the response contract doesn't communicate the limitation to API
consumers, which risks a confusing "why didn't the agent see my screenshot"
support issue once the frontend starts allowing mid-run image attachments on
this channel.

**Fix:** Until the live-ectx handle lands, either (a) add an explicit field to
the response (e.g. `"image_delivered": false`) when `validated_turn_images` is
non-empty but the live handle is unavailable, or (b) reject mid-run image
attachments at the API layer (e.g. 501/409) rather than silently accepting them,
so the frontend can surface an honest state instead of a false "steering"
success.

## Low

### IN-01: `StartingPointCard`'s new `attachmentRefs` / "image not retained" placeholder is unit-tested but unreachable in the live UI

**File:** `frontend/src/components/results/StartingPointCard.tsx:23-31, 43-58,
251-263`; the only production call site,
`frontend/src/components/results/AgentThinkingTab.tsx:618-622` and `:652-656`,
never passes `attachmentRefs`.

**Issue:** The new optional prop and its rendering branch are fully covered by
`StartingPointCard.test.tsx`, but no real caller threads a reopened run's
persisted attachment refs into it, so end users will never see the "image not
retained" placeholder this phase adds. This may be intentional incremental
wiring (a later phase presumably threads the reopen-fetched refs through
`AgentThinkingTab`), but as merged it's dead code in production.

**Fix:** Either wire `attachmentRefs` from the reopened run's persisted
`chat_message` attachment refs into `AgentThinkingTab` → `StartingPointCard`
now, or note the remaining wiring explicitly as a tracked follow-up so it isn't
mistaken for a completed end-to-end feature.

### IN-02: Duplicate defensive manifest-parsing logic between the app-layer writer and the kernel-pure reader

**File:** `backend/app/api/run_files.py:218-233` (`_read_manifest`) vs.
`backend/agents/capabilities/context_providers/uploaded_files.py:113-128`
(`UploadedFilesProvider._read_manifest`)

**Issue:** Both modules independently implement "read `.uploads/manifest.json`,
`json.loads`, degrade to `[]`/`{}` on any parse error or non-list shape." This
appears to be a deliberate consequence of the import-purity boundary (the
kernel-pure capability must not import the app-layer sandbox module), so it is
not obviously fixable without weakening that boundary — flagging only as a
maintainability note: a future change to the manifest schema must be kept in
sync by hand across the two implementations, with no shared test guaranteeing
that.

**Fix:** No action required beyond a code comment cross-referencing the sibling
implementation (already partially present); consider a shared, tiny stdlib-only
helper module both could import if a third consumer ever appears.

---

_Reviewed: 2026-07-08_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
