# Prompt — author or refresh a module architecture card

You are updating ONE architecture card in a Velocity knowledge base. The card is
already on disk with its machine-generated section filled in. Your job is the
part no script can produce: the prose that explains what this module is for and
why it is built the way it is.

Substitute the caller's values for `{{CARD}}` (repo-relative path to the
`MOD-*.md`) and `{{SIGNATURE}}` (the `code_signature` value the caller read off
that card) before running.

---

## Read first

1. `{{CARD}}` — in full. The frontmatter gives you `path`, `file_count`, and
   `code_signature`. The block between `<!-- AUTO-GENERATED BELOW THIS LINE`
   and `<!-- /AUTO-GENERATED -->` is the authoritative file list, module
   dependency edges and external packages. **Trust it. Do not restate it.**
2. Every source file the card lists that plausibly carries the module's
   design — entry points, anything named for a role (`*_runner`, `*_factory`,
   `registry`, `engine`), and whatever the other files import most. For a
   large module read the top 10–15 by that judgement, not all of them.
3. If a `## Purpose` / `## Shape` / `## Why this shape` already exists on the
   card, read it as the prior author's claim. You are revising it against the
   code as it stands now, not starting from a blank page.

## Write

Replace everything BELOW the `<!-- /AUTO-GENERATED -->` line with exactly three
sections, in this order. Touch nothing above that line — the frontmatter and the
generated block are owned by `tools/knowledge/build_architecture.py` and any edit
you make there is overwritten on the next run.

### `## Purpose`

Two short paragraphs, maximum. What this module is responsible for, in terms of
the role it plays for its callers. Name the two or three files that carry that
responsibility. A reader who knows nothing about the module should be able to
decide from this alone whether it is the one they need.

### `## Shape`

How the module is put together internally. Lead with the single load-bearing
structural fact — the funnel every call passes through, the registry everything
resolves against, the one-way dependency. State it in bold, then show it.

Then a bulleted breakdown, one bullet per structural role (not one per file).
Group files that serve the same role into one bullet. Each bullet names the
file(s) and says what that role does and what it guarantees.

If the module warrants a diagram, put it directly under the opening statement —
see `architecture-diagram-update.md` for when it warrants one and how to draw it.

### `## Why this shape`

The reasoning a maintainer needs before they change something. Every paragraph
answers "why is it this way and not the obvious alternative". Prefer the
concrete: an invariant with its ID, a CI gate that enforces the rule, a design
that was tried and removed, a constraint from a dependency. If you cannot find
a real reason for a structural choice, say what the choice is and that the
reason is not recorded in the code — do NOT invent a rationale.

## Then stamp it

Set `prose_signature: {{SIGNATURE}}` in the card's frontmatter, immediately
after the `code_signature` line, replacing any existing `prose_signature`.

This is the whole point of the exercise: the stamp records which version of the
code your prose actually describes. `build_architecture.py --stale-prose`
compares it against the live `code_signature` and flags the card the moment
they diverge. Stamping without genuinely revising the prose defeats the
mechanism — it silently marks stale analysis as current.

## Rules

- **Reference by name, plainly.** Write `` `model_factory.build_model` `` or
  `chat_runner.py` as bare text. `build_architecture.py` converts every file,
  module-id, `module.Symbol` and card-id reference into a working relative link
  on the next run. Do not write markdown links yourself — hand-written links
  break when a card is renamed, and the generator's do not.
- **Symbol names must be real.** Every function, class or method you name must
  exist in the source right now. This prompt exists because a rename left the
  old name sitting in the prose; do not add new instances of that.
- **Never restate the generated block.** No file listings, no dependency
  listings, no external-package listings. They are directly above your text.
- **No invented history.** "Was refactored in Phase 7b" is a claim. Make it only
  if a card, a comment or a test says so; otherwise describe what is there.
- **Length follows substance.** A 2-file type-definitions module gets three
  sentences per section and no diagram. A 115-file kernel earns the full
  treatment. Padding a thin module to look thorough makes the corpus worse.
- **Do not touch any other file.** One card per run.
