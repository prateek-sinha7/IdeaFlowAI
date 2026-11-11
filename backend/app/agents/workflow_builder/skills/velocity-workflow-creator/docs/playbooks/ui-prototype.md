# Playbook: UI prototype

Use when the deliverable is a clickable HTML prototype of an app or a set of screens, made
from a brief, from uploaded documents, or both. This is the first playbook the builder uses
(problem-decomposition §3a). It states the expert stages of the work, so the builder cuts
parts from the stages below and not from the request's wording.

## Depth

- **Full** (default). Use it unless the user chose Fast. Seven root steps; it is the depth
  that gives a reviewer a spec, a design and a QA pass before the file is built.
- **Lite** (only when the user asks for Fast, or the request is a single screen). Four root
  steps: read, analyze and ask, spec with design as phases, build.

Ask "Fast or Thorough?" with the outline in the same message (SKILL.md step 3). When the user
does not answer, use Full.

## Stages

| # | Stage | Job | Output (file) | Gate or check |
|---|---|---|---|---|
| 1 | Read | Extract facts, quotes and open points from each upload, with references | `notes/doc-<slug>.md` | Every note has five sections; none lacks a reference |
| 2 | Analyze | Turn the notes into numbered requirements and screens | `analysis/requirements.md` | Every requirement has an ID and a source |
| 3 | Clarify | Put the questions the documents leave open to the user | `analysis/gaps.md` | `human` gate after stage 2, `redoable`; each question has a suggested answer |
| 4 | Spec | Screens, fields, actions, the three states, journeys, acceptance lines | `spec.md`, `journeys.md` | Every requirement and screen appears in the spec; no TBD |
| 5 | Design | Information architecture, layout rules, tokens, components, accessibility | `design.md` (and `build/screens.json` if the screen plan is checked) | Every screen in the spec has a design entry |
| 6 | Build | One self-contained HTML file, one route per screen, every journey clickable | `prototype.html` | `html_static`, `html_render`, `fix` with `max_attempts: 2` |
| 7 | QA | Check the file against the spec and journeys; send a revision back to Build | review notes; a `pass` or `revise` decision | Critic loop, `loop_max_iterations: 2`, `on_loop_exhausted: continue` |

Lite merges stages 4 and 5 into one step (spec with design phases) and drops stage 7.

## Where the human answers

Stage 3 is the only human gate. Put it after the stage that finds the gaps (stage 2), never
before the reading. A gate before the reading asks questions the documents may already answer.
The user answers with Request changes; the analyst re-runs with the answers as guidance.

## Validators at user trust

- `html_static` and `html_render`: structure and navigation of `prototype.html`. Use them on
  the build step with `fix: {"max_attempts": 2}`.
- `design_quality` (warnings only): optional, on the build step.
- `journeys_coverage`: when `journeys.md` and `notes/doc-*.md` exist.
- `screens_plan_coverage`: when the design writes `build/screens.json`.
- `spec_plan_coverage`: when a plan lists tasks that must cover the spec.

No validator checks length, tone or facts. Put those limits in the prompts of the spec and
design steps, and say in the response that only the prompts enforce them.

## What each step must check before it finishes

- Read: every upload has a note.
- Analyze: every requirement has an ID and a source; every screen lists the requirements it serves.
- Spec: every screen has the empty, loading and error states; every journey has an alternate
  path for each action that can fail.
- Design: every screen has a layout entry; interactive elements have a visible focus state.
- Build: every screen ID has a route; every journey is clickable from start to end.
- QA: every requirement ID is covered by a journey or a screen.

## Traps

- A one-step "build the prototype from the request" skips the spec. Do not use it for a
  document-based request.
- Writing the spec after the build leaves the build with nothing to check against.
- A gate on a worker step (for example on each screen's builder) stops the run for every
  screen. Gate the analyst, never the workers.
- Asking the user about visual style at stage 3. Style is the design step's job.

## Shipped reference

`examples/prototype_from_documents.workflow.json` is the Lite shape with four steps (read,
analyze with a human gate, spec, build). Extend it with the design and QA stages above
when the depth is Full. Compare `catalog_lookup.py example prototype_v2` for the stage list of
the platform's own prototype workflow at file trust.
