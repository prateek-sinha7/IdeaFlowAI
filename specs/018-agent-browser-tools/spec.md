# Feature Specification: A Playwright tool set agents can be granted

**Spec ID**: 018-agent-browser-tools
**Created**: 2026-08-27
**Status**: **Done** — 13/13 tasks · 4/4 checkpoints, executed via [workflow.js](workflow.js) (17 nodes) on 2026-08-27. 222 tests green across 6 files (`test_playwright_session.py` 39, `test_playwright_tools.py` 29, `test_engine_cancel.py` 6, `test_create_runner.py` 22, `test_sandbox_deliverable.py` + `test_registry_capabilities.py` 117), independently re-run standalone outside the workflow. `render_check.py`, `gates/validation.py` and `strategies/task_loop.py` confirmed untouched (empty diff). Two deviations from plan.md, both recorded in [tasks.md](tasks.md): T4's first pass used a fresh event loop per tool call, which would have stranded every earlier `page`/`context` the moment a call returned — defeating FR-007's persistent-session guarantee — and was replaced with a single dedicated background event-loop thread every tool call runs on; and the change touched three files plan.md didn't list (`capabilities/tools/__init__.py`'s registration import, plus `test_engine_cancel.py` as a new file), all legitimate and none in violation of the Change Budget's intent. Not yet committed — the working tree is left for the user to review.
**Root**: `backend/app/agents/playwright_session.py`, `backend/app/agents/tools/playwright.py`, `backend/agents/capabilities/tools/playwright.py`, `backend/agents/capabilities/tools/__init__.py`, `backend/agents/factory.py`, `backend/agents/execution_engine/engine.py`, `backend/app/agents/sandbox.py`, `backend/app/core/config.py`, `backend/agents/prompts/ppt-deck-qa-v2/AGENT.md`, `backend/agents/prompts/prototype-validate/AGENT.md`
**Grounding**: `app/agents/render_check.py` (the existing headless harness), spec 017 / [FIX-321](../../.knowledge/cards/20260827-0054-FIX-321.md) (the per-run sandbox-bound tool-set precedent), [FIX-307](../../.knowledge/cards/20260826-0124-FIX-307.md) (the browser-lifecycle defect this design must not reproduce), ADR-0031 (the workspace spine screenshots land on).

---

## Clarifications

### Session 2026-08-27

- Q: What URLs may `playwright_navigate` open? → A: **`file://` plus localhost, and the policy must be
  configurable.** `file://` covers the stated case (an agent opens an HTML file it just wrote);
  localhost covers an agent driving a dev server. Open `http(s)` is the same trust surface as
  `web_fetch` — model-driven outbound egress from a container holding database credentials — so it
  is not the default, but the allowlist is a setting rather than a constant so it can be widened
  per deployment without a code change.
- Q: Include `playwright_evaluate` (arbitrary JS in the page)? → A: **Yes.** Reading computed styles,
  measuring real geometry and poking app state are the things that make a browser worth having
  rather than a screenshot service, and the alternative is agents inventing worse workarounds. It
  is arbitrary execution against whatever the run loaded, which the URL policy is what bounds.
- Q: Which agents get the grant in this build? → A: **`ppt-deck-qa-v2` and the prototype validator
  agent (`prototype-validate`).** The deck QA step is the only writer of `presentation.html` and
  currently judges a deck it has never rendered; `prototype-validate` sits where `render_check`
  already runs engine-side, so it can inspect what it is being asked to sign off rather than only
  reading the verdict.

---

## 1. Problem

The platform already runs headless Chromium. `app/agents/render_check.py` loads a prototype,
drives its navigation, and collects console and page errors, and the browser plus its OS libraries
are baked into the backend image (`Dockerfile`, `PLAYWRIGHT_BROWSERS_PATH=/opt/playwright`, ~350 MB
already paid for).

No agent can reach any of it. `render_check` is reached only from engine-side callers — the
`validation` gate (`agents/capabilities/gates/validation.py`) and the `task_loop` strategy, which
inject it as a callable. From an agent's side it does not exist. The consequence is that agents
whose entire job is judging a rendered artifact never see it rendered:

- `ppt-deck-qa-v2` is the only writer of `presentation.html` and reviews it as **source text**. A
  headline printing through its own body copy is invisible in the markup and obvious on screen.
  This is not hypothetical — spec 017 records a deck that shipped with exactly that defect.
- `prototype-validate` receives a verdict from a validator it cannot interrogate. When the verdict
  and the agent's reading of the source disagree, the agent has no way to look.

Meanwhile the shape for granting a sandbox-bound tool set already exists and shipped yesterday: the
`pptx` set (spec 017) binds four tools per run through `RunSandbox`, is declared by one line of
agent frontmatter, and required no engine change. What is missing is a browser equivalent.

## 2. What it does

Adds a `playwright` tool set — a registered `tool_provider` capability — that an agent opts into
with one line of its `AGENT.md`:

```yaml
tools:
  - playwright
```

Because an agent already declares its own `pipeline_type`, that single line is what "selected
agents in selected workflows" means. No engine edit, no workflow-name check, no new manifest key.

Granted the set, an agent can open a file it wrote, read the page's structure, interact with it,
and capture what it saw — with every path resolved inside the run sandbox and every screenshot
written where the run's own workspace browser shows it.

`render_check.py` is not modified, refactored, or shared with. It is a self-contained macro with
its own lifecycle that works; entangling it with a long-lived session is how [FIX-307](../../.knowledge/cards/20260826-0124-FIX-307.md) happened.

## 3. User Scenarios & Testing *(mandatory)*

### Primary user story

A deck QA agent has just landed `presentation.html` in the workspace. Instead of re-reading its own
markup, it opens the file in a headless browser, reads back the page structure, screenshots the
slides, sees that slide 7's title overlaps its body text, fixes the CSS, re-opens the file, and
confirms the overlap is gone — all inside the step, with the screenshots left in the workspace as
evidence a human can check afterwards.

### Acceptance scenarios

1. **Given** an agent declaring `tools: [playwright]`, **when** its step runs, **then** the browser
   tools appear in its bound tool set and its native filesystem tools are still present.
2. **Given** an agent NOT declaring `tools: [playwright]`, **when** its step runs, **then** no browser
   tool is bound and its tool set is byte-identical to before this feature.
3. **Given** a granted agent, **when** it navigates to a file it wrote and requests a page
   structure readback, **then** it receives a structured list of interactive elements each carrying
   a stable reference it can act on.
4. **Given** a page readback, **when** the agent acts on one of those references, **then** the
   action targets that element — no coordinates, no vision, no guessing.
5. **Given** a granted agent, **when** it captures a screenshot, **then** the image is written
   inside the run sandbox, is visible in the run's workspace, and does **not** appear in the run's
   deliverable.
6. **Given** a granted agent, **when** it navigates to a URL outside the configured policy, **then**
   the tool returns an actionable refusal and no request leaves the process.
7. **Given** a run that used the browser, **when** the run ends by ANY path — success, failure, or
   cancellation — **then** no browser process survives it.
8. **Given** a user- or database-authored workflow manifest, **when** it names the `playwright` tool
   set, **then** the grant is refused.
9. **Given** a granted agent making several tool calls in sequence, **when** it navigates and then
   interacts, **then** the second call acts on the page the first one loaded.

### Edge cases

- Chromium missing or failing to launch (a dev machine without `playwright install`): every tool
  returns actionable text saying the browser is unavailable. The step continues; it does not crash
  and does not silently report success.
- A page that never reaches a settled load state: the navigation times out and says so, rather than
  hanging the step until the run's own timeout.
- An agent that never closes the browser: an idle timeout reclaims it, and run teardown reclaims it
  unconditionally regardless.
- Two agents in the same run using the browser concurrently (a parallel group): neither sees the
  other's pages, cookies, or storage.
- An agent acting on a stale element reference after re-navigating: the tool says the reference is
  stale and that a fresh readback is needed — it does not act on the wrong element.
- A screenshot filename that tries to escape the sandbox: rejected by the existing traversal guard.

## 4. Requirements *(mandatory)*

### Functional Requirements

- **FR-001** — The tool set MUST be a registered `tool_provider` capability named `playwright`,
  granted solely by an agent's `tools:` frontmatter. No engine edit, and no workflow- or
  agent-name literal anywhere in the resolution path (SC-001).
- **FR-002** — The capability provider MUST emit tool KEYS as strings, never tool objects, so
  `agents.capabilities` stays import-clean of `app.*` (import-linter contract). The factory, which
  is the composition root, resolves key → implementation.
- **FR-003** — The provider MUST report that it needs the native filesystem surface
  (`exclude_builtin=False`). Granting `playwright` to an agent that previously declared no tool set
  MUST NOT remove that agent's filesystem tools. (`prototype-validate` declares no `tools:` today
  and reaches `([], False)`; a set returning `True` would silently strip its `read_file`.)
- **FR-004** — The capability MUST be registered `user_allowed=False`. A user- or DB-authored
  manifest MUST NOT be able to grant itself a browser by naming it (CAP-03). Only a file manifest
  can.
- **FR-005** — Every filesystem path a browser tool reads or writes MUST resolve through
  `RunSandbox.path_for`, which rejects traversal.
- **FR-006** — Screenshots and any other browser output MUST be written under a RESERVED sandbox
  prefix that is excluded from the deliverable walk, alongside the existing `.uploads/`, `.logs/`
  and `.verify/` prefixes. They MUST remain visible in the run workspace — evidence a human cannot
  inspect is evidence that has to be taken on trust.
- **FR-007** — A browser session MUST persist across tool calls within a step, so that navigate →
  interact → capture operate on one page. A tool set where each call is independent cannot satisfy
  the primary user story.
- **FR-008** — The session MUST NOT be managed by an `async with async_playwright()` block. It MUST
  hold the Playwright handle explicitly and release it explicitly. (FIX-307: leaving that block
  tears down the browser, the next page acquisition raises "Target page, context or browser has
  been closed", and the error was swallowed — the validator reported clean on every run for weeks.)
- **FR-009** — The session MUST be released on every run exit path — success, failure, and
  cancellation. A leaked browser per abandoned run is a memory leak with a ~100–200 MB unit.
- **FR-010** — One browser per run; one isolated browsing context per agent. Contexts are cheap and
  give per-agent cookie/storage isolation; a browser per agent multiplies the footprint by the
  fan-out width.
- **FR-011** — The session MUST be created lazily, on the first browser tool call. An agent granted
  the set but never using it MUST NOT cost a browser launch.
- **FR-012** — The tool set MUST expose a page-structure readback that returns interactive elements
  with STABLE REFERENCES the interaction tools accept. Agents MUST NOT be asked to act on pixel
  coordinates.
- **FR-013** — The tool set MUST expose, at minimum: navigate, structure readback, click, type,
  screenshot, console-message readback, wait, evaluate, and close.
- **FR-013a** — The agent-facing tool NAMES MUST carry the `playwright_*` prefix
  (`playwright_navigate`, `playwright_snapshot`, `playwright_click`, …), matching the
  capability name. One word names the whole surface: an agent granted `tools: [playwright]`
  sees tools that say `playwright_`, and a reader grepping for either finds both. The
  alternative considered and rejected was `browser_*`, which is what Playwright MCP exposes;
  it buys familiarity at the cost of a set whose grant word and tool names do not match.
- **FR-014** — `playwright_evaluate` MUST be included, and MUST be bounded by the same URL policy that
  bounds navigation — the policy is what limits what a page can be, and therefore what evaluated
  code can reach.
- **FR-015** — Navigable URLs MUST be governed by a CONFIGURABLE policy whose default is `file://`
  (resolved through the sandbox) plus localhost. Widening it MUST be a setting change, not a code
  change.
- **FR-016** — A URL outside the policy MUST be refused before any network or filesystem access
  occurs, and the refusal MUST name the policy so the agent can act on it.
- **FR-017** — Every tool MUST return ACTIONABLE TEXT and MUST NOT raise. An unavailable browser, a
  navigation timeout, a stale reference and a policy refusal are all things the agent can respond
  to; an exception is not. (Mirrors the pptx tool-set contract.)
- **FR-018** — An unavailable or un-launchable browser MUST be reported as unavailable, never as a
  clean result. Silent success is the FIX-307 failure mode and MUST NOT be reproduced.
- **FR-019** — `app/agents/render_check.py` MUST NOT be modified, and its behaviour MUST be
  unchanged.
- **FR-020** — `ppt-deck-qa-v2` and `prototype-validate` MUST be granted the set in this build. No
  other agent's bound tool set may change.

### Key Entities

- **Browser session** — the per-run lifecycle owner. Holds the Playwright handle, the browser, the
  per-agent contexts, and the reference registry. Created lazily, released deterministically. The
  one piece of genuinely new machinery in this feature.
- **Element reference** — the stable handle a structure readback hands out and the interaction
  tools consume. What makes the tool set usable without vision, and what must go stale loudly
  rather than silently after a re-navigation.
- **URL policy** — the configurable allowlist governing what may be opened. The single security
  boundary of this feature; everything else is containment of files already inside the sandbox.
- **Reserved output prefix** — where browser artifacts land: inside the workspace, outside the
  deliverable.

## 5. Out of scope

- Replacing or refactoring `render_check.py`, and sharing a session with it.
- Exposing the browser through MCP. The requirement is that screenshots live in the RUN sandbox,
  and an MCP server's output directory is server-scoped, not run-scoped — satisfying it would mean
  one server process per concurrent run, on top of the Chromium already in the image. The user's
  own Playwright MCP configuration is a separate concern that this feature does not touch.
- Video recording, tracing, and HAR capture.
- Visual diffing or screenshot comparison. Capture is in scope; judging two images is not.
- A frontend surface for browsing the captured screenshots beyond what the existing workspace
  already renders.
- Granting the set to any agent beyond the two named in FR-020.
- Enabling local exec. Localhost navigation is permitted by policy, but nothing here starts a
  server; an agent that wants one still needs a capability this feature does not provide.

## 6. Success Criteria *(mandatory)*

- **SC-001** — A granted agent can open an HTML file from its workspace, read the page structure,
  interact with an element by reference, and capture a screenshot, in one step, with no engine
  change.
- **SC-002** — Every agent not named in FR-020 binds a tool set byte-identical to before this
  feature. Verified by the existing characterization snapshots.
- **SC-003** — `prototype-validate` retains its filesystem tools after being granted the set.
- **SC-004** — Screenshots taken during a run appear in that run's workspace and do NOT appear in
  its deliverable.
- **SC-005** — After a run that used the browser ends — by success, failure, or cancellation — no
  browser process attributable to it remains.
- **SC-006** — A navigation to a URL outside the configured policy is refused, and widening the
  policy to permit it requires no code change.
- **SC-007** — With Chromium absent, every browser tool returns an availability message and no step
  crashes or reports a false clean.
- **SC-008** — A DB- or user-authored manifest naming `playwright` does not receive the tools.
- **SC-009** — `render_check`'s own test suite passes unchanged.

## 7. Risks

| risk | containment |
|---|---|
| A leaked browser per abandoned run exhausts memory | Release on every exit path (FR-009), plus an idle timeout and an explicit close tool. Three independent reclaim paths because the failure is slow and silent. |
| The session is built with `async with` and reproduces FIX-307 | FR-008 states the constraint; a test asserting a page is still usable across two tool calls fails loudly if it regresses. |
| Screenshots leak into user deliverables | Reserved prefix (FR-006), which reuses the exclusion mechanism `.verify/` already proved. |
| `playwright_evaluate` becomes an arbitrary-execution hole | Bounded by the URL policy — with the default policy the only reachable pages are files the run itself wrote. Widening the policy widens this too, which is a deliberate deployment decision. |
| Adding a tool set to `prototype-validate` silently strips its filesystem tools | FR-003 + SC-003. This is a real trap in `_resolve_runner_tools`' AND-accumulator, not a theoretical one. |
| Agents flail against a page they cannot see | The structure readback (FR-012) is what prevents this; screenshots are evidence for humans, not a navigation aid for the model. |
| Concurrent agents in a parallel group interfere | One context per agent (FR-010). |

## Assumptions

- Chromium and its OS libraries are present wherever the backend runs. True in the prod image; on a
  dev machine it needs `playwright install chromium`, and its absence degrades to unavailable
  rather than failing (FR-018).
- `--no-sandbox` remains required for Chromium inside the container, as `render_check` already
  does. This disables CHROMIUM's process sandbox and has no bearing on `RunSandbox` isolation —
  the two are unrelated mechanisms that share a word.
- The run sandbox is local disk co-located with the backend process, so an in-process browser can
  open its files directly. If `RuntimeEnvironment` later swaps to a remote runtime, the session
  must move with the sandbox — cheap to accommodate now by keeping the session behind the port,
  expensive to retrofit.
- `app/agents/tools/playwright.py` does not shadow the installed `playwright` package. Python 3
  imports are absolute and this is a package module (`app.agents.tools.playwright`), so
  `from playwright.async_api import ...` inside it resolves to site-packages. The name is safe; it
  is called out because it reliably looks like a defect during review.
- Deck and prototype pages are self-contained local HTML. A page depending on remote assets will
  render degraded under the default URL policy, which is the correct behaviour for those artifacts.
