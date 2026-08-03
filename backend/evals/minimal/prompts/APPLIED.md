# What was applied, and what wasn't

The durable record. `advices.json` also carries a `status` field per entry, but
`./advice.sh` rebuilds that file from scratch — those marks are wiped on the next
run. This file isn't.

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
