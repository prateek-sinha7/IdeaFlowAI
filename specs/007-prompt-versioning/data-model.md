# Data Model: Applying Advisor Prompt Edits

**No database entities. No schema. No migrations.** Prompts are files on disk and stay files.

What follows is the file and document model the two commands operate on.

---

## Entities

### 1. `AGENT.md` — the live prompt (existing, unchanged in shape)

```
backend/agents/prompts/<agent-id>/AGENT.md
```

Two parts, and the split is the whole safety story:

| Part | Content | May `apply-advice` change it? |
|---|---|---|
| **Frontmatter** — everything from the opening `---` through the closing `---` | The engine's contract: `id`, `name`, `role`, `pipeline_type`, `order`, `max_tokens`, `tools`, `guardrails`, `produces`, `consumes`, `gate`, `injects`, `model`, … | **Never.** Preserved byte-for-byte, treated as an opaque string |
| **Body** — everything after the closing `---` | The system-prompt prose | Yes — this is the only mutable surface |

### 2. `AGENT.vN.md` — an archived body (new)

```
backend/agents/prompts/<agent-id>/AGENT.v1.md
backend/agents/prompts/<agent-id>/AGENT.v2.md
```

- **Body only** — no frontmatter, so an archive can never drift from the contract.
- Written once, never modified. Removed only by `revert`.
- Invisible to the runtime: `loader.py:144` and `:201` both match the literal filename
  `AGENT.md`, so no scan, registry entry or DAG validation can see these.

### 3. `prompt_advice_<token>.json` — the advisor's structured output (new)

```
backend/evals/grading/.runs/<workflow>/<dataset-run-id>/reports/prompt_advice_<token>.json
```

A serialisation of the existing pydantic `PromptAdvice`
(`model/prompt_advisor.py:60-68`) — written alongside, not instead of, the existing
`prompt_advice_<token>.md`. Path owned by `artifacts.py`, as all run-folder paths are.

---

## Fields and Constraints

### `PromptEdit` (existing schema, `prompt_advisor.py:46-58`) — how each action is applied

| `action` | `current_text` | `proposed_text` | Applied as |
|---|---|---|---|
| `modify` | required, must match **exactly once** in the body | required | Replace the match with `proposed_text` |
| `remove` | required, must match **exactly once** | empty | Delete the match |
| `add` | empty | required | Insert after the anchor resolved from `section` (see below) |

**`section` anchor resolution for `add`** (plan AD-04), in order:

1. Exactly one markdown heading (`#`…`######`) whose text equals `section` trimmed → insert
   after that heading's content block.
2. Otherwise exactly one literal substring occurrence of `section` in the body → insert after
   the containing paragraph.
3. Otherwise → **fail the entire command** (exit 9). There is no end-of-file fallback.

### Constraints

| # | Constraint | Failure |
|---|---|---|
| C1 | `current_text` must occur **exactly once** — zero or ≥2 occurrences both fail | exit 9, naming the edit index and the count found |
| C2 | An edit whose `section` names a frontmatter field is refused; remaining edits still apply | exit 10 for that edit; command continues |
| C3 | Frontmatter bytes are identical before and after | Post-write assertion: prefix compares equal and still parses |
| C4 | All edits are computed in memory before any write; a single failure writes nothing | — |
| C5 | Archive number is `max(existing N) + 1`; gaps are never filled and numbers never reused | — |
| C6 | Archives are never overwritten | — |

## Relationships

```
run folder
  └── reports/prompt_advice_<token>.json   ──reads──►  apply-advice
                                                          │
                                                          ├── writes ► AGENT.vN.md   (old body, archived first)
                                                          └── writes ► AGENT.md      (new body, frontmatter preserved)

AGENT.vN.md (highest N)  ──reads──►  revert  ──writes──►  AGENT.md,  ──deletes──► AGENT.vN.md
```

Write order is fixed: **archive first, then `AGENT.md`** (plan AD-05), so an interruption
between the two leaves the previous body recoverable rather than lost.

## Migrations

**None.** Nothing to migrate — no database, no config format change, no existing file rewritten
on upgrade.

One back-compatibility case, handled at runtime rather than by migration: run folders graded
before the JSON sidecar existed contain only `prompt_advice_<token>.md`. `apply-advice` against
one of those exits 2 with a message naming `grade.sh advise <run-id>`, which re-advises an
existing run without re-dispatching agents.

The seven zero-byte `AGENT.v2.md` files currently on disk need no migration either — they are
untracked, empty, and were never read by anything. Under this model they would be *archives*
numbered 2. Design should decide whether to delete them or leave them; they are harmless either
way, but an empty archive would restore an empty prompt if reverted onto, so deleting them is
the safer default.

## Validation Rules

Applied by `prompt_edits.py` (pure) before any write:

1. The file contains a well-formed frontmatter block terminated by `---`; otherwise fail — do
   not guess that the whole file is body.
2. Every `modify`/`remove` edit satisfies C1.
3. Every `add` edit resolves its anchor unambiguously.
4. No edit targets a frontmatter field (C2).
5. The resulting body is non-empty (an empty prompt body is an `AgentSpecError` at load time —
   `loader.py` requires a non-empty body).
6. After writing: re-read `AGENT.md`, assert the frontmatter prefix is byte-identical to the one
   read, and assert `frontmatter.loads` still parses it.
