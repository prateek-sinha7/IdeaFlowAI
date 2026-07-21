# Phase 32 — Deferred Items

Out-of-scope discoveries logged during execution (not fixed by the discovering plan).

- **[plan 06] Pre-existing AgentProgressPanel test failure** — `src/components/workflow/AgentProgressPanel.test.tsx > "treats a _revision completion the same as its base for the filter"` fails on the committed baseline (asserts the "Presentation" chip is hidden for a `ppt_revision` run; the component still renders it). File untouched by plan 06 (last committed 812ea7bd); does not import RunChatLane/DashboardLayout/PreviewPanel. Outside plan 06 verification scope (chat/ + layout/). Not fixed per scope boundary. Owner: AgentProgressPanel chaining-filter or plan-08 Steps relocation.

- **[plan 08] Pre-existing workflow/ suite failures (4), out of scope** — surfaced while running the plan-08 broad delta suite; all in files this plan never touched and none import AgentThinkingTab/WaveTreePanel/PreviewPanel:
  1. `workflow/ReviewGatesSection.test.tsx > "PIPELINE_CATEGORIES counts are reconciled (ppt=3, prototype=4, all=54)"` — LIBRARY_AGENTS data-integrity count mismatch (AgentLibraryData, Phase 37 composer/config territory).
  2. `workflow/ReviewGatesSection.test.tsx > "each non-custom category count matches the LIBRARY_AGENTS membership"` — same LIBRARY_AGENTS reconciliation.
  3. `workflow/ReviewGatesSection.test.tsx > "unchecking ALL gates yields onChange([], true)"` — ReviewGatesSection gate-payload, unrelated to the Steps render path.
  4. `workflow/IdeaInputPage.declaredCapabilities.test.tsx > "fetches the compiled projection … 'Declared by this workflow' strip"` — SURF-03 live-fetch wiring (network-gated).
  Structurally impossible for a WaveTreePanel/AgentThinkingTab reskin to cause (data reconciliation + network fetch). Not fixed per scope boundary.
