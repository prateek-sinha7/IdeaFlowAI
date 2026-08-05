---
id: FIX-049b
type: fix
date: 2026-07-10
status: done
area: [frontend, agents]
files:
  - frontend/src/components/results/AgentDetailPanel.tsx
summary: >-
  Live agent output not visible while a prototype agent runs — the Steps L2 detail
  "live" card was blank for every running agent (spec-writer / plan / analyze / build)
source: .planning/FIX-REGISTER.md#fix-049
collision_of: FIX-049
invariants: [INV-3, SC-001]
---

# FIX-049b

> **Reused id.** The register uses `FIX-049` for more than one unrelated
> fix. This card is one of them; the suffix exists only here, so that one card
> means one fix. The register itself is unchanged — see `source:`.

**Phase / trigger:** Phase 39/42 (run-screen Steps detail) · commit 182200b1

> No detail section exists in the register for this entry — only the
> summary-table row below. Nothing has been invented to fill the gap.

## Description

Live agent output not visible while a prototype agent runs — the Steps L2 detail "live" card was blank for every running agent (spec-writer / plan / analyze / build)

## Root cause

The engine emits only agent_chunk (the model's streamed output) per agent, never a separate agent_thinking event, so agent.thinkingText is ALWAYS empty — but AgentDetailPanel fed its live card from thinkingText, so a running agent showed a blank "Reasoning (live)" cursor with no text. Fix (FE-only): feed the live agent.output (from agent_chunk) into the card instead, labelled "Output (live)", scrollable + auto-follows the streaming tail; the completed output still renders via OutputPreviewSection. Verified fail-before/pass-after with a new spec.

## Files changed

- `frontend/src/components/results/AgentDetailPanel.tsx`
