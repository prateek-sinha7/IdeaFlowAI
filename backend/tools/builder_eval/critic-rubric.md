# Critic rubric (offline eval only)

The critic scores a builder manifest after a live eval run. It runs in
`tools/builder_eval/critic.py`, never in a production turn. Each dimension gets a score
1-5 and a one-line reason. Code computes the facts first (prompt lengths and sections, gates
before irreversible steps, loop caps, the slot table, the defaults-run shape); the model judges
with those facts in front of it and may not contradict them.

| Score | Meaning |
|---|---|
| 5 | Fully meets the dimension; nothing to fix. |
| 4 | Meets it with a minor gap that would not change a run's result. |
| 3 | A real gap: some runs would produce a weaker or wrong result. |
| 2 | Mostly missing. |
| 1 | Absent, or the manifest contradicts it. |

## Dimensions

| Key | What is judged | 5 looks like | 1 looks like |
|---|---|---|---|
| `requirement_coverage` | Every blocking and important slot value (the slot table) is met by a step, a setting or a prompt rule. | Each slot maps to something concrete. | Slots the user answered are ignored. |
| `missing_input_behaviour` | Every working step says what it does when an input is missing (NEEDS_INPUT, ask, or a marked assumption). | Every step has IF INPUT IS MISSING with a concrete rule. | No step defines it; placeholders would be written. |
| `irreversible_gates` | Every post, integration write or exec has a gate directly before it (code fact: `irreversible_gate` issues). | No issues, or nothing irreversible. | An ungated write. Score 1 whenever the code fact lists an issue. |
| `loop_caps` | Every loop (backward route) has `loop_max_iterations` 2-3 and an exit; no unbounded repetition. | Capped loops, or no loops. | A loop without a cap. |
| `prompt_depth` | Working prompts follow the prompt standard (code fact: length and missing sections per step). | Every working prompt 3,000-7,000 characters with all sections. | Thin prompts with sections missing. |
| `assumptions_echoed` | Every assumed slot appears in the reply's Assumptions block or Open questions. | All echoed. | None echoed. |
| `no_placeholders` | The deliverable cannot be a template: prompts never tell a step to write "[Name]"-style placeholders, and missing facts stop or are marked. | Placeholders are forbidden in the prompts. | A step is told to fill gaps with placeholders. |
| `answers_changed_manifest` | For a scripted run: where the user's answers differ from the defaults, the manifest differs from the defaults run in that direction (code fact: the answers chosen and the shape diff). `null` for a defaults run. | Every non-default answer shows up in the design. | The manifest equals the defaults run despite different answers. |

## Questions (code check, reported, not scored)

`approval_where_without_write`: the round-one `human_approval_points` question was asked in
the WHERE/WHAT form (no option removes the person), but after the handoff the workflow has no
external write (`irreversible_actions` none or not applicable; for example H1 answered "1a,
returned as files"). Without a write, a WHETHER question ("should a person review?") was the
right form. `report.py` counts the sessions where this happens; the decision on it is open.

## Pass bar

A manifest passes when every non-null dimension scores 4 or more. The flag-flip bar was
every dimension >= 4 on >= 90% of manifests.
