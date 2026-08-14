# Spec 012 — investigation reports

Read-only investigations produced while getting `sample_subagents` (four `custom-agent`
instances, spec-012 nesting shape) to run, and while working out what that exposed about
the engine's two sources of truth.

Every factual claim carries a `file:line` or commit sha. Where something could not be
evidenced it says "no evidence found" rather than guessing.

## Read in this order

| # | Report | What it answers |
|---|---|---|
| 1 | [plan-vs-membership-observed.md](plan-vs-membership-observed.md) | What the compiled plan, the registry membership, and the resolver DAG actually contain — measured, with the real equality condition |
| 2 | [plan-as-roster.md](plan-as-roster.md) | Deleting the membership assertion: what it protected, what is now exposed, and one live regression it introduced |
| 3 | [dag-validation-bypass.md](dag-validation-bypass.md) | The `depends_on` ordering branch: what it does and does not skip, and why the discriminator is unsafe |
| 4 | [dynamic-loader.md](dynamic-loader.md) | Hardcoded frozenset → filesystem discovery: the SC-001 argument, and the two tests it breaks |
| 5 | [agent-vs-workflow-config.md](agent-vs-workflow-config.md) | Full audit of which config lives on the agent but should live on the workflow |
| 6 | [dag-ownership.md](dag-ownership.md) | **The decision report.** Should `workflow.yaml` own the DAG and agents be free? Evidence, industry practice, migration path |
| 7 | [step-fanout.md](step-fanout.md) | Feasibility of running independent steps in parallel — not yet built |
| 8 | [composer-ui-findings.md](composer-ui-findings.md) | Composer UI sweep — 4 fixed defects, one of them silent data loss on reload |
| 9 | [sample-subagents-findings.md](sample-subagents-findings.md) | Live `sample_subagents` run findings — 4 fixed defects (delivery-echo, tool-call LIFO, stale filename example, artifact-fallback override) |
| 10 | [outstanding-bugs.md](outstanding-bugs.md) | The severity-ranked catalog of every custom-workflow defect (refs **A**–**O**) — the direct source for `../bugs.md`, `../issues.md`, and `SPEC012-ADR-09`/`-10` |
| 11 | [parallel-subagents-no-html.md](parallel-subagents-no-html.md) | Earliest investigation: why a custom workflow never produced `output.html` across 10 runs — the deliverable-strategy root cause `outstanding-bugs.md` calls **0** |
| 12 | [task-prompt-injected-into-output.md](task-prompt-injected-into-output.md) | Second investigation, superseded by 13: why step instructions leaked into agent output |
| 13 | [composed-workflow-prompt-contract.md](composed-workflow-prompt-contract.md) | The full prompt-contract investigation — supersedes 12, adds the root cause that reading only the user-facing context missed. Directly synthesized into `outstanding-bugs.md` |

Reports 1–5 describe the current state. Report 6 is the recommendation that follows from
them. Report 7 is a separate feasibility question that reports 1–6 do not depend on.
Reports 8–9 are evidence for `../bugs.md` and `../issues.md` — the spec's tracked
bug/issue log, one directory up. Reports 11–13 are the chronological history behind
report 10; read 10 first — it is the synthesis, and 11–13 are needed only for `file:line`
evidence tracing.

## The one-paragraph version

The engine derives execution order from `produces`/`consumes` declared on each agent, while
per-step configuration lives in `workflow.yaml`. That works while every agent belongs to
exactly one pipeline. It breaks the moment one `AGENT.md` is instantiated N times, because
all N instances share one set of contracts and the resolver cannot tell them apart. The
measured evidence says the contract system was never really used as one: 72 of 87 agents
declare `produces: [<their own id>]`, which is `depends_on` written backwards and stored on
the wrong object. The recommendation is that `workflow.yaml` owns structure and order,
agents become free and reusable, and `produces`/`consumes` is kept for satisfiability
checking and context routing but stops deciding sequence.

## Decisions

Every report below that reached a decision carries a `Verdict` callout near its top
naming the `SPEC012-ADR-NN` id. **`../ADR.md`** is the full record, in this spec's own
words — read that first; come back here for the supporting analysis.

Three of the four items originally logged here as open have since been decided
(`SPEC012-ADR-01`, `-02`, `-04`). One remains genuinely open: the code-gen pipelines'
execution order (`app_builder`/`dotnet_to_azure`/`mulesoft_to_springboot`) — see
`../ADR.md`'s Open questions, and the tracking callout at the top of
[dag-ownership.md](dag-ownership.md).

## Supporting data

The raw dumps this report was originally built from (`dump_raw.py`,
`dump_plan_vs_membership.py`, and their `workflow.compiled.json` /
`agents.membership.json` output) were removed 2026-08-13 — the findings above stand on
their own and do not depend on the raw data being present. `check_condition.py` remains
at the repo root and still evaluates the real assertion verbatim for every pipeline type:

```
check_condition.py   evaluates the real assertion verbatim for every pipeline type
```

Run from `backend/` with `DATABASE_URL=sqlite:///:memory: python3.11 ../check_condition.py`.
Read-only, makes no network calls, touches no real database.
