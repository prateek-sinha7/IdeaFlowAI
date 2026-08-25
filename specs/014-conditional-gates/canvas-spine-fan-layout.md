# Canvas layout: the spine-and-fan formula

One formula for every canvas shape. Not a per-case fix. If a new shape renders
wrong, the formula is wrong or misapplied — do not special-case the shape.

## The principle

**SPINE** — a straight line the main chain runs along. Today it is HORIZONTAL
(left → right); depth increases along it. The spine axis is the *major* axis.

**FAN** — everything a branch opens up is distributed PERPENDICULAR to the
spine (so today: vertically), symmetric about the branching node.

A vertical spine is the same formula with the axes swapped. Nothing below
depends on which axis is major, so the transpose must stay a one-line change.

```
        spine (major axis) ───────────────────────────────►
                                        ┌── m0 ──┐
  brief ── n1 ── n2 ── GATE ────────────┤── m1 ──┤  fan (minor axis)
                                        └── m2 ──┘   symmetric about GATE
```

## Use the standard algorithm — do not invent one

**The root graph is a DAG with back-edges, NOT a tree.** A node can have two
parents (`refactor` is reached from `depth`'s `deep` outcome AND from
`verify`'s `fail` loop), and back-edges exist by design (R-06/R-07 loops).
Tree layout cannot express that.

An earlier draft of this file said to apply Reingold–Tilford (the tidy-**tree**
algorithm in `treeLayout.ts`) to the root graph. **That was wrong** and is
corrected here. Reingold–Tilford remains correct for the SUB-AGENT tree, which
really is a tree — leave `treeLayout.ts` alone for that job.

The established pattern for a layered DAG is the **Sugiyama framework** (1981)
— what Graphviz `dot`, Dagre and ELK all implement. Its four phases map one to
one onto the defects seen here:

| Phase | Standard technique | Fixes |
|---|---|---|
| 1. Cycle removal | temporarily reverse back-edges | loop targets (`verify → refactor`) |
| 2. Layer assignment | longest-path / network simplex | columns assigned by ARRAY INDEX instead of graph depth |
| 3. Crossing reduction | barycenter / median, a few sweeps | long diagonal edges crossing the canvas |
| 4. Coordinate assignment | **Brandes–Köpf** (2002) | fans not centred on their gate; uneven pitch |

Plus **dummy nodes**: an edge spanning more than one layer is split by a chain
of invisible nodes, one per intermediate layer. This is what keeps long edges
straight and routed instead of cutting diagonally across the drawing.

### No new dependency

This codebase deliberately avoids layout libraries — `treeLayout.ts:5-7`
("reimplemented by hand so the canvas stays dependency-free") and
`specs/015-frontend-routing/plan.md:43` ("prefers hand-rolled solutions over
pulling in libraries where avoidable"). Honour that: implement Sugiyama by
hand.

Hand-rolled does NOT mean invented. Implement the NAMED phases above, keep the
phase boundaries visible in the code, and cite the algorithm in comments so the
next engineer recognises it instead of re-deriving it. Simplifications are fine
where justified in a comment — e.g. longest-path layering instead of network
simplex, median heuristic with 2–4 sweeps instead of optimal crossing
minimisation.

Sections 3–4 below describe the fan geometry within one layer. They remain
valid as the *within-layer* rule, and are the simple case of phase 4.

## The formula

### 1. Depth (major axis) — Sugiyama phase 2

`col(n)` = **topological rank**: `col(n) = 1 + max(col(p))` over all incoming
edges `p → n`, after back-edges have been reversed (phase 1). `col(brief) = 0`.

This is longest-path layering. It is NOT the node's index in the steps array —
using array index is a real defect seen here: `done-simple` and `depth` are both
at graph depth 3 but were placed in columns 3 and 4, so two sibling branches
marched rightward in sequence instead of running in parallel.

`x(col)` = cumulative, per-column: `x(0) = START_X`, and
`x(c+1) = x(c) + max(NODE_W + NODE_GAP, halfExtent(c) + halfExtent(c+1) + NODE_GAP)`.

### 2. Members of a fan

For a gate `g`, its fan members, in declared outcome order, are:
- each **forward** step target (`order(target) > order(g)`), and
- each **external workflow** node (`trigger: "workflow"`), height
  `EXTERNAL_NODE_H`.

**Excluded:** backward/loop targets (already placed earlier on the spine —
including one would drag it out of position), and any node already claimed by
another gate's fan.

A non-gate node's successor is a fan of exactly one member — the linear case
falls out of the same code path, it is not a separate branch.

### 3. Breadth ORDER within a layer — Sugiyama phase 3

Decides which SLOT each node takes in its layer. A permutation only — no
coordinates yet.

**Barycenter / median heuristic.** Sweep down the layers then up, repeatedly
(2–4 sweeps is plenty):

```
for each node n in layer L:
    key(n) = median( position(p) for p in neighbours(n) in the adjacent layer )
sort layer L by key(n)      # ties keep previous relative order → determinism (I7)
```

Include dummy nodes (§3b) in the sort — that is what stops long edges from
crossing the fans.

Seed the first pass with declared outcome order so a gate's outcomes start in
authored order and only move to remove crossings (satisfies I6).

**Cousins do NOT need subtree-extent reservation.** An earlier draft of this
file specified a bottom-up `extent()` recursion; that is a TREE technique and
is retracted. In a layered DAG two cousins are simply two nodes in the same
layer — ordering plus the §4 separation constraint keeps them apart, and
nesting depth needs no special handling.

### 3b. Dummy nodes

Any edge spanning more than one layer is split into a chain of invisible nodes,
one per intermediate layer. They participate in ordering (§3) and in separation
(§4), then are dropped — their coordinates become the edge's bend points. This
is what keeps a long edge straight and routed instead of slashing diagonally
across the drawing.

### 4. Breadth COORDINATE — Sugiyama phase 4

Decides where each slot actually sits. Use **Brandes–Köpf** (2002), the linear
time standard (Dagre uses it):

1. Four passes: {topmost, bottommost} alignment × {leftmost, rightmost} bias.
2. In each pass align every node with its **median neighbour**, forming blocks
   of vertically-aligned nodes (this is what straightens long edges).
3. Compact each block subject to the separation constraint below.
4. Average the four candidate coordinates per node → balance and symmetry.

**Separation constraint (size-aware).** Classic Sugiyama assumes uniform node
sizes; ours are not (a 176px step card beside a 58px external node), so
separation between layer-adjacent `u` and `v` is:

```
sep(u, v) = (h(u) + h(v)) / 2 + ROW_GAP
```

A gate's fan then comes out centred on the gate with even pitch, because the
gate IS the median neighbour of its outcome group — I3 and I4 fall out of the
algorithm rather than being enforced afterwards.

Simpler fallback, if Brandes–Köpf is too much for a first cut: Sugiyama's
original **priority method** (iterative median with priorities). Say so in a
comment if you use it — it is known to give less even results, which is roughly
the current symptom, so prefer Brandes–Köpf.

### 5. Normalise

After the whole graph is laid out, translate every node by
`−min(y) + PADDING` if any `y` would be negative. Coordinates are never
emitted negative or outside the content area.

## Invariants (the acceptance test)

Assert these over COMPUTED layout values for every shape below. `jsdom` has no
layout engine — `getBoundingClientRect()` is all zeros there, so assertions on
real pixel geometry are vacuous and must not be used.

- **I1 no overlap** — no two node boxes intersect, heights included.
- **I2 in bounds** — no negative `x`/`y`; nothing outside the content area.
- **I3 centred** — each fan's centre equals its gate's centre on the minor
  axis (±1px).
- **I4 even** — within one fan, consecutive `centre(i+1) − centre(i)` equals
  `(extent(i) + extent(i+1))/2 + GAP` exactly. Uniform members ⇒ uniform pitch.
- **I5 compact** — a fan's total extent equals the §4 formula. No slack from
  nudge loops.
- **I6 ordered** — fan members appear in declared outcome order along the
  minor axis.
- **I7 determinism** — same graph in ⇒ identical coordinates out. No
  iteration-order or Map-insertion dependence.

## Shapes that must all pass

| Shape | What it covers |
|---|---|
| linear chain | fan of one; degenerate case |
| A1 `ex_A1_loop` | backward/loop target excluded from the fan; predecessor keeps its chain edge and is not a leaf |
| A2 `ex_A2_branch` | 3 forward step targets, uniform height |
| A3 `ex_A3_divert` | mixed: 1 step target + 2 external nodes, unequal heights |
| A4 `ex_A4_human_gate` | 3 targets + two gates on one step |
| workflow-only gate | every outcome is `trigger: workflow`; no step target to anchor the column |
| **nested branch** | a branch target that is itself a gate — §3 recursion |
| **deep nest** | branch → branch → branch; cousin subtrees must not collide |

## Anti-patterns — do not do these

- **No iterative nudge-until-no-collision.** It produced a 733px gap next to a
  174px one and pushed a node to `y = −88`, off-canvas.
- **No per-shape branches** (`if (allWorkflowOutcomes) …`). One formula.
- **No mixing units.** A row *index* is not a row *offset*; a prior bug
  compared the two with `Set.has`.
- **No asserting row indices differ** as a proxy for "no overlap". Different
  rows still collide when heights differ — that is how a broken canvas shipped
  with a green test.
- **Do not pre-seed every node with a default row** and then guard fan
  membership on "does it already have a position" — that guard is then always
  false and step targets silently never join the fan.

## Auto-arrange

Auto-arrange = run this formula. Because the formula is the DEFAULT layout, an
opened workflow is already arranged with no click and no flash-then-rearrange.
The Auto-arrange button recomputes it, discarding manual drag overrides. Normal
renders must NOT discard `dragOverrides`.
