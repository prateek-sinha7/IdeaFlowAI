# Cycle 1 result — v3

Run: `260803-191418-prototype_aws_3_permits` (judged as `…-opusjudge`)
Prompts: **v3** · Instrument: opus sub-agent panel, identical to baseline.
Arithmetic verified mechanically — `ALL CONSISTENT`.

## Scores

| stage | v2 baseline | v3 cycle 1 | Δ |
|---|---|---|---|
| specify | 46.2 | 56.8 | **+10.6** |
| plan | 46.4 | 39.6 | −6.8 |
| analyze | 46.5 | 63.5 | **+17.0** |
| build | 39.3 | 19.4 | **−19.9** |
| validate | 18.4 | 77.9 | **+59.5** |
| **mean** | **39.4** | **51.4** | **+12.1** |

## Deterministic checks — both recovered

| stage | v2 | v3 |
|---|---|---|
| build | 0/1 | **1/1** |
| validate | 0/1 | **1/1** |

## Sub-dimension movement on the four targeted defects

| target | dimension | v2 | v3 |
|---|---|---|---|
| validate repaired nothing | `defect_repair_delta` | **0** | **92** |
| analyze missed the arithmetic | `defect_detection` | 16 | 44 |
| specify shipped deliberation | `spec_consistency_completeness` | 7 | 11 |
| build page completeness | `page_completeness` | 0 | 0 |

## What worked

**The validate rewrite is the result of this cycle.** `defect_repair_delta`
**0 → 92**, stage score **18.4 → 77.9**, with 0 blocking and 1 major finding
against the baseline's 3 blocking. Mechanically it took the artifact from 30 227
bytes / 7-of-7 thin sections to 63 377 bytes / 1 thin, and 8 → 16 JS functions.

The content of the check did not change between v2 and v3 — v2 already listed
routes, empty sections and handlers as P0 boxes. What changed is that v3 makes
the agent **write the audit out before its first edit**. That is the cleanest
evidence in this whole exercise for the cycle thesis: *a non-thinking model does
not execute a checklist it merely reads; it executes one it must emit.*

**analyze +17.0**, `defect_detection` 16 → 44 — the "write the addends down"
rule. Same mechanism: the output is the scratchpad.

**specify +10.6**, and the entry-point and parameterised-route rules reached
build, where both deterministic checks now pass.

## What regressed, and why

### build 39.3 → 19.4 — my error, diagnosed

The panel: *"zero `<table>`, zero `<tbody>`, zero `innerHTML` assignments and not
one render function"*. `seedData()` builds 47 permits and 100 inspections that
never reach the DOM. All seven sections are a heading over an empty container
(172 bytes each). Output tokens fell 40 524 → 10 835.

Cause: **I added +62 lines — more than any other stage — to the stage already
closest to its output ceiling**, including two worked code blocks. `ADVISE.md` §5
says in as many words *do not add length to fix a length problem*, and I did
exactly that. Build spent its budget on CSS, seed data and the router — all
things my new sections drew attention to — and never reached rendering.

The new rules themselves were not wrong: the router now splits the hash into
segments and both deterministic route checks pass. They were too long.

### plan 46.4 → 39.6, `task_self_containment` 17 → 4 — the escape hatch

New rule 4 offered two legal forms: write every row, **or** state the generation
rule completely. The plan took the second and used it to specify nothing:
*"Seed 47 permits, 100+ inspections, 6 staff records into window.appState"* with
no concrete values at all. Build then honoured it literally with
`Math.random() * 1400000` valuations and `` `${9 + (i % 8)}:${(i % 2) * 30}0 AM` ``,
which emits `"10:300 AM"` on every odd index.

So the rule closed the "…as specified in spec" hole and opened a worse one. The
missing constraint is **dataset size**: nothing bounded the plan to a set it could
actually write, so it inflated to 47 records and then had to defer.

## Cycle 2 plan

1. **build — cut, don't add.** Reduce the three new sections to their operative
   sentence (~10 lines, from 62). Add an explicit emission order for the one-shot
   branch: a page is not finished until its render function exists *and is called*.
2. **plan — bound the dataset.** A generation rule is only legal when it produces
   specific, domain-plausible values; prefer 8–15 records written in full over 47
   generated. Remove the escape hatch rule 4 accidentally created.
3. **validate — port build's add-a-token rule.** Colour literals went 7 → 20, all
   status badge pairs (`#721c24`/`#f8d7da`, `#856404`/`#fff3cd`). validate has only
   the passive `- [ ] no raw hex outside :root`; it lacks build's *"if the shade
   has no token, add the token"*. This regression is a side effect of validate
   working — it could not write bad colours while writing nothing.
4. **Do not touch the validate audit rule.** Largest clean effect in the cycle.
5. **analyze — leave alone.** +17.0 and no blocking findings.
