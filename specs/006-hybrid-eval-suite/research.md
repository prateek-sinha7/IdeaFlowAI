# Research — why the suite is shaped this way

Options considered before building `evals/hybrid/`, and why each call went the way it did. The
defect evidence itself is in [`FINDINGS.md`](FINDINGS.md); this is the design reasoning.

---

## 1. Fix first, or reproduce first?

| Option | Consequence |
|---|---|
| Fix the pipeline, then add tests | Fastest to a green run. But the defect is *structural* — nothing ever compared an edit to the instruction — so a fix with no reproduction can regress silently and be argued about forever. |
| **Reproduce, then fix** ✅ | Slower to start. The defect becomes a standing, executable claim, and the fix has a definition of done that is not a matter of opinion. |

**Chosen: reproduce first** (2026-07-22). The suite is the by-product. This is why Phase 3 — the
fix — is still unstarted while Phases 0–2 are complete: that ordering was deliberate, not
neglect.

## 2. Who decides pass/fail — code, or a model?

| Option | Verdict quality | Cost | Drift |
|---|---|---|---|
| **Code checkers** ✅ | Binary, names the exact failure | free | none |
| LLM judge | Nuanced, can assess quality | tokens per run | needs a baseline and recalibration |

**Chosen: code.** "Did the Save button end up with a working handler?" is a *fact*. Spending
tokens and accepting drift to answer a question a regex settles is a bad trade. Quality
questions that code genuinely cannot answer are a different system's job — see
[`005-prompt-eval-scoring`](../005-prompt-eval-scoring/spec.md). Keeping the two apart is what
stops the cheap checks becoming hostage to the expensive ones.

## 3. Scripted model, or real model, for the default suite?

| Option | Determinism | Cost | What it can prove |
|---|---|---|---|
| **Scripted stand-in (default)** ✅ | total | 0 tokens | the *machinery*: wiring, ordering, gates, seams |
| Real model (opt-in `--live`) ✅ | probabilistic | tokens | whether the real prompt works *today* |

**Chosen: both, strictly separated.** The scripted tier is what makes it safe to run on every
change; the live tier is the only thing that can tell you the prompt actually works. Conflating
them yields a suite that is either too expensive to run or too weak to trust. `--live` is a
universal flag, never implicit, so the free path can never accidentally spend money.

## 4. One scenario per bug, or one scenario with many?

The original design was one scenario per defect (S1 = save button, S2 = reports page, …). It was
retired in favour of a single 10-bug fixture.

**Why:** a real revision request is a punch list, not one isolated defect. One-bug scenarios were
measuring an easier task than the product actually faces, and each additional scenario multiplied
the token cost of a benchmark. The combined fixture answers the question that matters — *does one
revision turn fix a realistic list?* — for the price of one run, and the aggregate checker still
reports which of the ten failed.

## 5. Should a benchmark run once, or N times?

A single run of a probabilistic model proves very little: the same prompt has been observed
passing and missing on consecutive runs. `live_benchmark.py` runs a scenario N times and reports
a **rate**, with infrastructure errors excluded from the denominator so an expired token cannot
masquerade as a bad prompt.

## 6. Where should the suite live?

It began at `backend/tests/evals/` — under `tests/`, where a test suite belongs. Two problems
emerged:

1. A bare `pytest` collected it, meaning a plain test run could reach the live tier.
2. Its sibling grading package is *not* a test suite — it is a tool that always spends money, and
   pytest must never collect it.

Both moved to `backend/evals/` on 2026-07-29, one package per eval kind, each owning its own CLI.
Discovery survived unchanged because every path is derived from the module's own location rather
than hardcoded.

## 7. Prior art consulted

- The existing runtime validators (`app/agents/static_check.py`, `render_check.py`) — reused
  rather than reimplemented, so a structural verdict means the same thing inside the run loop as
  it does in an eval.
- `agents/workflows/<pipeline_type>/` — the suite mirrors this layout deliberately, so a
  pipeline and its coverage are navigable side by side.
- The frozen `evals/model_graded/` branch — a worked example of what happens when a score has no
  variance and the gate rejects correct output. Its failure is the direct argument for rule 5 in
  [`contracts/checker-contract.md`](contracts/checker-contract.md).
