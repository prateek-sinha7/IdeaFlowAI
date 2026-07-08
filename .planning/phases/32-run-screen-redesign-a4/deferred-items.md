# Phase 32 — Deferred Items

Out-of-scope discoveries logged during execution (not fixed by the discovering plan).

- **[plan 06] Pre-existing AgentProgressPanel test failure** — `src/components/workflow/AgentProgressPanel.test.tsx > "treats a _revision completion the same as its base for the filter"` fails on the committed baseline (asserts the "Presentation" chip is hidden for a `ppt_revision` run; the component still renders it). File untouched by plan 06 (last committed 812ea7bd); does not import RunChatLane/DashboardLayout/PreviewPanel. Outside plan 06 verification scope (chat/ + layout/). Not fixed per scope boundary. Owner: AgentProgressPanel chaining-filter or plan-08 Steps relocation.
