---
name: goal-v2-spec-plan
display_name: Goal v2 — Spec and Plan
description: How to write a traced spec and a compact task list (10–12 tasks) with one output assembly per request type, so independently built pieces fit together. Use in the spec + plan step of goal_v2.
category: workflow
isBeta: false
tags:
- spec
- planning
- tasks
---

# Spec and plan (v2)

Write `spec.md` and `tasks.json`. `ledger_check` mode `coverage` must be clean before you finish.

## spec.md

1. **Intent** — from `.goal/intent.json`; profile; template and design.
2. **`## Screens` table** — columns `Screen id | Source | Purpose`; `template (<home screen id>)` for the screen
   that replaces the template's home screen (as named in `.context/design/template/SKILL.md`, when it names one),
   `new (copies <id>)` for others, `new` with no template. Lower-case kebab-case ids.
3. **Architecture (web tools) — mandatory section.** One page, one app script, these modules in this order:
   - `parse` — one parser per input message type, local-name matching, returning plain objects;
   - `state` — one shared state object for both workspaces (ids, loaded messages, user inputs);
   - `rules` — pure functions returning blocks and warnings per use case;
   - `build` — **one XML writer per output request type**. The writer emits the whole document: declaration,
     root with namespaces, DistributionChain, PayloadAttributes, Request. Use-case code supplies only the inner
     Request content as data or element calls — never a finished document and never its own declaration;
   - `render` — writes the screens from state; one output panel per workspace.
   Name the shared function each use case calls. Pieces built by different tasks must meet through these names.
4. **Per screen** — Purpose, Layout, Fields, Actions, States, Requirements (`ids:`), and the `data-test` names
   the acceptance tests use.
5. **Rules** — one line per rule with its ids.
6. **Output** — formats, file names, element order, namespaces (copy them from the sample messages), indent.
7. **Not built** — every `constraint` row.

## tasks.json — compact

```json
{"tasks": [{"id": "T01", "title": "...", "ids": ["G1", "G2"], "acceptance": [".goal/acceptance/G1.json"],
            "depends_on": [], "targets": ["prototype.html"], "body": "..."}]}
```

Aim for **10–12 tasks**: (1) shell, settings, loading and the parse module; (2) state + the shared XML writer and
output panels; then **one task per use case** (screens, rules and its Request content together); then
non-functional (keyboard, theme, responsive). Every ledger id in at least one task; every task lists its
acceptance files and the `data-test` names they target; the body names the shared functions to use.
