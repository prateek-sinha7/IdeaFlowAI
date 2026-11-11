# Playbook: requirements document (spec, PRD or user stories)

Use when the deliverable is a written requirements document: a specification, a product
requirements document (PRD), user stories with acceptance criteria, or a backlog built from
them. This is the second playbook (problem-decomposition §3a). It shares its first three
stages with the UI prototype playbook (`ui-prototype.md`), so a builder can reuse them.

## Depth

- **Full** (default for a PRD or spec from documents): seven stages below.
- **Lite** (user chose Fast, or the request names one feature): read, then one step that
  analyzes, asks and writes the document, then a reviewer.

## Stages

| # | Stage | Job | Output (file) | Gate or check |
|---|---|---|---|---|
| 1 | Read | Extract facts, quotes and open points from each upload, with references | `notes/doc-<slug>.md` | Every note has five sections |
| 2 | Analyze | Numbered requirements, actors, data, business rules, scope in and out | `analysis/requirements.md` | Every requirement has an ID and a source |
| 3 | Clarify | Questions the documents leave open, each with a suggested answer | `analysis/gaps.md` | `human` gate after stage 2, `redoable` |
| 4 | Stories | User stories per actor, each with acceptance criteria | `stories.md` | Every requirement is covered by at least one story |
| 5 | Non-functional | Performance, security, privacy, accessibility, data retention, limits | `nfr.md` | Every NFR names a measurable target or says "to be confirmed" with its gap ID |
| 6 | Assemble | The document in the requested form (spec, PRD or backlog) | `spec.md` (or `prd.md`, `backlog.md`) | Every requirement appears in the document's acceptance section |
| 7 | Review | A critic checks the document against the notes and requirements; a revision goes back to stage 6 | review notes; `pass` or `revise` | Critic loop, `loop_max_iterations: 2`, `on_loop_exhausted: continue` |

For a backlog, add `backlog_plan_coverage` on the assemble step, with `fix` and the
`validation` gate. It checks that every coverage item is placed in an epic and a slice.

## Where the human answers

Stage 3 only, after stage 2. The user answers with Request changes. Do not gate stage 4 to 7:
the user sees the document at the end and can ask for a revision with the review gate.

## Traps

- Stories without acceptance criteria are not stories. Each story gets at least one
  criterion a reviewer can check.
- Non-functional requirements without a number are wishes. Mark each as a target or a gap.
- A PRD and a spec are different: a PRD states what and why for the product, a spec states
  how the system behaves. Use the form the user asked for.
- No validator checks length or tone: enforce the requested length in the prompts of stages 4
  and 6, and say so in the response.

## Shipped reference

`catalog_lookup.py example user_stories` shows a chain of catalog agents for stories (trust
file). `catalog_lookup.py example backlog us-review` shows a reviewer step.
