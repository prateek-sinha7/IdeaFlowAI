# Agile / Scrum Writing Rules

## User Story Format

Every user story must follow the canonical form:
**As a** [specific persona], **I want** [concrete capability], **so that** [measurable business outcome].

- Reference a named persona from the domain analysis — never write "a user" or "the system".
- The "I want" clause must describe a single, deliverable capability.
- The "so that" clause must state a measurable or observable benefit.

## Story Sizing

Stories must be small enough for one sprint (1–5 days of work for a competent engineer).
Use Fibonacci story points: 1, 2, 3, 5, 8, or 13.

- 1 pt: Config change or copy update (under 2 hours)
- 2 pts: Simple CRUD or single component (half day)
- 3 pts: Moderate — multiple components, some logic (1 day)
- 5 pts: Complex — API + UI + validation + tests (2–3 days)
- 8 pts: Very complex — multiple integrations or unknowns (1 week)
- 13 pts: Must be split into smaller stories before acceptance

## Acceptance Criteria

Write acceptance criteria in Gherkin format: **Given** [precondition], **When** [action], **Then** [observable outcome].

- Cover the happy path plus at least one error or edge case per story.
- Use specific values, states, and behaviours — not vague language like "works correctly".
- Non-functional acceptance criteria (latency, throughput, accessibility, security) must be measurable.

## Epic Structure

Group related stories under an epic with a clear business value statement.
Assign a priority label to every epic: P0 (must-have for launch), P1 (should-have), P2 (nice-to-have).

## INVEST Checklist

Every story must satisfy INVEST before it is accepted into a sprint:
- **Independent**: can be developed without blocking another story
- **Negotiable**: scope can be discussed with the team
- **Valuable**: delivers value to a named persona
- **Estimable**: team can assign story points
- **Small**: fits within one sprint
- **Testable**: acceptance criteria are verifiable

## Definition of Done

Each story is done when: code is merged, tests pass at the stated coverage threshold,
documentation is updated, telemetry is emitted, and accessibility has been checked.
