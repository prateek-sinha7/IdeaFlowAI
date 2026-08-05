# Integration Contracts: Applying Advisor Prompt Edits

## External services

**None.** `apply-advice` and `revert` make no network call. They read a JSON file the run
already produced and write files on the local filesystem. Zero tokens, zero external
dependencies.

*(The `grade.sh advise` command that produces the input does call a judge model — but that is
existing behaviour owned by [005-prompt-eval-scoring](../../005-prompt-eval-scoring/spec.md),
not added here.)*

## Events, jobs, queues, webhooks

**None.** No background job, no queue message, no scheduled task, no webhook. Both commands are
synchronous and finish in milliseconds.

## Database

**None.** No table, no migration, no read, no write.

## Version control

**None, deliberately.** No command in this feature invokes git (spec R-09). The developer
reviews `git diff` and commits.

---

## Internal contracts — what this feature depends on, and what would break it

These are in-process, not integrations, but they are the couplings that matter for review.

### 1. `PromptAdvice` / `PromptEdit` schema

**Producer**: `evals/grading/model/prompt_advisor.py:46-68`
**Consumer**: `prompt_edits.py` via the new JSON sidecar

| Field | Relied on for |
|---|---|
| `action` | Dispatch: `add` / `remove` / `modify` |
| `section` | The anchor for `add` (data-model.md, AD-04) |
| `current_text` | Verbatim, exactly-once match for `remove` / `modify` |
| `proposed_text` | The inserted or replacing text |
| `reason` | Printed in the diff output |

**Breaks if**: a field is renamed, or `action` gains a value. Mitigation: the consumer rejects an
unknown `action` with exit 9 rather than ignoring it, so a schema extension fails loudly instead
of silently dropping an edit.

### 2. `AGENT.md` file format

**Owner**: `backend/agents/loader.py` (`load_agent_spec`, `:129`)
**Relied on**: YAML frontmatter delimited by `---`, followed by a non-empty markdown body.

**Contract this feature honours**: the frontmatter block is opaque and is written back
byte-for-byte. Everything the engine reads from `AGENT.md` — `id`, `pipeline_type`, `order`,
`produces`, `consumes`, `tools`, `guardrails`, `gate`, `injects`, `model`, `max_tokens` — is
therefore unchanged by construction.

### 3. Agent-folder scanning

**Owner**: `loader.list_agent_ids` (`:182`) → `registry._discover_pipeline_agents` (`:57`) →
`PIPELINE_AGENTS` (`:78`, computed at import).

**Contract relied on**: the scan matches the literal filename `AGENT.md` (`loader.py:201`) and
never globs. This is what makes `AGENT.vN.md` invisible to the registry, the DAG resolver, the
workflow manifests and the engine's manifest-vs-registry assertion.

**Breaks if**: that scan is ever changed to `glob("AGENT*.md")` — every archive would then
register as a duplicate agent, most likely failing on duplicate `order`. **Guarded by** the R-10
regression test, which asserts the agent count and every `PIPELINE_AGENTS` list are unchanged
with archive files present on disk. That test is the tripwire for this contract; it should say
so in its docstring.

### 4. Run-folder paths

**Owner**: `evals/grading/artifacts.py` — sole owner of every run-folder path (005 §3).
**Contract**: the JSON sidecar path is added there, not composed inline in the advisor or the
CLI.

## Backward compatibility summary

| Consumer | Impact |
|---|---|
| Execution engine / kernel | None — no runtime file is modified |
| Agent registry, workflow manifests, DAG resolver | None — archives are invisible |
| Per-user prompt overrides (`app/agents/prompt_overrides.py`) | None — untouched, still applied at compose time |
| Existing `grade.sh` verbs | None — purely additive |
| Existing run folders | Readable; a pre-sidecar run gets a clear exit-2 message pointing at `grade.sh advise` |
