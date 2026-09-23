# Feature Specification: File extract support — materialise a document into pages an agent can actually read

**Spec ID**: 019-file-extract-support
**Created**: 2026-08-28
**Status**: IMPLEMENTED — PDF scope in `16b45d106`, Office scope (`.docx` / `.xlsx` / `.pptx`) alongside this revision. Every Office cost figure remains **UNMEASURED** (no representative document); the `.xlsx` page ceiling and the image-size estimate are the two to confirm first
**Root**: `backend/app/agents/tools/pdf_tools.py`, `backend/agents/capabilities/tools/pdf.py`, `backend/agents/capabilities/tools/__init__.py`, `backend/agents/capabilities/input_providers/pdf_pages.py`, `backend/agents/factory.py`, `backend/app/agents/sandbox.py`, `backend/app/api/file_extract.py`, `backend/agents/prompts/<granted-agent>/AGENT.md`
**Grounding**: spec [018](../018-agent-browser-tools/spec.md) + [FIX-323](../../.knowledge/cards/20260827-0946-FIX-323.md) — the per-step `spec.tools` grant, and the write-to-disk-return-text tool shape · spec [017](../017-ppt-v2-pptx/spec.md) + [FIX-321](../../.knowledge/cards/20260827-0054-FIX-321.md) — sandbox-bound tool sets · `agents/capabilities/input_providers/run_images.py` — the only working image→model path in this codebase · UPLD-01 / UPLD-03 — upload and the sticky-text provider · the retired `014-pdf-tools` draft, whose central decision this spec **reverses on measured evidence**
**Evidence**: every figure in §3 was measured on the real target document, `.reference/Alliance/Inland Marine Creating a Quote 2.pdf`. The scripts are committed at `.reference/tmp/_run.py`, `_interleave.py`, `_materialize.py` and are re-runnable; their output is in `.reference/tmp/`.

---

## Clarifications

### Session 2026-08-28

Decisions taken in conversation, each with the reason it is not recoverable from the code.

- **Q: Grant per workflow (`capabilities: {pdf: true}`) or per step (`AGENT.md tools: [pdf]`)?**
  **A: Per step**, the spec 018 route. `014` chose the workflow-wide flag, which requires generalising `manifest.py`'s hardcoded `set(capabilities.keys()) != {"internet"}` and thereby widens what any user-authored manifest may declare — `014`'s own RISK-03. `spec.tools` is not the `capabilities` block, so **no `manifest.py` change is needed** and that risk never arises. It also stops every step in a pipeline paying tool-description cost when one step reads PDFs.

- **Q: Do the tools return content to the model, or write to disk?**
  **A: Write to disk, return a receipt.** Both shipped visual specs already do this — `playwright_take_screenshot` writes a PNG to `.browser/` and returns text; `screenshot_pptx` renders slides into the workspace and returns text. **No tool in this codebase returns an image**, and the one mechanism that does put images in front of a model is the `input_provider` port (`run_images`). Building on that retires `014`'s largest unproven assumption outright (see RISK-01, now closed).

- **Q: Embedded images, or rendered pages?**
  **A: Crops of the RENDERED page. This reverses `014` on measured evidence.** `014` returned embedded images and explicitly rejected rendering. On the real document that silently destroys the instruction — see §3.1. Cropping the render to each image's bounding box keeps the annotation layer, frames tightly, and costs **2.9× less** than rendering whole pages.

- **Q: How do text and images stay paired?**
  **A: `text.md` interleaves `@[[image-N.png]]` placeholders in true reading order**, derived from vertical position. Verified end to end on page 2: every instruction lands immediately above the screenshot it refers to.

- **Q: Where does resume state live?**
  **A: In the folder itself.** A page directory exists ⇔ that page is done. No cache file, no progress record — `set(range(1, pages+1)) − set(existing_dirs)` is the remaining work. This deleted an entire subsystem from the earlier draft.

- **Q: Multi-threading?**
  **A: Never threads. Processes, above a page threshold.** Measured: `pdfplumber` text extraction is pure Python and gains **0.99×** on 4 threads; `pypdfium2` rendering across threads **crashes the process** (exit 133, SIGTRAP, no traceback — PDFium is not thread-safe). Processes give each worker its own GIL and its own PDFium instance and do work. See §3.4.

- **Q: OCR?**
  **A: Out of scope — confirmed by the user, and now confirmed by measurement.** The target document is Word-generated with a real text layer on every page (minimum 404 characters). No page needs OCR. The absence is made safe rather than assumed away: `pdf_info` reports a per-page text-layer verdict, and a page whose meaning is visual is reachable as a rendered crop regardless.

- **Q: `user_allowed`?**
  **A: `True`.** Unlike `playwright` (`False`, file manifests only), reading a document the user uploaded to their own run is not privileged.

---

## 1. Problem

A user uploads a large PDF to a run. The bytes land in the sandbox, `pypdf` pulls the text out **once** at ingest, and that flat string is stapled into the brief. From then on the document is a fixed block of text: no second question, no single page, no page numbers, and nothing outside the text layer.

For the target document class that is not a limitation, it is a wall. **Measured on the real document: 21 pages carry 16,843 characters — about 800 per page — and 67 embedded images.** The text layer alone is roughly 4,200 tokens and reads like scaffolding with the content removed: *"In Spinnaker, search for the policy under Specialty Accounts"* followed by nothing, where the screenshot showing **which** control to click has been dropped.

**The obvious fix does not work here, and the reason is structural.** A PDF *skill* would hand the agent a script to run, and **no agent in this runtime can execute code** — `grep -rniE "def (bash|shell|run_python|execute_code)|BashTool|subprocess"` over the entire tool surface returns zero hits, and `scripts/skills_audit.py` flags any skill body telling an agent to invoke an `execute` tool. That is deliberate. The upstream PDF skill this work began from is, here, documentation an agent can read and cannot act on — and its `LICENSE.txt` prohibits redistribution besides.

So the capability arrives as **tools the backend runs on the agent's behalf**, in the shape specs 017 and 018 have both shipped.

## 2. What it does

**A `pdf` tool set, granted per step**, that **materialises** a document into a folder of pages, and an **input provider** that puts those pages' images in front of a model.

**`pdf_extract(path, pages="")` — the materialiser.** Renders each page, extracts layout-aware text, crops every picture out of the render, merges fragments, and writes:

```
.pdf/{slug}/pages/NN/text.md        text with @[[image-N.png]] in reading order
.pdf/{slug}/pages/NN/image-N.png    a CROP OF THE RENDER at that picture's bbox
.pdf/{slug}/document.md             every page, one file
.pdf/{slug}/manifest.json           source_sha256, page count, page→image map
```

It returns a **receipt**, not content — page count, image counts, character count, estimated cost — so the agent can decide what to do next without spending the document's whole budget finding out.

**`pdf_info(path="")` — what am I holding?** Inventory of every upload, or a profile of one: page count, **per-page** text-layer verdict, character density, image counts, encryption state, provenance metadata, outline where present, and an estimated reading cost. Cheap, and it never materialises anything.

**`pdf_find(query, path="")` — where is it?** Searches the materialised `text.md` files, returning document, page and surrounding context — output shaped to feed straight into the next call's page argument.

**`pdf_page_image(path, page)` — show me the whole page.** One page rendered entire, for when the cropped pictures are not the question: a full-page diagram, a layout that only reads as a whole, a page whose text extraction is untrustworthy.

**`pdf_pages` — the input provider.** A step declares `injects: [pdf_pages]` and the engine composes the materialised page images into that step's prompt as real image content blocks, using the same `InputContentProvider` port `run_images` already satisfies. **This is the only mechanism in this codebase that puts an image in front of a model**, and using it is what makes the visual half of this feature provable rather than hoped-for.

```
 upload (UPLD-01, built)              AGENT.md: tools: [pdf]
        |                                      |
        v                                      v
 .uploads/doc.pdf  ------------------>  pdf_extract  (materialiser)
                                               |
                                               v
                              .pdf/{slug}/pages/NN/text.md
                                                   /image-N.png
                                               |
        +--------------------------------------+
        |                                      |
   read_file text.md                     injects: [pdf_pages]
   (agent sees the prose and                    |
    @[[image-3.png]] holes)                     v
                                        engine composes REAL image
                                        blocks into the step's prompt
                                        (same port as run_images)
```

The agent reads `text.md` and gets a complete, correctly-ordered document where each instruction is followed by a labelled hole; the provider hands it the pictures that fill them. `read_file` on a PNG returns binary garbage, so the placeholder is a marker, never a link.

## 3. Measured evidence

Everything below was measured on `.reference/Alliance/Inland Marine Creating a Quote 2.pdf` — 21 pages, 1.1 MB, `Microsoft® Word für Microsoft 365`, created 2022-05-16, not encrypted, **outline: 0 entries**.

### 3.1 The finding that reversed the design

Page 2's rendered image shows the Spinnaker search screen carrying **four red arrows and a red circle** — pointing at *My Accounts*, circling *Search*, marking the *Type of search* dropdown and the *Account Name* field. The prose says "search for the policy under Specialty Accounts"; the arrows say **which controls**.

The same screenshot extracted as an embedded image (`embedded-2.png`, 1035×574) is pixel-clean and **has no arrows and no circle**. They are PDF vector overlays drawn on top of the image, not part of it.

**So embedded extraction silently deletes the instruction** and hands the model a form where every field looks equally important. `014` chose embedded images and rejected rendering; for this document class that is backwards. A crop of the render at the same bounding box was verified to contain every annotation.

### 3.2 Fragmentation is real

Page 2 reports 5 image objects but shows 4 visual regions. `embedded-5.png` (953×66) is the bottom two rows of the *Account Transactions* table — one screenshot stored as two XObjects, split at an arbitrary seam. Page 3 repeats the same 954×144 + 953×66 pair.

**The detection rule fell out of the data**: image 4 ends at `bottom=671.0` and image 5 begins at `top=671.0` — exactly contiguous, overlapping x-range. Merging adjacent boxes on that rule collapsed **10 fragments across the document (67 → 57)**.

### 3.3 Cost of reading the whole document

```
                                          tokens
text layer only                          ~4,200     cheap, and not enough
embedded images (deduped)               ~15-20k     wrong: no annotations
cropped images (merged + deduped)       ~18,569     correct
full-page renders @2.0                  ~54,285     correct, 2.9x the crops
------------------------------------------------
TOTAL SHIPPED  crops + text             ~22,337
```

The whole 21-page document fits in one context. **Page-range bounds matter far less for documents this size than the earlier draft assumed**, and crops beat whole-page rendering on both accuracy of framing and cost.

Render legibility was verified directly: at scale 2.0 (1224×1584) the page, including small table text, was read without difficulty.

### 3.4 Parallelism

```
THREADS
  pdfplumber text, 4 threads            0.99x       pure Python, GIL-bound
  pypdfium2 render, 4 threads           CRASH       exit 133 (SIGTRAP), no traceback

PROCESSES (chunked: each worker takes a contiguous range, opens the doc once)
  21-page real document
    sequential            2.67s   (127.1 ms/page)
    2 processes           1.03s   2.60x
    4 processes           0.78s   3.44x
    8 processes           0.64s   4.20x
  100-page synthetic document
    sequential            6.96s   ( 69.6 ms/page)
    4 processes           2.00s   3.48x
```

`pypdfium2` is not thread-safe and rendering across threads kills the **process**, not the call — in the backend that takes down the worker and every concurrent run on it.

**Measurement noise is real and is recorded rather than hidden**: an earlier run of the same benchmark on the same document reported 2.15× at 4 workers where this one reports 3.44×. The direction is solid; the magnitude is approximate.

### 3.5 What is already true in the runtime

| Fact | Source |
|---|---|
| No code-execution tool exists anywhere | `grep` over `app/agents/tools/` + `agents/capabilities/tools/` → 0 hits |
| **No tool returns an image**; `playwright_take_screenshot` and `screenshot_pptx` both write to disk and return text | `app/agents/tools/playwright.py`, `pptx_tools.py` |
| `run_images` is an `input_provider` returning real `{"type":"image",…}` blocks, composed by `_compose_input_blocks` | `capabilities/input_providers/run_images.py` |
| `input_providers` are declared at **workflow** level and gated **per step** on `set(spec.injects) ∪ set(step.injects)`; they receive `ctx` and take **no per-step arguments** | `manifest.py:295`, `engine.py:10804-10812` |
| `playwright` is granted by `spec.tools`, not a capability flag — `manifest.py` is not involved | `factory.py:1094` |
| `manifest.py` still hardcodes `set(capabilities.keys()) != {"internet"}` | `manifest.py:324` |
| `_resolve_custom_tool_keys(keys, ctx, sandbox, agent_id)` already threads the sandbox — `014`'s "highest-risk edit" is **already done** | `factory.py:1010` |
| Reserved, deliverable-excluded prefixes are `.uploads/ .logs/ .verify/ .browser/ .agent_outputs/` | `sandbox.py:41-67, 423-443` |
| `pypdfium2` is a **hard dependency of `pdfplumber`** (`Requires: pdfminer.six, Pillow, pypdfium2`) | `pip show pdfplumber` |
| `_extract_pdf` joins page text with empty pages **dropped**, so sidecar page *N* ≠ document page *N* | `file_extract.py` |
| The repo uses `asyncio.to_thread` for blocking work; there is **no `ProcessPoolExecutor` anywhere** | `main.py:202`, `handoff_pipeline.py` |

## 4. User Scenarios & Testing *(mandatory)*

### Primary user story

A user attaches a 21-page underwriting walkthrough and asks for the quoting procedure to be extracted. The extractor agent calls `pdf_extract`, which materialises 21 page folders in about a second and returns a receipt: *21 pages, 50 images, ~22,000 tokens to read whole*. The agent reads `document.md` and sees every instruction followed by a labelled hole. A vision step declaring `injects: [pdf_pages]` receives the page images as real content blocks and fills each hole with what the screenshot shows — including the red arrow that identifies the control the prose only gestures at. The procedure it produces cites page numbers a human can check against the original.

### Acceptance scenarios

1. **Given** an uploaded PDF and an agent granted `tools: [pdf]`, **when** it calls `pdf_extract`, **then** `.pdf/{slug}/pages/NN/` exists for every page, each with `text.md`, and the tool returns a receipt naming page and image counts and an estimated cost — not document content.
2. **Given** a page with prose, screenshot, prose, screenshot, **when** its `text.md` is read, **then** the placeholders appear **between** the prose blocks in the order the page presents them, never batched at the end.
3. **Given** a page carrying annotation overlays, **when** its `image-N.png` is inspected, **then** the annotations are present.
4. **Given** two image objects that are vertically contiguous with overlapping x-range, **when** the page is materialised, **then** they become **one** image and one placeholder.
5. **Given** a step declaring `injects: [pdf_pages]`, **when** it is dispatched, **then** its prompt carries the materialised images as image content blocks.
6. **Given** a partly-materialised document, **when** `pdf_extract` runs again, **then** only the missing pages are processed and completed pages are untouched.
7. **Given** extraction interrupted mid-page, **when** it runs again, **then** the interrupted page is **redone**, because an incomplete page directory never became visible.
8. **Given** a document already materialised, **when** a **different** file is uploaded under the same name, **then** the stale folder is discarded rather than served.
9. **Given** an agent **not** granted `tools: [pdf]`, **when** its runner is composed, **then** no pdf tool is bound and the composed tool set is byte-identical to the pre-change snapshot.
10. **Given** a path escaping the run root, **when** any tool is called with it, **then** an error string is returned, nothing is read or written, and no exception reaches the graph.
11. **Given** a document above the page threshold, **when** it is materialised, **then** the work runs across processes and the run's event stream keeps flowing throughout.

### Edge cases

- **A run with no uploads.** `pdf_info` says so plainly rather than returning an empty list that reads like a failed call.
- **Non-PDF uploads** (`docx`, `pptx`, `txt`, `md`, `csv`, `json` are all accepted by UPLD-01) are listed as present and unreadable by these tools; omitting them lets an agent conclude they were never uploaded.
- **Encrypted PDFs** — openable-with-empty-password, genuinely locked, and corrupt are three states and must be reported as three.
- **A resumed run on a wiped sandbox.** The `.txt` sidecar survives via the `artifact_refs` mirror; the PDF bytes and `.pdf/` may not. Say the source is gone, don't report it as missing.
- **A page with no images** — `text.md` with no placeholders, and no empty image files.
- **A page with no text** — placeholders only; `pdf_info`'s per-page verdict is what tells the agent this was expected.
- **A picture spanning a page break.** Materialisation is page-scoped; reassembly across pages is not attempted and must not be silently implied.
- **Two agents in one run extracting concurrently** (a fan-out step).
- **A common search term.** `pdf_find("the")` caps its hits and says it capped them.
- **A malformed page range** — `9-3`, `0`, `999999`, `4,,7`.

## 5. Requirements *(mandatory)*

### Functional Requirements

**Libraries**

- **FR-001** Two direct PDF libraries: **`pypdf`** for structure (page count, metadata, outline, encryption state) and **`pdfplumber`** for layout-aware text *and* for image bounding boxes — `page.images` carries position and stream together, so position and pixels come from one library and there is no cross-library index to mismatch. **`pypdfium2` supplies rendering and is NOT added to `requirements.txt`**: it is already a hard dependency of `pdfplumber`, and a direct pin would assert a version contract the project does not control.
- **FR-002** No OCR engine, no `reportlab`, no `qpdf`. `pdftotext -layout` is rejected despite comparable output because it needs poppler in the image.
- **FR-002a** For the **PDF path only**, no `apt-get` layer: every PDF library above is pure-Python-installable. FR-027 amends this for LibreOffice, and for nothing else — the prohibition still binds OCR, poppler and `qpdf`.

**Materialisation**

- **FR-003** `pdf_extract(path, pages="")` materialises the document into `.pdf/{slug}/` and returns a **receipt** — pages processed, pages skipped as already present, image counts before and after merge and dedupe, character count, estimated tokens to read whole. It never returns page content.
- **FR-004** Per page it writes `text.md`: layout-aware text and `@[[image-N.png]]` placeholders **interleaved in reading order**, derived by sorting text lines and image bounding boxes on vertical position. Placeholders are never batched at the end.
- **FR-004a** Each placeholder carries an inline comment naming the image's pixel dimensions and how many source objects it came from, so the output can be audited while being read.
- **FR-005** `image-N.png` is a **crop of the rendered page** at the picture's bounding box — **not** the embedded image. §3.1 is the evidence: the embedded image loses the annotation overlays that carry the instruction, and the crop keeps them while framing more tightly and costing 2.9× less than a whole-page render.
- **FR-005a** Adjacent image boxes that are vertically contiguous (gap ≤ a small constant) with overlapping x-ranges are **merged into one** crop and one placeholder. Measured: 10 merges across the target document.
- **FR-005b** **Image dedupe is NOT built** — resolved in [research.md](research.md) R-01 by measurement. Pricing all 50 materialised crops: perfect dedupe would save **541 tokens, 2% of image tokens** (2.4% of the document). The repeated logo crops to 262x98 = **34 tokens**; the expensive images are screenshots, and screenshots are unique. Every exact method available carries a correctness bug — hashing the embedded stream collapses **the same screenshot bearing different annotations**, which is the content this feature exists to preserve — and paying that risk for 2% is the wrong trade. Writing each crop once per page is all that ships; incidental repeats are acceptable.
- **FR-006** `document.md` concatenates every page with page markers; `manifest.json` records `source_sha256`, page count, and the page→image map.

**Resume and identity**

- **FR-007** **The folder is the state.** A page directory exists ⇔ that page is complete. Remaining work is `set(range(1, pages+1)) − set(existing page dirs)`. There is no cache file and no progress record.
- **FR-007a** A page is materialised into a temporary directory and moved into place with a single atomic rename. A page directory therefore exists **only if it is complete**, by construction — no marker file to forget, no partial state to interpret. This also makes concurrent extraction safe: two workers racing the same page each build their own temp directory and one rename wins, with identical content either way.
- **FR-007b** Bias toward redo. Re-materialising a complete page is cheap; skipping an incomplete one is a silent wrong answer that reaches the deliverable.
- **FR-008** `manifest.json` carries `source_sha256`. On open, a hash mismatch means the whole folder is stale and is discarded — uploads dedupe by **filename**, so a re-upload under the same name would otherwise be served the previous document's pages.
- **FR-008a** The slug is derived from the filename, sanitised, and every write resolves through `RunSandbox.path_for`. A human-readable path is deliberate — being able to open the folder and look is half the value of this design.

**Reading**

- **FR-009** `pdf_info(path="")` inventories every upload in a **stable, sorted order**; with a path it profiles one document: page count, **per-page** text-layer verdict, character density, image count, encryption state distinguished into openable/locked/unparseable, metadata, outline where present, and estimated reading cost. It materialises nothing.
- **FR-009a** The text-layer threshold is printed **alongside the raw per-page character count**, so a model can disagree with it.
- **FR-009b** Outline reporting is retained but is **not** the navigation answer: the target document, being Word-generated, carries **zero** outline entries. It costs nothing when present and must not be relied on.
- **FR-010** `pdf_find(query, path="")` searches materialised `text.md` files across every document by default, returning document, page and surrounding context. Hits are capped, and a capped result says so.
- **FR-011** `pdf_page_image(path, page)` renders one page entire, for a full-page diagram or a layout that only reads as a whole.

**Delivery to the model**

- **FR-012** A `pdf_pages` **input provider** satisfies the `InputContentProvider` port and composes materialised page images into a step's prompt as image content blocks — the same mechanism `run_images` uses.
- **FR-012aa** **The wiring takes TWO declarations, and neither is `injects: [pdf_pages]`.** An earlier draft of this spec said the gate was the provider name; it is not, and an implementation following that would get an empty list with no error. Verified against `engine.py::_compose_input_blocks` and the one working example (`workflows/prototype/workflow.yaml` + `prompts/prototype-specify/AGENT.md`):
  1. **`workflow.yaml`** — `input_providers: [pdf_pages]`, a WORKFLOW-level manifest key. `compiler.py` validates the name against the registry and threads it onto `ectx.compiled_input_providers`.
  2. **`AGENT.md`** — `injects: [images]`, the GENERIC token. The engine's gate is literally `if "images" not in agent_injects: return []`; the provider name never appears in an `AGENT.md`.

  Declaring only one half is silent: no images, no error, no log. This is the single most likely way to implement this feature and get nothing.
- **FR-012ab** **Images appear on the dispatch AFTER the one that created them.** `_compose_input_blocks` runs per dispatch inside the agent's tool loop, so an agent that calls `extract_text` in dispatch *n* sees the resulting crops from dispatch *n+1* onward — one agent CAN both materialise and look, without a second step. The cost is that the blocks are sticky and re-render on **every** subsequent dispatch: a 21-page document is ~22,000 image tokens re-sent per dispatch for the rest of that agent's turn. An agent that only needs to *name* what is available should not declare `injects: [images]` at all.
- **FR-012a** Input providers receive `ctx` and take **no per-step arguments**, so the provider's scope must be derived from run/step state. A design that requires per-worker page targeting (one fan-out worker per page) needs that scope to come from the step's own task, and must be stated rather than assumed.
- **FR-012b** Returned images are downscaled as needed to stay inside the provider's per-image pixel, byte and token ceilings. An over-ceiling image is rejected by the provider, which fails the whole request rather than one tool call.

**Concurrency and blocking**

- **FR-013** Parallel materialisation uses **processes, never threads**. §3.4 is the evidence: threads give 0.99× on text extraction and **crash the process** on rendering, because PDFium is not thread-safe.
- **FR-013a** Each worker takes a **contiguous page range and opens the document once**. Per-page tasks are dominated by re-opening the file.
- **FR-013b** Parallelism is **gated on page count**, since process spawn is a fixed cost a small document never earns back. The threshold is a named constant; measurement noise (§3.4) means it is chosen conservatively and revisited against real documents, not derived from a single benchmark.
- **FR-014** Materialisation runs **off the event loop** (`asyncio.to_thread` around the pool call). A multi-second synchronous tool call on the loop stalls the run's event stream and the user sees a hung run. This would be the repo's first `ProcessPoolExecutor`; the pattern is new and should be introduced explicitly rather than slipped in.

**Binding and safety**

- **FR-015** A capability module registers the provider with `user_allowed=True`, returning tool keys with `exclude_builtin=False` so native filesystem tools stay bound alongside. It imports **only** the registry decorator and the tool base — no `app.*` — preserving the `agents.capabilities ↛ app` contract. The factory resolves keys to concrete tools.
- **FR-016** Tools bind when a step declares `tools: [pdf]`. **`manifest.py` is not modified** and no workflow-level `capabilities` key is introduced.
- **FR-017** With the grant absent, no pdf tool is bound and the composed tool set is **byte-identical** to the pre-change snapshot, asserted against the existing characterization snapshots.
- **FR-018** `.extract/` is added to the sandbox's reserved-prefix set, so materialised pages are **excluded from the run deliverable** exactly as `.browser/`, `.verify/` and `.uploads/` are. Without this every extracted PNG ships to the user. The prefix is `.extract/`, not `.pdf/`: a tree holding `.docx` and `.xlsx` pages under a name that says `pdf` is the same misdescription FR-039a removes from the registry.
- **FR-019** Every path resolves through `RunSandbox.path_for`; a path escaping the run root returns an error string and touches nothing.
- **FR-020** **No tool ever raises into the graph.** Traversal refusals, parse failures, missing files, absent dependencies and render failures all return readable text. A tool that raises kills the step; a tool that explains lets the agent recover.
- **FR-021** When the source PDF is absent but its sidecar survives (a resumed run on a wiped workspace), the tools say exactly that, distinguished from a document never uploaded.

**Office formats — one route, not three**

- **FR-026** A `.docx`, `.xlsx` or `.pptx` upload is materialised by **converting it to PDF first**, then running the PDF materialiser unchanged. There is no second extractor, no second on-disk layout and no second contract. The conversion is `soffice --headless --convert-to pdf` — the same binary and the same invocation `pptx_tools._render_slides` already uses to verify a generated deck.
- **FR-026a** The route follows from §3.1 applying unchanged to Office formats: a screenshot carrying callout arrows is one embedded picture **plus separate DrawingML shapes**, so `python-docx` / `python-pptx` image extraction drops the annotation exactly as embedded PDF extraction did. Only a render preserves it, and none of the three formats has an in-process renderer. Three native extractors would reproduce, three times, the defect this spec exists to prevent.
- **FR-027** **This reverses FR-002's `no apt-get layer` for LibreOffice, and only for LibreOffice.** Cost stated plainly: `libreoffice-core` plus the Writer/Calc/Impress filters add roughly **400–600 MB** to the runtime image — **UNMEASURED**, to be confirmed against the built image before this is merged (see [Assumptions](#assumptions)). No OCR engine and no poppler arrives with it.
- **FR-027a** The dependency is **already assumed by shipped code**, and already satisfied in exactly one of the two environments this project runs in. `pptx_tools._render_slides` (spec [017](../017-ppt-v2-pptx/spec.md)) shells out to `soffice`, then to `pdftoppm`:
  - **On a developer machine it works.** Homebrew supplies both (`/opt/homebrew/bin/soffice`, `/opt/homebrew/bin/pdftoppm`), so the deck check really converts and really writes `slide-*.png` into `.verify/` — the converted PDF visible there is genuine output, not a leftover.
  - **In the built image it does not.** `backend/Dockerfile`'s runtime stage installs `libpq5`, `curl`, `ca-certificates`, `libstdc++6`, `git` and Playwright's Chromium — no LibreOffice, no poppler. There the check returns *"not rendered — LibreOffice is not installed here"* and passes.

  So spec 017's verification is **environment-dependent**: green locally because it ran, green in the container because it didn't. Installing LibreOffice closes that divergence as a side effect; the closure must be confirmed against the built image, not assumed.
- **FR-028** Conversion output is cached at `.pdf/{slug}/source.pdf`, under the same folder-is-the-state rule: present ⇔ conversion completed. A second `pdf_extract` on the same upload reuses it and never re-converts. `pdf_page_image` on a converted document renders from it.
- **FR-029** `source_sha256` hashes the **uploaded file's own bytes** — the `.docx`, never the derived PDF — because that is what changes when a document is re-uploaded under the same name. `manifest.json` gains `source_format` and, for a converted document, `converted_by`.
- **FR-030** The layout is `.extract/{format}/{slug}/pages/NN/` — **the source format is a directory level**, and the slug is the filename with its extension stripped. `report.docx` and `report.pdf` are different documents that slug identically, so without a mechanism to separate them each would see a `source_sha256` mismatch, discard the other's folder and re-materialise — forever, alternating. This is a **live defect in the shipped PDF-only code**, dormant only because one format is accepted; it becomes reachable the moment a second is.
- **FR-030a** Every consumer that enumerates materialised documents walks **two** levels. One level down finds format directories and no `manifest.json`, so a one-level walk returns nothing rather than failing loudly — `document_find` and the `pdf_pages` provider both do this, and both are covered by a test that would pass on a one-level tree if it did not assert across formats.
- **FR-031** LibreOffice absent, failed, timed out, or refusing to open the file returns readable text naming which of those happened — never an exception, never a silent empty result. A file no renderer will open is corrupt, and saying so is the useful answer.
- **FR-032** Every conversion runs with its **own `-env:UserInstallation` profile directory**, removed afterwards. A shared profile is not concurrency-safe: two `soffice` processes against one profile race, and one exits without producing output. This spec's own process pool (FR-013) makes concurrent conversion reachable, so the collision is not hypothetical.
- **FR-033** Conversion is bounded by a timeout (the 180 s `pptx_tools` already uses) and the converted page count is read **before** materialising.
- **FR-034** **No page cap. Nothing is ever refused for being large.** A client's 1000-page PDF is real content, not an abuse case, and a document tool that refuses documents has failed at its own job. Measured on the screenshot-heavy reference document — the worst case, since text-only pages are far smaller: **204 KB/page → 1000 pages ≈ 0.19 GB on disk**, and **1.7 s / 21 pages → ~83 s sequential, ~25 s** once the process pool engages above the parallel threshold. The architecture already absorbs this: processes (FR-013), resume as a property of the folder (FR-007), and `pages=` for slicing by choice.
- **FR-034a** Above a named page count the receipt **mentions** that `pages=` exists and what reading the whole thing would cost. Advisory only — the document is already fully materialised when that line prints. An earlier draft made this a refusal; that was wrong, and the constant is now a threshold for advice rather than a gate.
- **FR-034c** **Word-splitting is tightened for grids.** `pdfplumber`'s default `x_tolerance=3.0` is tuned for prose, where a 3pt gap really is one word. A converted spreadsheet breaks that: a right-aligned number ends flush against the next column's left-aligned value, so `46445` and `Yes` arrive as the single token `46445Yes` — **a value that appears nowhere in the workbook**. Measured: `1.5` separates the columns and leaves prose byte-identical (15,072 characters on the 21-page reference PDF at every tolerance from 3.0 down to 1.0), so the fix costs nothing.
- **FR-034b** A spreadsheet's page count is stated for what it is: **LibreOffice's pagination of a sheet, driven by print settings nobody set deliberately** — not a structure the workbook has. The receipt says so on every `.xlsx`, because a page number that looks like document structure and isn't is the quiet way to be wrong.
- **FR-035** A `.docx` has no fixed pagination in the source either. Page numbers in materialised output are **LibreOffice's pagination, not Word's**, and every consumer-facing string citing a page for a converted document says so. Presenting "page 4" as though Word would agree is FR-022's defect in a new costume.
- **FR-036** Fidelity is LibreOffice's, not the authoring application's — fonts substitute and layout can shift. Acceptable for the target use (screenshots with overlays, prose, tables); **not** claimed for pixel-exact reproduction.
- **FR-037** `.xlsx` joins `_ALLOWED_EXTS` in `run_files.py`. It does **not** join `_EXTRACTABLE_EXTS`: no `openpyxl` is added, so an `.xlsx` upload gets **no flat `.txt` sidecar**, and the ingest path says so rather than writing an empty one. Spreadsheet content reaches an agent through the tools — which is where FR-024 wants it regardless.
- **FR-038a** FR-016's "no workflow-level capabilities key" concerns the `capabilities:` block that `manifest.py` gates. It does **not** extend to `input_providers:`, which is a pre-existing workflow-level manifest key (`manifest.py` already parses it; `manifest.py` still needs no edit) and is REQUIRED for the image half — see FR-012aa. The tool half is per-step (`tools: [file_extract]`); the image half is not, and cannot be.
- **FR-038** The `.pdf/` reserved prefix, the `pdf_pages` input provider, the per-step `tools:` grant and the deliverable exclusion are **reused unchanged**. No new capability kind, no new provider, no new reserved prefix, and `manifest.py` stays byte-unchanged.
- **FR-039** **One format-neutral entry point.** The agent calls `extract_text(path, pages="")` for a `.pdf`, `.docx`, `.xlsx` or `.pptx` alike and never learns which one needed a converter. Format dispatch, `soffice` discovery, the profile directory, the timeout and the conversion cache are all **below** the tool boundary. An agent that has to know a document's container format in order to pick a tool has been handed the implementation as an interface.
- **FR-039a** Module, capability and tool names all say the same thing: `app/agents/tools/file_extract_tools.py`, capability key **`file_extract`** (`tools: [file_extract]`), exposing `extract_text`, `file_info`, `file_find`, `file_page_image`. A module named `pdf_tools` or a key named `pdf` that materialises a `.docx` is a lie in a registry whose entire job is truthful membership, and `_KNOWN` is the compiler's INV-4 surface. The rename costs nothing **today**: the capability was committed in `16b45d106` and **no `AGENT.md` declares it yet**. It never gets cheaper, and after the first grant ships it is a breaking change to a user-declarable capability.
- **FR-039b** `extract_text` keeps FR-003's contract unchanged: it **materialises and returns a receipt**, never page content. The name says what the agent gets — a document turned into readable text and pictures on disk — not that the string comes back in the tool result. A large document's text does not fit in a tool result, which is why the receipt exists.
- **FR-039c** The name collides with `app/api/file_extract.py::extract_text`, the ingest sidecar endpoint. They are different layers doing different jobs (flat `.txt` for the brief vs. materialisation for an agent) and the collision is in reading, not in code. Whichever is renamed, the two must not be confused in prose again.
- **FR-044** **Three routes, one entry point.** `extract_text(path, pages="", file_type="")` decides by format and the caller never picks a tool per type:
  1. **Plain text** — `.txt`, `.md`, `.csv`, `.json`: the content comes **straight back in the tool result** and nothing is written. Materialising a `.txt` into pages of itself adds a directory, a manifest and a second read for no gain. Capped at a named constant, and a truncated return says so and points at `read_file`.
  2. **Paged** — `.pdf`, `.docx`, `.xlsx`, `.pptx`: materialised into `.extract/{format}/{slug}/`, Office formats converted by LibreOffice first. The receipt **names `document.md`** and the content stays on disk, because a large document's text does not fit in a tool result.
  3. **Anything else** — refused in readable text, with **no blind conversion attempt**. The upload allow-list decides which bytes reach this process (FR-040), and LibreOffice is a large C++ parser to aim at unknown input on speculation.
- **FR-044a** `file_info` follows the same split: a plain-text upload is described by character and line count and is never handed to a PDF parser, and the inventory says which of the three routes each upload takes.
- **FR-040** `.doc`, `.xls`, `.ppt`, `.odt`, `.ods`, `.odp` and `.rtf` are **not** accepted, though LibreOffice converts all of them. Widening what the platform ingests is a security decision, not a free consequence of owning a converter.
- **FR-041** The conversion is **one shared helper**, not a second copy. `pptx_tools._render_slides` (the repo's only `soffice` call site) and the Office materialiser both call a single `app/agents/tools/soffice.py::convert_to_pdf(src, out_dir)` that owns binary discovery, the per-call profile directory (FR-032), the timeout (FR-033) and the "which failure was it" message (FR-031). Two copies of a subprocess invocation drift, and the one that drifts is the one nobody is looking at.
- **FR-042** Only the **convert-to-PDF half** of ppt_v2's path is shared. Its second step — `pdftoppm -png -r 60` — is **not** reused: `pypdfium2` already renders in-process inside `pdf_tools`, it is the same renderer the crop geometry measures against, and it needs no second binary. Reusing `pdftoppm` would re-admit poppler, which FR-002 still forbids.
- **FR-043** Once FR-041 and FR-042 land, `pptx_tools._render_slides` renders its own deck check through `pypdfium2` too, and its `pdftoppm` branch is deleted. That branch has never run in the built image (FR-027a), so this removes a dependency the project believed it had and never actually satisfied — not a working code path.

**Pre-existing defect this feature would otherwise contradict**

- **FR-022** `_extract_pdf` joins per-page text with empty pages **dropped**, so page *N* in the ingest sidecar is not page *N* in the document and any citation taken from the brief is silently wrong. The sidecar must preserve page correspondence.
- **FR-023** A missing PDF dependency logs at ERROR naming the module, distinguishable from a genuine extraction failure; `_extract_pdf` still returns a string and never raises.
- **FR-024** An agent granted these tools **should not usually also declare `injects: [uploaded_files]`** — guidance, not a prohibition, and deliberately unenforced.
  The two are independent: `.uploads/` is created by the ingest endpoint, never by the provider, so the tools reach uploads whether or not the inject is declared and declaring both enables nothing extra. What it costs is duplication — the same document flat in every prompt AND page-structured on disk. The flat copy carries no images and is capped at `BRIEF_MAX_CHARS` (450,000), which is large enough that truncation is the exception rather than the rule.
  A workflow that wants the sticky brief text *and* the page images is a legitimate combination, so this is a token-cost note for the workflow author to weigh, not an error to catch. One asymmetry worth knowing: an `.xlsx` has no sidecar at all (FR-037), so an agent relying on the inject alone sees every other upload's text and not the spreadsheet's.
- **FR-025** No EXISTING `AGENT.md` is edited and no engine or compiler change is made. `run_files.py` gains `.xlsx` to its upload allow-list (FR-037) and nothing else.
- **FR-045** One new agent ships with the tools: **`backend/agents/prompts/file-analyst/AGENT.md`**, `tools: [file_extract]`, its own `pipeline_type: file_analyst` so it alters no existing pipeline — the shape spec 018's `playwright-smoke-test` established for an agent that exists to exercise a new capability.
- **FR-045a** The analyst is **selective, not exhaustive**. It calls `file_info()` first — free, writes nothing — reads the request, and extracts only the uploads the request implicates. Materialising every upload costs ~22,000 tokens for one 21-page PDF alone, and a workflow with five uploads usually needs one. When the target is genuinely ambiguous it extracts the candidates rather than guessing, because a wasted extraction is cheaper than an answer built on the wrong document.
- **FR-045c** The analyst declares `injects: [images]` so it can describe what a screenshot actually shows, using FR-012ab's next-dispatch behaviour: inventory, extract, then look at the crops on the following dispatch and fold what it sees into its report. This is DORMANT until a workflow declares `input_providers: [pdf_pages]` (FR-012aa), which is correct — the agent is ready and costs nothing until a workflow opts in.
- **FR-045b** The analyst returns a **map, not a copy**: which uploads exist, what they are, and the `document.md` path for each one it extracted. It does not read `document.md` into its own context unless the request needs it to answer from it — pulling a whole document into step 0 defeats the purpose of step 0. It never describes a picture it has not seen: images reach a model only through a step declaring `injects: [pdf_pages]`, so an answer that depends on what is inside a screenshot is reported as such, naming the page.

### Key Entities

- **Uploaded document** — a file under `.uploads/`, with a `manifest.json` entry and, for extractable types, a `.txt` sidecar. Owned by one user and one run.
- **Materialised document** — `.extract/{format}/{slug}/`: `manifest.json` (source hash, source format, page map), `document.md`, one directory per completed page, and — for a converted Office source — the cached `source.pdf` it was rendered from. Deliverable-excluded, disposable, rebuildable, and **self-describing** — it is simultaneously the output, the cache and the resume state.
- **Page** — `text.md` plus zero or more `image-N.png`. Exists only when complete.
- **Placeholder** — `@[[image-N.png]]` in `text.md`. A marker that a picture belongs at this position, **not** a link an agent can follow: `read_file` on a PNG returns binary garbage.

## 6. Out of scope

- **Code execution for agents.** The alternative answer to §1, and its own spec.
- **OCR.** Confirmed unnecessary on the target document, and made safe by FR-009 and FR-005 rather than assumed away.
- **PDF authoring** — creating, merging, splitting, rotating, watermarking, encrypting.
- **PDF form filling.** No AcroForm in the target class, and the half of the upstream skill most encumbered by its licence.
- **Cell-addressed table extraction as its own tool.** Layout-aware text plus the page crop preserves tabular meaning here.
- **Reassembling a picture or table across a page break.** Materialisation is page-scoped and says so.
- **Native Office extractors** as a parallel materialisation path — rejected by FR-026a, not deferred: they lose the overlay annotations this feature exists to preserve.
- **Per-format internal handling beyond text.** DEFERRED, not rejected — text extraction is the agreed scope for now, and the shape below is the known next step.
  The clearest case is **`.xlsx` → one CSV per sheet**, attached as files rather than flattened into page text. Converting a workbook to PDF and reading its pages back is the wrong shape for a spreadsheet twice over: it invents a pagination the workbook does not have (FR-034b), and it destroys the one structure that matters — the cell grid. FR-034c tightens word-splitting so columns at least stay separate, but that is a repair on a lossy path, not the right path. A sheet is already tabular; emitting it as CSV keeps rows, columns and sheet names intact and costs no renderer at all.
  This would make `extract_text` a fourth route rather than a change to the existing three, and the same reasoning may later apply per format (a `.docx`'s heading structure, a `.pptx`'s per-slide notes). Nothing here blocks it: the entry point already dispatches on format, and `.extract/{format}/{slug}/` already has room beside `pages/` for whatever a format's natural output is.
- **Legacy and OpenDocument formats** (`.doc`, `.xls`, `.ppt`, `.odt`, `.ods`, `.odp`, `.rtf`). FR-040.
- **Round-tripping or editing an Office document.** Conversion is one-way and read-only.
- **Matching Word or Excel pagination.** FR-035 states the divergence; reproducing it is a different feature.
- **Replacing or re-authoring the vendored `pdf-reader` skill.** Licence-encumbered and unrunnable here; not part of this feature.
- **Changing the `uploaded_files` provider.** FR-024 governs the interaction by declaration, not by modifying a shipped capability.
- **Fixing the severed fan-out lever.** `agentToManifestStep` hardcodes `strategy = "single_shot"` at save time, so a per-image fan-out cannot persist today. This feature's artifacts support a fan-out when that is fixed; fixing it is not in scope here.

## 7. Success Criteria *(mandatory)*

- **SC-001** An agent handed the target document produces a procedure citing the page each step came from, and the cited page really contains it.
- **SC-002** For an instruction whose meaning lives in an annotated screenshot, the agent's output reflects **which control the arrow points at** — the failure mode embedded extraction produces silently.
- **SC-003** Every instruction in the extracted text is followed by the picture it refers to, in the order the document presents them.
- **SC-004** Re-running extraction on an already-processed document completes without re-reading the PDF, and re-running after an interruption produces a complete document.
- **SC-005** Uploading a different file under a previously-used name never yields the old document's pages.
- **SC-006** A workflow whose steps were not granted the tools behaves exactly as before, with no measurable change to prompt size or output.
- **SC-007** Extraction of a large document does not stall the run's event stream, and never takes down the backend worker.
- **SC-008** No tool call reads or writes outside its own run, and no malformed, encrypted or corrupt document fails a run rather than informing the agent.
- **SC-009** No materialised file appears in the user's deliverable.
- **SC-010** A `.docx` whose instruction lives in an annotated screenshot yields a crop that still carries the annotation — SC-002 holding across formats is the whole point of FR-026.
- **SC-011** `report.docx` and `report.pdf` uploaded to one run materialise into `.extract/docx/report/` and `.extract/pdf/report/`, and neither discards the other on any number of re-runs.
- **SC-011a** A step declaring `injects: [pdf_pages]` in a run holding several materialised documents receives images from **all** of them, in the same order every time — a document the user uploaded is never silently dropped.
- **SC-012** An `.xlsx` reports its converted page count before materialising, and a sheet that paginates into hundreds of pages refuses rather than filling the sandbox.
- **SC-013** Spec 017's deck render check behaves identically on a developer machine and in the built image, instead of passing for opposite reasons in each.
- **SC-013a** One call — `extract_text` — handles every accepted type, and nothing in an agent's prompt or tool list names a container format.
- **SC-013b** A `.md` upload returns its text in the tool result and creates no `.extract/` directory; a `.pdf` upload creates one and returns a receipt naming `document.md`; a `.zip` upload returns a refusal and no conversion is attempted.
- **SC-014** With LibreOffice absent, every tool still returns readable text naming the missing binary, and no run fails.
- **SC-015** Exactly one `soffice` invocation exists in the codebase, and both ppt_v2's deck check and Office materialisation reach it through that one helper.
- **SC-016** No `pdftoppm` call site remains, and ppt_v2's deck check still reports a real page count.

## 8. Risks

- **RISK-01 — CLOSED.** The earlier draft's largest risk was that image content blocks inside a `tool_result` were proven only at the adapter, never against a model. **This design does not use that path.** Images reach the model through the `input_provider` port that `run_images` already uses in production. Recorded as closed rather than deleted, because the shape of the earlier design is what made it a risk and the change is the mitigation.
- **RISK-02 — CLOSED by measurement, not solved.** The risk was that dedupe is hard and its exact fix is a correctness bug. Both true, and both irrelevant: perfect dedupe saves 2% of image tokens (541 of 18,569), so **nothing is built** and the correctness bug is never introduced. Recorded as closed rather than deleted because "the optimisation is not worth its risk" is the finding, and a future reader tempted to add dedupe needs to see the number. Revisit only if a document is measured where repeated images are a double-digit share.
- **RISK-03 — every measurement comes from one document.** 21 pages, Word-generated, screenshot-heavy, no scans, no outline. The constants, thresholds and cost estimates are calibrated to it. A 400-page scanned document would invalidate the OCR decision, the page-count threshold and the whole cost model at once.
- **RISK-04 — benchmark noise.** Two runs of the same process-pool benchmark on the same document gave 2.15× and 3.44× at 4 workers. The parallelism threshold (FR-013b) must not be tuned to a single run.
- **RISK-05 — FR-022 changes brief content for every existing PDF upload.** Fixing sidecar page correspondence alters the text stapled into any workflow already using `injects: [uploaded_files]`. It is the correct fix and it is not free; the alternative is leaving known-wrong page numbering and forbidding citation from the brief.
- **RISK-06 — `.pdf/` is a new writable surface.** Unless reserved (FR-018), every extracted image ships in the user's deliverable — the exact trap spec 018 hit with `.browser/`.
- **RISK-07 — the first `ProcessPoolExecutor` in this codebase.** Process pools inside an async API layer bring their own failure modes (spawn cost, memory multiplied per worker, orphaned children on cancellation). The measured gain is real; the operational surface is new.
- **RISK-08 — `pdfplumber` and `pypdf` disagree on image count** (67 vs 66 on the target document). Image *indices* are therefore not a stable identifier across libraries, which is why FR-001 takes both position and pixels from one of them.
- **RISK-09 — image size, unmeasured.** LibreOffice is the largest single thing this image would carry — an estimated 400–600 MB on top of Playwright's ~350 MB. The estimate is from package sizes, not from a build. If it lands materially higher, the trade is worth re-opening: the fallback is FR-026a's rejected route, accepting lost annotations.
- **RISK-10 — `soffice` must run as the non-root runtime user.** The image switches to uid 10001. LibreOffice needs a writable profile and `HOME`; FR-032's per-call `-env:UserInstallation` directory must resolve somewhere that user can write, or every conversion fails identically and only in the container.
- **RISK-11 — conversion latency is paid on first extract.** `soffice` startup is seconds, per document, before any page is materialised. The folder-is-the-state cache (FR-028) pays it once, but the first call on a converted document is measurably slower than on a native PDF and the receipt should not hide that.
- **RISK-12 — `.xlsx` pagination is the least predictable input this feature accepts.** The same sheet converts to 1 page or 300 depending on print settings nobody set deliberately. FR-034 guards it; the guard's ceiling is a guess until a real spreadsheet is measured.
- **RISK-12a — a check that is green in both environments for opposite reasons is worse than a red one.** `_render_slides` passes locally by converting and passes in the container by finding no converter. Any check that degrades to a pass has this shape, and installing the binary fixes this instance without fixing the pattern.
- **RISK-13 — FR-039a's rename touches a just-committed public surface.** Renaming `pdf` → `documents` is free only while no `AGENT.md` declares it. Every day it is deferred the rename gets more expensive, and after the first grant ships it is a breaking change to a user-declarable capability.

## Assumptions

- Documents are digitally generated with a real text layer on most pages — verified on the target document, where every page carries at least 404 characters.
- Uploads arrive through the existing owner-scoped endpoint and its caps. This spec adds no ingress and changes no limit.
- The per-run sandbox is the only place these tools read or write, with traversal safety inherited from `RunSandbox.path_for` rather than re-implemented.
- Reading a user's own uploaded document is unprivileged, so the capability is user-declarable — unlike the browser tool set.
- **UNMEASURED — every Office figure in this spec.** No `.docx`, `.xlsx` or `.pptx` was profiled: the user has no representative document, so unlike §3 (measured end to end on a real PDF) the image-size estimate, the conversion latency, the `.xlsx` page ceiling and the fidelity claim are all reasoned from format structure. **Confirm each against a real document before implementation**, and treat any of them being wrong as a reason to re-open FR-026, not to patch a constant.
- LibreOffice's PDF output is faithful enough that a screenshot's overlay shapes render as drawn. This is the single assumption FR-026 rests on; if it fails, the whole route fails and native extraction is no better.
- A vision step is authored in the workflow; this spec supplies the artifacts and the delivery mechanism, not the pipeline. How many steps see the pages, and whether one agent loops or several fan out, is a workflow-authoring decision (constrained by the severed fan-out lever noted in §6).
