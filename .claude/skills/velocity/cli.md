# velocity — tool surface

## Named commands

Every command lives HERE and nowhere else. Sub-skills refer to these names;
they never spell out a `python3 tools/...` line of their own. One command,
one definition — so a change to an invocation is a one-line edit here rather
than a hunt through seven files that will inevitably miss one.

| name | command |
|---|---|
| **the status command** | `python3 tools/knowledge/status.py` |
| **the status command (JSON)** | `python3 tools/knowledge/status.py --json` |
| **the full rebuild** | `python3 tools/knowledge/rebuild_knowledge.py` |
| **the cards-only rebuild** | `python3 tools/knowledge/rebuild_knowledge.py --skip-architecture` |
| **the rebuild dry-run** | `python3 tools/knowledge/rebuild_knowledge.py --check` |
| **the sync-point stamp** | `python3 tools/knowledge/rebuild_knowledge.py --skip-architecture --set-sync-point` — rebuilds cards-only AND moves `state.yaml`'s `last_sync_commit`/`last_sync_date` to HEAD. Only `sync` may run this, and only after actually reconciling the commit delta (steps 2-7 of `sync.md`) — running it bare re-baselines the watermark with no review, silently dropping whatever came before from every future sync window. |
| **the ID linter** | `python3 tools/knowledge/normalize_card_ids.py --check` |
| **the ID migration** | `python3 tools/knowledge/normalize_card_ids.py` |
| **the architecture rebuild** | `python3 tools/knowledge/build_architecture.py` (`--only MOD-<id>` to scope) |
| **the summary applier** | `python3 tools/knowledge/apply_summaries.py` (`--check` to preview) |
| **the link validator** | `python3 tools/knowledge/validate_links.py` |

If a sub-skill names a command you cannot find above, that is a bug in the
sub-skill — say so rather than inventing an invocation.


The single reference for every script under `tools/`. Sub-skills link here
instead of carrying their own copies of invocations, so a command only ever
has to be corrected in one place.

**You run these, not the user.** When a sub-skill's procedure reaches a
regeneration step, run it yourself and report what changed. Never hand the
user a command to paste — the point of `/velocity` is that they talk to the
skill and the skill handles the tooling.

## Before you rebuild: check

```sh
python3 tools/knowledge/status.py          # ~0.5s, read-only, ~15 lines
python3 tools/knowledge/status.py --json   # same data, machine-readable
```

Counts cards, architecture cards, INDEX entries, source-file coverage, sync
distance from HEAD, and ID-scheme conformance. Reads no card bodies and runs
no extractors, so it is safe to call freely. Exit 0 = current, 1 = something
stale. Prefer this over guessing whether a rebuild is needed -- and over
counting files yourself, which costs far more tokens than running it.

## The one command

Everything derived is rebuilt, in dependency order, by:

```sh
python3 tools/knowledge/rebuild_knowledge.py
```

```
architecture ──► index ──► context ──► validate
```

The order is load-bearing: `build_context` reads `modules.json` and the
`## Purpose` sections `build_architecture` writes, and `build_index` counts
the architecture cards. It fails fast — a stage that errors stops the run and
no LATER stage executes.

**Fail-fast is not atomic, and the difference matters.** Each stage writes as
it completes, so a stage-2 failure leaves stage 1's output already on disk. A
crash in `index` after `architecture` succeeded leaves 36 rewritten
`MOD-*.md` plus `modules.json`, while `INDEX.md`, `state.yaml` and
`CONTEXT.md` still describe the previous state. There is no rollback.

So when a stage fails: report WHICH stage, and treat everything before it as
already applied. Re-run the whole command after fixing the cause — the stages
are idempotent, so repeating completed work is free and re-converges the
tree. Never report a failed rebuild as "nothing was written".

| flag | when |
|---|---|
| *(none)* | source **or** cards changed — the safe default |
| `--skip-architecture` | only cards changed; skips the ~1-2 min source scan |
| `--check` | runs `architecture --check` and `validate`; **skips `index` and `context` entirely** — they have no dry-run mode, so it cannot tell you whether they would succeed |

Prefer this over calling the stages individually. Reach for a single stage
only when scoping a change (e.g. `--only` on one module).

## The stages

| script | reads | writes | notes |
|---|---|---|---|
| `build_architecture.py` | `backend/**/*.py`, `frontend/src/**` | `architecture/MOD-*.md`, `modules.json` | shells out to pydeps + dependency-cruiser; slowest stage |
| `build_index.py` | `.knowledge/cards/` | `INDEX.md`, `state.yaml` | fast; run after any card write |
| `build_context.py` | cards + `modules.json` + `MOD-*.md` | `CONTEXT.md` | the priming pack |
| `validate_links.py` | all of `.knowledge/` | *nothing* | read-only; checks markdown links AND every `## Related` cross-ref (id resolves + target file exists); exits non-zero on either |

`build_architecture.py --only MOD-<id>` restricts which `MOD-*.md` files are
rewritten (`modules.json` is always regenerated in full). Use it when another
agent may be editing the hand-authored prose in other module cards.

## Card-writing helpers

| script | purpose |
|---|---|
| `apply_summaries.py` | applies agent-drafted `{id: summary}` batches from `.knowledge/.stage/summaries/*.json` to cards. Touches only the `compact_summary:` line; every other key, key order, and the body are preserved byte-for-byte. `--check` to preview. |
| `normalize_card_ids.py` | enforces the `{TYPE_CODE}[-{SUBTYPE}]-{rest}` ID scheme. `--check` is a **linter** — run it to catch any card whose prefix does not match its type. Applying is a migration; re-running is a no-op. |

## What rebuild can and cannot touch

Rebuild **never deletes**. No stage calls `unlink`, `rmtree`, or `rename`.

| | |
|---|---|
| **Never written** | `.planning/**`, `backend/`, `frontend/` |
| **Rewritten (derived)** | `INDEX.md`, `state.yaml`, `CONTEXT.md`, `modules.json`, the section BELOW the divider in `MOD-*.md`, and the `## Related` block at the foot of each card |
| **Preserved verbatim** | everything ABOVE the `---` divider in `MOD-*.md` |

Three guarantees protect the hand-authored module prose, which is the only
irreplaceable thing rebuild goes near:

- A `MOD-*.md` whose frontmatter will not parse is **skipped, not
  rewritten**, and the run exits non-zero telling you which file. Nothing is
  overwritten. Fix the frontmatter by hand and re-run.
- A `MOD-*.md` with no `---` divider is treated as entirely hand-written and
  kept in full. The placeholder (`## Purpose … not yet authored`) is only
  ever used for a file that does not exist or is empty.
- A `MOD-*.md` with no live module behind it (root dropped from
  `MODULE_ROOTS`, package deleted) is reported as an **orphan and left on
  disk**. Deleting it is a human decision.

Cards are inputs with ONE generated exception: the `## Related` block, which
sits in the body directly under the frontmatter between `<!-- RELATED -->` and
`<!-- /RELATED -->`. `build_index.py` re-renders what is BETWEEN those markers;
everything outside them is yours and is never touched. A card with no
resolvable refs has the block removed rather than left stale.

**The block is the source of the graph, not a copy of it.** The card ids in it
are read back and preserved — the rebuild never invents or drops one. What it
refreshes is the link TARGETS, which embed filenames carrying a datetime: rename
a card and every link to it would otherwise be silently wrong. So edit the block
to change the graph, and let the rebuild fix the paths. **Author the full
markdown link form** (`[FIX-034](20260704-1815-FIX-034.md)`), not a bare id —
one link pattern, everywhere a card references another, not just here.

## Rules that keep this safe

- **Never hand-edit a derived artifact.** `INDEX.md`, `state.yaml`,
  `CONTEXT.md`, `modules.json`, and everything below the
  `<!-- AUTO-GENERATED BELOW THIS LINE -->` marker in `MOD-*.md` are outputs.
  Edit the cards or the source, then regenerate.
- **Above the `---` divider in `MOD-*.md` is yours.** The `## Purpose` /
  `## Shape` / `## Why this shape` prose is hand-authored and preserved
  verbatim across every rebuild. That is where module analysis belongs.
- **Every script is idempotent.** Re-running changes nothing if nothing
  changed, so when in doubt, re-run.
- **`--check` before a bulk apply.** `apply_summaries.py` and
  `normalize_card_ids.py` both support it.
- **A failed extractor aborts.** `build_architecture.py` refuses to write
  empty dependency sections over good data if pydeps or dependency-cruiser
  fails. Report the failure; do not work around it by skipping the stage.
- **No git.** These scripts never run `git commit` / `git add` / `git push`
  or any branch operation, and neither do you. Regenerated files are left
  uncommitted for the user to review and commit.

## Which sub-skill runs what

| sub-skill | typical call |
|---|---|
| `status.md` | `python3 tools/knowledge/status.py` — read-only, never regenerates |
| `sync.md` | `python3 tools/knowledge/rebuild_knowledge.py` (source may have moved), then **the sync-point stamp** as its true final action |
| `prime.md` | **the status command** first; if stale, hands off to `sync.md` and/or `diagrams.md` in full (see their own procedures) before its own `rebuild_knowledge.py --skip-architecture`, then read `CONTEXT.md` |
| `diagrams.md` | `python3 tools/knowledge/build_architecture.py --affected` / `--stale-prose` to find work, one Haiku subagent per affected card to re-author it, then `build_architecture.py` + `--stamp` per card |
| `book-keeping.md` | after writing a card: `python3 tools/knowledge/rebuild_knowledge.py --skip-architecture` |
| `analyze.md` / `fix.md` | no tool call of their own — they consume `INDEX.md` / `CONTEXT.md`. **Not read-only end to end**: `analyze.md`'s final step hands off to `book-keeping`, which writes a card and then runs `rebuild_knowledge.py --skip-architecture`. |

If a card write also changed module structure (new package, moved file), drop
the `--skip-architecture`.
