# Clarifications — 007-prompt-versioning

**Date**: 2026-07-30 (supersedes the first clarification round the same day)

The first draft of this spec built a prompt *version selection* system: pinned versions per run,
an `ab` command, changes to `loader.py`, `factory.py` and `AgentContext`. The developer's
direction was that this is more than the job needs — the actual requirement is **a way to
implement the changes the advisor suggests**, and how A/B runs happen is not part of it.

This round records the simpler design and what was dropped.

---

## C-01 — Where does the old prompt go? → **`AGENT.md` stays live; the old body is archived beside it**

| Option | |
|---|---|
| **A (chosen)** | **`AGENT.md` is always the live prompt. The old body is copied to the next free `AGENT.vN.md`.** |
| B | `AGENT.md` frozen for the engine; new prompts in `AGENT.vN.md`, selected by the eval |

**Decision**: **A**.

Option B would let you grade a prompt without changing what the engine runs, but it needs a
version-selection path through `loader.py` and `factory.py`, and it creates a state where the
engine and the eval are running different prompts — the drift is the point of the design, and
also its main hazard.

Option A needs **no runtime code at all**. `loader.load_agent_spec` opens `agent_dir /
"AGENT.md"` by exact name (`loader.py:144`) and `loader.list_agent_ids` — which builds
`PIPELINE_AGENTS` at import time (`registry.py:57-79`) — matches that filename exactly
(`loader.py:201`). Archive files are invisible to it. Nothing in the engine, kernel, registry,
resolver or manifests can observe this feature.

**Numbering**: first archive is `AGENT.v1.md`, next is `AGENT.v2.md`. Higher number = more
recent archive; `AGENT.md` is always newer than all of them.

---

## C-02 — Does the command edit `AGENT.md` straight away? → **Yes, and print the diff**

| Option | |
|---|---|
| **A (chosen)** | **One command: archive, apply, print the diff** |
| B | Write a draft file, apply it with a second command |

**Decision**: **A**. The archive *is* the safety net — the previous prompt is on disk before
`AGENT.md` is touched, and `revert` is one command. A draft step would add a command to every
iteration to protect against something already protected.

---

## C-03 — Which of the advisor's edits get applied? → **All of them**

| Option | |
|---|---|
| **A (chosen)** | **Apply every proposed edit** |
| B | Interactive picking from a list |
| C | Apply all, `--skip N` to exclude |

**Decision**: **A**. Simplest, non-interactive, scriptable. If the result is worse, revert costs
one command and nothing is lost.

Option C stays available as a later additive flag if one advisor suggestion in ten turns out to
be reliably wrong — but adding it before that pattern is observed is guessing.

---

## C-04 — Safety rules carried over from the first draft *(unchanged, and the reason the simple design is safe)*

These were the parts of the original spec worth keeping:

- **Frontmatter is never edited** (R-03/R-04). It is the engine's contract — `id`,
  `pipeline_type`, `order`, `produces`/`consumes`, `tools`, `gate`, `injects`, `model` — and a
  change there can break the registry, DAG validation, or the manifest/registry agreement the
  engine asserts at run entry. `apply-advice` edits only the body below the closing `---` and
  writes the frontmatter back byte-for-byte; an advisor edit targeting a frontmatter field is
  refused by name.
- **Exact-match-or-fail** (R-06). An edit whose `current_text` is absent or appears more than
  once fails the command and writes nothing. Fuzzy matching would put an edit in the wrong place
  silently, which is worse than a failed command.
- **Archives are body-only.** With no frontmatter, an archive cannot drift from the contract.

---

## C-05 — How do you tell whether the edit helped? → **Existing commands; nothing new**

The first draft proposed an `ab` command. Dropped. The grading package already has what is
needed and it was built for exactly this:

- runs already stamp `system_prompt_hash` per row (`artifacts.py:115`, `model_grader.py:795`)
- `grade.sh compare <a> <b>` already diffs two runs, with a noise guard that refuses to call a
  within-variance delta an improvement (`compare.py:41,93`)
- `grade.sh history <agent>` already groups runs by prompt (`compare.group_by_prompt`)

So Story 3 is: re-run the config, then `compare`. If a one-command wrapper around that proves
genuinely useful after the loop has been used for a while, it is additive and can be specified
then.

---

## C-06 — Git → **No git operations** *(carried over, unchanged)*

The commands write files. Committing is the developer's.

**Consequence, stated plainly**: prompt changes can still be swept into feature commits — the
entanglement noted in the first draft (11 revisions of `prototype-revision-agent/AGENT.md`, all
inside `KAN-*` commits) is not fixed by this spec. What partly substitutes is that graded runs
record `system_prompt_hash`, so a run's prompt is identifiable from its artifacts even when the
commit history is unhelpful.

---

## C-07 — The score still has to be worth acting on *(carried over)*

[008-grading-calibration](../008-grading-calibration/spec.md) documents that the harness
currently grades a hand-verified golden artifact at 80.0 while a run whose HTML the code track
rated 0 scored 89.5+, and names prompt work as downstream-unsound until fixed.

This does not block 007 — applying an advisor edit is a text operation that costs nothing and
is trivially reversible, and the advisor's *reasoning* is readable on its own merits. But
deciding that an applied edit **helped** depends on 008. Recorded so the numbers don't look
authoritative before they are.

---

## Dropped from the first draft

| Dropped | Why |
|---|---|
| Per-run version pinning (`AgentContext.prompt_versions`) | Not needed once `AGENT.md` is always live (C-01) |
| `loader.py` / `factory.py` changes, version-body cache | Same |
| `grade.sh ab` | `compare` + `history` already do this (C-05) |
| `grade.sh promote` | Nothing to promote — `apply-advice` writes the live file directly |
| `--repeats` default, arm-equality assertions on four hashes | Belonged to `ab` |
| `loader.clear_spec_cache()` | Was needed to hot-swap a pinned version mid-process; no longer relevant |
| Version `note` annotations, named variants, `prompts.lock.yaml` | All served version selection |
