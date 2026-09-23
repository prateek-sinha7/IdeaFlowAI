export const meta = {
  name: 'spec-019-file-extract-support',
  description: 'Spec 019 — PDF extraction: materialise a document into pages an agent can read. 18 tasks + 5 validators, dependency-scheduled',
  phases: [
    { title: 'Materialiser', detail: 'T1-T7 + V1 — offline: reading order, crops, atomic materialisation' },
    { title: 'Binding', detail: 'T8-T13 + V2 — capability, registry, factory, reserved prefix' },
    { title: 'Delivery', detail: 'T14-T16 + V3 — the pdf_pages input provider' },
    { title: 'Parallelism', detail: 'T17 + V4 — process pool, never threads' },
    { title: 'Sidecar', detail: 'T18 + V5 — the pre-existing page-correspondence defect' },
  ],
}

const REPO_NOTES = `
PROJECT: VELOCITY-AI (internally "Flowin") — a workflow-agnostic agent execution runtime.
Backend is Python/FastAPI under backend/. You are in the worktree
VELOCITY-AI-worktrees/feat-pdf-workflow on branch feat/pdf-workflow.

HOW TO VERIFY
- Run ONE test file at a time. NEVER run the full suite — it breaks the user's machine.
  Each task names its exact command; run that and nothing broader.
- Backend tests: pytest <path> -q, invoked from the repository root.
- The working interpreter is python3.11 (python3 lacks fastapi/sqlalchemy here).
- If a command you need is not named in your task, ask for it in your blockers rather than
  inventing a broad invocation.

GIT — ABSOLUTE
- NEVER run git add, git commit, git push, git checkout, git branch, git merge, git stash,
  git reset, or any other git write. The user handles ALL git themselves, without exception.
- Read-only git (git diff, git status, git log) is fine for inspecting your own work.
- Do not add Co-Authored-By or any AI-attribution trailer anywhere.

SCOPE DISCIPLINE
- Change ONLY what your task names. Every changed line must trace directly to your task.
- Do not "improve" adjacent code, comments, or formatting. Do not refactor anything that is
  not broken. Match the existing style of the file you are editing.
- If you notice unrelated dead code or a bug outside your task, MENTION it in your summary.
  Do not fix it.
- Remove imports/variables your OWN change orphaned. Leave pre-existing dead code alone.
- The working tree is SHARED and NOTHING is committed between tasks. `git diff` and
  `git status` show the CUMULATIVE work of every task that ran before you — that is normal,
  not a scope violation by you. NEVER revert, overwrite or delete a file you did not create
  in this task (no `git show HEAD:f > f`, no `rm` of a sibling's file). If a validator tells
  you the diff is too wide, the fix is to narrow YOUR OWN edits and say so — destroying
  another task's output is the single worst thing you can do here.

THE ONE RULE THAT CAN TAKE DOWN THE BACKEND
- NEVER use ThreadPoolExecutor, threading.Thread, or any thread for PDF work.
  PDFium (via pypdfium2) is NOT thread-safe. Rendering across threads crashes the PROCESS —
  measured: exit 133, SIGTRAP, no traceback, nothing to catch. In the backend that kills the
  worker and every concurrent run on it. Parallelism is ProcessPoolExecutor or nothing.
  asyncio.to_thread around a whole blocking call is fine and required (that is ONE thread,
  for non-blocking, not many for speed).

THE DECISION THE WHOLE SPEC TURNS ON
- image-N.png is a CROP OF THE RENDERED PAGE, never the embedded image. Measured on the real
  document: page 2's screenshot carries four red arrows and a circle identifying which controls
  to click; extracted as an embedded image it has NONE of them, because they are PDF vector
  overlays drawn on top. Embedded extraction silently deletes the instruction.
  If you find yourself calling page.images[k].data to produce a deliverable image, stop.

OFF LIMITS
- backend/agents/workflows/manifest.py — byte-unchanged. This feature is granted via
  spec.tools (AGENT.md "tools: [pdf]"), so the capabilities block is never approached.
- backend/agents/execution_engine/** and backend/agents/workflows/compiler.py — untouched.
- backend/app/api/run_files.py — no new ingress.
- backend/agents/capabilities/context_providers/uploaded_files.py — untouched.
- No database migrations. No new dependency in requirements.txt (pypdfium2 arrives via
  pdfplumber — do NOT pin it). No apt-get layer. No frontend change. No AGENT.md edits.
- Existing test_tool_provider_* assertions in test_create_runner.py must pass UNCHANGED.
  Editing a characterization snapshot to go green is how a real regression gets hidden.

ARCHITECTURE INVARIANTS THAT APPLY HERE
- SC-001: the kernel stays workflow-agnostic. No "if pipeline_type == ..." and no
  workflow-name or agent-name literal in any resolution path you write.
- backend/agents/capabilities/ MUST NOT import from app.* — an import-linter contract
  enforces this. Capability providers emit STRING KEYS; the factory resolves them.
- Every sandbox path goes through RunSandbox.path_for, which is traversal-proof.
- Tools NEVER raise into the graph. Every failure returns readable text the model can act on.

REFERENCE IMPLEMENTATIONS — read these before writing new code
- .reference/tmp/_materialize.py — the reference implementation of Phase 1, already run
  against the real document. Its output is .reference/tmp/materialized/. Phase 1 REPRODUCES
  this behaviour inside the tool; it does not invent it.
- backend/app/agents/tools/pptx_tools.py — the per-run sandbox-bound tool module shape.
- backend/agents/capabilities/tools/pptx.py — the string-key provider shape.
- backend/agents/capabilities/input_providers/run_images.py — the input-provider port shape.
- backend/agents/factory.py ~line 1094 — the playwright key-resolution branch to mirror.

SPEC DOCUMENTS
- specs/019-file-extract-support/spec.md — requirements (FR-nnn), measured evidence (§3), risks.
- specs/019-file-extract-support/plan.md — design, file inventory, change budget, phases.
- specs/019-file-extract-support/research.md — the three resolved decisions and WHY.
- specs/019-file-extract-support/contracts/on-disk-format.md — NORMATIVE on-disk layout and the
  @[[image-N.png]] placeholder grammar.
- specs/019-file-extract-support/tasks.md — your task, verbatim, with full detail.
Read the plan and the contract before your first edit. They explain WHY, which the task
text assumes.
`.trim()

const TASK_RESULT_SCHEMA = {
  type: 'object',
  properties: {
    taskId: { type: 'string' },
    status: { type: 'string', enum: ['done', 'blocked'] },
    filesChanged: { type: 'array', items: { type: 'string' } },
    summary: { type: 'string' },
    acSelfCheck: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          criterion: { type: 'string' },
          met: { type: 'boolean' },
          note: { type: 'string' },
        },
        required: ['criterion', 'met'],
      },
    },
    blockers: { type: 'string' },
  },
  required: ['taskId', 'status', 'filesChanged', 'summary', 'acSelfCheck'],
}

const VALIDATOR_RESULT_SCHEMA = {
  type: 'object',
  properties: {
    validatorId: { type: 'string' },
    pass: { type: 'boolean' },
    checks: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          criterion: { type: 'string' },
          result: { type: 'string', enum: ['pass', 'fail'] },
          evidence: { type: 'string' },
        },
        required: ['criterion', 'result', 'evidence'],
      },
    },
    failedTasks: { type: 'array', items: { type: 'string' } },
    summary: { type: 'string' },
  },
  required: ['validatorId', 'pass', 'checks', 'failedTasks', 'summary'],
}

const PDF_TOOLS    = 'backend/app/agents/tools/pdf_tools.py'
const PROVIDER     = 'backend/agents/capabilities/tools/pdf.py'
const REGISTRY     = 'backend/agents/capabilities/registry.py'
const TOOLS_INIT   = 'backend/agents/capabilities/tools/__init__.py'
const FACTORY      = 'backend/agents/factory.py'
const SANDBOX      = 'backend/app/agents/sandbox.py'
const IP_PROVIDER  = 'backend/agents/capabilities/input_providers/pdf_pages.py'
const IP_INIT      = 'backend/agents/capabilities/input_providers/__init__.py'
const FILE_EXTRACT = 'backend/app/api/file_extract.py'
const TEST_TOOLS   = 'backend/tests/agents/test_pdf_tools.py'
const TEST_IP      = 'backend/tests/agents/test_pdf_pages_provider.py'
const TEST_RUNNER  = 'backend/tests/agents/test_create_runner.py'

// Model classification is PRE-DECLARED in tasks.md § Model classification and is read from
// there, never chosen at dispatch time. haiku for mechanical work; sonnet only for the four
// tasks classified as needing engineering judgment; opus ONLY inside the escalation ladder.
const NODES = {
  // ---------------- Phase 1 — Materialiser ----------------
  T1: {
    kind: 'task', agentType: 'junior-engineer', model: 'haiku', phase: 'Materialiser',
    deps: [], files: [PDF_TOOLS], file: PDF_TOOLS, traces: 'FR-008a, FR-019, FR-020',
    desc: [
      'Create backend/app/agents/tools/pdf_tools.py: module docstring, the four tool-key',
      'constants, and the private helpers — resolve an uploads-relative path through',
      'RunSandbox.path_for, read bytes, list uploaded PDFs in SORTED order, and derive a',
      'filesystem-safe slug from an upload filename.',
      '',
      'Import every PDF library LAZILY, inside the functions that use them. The factory imports',
      'this module at composition time and must not pull pdfminer into every run.',
      '',
      'Establish the never-raise discipline now — every later task inherits it. Each public',
      'entry point returns a readable string on failure. A tool that raises kills the step.',
      '',
      'No tools yet. Helpers and safety only.',
    ].join('\n'),
    ac: [
      'The module imports successfully even with no PDF library installed.',
      'A traversal path ("../../etc/passwd", and an absolute path outside the run root) returns an error string and reads nothing.',
      'slug("Inland Marine Creating a Quote 2.pdf") == "inland-marine-creating-a-quote-2".',
      'Listing uploads returns a deterministic sorted order.',
      'The only file YOU edited is backend/app/agents/tools/pdf_tools.py. Other changes in the working tree belong to sibling tasks — leave them alone.',
    ],
  },

  T2: {
    kind: 'task', agentType: 'junior-engineer', model: 'haiku', phase: 'Materialiser',
    deps: ['T1'], files: [PDF_TOOLS], file: PDF_TOOLS, traces: 'FR-009, FR-009a, FR-009b',
    desc: [
      'Add pdf_info(path="") to pdf_tools.py.',
      '',
      'Empty path -> inventory EVERY upload in sorted order, saying for each whether these',
      'tools can read it. A non-PDF upload (docx/pptx/txt/md/csv/json are all accepted by the',
      'upload endpoint) is listed as present-and-unreadable — omitting it lets an agent',
      'conclude the user never uploaded it. A run with no uploads says so explicitly rather',
      'than returning an empty list that reads like a failed call.',
      '',
      'With a path -> page count; a PER-PAGE text-layer verdict (not only a document-level',
      'one); character density; embedded image count; encryption state distinguished into',
      'openable / locked / unparseable; metadata (author, producer, dates); the document',
      'outline where present; and an estimated token cost to read the document.',
      '',
      'Print the text-layer threshold BESIDE the raw per-page character count, so a model can',
      'disagree with it. An invisible threshold cannot be argued with.',
      '',
      'Report the outline but do NOT build navigation on it — the real target document has',
      'ZERO outline entries (Word emits no bookmarks). It costs nothing when present.',
      '',
      'pdf_info materialises nothing. It is the cheap look-before-you-leap call.',
    ].join('\n'),
    ac: [
      'On the real document it reports 21 pages, a text layer on every page, outline 0 entries, producer "Microsoft(R) Word fuer Microsoft 365".',
      'A run with zero uploads returns an explicit statement, not an empty list.',
      'A non-PDF upload appears in the inventory marked unreadable by these tools.',
      'The threshold value appears in the output next to the raw character counts.',
      'No file is written anywhere by pdf_info.',
    ],
  },

  T3: {
    kind: 'task', agentType: 'senior-engineer', model: 'sonnet', phase: 'Materialiser',
    deps: ['T1'], files: [PDF_TOOLS], file: PDF_TOOLS,
    traces: 'FR-004, FR-004a, FR-005, FR-005a, FR-005b',
    desc: [
      'The algorithmic heart. Classified sonnet because it reconciles two coordinate systems',
      'and one merge rule, and every downstream artifact is wrong if this is wrong.',
      '',
      '1. READING ORDER. Take text lines (page.extract_words(), grouped by rounded "top") and',
      '   image bounding boxes (page.images) from pdfplumber ONLY. Merge into one list, sort by',
      '   vertical position, emit text and @[[image-N.png]] placeholders interleaved.',
      '   Position and pixels must come from ONE library: pypdf and pdfplumber disagree on image',
      '   count (67 vs 66 on the real document), so indices are not portable between them.',
      '',
      '2. FRAGMENT MERGE. Adjacent boxes whose vertical gap is <= a small constant AND whose',
      '   x-ranges overlap are ONE picture. Measured: page 2 image 4 ends at bottom=671.0 and',
      '   image 5 begins at top=671.0 — one screenshot stored as two XObjects, split at an',
      '   arbitrary seam. Expect 10 merges across the document (67 raw -> 57).',
      '',
      '3. CROP GEOMETRY. Scale the merged bbox by render.width/page.width and crop the RENDERED',
      '   page (pypdfium2). NEVER the embedded image. This is the decision the whole spec turns',
      '   on: the embedded image loses the red annotation arrows that carry the instruction.',
      '',
      '4. AUDIT COMMENT. Each placeholder carries <!-- WxH, N source object(s) -->.',
      '',
      'Build NO dedupe (research.md R-01): perfect dedupe saves 541 tokens = 2% of image tokens,',
      'and its only exact form — hashing the embedded stream — collapses the same screenshot',
      'bearing DIFFERENT annotations, which is a correctness bug.',
      '',
      'The placeholder syntax is NORMATIVE — read contracts/on-disk-format.md before writing it.',
    ].join('\n'),
    ac: [
      'On page 2 the placeholders appear BETWEEN the prose blocks in document order, never batched at the end.',
      'The crop for page 2\'s Spinnaker search screen contains the red arrows and the red circle.',
      'Page 2 image objects 4 and 5 become ONE merged image and ONE placeholder.',
      'Across the real document, 67 raw image objects reduce to 57 after merge.',
      'Each placeholder is on its own line, blank-line separated, and carries its audit comment.',
      'No dedupe logic was added.',
    ],
  },

  T4: {
    kind: 'task', agentType: 'senior-engineer', model: 'sonnet', phase: 'Materialiser',
    deps: ['T3'], files: [PDF_TOOLS], file: PDF_TOOLS,
    traces: 'FR-003, FR-006, FR-007, FR-007a, FR-007b, FR-008',
    desc: [
      'pdf_extract(path, pages="") drives T3 across pages and writes the contract layout.',
      'Classified sonnet because it owns atomicity and resume correctness.',
      '',
      'THE ATOMICITY RULE IS THE WHOLE TASK. Build each page in a TEMP directory and move it',
      'into place with a single os.rename. A page directory then exists ONLY IF IT IS COMPLETE,',
      'by construction — no marker file anyone can forget, no partial state to interpret.',
      'This is also what makes concurrent extraction safe: two workers racing one page each',
      'build their own temp dir and one rename wins, with identical content either way.',
      '',
      'RESUME is set(range(1, page_count+1)) - set(existing page dirs). There is no cache file',
      'and no progress record: the folder IS the state.',
      '',
      'BIAS TO REDO. Re-materialising a complete page is cheap; skipping an incomplete one is a',
      'silent wrong answer that reaches the deliverable.',
      '',
      'manifest.json carries source_sha256 of the PDF BYTES. On open, a mismatch discards the',
      'whole folder — uploads dedupe by FILENAME, so the same name can carry different content',
      'and serving the old pages would be silently wrong.',
      '',
      'Also write document.md (all completed pages, page markers between them).',
      '',
      'Return a RECEIPT, never content: pages processed, pages skipped as already present,',
      'image counts before and after merge, character count, estimated tokens to read whole.',
      '',
      'Layout is NORMATIVE — contracts/on-disk-format.md.',
    ].join('\n'),
    ac: [
      'Materialising the real document produces 21 page directories, each with text.md.',
      'A second run reports 21 skipped and rewrites nothing (mtimes unchanged).',
      'Deleting one page directory and re-running rebuilds exactly that page.',
      'Simulating a crash mid-page leaves NO page directory for it, and the next run builds it.',
      'Changing the source bytes under the same filename discards the folder and re-extracts.',
      'The return value contains no page text — only counts and estimates.',
      'manifest.json validates against contracts/on-disk-format.md.',
    ],
  },

  T5: {
    kind: 'task', agentType: 'junior-engineer', model: 'haiku', phase: 'Materialiser',
    deps: ['T4'], files: [PDF_TOOLS], file: PDF_TOOLS, traces: 'FR-010',
    desc: [
      'Add pdf_find(query, path="") to pdf_tools.py.',
      '',
      'Search the MATERIALISED text.md files, not the PDFs — that is the whole point of having',
      'materialised them. Default to every document; narrow when path is given.',
      '',
      'Return each hit as document, page number and surrounding context — output shaped to feed',
      'straight into a page argument. Cap the number of hits and SAY SO when capped, suggesting',
      'the query be narrowed; a search for a common word over hundreds of pages must not return',
      'thousands of hits.',
      '',
      'If the document has not been materialised yet, say that rather than returning "not found".',
    ].join('\n'),
    ac: [
      'A term present on three pages returns three hits naming their page numbers.',
      'A term present nowhere returns an explicit no-match message.',
      'A very common term is capped, and the reply states the cap and suggests narrowing.',
      'Searching an unmaterialised document says so, distinctly from no-match.',
      'No PDF is opened by pdf_find.',
    ],
  },

  T6: {
    kind: 'task', agentType: 'junior-engineer', model: 'haiku', phase: 'Materialiser',
    deps: ['T4'], files: [PDF_TOOLS], file: PDF_TOOLS, traces: 'FR-011, FR-012b',
    desc: [
      'Add pdf_page_image(path, page) to pdf_tools.py — render ONE page entire.',
      '',
      'This is the escape hatch for what cropped pictures cannot answer: a full-page diagram, a',
      'layout that only reads as a whole, a page whose text extraction is untrustworthy.',
      '',
      'Downscale to stay inside the per-image pixel/byte/token ceilings. An over-ceiling image',
      'is rejected by the provider and fails the WHOLE request, not just this call.',
      '',
      'Write into the same page directory the materialiser owns, with a distinct name so it',
      'cannot be confused with a cropped picture.',
    ].join('\n'),
    ac: [
      'Returns a path and a size for a valid page.',
      'An out-of-range page number returns an error string and writes nothing.',
      'The rendered output is within the per-image ceilings after downscaling.',
      'The filename cannot be mistaken for an image-N.png crop.',
    ],
  },

  T7: {
    kind: 'task', agentType: 'junior-engineer', model: 'haiku', phase: 'Materialiser',
    deps: ['T4'], files: [TEST_TOOLS], file: TEST_TOOLS, traces: 'FR-003 .. FR-011',
    desc: [
      'Create backend/tests/agents/test_pdf_tools.py.',
      '',
      'Cover: reading-order interleave; fragment merge on contiguous bboxes; crop-vs-embedded',
      '(the annotation overlay must survive in the crop); temp-dir + rename atomicity; resume',
      'skips complete pages and redoes an interrupted one; source_sha256 staleness discard;',
      'traversal refusal; every failure path returns text and never raises.',
      '',
      'Use a SMALL committed fixture PDF you generate in the test (or a tiny checked-in file).',
      'Do NOT depend on .reference/, which is untracked and will not exist in CI.',
      '',
      'Name tests so the -k selectors in the other tasks work: info, order, merge, crop,',
      'materialise, resume, stale, find, page_image, parallel.',
    ].join('\n'),
    ac: [
      'pytest backend/tests/agents/test_pdf_tools.py -q passes standalone.',
      'No test requires network, a live model, or anything under .reference/.',
      'The -k selectors named above each select at least one test.',
    ],
  },

  V1: {
    kind: 'validator', agentType: 'qa-engineer', model: 'haiku', phase: 'Materialiser',
    deps: ['T2', 'T5', 'T6', 'T7'], files: [], guards: ['T1','T2','T3','T4','T5','T6','T7'],
    desc: 'Checkpoint A — the materialiser reproduces the reference output.',
    ac: [
      'Materialising .reference/Alliance/Inland Marine Creating a Quote 2.pdf produces the structure in .reference/tmp/materialized/: 21 page directories, text.md + image-N.png in each, document.md, manifest.json.',
      'Page 2 text.md has placeholders BETWEEN prose blocks, and its search-screen crop contains the red arrows.',
      '67 raw image objects reduce to 57 after fragment merge.',
      'No dedupe logic exists anywhere in pdf_tools.py.',
      'pytest backend/tests/agents/test_pdf_tools.py -q passes.',
      'The only files YOU edited are pdf_tools.py and test_pdf_tools.py. Other changes in the working tree belong to sibling tasks — leave them alone.',
    ],
  },

  // ---------------- Phase 2 — Binding ----------------
  T8: {
    kind: 'task', agentType: 'junior-engineer', model: 'haiku', phase: 'Binding',
    deps: [], files: [PROVIDER], file: PROVIDER, traces: 'FR-015',
    desc: [
      'Create backend/agents/capabilities/tools/pdf.py.',
      '',
      '@register("tool", "pdf", user_allowed=True, description=...). provide() returns the four',
      'string KEYS and exclude_builtin=False, so native filesystem tools stay bound alongside.',
      '',
      'user_allowed=True is deliberate and differs from playwright (False): reading a document',
      'the user uploaded to their own run is not a privileged operation.',
      '',
      'Import ONLY the registry decorator. No app.* import, no PDF library — an import-linter',
      'contract enforces agents.capabilities does not depend on app. Copy the shape of',
      'backend/agents/capabilities/tools/pptx.py.',
    ].join('\n'),
    ac: [
      'provide() returns the four pdf tool keys and False.',
      'The module imports with no PDF library present.',
      'No app.* import appears anywhere in the file.',
      'lint-imports reports the agents.capabilities -> app contract KEPT.',
    ],
  },

  T9: {
    kind: 'task', agentType: 'junior-engineer', model: 'haiku', phase: 'Binding',
    deps: [], files: [REGISTRY], file: REGISTRY, traces: 'FR-015',
    desc: [
      'backend/agents/capabilities/registry.py.',
      '',
      'Add ("tool", "pdf") AND ("input_provider", "pdf_pages") to _KNOWN, each with a',
      '"# spec 019" provenance comment matching the surrounding style exactly.',
      'Add both module paths to the discover list (around line 284).',
      '',
      '_KNOWN is the compiler\'s INV-4 membership surface — a name absent from it cannot be',
      'referenced at all. Add BOTH now even though the input provider lands in Phase 3; the',
      'entry is inert until its module exists, and splitting it across phases invites the',
      'second one being forgotten.',
      '',
      'Change nothing else in this file.',
    ].join('\n'),
    ac: [
      'Both (kind, name) pairs are present in _KNOWN with provenance comments.',
      'Both module paths are in the discover list.',
      'registry.is_registered("tool", "pdf") is True after discover().',
      'git diff shows additions only — no existing entry was reordered or edited.',
    ],
  },

  T10: {
    kind: 'task', agentType: 'junior-engineer', model: 'haiku', phase: 'Binding',
    deps: ['T8'], files: [TOOLS_INIT], file: TOOLS_INIT, traces: 'FR-015',
    desc: [
      'backend/agents/capabilities/tools/__init__.py.',
      '',
      'Add: from agents.capabilities.tools import pdf  # noqa: F401 — import side effect: @register',
      'and extend __all__.',
      '',
      'Registration happens as an IMPORT SIDE EFFECT. Spec 018 omitted this exact file from its',
      'plan and had to record it as a deviation — it is called out here so that does not happen',
      'a second time. Also update the module docstring if it counts the registered providers.',
    ].join('\n'),
    ac: [
      'Importing agents.capabilities.tools registers ("tool","pdf") with no other import needed.',
      '__all__ includes "pdf".',
      'The docstring\'s provider count, if it states one, matches reality.',
    ],
  },

  T11: {
    kind: 'task', agentType: 'junior-engineer', model: 'haiku', phase: 'Binding',
    deps: ['T10', 'V1'], files: [FACTORY], file: FACTORY, traces: 'FR-016',
    desc: [
      'backend/agents/factory.py — _resolve_custom_tool_keys.',
      '',
      'Add a branch resolving the four pdf_* keys via make_pdf_tools(sandbox), MIRRORING the',
      'playwright branch at approximately line 1094 — including its no-sandbox guard, which',
      'SKIPS rather than raises (an unbound tool would write outside the run).',
      '',
      'sandbox is ALREADY threaded through this signature by specs 017/018. Do NOT change the',
      'signature — that was the retired 014 draft\'s highest-risk edit and it is already done.',
      '',
      'Do NOT add a ctx.capabilities gate. This feature is granted by spec.tools',
      '(AGENT.md "tools: [pdf]"), never by a workflow capabilities flag. manifest.py stays',
      'byte-unchanged.',
      '',
      'Use a lazy import for make_pdf_tools, as the neighbouring branches do.',
    ].join('\n'),
    ac: [
      'An agent declaring tools: [pdf] resolves exactly four tools, plus its native filesystem tools.',
      'An unknown custom-tool key still raises ValueError.',
      'The _resolve_custom_tool_keys signature is unchanged.',
      'No capabilities-flag gate was added and manifest.py was not touched.',
      'pytest backend/tests/agents/test_create_runner.py -q passes.',
    ],
  },

  T12: {
    kind: 'task', agentType: 'junior-engineer', model: 'haiku', phase: 'Binding',
    deps: [], files: [SANDBOX], file: SANDBOX, traces: 'FR-018',
    desc: [
      'backend/app/agents/sandbox.py.',
      '',
      '1. Add _PDF_PREFIX = ".pdf/" beside _BROWSER_PREFIX (around line 59). Comment it: the',
      '   materialised pages a granted agent extracted; evidence for the human, not part of what',
      '   the run delivered.',
      '2. Add _PDF_PREFIX to the startswith tuple inside is_deliverable_relpath (around 440).',
      '3. LEAVE IT VISIBLE to list_files — inspectability is half of why this design was chosen',
      '   (research.md R-02). Do not add it to any listing exclusion.',
      '4. The .agent_outputs/ comment claims to be the ONLY listed-but-not-delivered prefix.',
      '   That stops being true. Correct it in the same voice.',
      '5. Update is_deliverable_relpath\'s docstring subtree count.',
      '',
      'Without step 2 every extracted PNG ships in WorkflowRun.output — the exact trap spec 018',
      'hit with .browser/.',
    ].join('\n'),
    ac: [
      'is_deliverable_relpath(".pdf/doc/pages/01/text.md") is False.',
      'is_deliverable_relpath(".pdf/doc/pages/01/image-1.png") is False.',
      'is_deliverable_relpath("presentation.html") is still True.',
      '.pdf/ paths still appear in list_files output.',
      'The docstring subtree count matches the actual tuple length.',
      'The .agent_outputs/ "only one" comment is corrected.',
      'pytest backend/tests/agents/test_sandbox_deliverable.py -q passes.',
    ],
  },

  T13: {
    kind: 'task', agentType: 'junior-engineer', model: 'haiku', phase: 'Binding',
    deps: ['T11'], files: [TEST_RUNNER], file: TEST_RUNNER, traces: 'FR-017',
    desc: [
      'backend/tests/agents/test_create_runner.py.',
      '',
      'ADD one test: an agent NOT declaring tools: [pdf] composes a tool set byte-identical to',
      'the pre-change snapshot.',
      '',
      'DO NOT MODIFY any existing test_tool_provider_* assertion. They must pass UNCHANGED.',
      'Updating a characterization snapshot to make a build green is exactly how a real tool-set',
      'regression gets papered over — the spec asks for them unchanged, not merely passing.',
      '',
      'Additions only.',
    ].join('\n'),
    ac: [
      'The new ungranted-agent test passes.',
      'Every pre-existing test in the file passes UNMODIFIED.',
      'git diff on this file shows additions only — no existing line changed or deleted.',
    ],
  },

  V2: {
    kind: 'validator', agentType: 'qa-engineer', model: 'haiku', phase: 'Binding',
    deps: ['T13', 'T12', 'T9'], files: [], guards: ['T8','T9','T10','T11','T12','T13'],
    desc: 'Checkpoint B — binding, import purity, and no deliverable leak.',
    ac: [
      'A granted agent has all four pdf tools; an ungranted agent\'s composed tool set is byte-identical to the pre-change snapshot.',
      'lint-imports reports the agents.capabilities -> app contract KEPT.',
      'git diff on backend/agents/workflows/manifest.py is EMPTY.',
      'Nothing under .pdf/ reaches serialize_sandbox_deliverable, and .pdf/ is still listed by list_files.',
      'No existing characterization assertion in test_create_runner.py was edited.',
      'pytest backend/tests/agents/test_create_runner.py -q and test_sandbox_deliverable.py -q both pass.',
    ],
  },

  // ---------------- Phase 3 — Delivery ----------------
  T14: {
    kind: 'task', agentType: 'junior-engineer', model: 'haiku', phase: 'Delivery',
    deps: ['V2'], files: [IP_PROVIDER], file: IP_PROVIDER, traces: 'FR-012, FR-012a, FR-012b',
    desc: [
      'Create backend/agents/capabilities/input_providers/pdf_pages.py.',
      '',
      'This is the ONLY mechanism in this codebase that puts an image in front of a model. No',
      'tool returns an image; playwright_take_screenshot and screenshot_pptx both write to disk',
      'and return text. Copy the shape of input_providers/run_images.py exactly.',
      '',
      '@register("input_provider", "pdf_pages", user_allowed=True). Satisfy the',
      'InputContentProvider port: a name attribute plus async def load(self, ctx) -> list,',
      'returning {"type":"image","source_type":"base64","mime_type":...,"data":...} blocks read',
      'from the run\'s .pdf/ tree.',
      '',
      'Degrade to [] when .pdf/ is absent, empty or unreadable — a broken extraction must never',
      'break the agent.',
      '',
      'Downscale every image to the per-image ceilings BEFORE returning. An over-ceiling image',
      'is rejected by the provider and fails the WHOLE request, not one tool call.',
      '',
      'The provider receives ctx and takes NO per-step arguments — scope must come from run/step',
      'state. Registry + stdlib imports only; no app.* import.',
    ].join('\n'),
    ac: [
      'Returns image content blocks when .pdf/ holds materialised pages.',
      'Returns [] when .pdf/ is absent, empty, or unreadable — no exception escapes.',
      'Every returned block is within the per-image pixel/byte/token ceilings.',
      'No app.* import; lint-imports contract kept.',
      'The block shape matches run_images.py exactly.',
    ],
  },

  T15: {
    kind: 'task', agentType: 'junior-engineer', model: 'haiku', phase: 'Delivery',
    deps: ['T14'], files: [IP_INIT], file: IP_INIT, traces: 'FR-012',
    desc: [
      'backend/agents/capabilities/input_providers/__init__.py.',
      '',
      'Add the import side effect for pdf_pages (same shape as the tools package).',
      '',
      'Correct the docstring: it currently says "The sole provider this wave: run_images",',
      'which stops being true. Name both, in the same voice.',
    ].join('\n'),
    ac: [
      'Importing the package registers ("input_provider","pdf_pages").',
      'The docstring names both providers and no longer claims a sole one.',
    ],
  },

  T16: {
    kind: 'task', agentType: 'junior-engineer', model: 'haiku', phase: 'Delivery',
    deps: ['T15'], files: [TEST_IP], file: TEST_IP, traces: 'FR-012',
    desc: [
      'Create backend/tests/agents/test_pdf_pages_provider.py.',
      '',
      'Cover: a step declaring injects: [pdf_pages] receives image blocks; a step not declaring',
      'it receives none; an absent .pdf/ tree is dormant and yields [].',
      '',
      'The dormancy test is the important one — it is what proves INV-3 byte/event parity holds',
      'for every existing workflow.',
    ].join('\n'),
    ac: [
      'pytest backend/tests/agents/test_pdf_pages_provider.py -q passes standalone.',
      'A dormancy test exists and asserts [] with no .pdf/ tree.',
    ],
  },

  V3: {
    kind: 'validator', agentType: 'qa-engineer', model: 'haiku', phase: 'Delivery',
    deps: ['T16'], files: [], guards: ['T14','T15','T16'],
    desc: 'Checkpoint C — images actually reach a declaring step.',
    ac: [
      'A step declaring injects: [pdf_pages] gets image content blocks in its composed input.',
      'A step not declaring it gets none — dormancy holds for every existing workflow.',
      'Import purity kept and per-image ceilings enforced.',
      'pytest backend/tests/agents/test_pdf_pages_provider.py -q passes.',
    ],
  },

  // ---------------- Phase 4 — Parallelism ----------------
  T17: {
    kind: 'task', agentType: 'senior-engineer', model: 'sonnet', phase: 'Parallelism',
    deps: ['V3'], files: [PDF_TOOLS], file: PDF_TOOLS,
    traces: 'FR-013, FR-013a, FR-013b, FR-014',
    desc: [
      'Add parallel materialisation to pdf_tools.py. Classified sonnet because the failure mode',
      'is a dead backend worker.',
      '',
      'ProcessPoolExecutor, FOUR workers, engaged ONLY above a page threshold (~30), the whole',
      'call wrapped in asyncio.to_thread. Both numbers are NAMED MODULE CONSTANTS so they can be',
      'recalibrated in one place.',
      '',
      'Each worker takes a CONTIGUOUS page range and opens the document ONCE. Per-page tasks are',
      'dominated by re-opening the file and do not scale.',
      '',
      'NEVER A THREAD. Measured: pdfplumber gains 0.99x on 4 threads (pure Python, GIL-bound),',
      'and pypdfium2 rendering across threads CRASHES THE PROCESS — exit 133, SIGTRAP, no',
      'traceback, nothing to catch. PDFium is not thread-safe. In the backend that kills the',
      'worker and every concurrent run on it.',
      '',
      'asyncio.to_thread around the whole blocking call is REQUIRED and is not a violation of',
      'the above: that is one thread for non-blocking, not many for speed. Without it a',
      'multi-second synchronous call stalls the run\'s event stream and the user sees a hung run.',
      '',
      'Below the threshold, run sequentially — process spawn is a fixed cost a small document',
      'never earns back. The 21-page reference document MUST take the sequential path.',
      '',
      'This is the repo\'s first ProcessPoolExecutor. main.py and handoff_pipeline.py use',
      'asyncio.to_thread only.',
    ].join('\n'),
    ac: [
      'A document above the threshold materialises across processes, and its output is byte-identical to the sequential path.',
      'The 21-page reference document takes the sequential path.',
      'grep -rn "ThreadPoolExecutor\\|threading" backend/app/agents/tools/pdf_tools.py returns NOTHING.',
      'The worker count and page threshold are named module constants.',
      'The blocking call is wrapped in asyncio.to_thread.',
      'Each worker opens the document once per contiguous range, not once per page.',
    ],
  },

  V4: {
    kind: 'validator', agentType: 'qa-engineer', model: 'haiku', phase: 'Parallelism',
    deps: ['T17'], files: [], guards: ['T17'],
    desc: 'Checkpoint D — parallel, non-blocking, and provably thread-free.',
    ac: [
      'HARD GATE: grep -rn "ThreadPoolExecutor\\|threading" backend/app/agents/tools/pdf_tools.py returns nothing. Report FAIL if it returns anything at all.',
      'Parallel and sequential paths produce identical output for the same document.',
      'The threshold is a named constant and the 21-page document is below it.',
      'asyncio.to_thread wraps the blocking call so the event stream keeps flowing.',
      'pytest backend/tests/agents/test_pdf_tools.py -q passes.',
    ],
  },

  // ---------------- Phase 5 — Sidecar ----------------
  T18: {
    kind: 'task', agentType: 'senior-engineer', model: 'sonnet', phase: 'Sidecar',
    deps: ['V4'], files: [FILE_EXTRACT], file: FILE_EXTRACT, traces: 'FR-022, FR-023',
    desc: [
      'backend/app/api/file_extract.py — a PRE-EXISTING defect this feature would otherwise',
      'contradict. Classified sonnet because of its blast radius.',
      '',
      '_extract_pdf joins per-page text with EMPTY PAGES DROPPED, so sidecar page N is not',
      'document page N, and any citation taken from the brief is silently wrong. Preserve page',
      'correspondence.',
      '',
      'Separately: an ImportError must log at ERROR naming the module, distinguishable from a',
      'genuine parse failure. The function still returns a string and NEVER raises — the return',
      'contract run_files.py depends on is unchanged.',
      '',
      'THIS IS THE ONLY CHANGE WHOSE BLAST RADIUS REACHES EXISTING WORKFLOWS. It alters the',
      'brief text of anything already using injects: [uploaded_files]. In your summary, NAME',
      'which workflows declare that inject and describe what their brief now contains.',
      '',
      'Held to last on purpose. Do not widen it.',
    ].join('\n'),
    ac: [
      'A PDF whose page 2 has no text yields a sidecar in which page 3\'s text is still at position 3.',
      'A missing dependency logs at ERROR naming the module; a parse failure logs differently.',
      '_extract_pdf still returns a string and never raises.',
      'The summary names every workflow declaring injects: [uploaded_files] and what changed for it.',
      'pytest backend/tests/unit/test_file_extract_fix191.py -q passes.',
    ],
  },

  V5: {
    kind: 'validator', agentType: 'qa-engineer', model: 'haiku', phase: 'Sidecar',
    deps: ['T18'], files: [], guards: ['T18'],
    desc: 'Checkpoint E — page correspondence holds and the blast radius is stated.',
    ac: [
      'Page correspondence holds on a document containing an empty page.',
      'The dependency-missing and parse-failure log lines are distinguishable.',
      'The change in brief content is described explicitly, naming affected workflows.',
      'The only file YOU edited is backend/app/api/file_extract.py. Other changes in the working tree belong to sibling tasks — leave them alone.',
    ],
  },
}

// ---------------------------------------------------------------------------
// Scheduler — do not edit below this line for a normal generation.
// ---------------------------------------------------------------------------

const MAX_PARALLEL = 4
const NORMAL_FIX_ATTEMPTS = 3
const SENIOR_FIX_ATTEMPTS = 2
const LEAD_FIX_ATTEMPTS = 2

function escalationLadder(node) {
  if (node.agentType === 'junior-engineer') {
    return [
      { agentType: 'junior-engineer', model: node.model, attempts: NORMAL_FIX_ATTEMPTS },
      { agentType: 'senior-engineer', model: node.model, attempts: SENIOR_FIX_ATTEMPTS },
      { agentType: 'technical-lead', model: 'opus', attempts: LEAD_FIX_ATTEMPTS },
    ]
  }
  if (node.agentType === 'senior-engineer') {
    return [
      { agentType: 'senior-engineer', model: node.model, attempts: NORMAL_FIX_ATTEMPTS },
      { agentType: 'technical-lead', model: 'opus', attempts: LEAD_FIX_ATTEMPTS },
    ]
  }
  return [
    { agentType: node.agentType, model: node.model, attempts: NORMAL_FIX_ATTEMPTS },
    { agentType: node.agentType, model: 'opus', attempts: LEAD_FIX_ATTEMPTS },
  ]
}

function maxAttemptsFor(node) {
  return escalationLadder(node).reduce((sum, tier) => sum + tier.attempts, 0)
}

function tierForAttempt(node, attempt) {
  let remaining = attempt
  const ladder = escalationLadder(node)
  for (const tier of ladder) {
    if (remaining <= tier.attempts) return tier
    remaining -= tier.attempts
  }
  return ladder[ladder.length - 1]
}

const state = {}
const results = {}
const taskFailCount = {}
for (const id of Object.keys(NODES)) state[id] = 'pending'

async function safeAgent(prompt, opts) {
  try {
    return await agent(prompt, opts)
  } catch (e) {
    log(`agent() threw for ${opts.label || '(unlabeled)'}: ${e?.message || e}`)
    return null
  }
}

async function safeAgentRetrying(prompt, opts, retries = 2) {
  for (let i = 0; i <= retries; i++) {
    const r = await safeAgent(prompt, i === 0 ? opts : { ...opts, label: `${opts.label}-infra-retry${i}` })
    if (r) return r
    if (i < retries) log(`${opts.label}: agent() call itself failed (infra/schema glitch, not a task defect) — retrying (${i + 1}/${retries})`)
  }
  return null
}

function isReady(id) {
  return state[id] === 'pending' && NODES[id].deps.every((d) => state[d] === 'done')
}

function filesInFlight() {
  const set = new Set()
  for (const [id, s] of Object.entries(state)) {
    if (s === 'running') for (const f of NODES[id].files || []) set.add(f)
  }
  return set
}

function collidesWithRunning(id) {
  const inFlight = filesInFlight()
  return (NODES[id].files || []).some((f) => inFlight.has(f))
}

function taskPrompt(id, feedback) {
  const t = NODES[id]
  const feedbackBlock = feedback ? `
==============================================================================
THIS IS A RETRY. A validator already REJECTED this task's work. Do not just repeat the same
approach — read the failure evidence below and fix the SPECIFIC problem it names.

Validator's failure report:
${feedback}
==============================================================================
` : ''
  return `
You are executing task ${id}, as one step of an automated workflow. Another agent will
validate your work afterward against the acceptance criteria below — be honest in your
self-check, do not claim something passed if you are unsure.

${REPO_NOTES}
${feedbackBlock}
TASK ${id}
File(s): ${t.file}
${t.traces ? `Traces to: ${t.traces}\n` : ''}
Description:
${t.desc}

Acceptance criteria (self-check each one honestly before returning):
${t.ac.map((a, i) => `${i + 1}. ${a}`).join('\n')}

Do the work now using your file/bash tools. Then return the structured result: taskId="${id}",
status ("done" if you completed the work and believe the AC are met, "blocked" if you could not
proceed — explain why in "blockers"), filesChanged (the real list of paths you touched),
summary (what you actually did, 2-4 sentences), and acSelfCheck (one entry per AC line above,
with met:true/false and a short note).
`.trim()
}

function validatorPrompt(id) {
  const v = NODES[id]
  const reportsText = v.guards
    .map((gid) => {
      const r = results[gid]
      if (!r) return `${gid}: NOT YET RUN`
      if (typeof r === 'string') return `${gid}: ${r}`
      return `${gid} [${r.status || (r.pass ? 'pass' : 'fail')}] — ${r.summary}\n  filesChanged: ${(r.filesChanged || []).join(', ') || '(none reported)'}\n  self-check: ${JSON.stringify(r.acSelfCheck || r.checks)}`
    })
    .join('\n\n')
  return `
You are validator ${id}. You guard: ${v.guards.join(', ')}.
Your job is to judge, by actually inspecting the code and running commands, whether these
genuinely satisfy the criteria below — do NOT just trust the task reports, they are context only.

${REPO_NOTES}

${v.context ? `IMPORTANT CONTEXT: ${v.context}\n` : ''}
TASK/GUARD REPORTS (context, verify independently):
${reportsText}

PASS requires ALL of the following (check each by inspection/exercise, not by reading the diff alone):
${v.criteria.map((c, i) => `${i + 1}. ${c}`).join('\n')}

For each criterion, actually check it — read the relevant files, run the project's real
verify/test commands, and where a criterion requires exercising live behavior you cannot
directly run, reason carefully from the code and say explicitly in "evidence" that this is
inferred rather than observed directly.

Return: validatorId="${id}", pass (true only if every criterion passes), checks (one entry per
criterion with result pass/fail and evidence), failedTasks (which of ${v.guards.join(', ')} are
responsible — empty array if pass), summary (2-4 sentences).
`.trim()
}

async function runNode(id) {
  const node = NODES[id]
  state[id] = 'running'
  log(`-> ${id} [${node.agentType || node.model}] (${node.phase}) starting`)

  if (node.kind === 'task') {
    // Tasks retry on an INFRA failure exactly as validators do. The first run of spec 019
    // lost 4 of 11 agents to empty results — every one had already written correct code —
    // and each was marked 'error', blocking V1 and 13 downstream nodes over a reporting
    // glitch rather than a defect. safeAgent (no retry) here was the bug.
    const report = await safeAgentRetrying(taskPrompt(id), {
      label: id, phase: node.phase, agentType: node.agentType, model: node.model, schema: TASK_RESULT_SCHEMA,
    })
    state[id] = report ? 'done' : 'error'
    results[id] = report
    log(`${state[id] === 'done' ? 'OK' : 'FAILED'} ${id}${report ? ` (self-reported: ${report.status})` : ' (no report)'}`)
    return
  }

  let result = await safeAgentRetrying(validatorPrompt(id), {
    label: id, phase: node.phase, agentType: node.agentType, model: node.model, schema: VALIDATOR_RESULT_SCHEMA,
  })

  let round = 0
  while (result && !result.pass && result.failedTasks?.length > 0) {
    const redoable = result.failedTasks.filter(
      (tid) => NODES[tid] && NODES[tid].kind === 'task' && (taskFailCount[tid] || 0) < maxAttemptsFor(NODES[tid])
    )
    const exhausted = result.failedTasks.filter((tid) => NODES[tid] && (taskFailCount[tid] || 0) >= maxAttemptsFor(NODES[tid]))

    if (exhausted.length) {
      for (const tid of exhausted) {
        log(`${id}: ${tid} already exhausted its ${maxAttemptsFor(NODES[tid])}-attempt escalation ladder — not retrying again.`)
      }
    }
    if (redoable.length === 0) {
      log(`${id}: every currently-failing task has exhausted its fix budget — stopping retries, reporting blocked.`)
      break
    }

    round++
    log(`VALIDATOR FAIL ${id} (round ${round}) — redoing ${redoable.join(', ')}`)

    const failedChecks = (result.checks || []).filter((c) => c.result === 'fail')
    const feedbackText = [
      result.summary || '',
      failedChecks.length
        ? `Failed criteria:\n${failedChecks.map((c) => `- ${c.criterion}\n  Evidence: ${c.evidence}`).join('\n')}`
        : '',
    ].filter(Boolean).join('\n\n')

    const redone = await parallel(
      redoable.map((tid) => async () => {
        taskFailCount[tid] = (taskFailCount[tid] || 0) + 1
        const attempt = taskFailCount[tid]
        const tier = tierForAttempt(NODES[tid], attempt)
        const escalated = tier.agentType !== NODES[tid].agentType
        if (escalated) {
          log(`${tid}: attempt ${attempt}/${maxAttemptsFor(NODES[tid])} — escalating to ${tier.agentType}${tier.model === 'opus' ? ' (opus)' : ''}.`)
        }
        const r = await safeAgent(taskPrompt(tid, feedbackText), {
          label: `${tid}-retry${attempt}${escalated ? `-${tier.agentType}` : ''}`,
          phase: NODES[tid].phase,
          agentType: tier.agentType,
          model: tier.model,
          schema: TASK_RESULT_SCHEMA,
        })
        return [tid, r]
      })
    )
    for (const pair of redone.filter(Boolean)) {
      const [tid, r] = pair
      if (r) results[tid] = r
    }

    result = await safeAgentRetrying(validatorPrompt(id), {
      label: `${id}-recheck${round}`, phase: node.phase, agentType: node.agentType, model: node.model, schema: VALIDATOR_RESULT_SCHEMA,
    })
  }

  if (result && result.pass) {
    state[id] = 'done'
    results[id] = result
    log(`VALIDATOR PASS ${id}${round ? ` (after ${round} fix round${round === 1 ? '' : 's'})` : ''} — ${result.summary}`)
  } else {
    state[id] = 'error'
    results[id] = result
    log(`VALIDATOR ${id} still FAILING after ${round} fix round(s) — PHASE BLOCKED. ${result ? result.summary : '(no result)'}`)
  }
}

async function scheduler() {
  const active = new Map()

  while (true) {
    const remaining = Object.keys(NODES).filter((id) => state[id] !== 'done' && state[id] !== 'error')
    if (remaining.length === 0) break

    const anyRunning = active.size > 0
    const anyReady = remaining.some((id) => isReady(id) && !collidesWithRunning(id))
    if (!anyRunning && !anyReady) {
      const stuck = remaining.filter((id) => state[id] === 'pending')
      log(`Nothing left can become ready — ${stuck.length} node(s) permanently blocked (likely a failed hard-gate upstream): ${stuck.join(', ')}`)
      break
    }

    while (active.size < MAX_PARALLEL) {
      const next = Object.keys(NODES).find((id) => isReady(id) && !collidesWithRunning(id) && !active.has(id))
      if (!next) break
      const p = runNode(next)
        .catch((e) => { log(`runNode(${next}) threw unexpectedly: ${e?.message || e}`); state[next] = 'error' })
        .then(() => { active.delete(next) })
      active.set(next, p)
    }

    if (active.size === 0) break
    await Promise.race(active.values())
  }

  await Promise.all(active.values())
}

phase('Foundation')
phase('Session')
phase('Binding')
phase('Acceptance')

log(`Spec 018 — ${Object.keys(NODES).length} nodes. Dispatching every node whose deps are satisfied, up to ${MAX_PARALLEL} concurrent.`)

await scheduler()

const done = Object.keys(NODES).filter((id) => state[id] === 'done')
const errored = Object.keys(NODES).filter((id) => state[id] === 'error')

log(`Finished: ${done.length}/${Object.keys(NODES).length} done, ${errored.length} error/blocked.`)
if (errored.length) log(`Blocked nodes: ${errored.join(', ')} — see their reports for what to fix.`)

// Ledger sync — a third role, distinct from doing the work and from judging it.
// Unlike spec 018's version this ALSO restyles the mermaid task graph, because a status
// diagram that goes stale is worse than no diagram: it reports progress that did not happen.
// Edges are still never touched — only node classes.
await safeAgent(
  [
    'You are recording results into a task ledger. You do NOT write code and you do NOT judge work.',
    '',
    'File: specs/019-file-extract-support/tasks.md',
    '',
    'It contains a "## Ledger" markdown table with a status column of empty checkboxes, a',
    '"**Status**:" line near the top, and a "## Task graph" mermaid diagram whose last two',
    'lines define classDef done and classDef blocked.',
    '',
    'Update ONLY status representations:',
    '  1. Ledger status cells: a checked box for done ids, the word BLOCKED for errored ids.',
    '  2. The evidence column: one short phrase per completed row (e.g. the test that passed).',
    '  3. The "**Status**:" line: the done/total task and checkpoint counts.',
    '  4. The mermaid graph: append (or update) ONE class line per settled node at the end of',
    '     the diagram, immediately before the classDef lines — e.g.',
    '         class T1,T2,T3 done',
    '         class T7 blocked',
    '     Use exactly two class lines at most: one for done ids, one for blocked ids. If a',
    '     class line already exists, REPLACE it rather than adding a second.',
    '',
    'DONE ids: ' + (done.join(', ') || '(none)'),
    'BLOCKED ids: ' + (errored.join(', ') || '(none)'),
    '',
    'Do NOT touch any task description, acceptance criterion, prose section, the model',
    'classification table, or any mermaid EDGE or node LABEL. Do NOT edit any file other than',
    'tasks.md. Do NOT run any git command.',
    '',
    'Return taskId="LEDGER", status="done", filesChanged, a 2-sentence summary, and an',
    'acSelfCheck confirming you changed only status representations and mermaid class lines.',
  ].join('\n'),
  { label: 'ledger-sync', phase: 'Sidecar', agentType: 'junior-engineer', model: 'haiku', schema: TASK_RESULT_SCHEMA },
)

return {
  done, errored, results,
  summary: `${done.length}/${Object.keys(NODES).length} nodes done. ` +
    (errored.length ? `Blocked at: ${errored.join(', ')}.` : 'All nodes passed.'),
}
