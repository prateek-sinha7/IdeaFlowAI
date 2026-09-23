# velocity status

Report what the knowledge base holds and what has drifted. Cheap by design:
one command, ~15 lines of output, no card bodies read, no codebase scan.

## Procedure

1. Run it. That is the whole scan — do not glob cards, count files, or read
   `state.yaml` yourself first: run **the status command** (`cli.md`).

2. **Lead with which tree you are reporting on.** The output's first two
   lines name the working tree, its branch, and any other checkouts of the
   same repo. Say that out loud before the numbers — do not drop it as
   noise. See "Two trees" below; this is the single most common source of
   confusion in this repo.

3. Relay the table as-is, then add one or two sentences of interpretation:
   what is stale, and whether it matters right now. Do not restate every row
   in prose — the table already says it.

4. If anything is STALE, offer the fix the script names. Run it if the user
   says yes; do not run it unprompted, since `status` is a read-only verb and
   a rebuild takes ~1-2 min when the architecture stage is involved.

Exit code is 0 when everything is current and 1 when any check is stale, so
`status` doubles as a gate in a hook or CI step. `--json` emits the same data
machine-readably.

## What it checks

| row | means |
|---|---|
| `cards` | `.md` files in `cards/` vs the count `state.yaml` recorded |
| `architecture cards` | `MOD-*.md` on disk vs `state.yaml` |
| `source files covered` | files `modules.json` describes vs source files actually on disk — catches a stale architecture build |
| `INDEX.md entries` | index lines vs cards; drift means a card was added without regenerating |
| `CONTEXT.md commit` | the commit `CONTEXT.md` was built from vs HEAD |
| `commits since sync` | how far `last_sync_commit` trails HEAD |
| `source files changed` | `backend/`+`frontend/` churn since the sync point — if non-zero the architecture needs a full rebuild, not `--skip-architecture` |
| `ID scheme conformance` | cards whose ID prefix is a valid TYPE_CODE (`FIX`/`BUG`/`ISS`/`ADR`) |
| `staged proposals` | files sitting in `.stage/` awaiting approval — reported as PENDING, never STALE, since staged work is deliberate |

## Two trees

This repo is checked out more than once — a main checkout and one or more
git worktrees under `.claude/worktrees/`, each on a different branch, each
with its own `.knowledge/`. They have **separate card stores, separate
`state.yaml`, separate everything**.

That means two sessions can both be correct and still report different
numbers. Without saying which tree produced them, the difference reads as
data corruption, and the user reasonably concludes the tooling has gone
haywire. It has not — they are two different knowledge bases.

So:

- Always name the tree and branch before the numbers. `status.py` prints
  both, and lists the other checkouts under a `NOTE:` line.
- When the user reports output that does not match what you see, **check the
  tree first**, before investigating drift. `git worktree list` shows every
  checkout and its branch.
- Never present a number from one tree as though it described another. If
  you are comparing trees, label every figure with its tree.
- `tools/knowledge/status.py` reports the tree it LIVES in, not the shell's cwd. The
  worktree's copy always describes the worktree, even if invoked from
  elsewhere.

## Reading the result

- **`source files covered` stale, everything else OK** — someone changed code
  without re-running the architecture stage. Use **the full rebuild**.
- **`cards` / `INDEX.md entries` stale** — a card was written by hand without
  regenerating. `--skip-architecture` is enough.
- **`ID scheme conformance` stale** — cards exist whose prefix does not match
  their type. Run **the ID linter** to list them;
  applying it is a migration, so confirm with the user first.
- **`staged proposals` PENDING** — `.stage/` has unapplied proposals. That is
  `sync`'s job, not `status`'s. Mention it; do not apply them here.

## Hard rule

`status` never writes. It does not regenerate, does not apply staged
proposals, and does not run git beyond `rev-parse` / `rev-list` / `diff
--name-only`. If a fix is needed, name it and let the user choose.

See `cli.md` in this directory for the full tool surface.
