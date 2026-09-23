# velocity: legacy registers (backward compatibility — DELETABLE)

**This file is temporary scaffolding.** It exists so the `/velocity` skills keep
working while the old `.planning/` register system is still live. Everything the
skills know about that system lives here and nowhere else.

## Cutting over — how to delete this

When the registers are retired, do exactly this and nothing more:

```sh
rm skills/velocity/legacy-registrars.md
rm -rf .planning/
```

**No other skill file needs editing.** Every reference to this file elsewhere is
written as a self-cancelling conditional — "if `legacy-registrars.md` exists,
follow it" — so deleting the file turns those instructions off on their own.

Before cutting over, check the one real dependency: some cards are stubs whose
narrative exists only in the registers. Run the stub check in §4 and backfill
those card bodies first, or that history is lost.

---

## 1. What the legacy system is

> **Fallback only, and say when you use it.** `.knowledge/` is the source of
> truth; `.planning/` is a frozen archive kept for history the cards do not
> carry. Check the cards first. Never write here. And whenever an answer
> draws on `.planning/`, tell the user explicitly — name the file and say the
> knowledge base did not have it. See `SKILL.md` § `.planning/` is a
> read-only fallback.

Five append-only markdown registers under `.planning/`, maintained by hand
before the card store existed:

| Register | Holds |
|---|---|
| `.planning/FIX-REGISTER.md` | one summary row per `FIX-NNN` — description, root cause, files, test counts |
| `.planning/FIX-TEST-REGISTER.md` | `TEST-NNN` rows keyed to a Fix ID, plus detail |
| `.planning/ISSUES-REGISTER.md` | `ISS-NNN` — defects found but NOT fixed; append-only |
| `.planning/IMPLEMENTATION-REGISTER.md` | one pointer-first entry per shipped phase / quick task |
| `.planning/STATE.md` | Quick Tasks Completed rows + the `Last activity:` line |

`.planning/` is the ONLY copy. `.knowledge/docs/` used to mirror it and was
deleted — duplicating a frozen archive into the knowledge base bought nothing
and gave every fact two homes that could disagree. Refer to `.planning/`
directly until the cut-over retires it.

## 2. Reading — consult a register only when the card store comes up short

The card store is authoritative. Go to the registers **only** when:

- a card exists but its body is a stub with no root cause (many `PH-*`,
  `PHASE-*` and `QUICK-*` cards are pointers, and some `FIX-*` cards — e.g.
  `FIX-217` — are a bare title), **or**
- an ID is referenced somewhere but has no card at all.

Then:

```sh
grep -n "<ID>" .planning/*.md          # registers are large — always grep, never read whole
grep -rn "<ID>" .planning/phases/ .planning/quick/
```

Per-phase and per-task narrative lives in `.planning/phases/<phase>/` and
`.planning/quick/<id>/*-SUMMARY.md`.

**Never bulk-read a register.** `IMPLEMENTATION-REGISTER.md` is 1.2 MB and
`FIX-REGISTER.md` is 724 KB — either will bury your context. Grep with context.

## 3. ID allocation — the one thing the registers still contribute

**Nothing here writes.** The registers are a frozen archive: no rows are
appended, no IDs are allocated into them, no `Last activity:` line is touched.
This section adds READ sources to `book-keeping.md` Step 1 and nothing else.
Where anything appears to conflict, `SKILL.md` § `.planning/` is a read-only
fallback wins — this file never overrides it.

### 3a. ID allocation gains two more read sources

`book-keeping.md` Step 1 takes the max across the card store and git history.
**Also** grep the registers, because an ID can be recorded in a register and
nowhere else. These are `grep`s — reads, not writes:

```sh
grep -oE "FIX-[0-9]+" .planning/FIX-REGISTER.md    | sed 's/FIX-//' | sort -n | tail -1
grep -oE "ISS-[0-9]+" .planning/ISSUES-REGISTER.md | sed 's/ISS-//' | sort -n | tail -1
grep -oE "ISS-[0-9]+" .planning/FIX-REGISTER.md    | sed 's/ISS-//' | sort -n | tail -1
grep -oE "TEST-[0-9]+" .planning/FIX-TEST-REGISTER.md | sed 's/TEST-//' | sort -n | tail -1
```

Next ID = max across **all** sources (card store + both git passes + these), + 1.

Why this matters — it has been got wrong twice, in both directions:
- `FIX-214/215/216b` were live in dev commit messages while `FIX-REGISTER.md`
  topped out at 213. *(register lags git)*
- `ISS-050` was taken by an id that appeared only in a commit message, in
  neither the register nor the card store. A register-only lookup returned 049,
  so 050 was reissued for an unrelated defect and later renumbered to 064.
  *(no single source is sufficient)*

### 3b. No register row — the card IS the record

The registers used to gain a summary row per fix. They no longer do. Everything
that row held now lives in the card: the description, root cause, files, and
the Step 2 test-coverage block. Writing a row would fork the record into two
stores that immediately disagree, and the archived one is the one nobody
regenerates.

So: **do not append to `FIX-REGISTER.md`, `FIX-TEST-REGISTER.md`,
`ISSUES-REGISTER.md`, `IMPLEMENTATION-REGISTER.md`, or `STATE.md`** — not a
row, not a `Last activity:` bump, not an ID reservation.

**Deferred items are still bookkeeping** — but as a card. Anything
found-but-not-fixed gets its own `issue` card, per `book-keeping.md` Step 3. A
finding that lives only in a session transcript is a finding you will pay to
rediscover.

### 3c. Extra closing-gate row

Add exactly one line to `book-keeping.md` Step 5:

- [ ] ID allocated from the max including the register greps in §3a

## 4. Stub check — run before cutting over

Cards whose narrative exists only in a register will lose it when `.planning/`
is deleted. Find them:

```sh
# cards whose body is under ~200 chars after the frontmatter
python - <<'PY'
import pathlib, re
for p in sorted(pathlib.Path('.knowledge/cards').glob('*.md')):
    m = re.match(r'^---\n.*?\n---\n(.*)$', p.read_text(), re.S)
    body = (m.group(1) if m else '').strip()
    if len(body) < 200:
        print(len(body), p.name)
PY
```

As of 2026-08-16 that is ~15 cards, and every one was judged to carry real
content (an out-of-scope decision, a pointer). The larger exposure is the ~105
`PH-*` / `PHASE-*` / `QUICK-*` cards whose `compact_summary` was recovered from
`IMPLEMENTATION-REGISTER.md` and `.planning/quick/<id>/*-SUMMARY.md` — their
summaries survive in the cards, but their full narrative does not.

## 5. Stale facts in the legacy docs

The old protocol carried values that are wrong on this machine. Recorded here so
they die with this file:

| Claim in the legacy docs | Reality |
|---|---|
| `scripts/knowledge/*.py` (`extract.py`, `check.py`, `ctx.py`) | Does not exist. Tracked in git, deleted from the working tree. Use `tools/knowledge/build_index.py`. |
| `.knowledge/surface/INDEX.md` | Does not exist. The index is `.knowledge/INDEX.md`. |
| Migration head `0026` | `0030` |
| Playwright live on `:8002` | backend runs on `:8010` |
