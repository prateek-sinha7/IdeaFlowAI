# Cycle 1 — v2 → v3

Source of advice: the opus sub-agent panel's findings on the baseline run
`260803-182408-…-opusjudge` (§4b of `ADVISE.md` — judge findings carry severity
and per-dimension grouping, which the pooled `advices.json` does not).

The pooled advice file was **not** used as a ranking signal: all 149 entries carry
`count: 1`, so it offers no recurrence information (`ADVISE.md` §1). Every rule
below is justified by a panel finding verified against the artifact.

## The design thesis for this cycle

The artifact producer is `claude-haiku-4-5` with **thinking off**, emitting a
whole document in one pass. It has no scratchpad. So every rule this cycle either

- **fires at the moment of the decision** (substitute the value and evaluate it on
  the line you are writing), or
- **makes the output itself the scratchpad** (write the addition down; write the
  audit before you edit).

Rules phrased as goals to hold across a document were the ones that did not land
in v1→v2, so none were added in that form.

## Applied

### specify — `ONE PLACE PER FIGURE` (replaces `DECISION-RECORD RULE`)

The v2 rule "never emit two candidate values for one field" **did not land** — the
spec shipped three Fees card sets. Restating it was not an option (`ADVISE.md`
§5). Cause: the model writes figures while computing and cannot retract an
earlier paragraph. Structural fix — make a second statement impossible:

- every figure has exactly one owning section, the one listing its items;
- everywhere else refers to it **by name, never by value**;
- the addition is written out in the owning section before the result is stated.

Also handles the `$8,188,000` vs `$8,148,000` arithmetic error at source.

### specify — navigation rules `0`, `0a`, `0b`

- **0** exactly one entry point (baseline marked five of six pages "Yes").
- **0a** every state machine declares its terminal state's action (baseline left
  the action at the final stage undefined).
- **0b** a parameterised route names the page id it resolves to — the upstream
  half of the build blocking defect.

### plan — isolation contract items `4`, `5`, `6`

- **4 no deferral to another document.** `(… 9 more rows as specified in spec)` is
  the direct cause of `task_self_containment 17`. Two legal forms only: write
  every row, or state the generation rule completely.
- **5 every field any task reads is created by Task 1.** Baseline wrote to
  `appState.inspections`, which Task 1 never created.
- **6 a later task may not silently redefine an earlier one.** Baseline had Task 8
  overwriting Task 6's fee semantics.

### analyze — rules `2`, `2a`, `2b` under the evidence rule

`defect_detection 16`: the stage missed that the valuations sum to `$8,148,000`,
not the `$8,188,000` asserted three times. v2 already said "recompute every
number" — it did not land, because a non-thinking model cannot add a column in its
head. Cause-level fix: **the report is the working.**

- **2** write the addends on one line before the verdict; a total without its
  addends written is reported unchecked, not Clear.
- **2a** count by listing identifiers, never by estimating.
- **2b** test every range/band/enum for coverage in both directions.

### build — three new sections

- **`THE SEED MUST SATISFY ITS OWN PREDICATE`** — substitute the seed into the
  predicate and evaluate it in a comment on the line above. Targets blocking
  defect 1 at the moment of writing the condition.
- **`A ROUTE WITH A PARAMETER RESOLVES BY PAGE ID`** — split the fragment, first
  segment is the key, `routes` maps key → section id. Targets blocking defect 2,
  with the worked router as the shape to copy.
- **`EVERY RUNTIME-GENERATED CLASS NAME MUST HAVE A RULE`** — enumerate the values
  the field can take before interpolating a class name.

### validate — `STEP 1: WRITE THE AUDIT BEFORE YOU EDIT ANYTHING`

The single most important edit this cycle. `defect_repair_delta 0` came from a
prompt that was a **passive checklist** — boxes the agent reads, agrees with, and
does not execute. Replaced with a mandatory written enumeration produced *before*
the first edit: routes, seed-vs-predicate, sections, control/handler ratios,
runtime class names — each line ending `OK` or `BROKEN → …`, restated with final
status at the end. Plus the explicit backstop:

> Repairing zero defects is a valid outcome only when every line above reads `OK`.
> If your audit found defects and your diff is one attribute, you have not done
> this stage.

### validate — removed the domain-specific page recipes

Deleted 1 619 characters enumerating what to put on an "issues" / "traffic" /
"contributors" / "repositories" / "profile" page. Straight violation of
`ADVISE.md` §5 (no brief's nouns in a prompt that runs on every domain), and it
was budget spent teaching one domain's page shapes. Replaced with a rule to bind
to the prototype's own existing seed collections.

## Rejected

1. **"Field inspections are seeded for permits not yet issued"** (major, 2
   findings across specify and build). Real, but it is domain logic — the rule
   would have to name inspections and permits. The general form ("a dependent
   record may not exist for a parent that has not reached the state that creates
   it") is a plausible abstraction, but it is supported by **one brief**, and by
   `ADVISE.md` §5 that earns a rule only if the mechanism is obviously general. It
   is not obviously general; a scheduling app may legitimately pre-book. Dropped.
2. **"Settings introduces a fourth reviewer discipline outside the brief's
   three"** (minor ×2). Pure subject matter.
3. **"Permit numbering breaks its own date ordering at one row"** (minor). Same.
4. **Accessibility left undecided** (major, `design_system_coherence`). Real and
   general, but it is an *addition* of scope to a prompt already near its budget,
   and the stage's failing dimension this cycle is `spec_consistency_completeness`
   at 7, not `design_system_coherence` at 74. Deferred to a later cycle rather
   than spending budget now.
5. **"`.status-row` / `.setting-row` declared and never used"** (minor). Cosmetic;
   no user-visible cost.

## Unreachable

None this cycle — no applied finding targeted
`backend/agents/guardrails/html-prototype.md`.

## Harness observations (recorded, not fixed — `ADVISE.md` §0)

- `cli run` resolves its config path relative to `evals/minimal/`, so
  `evals/minimal/configs/x.yaml` fails with `FileNotFoundError` on a doubled path
  while `configs/x.yaml` works. Cosmetic but easy to trip over.
- The eval never injects `=== CURRENT TASK ===`, so build always takes its
  one-shot fallback branch (see `../RESEARCH_WHY_NO_IMPROVEMENT.md` §4). All build
  rules this cycle were written to hold in that branch.

## Line-count delta

| stage | v2 | v3 | delta |
|---|---|---|---|
| specify | 224 | 256 | +32 |
| plan | 219 | 237 | +18 |
| analyze | 140 | 159 | +19 |
| build | 201 | 263 | +62 |
| validate | 165 | 194 | +29 (net; +48 added, −19 domain recipes removed) |

Frontmatter verified byte-identical for all five (`diff` on the frontmatter block
plus a `frontmatter.load()` parse check). No brief noun introduced.

Activated with `./activate.sh prototype v3` — all five OVERRIDDEN.
