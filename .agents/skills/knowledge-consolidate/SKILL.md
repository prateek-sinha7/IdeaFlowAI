---
name: knowledge-consolidate
description: "Review recent fix cards and propose ADRs for the rules they established. Use per phase, monthly, or after a cluster of related fixes. Proposals go to the user for approval — this skill never accepts a decision on its own."
argument-hint: "[area or ID range]"
allowed-tools:
  - Read
  - Write
  - Bash
  - Grep
---

# Knowledge Consolidate

## Objective

Turn repeated history into a stated rule. A fix records *what happened once*; a
decision records *what now holds*. Without this step `RULES.md` slowly stops
describing the system, and the cards decay into an archive nobody loads.

This is the episodic → semantic step, and it is **the one loop that must not run
unattended**. Every proposal goes to the user.

## Workflow

### 1. Gather the candidates

```bash
python3 scripts/knowledge/ctx.py --rules            # what is already covered
python3 scripts/knowledge/ctx.py --type fix "<area>"
```

Read the candidate cards' bodies. Not their summaries — the rule is usually in the
root-cause reasoning, not the symptom.

### 2. Apply the test

Promote a fix to a decision only if **all** of these hold:

1. It constrains *future* work, not just this one occurrence.
2. Someone could plausibly do the opposite tomorrow.
3. It has a real cost — the `accepting …` clause is not empty.
4. `RULES.md` does not already say it.

Roughly **one fix in five** passes. Forcing the rest is actively harmful: a rules
file padded with non-rules is a rules file nobody reads.

Strong signals: two or more fixes with the same root cause; a fix whose body says
"this mirrors how X already works"; a "deleted — do not resurrect" note in a phase
shard.

### 3. Draft the ADR

Follow `.knowledge/schema.md`. The header carries a **Y-statement**:

> In the context of **\<use case\>**, facing **\<concern\>**, we decided
> **\<option\>**, to achieve **\<quality\>**, accepting **\<downside\>**.

Body is MADR 4.0: Context and Problem Statement · Considered Options · Decision
Outcome · Consequences · Confirmation.

Two rules that carry most of the value:

- **`accepting` is mandatory.** A decision with no stated cost is a description, and
  gives the reader no way to know when the trade-off stopped being worth it.
- **Confirmation must be honest.** Name the test that would fail if the rule were
  violated. If none exists, **say that plainly** — a stated coverage gap is useful;
  a claimed test that does not exist is a lie the next reader will act on.

Set `status: proposed`, link `derived_from:` to the evidence cards, and add
`produces: [ADR-nnnn]` to those cards via `.knowledge/overrides.json` so the link
survives re-extraction.

### 4. Hand over

Present each proposal as: the rule in one sentence, the cards it came from, and the
cost being accepted. Ask the user to accept, reject, or reword.

Only the user moves a decision to `status: accepted`. Then:

```bash
python3 scripts/knowledge/build_index.py
```

## Never

- Never write `status: accepted` yourself.
- Never invent a rationale the evidence does not support. If the fixes do not say
  *why*, the honest output is "these three fixes share a cause but no stated rule —
  worth a decision, needs a human".
- Never supersede an existing ADR silently. Set `supersedes:` on the new card and
  `status: superseded` on the old one, in the same change.
