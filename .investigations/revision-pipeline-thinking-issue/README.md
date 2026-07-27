# Start here

## The bug, in one breath

When you ask the revision pipeline to fix something on a prototype, it can
report "done" and update the file — **without actually fixing what you
asked for**. Nothing in the pipeline ever checks the edit against your
instruction; it only checks that the HTML is still structurally valid. A
harmless-looking no-op edit passes every gate.

(There's a second, smaller issue — no "thinking" is visible during a run —
but it's parked until the main bug is fixed. See [FINDINGS.md](FINDINGS.md)
if you want it, section B.)

## How to run it

```bash
cd backend
./run-eval.sh          # the whole offline suite — 0 tokens, ~2s
./run-eval.sh defect   # JUST the two tests that show the bug failing, unmasked
./run-eval.sh live-s1  # sends a real prompt to real Haiku and checks the result (costs tokens)
```

## How to read the result

**`./run-eval.sh` (plain, no args)** — this is the "is everything as expected"
check.
- **All green** → correct **today**. It means: the bug still exists (2 tests
  called `xfailed`, which is the *expected*, tracked state of a known bug —
  not a real pass), and nothing else broke.
- **Anything red** → something changed unexpectedly. Stop and look.

**`./run-eval.sh defect`** — this deliberately unmasks the 2 bug tests so you
can see the real failure instead of the "expected failure" label.
- **2 failed** → correct. This *is* the bug, shown plainly. Each failure
  shows: the pipeline said "done," but the specific thing you asked for
  (e.g. `onclick="saveSettings()"`) is missing from the delivered file.
- **0 failed** → someone fixed the underlying bug (or broke the test).

**`./run-eval.sh live-s1`** — the only test that talks to the *real* model
(Haiku) instead of a scripted stand-in. This tells you how the current
prompt performs on one real case, right now. It can go green even while
`defect` is red — that's not a contradiction, see below.

## Why "defect" can be red while "live-s1" is green

They test two different things:

| | What it tests | What red means |
|---|---|---|
| `defect` (S1/S2) | Does the **pipeline's safety net** catch a bad edit? | The pipeline has no check comparing the edit to your instruction — a structural flaw, always true regardless of model skill |
| `live-s1` | Did the **real model**, right now, do a good job on this one case? | The prompt failed to get the right result from Haiku on this instruction |

`defect` uses a scripted fake model that we deliberately made do a bad edit,
specifically to prove the pipeline's checks (`static_check`, `render_check`,
the retry logic) never look at what you actually asked for — only at
"is this still valid HTML." That's true no matter how good or bad the real
model is. `live-s1` is the separate question of "is the real model good
enough on this one case" — and today, on the easy case in the suite, it is.

## If you just want to know "is this still broken"

Run `./run-eval.sh defect`. Two failures = still broken. That's the whole
answer — you don't need to read anything else in this folder for that.

## If you want the deep detail

- [FINDINGS.md](FINDINGS.md) — root cause, file:line citations
- [PLAN.md](PLAN.md) — the phased fix plan
- [STATUS.md](STATUS.md) — what's built, what's pending, what's parked
- `requirements.md` / `design.md` / `tasks.md` — the atomic breakdown behind
  the plan

## Where things stand right now (2026-07-27)

The eval suite that **proves** the bug exists is built and green. The actual
**fix** (a check that compares the edit against the instruction) has **not
been built yet** — that's Phase 3, and it's waiting on a go-ahead before
starting. See STATUS.md → "Next step".
