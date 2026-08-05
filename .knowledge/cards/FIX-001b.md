---
id: FIX-001b
type: fix
date: 2026-06-16
status: done
area: [backend, agents, artifacts]
files:
  - backend/agents/prompts/od-ppt-validator/AGENT.md
  - backend/agents/prompts/od-ppt-composer/AGENT.md
summary: >-
  Harden od-ppt-validator output contract (remove checklist-as-preamble loophole) +
  fix od-ppt-composer filesystem tool calls on Windows
source: .planning/FIX-REGISTER.md#fix-001
collision_of: FIX-001
invariants: [INV-1, INV-3, INV-12, SC-001]
---

# FIX-001b

> **Reused id.** The register uses `FIX-001` for more than one unrelated
> fix. This card is one of them; the suffix exists only here, so that one card
> means one fix. The register itself is unchanged — see `source:`.

**Phase / trigger:** Phase 15

> No detail section exists in the register for this entry — only the
> summary-table row below. Nothing has been invented to fill the gap.

## Description

Harden od-ppt-validator output contract (remove checklist-as-preamble loophole) + fix od-ppt-composer filesystem tool calls on Windows

## Root cause

Validator: "two short sentences" loophole allowed model to print full checklist as preamble without <artifact> wrapper → raw checklist rendered as deck. Composer: deepagents filesystem glob crashes on Windows (pathlib.rglob ValueError) → composer told to use context-injected files instead of tool calls

## Files changed

- `backend/agents/prompts/od-ppt-validator/AGENT.md`
- `backend/agents/prompts/od-ppt-composer/AGENT.md`
