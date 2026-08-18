# sample_subagents composed workflow — test findings

Environment: backend at `localhost:8000` (llm_provider default = bedrock), engine +
compiler read directly for compilation checks, one live end-to-end run executed
through the real API (`run_id e4b0853a-ce2a-4daa-a80b-bf14242da2a9`, topic
"mountain climbing"), completed in 167.1s wall clock.

Files inspected: `backend/agents/workflows/sample_subagents/workflow.yaml`,
`backend/agents/workflows/compiler.py`, `backend/agents/workflows/plan.py`,
`backend/agents/workflows/artifacts.py`, `backend/agents/factory.py`,
`backend/agents/execution_engine/engine.py`, `backend/app/api/run_commands.py`,
`.knowledge/cards/ADR-0009.md`, `.knowledge/cards/ADR-0007.md`.

---

## Confirmed defects

### 1. [HIGH] Injected "Write your deliverable to `X`." line gets echoed back as the leaf agent's entire output

- **What I ran**: live run `e4b0853a-…` against the real, as-shipped
  `sample_subagents` workflow (mode: parallel, unmodified).
- **Observed**: `custom-agent:joke`'s actual streamed output — and therefore the
  file the artifact-fallback wrote — is the literal string
  `Write your deliverable to \`joke-mountain-climbing.md\`.` (verified on disk:
  `backend/runs/<user>/<run>/joke-mountain-climbing.md`). This is not a joke; it
  is the boilerplate instruction line the factory appends to every custom-agent
  prompt.
- **Expected**: one line containing a joke about "mountain climbing", per the
  step's own prompt (`workflow.yaml:100-103`: "Output only the joke, no
  commentary or preamble").
- **Root cause**: `agents/factory.py:565` unconditionally appends
  `f"Write your deliverable to \`{filename}\`."` as the LAST line of every
  custom-agent's composed prompt, after the step's own "output only X, no
  commentary" instruction. On this run (Bedrock Haiku, not even the weaker
  Ollama qwen3.5:4b target), the model treated that trailing imperative as the
  content to emit rather than a meta-instruction.
- **Compounding effect**: the downstream `page` agent (whose prompt explicitly
  says "Use their exact contents — do not invent your own",
  `workflow.yaml:53-55`) read the broken `joke-mountain-climbing.md`, recognized
  it was unusable, and fabricated its own joke text ("Why don't mountain
  climbers ever get lost?…") that appears nowhere in any upstream artifact —
  a direct violation of its own instruction, caused by the upstream corruption.
- **File:line**: `backend/agents/factory.py:565` (root cause);
  `backend/agents/workflows/sample_subagents/workflow.yaml:100-103` (the
  step whose output this corrupted).
- **Severity**: HIGH — silently corrupts a leaf deliverable and cascades into a
  documented prompt-contract violation in the parent step, on a non-degraded
  (Bedrock Haiku) model, not just the weak-model edge case ADR-0007 was written
  for.

### 2. [HIGH] tool_call/tool_result pairing in the persisted `agent_outputs` is LIFO, not FIFO — misattributes results to the wrong call

- **What I ran**: same live run; inspected `GET /api/runs/{id}` response's
  `agent_outputs[3]` (the `page` step)'s `tool_calls` array.
- **Observed**: three consecutive failed `read_file` calls
  (`/emoji/mountain.md`, `/fact/mountain-climbing.md`,
  `/joke/mountain-climbing.md`) each got a `result` naming the WRONG missing
  file — shifted by one position (call *i*'s persisted result actually
  corresponds to call *i-1*'s path). The same shift recurs for the three
  successful `read_file` calls against the real artifacts: the persisted
  result for `/fact-mountain-climbing.md` shows the joke agent's broken text,
  and the result for `/joke-mountain-climbing.md` shows the fact text — swapped
  relative to what is actually on disk (verified directly:
  `fact-mountain-climbing.md` correctly holds the fact, `joke-mountain-climbing.md`
  correctly holds the broken joke-agent text).
- **Expected**: each tool_call's persisted `result` is the result of that exact
  invocation.
- **Root cause**: `app/api/run_commands.py`, `_apply_terminal_output_columns`
  (the docstring at line ~1826 states it is "the SOLE writer of these columns
  for BOTH the launch path AND the two resume entry points"), lines
  1883-1887:
  ```python
  for tc in reversed(current_agent.get("tool_calls", [])):
      if tc.get("tool") == data.get("tool") and tc.get("result") is None:
          tc["result"] = data.get("result")
          break
  ```
  This matches purely by tool NAME (no call id) and walks the list
  most-recent-first (LIFO). When two or more calls to the same tool are
  outstanding and their results resolve in call order (FIFO — the normal
  case), the first incoming result gets attached to the LAST-issued call
  instead of the first, and every subsequent result shifts by one.
- **File:line**: `backend/app/api/run_commands.py:1876-1887`.
- **Impact**: the persisted/API-visible tool-call audit trail (what a
  developer or the UI's tool-call inspector would show for any run with ≥2
  same-named tool calls in one agent turn) is silently wrong. I could not
  confirm this reached the MODEL's own context incorrectly — `page.html`'s
  actual fact section matches the real on-disk fact file, so the live
  `read_file` results delivered to the model were almost certainly correct;
  this bug is in the persistence/collector layer, not necessarily the
  live dispatch loop.
- **Severity**: HIGH for observability/debuggability (corrupts the only
  API-visible tool trace for exactly the composed-multi-agent workflows this
  spec exists to support — many same-named `read_file` calls per step).

### 3. [MEDIUM] Stale dot-separated filename example in the `page` step's prompt contradicts the actual (hyphen) artifact-naming convention

- **What I checked**: `backend/agents/workflows/sample_subagents/workflow.yaml:52-55`
  (new/untracked in this branch — `git status` shows it as `A`, not previously
  committed) vs. `backend/agents/workflows/artifacts.py:116-132` and
  `.knowledge/cards/ADR-0007.md`.
- **Observed**: the `page` step's prompt says: *"read the three files named
  emoji.\*, fact.\*, and joke.\* (e.g. `/emoji.mountain.md` at the root)"* — a
  DOT between instance_id and topic. The actual convention, per
  `artifact_name()` and ADR-0007, is a HYPHEN: `emoji-mountain-climbing.md`.
  ADR-0007 documents that this exact dot-vs-hyphen confusion was previously
  observed causing qwen3.5:4b to misread the dot as a path separator and fail
  to find the file.
- **Expected**: the prompt's own example should match the real convention it
  is instructing the model to rely on.
- **Observed effect in the live run**: the `page` agent's first three
  `read_file` calls (using the stale dot/slash-shaped guess) all failed; it
  recovered via a `glob` call and found the real hyphenated filenames. On
  Bedrock Haiku this cost 2 extra tool round-trips but did not break the run;
  on qwen3.5:4b — the model ADR-0007 was written about — this is the exact
  failure mode ADR-0007 fixed once already.
- **File:line**: `backend/agents/workflows/sample_subagents/workflow.yaml:53`.
- **Severity**: MEDIUM — currently masked by the model's ability to recover
  via glob, but reintroduces a previously-fixed failure class for the
  small-model target this workflow is designed to exercise.

### 4. [MEDIUM] Artifact-fallback safety net ignores `deliverable_filename_override`, targeting the wrong file for the deliverable-producing step

- **What I checked**: `backend/agents/execution_engine/engine.py`,
  `_check_artifact_fallback` (~line 3277-3316, called at line 4447-4449) vs.
  `agents/factory.py:555-566` (`_resolve_step_skills`'s neighbor, the prompt
  composer), which DOES consult `ctx.deliverable_filename_override` when
  telling the model what to write.
- **Observed on disk** (same run): `page.html` (the declared `single_file`
  deliverable, `deliverable_filename_override="page.html"`) was written
  correctly by the model at `14:18:02`. Seven seconds later, at `14:18:09`,
  the engine's artifact-fallback ALSO fired for the `page` step and wrote a
  second, byte-identical file `page-mountain-climbing.md`
  (`artifact_name(instance_id, topic)` — ignoring the override).
- **Root cause**: `_check_artifact_fallback` hardcodes
  `filename = artifact_name(instance_id, topic)` and never checks
  `ectx.deliverable` / the step's `deliverable_filename_override`, unlike the
  prompt-composition path that already threads this through correctly
  (`factory.py:559`: `ctx.deliverable_filename_override or
  artifact_name(instance_id, ctx.topic)`).
- **Impact today**: a harmless-looking but real duplicate file write on every
  run whose deliverable-producing step succeeds normally. **Worse case (not
  observed this run, but reachable)**: if the deliverable-producing model
  fails to call `write_file` on the declared name, this "guarantee" writes the
  streamed text to the WRONG filename (`page-<topic>.md` instead of
  `page.html`), while still emitting a success-shaped `artifact_fallback`
  event — the `single_file` deliverable resolver, which reads back the exact
  declared name, would then find nothing, but nothing about the emitted event
  signals that the guarantee targeted the wrong file.
- **File:line**: `backend/agents/execution_engine/engine.py:3277-3316` (fix
  site), contrast `backend/agents/factory.py:555-566` (already-correct
  precedent in the same file family).
- **Severity**: MEDIUM — confirmed duplicate-write today; the fail-closed gap
  (fallback pointing at the wrong deliverable filename) was reasoned from code
  but not independently reproduced by forcing the model to skip `write_file`.

---

## Working as intended

- **`mode: parallel` vs `mode: sequential` compile to the same flat Step order,
  and the engine dispatches both strictly serially today.** Verified by
  compiling both variants in-process (`WorkflowCompiler.compile` against copies
  in `/tmp`, since manifests must live under the fixed
  `agents/workflows/` root to be engine-loadable and the backend could not be
  restarted to register a new pipeline_type):
  - parallel: `emoji(deps=[]) → fact(deps=[emoji]) → joke(deps=[]) →
    page(deps=[fact,joke])`
  - sequential: `emoji(deps=[]) → fact(deps=[emoji]) → joke(deps=[fact]) →
    page(deps=[fact,joke])`
  Only the `joke` step's `depends_on` differs; the compiled `steps` LIST ORDER
  is identical in both modes. `engine.py:1762-1765` then takes
  `ordered_agents = list(agents)` (the compiler's already-topo-sorted flat
  order) whenever any step declares `depends_on` — true for both modes here —
  so dispatch order is byte-identical regardless of `mode`. This matches
  ADR-0009's finding.
  - **Live-verified timing** (this run, `mode: parallel` as shipped, from
    `run-logs.jsonl`): `emoji 14:15:22.823→14:16:07.582`,
    `fact 14:16:07.626→14:16:44.399` (started 44ms after emoji ended),
    `joke 14:16:44.412→14:17:04.447` (started 13ms after fact ended),
    `page 14:17:04.483→14:18:09.844`. Zero overlap between `fact` and `joke`
    despite `mode: parallel` declaring no edge between them — reproduces
    ADR-0009's measurement independently, on a fresh run today.
- **`subagents.max_parallel` under `mode: parallel` is consistently rejected**,
  not silently accepted or inconsistently enforced. Verified by compiling a
  mutated copy of the manifest with `max_parallel: 2` added under the
  top-level `subagents:` block — raises `CompilerError` naming the field
  (`compiler.py:519-526`), matching ADR-0009 Decision 3's claim.
- **No UI/event misreports parallelism.** `agent_start`/`agent_complete`
  events (`app/api/run_commands.py:1861-1904`) carry no `parallel`/`wave`
  field; nothing in the payload claims concurrent execution.
- **Artifacts are correctly keyed on `instance_id` and do not clobber each
  other** for the three leaf steps: `emoji-mountain-climbing.md`,
  `fact-mountain-climbing.md`, `joke-mountain-climbing.md` all exist
  independently with distinct, correct content (aside from the joke content
  defect #1 above, which is a content-quality bug, not a clobbering bug).
- **Per-step skills are staged and read.** `backend/runs/<user>/<run>/skills/`
  contained `playful-tone/SKILL.md` (fact step) and, per the API's recorded
  `tool_calls`, the `emoji` and `page` agents each issued a `read_file` against
  their own `/skills/<name>/SKILL.md` and received its real content back —
  confirming per-step skill delivery reaches the agent, consistent with the
  declared `skills:` list per step in the manifest.

---

## Could not verify

- **Behavior on the actual target model (Ollama `qwen3.5:4b`).** The
  backend's `/health` reports `llm_provider: bedrock`, and the live run (no
  per-agent model override set, as instructed) resolved to
  `eu.anthropic.claude-haiku-4-5-20251001-v1:0` (the Bedrock Haiku default),
  not Ollama. I could not find a way to route to Ollama without setting an
  explicit per-agent `model`, which the task instructions said not to do
  (and a `qwen3.5:4b` id is not in the 5-id Bedrock allow-list, so it would
  likely be rejected outright). All findings above are therefore verified
  against Bedrock Haiku, not qwen3.5:4b — defect #1 and #3 are plausibly WORSE
  on the weaker target model (ADR-0007 was written specifically because of a
  qwen3.5:4b failure of the same shape as #3), but I did not reproduce them
  there.
- **A live run with `mode: sequential`** end-to-end through the HTTP API.
  Registering a second pipeline_type requires the backend process to
  re-import `agents/loader.py`'s `SUPPORTED_PIPELINE_TYPES` (derived from disk
  at import time), which requires a restart — explicitly disallowed by the
  task. I verified the sequential/parallel equivalence by direct in-process
  compilation (see "Working as intended" above) instead of a second live run.
- **The `skill_used` INFO log line** (`app/agents/deep_agent_runner.py`,
  per `backend/CLAUDE.md`'s "Debug tracing" section). The running backend
  process was started outside this session and writes to its own stdout, not
  a file I could tail. Indirect evidence (the emoji/page agents' recorded
  `read_file` calls against their staged `SKILL.md` files, and outputs
  consistent with those skills' instructions) strongly suggests skills were
  actually used, but I did not see the INFO line itself.
