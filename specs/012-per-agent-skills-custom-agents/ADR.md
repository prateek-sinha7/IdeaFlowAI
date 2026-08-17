# Spec 012 — decisions

Every architectural decision made while implementing this spec — most of them taken as a
direct result of the investigation reports in `reports/`, a few taken directly against a
spec requirement or during the custom-workflow bug-fixing session. See `bugs.md` and
`issues.md` in this same folder for the defects; this file is for the design calls behind
them.

**IDs are `SPEC012-ADR-NN`, stable and sequential — cite these.** Each row states the
decision in full; you should not need to open anything else to understand what was
decided and why. `Ref` points at the global `.knowledge/cards/ADR-XXXX.md` card for
whoever wants the original write-up, background, and alternatives considered — it is
supporting depth, not the primary record.

Numbered in the order the underlying investigation reports appear in `reports/README.md`
("Read in this order"), then by the two decisions made directly against a spec
requirement, then by the two made during the later bug-fixing session. Not chronological
by decision date — grouped by source, so related decisions sit together.

---

## Decisions (10)

| ID | Decision | Driven by | Status | Ref |
|---|---|---|---|---|
| **SPEC012-ADR-01** | The compiled plan is the run's agent roster. The engine used to build the roster twice — once from the manifest, once from registry membership (`pipeline_type:`/`order:` in each `AGENT.md`) — and raised `RuntimeError` if they disagreed. That's unsatisfiable for a custom workflow: its steps are instances of one template with no `AGENT.md`, so registry membership is always `[]`. Deleted the assertion rather than relax it; the plan is now the single source. | `reports/plan-as-roster.md` | Accepted | `ADR-0003` |
| **SPEC012-ADR-02** | The roster has three sources, and the plan **fills in** rather than **overrules**. Fixing ADR-01 by unconditionally rebuilding from the plan introduced a regression: a user who picked 3 agents in the composer got all 9 steps from the static `custom` manifest, because the plan overwrote their selection. The caller's list — when one exists — wins; the plan is the source of last resort, used only when the caller has nothing (a template-instance workflow). | `reports/plan-as-roster.md` | Accepted | `ADR-0008` |
| **SPEC012-ADR-03** | Declared order wins over inferred order whenever a step carries `depends_on`. Two competing orderings exist: the resolver's topo-sort over `produces`/`consumes`, and the compiler's topo-sort over manifest-declared `depends_on`. Four instances of one contract-free template can't be ordered by contracts at all — there's nothing to infer from. So: if any compiled step has a `depends_on` edge, use declared order for the whole plan; otherwise keep the resolver's inferred order, unchanged for every existing pipeline. **Known sharp edge, accepted anyway:** the check is `any(...)` — one hand-authored `depends_on:` line on an ordinary manifest flips ordering for the *entire* plan, and three production pipelines (`app_builder`, `dotnet_to_azure`, `mulesoft_to_springboot`) have a resolver order that differs from their manifest order. Adding one `depends_on:` to any of them would silently revert their execution order with no error, no warning, no test. | `reports/dag-validation-bypass.md` | Accepted | `ADR-0004` |
| **SPEC012-ADR-04** | Which pipeline types exist is derived from disk at import, not a hand-typed `frozenset`. The old list had to be edited by hand for every new workflow, and a forgotten edit silently broke discovery for the new type — a direct violation of SC-001 ("launchability is keyed on a declared flag, never a hardcoded name list"). Now derived from three sources: every `agents/workflows/<id>/` containing a `workflow.yaml`, every `pipeline_type` an `AGENT.md` declares, and a small fixed set of run-label aliases. **Consequence accepted and implemented:** the set grew 17→21, newly exposing three `sample_*` fixture manifests that reference agents with no `AGENT.md` and can't run. Closed by setting `user_launchable: false` on those three (verified on disk) and updating the two tests that had asserted "must be absent" to "must be not launchable" instead — the correct reading of SC-001, not a special case. | `reports/dynamic-loader.md` | Accepted, implemented | `ADR-0005` |
| **SPEC012-ADR-05** | The wave-scheduling **surface** is compiler-derived; the **dispatcher** is a separate, later decision. Independent steps running concurrently needs `Step` objects to carry what `build_waves` already expects of `Task` objects — a conflict key and a stable id. Added `Step.conflict_keys` (derived from `instance_id`, never authored — keeps `_ALLOWED_STEP_KEYS` closed, so this can't become a manifest control-flow key) and a `Step.id` property aliasing `agent_id`. **Explicitly partial:** this is scaffolding only. The dispatcher itself — the `asyncio.Queue` fan-in, cancellation-and-drain, HITL pause at a wave boundary, and durable state for a partially-complete wave — is not built. A confirmed, unrelated bug was found during this investigation and is tracked separately in `bugs.md`/`issues.md`, not here: `skill_staging`'s prune-on-stage logic assumes exactly one step in flight and would silently delete a concurrent sibling's skill files. | `reports/step-fanout.md` | Partial — surface built, dispatcher not | `ADR-0009` |
| **SPEC012-ADR-06** | Per-step skill scoping prunes stale skill directories rather than wiping and rewriting the whole tree. The run sandbox's `skills/` directory is shared across every step in a run, and staging only ever wrote — nothing removed a previous step's skill directory. A later step could read a skill it was never attached to, straight off disk (observed: a step read a skill left behind by an earlier one and answered with the wrong capability instead of its own). Prune only the directories not in the current step's attached set; a re-attached skill keeps its file untouched, preserving staging idempotency. **Consequence accepted:** the prune set is *this step's* attached ids, so it is not concurrency-safe by construction — two steps running at once would each prune the other's skill. Inert today because the step loop is strictly serial (see `SPEC012-ADR-05`); a lock would not fix it, since the prune SET would still be wrong — the real fix if step concurrency ever ships is pruning against the whole wave's union. | Spec requirement R-01 | Accepted | `ADR-0006` |
| **SPEC012-ADR-07** | Custom-agent artifact filenames use a hyphen between `instance_id` and `topic`, not a dot. `<instance_id>.<topic>.md` reads to a small local model as a path separator — observed on `qwen3.5:4b`, which wrote `/joke/mountain.md` instead of the file, then let the artifact-fallback save its own chat text ("Written to `/joke/mountain.md`.") as the artifact, so the downstream step read that sentence instead of the joke. A separator that cannot be mistaken for a directory removes the whole failure chain. **Consequence accepted:** the two halves are both hyphen-slugs, so the resulting filename is not mechanically splittable back into its parts — anything needing the `instance_id` must carry it separately rather than parsing the name. | Spec requirement R-12 | Accepted | `ADR-0007` |
| **SPEC012-ADR-08** | Run-level skill attachment is retired entirely; the per-agent picker (`AgentSkillsPicker`, this spec's `Step.skills`) is the single authoring surface. Two competing scopes existed under one word — "skills" meant a run-wide bag applied uniformly to every agent in one panel, and a per-agent list in another — and a user could not tell which one they were editing. Removed the run-level surface from the UI, the launch payload, and the save payload. **Consequence accepted:** launch paths with no per-agent UI — revisions, chains, wizard launches — can no longer attach skills at all. Hooks stay run-level, because no per-step hooks field exists yet; this decision covers skills only. | This spec's own design (per-agent `Step.skills`, R-01/R-36) | Accepted | `ADR-0010` |
| **SPEC012-ADR-09** | The delivery block's derived filename (`artifact_name(instance_id, topic)`) is authoritative; a filename a step's own prompt names (e.g. "save it to paragraph.md") is not honoured. Three mechanisms — the artifact-fallback guarantee, the roster, and the deliverable readback — must all agree on one filename, and only a machine-derived name can guarantee that; a user-authored name is known only to the prompt text, and any disagreement produces a step that reports success while downstream reads nothing. **Trialled the opposite and reverted:** removing the delivery block let the full multi-step chain execute for the first time, but the artifact-fallback guarantee then wrote empty files for steps that had already written their own, and the roster advertised those 0-byte files to the next step — trading one bug for a worse one. **Consequence accepted:** an authored filename is silently ignored, with no warning; inter-step handoff travels through the roster, never through a name the author chose. | `reports/outstanding-bugs.md` (custom-workflow bug-fixing session) | Accepted | `ADR-0011` |
| **SPEC012-ADR-10** | Composer tool-grant toggles (`read_files`, `write_files`, `exec`, `spawn_subagents`) are fixed values, not author-editable. Traced every consumer of `step.tools` and found none of the four toggles did what its label claimed: `write_files`/`read_files` don't gate the native filesystem tools (bound regardless via `exclude_builtin=False`) — `read_files: false` only disabled the secret-scan hook, the opposite of what a security-minded author would expect; `exec`/`spawn_subagents` are rejected outright by the compiler for `db`-trust manifests, so granting either only made the workflow fail validation on save. `write_files` in particular has no coherent "off": every composed step must write exactly one file, its artifact — the handoff `SPEC012-ADR-09` describes — so enforcing `false` would break the workflow it's attached to. Fixed the manifest to state what the runtime already does (`read_files`/`write_files` always `true`, `exec`/`spawn_subagents` always `false`, removed from the palette) rather than build enforcement for a feature that never worked. **Consequence accepted:** per-step privilege scoping is no longer a product surface at all — the fields remain in the schema for an engineer-authored manifest, but a Composer user cannot express "this step may not write arbitrary files." | `reports/outstanding-bugs.md` (custom-workflow bug-fixing session) | Accepted | `ADR-0012` |

---

## Open questions

Real architectural decisions this spec's own reports raised, that were **not** formalized
— tracked here rather than silently dropped.

### The big one: who owns the DAG?

`reports/dag-ownership.md` — titled "the decision report" in `reports/README.md` — argues
`workflow.yaml` should own structure and order **unconditionally**, and agents should be
free, reusable, order-agnostic capabilities with no fixed pipeline. Its evidence: 72 of 87
agents declare `produces: [<their own agent id>]`, which is `depends_on` written
backwards and stored on the wrong object — the only 8 agents using genuine shared type
names all belong to `spec_kit`, which no manifest references and which the resolver
reports unsatisfiable. Zero agents are reused across the 16 pipelines. The type system
this argument concerns has, in practice, never been used as a type system.

**This was not accepted.** `SPEC012-ADR-03` above took a narrower fallback instead —
declared order wins only when a step already carries a `depends_on` edge — leaving the
resolver's inferred order as the default everywhere else. Verified live: `engine.py`
still falls back to `validation.dag` when no step declares `depends_on`.

The report's own migration path names the blocker: Step 1 is freezing the current
resolver order for `app_builder`/`dotnet_to_azure`/`mulesoft_to_springboot` into their
manifests — behavior-preserving, since the resolver already dictates what they execute —
but "preserves today's behavior" and "is the *desired* order" are different claims, and
someone who knows those three pipelines needs to confirm the second before it is written
into the spec as intentional. Until that happens, this stays open.

### `agent-vs-workflow-config.md`'s unresolved recommendations

Six of this report's eight ranked findings have not been acted on. The two most
load-bearing:

- **`order` is dead for execution, alive only for `/api/agents` listing** — but
  `backend/CLAUDE.md` and `.planning/IMPLEMENTATION-REGISTER.md` still describe the
  deleted membership assertion as active, misleading a reader into thinking `order`
  still governs execution. A docs fix, not a design decision, but urgent — nothing else
  in this file depends on resolving it first.
- **Step `tools:` (a `ToolPermissions` grant) and agent `tools:` (a tool-SET name) are a
  pure name collision**, not the same field read twice. `_resolve_runner_tools` reads
  only `spec.tools`; step `tools:` is authored in 5 non-product `sample_*` manifests and
  read only by the fanout/exec/MCP privilege checks. Anyone reading a workflow's `tools:`
  key would reasonably assume it affects tool binding — it does not. (`SPEC012-ADR-10`
  above fixes the Composer-facing symptom of a related but distinct problem — the grants
  being unenforceable — without touching this naming collision.)

The remaining four (delete the dead `context_from` field, delete the dead `max_tokens`
field from `AGENT.md`, move `gate` into the manifest as an overridable step-level
default, rename step `tools:` to `permissions:`) are recorded in
`reports/agent-vs-workflow-config.md`'s "Ranked: what to move, what to delete" section
and have not been picked up.

## A metadata note, not a decision gap

The global `.knowledge/cards/ADR-0005.md` (`SPEC012-ADR-04` above) does not list
`reports/dynamic-loader.md` in its own `derived_from` frontmatter — only
`.knowledge/INVARIANTS.md#SC-001`. The report is clearly the direct evidentiary source
(its "four test-fixture manifests become visible, two ISS-015 assertions must move"
language is close to verbatim in both), so this reads as an omission in the card's
frontmatter rather than a real discrepancy in what was decided. Not fixed here — editing
a canonical `.knowledge/cards/` file's frontmatter is outside this document's scope — but
worth someone correcting directly on that card.
