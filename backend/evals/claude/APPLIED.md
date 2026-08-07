# What was applied, and what wasn't

The durable record. `advices.json` also carries a `status` field per entry, but
`cli advice` rebuilds that file from scratch — those marks are wiped on the next
run. This file isn't.

---

# All five prototype agents — v2, 2026-08-03 (AWS pool)

**Note on numbering.** The v2/v3/v4 files described further down were deleted from
`prompts/agents/`; only `v1` survived, and all five agents were `canonical` when this
pass started. So this pass rebases on `v1` and takes the name `v2` again. The 2026-07-31
sections below describe *different files with the same names* — they are history, not
the parents of these.

**Pool:** 149 advices across 5 stages, rebuilt 2026-08-03 from 9 run directories.
Those 9 are **3 briefs × 3 judges over byte-identical artifacts** (verified by md5 on
`artifacts/*`), not 9 independent runs. Distinct rows available: **3**.

**Attribution caveat — read before interpreting the next eval.** All five agents were
changed in one sweep, against §5 of `ADVISE_AND_PROMOTE.md`, at the user's explicit
direction. Stages feed each other, so if the next run moves, *no per-stage attribution
is possible*. To recover it, reset all five and re-activate one at a time:
`./activate.sh <agent-id> v2` / `./activate.sh <agent-id> reset`.

## What the pool could and could not tell us

`count`/`runs` in `advices.json` is **not** a generality signal in this pool. The file
clusters by exact string, and **0 of 149 entries spanned more than one brief** — every
entry is a count-1 anecdote by the doc's own test. Recurrence had to be established by
clustering semantically by hand, and by leaning on the two sources that don't drift:
the deterministic checks, and defects that all three judges found on the same bytes.

## Applied — with the row support for each

Support is counted in **distinct briefs (max 3)**. "det." = confirmed by
`score.json`, which outranks judge prose.

| stage | rule added | support |
|---|---|---|
| specify | Aggregates are computed from the items they summarize; the itemization is authoritative | 3/3 blocking |
| specify | A displayed subset must declare its relationship to the declared whole | 2/3 blocking |
| specify | Decision-record rule — no deliberation, no competing candidate values in the output | 1/3, contract violation |
| specify | Per-entity data rule — detail content for every navigable member, incl. nested collections | 3/3 (root of the plan/build defect) |
| specify | Interaction completeness — initial state, empty state, combined state | 2/3 blocking |
| specify | Declare a token for every colour incl. tinted/translucent variants | 3/3 (cause of the build defect) |
| plan | Sub-agent isolation contract — shared mechanisms fully specified where created | 3/3 blocking |
| plan | Per-entity data rule for detail tasks | 3/3 blocking |
| plan | Numeric agreement across tasks; specify a value as computed **or** given, never both | 3/3 |
| plan | Final task rewritten from QA checklist to concrete cross-page wiring edits | 1/3, mechanism general |
| analyze | Evidence rule — a status is the result of a comparison; Clear carries its evidence | 3/3 blocking, 2 judges |
| analyze | Recompute every asserted number; report contradictions rather than resolving them | 3/3 |
| build | Derive, don't restate — figures computed at render time from the owning structure | 2/3 |
| build | Detail views interpolate the whole record incl. nested collections | 3/3 det.-adjacent |
| build | A handler must change what is rendered; `alert()` is not an implementation | 2/3 |
| build | Tint tokens — add a token rather than inline a shade | 3/3 (cause fix) |
| build | Scope DOM queries to the page, never document-wide positional index | 1/3, classic defect |
| validate | Post-edit verification, duplicate-declaration check first | 1/3 **det.**, blocking |
| validate | Repair completeness — fix every copy of a corrected fact, and the set not the instance | 2/3 |
| validate | Prefer deriving over writing a corrected constant | 1/3 |

## Cause-level fixes, not louder restatements

Four defects recurred *despite* an existing rule. Per §3 the rule is then not the fix,
and restating it has already been measured to move the score the wrong way. What was
actually wrong:

1. **"Use ONLY `:root` variables for colors" (build) — broken in 3/3.** The prototypes
   all defined rich *solid* status tokens, but badges and highlighted rows need a
   *low-alpha wash* of one, and no token expressed that. Verified numerically: a literal
   `rgba(16, 185, 129, 0.1)` is exactly the file's own `--success: #10b981` at 10%.
   The agent had to hand-write the literal. Fix: require the tint to exist as its own
   token — in specify (declare it) and build (add one rather than inline a shade).
2. **"Zero placeholder text" (build) — a page shipped the literal word "placeholder".**
   The rule enumerated banned strings ("Lorem ipsum", "TBD", "Coming soon"), which
   invites string-matching. Fix: state the property — text that *names* a missing
   feature instead of being it — not a word list.
3. **"Every interactive element has a handler" (build/validate) — satisfied while inert.**
   `alert('Sort by X implemented.')` is a handler. Fix: the handler must change what is
   rendered, and must read the control it belongs to.
4. **"Be concise / 1–2 lines / scannable in under 60 seconds" (analyze) — this *caused*
   the dominant analyze defect.** The prompt rewarded a short report, so the agent
   emitted status tokens without doing the comparison. Fix: brevity explicitly yields
   to evidence, and a Clear status must carry what was compared.

## REJECTED — do not re-apply

1. **"`.success-toast` / `.error-toast` are declared in the stylesheet and attached to
   nothing"** (opus, validate/token_and_chrome_consistency). **The claim is false.**
   Neither `build.html` nor `validate.html` for that brief contains the string `toast`
   at all. A rule about unused toast classes would have been written against a
   hallucination. The verified part of the same finding — native `alert()` used for
   user feedback throughout — was applied instead.
2. **"12/17 nav links dead" in build (det., 1 brief) — not treated as a build defect.**
   The routing was correct: it mapped a parameterized detail route to its section
   properly. The static checker assumes a section is named after the route's first
   segment, so it flags a correct parameterized route. Writing a prompt rule here would
   have taught the agent to satisfy the checker rather than the user. Worth fixing in
   `checks.py`, not in a prompt.
3. **Region-specific data-formatting advice** (phone-number formats, culturally specific
   names, city dialling codes; several entries, scores 30–50, all 1 brief). Pure subject
   matter — it would put one brief's domain into a prompt that runs on every domain.
4. **"Add a Brief Coverage subsection to each page spec"** (score 60, 1 brief) and
   **"omit or mark Deferred any display-only field without a functional purpose"**
   (score 55, 1 brief). Both are per-page bookkeeping sections that grow the spec without
   changing what gets built; neither defect they target appeared in another brief.
5. The three specify advices rejected on 2026-07-31 (sabotaged-canary run) remain
   rejected — see the section below. They did not reappear in this pool.

## NOT APPLICABLE — targets the guardrail, not the agent

Advice naming text in `backend/agents/guardrails/html-prototype.md` cannot be applied
through this mirror: `activate.sh` overrides only the `AGENT.md` body. The two entries
recorded on 2026-07-31 (below) still stand, unreached by this pass.

## Line-count delta

| stage | v1 | v2 | delta |
|---|---|---|---|
| specify | 186 | 224 | +38 |
| plan | 196 | 219 | +23 |
| analyze | 125 | 140 | +15 |
| build | 169 | 201 | +32 |
| validate | 142 | 165 | +23 |

Frontmatter verified byte-identical for all five. No noun from any brief appears in any
prompt body. No emoji was introduced: the glyphs present are the frontmatter `icon:`
field and the report's contractual status markers, both already in v1.

---

# History — 2026-07-31 pool (files since deleted)

Pool: 115 advices across 5 prototype stages, from 8 runs on 2026-07-31.
Applied 110 · rejected 3 · not applicable 2.

## All five prototype agents — v2, 2026-07-31

Every advice from the 7 clean runs applied, plus generalisation: the pool is
saturated with one dataset's vocabulary (a warehouse-slotting app), so each
suggestion was lifted from its single observed instance to the class of thing it
belongs to before being written in. Domain nouns were scrubbed; a clause was added
to the specify prompt stating that all examples illustrate *form* only, since a
prompt that dense in examples tends to leak them into output.

| stage | applied | rejected | n/a |
|---|---|---|---|
| specify | 33 | 3 | 0 |
| analyze | 18 | 0 | 0 |
| plan | 18 | 0 | 0 |
| build | 20 | 0 | 1 |
| validate | 21 | 0 | 1 |

## All five agents — v3, 2026-07-31

No new advice. Restructure of v2 only: same rules, deduplicated, per-page
constraints pushed up into the output scaffold so a small model fills labelled
blanks rather than recalling prose rules. specify went 259 → 165 lines.

## REJECTED — do not re-apply

Three specify advices, all from run **260731-153332**. That run used a sabotaged
prompt (its advice includes `remove: "Say Hello World specify"`, an instruction
that exists in no version of the real prompt), and `advices.json` confirms it:
specify carries **two** `system_prompt_hashes` where every other stage has one.
The judge was grading a canary, so its suggestions describe a prompt that never
shipped.

1. *"Begin every response by explicitly restating the user's request…"* (score 100)
2. *"If the user's request is unclear, ask clarifying questions…"* (score 80)
3. *"remove: Say Hello World specify"* (score 100) — targets nothing real

(1) and (2) both break the absolute output contract: anything before `<spec>`, or
any question at all, means the Task Planner receives no tasks and the run produces
nothing. They will keep reappearing at high advisory scores as long as that run is
in the pool.

The *intent* of (1) is satisfied without the violation: v2 added a mandatory
`## Brief Interpretation` section as the first section **inside** `<spec>`, which
restates the brief and records every decision made on unstated details — as
resolved decisions, never as open questions.

## NOT APPLICABLE — target the guardrail, not the agent

Two `remove` advices name text living in `backend/agents/guardrails/html-prototype.md`,
not in any `AGENT.md` body. `activate.sh` only overrides the body, so they cannot be
applied through the `.vN.md` mirror. Apply them to the guardrail file directly if you
want them.

- build / visual_coherence — *remove* "No explanation text before `<!doctype html>` or after `</html>`." (guardrail line 8)
- validate / defect_repair_delta — *remove* "**Initialization Order**: …" (guardrail line 32)

## How to tell whether any of this worked

Not from this file. Advice collected against v2's prompt hash is automatically
distinguishable from advice collected against v1's — `advices.json` records
`system_prompt_hashes` per stage. If a gap that was fixed stops appearing in the
next pool, it stuck. If it reappears under the new hash, it didn't.

Watch specify's output contract on v3 specifically: it is the one place redundancy
was *reduced* (5 restatements → 3), and it guards the only failure that breaks the
whole pipeline.

---

# v3 and v4 — 2026-08-03, OPUS-AUTOMATIC loop (permits brief)

Driven by `OPUS-AUTOMATIC/PLAN.md`. Full record in `OPUS-AUTOMATIC/`; this is the
durable index.

**Instrument:** opus sub-agent panel (`JUDGE.md`) for the baseline and every cycle —
the first time a before/after in this project has held one instrument throughout.

**v3 (measured).** Mean 39.4 -> **51.4**. Deterministic checks build 0/1 -> 1/1 and
validate 0/1 -> 1/1. Per stage: specify +10.6, plan -6.8, analyze +17.0, build
-19.9, validate **+59.5**.

**v4 (written, activated, UNMEASURED)** — the run was blocked by an expired AWS
Bedrock key. See `OPUS-AUTOMATIC/FINDINGS.md` -> "Cycle 2 blocker".

## Previous-pass audit (v2 -> v3) — what landed

| rule | metric | result |
|---|---|---|
| validate: write the audit before editing | `defect_repair_delta` | 0 -> **92** LANDED |
| analyze: write the addends down | `defect_detection` | 16 -> **44** LANDED |
| build: parameterised route resolves by first segment | route checks | 0/1 -> **1/1** LANDED |
| build: seed must satisfy its own predicate | deterministic checks | 0/1 -> **1/1** LANDED |
| specify: one place per figure | `spec_consistency_completeness` | 7 -> 11 DID NOT LAND — rewritten in v4 as "a summary card is a derivation, never a number" |

## The generalisable finding

A non-thinking model does not execute a checklist it reads; it executes one it must
**emit**. validate's check *content* was unchanged between v2 and v3 — only the
requirement to write the audit out before editing was added, and repair went from
0 to 92. Two independent stages in one cycle support this. Design future edits
around it: make the output the scratchpad.

Corollary: rules cost output budget. build got +62 lines and stopped rendering
entirely (`page_completeness` 0, "not one render function"). Do not add length to
the stage nearest its output cap.

## REJECTED — do not re-apply

1. **Accessibility left undecided** (specify, major, both cycles). Real and general,
   but an addition to the longest prompt whose failing dimension is
   `spec_consistency_completeness`, not `design_system_coherence` (70). Deferred
   twice; if never affordable, that is itself the finding.
2. **Inspections seeded for permits not yet issued** (major). Domain logic; the
   general form is not obviously general (some domains pre-book legitimately).
3. **Region/domain data-shape advice** — extra reviewer disciplines, permit
   numbering order, calendar dates. Pure subject matter.
4. **Duplicate global handler names across isolated tasks** (minor). Plan's
   isolation contract already covers it and it did not land; no cause-level
   rewrite available yet, so restating it is forbidden by ADVISE.md section 2.

## Harness observations — recorded, NOT fixed (ADVISE.md section 0)

- `cli run` resolves its config path relative to `evals/minimal/`, so
  `evals/minimal/configs/x.yaml` fails on a doubled path; `configs/x.yaml` works.
- The eval never injects `=== CURRENT TASK ===`, so build always takes its one-shot
  fallback branch. All build rules were written for that branch.
- `AWS_BEARER_TOKEN_BEDROCK` wraps temporary STS credentials whose session can die
  long before the token's own 12-hour presign window closes — a run can start fine
  and fail 20 minutes later.
- **FIXED 2026-08-04 (on explicit instruction — outside the ADVISE prompt-only scope).**
  All four downstream stages were blind, not just validate. `build_judge_prompt` now
  takes `upstream=` and emits an `=== UPSTREAM ARTIFACT: <path> ===` section per prior
  stage; `cli._upstream_files` rebuilds those from each prior stage's stored `response`
  under its `seed_as` (or `deliverable`, which is how build reaches validate). Rebuilt
  from `response`, NOT from the row's `artifacts` snapshot — that snapshot is taken
  after the stage runs, so validate's `prototype.html` is validate's own output and
  diffing it would compare a file with itself. Threaded through `judge.judge()` so the
  live Mistral/Bedrock path is fixed too, and both JUDGE.md and OPUS_JUDGE.md render
  snippets updated. Verified on run 260804-024305: validate's judge prompt grew
  70,113 -> 199,203 chars and now exposes the true 11-line repair diff; specify is
  unchanged at 30,393 (it has no upstream, correctly).
  Blind weight removed: plan `page_coverage` 40%, analyze `cross_artifact_grounding`
  40%, build `page_completeness` 35%, validate `defect_repair_delta` 35%.

- **`defect_repair_delta` has never been scored on evidence.** The validate judge
  prompt is built from `row["prompt"]`, which for validate is the 840-character
  brief alone — the build artifact validate was asked to audit and repair is not in
  the prompt at any point. Section sizes of a rendered `validate.txt`
  (run 260804-024020): system prompt 29 chars (empty), brief 840, response 65,431,
  rubric 2,281, dimensions 1,362. A judge reading the prompt as rendered cannot see
  what changed, yet `defect_repair_delta` carries 35% of validate's weight.
  Found independently by two of three Opus judges on cycle 10, both of whom
  recovered the prior artifact by extracting the response block out of the sibling
  `judge_prompts/build.txt` and diffing it; confirmed by direct inspection.
  Consequence: every historical validate number is suspect on this dimension,
  including cycle 9's 85.3 and the v3 `defect_repair_delta` 0 -> 92 result that
  the "write the audit before you edit" rule was credited with.
- Judges can raise confident, wholly false blocking findings. On cycle 10 an
  analyze judge scored `defect_detection` 0 for failing to catch "an unescaped-quote
  syntax error in the INS-007 seed"; `node --check` on the artifact's only script
  block passes clean. Verify any mechanical claim before acting on it.

## Line counts

| stage | v2 | v3 | v4 |
|---|---|---|---|
| specify | 224 | 256 | 273 |
| plan | 219 | 237 | 242 |
| analyze | 140 | 159 | 159 |
| build | 201 | 263 | 240 |
| validate | 165 | 194 | 200 |

Frontmatter verified byte-identical at every step.
