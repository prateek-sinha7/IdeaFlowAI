<tasks>

## Task 1: Shell, routing and nav
Build the app shell with a hash router. One `<section data-page>` per page and
one routes-map entry per section: slot-grid, sku-detail, replenishment,
velocity-report, moves, settings. Nav links use `href="#/path"`.

## Task 2: Slot Grid
Table of 20 pick slots: slot code, SKU, on-hand, daily picks, fill %. Aisle
filter, below-reorder toggle, SKU search.

## Task 3: SKU Detail at #/sku/:id
Velocity history table, current slot, Queue move action.

## Task 4: Replenishment
SKUs below reorder point with shortfall and suggested quantity.

## Task 5: Velocity Report
Top-10 ranking computed from the Slot Grid rows, not a second data source.

## Task 6: Moves
Queued moves with source slot, target slot, status, complete and cancel.

## Task 7: Settings
Reorder thresholds, slot capacity, aisle codes.

</tasks>
