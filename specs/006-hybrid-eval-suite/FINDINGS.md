# Findings — Prototype Revision Pipeline

All line numbers verified against `feature/diagrams-and-api-fixes` on 2026-07-21.

---

## Defect B first (it's the simpler chain, and Defect A's fix plan leans on it)

### B1. Extended thinking is OFF by default, globally, one knob for every agent

`backend/app/agents/model_factory.py::build_model()`:

```python
thinking_enabled = settings.THINKING_BUDGET_TOKENS > 0
```

`backend/app/core/config.py:117`:

```python
THINKING_BUDGET_TOKENS: int = 0
```

So today, on every environment that hasn't overridden the env var, **no agent
in the system requests extended thinking** — not just revision agents, all
of them. This is a single global switch; there is no per-agent or
per-pipeline override for it (contrast with the model itself, which *does*
have a 5-tier per-agent resolution path — see B4 below).

### B2. Even if enabled, thinking content is silently dropped before it ever becomes an event

`backend/app/agents/deep_agent_runner.py:829-839`:

```python
def _extract_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return ""
```

Anthropic extended thinking returns content blocks of `type == "thinking"`
(direct API) or `reasoning_content` (Bedrock Converse). `_extract_text` only
extracts `type == "text"` blocks. On the `on_chat_model_stream` path
(`deep_agent_runner.py:486-495`), a thinking delta arrives as one of these
blocks, `_extract_text` returns `""` for it, and the `if text:` guard means
**nothing is yielded for it at all** — not as a chunk, not as anything.

### B3. There is no `thinking` branch in `astream_events()`'s event-type dispatch

`deep_agent_runner.py:475-553` handles exactly four LangGraph event types:
`on_chat_model_start`, `on_chat_model_stream`, `on_chat_model_end`,
`on_tool_start`/`on_tool_end`. There is no code path that would ever produce
a `{"type": "thinking", ...}` yield even if B2 were fixed — the docstring's
own event-mapping table (lines 423-431) doesn't list thinking as a row.

### B4. The manifest-driven engine only maps `chunk` → `agent_chunk`; `agent_thinking` is unreachable from the live pipeline

`backend/agents/execution_engine/engine.py:3615-3631` — the loop that
consumes `agent.astream_events(...)` for every pipeline agent (prototype,
prototype_revision, all others) only branches on `etype == "chunk"`,
mapping it to the WS event `agent_chunk`. There is no `elif etype ==
"thinking"` anywhere in `engine.py`.

The **only** place `agent_thinking` is emitted anywhere in the backend is:

```
backend/app/services/handoff_pipeline.py:417
backend/app/services/handoff_pipeline.py:509
```

— both are **hardcoded, canned strings** (`"Reading relevant files and
planning the change..."`, `"Reviewing for security and best practices..."`),
not actual model reasoning, and `handoff_pipeline.py` is a **separate
subsystem** from the `ExecutionEngine`/`prototype_revision` pipeline this
investigation is about (it backs the Handoff/coder-agent feature, per
`backend/app/agents/handoff/coder.py`).

### B5. The frontend is fully built for this and is just never fed

`frontend/src/hooks/useWorkflow.ts:315-330` has a complete, working
`case "agent_thinking":` handler — it accumulates `thinkingText`, sets
`status: "thinking"`. `ThinkingBlock.tsx` and `AgentThinkingTab.tsx` render
it. This is dead weight from the live pipeline's perspective: correct code
with no producer.

### B5 conclusion

**"Enable thinking" (flip `THINKING_BUDGET_TOKENS` > 0) today would do
exactly one thing: make every Bedrock/Anthropic call slower and slightly
more expensive (thinking tokens are billed), force `temperature=1` on every
agent (`model_factory.py`, both branches), and produce zero visible change
in the UI** — because B2+B3+B4 discard the thinking content before it can
reach a WS event. This is the direct, falsifiable answer to "what happens
if we enable it": nothing good, without the runner + engine changes below.
It is not a config flip; it's a three-layer plumbing gap.

---

## Defect A — revisions don't reliably fix the reported issue

### A1. The revision pipeline has exactly two structural safety nets, and neither checks against the user's instruction

`backend/agents/workflows/prototype_revision/workflow.yaml`:

- **Step 1** (`prototype-revision-agent`, `single_shot`, `gates: [validation]`,
  `validators: [html_static, html_render]`, `post_step: revision_validation`):
  the agent that actually reads the instruction and edits `prototype.html`.
- **Step 2** (`prototype-revision-validate`, `gates: []`): a second agent
  that re-reads the file and fixes *structural* issues (empty pages, DS
  token drift, unwired nav) — **not gated**, so nothing re-runs
  `html_static`/`html_render` after its edits either (see A5).

Both nets are real and useful, but neither is a check of "did the edit
satisfy what the user asked for." They catch a different, narrower class of
problem (the edit broke something), not the class of problem being reported
(the edit didn't accomplish something).

### A2. The post-step fix-loop's own docstring says it only chases *new* issues vs. a pre-edit baseline

`backend/agents/capabilities/post_steps/revision_validation.py` computes a
**pre-edit baseline** (`compute_revision_baseline` on
`ctx.revision_original_html`) specifically so that pre-existing issues are
*not* touched. `backend/agents/execution_engine/engine.py:4392-4394`
(docstring of `_run_validation_fix_loop`):

> "With populated baselines (REVISION) only NEW static/console issues are
> selected, while hard render-breakage (page errors, dead nav) is always
> included."

This is intentional and correct *for its stated purpose* (don't regress
things the user didn't ask about) — but it means the loop's failure
condition (`failing = bool(error_lines)`, `engine.py:4466`) can never be
true because of "the reported bug is still there." If the revision agent's
edit is a structural no-op (touches nothing, or touches the wrong thing) but
introduces zero *new* static/console issues, `_select_issues_to_fix` returns
empty, `failing` is `False`, and the loop exits on the first pass reporting
success — with the user's actual issue untouched.

### A3. `clarify.mode: skip` means the entire interpretation burden sits on one Haiku turn, with no clarifying round-trip

`workflow.yaml:16-17`:
```yaml
clarify:
  mode: skip
```
The manifest's own comment says this is deliberate ("the revision
instruction is the complete brief"). That's a reasonable UX trade-off, but
it raises the stakes on step 1's single interpretation of the raw
instruction: there's no clarification, and (per Defect B) no visibility
into how the agent interpreted it either. An ambiguous instruction
("fix the dropdown") has no path to a follow-up question and no way for the
user to see, mid-run, that the agent picked the wrong dropdown.

### A4. No per-agent model override is configured for revision, despite the mechanism existing

`backend/agents/model_policy.py` documents a 5-tier `ModelResolver`
precedence: user override → `step.model` → `AgentSpec.model` → workflow
model → session/global Haiku default. Neither
`agents/prompts/prototype-revision-agent/AGENT.md` nor
`agents/prompts/prototype-revision-validate/AGENT.md` sets a `model:`
field, so both fall through to tier 5 (session model or the global Haiku
default) exactly like every other agent. The infrastructure to run *just*
the revision step on a stronger model already exists and needs no engine
change — it's a one-line `AGENT.md` frontmatter addition. (Flagged as an
optional lever, not the primary fix — see PLAN.md; the ask was to work
within Haiku.)

### A5. Step 2's edits are never re-validated

`workflow.yaml:58-59` — `prototype-revision-validate` runs with `gates: []`.
Its own `AGENT.md` explicitly instructs it to rewrite `:root` tokens, fill
empty pages, and rewire routers (`agents/prompts/prototype-revision-validate/AGENT.md:36-96`)
— all of which can introduce new static/render issues — but nothing runs
`html_static`/`html_render` afterward. This is a secondary risk (can cause
new problems, not the reported one), but worth listing: it means the LAST
agent to touch the file before delivery is also the one least checked.

### A6. `edit_file` failures are self-correctable within the run, not a root cause

Checked `deepagents`' `filesystem.py`/`filesystem middleware`: a
non-unique or non-matching `old_string` in `edit_file` returns a **tool
error message** back into the agent's own context (not a silent no-op, not
an exception that aborts the run) — the agentic loop can see the error and
retry with a better anchor within the same step. This rules out "the edit
tool silently failed" as a primary root cause; it's a possible contributor
in pathological cases (agent gives up after a bad anchor without retrying)
but not the systemic explanation.

### A7. Conclusion — the systemic gap

There is no closed-loop verification step, anywhere in `prototype_revision`,
that re-reads the user's original instruction and checks the *post-edit*
`prototype.html` against it. Both validation layers check "is the file
structurally healthy," never "does the file now do what was asked." On
Haiku specifically — a fast, cheap model with no extended-thinking budget
and no visible reasoning trace — that means the *only* thing standing
between "agent misunderstood/half-did the request" and "pipeline reports
success" is the single agent's own single-pass judgment, unchecked.

---

## Summary table

| # | Gap | File:Line | Severity |
|---|-----|-----------|----------|
| B1 | Thinking globally OFF by default (`THINKING_BUDGET_TOKENS=0`) | `backend/app/core/config.py:117` | Config, not a bug |
| B2 | `_extract_text` drops `thinking`/`reasoning_content` blocks | `backend/app/agents/deep_agent_runner.py:829-839` | Blocking |
| B3 | No `thinking` branch in the event dispatcher | `backend/app/agents/deep_agent_runner.py:475-553` | Blocking |
| B4 | Engine never maps any event to `agent_thinking` for pipeline agents | `backend/agents/execution_engine/engine.py:3615-3631` | Blocking |
| A1/A2 | Fix-loop only chases *new* issues vs. pre-edit baseline, never checks instruction-fulfillment | `backend/agents/execution_engine/engine.py:4392-4466`, `backend/agents/capabilities/post_steps/revision_validation.py` | Root cause (primary) |
| A3 | No clarification round-trip; single Haiku pass owns all interpretation | `backend/agents/workflows/prototype_revision/workflow.yaml:16-17` | Contributing |
| A4 | No per-agent model bump configured (mechanism exists, unused) | `backend/agents/model_policy.py`, both revision `AGENT.md`s | Optional lever |
| A5 | Step 2 (`prototype-revision-validate`) edits are never re-validated | `backend/agents/workflows/prototype_revision/workflow.yaml:58-59` | Secondary risk |
| A6 | `edit_file` no-op — ruled out as primary cause | deepagents `filesystem` middleware | Not root cause |
