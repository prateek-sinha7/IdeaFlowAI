---
name: knowledge-index
description: "Regenerate INDEX.md, RULES.md and the .cache/ link graph from the cards in .knowledge/. Use after adding, editing or deleting any card, or when check.py reports the index is stale. Pure script, no LLM, runs in about a second."
allowed-tools:
  - Read
  - Bash
---

# Knowledge Index

## Objective

The index is a **pure function of the card frontmatter**. It is generated, never
hand-written — which is the only reason it can be trusted. A hand-maintained index
drifts, and a drifted index is worse than none, because agents believe it.

## Workflow

```bash
python3 scripts/knowledge/build_index.py
python3 scripts/knowledge/check.py
```

That regenerates four artifacts and nothing else:

| Artifact | What it is |
|---|---|
| `.knowledge/INDEX.md` | one line per card — the session prime |
| `.knowledge/RULES.md` | decisions in force, grouped by area |
| `.knowledge/.cache/index.json` | structured mirror, read by `ctx.py` |
| `.knowledge/.cache/links.json` | file→cards, card→cards, backlinks |
| `.knowledge/.cache/stamp.json` | freshness key: frontmatter hash + counts |

Report the printed token estimate. **If the prime exceeds ~15 K tokens, stop and
say so** — past that, the always-loaded tier is no longer cheap and summaries need
tightening rather than the budget being quietly raised.

## Failure modes, and what they mean

`build_index.py` refuses to write on any of these, by design:

- **duplicate card ids** — two cards claim the same id; one must be suffixed
- **filename does not start with its id** — `--show` would resolve to the wrong file
- **missing `summary:` / `y:`** — a card with no index line is invisible, so it is
  treated as an error rather than silently omitted
- **unparseable frontmatter** — the dialect is deliberately small (see
  `.knowledge/schema.md`); it fails loudly rather than mis-parsing

Fix the card. Never work around it by editing the generated files — they are
overwritten on the next run.

## Never

- Never hand-edit `INDEX.md` or `RULES.md`. Edit the card, re-run.
- Never commit `.cache/` — it is derived and already git-ignored.
