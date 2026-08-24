# SPEC012-BUG-18 — the universal filesystem grant (R-22 / D-07)

| | |
|---|---|
| **Status** | Fixed — verified by A/B on live runs. Uncommitted. |
| **Found** | 2026-08-15, by a teammate whose `user_stories` run returned narration instead of a backlog |
| **Introduced by** | This spec, commit `24332e0c5` (merged to `dev`) |
| **Severity** | High — silent data loss (deliverables discarded) + unbounded token burn |
| **Affected modules** | `agents/factory.py`, `agents/workflows/compiler.py`, `app/agents/deep_agent_runner.py`, every `agents/workflows/*/workflow.yaml` |

---

## Defect

Spec 012's R-22 / D-07 "universal filesystem grant" bound `read_file` / `write_file` /
`edit_file` to **every agent declaring `tools: []`** — 61 of 87 agents. Those agents are
written and prompted as text-only ("output ONLY the markdown document"). Handed file tools
they never asked for, several began writing their output to the run sandbox instead of
returning it, where the `streamed_text` deliverable strategy cannot see it.

Two distinct failures follow from one line.

| | Failure | Cost |
|---|---|---|
| **A** | Deliverable orphaned — the agent wrote the real output to disk and streamed narration | user receives tool-call chatter instead of the artifact |
| **B** | Agents doing work that isn't theirs — a story-point estimator wrote an entire backlog | ~2.35 M tokens in the reported run |

**Non-deterministic.** Nothing forces an agent to use a tool it holds — it merely may. The
same pipeline passes on one run and fails the next on identical code, which is why it
survived signoff.

---

## Root cause

`agents/factory.py::_resolve_runner_tools` — one word.

```python
# before (24332e0c5^)                    # after the merge
if not spec.tools:                       if not spec.tools and not custom_keys:
    if mcp_tools:                            if mcp_tools:
        return (mcp_tools, False)                return (mcp_tools, False)
    return ([], True)                        return ([], False)
```

`exclude_builtin_tools` is an **exclusion** flag: `True` excludes the whole
`_BUILTIN_TOOLS` suite; `False` excludes only the library `task` tool — i.e. binds
everything else.

### Compounding effect

`no_tools = exclude_builtin_tools and not custom_tools` became `False`, so
`_NO_TOOLS_PREAMBLE` stopped being injected. The agents did not merely gain tools — they
simultaneously lost the paragraph telling them never to emit tool-call syntax:

> "You have NO tools in this session. You must NEVER emit tool-call syntax of any kind…"

### Third consumer of the same broken inference

`app/agents/deep_agent_runner.py` already documents **ISS-004**: the fabricated-XML
sanitiser was silently disabled by the same flag, leaking `<function_calls>` XML into the
user-visible stream. It was fixed by passing `sanitize_fabricated_xml=not spec.tools` —
i.e. by reading the **declaration** again instead of inferring from the resolved flag.
Defects A and B are two further consumers that were not found at the time.

---

## Blast radius

Verified against `git diff 24332e0c5^ 24332e0c5`:

```
built-in prompts touched            83
  └─ with real BODY changes          6   ← all PPT
built-in workflow.yaml semantic Δ    4   ← ppt, ppt_revision, od_ppt, od_ppt_revision
built-in agents with tools: changed  5   ← all PPT
```

Everything else was YAML re-indentation and frontmatter reformatting. For `user_stories`,
`prototype`, `app_builder`, `mulesoft_to_springboot`, `dotnet_to_azure`, `reverse_engineer`
and `chat`, **the entire behavioural delta was this one function** — no manifest or prompt
changed.

Two grant paths existed, not one:

| Path | Trigger | Scope |
|---|---|---|
| `return ([], False)` | every `tools: []` agent | fleet-wide, unconditional |
| `if delivery.staged: exclude_builtin_tools = False` | any run with attached skills | new in 012; pre-012 skills were prompt-injected, needing no fs |

### Runs affected

Every run since the merge. Locally `RUNS_ROOT=./runs` so sandboxes survive; in production
`RUNS_ROOT` defaults to `/app/runs` and orphaned files may already be gone — **not audited**
whether a customer-facing run shipped narration instead of an artifact.

`serialized_sandbox` pipelines shipped the junk directly to users:

| run | pipeline | markdown | meta-docs shipped |
|---|---|---|---|
| `650b0ccd` | mulesoft_to_springboot | 43 / 1097 KB | 17 / 253 KB (23%) |
| `705a8121` | app_builder | 29 / 811 KB | 19 / 201 KB (25%) |
| `ccd0b53b` | dotnet_to_azure | 24 / 437 KB | 12 / 159 KB (36%) |

`ccd0b53b` alone shipped nine overlapping summary documents in one folder
(`README.md`, `README_AI_INTEGRATION.md`, `DELIVERY_VERIFICATION.md`,
`AI_DELIVERY_SUMMARY.md`, `DELIVERABLES_SUMMARY.md`, `DELIVERY_SUMMARY.md`,
`FINAL_SUMMARY.md`, `QUICK_REFERENCE.md`, `AI_EXECUTIVE_SUMMARY.md`).

---

## What we did, and why

### Rejected: revert the one word

`return ([], True)` restores pre-012 behaviour, but breaks composed workflows — a
`custom-agent` instance is prompted to `write_file` its answer and would silently produce
nothing. It also leaves the decision hardcoded, which is the actual problem: **no manifest
had a say**.

### Chosen: make the workflow manifest the source of truth

Tool access is now resolved from the step's `tools:` block, bounded by a cap:

```
step tools:  ──intersect──▶  cap[trust]  ──▶  Step.tools  ──▶  denied tool names
```

**Why a cap and not just the request:** a user-authored (Composer) manifest is untrusted
input. It may grant `write_files` — writes are confined to the run sandbox by
`FilesystemBackend(virtual_mode=True)` — but never `exec`, `spawn_subagents` or `network`.
The intersection is a pure AND, so a cap can only narrow a request, never widen one.

**Why the cap lives in its own module:** every permission decision is now in
`agents/workflows/permission_caps.py` — the caps, the intersection, the permission→tool
mapping, the grant vocabulary, and the trace format. Consumers consume:

```
compiler.py   effective = apply_cap(step_grant, trust, …)
factory.py    denied    = permission_caps.denied_tools(ctx.step_tools)
engine.py     carries Step.tools to the factory — decides nothing
runner        excludes the names it was handed
```

An earlier iteration had the permission→tool mapping in `factory.py`; that was a permission
decision living outside the permission module and was consolidated.

**Why `read_files` defaults on:** absent `tools:` means read-only, not deny-all. Deny-all
would have required writing a block on all 85 steps; read-only required 24. Claude Code's
own default is the precedent — read-only, scoped, write never defaulted.

### Files changed

```
agents/workflows/permission_caps.py     NEW — every permission decision
agents/workflows/compiler.py            applies the cap; no longer defines one
agents/factory.py                       AgentContext.step_tools/workflow_name; asks for denials
agents/execution_engine/engine.py       carries Step.tools (2-line pass-through)
app/agents/deep_agent_runner.py         accepts denied_tools, applies last
agents/workflows/*/workflow.yaml        24 steps granted write explicitly
tests/agents/test_tool_grant_invariants.py  NEW — 16 tests
```

---

## Verification — live A/B, same input, same pipeline

Input: *"Build a simple todo list app for personal task tracking, with due dates and
priority levels."* — byte-identical to the original failing run `7c1e5028`.

| | **A** — write granted | **B** — read only |
|---|---|---|
| run | `270c7fa4` | `b868a6b6` |
| orphaned sandbox files | 2 files, 34 KB | **none** |
| `story-estimator` returned | 2,423 B (stub) | **19,586 B** |
| `backlog-reviewer` returned | 4,384 B | 8,206 B |
| deliverable | 19,572 B | **23,243 B** |
| tokens | 208,299 | 269,977 |
| cost | $0.278 | $0.278 |

Run A reproduced the defect exactly, attributed by timestamp:

```
story-estimator   00:56:51 ─ 00:57:49 UTC
  └─ tmp/todo_backlog_with_dependencies.md  15,015 B @ 00:57:42
backlog-compiler  00:58:43 ─ 01:00:11 UTC
  └─ tmp/todo_app_backlog.md                19,602 B @ 00:59:31
```

Run B: zero files written by any agent. `story-estimator` went from a 2.4 KB stub to
19.6 KB of returned work — **it was never doing less work, it was writing it where nothing
reads it.**

Run B output is also clean: starts directly with `# Epic:` (Run A and the original run both
leaked a `"Now I'll compile the complete, polished backlog document:"` preamble), 7 epics /
20 stories / 80 Given-When-Then clauses, zero fabricated tool XML.

### Note on tokens

Token count went **up** (208k → 270k), cost flat (cache). Expected: the estimator's 19 KB
now flows through context to four downstream agents instead of sitting on disk. The saving
is not on healthy runs — it is avoiding the 2.35 M case where an agent spends six minutes
writing ten documents nobody consumes.

### Structural fix across other pipelines (compile-verified, not yet run)

```
pipeline                 write   read-only
app_builder                5        10      ← the 10 that shipped meta-doc junk
mulesoft_to_springboot     5         8
dotnet_to_azure            4         9
prototype                  2         3
ppt                        3         0
```

---

## Outstanding

- **Six assertions still pin R-22** and will fail: `tests/agents/test_create_runner.py` (4),
  `test_mcp_client.py` (1), `test_text_only_prompt_hygiene.py` (1). Untouched deliberately —
  each needs a decision about what it should now prove.
- **Only `user_stories` was executed.** The other pipelines are compile-verified only.
- **Full suite not run.**
- **Red baseline never recorded** for the invariant tests — see
  [report-open-issues.md](../permission-bug/report-open-issues.md) §1.
- **Production impact not audited** — whether any customer run shipped narration.
- **`test_step_declaring_write_files_is_granted_write`** was the ceiling gap; resolved by
  this fix (the cap now admits `write_files`).

---

## References

Full investigation, research and design in
[`../permission-bug/`](../permission-bug/):

| Report | Contents |
|---|---|
| [report-diagnosis.md](../permission-bug/report-diagnosis.md) | Root cause, run-by-run evidence, the chain |
| [report-agent-permission-patterns.md](../permission-bug/report-agent-permission-patterns.md) | How other systems model tool permissions |
| [report-capability-confinement.md](../permission-bug/report-capability-confinement.md) | ocap / kernel precedents; mint-time vs use-time |
| [report-runtime-caps-multitenancy.md](../permission-bug/report-runtime-caps-multitenancy.md) | Entitlement/permission/quota split, runtime caps |
| [report-target-design.md](../permission-bug/report-target-design.md) | The target design and sequencing |
| [report-open-issues.md](../permission-bug/report-open-issues.md) | Everything still outstanding |

### Two findings worth carrying forward

**Independent confirmation.** CrewAI's community documented this exact failure mode: a
researcher agent given file-write tools *"would occasionally decide to do the work itself
instead of returning findings for the next agent."*

**The principle.** *"The model is not your authorization layer."* `story-estimator` was
told "output ONLY the markdown document" and wrote a 20 KB file anyway. A system prompt is
interpreted guidance, not enforced confinement.
