---
auto-approve-staged-changes: false
---

# velocity: sync

Reconcile `.knowledge/` with commits that landed since the last sync. Flip
`auto-approve-staged-changes: true` above to skip the approval prompt in step
6 and apply all staged proposals automatically.

Preconditions: `.knowledge/state.yaml` exists and has `last_sync_commit`.

Leaves behind: proposal files in `.knowledge/.stage/` (consumed by step 7),
updated cards/architecture, a regenerated `INDEX.md`, an updated
`state.yaml`.

## Procedure

1. Read `.knowledge/state.yaml`. Extract `last_sync_commit` and
   `last_sync_date`. If `last_sync_commit` is missing or empty, stop and tell
   the user sync has never run — recommend running `prime` after a manual
   review instead of guessing a starting point.

   Then confirm the commit actually EXISTS in this checkout before using it:

   ```sh
   git cat-file -e <last_sync_commit>^{commit} 2>/dev/null && echo resolves || echo MISSING
   ```

   A recorded commit can be absent from a perfectly healthy repo — a squashed
   or rebased branch, a shallow clone, or a fresh worktree all do this. If it
   reports MISSING, STOP and tell the user: name the commit, say it is not in
   this checkout's history, and ask whether to re-baseline from HEAD. Do not
   proceed to step 2 — `git log <missing>..HEAD` fails with a bare
   `fatal: Invalid revision range` that explains none of this, and do not
   silently substitute a different starting point, which would skip real
   history and produce a sync that looks successful while missing commits.

   **If the user says re-baseline:** run **the full rebuild** (`cli.md`). It
   resets `last_sync_commit` to HEAD and regenerates every derived artifact,
   which is the only recovery path — with no resolvable starting commit there
   is no delta to mine, so steps 2-6 have nothing to work from. Say plainly in
   your report that **no proposals were generated and no history was
   reviewed**: the baseline moved to HEAD, so any card- or architecture-worthy
   change between the old commit and HEAD falls outside every future sync
   window. Recommend a manual review of that range if it matters. Then stop —
   do not continue to step 2.

2. Compute the delta since `last_sync_commit`:
   - `git log --name-status <last_sync_commit>..HEAD` for all changed source
     files (added/modified/deleted), plus the full commit messages in that
     range.
   - Separately list knowledge files touched since the sync point, in case
     they were hand-edited outside this skill:

     ```sh
     git log --name-only --pretty=format: <last_sync_commit>..HEAD \
       -- .knowledge/cards .knowledge/architecture | sort -u
     ```

     Use git history, **not** file mtime. `find -newermt` looks equivalent and
     is not: a fresh clone or worktree stamps every file with the checkout
     time, so it reports the whole tree as hand-edited. That happened once and
     cost a review pass chasing dozens of phantom edits.

3. For each changed source file (excluding files under `.knowledge/`):
   - Look up its owning module in `.knowledge/architecture/modules.json`
     (match by path/glob).
   - Decide whether that module's `MOD-*.md` architecture card is now
     stale: files added or removed from the module, import edges changed,
     or the hand-authored `## Purpose` / `## Shape` no longer describes what
     the code does. Read the current card body to compare — do not assume
     staleness from the diff alone.
   - If stale, prepare a proposed edit to the card (see step 5).
   - If a source file maps to no known module, note it as an "unmapped
     file" in the summary — do not silently invent a new module.

4. Mine the commit messages in the delta for anything worth recording as a
   card. A proposal may ONLY be one of the four live types — `fix`, `bug`,
   `issue`, `adr`. Use commit body text and the referenced files as evidence.
   Skip trivial commits (formatting, typo fixes, dependency bumps) unless the
   message itself flags significance.

   **Never propose a `requirement`, `phase` or `doc` card, and never import a
   `.planning/` artifact as one.** Those types are retired: every card that
   carried them was a generated stub whose body only pointed into `.planning/`,
   and all 482 were deleted. Re-creating one from a commit message rebuilds the
   exact problem — a card that forwards instead of answering. A phase or quick
   task worth recording becomes a normal `fix` card, written by hand, carrying
   its own content.

5. Write every proposed change as one file per proposal in
   `.knowledge/.stage/`, named `{NNN}-{short-slug}.md`. Each proposal file
   must contain:
   - A header: what changes (new card / card edit / architecture edit),
     which file it targets (existing path, or the new path to be created),
     and why (cite the commit(s) or diff that justified it).
   - For a new card: the full proposed card body (frontmatter + content).
   - For an edit: a full before/after — the exact current text being
     replaced and the exact replacement text, not a prose description of
     the change.

6. Present a numbered summary of all staged proposals to the user (one line
   each: target file, one-line description). Then:
   - If this file's frontmatter has `auto-approve-staged-changes: true`,
     apply all proposals without asking, and say explicitly "auto-approve
     is on — applying all N proposals without confirmation."
   - Otherwise, ASK the user which proposals to apply (all / a subset /
     none) and wait for their answer before touching `.knowledge/cards/`
     or `.knowledge/architecture/`.

7. For each approved proposal: apply it to the real target file under
   `.knowledge/cards/` or `.knowledge/architecture/` (architecture edits
   only touch content above the `---` divider — never touch the
   auto-generated section below it). Delete the proposal file from
   `.stage/` once applied. Then regenerate every derived artifact by RUNNING
   **the full rebuild** yourself — see `cli.md` in this
   directory for the full tool surface, flags, and failure modes.

   That one command covers `INDEX.md`, `state.yaml` (including
   `last_sync_commit` at current HEAD, `last_sync_date` and all counts),
   the architecture cards, `CONTEXT.md`, and a link validation pass. Never
   hand-write any of them — they are derived over ~469 cards and hand-edits
   are silently dropped on the next regeneration. Architecture regeneration
   only rewrites content BELOW each card's divider; the hand-authored
   sections above it are preserved.

8. Invoke `prime` (this skill family's `prime.md`) so `CONTEXT.md` reflects
   the new sync point.

## Hard rule

NEVER run `git commit`, `git add`, `git push`, or any branch operation
(`git checkout`, `git branch`, `git merge`, etc.) as part of this skill. The
user handles all git operations themselves. This skill only reads git
history with `git log`/`git diff` and writes files under `.knowledge/`.
