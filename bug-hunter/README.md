# bug-hunter/

Everything the autonomous bug hunt writes lives here. Nothing else writes to this folder, and
the hunt writes nowhere else — no application source, no test files, no `.knowledge/` cards.

Agents: `.claude/agents/bug-tracker-orchestrator.md` (scheduler, Opus) and
`.claude/agents/page-bug-hunter.md` (one page, one bug, Sonnet).

## Layout

```
bug-hunter/
├── README.md              this file — the contract
├── bug_tracker.docx       the original design document
├── known-bugs.md          THE LEDGER — append-only, one section per bug
├── known-bugs.lock/       mkdir-based write lock (transient; absent when idle)
├── hunt-state.md          orchestrator's per-page state, survives a resume
├── reports/
│   └── <UTC>-hunt-report.md      one per completed or stopped hunt
└── evidence/
    └── <page-slug>/               one folder per page, e.g. settings-profile
        ├── <BUG-ID>/              one folder per FILED bug
        │   ├── 01-before.png
        │   ├── 02-failure.png
        │   ├── 03-<detail>.png    optional further states
        │   ├── console.log        optional — only when it carries the diagnosis
        │   ├── network.log        optional — failed/unexpected requests only
        │   └── notes.md           optional — longer repro detail
        └── _scratch/              disposable exploration shots; safe to delete
```

## Rules

- **`known-bugs.md` is the single source of truth.** One file, append-only. Workers read it
  whole before touching the browser and re-read it under the lock before appending. Never
  overwrite it, never split it, never rewrite an existing entry.
- **A bug folder is created only when a bug is actually filed.** `<BUG-ID>` matches the ledger
  section heading exactly, so a ledger entry and its evidence are one lookup apart.
- **Screenshots are ordinal-prefixed** (`01-`, `02-`, …) so they sort in reproduction order.
  Slug the rest: `01-before.png`, `02-failure.png`, `03-after-reload-still-broken.png`.
- **`_scratch/` is disposable.** Exploration shots land there; the ones that prove a bug get
  moved into its `<BUG-ID>/` folder. A round that finds nothing may leave scratch behind — it is
  safe to delete at any time and nothing may depend on it persisting.
- **Logs are excerpts, not dumps.** `console.log` / `network.log` carry only the lines that help
  reproduce or diagnose. Never paste a full console transcript.
- **`known-bugs.lock/` is a directory**, acquired with `mkdir` and released with `rmdir`. If it
  is present, a worker is mid-write — wait, do not delete it.
- **Page slugs are the route with slashes flattened**: `/settings/profile` → `settings-profile`,
  `/runs/<id>/steps` → `runs-id-steps`, `/` never appears (bare `/` is not a page here).

## Ledger entry shape

```markdown
## BUG-<UTC timestamp>-<page-slug> — <short title>

- **Page:** <page name>
- **Route:** <route or URL>
- **Severity:** Critical | High | Medium | Low
- **Status:** Open
- **Found at:** <UTC timestamp>
- **Found by:** <worker identifier, e.g. bug-settings-profile-r7>
- **Fingerprint:** `<route>|<component>|<trigger>|<symptom>`
- **Evidence:** `bug-hunter/evidence/<page-slug>/<BUG-ID>/`

### Summary
### Reproduction
### Expected
### Actual
### Evidence
### Browser Signals
```

`Status` stays `Open` — the hunt observes and documents, it does not fix. Closing a bug is a
human decision made later.
