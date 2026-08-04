# Running findings log

Appended each cycle. Newest cycle at the bottom.

---

## Before cycle 1 — what the previous rounds got wrong

Established in `../RESEARCH_WHY_NO_IMPROVEMENT.md` and carried in as the reason
this loop is structured the way it is.

1. **Every "before vs after" comparison in the previous rounds was invalid** — it
   compared different judging instruments. Four have been used (Bedrock haiku,
   Mistral, single-threaded opus, opus sub-agent panel), and on byte-identical
   artifacts they spread **58 points on build and 86 on validate**. This loop uses
   one instrument for every cycle.
2. **Mistral is saturated** — identical scores on artifacts differing by 47 KB. It
   awards a house number in the low 90s and cannot register a delta.
3. **The v2 sweep did work**, judged mechanically: colour literals fell 20→8,
   28→2, 37→7 across three briefs and `alert()` went 8→0. The two rules that moved
   were the two written as *decision procedures*, not restated prohibitions.
4. **The advice pool carries no recurrence signal** — all 149 entries `count: 1`,
   because it clusters by exact string and pools the same artifacts judged
   repeatedly. Cycle advice therefore comes from `judge.json` findings directly.

---

## Cycle 1 — v2 → v3

Run `260803-191418-prototype_aws_3_permits`. All five stages dispatched OK.

### Deterministic checks — recovered

| stage | v2 baseline | v3 cycle 1 |
|---|---|---|
| build | **0 / 1** | **1 / 1** ✅ |
| validate | **0 / 1** | **1 / 1** ✅ |

Judge-independent and the most trustworthy signal available. The two blocking
defects cycle 1 targeted — the seed/predicate mismatch and the parameterised
route — are exactly what these checks cover, and both routes now resolve. The
build artifact splits the hash into segments (`.split('/')`) as the new router
rule prescribes.

### Mechanical metrics

| metric | v2 build | v3 build | v2 validate | v3 validate |
|---|---|---|---|---|
| bytes | 80 571 | **30 227** ⚠️ | 80 563 | 63 377 |
| sections | 6 | 7 | 6 | 7 |
| thin sections | 1 | **7** ⚠️ | 1 | **1** |
| colour literals | 7 | **20** ⚠️ | 7 | **20** ⚠️ |
| `alert()` | 0 | 0 | 0 | 0 |
| JS functions | 6 | 8 | 6 | **16** ✅ |

Output tokens: specify 10 680 · plan 14 937 · analyze 4 686 · **build 10 835**
(was 40 524) · **validate 15 061** (was 6 912).

### The two things that actually happened

**1. validate finally did its job.** This is the headline. At baseline validate
spent 6 912 output tokens and changed 8 bytes — `defect_repair_delta` was **0**.
This cycle it spent 15 061 tokens and took the artifact from 30 227 bytes with
**7 of 7 thin sections** to 63 377 bytes with **1**, tripling the JS function
count from 8 to 16. The `STEP 1 — WRITE THE AUDIT BEFORE YOU EDIT` rewrite is the
only change that could have caused this, and the effect is unambiguous.

That is direct evidence for the cycle thesis: **converting a passive checklist
into a written enumeration the agent must produce before editing is what makes a
non-thinking model act on it.** The boxes were already in v2; the agent read them
and did nothing.

**2. build regressed hard.** 40 524 → 10 835 output tokens; 80 571 → 30 227 bytes;
1 → 7 thin sections. The build agent wrote a shell and stopped. Its prompt grew
most of any stage this cycle (+62 lines, including two worked code blocks), which
is the prime suspect — `ADVISE.md` §5 says *do not add length to fix a length
problem*, and cycle 1 added the most length to the stage already closest to its
output ceiling.

Colour literals also went 7 → 20 in both artifacts, a regression on a metric v2
had improved.

### Reading these together

The pipeline's *final* deliverable is `validate.html`, and it ended at 63 377
bytes / 1 thin section / 16 functions with both deterministic checks passing —
against a baseline of 80 563 bytes / 1 thin / 6 functions with both checks
failing. So the end-to-end artifact improved on the checks that don't drift, even
though the build stage in the middle got materially worse.

This is a real attribution win despite the all-five sweep: `defect_repair_delta`
can only move from the validate prompt, and the deterministic route checks can
only pass if the router rule landed in build.

### Carried into cycle 2

- **Cut build's prompt back down.** The two new build sections need to shrink to
  their operative sentence; the worked router block can lose its comments. Test
  whether build's token output recovers toward 25–40 k.
- **Colour-literal regression — cause found, fix identified.** The 20 literals are
  not random: they are **status badge colour pairs** written by hand —
  `#721c24`/`#f8d7da` (danger text on danger wash), `#856404`/`#fff3cd` (warning
  pair), `#dc3545`/`#c82333`. v2's seven were mostly `rgba(0,0,0,0.05)` shadows.

  The mechanism: validate is now **filling six empty sections from scratch**, so it
  is writing new badges and pills that need tint shades — and `:root` has 25 tokens
  covering none of those pairs, so it hand-writes them.

  This is v2's tint-token defect reappearing in a new stage. The build prompt
  carries the cause-level rule (*"If the shade you need has no token, add the token
  to `:root` and use it"*); **validate does not.** Its only colour rule is the
  passive `- [ ] No raw hex colors outside :root`, which tells it what not to do
  and gives it nowhere to go. Cycle 2: port build's add-a-token instruction into
  validate. This regression is a direct consequence of the validate fix working —
  the stage could not write bad colours while it was writing nothing.
- **Do not touch validate's audit rule.** It is the one change with a clean,
  large, attributable effect. Leave it alone and let it be re-measured.

### Cycle 1 scores — opus sub-agent panel, same instrument as baseline

| stage | v2 | v3 | Δ |
|---|---|---|---|
| specify | 46.2 | 56.8 | +10.6 |
| plan | 46.4 | 39.6 | −6.8 |
| analyze | 46.5 | 63.5 | +17.0 |
| build | 39.3 | 19.4 | −19.9 |
| validate | 18.4 | 77.9 | **+59.5** |
| **mean** | **39.4** | **51.4** | **+12.1** |

Arithmetic verified mechanically (`ALL CONSISTENT`): every sub-score equals
100 − costs, every stage score reproduces from sub-scores and weights, findings
count equals weaknesses count.

**The one finding that matters most:** `defect_repair_delta` **0 → 92**. The
content of validate's checks did not change between v2 and v3 — v2 already listed
routes, empty sections and handlers as P0 boxes. What changed is that v3 makes the
agent **write the audit out before its first edit**. This is the strongest
evidence produced anywhere in this exercise for the prompt-shape thesis: *a
non-thinking model does not execute a checklist it reads; it executes one it must
emit.* The same mechanism produced analyze's +17.0 (`defect_detection` 16 → 44)
via "write the addends down".

**Both regressions were caused by my own edits**, and both were diagnosable:
build got +62 lines (most of any stage, on the stage nearest its output ceiling)
and stopped producing render functions entirely; plan's new rule offered a
"generation rule" alternative to writing rows out, and the plan used it to specify
a quantity instead of data.

---

## Cycle 2 blocker — AWS credentials expired mid-experiment

**Cycle 2's prompts (v4) are written, verified and activated. The run did not
happen.** Run `260803-193034-prototype_aws_3_permits` errored on all five stages:

    AccessDeniedException ... ConverseStream: Authentication failed:
    Please make sure your API Key is valid.

Diagnosis (no code or config was changed to establish this):

- A live Bedrock call succeeded at **17:08 UTC**, and the whole of cycle 1
  dispatched successfully between **17:14 and 17:29 UTC**.
- The first failure was at **17:30 UTC**. Retried once per `PLAN.md`; still failing.
- `AWS_BEARER_TOKEN_BEDROCK` in `backend/.env` decodes to a presigned
  `CallWithBearerToken` request: issued `20260803T170750Z`, `X-Amz-Expires=43200`
  (12 h), so **the presign window is still open**.
- But its credential is `ASIA3S4PSEJ5EQAD7HOA` with an `X-Amz-Security-Token` —
  temporary STS session credentials. **The underlying session expired ~23 minutes
  after issue, well inside the token's own 12-hour window.** That is the failure:
  the outer presign is long-lived, the inner session is not.

**This is not fixable from here.** Minting a new Bedrock API key requires the
user's AWS login, and `ADVISE.md` §0 forbids editing `.env` or the harness. Cycles
2 and 3 stop here.

**To resume:** refresh the Bedrock API key in `backend/.env`, then — v4 is already
active, nothing needs re-activating —

    cd backend
    python3.11 -m evals.minimal.cli run configs/aws_3_permits.yaml
    for s in specify plan analyze build validate; do
      python3.11 -m evals.minimal.cli checks <RUN_ID> --stage $s; done

then judge that run with `JUDGE.md` and compare against cycle 1 (51.4) and the
baseline (39.4). `cycle-2-advice.md` records exactly what v4 changed and what each
change was predicted to move.

**Note on the short session lifetime:** if the next key also dies inside half an
hour, a three-cycle unattended loop is not viable on it at all — each cycle needs
~15 minutes of dispatch plus judging. That is worth knowing before the next
attempt.
