# Clarifications — 008-grading-calibration

**Resolved**: 2026-07-30 · 5 decisions made · 2 things deferred
**Evidence preserved**: `backend/evals/grading/model/workflows/prototype/golden/calibration/`

---

## The problem in one paragraph

Our golden artifact is verified perfect — code score 100, every check green, every button
tested. The grader gave it **80**. Meanwhile the grader has given broken output scores in
the 90s. So the grader ranks bad work above good work, which makes every number it produces
useless.

**Why it happens**: the grader counts how many things the judge complained about, and
lowers the score based on that count. It never looks at *how bad* those complaints are.

**And it's worse than the one stage I first reported.** Now that the full run is preserved
(C5), the numbers are in front of us — **every one of the five stages was capped, and 11 of
15 dimensions**:

| stage | judge actually said | what we recorded | dimensions capped |
|---|---|---|---|
| specify | 94.40 | **84.40** | 2 / 3 |
| plan | 91.60 | **84.40** | 2 / 3 |
| analyze | 97.45 | **88.00** | 2 / 3 |
| build | 94.55 | **80.00** | **3 / 3** |
| validate | 94.55 | **88.95** | 2 / 3 |
| **average** | **94.51** | **85.15** | **11 / 15** |

Not one of those 11 caps was triggered by an actual defect. They were triggered by sentences
like *"node labels are 11.5px where body text is 14px"* and *"this metric could be
contextualised with industry benchmarks"*. The judge scored the build 92/95/98 and called it
*"exceptional… near-flawless"*; we recorded 74/84/84.

**The fix, in one line**: stop counting complaints, start reading how serious they are —
and let the automated browser checks put a lid on what the judge is allowed to claim.

---

## C1 — Should the automated checks limit what the judge can give?

### The question in plain English

We have two graders. One is a **judge** (an LLM that reads the page and forms an opinion).
One is the **code track** (a real browser that clicks every button and reports what
actually broke). Today we just average them: 70% judge, 30% code.

That means if the browser says "this is completely broken, 0 out of 100" and the judge says
"looks lovely, 90", the final score is **63 — a D**. Broken output gets a D. That's wrong.

### What I found while investigating

My first idea was: "if the code score drops below 40, force the final score down." But I
checked, and **that would almost never fire**. There's an earlier gate (the "precheck") that
already throws out any HTML that's structurally broken before the judge ever sees it. So by
the time we're blending scores, the code score is nearly always 90+.

The real gap isn't at the broken end. It's in the **middle**: a page that's structurally
fine but has three navigation links that don't work (code score 70) can still get a 92 from
the judge, and today the averaging quietly turns that into 85 — a solid B.

### ✅ What we decided: the judge can't score more than 15 points above the browser

```
final score = whichever is lower of:
    (a) 70% judge + 30% code      ← today's formula
    (b) code score + 15
```

### What this actually does

| browser says | judge says | today's score | new score | what changed |
|---|---|---|---|---|
| 100 (all good) | 92 | 94.4 | **94.4** | nothing — our golden is unaffected |
| 85 | 92 | 89.9 | **89.9** | nothing — still within 15 points |
| 70 (3 dead links) | 92 | 85.4 | **85.0** | the browser pulls it down |
| 0 (broken) | 90 | 63.0 → **D** | **15.0 → F** | broken output can no longer pass |

**In short**: the judge is allowed to see quality that automated checks can't measure — but
only up to a point. It can't claim a page is great when the browser says half the buttons
are dead.

---

## C2 — How much should each complaint cost?

### The question in plain English

When the judge complains about something, how many points should that cost? Today the
answer is "a lot, and it doesn't matter what the complaint was":

| judge complains about | today's penalty |
|---|---|
| 1 thing | score capped at **84** |
| 2 things | score capped at **74** |
| 3+ things | score capped at **64** |

"The detail page is completely empty" and "I'd have used a slightly larger font" are treated
identically. And it gets worse: a judge that says nothing at all keeps its 98, while a
thorough judge that spots one cosmetic thing gets slammed to 84. **We are punishing the
judge for doing its job properly.**

### ✅ What we decided: the judge labels each complaint, and we price it accordingly

The judge now has to tag every complaint with one of three labels:

| label | means | costs |
|---|---|---|
| **blocking** | "I would refuse to ship this" | score is forced down to **45**, plus −8 |
| **major** | "a real gap a reviewer would want fixed" | **−8 points** |
| **minor** | "a nitpick, a preference" | **−1 point**, and never more than −4 total no matter how many |

No more caps on counting. Just: serious problems cost real points, nitpicks cost almost
nothing, and one genuinely unshippable defect forces a failing score regardless.

### What this actually does to our golden

The judge's real verdict on the build stage was 0 blocking, 0 major, and 4 nitpicks:

| dimension | judge gave it | nitpicks | old grader | new grader |
|---|---|---|---|---|
| data realism | 92 | 2 | 74 | **90** |
| page completeness | 95 | 1 | 84 | **94** |
| visual coherence | 98 | 1 | 84 | **97** |

**Build stage: 80.0 today → 95.2 with the fix. Grade B → A+.**

And because the same caps fired on all five stages, the whole run moves with it — from the
recorded **85.15 average up to 93.57 — within a point of the 94.51 the judge actually gave**. That's the
judge's own opinion, shaded slightly for the nitpicks it found, which is what should have
happened all along.

### And what it does to broken output

A broken page gets at least one **blocking** complaint from the judge → forced to 45.
And separately, C1's browser lid drops it to 15 anyway. **Two independent safety nets**:
one reads what the judge wrote, one reads what the browser measured. Neither depends on the
judge being harsh.

---

## C3 — How much do we build now?

### ✅ What we decided: fix the scoring problem, nothing else

**Building now** (this is the complete fix — nothing about the reported problem is left open):

0. ✅ **Done** — both reference files rescued out of `.runs/` into a committed folder (C5)
1. Judge labels its complaints blocking / major / minor
2. New pricing replaces the old counting
3. Browser lid on the judge's score
4. Rubric wording updated to match; the `hollow_console.html` fixture written
5. New `grade.sh calibrate` command; you run it; we re-pin the thresholds from its output

**Deferred** (written down, not built — see the bottom of this file):

- Automated checks for the three *document* stages (spec / plan / analysis) — they currently
  have no automated check at all, only the judge's opinion
- `options.repeats` — running the judge 3× and taking the middle score

Neither of those caused the problem you reported, and both would make this change
significantly bigger.

---

## C4 — What do we test the fix against?

### The question in plain English

The new `calibrate` command needs to prove the grader ranks things correctly. To do that it
needs **known-good** files (we have those — the golden set) and **known-bad** files (we
don't have those yet). Where do the bad ones come from?

### ✅ What we decided: one real broken file, one fake-good file

**1. `clinic_scheduler_broken.html` — a real failure, recovered from our own history**
→ **saved**, see C5

I found the actual broken output from run `260730-012401` still on disk and copied it out.
Code score **0.0**, 7 structural errors — all of them real:

```
dead nav link: '#/patient/101' has no matching <section data-page="patient">
   … (same for /102, /103, /104, /105)
routes map missing page id 'patient-detail'
routes map has extra id 'patientDetail' matching no section
```

This is genuine agent output that actually caused the problem. That matters — a file I broke
on purpose only proves the grader catches things I already knew to look for.

One thing worth knowing: it **fails the precheck**, so the judge never saw it and no judge
score was ever recorded. It tests the automated half of the scale, not the judgement half.
That's exactly why we need the second file.

**2. `hollow_console.html` — hand-written, looks fine, is empty inside** *(still to write)*

Every structural check passes. The browser is happy. But the pages are a heading over an
empty shell with generic made-up data.

This one is the important test. It's the case where **only the judge can catch the problem**
— there's nothing for the browser to report. If this file ever scores near our golden, it
means the rubric has stopped actually reading the content, and we'd want to know immediately.

### What `calibrate` will check

| file | must score |
|---|---|
| every golden brief | **90 or above** |
| `clinic_scheduler_broken` | **20 or below** |
| `hollow_console` | **50 or below** |
| gap between worst golden and best bad file | **at least 25 points** |

If any of these fail, the command exits with an error naming exactly which file, which
stage, and which complaint caused it. **This is the check that would have caught the
original problem automatically.**

---

## C5 — Where do the good and bad reference files actually live?

### The question in plain English

The proof that the grader is broken lives in `.runs/prototype/golden-mission-control/`.
I checked: **`.runs/` is gitignored** (`evals/grading/.gitignore` line 7). It is scratch
space. One cleanup and the evidence is gone — along with the only recorded example of the
broken output, which is in an even older run folder.

We would then be left arguing about a scoring bug with nothing to point at.

### ✅ What we decided: copy both ends of the scale into a committed folder — done now

```
backend/evals/grading/model/workflows/prototype/golden/calibration/
├── README.md
├── top/
│   └── mission_control.verdict.json        ← the good end
└── fail/
    ├── clinic_scheduler_broken.html        ← the bad end (real output)
    └── clinic_scheduler_broken.verdict.json
```

**Verified**: `git check-ignore` says these are not ignored. They will commit.

### What's in each one

**`top/mission_control.verdict.json`** — the four artifacts themselves were already safe in
`golden/mission_control/`. What was *not* safe was **the grading verdict**, so that's what's
frozen: for all five stages, what the judge reported, what the caps changed it to, and the
exact sentence that triggered each cap. This is the file that proves 11 of 15 dimensions
were capped by nitpicks.

**`fail/clinic_scheduler_broken.html`** — the 18.9 KB of real broken output, plus a
companion JSON recording its code score (0.0), its 7 structural errors, and its SHA-256 so
we can tell if it's ever silently modified.

### Why this matters beyond convenience

Once these are committed, `grade.sh calibrate` doesn't need a live run to check the scale —
it has a permanent good end and a permanent bad end to measure against. And when someone
changes the rubric six months from now, the question "did this make the golden score worse?"
has a checked-in answer instead of a deleted folder.

**Re-freeze the `top/` file** whenever the golden artifacts change, the rubric weights
change, or a new calibration run is recorded — and commit it in the same change, so the
fixture and the scale never drift apart.

---

## Deferred — written down, not built

| what | why we're not doing it now | why we're not dropping it |
|---|---|---|
| **Automated checks for spec / plan / analysis** | The problem you reported is on the HTML stages, and it's fully fixed there. Adding a whole new checker widens the change without making the fix more correct. | Those three stages have **no automated check at all** — the judge grades them and nothing verifies it. C1's browser lid can't protect a stage that has no browser score. |
| **`options.repeats`** | Running the judge 3× triples the cost of every run, and one-shot variance isn't what caused this problem. | **It currently doesn't work at all.** `config.py` line 272 validates the setting and then nothing reads it. Anyone who sets `repeats: 3` thinks they have a stability control they don't have. It has to be built or removed before someone relies on it. |

Neither one blocks `calibrate` — it grades whatever stages a run produced.

---

## Two things I found that you should know about

**1. A comment in our code cites evidence that doesn't exist.**
`judge.py` lines 32–38 justify the current caps by saying run `260730-012401` scored broken
HTML at 89.5. I checked that run folder — both rows show `precheck_passed: false` with no
judge score at all, and the backup folder only holds specify-stage files. The broken file
itself is real and now preserved (C5), but **the 89.5 number is not reproducible from the
run it cites**, so that sentence should be corrected or removed when we edit the file, not
copied forward. The caps' real cost is now documented with numbers that *do* reproduce: 11
of 15 dimensions, in `top/mission_control.verdict.json`.

**2. The two gates disagree at the edges.**
In that same run, `expense_approvals` scored **97** on the code track with zero structural
errors — and still failed the precheck. Worth remembering: a good code score is not the
same as passing the precheck, and neither one replaces the other.
