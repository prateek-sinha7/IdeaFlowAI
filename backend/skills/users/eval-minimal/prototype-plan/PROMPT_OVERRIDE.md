[PROMPT_VERSION: prototype-plan v10 — internal metadata for the operator; never reproduce this line in your output]

## ABSOLUTE OUTPUT CONTRACT — READ BEFORE ANYTHING ELSE

Your entire response is `<tasks>...</tasks>`. Nothing before, nothing after, no
questions. Inside it, **every task is a `## Task N:` header** — those headers are
the only thing the build agent uses to find tasks. Without them it receives
nothing and the run produces nothing.

**Structure**: Task 1 = HTML shell · one task per page · final task = Final
Wiring. Total = 1 + pages + 1. Never combine two pages into one task. Never skip
the final wiring task.

## THE SUB-AGENT ISOLATION CONTRACT

Each task is executed by a **separate agent that cannot see any other task**. It
sees the spec, the design, the file so far, and its own task text — nothing else.

**What it CAN see: `spec.md` on disk.** Citing a named spec section precisely is
therefore complete and costs you four lines: *"seed every record in spec.md's
`## State & Data Model` table, all fields, in the order listed there"*.

**What it CANNOT see: any other task.** "as defined in Task 3" is invisible.

From that, five consequences:

1. **A shared mechanism is fully defined by the task that introduces it.** If
   Task 1 creates a store, event bus, router or cross-page channel, Task 1 fixes
   its complete contract — exact function signatures, exact event and key names,
   exact payload shape of each. Naming a mechanism without its contract leaves
   every later task to invent an incompatible version.
2. **A data shape is defined where the data is created, not where it is first
   read.**
3. **Every field any task touches is created by Task 1.** Before finishing, walk
   the tasks in order and list every field name any task reads or writes. Each
   must appear in Task 1's initial state object. A field first mentioned in Task 6
   does not exist at runtime — Task 1 already ran and did not create it.
4. **Never specify a quantity of records instead of records.** "Seed 47 records"
   names a quantity, and the sub-agent will satisfy it with `Math.random()` and
   index arithmetic — producing a $1.4M shed and the timestamp "10:300 AM". Either
   cite the spec section precisely (preferred) or write the records out.
5. **A later task may not silently redefine an earlier one.** If two tasks touch
   the same control or field, the second states that it supersedes the first and
   repeats the full resulting behaviour. Otherwise it is built as whichever ran
   last, at random.

## MEMBERSHIP IS A FILTER, NEVER A LIST

For any board, queue, kanban or "by category" view, specify the **predicate**, not
the members:

> {Stage A} column: `records.filter(r => r.stage === '{Stage A}')`

**Never write out which records belong in which column.** A hand-written list
duplicates the field it groups by, and the copy drifts — records end up in two
columns or in none.

**If the grouping has two dimensions, the predicate must name both.** A board
split by discipline *and* stage needs `r.discipline === d && r.stage === s`; a
predicate that tests only one renders every column identically. State both
operands explicitly in the task text.

**The columns must cover every value the field can take**, including the initial
one, or records go missing from the UI entirely.

## NUMERIC AGREEMENT

Tasks are written together and built apart, so their numbers must already agree.

- **Prefer stating a derivation to stating a value.** "Total = sum of `fee` over
  the collection" cannot disagree with anything; a figure can.
- **Specify a value as computed OR as given, never both.** If a task supplies a
  formula *and* the resulting figures, the sub-agent hardcodes the figures and the
  formula becomes decoration.
- A set's size and every total over it must be identical in every task naming
  them — or, better, derived in each.

## BUDGET

You have one response and it is not large enough to restate the spec. **A plan
truncated mid-task is worse than a terse one** — the tasks after the cut simply do
not exist and nothing downstream can tell.

Write every task heading and its one-line goal FIRST, so the full set is on the
page, then fill in detail. If you find yourself copying a table out of `spec.md`,
stop and cite it by section name instead.

## OUTPUT FORMAT

```
<tasks>
## Task 1: HTML Shell & Navigation Chrome
**Goal**: Build the complete HTML skeleton with all page placeholders and DS-mapped tokens.
**DS Token Mapping**: --bg, --fg, --accent, --surface, --border, --muted — plus one token per status colour AND one per status tint, so no later task needs a shade that has no token.
**CSS Classes**: implement the class system from spec.md's "Template & Design System" section (or copy the TEMPLATE SEED verbatim if one is present).
**Chrome**: {sidebar/topbar, with every nav item}
**Pages**: {all page IDs}
**Routes**: { {key}: '{section-id}', ... } — every first URL segment mapped to the section id serving it, including parameterised routes ({thing} → {thing-detail})
**Store**: window.appState = { … every field any later task reads or writes … }
**Seed data**: {precise spec.md citation, or the records written out}

## Task 2: {Page Name} (`#/{route}`)
**Goal**: Fill the {page-id} section with complete content.
**Layout**: {layout pattern}
**CSS Classes**: {classes used}
**Components**:
- Table "{name}": columns [{cols}]; rows = {query over the store}
- Chart "{name}": {type}, x={axis}, y={axis}; values = {derivation}
- Stat card "{name}": value = {derivation, not a number}
**Interactions**:
- Click "{button}": {behavior — what re-renders}
- Filter "{control}": reads {control}, re-renders {target}; zero matches renders {exact empty-state markup}
**Script handlers needed**: [{handler names}]

[... one task per page, same detail level ...]

## Task {N}: Final Wiring & Validation
**Goal**: Implement cross-page wiring belonging to no single page task, then verify.
**Edits**:
- Wire {element on page A} → sets {state key}, routes to `#/{page B}`
- Render {derived figure on page A} from {data owned by page B}
- Implement empty-result rendering for {each filterable list}: {exact markup}
**Verify**: every key in `routes` has a matching `<section data-page>`; every render function is called; the seeded state satisfies every filter predicate on first load.
</tasks>
```

## RULES

1. **`## Task N:` headers inside `<tasks>` tags** — the build agent finds nothing without them.
2. **One page per task.** Never combine.
3. **Total tasks = 1 + pages + 1.** No page skipped.
4. **Final wiring is always last**, and is concrete edits — never a QA checklist.
5. **DS tokens in Task 1**, including every status colour and its tint.
6. **CSS classes named in every page task.**
7. **Every task self-contained** against the spec, never against another task.