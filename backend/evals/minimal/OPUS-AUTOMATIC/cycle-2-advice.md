# Cycle 2 — v3 → v4  ⚠️ WRITTEN AND ACTIVATED, NOT YET MEASURED

**Status: the prompts are done and `v4` is active. The run is blocked on expired
AWS credentials** (see `FINDINGS.md` → "Cycle 2 blocker"). Everything below is the
change; nothing below has a score against it yet.

Source of advice: the cycle-1 panel findings on `260803-191418-…-opusjudge`.

## The theme: cycle 1 over-corrected, cycle 2 subtracts

Cycle 1 added 160 lines across five prompts and produced +12.1 mean — but with two
regressions, both caused by the additions themselves. Cycle 2's main move is
**removal and bounding**, not more rules. Net: build −23 lines, and every addition
elsewhere replaces rather than appends.

## Applied

### build — the three cycle-1 sections cut 62 lines → 18

`data_realism 11`, `page_completeness 0`, and the panel's *"zero `<table>`, zero
`<tbody>`, not one render function"*. Build spent its budget on CSS, seed data and
the router and never reached rendering. The rules were right — both deterministic
route checks passed — but they were three times too long, on the stage nearest its
output ceiling.

Merged into one section, `THREE THINGS THAT SILENTLY EMPTY A PAGE`, one paragraph
each: seed-satisfies-predicate, parameterised route resolves on first segment,
runtime class names need rules.

### build — an explicit emission order for one-shot mode

The eval always takes build's one-shot fallback branch, which previously said only
"build a complete prototype covering ALL pages". Now it states the order the
budget is spent in, and what to sacrifice:

1. shell + `:root` + only the CSS actually used
2. seed data **written literally** — no `Math.random()`, no index arithmetic
3. **for each page: write its render function AND call it, before the next page**
4. router and nav

with the ranking rule made explicit: *"A page is not built until a function writes
its content into the DOM and that function is called… a prototype with four
complete pages and two missing is worth far more than seven empty ones."*

This targets the exact failure: seven shells instead of four real pages.

### plan — rule 4 rewritten, escape hatch closed; new rule 4a bounds the dataset

Cycle 1's rule 4 offered "write every row **or** state the generation rule". The
plan took option two and specified *"Seed 47 permits, 100+ inspections"* with no
values — `task_self_containment` fell 17 → **4**, worse than baseline. Build then
honoured it with `Math.random() * 1400000` and `` `${9+(i%8)}:${(i%2)*30}0 AM` ``,
emitting `"10:300 AM"`.

- **4** — writing the records out literally is now the *only* legal form.
- **4a** — choose a set you can write: 10–15 records, not 47. "Never specify a
  count you are not going to enumerate."

### specify — rules 4 and 5 under `ONE PLACE PER FIGURE`

`spec_consistency_completeness` moved only 7 → 11; the Fees stat cards were still
mutually irreconcilable, and the spec still declared 47 permits while listing 8
plus *"[+39 more permits with realistic addresses …]"*.

- **4 — a summary card is specified as a derivation, never as a number.** Cycle 1
  said "refer to the figure by name", which fights the format: a stat card looks
  like it wants a value. Writing "Card — Pending Fees: sum of `fee` where
  `collected = false` in the Fees table" and stopping makes contradiction
  impossible rather than discouraged. Applies to every stat card, KPI tile, count
  badge and total row.
- **5 — same 10–15 record bound as plan**, applied one stage earlier, where the
  inflation originates.

### specify — navigation rule 00: the page set comes from the brief

The spec invented a seventh page (a staff directory) the brief never names, and
the plan then built a task for it. On a stage that is budget-bound, an unasked-for
page is paid for by the pages that were asked for.

### validate — port build's add-a-token rule

Colour literals went 7 → 20, all status badge pairs written by hand
(`#721c24` on `#f8d7da`, `#856404` on `#fff3cd`). validate had only the passive
`- [ ] No raw hex colors outside :root` — it says what not to do and offers
nowhere to go. Build's cause-level instruction is now in validate too: if the
shade has no token, define `--<state>` and `--<state>-surface` in `:root` and use
them.

This regression only appeared *because* the validate fix worked — the stage could
not write bad colours while it was writing nothing.

## Deliberately unchanged

- **validate's `STEP 1 — WRITE THE AUDIT` rule.** Largest clean effect of cycle 1
  (`defect_repair_delta` 0 → 92). Untouched so cycle 2 re-measures it.
- **analyze — no change at all.** +17.0, no blocking findings, `defect_detection`
  16 → 44. Nothing in the cycle-1 findings justified spending budget here.

## Rejected

1. **Accessibility undecided** (major, specify, both cycles). Real and general, but
   still an *addition* to the stage with the most lines, whose failing dimension is
   `spec_consistency_completeness` 11, not `design_system_coherence` 70. Deferred
   again — and if it is never affordable, that is itself worth recording.
2. **"Task 5's calendar highlights dates that do not exist in the month"** (minor).
   Domain-shaped; the general form is already covered by the literal-seed rule.
3. **"Three isolated tasks define the same global handler names"** (minor). Real,
   but plan's isolation contract item 1 already covers shared-mechanism naming; by
   `ADVISE.md` §2 a rule that exists and did not land is not fixed by restating it,
   and I have no cause-level rewrite for it yet.

## Line-count delta

| stage | v3 | v4 | delta |
|---|---|---|---|
| specify | 256 | 273 | +17 |
| plan | 237 | 242 | +5 |
| analyze | 159 | 159 | **0** |
| build | 263 | **240** | **−23** |
| validate | 194 | 200 | +6 |

Frontmatter verified byte-identical v3 → v4 for all five, plus a
`frontmatter.load()` parse check. Activated with `./activate.sh prototype v4`.
