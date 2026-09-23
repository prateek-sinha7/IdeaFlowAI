# Research — the three decisions open at spec time

**Spec**: [019-file-extract-support](spec.md) · resolved 2026-08-28, before planning
All three were measured on `.reference/Alliance/Inland Marine Creating a Quote 2.pdf`.

---

## R-01 — Image dedupe: **do not build it**

**Decision**: ship no dedupe beyond whatever falls out of writing each crop once per page.
Delete FR-005b and RISK-02 from the spec.

**Rationale — measured.** Grouping all 50 materialised crops by size and pricing them:

```
total image tokens on disk                          18,569  (50 files)
if EVERY repeat were perfectly deduped, saving         541
                                                    ------
                                                        2%  of image tokens
                                                      2.4%  of the 22,337 total
```

The Allianz logo — the thing dedupe was invented to remove — crops to 262×98, which is
**34 tokens**. Twenty-one of them is 714 tokens against a 22,337-token document. The
expensive images are the screenshots, and screenshots are unique by definition.

So the entire dedupe design was optimising a 2% line, and its correct implementation carried
a correctness bug: hashing the embedded stream (the only exact method) collapses **the same
screenshot bearing different annotations**, which is precisely the content this feature exists
to preserve. Paying a correctness risk for 2% is a bad trade in the direction that matters.

**Alternatives considered**

| Option | Verdict |
|---|---|
| Exact crop-pixel hash | Measured: caught 7 of ~20 logo repeats. Independent page renders anti-alias identical furniture at different sub-pixel offsets, so exact hashing structurally cannot work here |
| Embedded-stream hash | Exact and **wrong** — collapses the same screenshot with different arrows |
| Perceptual hash (dHash/aHash) | Robust to anti-aliasing, and equally robust to a small red arrow. Same correctness bug, fuzzier |
| Position-recurrence furniture detection (same bbox on ≥N pages ⇒ furniture) | Correct and cheap, and would have been the choice **if the saving justified any code**. It does not |
| **Build nothing** | **Selected.** 2% is below the threshold at which any of the above earns its maintenance |

**Revisit when**: a document is measured where repeated images are a double-digit share of
image tokens — e.g. a full-width banner on every page of a 400-page manual. The
position-recurrence option is the one to build then.

---

## R-02 — Is `.pdf/` visible in the Workspace tab?

**Decision**: **listed but not delivered** — the same asymmetry `.verify/` and `.browser/` use.

**Rationale.** Being able to open the folder and look at `text.md` beside `image-2.png` is
half of why this design was chosen over returning content from a tool. Hiding it from the
Workspace tab would discard that for no gain. It must still be excluded from
`is_deliverable_relpath`, because the extraction is scaffolding and the deliverable is
whatever the workflow produced.

`sandbox.py` already documents this exact pattern for `.agent_outputs/` — *"THIS PREFIX IS
THE ONLY ONE THAT IS LISTED BUT NOT DELIVERED, and that asymmetry is the whole point."*
`.pdf/` becomes the second, and that comment needs correcting when it does.

**Alternatives considered**: hidden entirely (loses the inspectability the design is built on);
delivered (ships megabytes of scaffolding into `WorkflowRun.output` — the trap spec 018 hit
with `.browser/`).

---

## R-03 — Parallelism: worker count and threshold

**Decision**: `ProcessPoolExecutor`, **4 workers**, engaged only above **~30 pages**, the whole
call wrapped in `asyncio.to_thread`. Both numbers are named constants, and both are recorded
as *conservative choices under measurement noise*, not as derived optima.

**Rationale — measured.**

```
21-page real document        100-page synthetic
  sequential  2.67s            sequential  6.96s   (69.6 ms/page)
  2 procs     1.03s  2.60x     4 procs     2.00s   3.48x
  4 procs     0.78s  3.44x
  8 procs     0.64s  4.20x
```

- **Never threads.** `pdfplumber` gains 0.99× (pure Python, GIL-bound) and `pypdfium2`
  rendering across threads **crashes the process** — exit 133, SIGTRAP, no traceback. PDFium
  is not thread-safe; in the backend that kills the worker and every concurrent run on it.
- **4, not 8.** Eight buys ~22% more speed for double the memory, and each worker holds its
  own PDFium state and page buffers. On a large scanned document that multiplier is the
  constraint, not CPU.
- **Threshold ~30, not 21.** Two runs of the same benchmark on the same document disagreed
  (2.15× and 3.44× at 4 workers), so the crossover cannot be located on this evidence. Setting
  the threshold above the measured document means this document runs sequentially in ~2.7s —
  correct behaviour, and it keeps the pool off the common path until a document is large
  enough that the win is unambiguous.
- **Off the event loop regardless.** Even 2.7s synchronous on the loop stalls the run's event
  stream and the user sees a hung run.

**Alternatives considered**: threads (measured useless, then fatal); always-on pool (spawn cost
on every small document, and it would make this 21-page document *slower* in the noisy case);
per-page tasks instead of contiguous chunks (dominated by re-opening the file).

**Note**: this would be the repo's first `ProcessPoolExecutor` — `main.py` and
`handoff_pipeline.py` use `asyncio.to_thread` only. New operational surface: spawn cost,
memory per worker, orphaned children on cancellation.
