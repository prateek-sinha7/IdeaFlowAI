# Slotting Optimisation Workbench — Granite Peak Distribution

## Pages

### Slot Grid
Lists 20 pick slots. Columns: slot code (aisle-bay-level, e.g. A-07-2), SKU,
on-hand, daily picks, fill %. Filterable by aisle and by a "below reorder
point" toggle. SKU text search narrows rows as you type.

| slot | sku | on_hand | daily_picks | fill_pct |
| --- | --- | --- | --- | --- |
| A-07-2 | GPD-4417 | 84 | 31 | 62 |
| A-07-3 | GPD-2260 | 12 | 44 | 18 |
| B-01-1 | GPD-8891 | 240 | 9 | 91 |

### SKU Detail
Reached at #/sku/:id from any Slot Grid row. Shows the SKU velocity history
table, its current slot, and a "Queue move" action which selects a suggested
better slot. Queuing a move adds a row to Moves and flags the source row on
the Slot Grid.

### Replenishment
Slots below reorder point, with case quantities and suggested top-up.

### Velocity Report
Top-10 movers, derived from the same rows the Slot Grid renders — no separate
data source, so the two can never disagree.

### Moves
Queued moves from SKU Detail: SKU, from slot, to slot, status.

### Settings
Reorder point threshold, aisle list, case-quantity defaults.

## Data model
Slot { code, sku, on_hand, daily_picks, fill_pct, reorder_point }
Sku  { id, description, case_qty, velocity_history[] }
Move { sku, from_slot, to_slot, status }

## Interactions
Clicking a Slot Grid row routes to #/sku/:id. Queue move writes a Move and
marks the source slot. The Velocity Report recomputes from the slot list on
every render so it always agrees with the grid.

## Content rules
Every table renders at least 5 rows of domain-realistic data — real-looking SKU
codes (GPD-4417), aisle codes in A-07-2 form, case quantities that divide the
on-hand figures. No "Widget 10000", no Lorem ipsum, no empty states on first
paint.

## Edge cases
A slot with zero on-hand still renders, flagged below reorder point. A SKU with
no velocity history shows the empty table with its header intact rather than
collapsing. Queuing a move for a SKU that already has a queued move replaces
the existing row rather than adding a duplicate.

## Design notes
Six pages share one chrome: left nav listing the six destinations, a header
carrying the page title, and a single content column. Tables use consistent
column ordering — identifier first, then quantities, then derived percentages.
Dates are rendered as fixed strings, not computed at load, so the prototype
reads identically on every open.
