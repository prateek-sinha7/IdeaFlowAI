export const meta = {
  name: 'spec-018-playwright-tools',
  description: 'Spec 018 — a Playwright tool set agents can be granted: 13 tasks + 4 validators, dependency-scheduled',
  phases: [
    { title: 'Foundation', detail: 'T1, T2 + V1' },
    { title: 'Session', detail: 'T3a-T3c, T7, T11 + V2 (hard gate)' },
    { title: 'Binding', detail: 'T4, T5, T6, T8, T9, T10 + V3' },
    { title: 'Acceptance', detail: 'V4' },
  ],
}

const REPO_NOTES = `
PROJECT: VELOCITY-AI (internally "Flowin") — a workflow-agnostic agent execution runtime.
Backend is Python/FastAPI under backend/. You are working in the main checkout on branch
feat/conditional-gates.

HOW TO VERIFY
- Run ONE test file at a time. NEVER run the full suite — it breaks the user's machine.
  Each task names its exact command; run that and nothing broader.
- Backend tests: pytest <path> -q, invoked from the repository root.
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
  not broken. Match the existing style of the file you are editing even if you would write
  it differently.
- If you notice unrelated dead code or a bug outside your task, MENTION it in your summary.
  Do not fix it.
- Remove imports/variables your OWN change orphaned. Leave pre-existing dead code alone.

OFF LIMITS
- backend/app/agents/render_check.py must NOT be modified, refactored, or imported from the
  new session module. It is a working macro with its own browser lifecycle. Spec 018 depends
  on it staying byte-identical; a validator checks this.
- backend/agents/capabilities/gates/validation.py and
  backend/agents/capabilities/strategies/task_loop.py (the engine-side callers of
  render_check) are also untouched.
- No database migrations. No workflow manifest changes under backend/agents/workflows/.
  No frontend changes.

ARCHITECTURE INVARIANTS THAT APPLY HERE
- SC-001: the kernel stays workflow-agnostic. No "if pipeline_type == ..." and no
  workflow-name or agent-name literal in any resolution path you write.
- backend/agents/capabilities/ MUST NOT import from app.* — an import-linter contract
  enforces this. Capability providers emit STRING KEYS; the factory resolves them.
- Every sandbox path goes through RunSandbox.path_for, which is traversal-proof.

REFERENCE IMPLEMENTATIONS — read these before writing new code
- backend/app/agents/tools/pptx_tools.py — the per-run sandbox-bound tool module shape.
- backend/agents/capabilities/tools/pptx.py — the string-key provider shape.
- backend/agents/factory.py lines 997-1085 — the key-resolution branch shape.
- backend/app/agents/render_check.py — how this codebase already drives headless Chromium
  (read it for the launch args and the availability-degradation pattern; do not edit it).

SPEC DOCUMENTS
- specs/018-agent-browser-tools/spec.md — requirements (FR-nnn) and success criteria.
- specs/018-agent-browser-tools/plan.md — the design, file inventory, and rationale.
- specs/018-agent-browser-tools/tasks.md — your task, verbatim.
Read the plan before your first edit. It explains WHY, which the task text assumes.
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

const SANDBOX = 'backend/app/agents/sandbox.py'
const CONFIG = 'backend/app/core/config.py'
const SESSION = 'backend/app/agents/playwright_session.py'
const TOOLS = 'backend/app/agents/tools/playwright.py'
const PROVIDER = 'backend/agents/capabilities/tools/playwright.py'
const FACTORY = 'backend/agents/factory.py'
const ENGINE = 'backend/agents/execution_engine/engine.py'
const AGENT_DECKQA = 'backend/agents/prompts/ppt-deck-qa-v2/AGENT.md'
const AGENT_PROTOVAL = 'backend/agents/prompts/prototype-validate/AGENT.md'
const TEST_TOOLS = 'backend/tests/agents/test_playwright_tools.py'
const TEST_SESSION = 'backend/tests/agents/test_playwright_session.py'

const NODES = {
  T1: {
    kind: 'task', agentType: 'junior-engineer', phase: 'Foundation',
    deps: [], files: [SANDBOX], file: SANDBOX, traces: 'FR-006',
    desc: [
      'Reserve a ".browser/" sandbox prefix so browser output stays VISIBLE in the run',
      'workspace but is EXCLUDED from the deliverable — exactly as ".verify/" already does.',
      '',
      'Steps:',
      '1. Add _BROWSER_PREFIX = ".browser/" alongside _VERIFY_PREFIX (around line 54).',
      '   Comment it: screenshots and page captures a granted agent takes land here; they are',
      '   evidence for the human, not part of what the run delivered.',
      '2. Add _BROWSER_PREFIX to the startswith tuple inside is_deliverable_relpath',
      '   (around line 434).',
      '3. Update that function docstring — it currently says "the four reserved subtrees".',
      '   It is now five. Name the new one in the same style as the others.',
      '',
      'Change NOTHING else in this file. is_deliverable_relpath is the ONE definition used by',
      'both the deliverable walk and the workspace API — editing it here is precisely why the',
      'UI cannot drift from the walk. Do not add a second copy of the rule anywhere.',
    ].join('\n'),
    ac: [
      'is_deliverable_relpath(".browser/shot.png") returns False.',
      'is_deliverable_relpath(".browser/nested/a.png") returns False.',
      'is_deliverable_relpath("presentation.html") still returns True.',
      'The docstring subtree count matches the actual tuple length.',
      'pytest backend/tests/agents/test_sandbox_deliverable.py -q passes.',
      'git diff --stat shows ONLY backend/app/agents/sandbox.py changed.',
    ],
  },

  T2: {
    kind: 'task', agentType: 'junior-engineer', phase: 'Foundation',
    deps: [], files: [CONFIG], file: CONFIG, traces: 'FR-015',
    desc: [
      'Add the configurable browser URL policy SETTING. This task is the setting only —',
      'the parsing logic belongs to T3b and must NOT be written here.',
      '',
      'In the Settings class (starts around line 93), following the exact style of its',
      'neighbours, add:',
      '',
      '    BROWSER_URL_POLICY: str = "file,localhost"',
      '',
      'Comment it with three things:',
      '  - what each token permits: "file" (local files, resolved through the run sandbox),',
      '    "localhost" (http on localhost / 127.0.0.1 only), "http" (any http(s)).',
      '  - that "file" paths resolve through RunSandbox.path_for and cannot escape the run.',
      '  - that adding "http" grants model-driven OUTBOUND egress from a container holding',
      '    database credentials — the same trust surface as web_fetch — which is why it is',
      '    not in the default.',
      '',
      'Place it near the other feature-flag style settings, not at the top of the class.',
      'Do not touch any other setting.',
    ],
    ac: [
      'settings.BROWSER_URL_POLICY equals "file,localhost" with no environment override set.',
      'The field is typed str and sits with its neighbours in the Settings class.',
      'The comment names all three tokens and states the http egress risk.',
      'No parsing/validation logic was added in this file.',
      'git diff --stat shows ONLY backend/app/core/config.py changed.',
    ],
  },

  T3a: {
    kind: 'task', agentType: 'senior-engineer', phase: 'Session',
    deps: ['V1'], files: [SESSION], file: SESSION + '  (new file)',
    traces: 'FR-007, FR-008, FR-009, FR-010, FR-011, FR-018',
    desc: [
      'Create PlaywrightSession — the per-run browser lifecycle owner. This is the one piece',
      'of genuinely new machinery in spec 018 and the only place its known failure mode lives.',
      '',
      'READ FIRST: .knowledge/cards/20260826-0124-FIX-307.md, and',
      'backend/app/agents/render_check.py (for the launch args and the availability pattern —',
      'do not edit that file).',
      '',
      'THE CONSTRAINT THAT DEFINES THIS FILE:',
      'render_check.py wraps its browser work in "async with async_playwright()". That is',
      'correct for a MACRO that launches, works, and tears down in one call. It is WRONG here,',
      'because this session must outlive a single tool call. Leaving that block tears the',
      'browser down and the next page acquisition raises "Target page, context or browser has',
      'been closed". FIX-307 is exactly that bug, and the reason it went unnoticed for weeks is',
      'that the error was swallowed into a findings list — the validator reported CLEAN on',
      'every run. So:',
      '',
      '  - Use: pw = await async_playwright().start()   ... later ...   await pw.stop()',
      '  - NEVER use: async with async_playwright()',
      '',
      'Required behaviour:',
      '1. LAZY. Nothing launches until the first acquisition. An agent granted the tool set but',
      '   never calling a tool must cost no browser launch.',
      '2. chromium.launch(args=["--no-sandbox"]), matching render_check.py line 207. This',
      '   disables CHROMIUM own process sandbox (required inside the container) and has nothing',
      '   to do with RunSandbox isolation — say so in a comment, because the two share a word',
      '   and the next reader will assume it weakens run isolation.',
      '3. ONE browser per run. ONE BrowserContext per agent id. Contexts are cheap and isolate',
      '   cookies/storage; a browser per agent multiplies ~150 MB by the fan-out width.',
      '4. A module-level registry keyed by run id, so the tools (T4) and the engine (T7) reach',
      '   the same session object.',
      '5. release(run_id): idempotent, safe for a run that never had a session, and it MUST NOT',
      '   raise. It will be called from a finally: inside a 10,000-line async generator; a',
      '   release that throws there would mask the exception passing through it.',
      '6. An idle timer that releases after inactivity — defence in depth behind T7 finally.',
      '7. AVAILABILITY: if the playwright import fails or Chromium will not launch, the session',
      '   reports UNAVAILABLE so every downstream tool can say so. It must never present as a',
      '   working session that silently does nothing. That is the FIX-307 failure mode and',
      '   FR-018 forbids it.',
      '',
      'Do NOT write the URL policy resolver (T3b) or the snapshot/ref registry (T3c) here —',
      'those are separate tasks on this same file and will run after you.',
      '',
      'NOTE ON THE FILENAME: this module is app/agents/playwright_session.py and T4 will add',
      'app/agents/tools/playwright.py. Neither shadows the installed playwright package —',
      'Python 3 imports are absolute and these are package modules.',
    ].join('\n'),
    ac: [
      'The string "async with async_playwright" does NOT appear anywhere in the file.',
      'async_playwright().start() is held on the instance and stop() is called in release().',
      'Acquiring twice for the same run id returns the same browser instance.',
      'Acquiring for two different agent ids returns two different BrowserContext objects.',
      'No browser is launched until the first acquisition.',
      'release() on an unknown run id is a no-op and raises nothing.',
      'release() is idempotent — calling it twice for the same run raises nothing.',
      'The module imports cleanly on a machine where playwright is not installed, and reports unavailable rather than raising at import time.',
      'launch args include --no-sandbox with a comment distinguishing it from RunSandbox.',
      'git diff --stat shows ONLY the new backend/app/agents/playwright_session.py.',
    ],
  },

  T3b: {
    kind: 'task', agentType: 'junior-engineer', phase: 'Session',
    deps: ['T3a'], files: [SESSION], file: SESSION, traces: 'FR-015, FR-016',
    desc: [
      'Add the URL policy resolver to playwright_session.py. A PURE function — no browser, no',
      'network, no I/O beyond RunSandbox.path_for. It must be testable offline.',
      '',
      'It takes a requested URL (or path) plus the run sandbox, reads',
      'settings.BROWSER_URL_POLICY (added by T2), and returns EITHER a resolved URL to open OR',
      'a refusal string explaining why.',
      '',
      'Policy tokens, parsed from the comma-separated setting:',
      '  - "file": resolve the requested path through RunSandbox.path_for (traversal-proof)',
      '    and return a file:// URI for it. A path that escapes the sandbox is REFUSED.',
      '  - "localhost": permit http://localhost:<port> and http://127.0.0.1:<port> only.',
      '  - "http": permit any http(s) URL. NOT in the default policy.',
      '  - anything not permitted by an active token: REFUSED.',
      '',
      'The refusal must happen BEFORE any network or filesystem access occurs, and must name',
      'the active policy in its text so the agent can act on it rather than guessing. Example',
      'shape: "refused: https://example.com is not permitted by BROWSER_URL_POLICY=file,localhost".',
      '',
      'Do not touch anything T3a wrote. Add only this function and whatever tiny helper it',
      'needs.',
    ].join('\n'),
    ac: [
      'Under the default policy, a sandbox-relative path resolves to a file:// URI.',
      'Under the default policy, https://example.com is refused and the message names BROWSER_URL_POLICY and its value.',
      'A path like ../../etc/passwd is refused (path_for rejects it) rather than resolved.',
      'http://localhost:3000 is permitted under the default policy.',
      'http://evil.example is refused under the default policy.',
      'Setting the policy string to include "http" permits https://example.com with NO code change.',
      'The function performs no network or browser calls and is callable without a running event loop.',
      'git diff --stat shows ONLY backend/app/agents/playwright_session.py changed.',
    ],
  },

  T3c: {
    kind: 'task', agentType: 'junior-engineer', phase: 'Session',
    deps: ['T3a'], files: [SESSION], file: SESSION, traces: 'FR-012',
    desc: [
      'Add the structure readback (snapshot) and its element reference registry to',
      'playwright_session.py. This is what lets an agent act on a page WITHOUT coordinates and',
      'WITHOUT vision, and it is the difference between a tool set that works and one that',
      'flails.',
      '',
      '1. Produce a COMPACT text listing of the page interactive and landmark elements. For',
      '   each: its role, its accessible name, and a short stable reference token.',
      '   Example line shape:   button "Next slide" [ref=e14]',
      '2. Keep a per-page map from reference token to the real element, so the interaction',
      '   verbs in T4 can resolve a ref back to something clickable.',
      '3. INVALIDATE that map on navigation. An action using a ref from a previous page must',
      '   report that the ref is STALE and that a fresh snapshot is needed. It must NEVER',
      '   silently act on whatever element now occupies that slot — that is a wrong-element',
      '   action the agent has no way to detect.',
      '4. Keep the output COMPACT. This lands in a model context window on every call; a full',
      '   accessibility-tree dump of a large page is a context bomb. Prefer interactive',
      '   elements and landmarks over every node.',
      '',
      'Do not touch T3a lifecycle code or T3b policy resolver.',
    ].join('\n'),
    ac: [
      'A snapshot of a page containing a button and a link lists both, each with a distinct ref token.',
      'Resolving a ref token returns the corresponding element.',
      'After navigating to a different page, a ref from the previous page reports stale rather than resolving.',
      'The snapshot output is text and stays compact — it does not dump the entire accessibility tree.',
      'git diff --stat shows ONLY backend/app/agents/playwright_session.py changed.',
    ],
  },

  V1: {
    kind: 'validator', agentType: 'qa-engineer', phase: 'Foundation',
    deps: ['T1', 'T2'], guards: ['T1', 'T2'],
    context: 'T1 and T2 are deliberately small and independent. T2 must NOT contain parsing logic — that is T3b job, and finding parsing here means T2 overreached its scope.',
    criteria: [
      'is_deliverable_relpath excludes ".browser/" paths and still includes ordinary deliverable paths. Verify by reading the function AND running pytest backend/tests/agents/test_sandbox_deliverable.py -q.',
      'The .verify/, .uploads/, .logs/ and .agents/ exclusions still behave exactly as before — T1 added a prefix, it did not restructure the predicate.',
      'The is_deliverable_relpath docstring subtree count matches the actual tuple length.',
      'settings.BROWSER_URL_POLICY exists, is typed str, and defaults to "file,localhost".',
      'The BROWSER_URL_POLICY comment names all three tokens and states the outbound-egress risk of adding http.',
      'T2 added NO parsing or validation logic — the setting is a plain declared field.',
      'Exactly two files changed across both tasks: backend/app/agents/sandbox.py and backend/app/core/config.py. Confirm with git diff --stat.',
    ],
  },

  T4: {
    kind: 'task', agentType: 'junior-engineer', phase: 'Binding',
    deps: ['V2'], files: [TOOLS], file: TOOLS + '  (new file)',
    traces: 'FR-013, FR-013a, FR-014, FR-017',
    desc: [
      'Create the nine playwright_* tools plus bind_sandbox(sandbox).',
      '',
      'MODEL THIS FILE ON backend/app/agents/tools/pptx_tools.py. Read it first. Same',
      'module-level _SANDBOX bound by the factory, same docstring discipline, same contract.',
      '',
      'The nine tools:',
      '  playwright_navigate          — open a URL or a workspace file',
      '  playwright_snapshot          — read back the page structure with refs',
      '  playwright_click             — click an element by ref',
      '  playwright_type              — type into an element by ref',
      '  playwright_take_screenshot   — capture the page or one element',
      '  playwright_console_messages  — read console output collected so far',
      '  playwright_wait_for          — wait for text to appear, or for a duration',
      '  playwright_evaluate          — run JS in the page and return the result',
      '  playwright_close             — release this run browser early',
      '',
      'The prefix MATCHES the capability name deliberately (FR-013a): an agent granted',
      'tools: [playwright] sees tools that say playwright_. Do NOT rename them to browser_* —',
      'that is what Playwright MCP exposes and it was considered and rejected, because it',
      'leaves the grant word and the tool names out of step.',
      '',
      'THE CONTRACT — non-negotiable:',
      '  - EVERY tool returns ACTIONABLE TEXT and NEVER raises. An unavailable browser, a',
      '    navigation timeout, a stale ref, and a policy refusal are all things the agent can',
      '    respond to. An exception is not — it kills the step. This mirrors the pptx tool set',
      '    exactly, and for the same reason.',
      '  - playwright_navigate routes EVERY url through T3b policy resolver FIRST, before any',
      '    browser call.',
      '  - playwright_take_screenshot writes under ".browser/" via _SANDBOX.path_for, and RETURNS',
      '    the relative path it wrote so the agent can cite it in its own output.',
      '  - playwright_evaluate is included and is bounded by the same URL policy — under the',
      '    default policy the only reachable pages are files the run itself wrote.',
      '  - bind_sandbox(sandbox) sets the module-level _SANDBOX. It is called by the factory at',
      '    runner-composition time, never by the model. Say so in its docstring, as',
      '    pptx_tools.py does.',
      '',
      'The @tool docstrings are what the MODEL reads to decide when to call each tool. Write',
      'them as what the tool ANSWERS, not how it works.',
    ].join('\n'),
    ac: [
      'All nine tools exist, are decorated with @tool, and are importable from the module.',
      'Each tool returns a string on every error path — none of them raise. Verify by reading every except branch.',
      'playwright_navigate calls the T3b policy resolver before touching the browser.',
      'playwright_take_screenshot writes under .browser/ using _SANDBOX.path_for and returns the relative path.',
      'playwright_evaluate is present and documented as bounded by the URL policy.',
      'bind_sandbox sets the module-level _SANDBOX and its docstring says the factory calls it, not the model.',
      'With no sandbox bound, the path-writing tools return an actionable message rather than raising or writing outside the run.',
      'git diff --stat shows ONLY the new backend/app/agents/tools/playwright.py.',
    ],
  },

  T5: {
    kind: 'task', agentType: 'junior-engineer', phase: 'Binding',
    deps: ['T4'], files: [PROVIDER], file: PROVIDER + '  (new file)',
    traces: 'FR-001, FR-002, FR-003, FR-004',
    desc: [
      'Create the "playwright" tool_provider capability.',
      '',
      'COPY THE SHAPE of backend/agents/capabilities/tools/pptx.py exactly. Read it first.',
      '',
      'Requirements:',
      '  - @register("tool", "playwright", description=...) with user_allowed=False. A user- or',
      '    database-authored manifest must NOT be able to grant itself a browser by naming it',
      '    (CAP-03). Only a file manifest can.',
      '  - provide(spec, ctx) returns a tuple: (list of the nine string keys, False).',
      '  - Emit STRING KEYS, never tool objects. backend/agents/capabilities/ must not import',
      '    from app.* — an import-linter contract enforces it. The factory is the composition',
      '    root and resolves key to implementation.',
      '',
      'THE False IS LOAD-BEARING. Read this before you write it:',
      'That second tuple element is exclude_builtin, and _resolve_runner_tools ANDs it across',
      'every granted tool set. prototype-validate declares NO tools today, so it currently hits',
      'the "if not spec.tools and not custom_keys" short-circuit and returns ([], False) —',
      'meaning it keeps its native filesystem tools. The moment T9 grants it any tool set, it',
      'routes through the AND-accumulator instead. Returning True here would SILENTLY STRIP',
      'read_file from a validator agent whose entire job is reading files. Put this explanation',
      'in the class docstring so the next person to touch it does not "simplify" it to True.',
    ].join('\n'),
    ac: [
      'CapabilityRegistry().resolve("tool", "playwright") returns the provider.',
      'provide() returns exactly the nine tool keys T4 defined, as strings.',
      'provide() returns False as its second element.',
      'The provider is registered with user_allowed=False.',
      'The module contains no import from app.* — grep it to confirm.',
      'The class docstring explains why the False matters, naming prototype-validate.',
      'git diff --stat shows ONLY the new backend/agents/capabilities/tools/playwright.py.',
    ],
  },

  T6: {
    kind: 'task', agentType: 'junior-engineer', phase: 'Binding',
    deps: ['T5'], files: [FACTORY], file: FACTORY, traces: 'FR-001',
    desc: [
      'Wire the nine playwright keys into the factory key-to-implementation resolver.',
      '',
      'This is a COPY of the pptx branch. Read backend/agents/factory.py lines 997-1085 first.',
      '',
      '1. Add _PLAYWRIGHT_TOOL_KEYS as a frozenset next to _PPTX_TOOL_KEYS (around line 997),',
      '   listing the nine key names.',
      '2. Add ONE elif branch in _resolve_custom_tool_keys, immediately after the pptx branch',
      '   (around line 1066), mirroring it exactly:',
      '     - if sandbox is None: log a warning and continue (resolve to NOTHING rather than',
      '       raising) — an unbound tool would write outside the run. Keep the same warning',
      '       style as the pptx branch.',
      '     - otherwise: lazily import app.agents.tools.playwright, call bind_sandbox(sandbox),',
      '       getattr the concrete tool by key, and append if not already present.',
      '3. Update the _resolve_custom_tool_keys docstring — it enumerates which keys resolve to',
      '   what. Add the playwright line in the same style.',
      '',
      'Do NOT touch _resolve_runner_tools. Do NOT touch any other branch. Do NOT reorder the',
      'existing branches. Every pre-existing key must resolve byte-identically — the',
      'characterization snapshots gate this.',
    ].join('\n'),
    ac: [
      'The nine keys resolve to the nine tool objects when a sandbox is passed.',
      'The nine keys resolve to nothing (with a logged warning, NOT an exception) when sandbox is None.',
      'The pptx, planning, report_task_complete, web_search, web_fetch and spawn_subagents branches are untouched and still resolve byte-identically.',
      'An unknown key still raises ValueError as before.',
      'The docstring key list includes the playwright entry.',
      'pytest backend/tests/agents/test_create_runner.py -q passes.',
      'git diff --stat shows ONLY backend/agents/factory.py changed.',
    ],
  },

  T7: {
    kind: 'task', agentType: 'senior-engineer', phase: 'Session',
    deps: ['T3a'], files: [ENGINE], file: ENGINE, traces: 'FR-009',
    desc: [
      'Add the run-teardown hook that releases the browser session on EVERY exit path.',
      '',
      'THE FINDING THIS TASK IS BUILT ON:',
      'ExecutionEngine.execute() (line 1076) is an async generator. Its outer try: at line 2676',
      'carries exactly three handlers — asyncio.CancelledError (3421), BudgetExceeded (3447),',
      'and FanoutWorkerFailed (3465) — and NO finally:. Each handler returns or raises on its',
      'own path, so today there is no single point that every exit crosses. Verify this yourself',
      'before editing; if the structure has changed since, report it in blockers rather than',
      'guessing where to put the block.',
      '',
      'Add ONE finally: to that try which calls the T3a session release for this run id.',
      '',
      'Why a finally and not the handlers: a finally on an async generator also fires on',
      'GeneratorExit, which is the WebSocket-disconnect path — the consumer stops iterating and',
      'no handler runs at all. Covering the three excepts individually would miss it, and that',
      'is precisely the abandoned-run case that leaks a browser.',
      '',
      'Constraints:',
      '  - It MUST be a no-op for runs that never launched a browser. That is nearly every run.',
      '  - It MUST NOT raise. A release that throws inside a finally would MASK the exception',
      '    passing through it. On the cancel path that is load-bearing: read the ISS-023 comment',
      '    at lines 3429-3444 — a genuine task.cancel() must keep propagating so the disconnect',
      '    cleanup runs. Wrap defensively.',
      '  - Touch NOTHING else. Do not reorder handlers. Do not alter the cancel-path',
      '    return-versus-raise logic. Do not refactor anything nearby.',
      '  - Comment the block: why it exists, and why this is the only reliable point.',
      '',
      'This is a six-line addition to a 10,000-line file. Resist every temptation to tidy.',
    ].join('\n'),
    ac: [
      'A finally: block is attached to the outer try at engine.py:2676 and calls the session release.',
      'The release is called on normal completion of the generator.',
      'The release is called on each of the three handled abort paths (CancelledError, BudgetExceeded, FanoutWorkerFailed).',
      'The release is called on GeneratorExit when the consumer stops iterating.',
      'The release cannot raise out of the finally — it is wrapped defensively.',
      'The cancel path propagate-versus-return behaviour described in the ISS-023 comment is unchanged.',
      'A run that never launched a browser is completely unaffected — the release is a no-op.',
      'No other line in engine.py changed. Confirm with git diff.',
      'pytest backend/tests/agents/test_engine_cancel.py -q passes.',
    ],
  },

  T8: {
    kind: 'task', agentType: 'junior-engineer', phase: 'Binding',
    deps: ['T6'], files: [AGENT_DECKQA], file: AGENT_DECKQA, traces: 'FR-020',
    desc: [
      'Grant the playwright tool set to the ppt_v2 deck QA agent.',
      '',
      '1. In the YAML frontmatter, change:',
      '       tools:',
      '       - workspace',
      '   to:',
      '       tools:',
      '       - workspace',
      '       - playwright',
      '   Keep workspace. It is still needed.',
      '',
      '2. Add a SHORT section to the prompt body telling the agent it can now SEE the deck:',
      '   it can open presentation.html in a browser, screenshot the slides, and check for',
      '   overlapping or clipped text — the class of defect that is invisible in markup and',
      '   obvious on screen. Spec 017 records a deck shipping with exactly that defect: a',
      '   headline printing through its own body copy, which passed a source-text review.',
      '',
      'Keep it terse. Do NOT restructure the existing prompt, do not reorder its sections, do',
      'not rewrite its voice. This agent prompt is tuned; you are adding a capability note to',
      'it, not editing it.',
    ].join('\n'),
    ac: [
      'The frontmatter parses as valid YAML.',
      'tools contains BOTH workspace and playwright.',
      'The prompt body mentions the browser capability in exactly one place.',
      'The pre-existing prompt text is otherwise unchanged — verify with git diff that only the frontmatter line and the new section were added.',
      'git diff --stat shows ONLY backend/agents/prompts/ppt-deck-qa-v2/AGENT.md changed.',
    ],
  },

  T9: {
    kind: 'task', agentType: 'junior-engineer', phase: 'Binding',
    deps: ['T6'], files: [AGENT_PROTOVAL], file: AGENT_PROTOVAL, traces: 'FR-020, FR-003',
    desc: [
      'Grant the playwright tool set to the prototype validation agent.',
      '',
      'This agent has NO tools: key in its frontmatter today. Add one:',
      '    tools:',
      '    - playwright',
      '',
      'THIS IS THE FR-003 TRAP — read before you edit:',
      'With no tool set declared, _resolve_runner_tools short-circuits at',
      '"if not spec.tools and not custom_keys" and returns ([], False), which means this agent',
      'KEEPS its native filesystem tools. The moment you add any tool set, spec.tools becomes',
      'non-empty and it routes through the exclude AND-accumulator instead. T5 provider returns',
      'False, which is what preserves read_file and write_file here.',
      '',
      'DO NOT ASSUME IT WORKED. Verify that this agent still binds read_file and write_file',
      'after your change, by running the named test and reading its bound tool set. If they',
      'disappeared, that is a T5 defect — report it in blockers, do not work around it here.',
      '',
      'Also add a short body section: it can now open the prototype and SEE what the validator',
      'is judging, rather than only reading a verdict it cannot interrogate. Keep it terse and',
      'do not restructure the existing prompt.',
    ].join('\n'),
    ac: [
      'The frontmatter parses as valid YAML and declares tools: [playwright].',
      'THE AGENT STILL BINDS read_file AND write_file after the change — verified by inspecting the actual bound tool set, not by assuming.',
      'The prompt body mentions the browser capability in exactly one place.',
      'The pre-existing prompt text is otherwise unchanged.',
      'pytest backend/tests/agents/test_create_runner.py -q passes.',
      'git diff --stat shows ONLY backend/agents/prompts/prototype-validate/AGENT.md changed.',
    ],
  },

  T10: {
    kind: 'task', agentType: 'junior-engineer', phase: 'Binding',
    deps: ['T4'], files: [TEST_TOOLS], file: TEST_TOOLS + '  (new file)',
    desc: [
      'Write the tool-level tests for the nine playwright_* tools.',
      '',
      'Follow the conventions of backend/tests/agents/test_pptx_tools.py — read it first for',
      'how this project fakes a sandbox and asserts on tool return text.',
      '',
      'Cover at minimum:',
      '  1. Every tool returns TEXT rather than raising on its error path. Drive each one into',
      '     its failure mode and assert a string comes back.',
      '  2. A policy refusal names the active policy (BROWSER_URL_POLICY and its value).',
      '  3. playwright_take_screenshot writes under .browser/ and the written path is NOT a',
      '     deliverable — assert via is_deliverable_relpath, so this test also guards T1.',
      '  4. A traversal-shaped screenshot filename (e.g. ../../escape.png) is rejected.',
      '  5. With Chromium unavailable, EVERY tool reports unavailable and NONE reports success.',
      '     This is the FIX-307 regression class — a tool that silently returns a clean result',
      '     with no browser is the exact defect spec 018 FR-018 forbids.',
      '  6. With no sandbox bound, the path-writing tools refuse rather than writing anywhere.',
      '',
      'Tests must not require a real Chromium to pass — fake or skip the browser-dependent',
      'paths, but do NOT skip the availability-degradation tests, which are the important ones.',
    ].join('\n'),
    ac: [
      'pytest backend/tests/agents/test_playwright_tools.py -q passes on its own.',
      'The file covers all six areas listed in the description.',
      'The tests pass without a real Chromium installed.',
      'The unavailable-browser test asserts that no tool reports success.',
      'git diff --stat shows ONLY the new test file.',
    ],
  },

  T11: {
    kind: 'task', agentType: 'junior-engineer', phase: 'Session',
    deps: ['T3a', 'T7'], files: [TEST_SESSION], file: TEST_SESSION + '  (new file)',
    desc: [
      'Write the session and lifecycle tests.',
      '',
      'Cover at minimum:',
      '  1. THE FIX-307 REGRESSION GUARD: a page acquired in one call is still usable in a',
      '     SECOND, separate call. This is the single most important test in spec 018 — it is',
      '     the test whose absence let FIX-307 live for weeks. Make it unmistakable: name it',
      '     for what it guards and comment it with the card id.',
      '  2. release() is called on every engine exit path: normal completion, CancelledError,',
      '     BudgetExceeded, FanoutWorkerFailed, and GeneratorExit.',
      '  3. release() on an unknown run id is a no-op and raises nothing.',
      '  4. release() is idempotent.',
      '  5. release() cannot raise out of the finally, so it cannot mask a propagating exception.',
      '  6. Two agent ids within one run get isolated BrowserContexts.',
      '  7. The URL policy resolver permit/refuse table from T3b: file path, localhost, external',
      '     https under default policy, traversal path, and the same external https AFTER',
      '     widening the policy string.',
      '  8. Snapshot refs resolve, and go stale after navigation rather than resolving to the',
      '     wrong element.',
      '',
      'Tests must pass without a real Chromium. Fake the browser where needed; the lifecycle',
      'and policy logic are what is under test, not Chromium itself.',
    ].join('\n'),
    ac: [
      'pytest backend/tests/agents/test_playwright_session.py -q passes on its own.',
      'A named test asserts a page survives across two separate acquisitions, commented with FIX-307.',
      'Tests cover all five engine exit paths including GeneratorExit.',
      'Tests cover the full policy permit/refuse table including the widened-policy case.',
      'Tests cover ref staleness after navigation.',
      'The tests pass without a real Chromium installed.',
      'git diff --stat shows ONLY the new test file.',
    ],
  },

  V2: {
    kind: 'validator', agentType: 'qa-engineer', phase: 'Session',
    deps: ['T3a', 'T3b', 'T3c', 'T7', 'T11'],
    guards: ['T3a', 'T3b', 'T3c', 'T7', 'T11'],
    context: 'HARD GATE. Nothing downstream ships on a FAIL. This gate exists because FIX-307 — a browser-lifecycle defect in this same codebase — swallowed its own error and made a validator report CLEAN on every run for weeks. Treat "it looks fine" as a FAIL. Every criterion below must be checked by inspection or by running something, never by trusting a task report.',
    criteria: [
      'The string "async with async_playwright" appears NOWHERE in backend/app/agents/playwright_session.py. Grep for it and paste the result as evidence.',
      'The session holds the Playwright handle explicitly (async_playwright().start()) and stops it in release().',
      'A page acquired in one call is still usable in a second, separate call — the FIX-307 regression. Verify the test exists in test_playwright_session.py AND that it genuinely exercises two separate acquisitions rather than one.',
      'release() is invoked on all five exit paths: normal completion, CancelledError, BudgetExceeded, FanoutWorkerFailed, and GeneratorExit. Read the engine finally block and confirm it is positioned to catch all of them.',
      'release() on an unknown run id is a no-op and raises nothing; release() is idempotent.',
      'The release cannot raise out of the engine finally — confirm it is wrapped so it cannot mask a propagating exception, and that the ISS-023 cancel-path behaviour at engine.py:3429-3444 is unchanged.',
      'With Chromium unavailable, the session reports UNAVAILABLE and no code path reports a clean or successful result. This is the FIX-307 failure mode; verify it explicitly.',
      'Two different agent ids within one run receive two different BrowserContext objects.',
      'The URL policy resolver refuses out-of-policy URLs BEFORE any network or filesystem access, and its refusal text names BROWSER_URL_POLICY and its value.',
      'Snapshot refs go stale after navigation rather than resolving to a different element.',
      'pytest backend/tests/agents/test_playwright_session.py -q passes.',
      'pytest backend/tests/agents/test_engine_cancel.py -q passes.',
      'engine.py changed by ONLY the finally block — no reordering, no other edits. Confirm with git diff on that file.',
    ],
  },

  V3: {
    kind: 'validator', agentType: 'qa-engineer', phase: 'Binding',
    deps: ['T6', 'T8', 'T9', 'T10'],
    guards: ['T4', 'T5', 'T6', 'T8', 'T9', 'T10'],
    context: 'The single highest-risk item here is SC-003: prototype-validate had NO tools: key before T9, so it kept its native filesystem tools via a short-circuit in _resolve_runner_tools. Adding any tool set routes it through an AND-accumulator that can silently strip read_file. Check the ACTUAL bound tool set for that agent — not the provider return value, and not the task report.',
    criteria: [
      'The nine playwright_* tools bind for ppt-deck-qa-v2.',
      'The nine playwright_* tools bind for prototype-validate.',
      'SC-003: prototype-validate STILL binds read_file and write_file after being granted the tool set. Inspect the actual resolved tool list, not the provider return value.',
      'SC-002: every OTHER agent binds a tool set byte-identical to before this feature. The characterization snapshots are the oracle — run pytest backend/tests/agents/test_create_runner.py -q and report the result.',
      'SC-008: a user- or DB-authored manifest naming "playwright" does not receive the tools — the capability is registered user_allowed=False. Verify the registration, do not infer it.',
      'backend/agents/capabilities/tools/playwright.py contains no import from app.* — grep and paste evidence.',
      'SC-004: a path under .browser/ is excluded from the deliverable while an ordinary artifact path is not.',
      'Every playwright_* tool returns text on its error paths and none of them raise. Read the except branches in tools/playwright.py.',
      'pytest backend/tests/agents/test_playwright_tools.py -q passes.',
      'pytest backend/tests/agents/test_sandbox_deliverable.py -q passes.',
      'The two AGENT.md edits added only a tools entry and one short body section each — their existing prompt text is otherwise unchanged.',
    ],
  },

  V4: {
    kind: 'validator', agentType: 'qa-engineer', phase: 'Acceptance',
    deps: ['V3'],
    guards: ['T1', 'T3a', 'T4', 'T5', 'T6', 'T7', 'T8', 'T9'],
    context: 'Final acceptance against spec.md success criteria. Live end-to-end validation is the USER job, not yours — do not attempt to launch a real workflow run. Judge what is statically and test-verifiable, and say explicitly in evidence which criteria are inferred from code rather than observed live.',
    criteria: [
      'SC-001: trace the full path — an AGENT.md tools: [playwright] entry reaches the registered provider, whose string keys reach the factory branch, which binds sandbox-bound tools. Confirm no workflow-name or agent-name literal appears anywhere in that path (SC-001 / INV-1).',
      'SC-005: no browser can survive a run, by any exit path — the engine finally plus playwright_close plus the idle timer give three independent reclaim paths. Verify all three exist.',
      'SC-006: an out-of-policy URL is refused, and widening BROWSER_URL_POLICY permits it with NO code change.',
      'SC-007: with Chromium absent, no step crashes and nothing reports a false clean.',
      'SC-009: backend/app/agents/render_check.py is completely UNTOUCHED. Run git diff --stat and confirm the file does not appear. Then run pytest backend/tests/agents/test_nav_coverage.py -q and confirm it passes.',
      'backend/agents/capabilities/gates/validation.py and backend/agents/capabilities/strategies/task_loop.py are also untouched.',
      'No database migration was added. No file under backend/agents/workflows/ changed. No frontend file changed.',
      'The complete changed-file set matches plan.md exactly: 3 new source files, 2 new test files, 4 modified source files, 2 AGENT.md grants. Any extra file is a scope violation — name it.',
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
    const report = await safeAgent(taskPrompt(id), {
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
await safeAgent(
  [
    'You are recording results into a task ledger. You do NOT write code and you do NOT judge work.',
    '',
    'File: specs/018-agent-browser-tools/tasks.md',
    '',
    'It contains a "## Ledger" markdown table with a status column of empty checkboxes, a',
    '"**Status**:" line near the top, and a "## Task graph" mermaid diagram.',
    '',
    'Update ONLY status representations:',
    '  - Ledger status cells: set to a checked box for done ids, and to BLOCKED for errored ids.',
    '  - The evidence column: one short phrase per completed row (e.g. the test that passed).',
    '  - The "**Status**:" line: the done/total task and checkpoint counts.',
    '',
    'DONE ids: ' + (done.join(', ') || '(none)'),
    'BLOCKED ids: ' + (errored.join(', ') || '(none)'),
    '',
    'Do NOT touch any task description, acceptance criterion, prose section, or the mermaid',
    'graph edges. Do NOT edit any file other than tasks.md. Do NOT run any git command.',
    '',
    'Return taskId="LEDGER", status="done", filesChanged, a 2-sentence summary, and an',
    'acSelfCheck confirming you changed only status representations.',
  ].join('\n'),
  { label: 'ledger-sync', phase: 'Acceptance', agentType: 'junior-engineer', schema: TASK_RESULT_SCHEMA },
)

return {
  done, errored, results,
  summary: `${done.length}/${Object.keys(NODES).length} nodes done. ` +
    (errored.length ? `Blocked at: ${errored.join(', ')}.` : 'All nodes passed.'),
}
