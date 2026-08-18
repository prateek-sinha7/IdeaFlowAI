# Spec 012 — issues (not fixed)

Every defect found while getting composed (custom) workflows to run correctly under this
spec that was **not** fixed — a deliberate WONTFIX/BY DESIGN ruling, a real defect
deferred rather than scheduled, or a claim that did not reproduce. See `bugs.md` in this
same folder for what was fixed.

Tracked here, not in `.planning/ISSUES-REGISTER.md` — that register is for issues
reported through Jira. Everything below was found directly while implementing and
live-testing this spec, with no Jira ticket behind it.

**IDs are `SPEC012-ISSUE-NN`, stable and sequential — cite these, not the `Ref` column.**
`Ref` is the letter used in the source investigation this item came from, kept only so
the file:line evidence in [reports/outstanding-bugs.md](reports/outstanding-bugs.md)
stays findable.

Every WONTFIX/BY DESIGN row below is a **recorded decision**, not a silent drop — each
carries who/what ruled it out and why, so it is never re-litigated from a code comment
alone.

---

## WONTFIX / BY DESIGN — decisions recorded (2)

| ID | Ref | Defect | Root Cause | Decision | Rationale |
|---|---|---|---|---|---|
| **SPEC012-ISSUE-01** | A | Run brief injected into every step, including children with complete prompts | `_compose_context_message`, unconditional `parts[0]` | **WONTFIX** — owner ruling, 2026-08-13 | Load-bearing: with `{{topic}}` never substituted (**SPEC012-ISSUE-03**), the brief is the only channel carrying the subject into a composed step. The proposed demotion would change every composed step's context message, and every success to date happened with the imperative framing. Only bites when the brief is a full sentence competing with a step prompt |
| **SPEC012-ISSUE-02** | I | Delivery block overrides a filename the step's prompt named | `factory.py` always names `artifact_name(instance_id, topic)` | **BY DESIGN** — ADR-0011 | It IS the artifact-guarantee mechanism: the fallback writer, the roster and the deliverable readback must agree on one name, and only a derived name guarantees that. Removal was trialled and reverted — the chain ran, but the roster then advertised 0-byte artifacts. Full reasoning and alternatives considered in `.knowledge/cards/ADR-0011.md` |

## DEFERRED / PARKED — real, not scheduled (6)

| ID | Ref | Defect | Root Cause | Why parked |
|---|---|---|---|---|
| **SPEC012-ISSUE-03** | N | `{{topic}}` never substituted | No template engine in factory/compiler/engine | Belongs to the advance-agent-configuration design (author-defined variables), not a one-line replace |
| **SPEC012-ISSUE-04** | G | `streamed_text`+`.html` reports wrong mimetype | `streamed_text.py` maps by strategy, not filename | Trigger no longer reachable — deliverable is `single_file` now (`bugs.md`'s **SPEC012-BUG-01**), and **SPEC012-ISSUE-09** confirmed the pair isn't recreated |
| **SPEC012-ISSUE-05** | C1 | ~500 tokens document an uncallable `task` tool | `SubAgentMiddleware` injects prompt independent of tool filtering | Fix needs `HarnessProfile`, **beta** in deepagents 0.6.7 |
| **SPEC012-ISSUE-06** | C2 | Agent asks a clarifying question instead of working | `BASE_AGENT_PROMPT`, appended after ours | Same blocker as SPEC012-ISSUE-05 |
| **SPEC012-ISSUE-07** | C3 | Agent hunts files despite "do not look" | `BASE_AGENT_PROMPT` "Understand first" | Same blocker as SPEC012-ISSUE-05 |
| **SPEC012-ISSUE-08** | L | Model selection never reaches the runtime | Suspected: `OLLAMA` is a global switch, not per-run | Parked with Ollama; blocks all small-model drift testing |

## NOT REPRODUCED (1)

| ID | Ref | Defect | Verdict |
|---|---|---|---|
| **SPEC012-ISSUE-09** | H | Composer "Reset to default" believed to recreate the broken deliverable pair | Did not reproduce on the `cow` run — manifest already correct. Reopen if it recurs |

---

## Next actions

1. **SPEC012-ISSUE-05/06/07** — highest-severity remaining, and the only ones needing
   neither kernel nor engine work: `GeneralPurposeSubagentProfile(enabled=False)` and
   `HarnessProfile(base_system_prompt=…)`. Blocked on `HarnessProfile` graduating past
   beta in deepagents.
2. **SPEC012-ISSUE-08** — blocks all small-model drift testing until resolved.
3. **SPEC012-ISSUE-03** — needs the advance-agent-configuration design before it can move.

## Open question

- Which of **SPEC012-ISSUE-01**'s downstream consequences (children answering the brief
  instead of their own prompt) are actually observed in production custom workflows
  today, versus only in adversarial/long-brief test runs? That evidence would change
  whether the WONTFIX ruling should be revisited.
