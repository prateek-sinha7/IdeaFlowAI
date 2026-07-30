# Dev SSE + infrastructure issue investigations

Working files behind the second pass of
[`../DEV-SSE-INFRA-ISSUES-260729.md`](../DEV-SSE-INFRA-ISSUES-260729.md).

**Read the dossier, not these.** Every `<ID>.md` here has already been merged verbatim into the
matching issue section of the dossier as its `#### Fully-Detailed Investigation` subsection. These
copies are kept for provenance and for diffing if a section is ever edited in place.

## What this was

27 issues, 27 independent agents, one per issue, run 2026-07-30 against `dev` @ `3429d2d9`. Each
agent was required to read `../FIX-REGISTER.md` (3,705 lines) and `../IMPLEMENTATION-REGISTER.md`
(4,178 lines) **to EOF** before forming an opinion, then to re-derive the root cause independently
rather than accept the dossier's. No agent modified any file except its own output — the fix plans
are plans, nothing was implemented.

## Contents

| File | What it is |
|---|---|
| `AGENT-BRIEF.md` | The operating contract every agent read first: hard rules, mandatory reads, project invariants, the 12-section output structure, and the return contract. |
| `PENDING-QUEUE.md` | Launch ledger. The harness caps concurrent subagents at 20, so wave 1 ran 20 and wave 2 ran the remaining 7; this holds the wave-2 briefs verbatim. |
| `A1.md` … `E4.md` | One completed investigation per issue, `I1`–`I12`. |
| `DOSSIER-PRE-MERGE-BACKUP.md` | The dossier exactly as it stood **before** the investigations were merged — i.e. first-pass analysis only. Superseded; kept because the dossier was untracked at that point and this is its only record. |

## Section structure of each `<ID>.md`

`I1` anchor re-confirmation · `I2` register findings and collisions · `I3` root cause, confirmed
or corrected or replaced · `I4` blast-radius sweep · `I5` the complete fix · `I6` ripple-effect
analysis · `I7` architecture and invariant compliance · `I8` fail-before/pass-after test plan ·
`I9` rollback · `I10` sequencing and dependencies · `I11` open human decisions · `I12` rejected
shortcuts.

## Two things a reader should know before acting on any of this

1. **Where the two passes disagree, the `I1`–`I12` subsection wins.** Every issue came back
   `CONFIRMED-WITH-CORRECTIONS` or `REPLACED`. On five, the originally proposed fix is wrong rather
   than incomplete: **D6** (deletes live runs), **B2** (undone by the next `dockerd` start or
   deploy), **A5** (re-arms already-closed gates), **A2** (a stale pump tears down a resumed run's
   registration) and **D8** (unreachable today, so it would ship as dead code).
2. **E1–E4 are one verification pass short of the rest.** Those four agents were terminated by a
   session capacity limit after writing their files but before reporting, so their claims were
   never spot-checked against the code by the orchestrator. Every other issue's claims were.
