# Spec 018 — a Playwright tool set agents can be granted

## Goal

Give a named agent a real browser inside its own run sandbox: open a page, read its
structure, interact with it, capture what it saw. Granted by one line of `AGENT.md`
frontmatter, bound per run, contained by the sandbox, released deterministically.

Chromium is already in the image. The tool-binding pattern already shipped (spec 017).
What is missing is a session that outlives a single tool call, and the policy that bounds it.

## The one decision that shapes everything

**The session is persistent, and that is the only reason this feature is not trivial.**

`render_check.py` is a MACRO — launch, do everything, tear down, all inside one
`async with async_playwright()`. That shape is why it is robust, and it is exactly the
shape that cannot serve `navigate → click → screenshot` across three tool calls.

So this feature owns a lifecycle, and lifecycles are where this codebase has already been
burned. [FIX-307](../../.knowledge/cards/20260826-0124-FIX-307.md): browser work drifted
outside the `async with`, every `new_page()` raised *"Target page, context or browser has
been closed"*, the error was swallowed into `page_errors`, and the render validator
reported **clean on every run**. Silent, not loud.

Three consequences, all non-negotiable:

1. `async with` is banned for the session. `await async_playwright().start()` … `await pw.stop()`.
2. Release is wired into a `finally`, not into the happy path.
3. "Browser unavailable" is never reported as a clean result (FR-018). That is the FIX-307
   failure mode restated as a requirement.

```
first browser tool call
      │
      ▼
PlaywrightSession.acquire(run_id)      ── lazy: no call, no launch
      │
      ├─ pw = await async_playwright().start()      (held, not scoped)
      ├─ browser = await pw.chromium.launch(args=["--no-sandbox"])
      └─ context per agent  ──►  page  ──►  ref registry
      │
      ▼
tools act on the live page across calls
      │
      ▼
release: engine finally ── OR ── playwright_close ── OR ── idle timeout
```

Three reclaim paths, deliberately. The failure they guard is slow and silent, and a leak
costs ~100-200 MB per abandoned run.

## Where the teardown hook goes (the spec's one open item, now closed)

The spec left FR-009 unresolved: no run-teardown hook had been located. There isn't one.

`ExecutionEngine.execute()` (`engine.py:1076`) is an async generator whose outer `try:` at
`engine.py:2676` carries exactly three handlers — `CancelledError` (3421), `BudgetExceeded`
(3447), `FanoutWorkerFailed` (3465) — and **no `finally:`**. Each handler `return`s or
`raise`s on its own path.

So T7 adds one. A `finally:` on that try is the single point every exit crosses: normal
completion, all three handled aborts, an unhandled exception, and `GeneratorExit` when the
consumer stops iterating (the WebSocket-disconnect path). Nothing else in the file is
touched, and the release is a no-op for the 99% of runs that never launched a browser.

## Pipeline

```
AGENT.md: tools: [playwright]
      │
      ▼
_resolve_runner_tools (factory.py:1094)
      │   registry.resolve("tool", "playwright") -> PlaywrightToolProvider
      │   provide() -> (["playwright_navigate", ...], False)
      │                                            └── exclude_builtin=False, FR-003
      ▼
_resolve_custom_tool_keys (factory.py:1002)
      │   elif key in _PLAYWRIGHT_TOOL_KEYS:  bind_sandbox(sandbox); getattr(mod, key)
      ▼
app/agents/tools/playwright.py           ── the @tool verbs
      │
      ▼
app/agents/playwright_session.py         ── the lifecycle
      │
      ▼
RunSandbox.path_for(".browser/…")        ── traversal-proof, deliverable-excluded
```

Every arrow above except the last two boxes already exists and carries the `pptx` set today.

## NEW files (6)

| file | what |
|---|---|
| `backend/app/agents/playwright_session.py` | `PlaywrightSession`: explicit start/stop, per-run browser, per-agent context, the ref registry, idle timer. The only genuinely new machinery. |
| `backend/app/agents/tools/playwright.py` | The nine `playwright_*` `@tool` functions + `bind_sandbox`. Mirrors `pptx_tools.py` shape exactly — module-level `_SANDBOX`, actionable text, never raises. |
| `backend/agents/capabilities/tools/playwright.py` | `@register("tool", "playwright", user_allowed=False)`. Emits string keys. Import-clean of `app.*`. |
| `backend/tests/agents/test_playwright_tools.py` | Tool-level: policy refusals, sandbox containment, unavailable-browser degradation, stale refs. |
| `backend/tests/agents/test_playwright_session.py` | Lifecycle: survives across calls, released on every exit, one context per agent. |
| `backend/tests/agents/test_engine_cancel.py` | T7's engine `finally`: release is reached on normal completion, the cooperative AND the genuine cancel, `BudgetExceeded`, and `GeneratorExit` — plus a throwing release not masking the run. `tasks.md` names this file as T7's own **Verify** command, and the Risks table below already assumed it ("T7's test"); only this inventory had not caught up. |

### Why `playwright.py` does not shadow the package

`app/agents/tools/playwright.py` sits inside a package, and Python 3 imports are absolute.
`from playwright.async_api import async_playwright` inside it resolves to site-packages, not
to itself. The name is safe — it is called out here because it reliably looks like a defect
during review, and the second reviewer to flag it should find this paragraph instead of
filing it again.

## MODIFIED files (5)

| file | change |
|---|---|
| `backend/agents/factory.py` | One `elif key in _PLAYWRIGHT_TOOL_KEYS:` branch in `_resolve_custom_tool_keys`, plus the frozenset. Copy of the `pptx` branch at 1066-1081, including its no-sandbox skip. |
| `backend/app/agents/sandbox.py` | `_BROWSER_PREFIX = ".browser/"`, added to the `startswith` tuple in `is_deliverable_relpath` (line 434). One definition, so the workspace API cannot drift from the walk. |
| `backend/app/core/config.py` | `BROWSER_URL_POLICY: str` — the configurable allowlist (FR-015). Default `"file,localhost"`. |
| `backend/agents/execution_engine/engine.py` | The `finally:` described above. |
| `backend/agents/capabilities/tools/__init__.py` | One import line + `__all__` entry for `playwright`, mirroring the existing `pptx` line — without it `discover()`'s package import never fires the new `@register`. |

## MODIFIED tests (1)

| file | change |
|---|---|
| `backend/tests/agents/test_registry_capabilities.py` | Two `_EXPECTED_NAMES` entries. That list is the registration drift-guard — any new `@register` name has to be acknowledged there or `test_known_names_match_expected_exactly` goes red. `("tool", "playwright")` is this spec's; `("tool", "pptx")` closes a spec-017 gap that was already red on this branch and cannot be fixed by halves, because the assertion is set equality. |

## GRANTED (2)

| file | change |
|---|---|
| `backend/agents/prompts/ppt-deck-qa-v2/AGENT.md` | `tools: [workspace]` → `tools: [workspace, playwright]` |
| `backend/agents/prompts/prototype-validate/AGENT.md` | no `tools:` key → `tools: [playwright]` |

**`prototype-validate` is the dangerous one.** It declares no tool set today, so
`_resolve_runner_tools` short-circuits at `if not spec.tools and not custom_keys` and returns
`([], False)` — it keeps its native filesystem tools. Adding ANY tool set makes `spec.tools`
non-empty, which routes it through the `exclude` AND-accumulator instead. A provider
returning `exclude=True` silently strips `read_file` from a validator whose entire job is
reading files. FR-003 + SC-003 exist for this; T4 is where it is proven.

## REUSED unchanged

- Chromium + OS libs in the image (`Dockerfile:139-144`), `PLAYWRIGHT_BROWSERS_PATH=/opt/playwright`.
- `playwright==1.60.0` in `requirements.txt`.
- `RunSandbox.path_for` — traversal rejection, already `is_relative_to(root)`.
- `is_deliverable_relpath` — the single deliverable predicate; this adds one prefix to it.
- The `tool_provider` registry, `discover()`, and the `user_allowed` gate (CAP-03).
- The string-key → implementation resolution seam and its import-linter fence.
- The workspace file browser — `.browser/` screenshots surface there with no frontend change.

## Explicitly UNTOUCHED

- `app/agents/render_check.py`. Not modified, not refactored, not sharing a session. It is a
  working macro with its own lifecycle; entangling it with a long-lived session is how
  FIX-307 happened, and its own tests are SC-009.
- `agents/capabilities/gates/validation.py` and `strategies/task_loop.py` — the engine-side
  callers of `render_check`.
- Every agent not named above. SC-002 is the characterization snapshots.
- `agents/workflows/**` — no manifest changes. The grant is agent-level frontmatter.
- The user's own Playwright MCP configuration. Different process, different profile, real Chrome.

## Change budget

| | count |
|---|---|
| new source files | 3 |
| new test files | 3 |
| modified source files | 5 |
| modified test files | 1 |
| granted agents | 2 |
| new engine lines | 20 (one `finally` — 6 statements, plus the why-this-is-the-only-reliable-point comment T7 requires) |
| migrations | 0 |
| workflow manifest changes | 0 |

The three files above the spec's first-draft budget — `capabilities/tools/__init__.py`,
`test_engine_cancel.py`, `test_registry_capabilities.py` — are each a mechanical consequence of
something this plan already required (registration actually firing; `tasks.md`'s own T7 **Verify**
line; the drift-guard's set-equality assertion), not new scope. They are recorded here because
acceptance compares the changed-file set against this table, and an under-counted table reads as
scope creep.

## Risks and failure modes

| risk | containment |
|---|---|
| Session built with `async with`, reproducing FIX-307 | T2 writes the lifecycle; T3's test asserts a page is still usable on the SECOND tool call. A regression fails that test rather than reporting clean. |
| Leaked browser per abandoned run | Three reclaim paths (T7 `finally`, `playwright_close`, idle timeout). The `finally` is the load-bearing one; the others are defence in depth. |
| `prototype-validate` silently loses `read_file` | FR-003, SC-003, T4. The trap is a real branch in `_resolve_runner_tools`, not a hypothetical. |
| Screenshots leak into deliverables | `.browser/` prefix in the ONE predicate (T5). `.verify/` already proved the mechanism. |
| `playwright_evaluate` as an execution hole | Bounded by the URL policy. Under the default, the only reachable pages are files the run itself wrote. Widening the policy widens this — a deliberate deployment decision, which is why it is a setting and not a constant. |
| Engine `finally` destabilises a 10k-line generator | The added block only calls release, and release is a no-op when no session exists. T7's test covers all three abort paths plus `GeneratorExit`. |
| Agents flail against a page they cannot see | The snapshot/ref model (T2b). Screenshots are evidence for humans, not navigation for the model. |

## Deferred

- Granting the set beyond the two agents named.
- Video, tracing, HAR.
- Visual diffing of two screenshots.
- Any frontend surface beyond what the workspace browser already renders.
- Moving `PlaywrightSession` behind the `RuntimeEnvironment` port. Correct if exec ever goes
  remote; today the sandbox is local disk co-located with the process, and building the port
  indirection now would be speculative.
