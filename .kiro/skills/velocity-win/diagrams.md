# velocity diagrams

Re-author the DOMAIN architecture cards whose code has moved, and re-inline
their diagrams into `ARCHITECTURE.md`.

This is the **manual fallback** for the `knowledge-domains` pre-commit hook.
That hook does exactly this automatically, but it never blocks a commit — if
the `claude` CLI is missing from its PATH, times out, or the change touches too
many cards at once, it prints the affected cards and hands the work here.

You are the model the hook could not reach. Do the same work it would have.

## When this runs

- The hook said `refresh skipped: the claude CLI is not on PATH`
- The hook said `over the --max-refresh limit`
- The hook reported a `FAILED` or `TIMEOUT` card
- Someone edited a domain's code and wants the docs caught up now

## Arguments

`/velocity diagrams [CARD…]` — zero or more domain card names, exactly as the
hook printed them:

```
/velocity diagrams DOMAIN-agent-runtime DOMAIN-hitl-gating
```

**With card names** — work on those cards only. This is the normal case: the
hook has already computed the affected set and is handing it to you. Still run
step 1 to recover *which files* changed under each card, because the prompt
needs that list.

**With no arguments** — discover the set yourself in step 1.

A name may be given bare (`DOMAIN-agent-runtime`), with the extension, or as a
full path. Resolve it under `.knowledge/architecture/`. If a name matches no
card, say so and stop rather than guessing at a near-match — a typo that
silently re-authors the wrong card is worse than an error.

## Procedure

**1. Find what changed.** Never guess — ask the tool.

```
python tools/knowledge/build_architecture.py --affected
```

With no arguments it reads the staged changeset (`git diff --name-only
--cached`). Pass paths explicitly to check a specific set. It prints each
affected `DOMAIN-*.md` with the files that touched it, and exits 1 when
anything is affected.

This is where you get `{{CHANGED_FILES}}` for step 2 — the files listed under
each card. If you were given card names but this reports nothing (the change is
already committed, so nothing is staged), widen it:

```
python tools/knowledge/build_architecture.py --affected $(git diff --name-only HEAD~1)
```

If you still cannot recover a changed-file list, author the card from scratch
instead — pass `(none — first authoring)` as `{{CHANGED_FILES}}` and the prompt
switches modes. Do not invent a file list.

Also check what is already known-stale:

```
python tools/knowledge/build_architecture.py --stale-prose
```

A card is stale when its `prose_signature` differs from its `code_signature`.
The signature covers the card's `members:` globs **plus every file its prose
names** — so a card is answerable for files it merely passes through.

**2. Re-author each affected card — one Haiku subagent per card.** Per your
standing delegation rule, this is mechanical, well-specified, single-file work
— dispatch it rather than doing it inline. For every card the previous step
named, spawn a fresh Haiku subagent (`model: "haiku"`) with a prompt that
tells it to:

- Read `.kiro/skills/velocity-win/prompts/architecture-domain-update.md` itself,
  from disk, and follow it exactly. That file is the authority and it ships
  with this skill — the `knowledge-domains` pre-commit hook feeds the very
  same file to headless Claude, so this is the manual path through one
  procedure, not a second implementation of it. It must read it fresh, not
  work from anything paraphrased in the dispatch prompt, because it changes.
- Substitute its two placeholders itself: `{{CARD}}` (the card's repo-relative
  path, which you supply) and `{{CHANGED_FILES}}` (the files `--affected`
  listed under that card, one per line, which you also supply).
- Respect the prompt's incremental mode: when `{{CHANGED_FILES}}` names files,
  **fix only the claims those changes invalidate**, leave the rest of the
  prose alone. A card is hand-authored analysis, and rewriting a paragraph
  nothing invalidated is how a good one becomes a worse one.

One subagent, one card — never batch multiple cards into one dispatch. Each
card has its own changed-file list, and merging them produces prose that
describes the wrong domain's changes. Independent cards (no shared file in
their changed-file lists) may be dispatched in parallel, in one message with
multiple Agent calls; a card whose changed-file list overlaps another's should
be dispatched after, not concurrently with, the one it overlaps.

Review each subagent's diff before moving on to step 3 — a Haiku rewrite that
invents a claim the changed files don't support, or drifts outside the
incremental-mode scope, needs a re-dispatch with a corrected prompt, not a
silent pass-through.

**3. Rebuild.** This recomputes each card's `code_signature` from its NEW prose
and re-inlines every `## Shape` diagram into `ARCHITECTURE.md`:

```
python tools/knowledge/build_architecture.py
```

Only the `## Shape` diagram is lifted into `ARCHITECTURE.md`. The
`## In practice` sequence diagram stays in the card — that is deliberate, so
the overview stays readable beside thirteen siblings.

**4. Stamp each card you re-authored.**

```
python tools/knowledge/build_architecture.py --stamp .knowledge/architecture/DOMAIN-<name>.md
```

This sets `prose_signature = code_signature`. **Stamp only what you actually
revised.** Stamping an untouched card marks stale analysis as current and
defeats the entire mechanism.

You cannot stamp during authoring, and this is not an ordering quirk: the
signature hashes the files the prose names, so it does not exist until after
the prose is written and the rebuild has run.

**5. Verify before reporting done.**

```
python tools/knowledge/build_architecture.py --stale-prose   # expect 0 stale
python tools/knowledge/validate_links.py                     # expect 0 broken
```

`--stale-prose` also lists module cards as "never authored". That is normal and
not a backlog — `MOD-*.md` cards are the generated folder map and carry no
diagrams by design.

## Report

Say which cards you re-authored, which changed files drove each one, and what
you changed versus what you deliberately left. If a card's `members:` looks
wrong — a file the prose leans on that is not a member — say so and leave the
frontmatter alone. Membership is the user's call.

## Rules

- **Never edit `members:`.** Declared by hand; not yours to change.
- **Never hand-edit `ARCHITECTURE.md`'s diagram gallery.** It is regenerated
  between `<!-- DOMAIN-DIAGRAMS -->` markers and your edit will be overwritten.
- **Never add a diagram to a `MOD-*.md`.** Diagrams live in DOMAIN cards and
  `ARCHITECTURE.md` only.
- **Never touch anything between** `<!-- AUTO-GENERATED BELOW THIS LINE` and
  `<!-- /AUTO-GENERATED -->`.
- Nothing here runs git. The user handles commits themselves.
