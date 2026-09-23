# Spec 019 — PDF extraction: materialise a document into pages an agent can read

**Plans**: [spec.md](spec.md) · **Decisions**: [research.md](research.md) · **On-disk contract**: [contracts/on-disk-format.md](contracts/on-disk-format.md)
**Covers**: all 37 functional requirements — see [Requirement coverage](#requirement-coverage). A requirement added to the spec without a phase here means this plan is stale.

## Goal

Turn an uploaded PDF into a folder of pages an agent can actually work with: layout-aware text
with `@[[image-N.png]]` placeholders in reading order, and one cropped image per picture that
**keeps the annotation arrows** the embedded image throws away. Granted by one line of
`AGENT.md` frontmatter. Images reach the model through the `input_provider` port that already
ships.

`pypdf` and `pdfplumber` are already pinned or resolvable; `pypdfium2` arrives free as a
`pdfplumber` dependency. The tool-binding pattern shipped in spec 017 and the `spec.tools`
grant in spec 018. What is missing is the materialiser, the reserved prefix it writes to, and
one new input provider.

## The one decision that shapes everything

**`image-N.png` is a crop of the RENDERED page, not the embedded image.**

Everything else follows. The measurement (spec §3.1): page 2's screenshot carries four red
arrows and a circle identifying which controls to click; extracted as an embedded image it has
none of them, because they are PDF vector overlays drawn on top. The prose says *"search for
the policy under Specialty Accounts"* and the arrows say **which field** — so embedded
extraction silently deletes the instruction and hands the model a form where every field looks
equally important.

Spec `014` chose embedded images and explicitly rejected rendering. This reverses that.

Three consequences, all non-negotiable:

1. Every picture comes out of the render, so **`pypdfium2` is on the critical path** — and
   PDFium is not thread-safe (§3.4: threads crash the process, exit 133). Parallelism is
   processes or nothing.
2. Position comes from `pdfplumber` (`page.images` carries bbox and stream together) and pixels
   come from the render. **One library for geometry** — `pypdf` and `pdfplumber` disagree on
   image count (67 vs 66), so indices are not portable between them.
3. The output is files, not tool return values. That matches both shipped visual specs
   (`playwright_take_screenshot`, `screenshot_pptx` both write and return text) and it is what
   lets the `pdf_pages` provider deliver images through the port `run_images` already uses.

## The spec's open items, now closed

All three resolved in [research.md](research.md) before planning:

- **Dedupe — not built.** Measured: perfect dedupe saves 541 tokens, **2%** of image tokens.
  The logo crops to 34 tokens. FR-005b and RISK-02 are struck from the spec.
- **`.pdf/` is listed but not delivered**, the `.verify/` / `.browser/` asymmetry.
- **4 processes above ~30 pages**, both conservative under measured benchmark noise.

## Requirement coverage

Every FR maps to exactly one phase. This is the staleness check: an FR in the spec with no row
here, or a row naming an FR the spec no longer has, means one of the two documents moved without
the other.

| Phase | Requirements |
|---|---|
| **1 — materialiser, offline** | FR-001, FR-002 (libraries) · FR-003 (extract + receipt) · FR-004, FR-004a (interleave, audit comments) · FR-005, FR-005a, FR-005b (crop-of-render, fragment merge, **no dedupe**) · FR-006 (`document.md`, `manifest.json`) · FR-007, FR-007a, FR-007b (folder-is-state, atomic rename, bias-to-redo) · FR-008, FR-008a (`source_sha256`, slug + `path_for`) · FR-009, FR-009a, FR-009b (`pdf_info`, printed threshold, outline) · FR-010 (`pdf_find`) · FR-011 (`pdf_page_image`) · FR-020 (never raises) |
| **2 — binding** | FR-015 (provider, import purity) · FR-016 (`spec.tools`, `manifest.py` untouched) · FR-017 (byte-identical when ungranted) · FR-018 (`.pdf/` reserved) · FR-019 (`path_for` end to end) · FR-021 (source gone ⇒ say so) · FR-024 (don't also declare `injects:[uploaded_files]` — authoring guidance, no code) · FR-025 (nothing outside the budget) |
| **3 — delivery** | FR-012, FR-012a, FR-012b (`pdf_pages` provider, no per-step args, downscale to ceilings) |
| **4 — parallelism** | FR-013, FR-013a, FR-013b (processes, chunked, page threshold) · FR-014 (off the event loop) |
| **5 — sidecar fix** | FR-022 (page correspondence) · FR-023 (ImportError logs distinctly) |

FR-019, FR-020 and FR-025 are cross-cutting; they are listed at the phase where they first become
assertable, and every later phase inherits them.

## Pipeline

```
 upload (built)         AGENT.md: tools: [pdf]
      |                          |
      v                          v
 .uploads/doc.pdf  ------>  pdf_extract ---- asyncio.to_thread ----+
                                 |                                 |
                                 |                     ProcessPoolExecutor(4)
                                 |                     only if pages > 30
                                 v                                 |
                    for each page, in a TEMP dir  <----------------+
                      pdfplumber: text + image bboxes
                      pypdfium2 : render page
                      crop render at each bbox, merge contiguous
                      write text.md + image-N.png
                                 |
                          os.rename(tmp -> pages/NN)     <- atomic; exists == complete
                                 |
        +------------------------+------------------------+
        |                                                 |
  agent read_file text.md                        injects: [pdf_pages]
  (prose + @[[...]] holes)                                |
                                                          v
                                              engine composes REAL image
                                              blocks into the step prompt
```

## NEW files (3)

| File | What |
|---|---|
| `backend/app/agents/tools/pdf_tools.py` | `make_pdf_tools(sandbox)` → `pdf_extract`, `pdf_info`, `pdf_find`, `pdf_page_image`. Owns rendering, cropping, fragment-merge, reading-order interleave, temp-dir+rename, the process pool. Lazy imports. |
| `backend/agents/capabilities/tools/pdf.py` | `@register("tool", "pdf", user_allowed=True)`. Emits the four string KEYS, `exclude_builtin=False`. Imports only the registry decorator — no `app.*`, no PDF library. |
| `backend/agents/capabilities/input_providers/pdf_pages.py` | `@register("input_provider", "pdf_pages", user_allowed=True)`. Satisfies `InputContentProvider` (`name` + `async load(ctx) -> list`). Reads `.pdf/` off the run sandbox, returns image content blocks. Registry + stdlib only. |

## MODIFIED files (5)

| File | Change | Why |
|---|---|---|
| `backend/agents/capabilities/registry.py` | add `("tool", "pdf")` and `("input_provider", "pdf_pages")` to `_KNOWN`; add both module paths to the discover list | `_KNOWN` is the compiler's INV-4 membership surface; a name absent from it cannot be referenced by a manifest |
| `backend/agents/capabilities/tools/__init__.py` | `from agents.capabilities.tools import pdf  # noqa: F401` + `__all__` | registration is an import side effect. **Spec 018 forgot this file in its plan and recorded it as a deviation** — listing it here is that lesson applied |
| `backend/agents/capabilities/input_providers/__init__.py` | same import side effect; correct the docstring's *"The sole provider this wave: run_images"* | it will no longer be sole |
| `backend/agents/factory.py` | in `_resolve_custom_tool_keys`, resolve the four `pdf_*` keys via `make_pdf_tools(sandbox)`, mirroring the playwright branch at ~1094 | the factory is the composition root; `sandbox` is **already** threaded (spec 017/018) — `014`'s "highest-risk edit" is already done |
| `backend/app/agents/sandbox.py` | add `_PDF_PREFIX = ".pdf/"`; add to the `is_deliverable_relpath` exclusion tuple; **leave it visible to `list_files`**; correct the `.agent_outputs/` comment claiming it is the only listed-not-delivered prefix | without the exclusion every extracted PNG ships in `WorkflowRun.output` — the trap spec 018 hit with `.browser/` |

## MODIFIED files — the pre-existing defect (1)

| File | Change | Why |
|---|---|---|
| `backend/app/api/file_extract.py` | `_extract_pdf` must preserve page correspondence (currently drops empty pages from the join, so sidecar page *N* ≠ document page *N*); `ImportError` logs at ERROR distinct from a parse failure | FR-022/FR-023. **This changes brief content for every existing PDF upload** (RISK-05) — it is the correct fix and it is not free. Flag at the checkpoint before applying. |

## NEW tests (2)

| File | Covers |
|---|---|
| `backend/tests/agents/test_pdf_tools.py` | reading-order interleave; fragment merge on contiguous bboxes; crop-vs-embedded (the arrows must survive); temp-dir+rename atomicity; resume skips complete pages and redoes an interrupted one; `source_sha256` staleness discard; traversal refusal; every failure returns text and never raises |
| `backend/tests/agents/test_pdf_pages_provider.py` | the provider returns image blocks when the step declares the inject and `[]` when it does not; dormancy when `.pdf/` is absent |

## MODIFIED tests (1)

| File | Change |
|---|---|
| `backend/tests/agents/test_create_runner.py` | add the ungranted-agent assertion (FR-017: composed tool set byte-identical). The existing `test_tool_provider_*` snapshots must pass **unchanged** — updating them to go green is exactly how a real regression gets papered over |

## GRANTED (0 in this spec)

No `AGENT.md` is edited here. The tools are grantable; which agent gets them is a
workflow-authoring decision and belongs to the pipeline that consumes this feature.

## REUSED unchanged

`RunSandbox.path_for` (traversal safety) · the `InputContentProvider` port and
`_compose_input_blocks` · the `spec.tools` grant path · `_resolve_custom_tool_keys`'s existing
`(keys, ctx, sandbox, agent_id)` signature · `pdfplumber`/`pypdf`/`pypdfium2` as installed ·
UPLD-01's upload endpoint and every one of its caps.

## Explicitly UNTOUCHED

`backend/agents/workflows/manifest.py` — the `spec.tools` route means the `{"internet"}`
literal is never approached, and `014`'s RISK-03 never arises · `agents/execution_engine/**` ·
`agents/workflows/compiler.py` · `app/api/run_files.py` (no new ingress) ·
`context_providers/uploaded_files.py` (FR-024 governs the interaction by declaration) ·
`app/api/capabilities.py` (the palette enumerates the registry live) · the frontend, entirely.

## Change budget

```
NEW              3 source + 2 test files
MODIFIED         6 source + 1 test file
DELETED          0
DB migrations    0
new dependencies 0        (pypdfium2 arrives via pdfplumber; do NOT pin it)
apt-get layers   0
AGENT.md edits   0
frontend files   0
```

Anything outside this budget is a deviation and gets recorded in `tasks.md`, not absorbed.

## Phases and checkpoints

**Phase 1 — the materialiser, offline.** `pdf_tools.py`'s pure functions: reading-order
interleave, fragment merge, crop geometry, temp-dir+rename, manifest and staleness. No
registry, no factory, no sandbox wiring.
→ **Checkpoint A**: `test_pdf_tools.py` green, and the materialised output for the real
document matches `.reference/tmp/materialized/` — which is the reference implementation this
phase is reproducing, not inventing.

**Phase 2 — binding.** Capability module, registry entries, `__init__` side effects, factory
resolution, `.pdf/` reserved prefix.
→ **Checkpoint B**: a granted agent has the four tools; an ungranted one's tool set is
byte-identical to the pre-change snapshot; `import-linter` still reports
`agents.capabilities ↛ app` clean; nothing under `.pdf/` reaches the deliverable.

**Phase 3 — delivery.** The `pdf_pages` input provider.
→ **Checkpoint C**: a step declaring the inject receives image content blocks; one not
declaring it receives none; absent `.pdf/` is dormant.

**Phase 4 — parallelism.** Process pool behind the page threshold, wrapped in
`asyncio.to_thread`.
→ **Checkpoint D**: a >30-page document materialises across processes; the 21-page document
still runs sequentially; the event stream keeps flowing throughout; no thread ever touches
PDFium.

**Phase 5 — the sidecar fix (FR-022).** Held to last **on purpose**: it is the only change
whose blast radius reaches existing workflows.
→ **Checkpoint E**: page correspondence holds, and the brief-content change is shown to the
user before it is considered done.

## Risks and failure modes

- **Threading PDFium kills the backend worker**, not the call — exit 133, no traceback, no
  catch. The single most dangerous line anyone could add to this feature is a
  `ThreadPoolExecutor`. FR-013 exists to forbid it and Phase 4's checkpoint exists to prove it.
- **Forgetting `.pdf/` in `is_deliverable_relpath`** ships megabytes of scaffolding into
  `WorkflowRun.output`, silently. Spec 018 hit this with `.browser/`.
- **Updating the characterization snapshots to go green** would hide a real tool-set
  regression. FR-017 asks for them *unchanged*, not *passing*.
- **The sidecar fix changes existing briefs.** Phase 5, checkpoint, user sees it.
- **First `ProcessPoolExecutor` in the repo** — spawn cost, memory per worker, orphaned
  children on cancellation. New operational surface, gated behind a page threshold so it stays
  off the common path.
- **Every number here comes from one 21-page Word-generated document** (spec RISK-03). A
  400-page scanned document invalidates the OCR decision, the threshold and the cost model at
  once.

## Deferred

- Fixing the severed fan-out lever (`agentToManifestStep` hardcodes `single_shot`), which is
  what a per-image vision fan-out would need. This feature's artifacts support it when it lands.
- Per-step scoping for `pdf_pages`. Input providers receive `ctx` and take no per-step
  arguments (spec FR-012a), so "this worker gets page 4's images" needs scope derived from step
  state. Not needed by a single looping vision agent, which is what runs today.
- OCR. Out of scope, and confirmed unnecessary on the target document.
- DOCX/PPTX equivalents — they reuse this provider and grant.
- Image dedupe — measured at 2%, revisit only if a document makes it double-digit.
