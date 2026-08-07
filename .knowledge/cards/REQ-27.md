---
id: REQ-27
type: req
status: done
area: [workflow, agents, auth, artifacts]
summary: >-
  Shell Convergence (Phases 35–38, closed to mock fidelity in Phase 40 [B6])
source: .planning/REQUIREMENTS.md#shell-convergence-phases-35-38-closed-to-mock-fi
---

### Shell Convergence (Phases 35–38, closed to mock fidelity in Phase 40 [B6])

- [ ] **SHELL-01**: Shell chrome (dark top bar, nav pill Home·Library·My Workflows, profile menu, notifications) + reskin-only pages (Settings, pickers, Library) on the token layer
- [x] **SHELL-02**: Fused Home (launcher+grid+recents); History grouping/sort/delete; **My Workflows** rename + kebab actions; `WorkflowCatalog`→`HomeLaunchGrid`; "Catalogue" reserved for future marketplace (D-11)
- [x] **SHELL-03**: Run detail/reopen page off a run-summary endpoint aggregating existing data (agents, KPIs, failure banner, version timeline)
- [ ] **SHELL-04**: Generic Configure surface (Describe/Templates/DS/Gates/Settings for every deliverable) + Agent drawer + Workflow dialog with `user_allowed` gating (ND-1/ND-7/ND-8 gated) — **closed-by-Phase-41 [B7]**: the mock-fidelity rebuild of the single Configure screen (CFGUI-01/02) + the Library agent-detail drawer (CMPUI-05) close this requirement's Configure-surface + Agent-drawer clauses.
- [x] **SHELL-05**: Date-scoped analytics aggregations + chart components + per-deliverable estimates + notifications feed
