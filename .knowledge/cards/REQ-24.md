---
id: REQ-24
type: req
status: done
area: [workflow, artifacts]
summary: >-
  Shell Mock Fidelity (Phase 40 [B6])
source: .planning/REQUIREMENTS.md#shell-mock-fidelity-phase-40-b6
---

### Shell Mock Fidelity (Phase 40 [B6])

Phase 40 [B6] is the shell-convergence completion — it does NOT mint new requirement
ids; it OWNS and closes the existing **SHELL-01..04** (defined under "Shell
Convergence (Phases 35–38)" below) through the same anti-drift, mock-fidelity method
Phase 39 used for the run screen. The four Phase-40 success criteria map onto them as
a fidelity lens (Wave 1 = 40-01 harness; Wave 2 = 40-02..07 surfaces; the Configure/
Composer rebuild defers to Phase 41):

- **SHELL-01 (Phase 40 SC-1 — fidelity):** Each in-scope shell surface + every sub-view/sub-tab/state matches its `Hexaware Workspace v2` mock to the intended-divergence register (ND-A..D carried + ND-W..Z), proven by the side-by-side shell gallery (`gallery-shell.html`) + a HUMAN sign-off — not a prose claim.
- **SHELL-02 (Phase 40 SC-2 — as-is affordances):** The net-new as-is affordances land on live data — Home 3×2 deliverable card grid + "Jump back in" recents, Library card grids, Settings richer profile form, History filter chips / Sort tabs / date groups, the Catalogue grid.
- **SHELL-03 (Phase 40 SC-3 — live data / SC-001):** Data stays real & live (SC-001/ND-D) — no cloned mock values, no fabricated fields (ND-Y); existing components reused, chrome/layout rebuilt; intended divergences (ND-A brand · ND-B "My Workflows" · ND-C nav underline · ND-W "Run History" · ND-X no Voice · ND-Y no fabricated profile fields · ND-Z Library drawer → Phase 41) preserved.
- **SHELL-04 (Phase 40 SC-4 — oracle + green specs):** The blocked Catalogue is stubbed (`/api/user-workflows`) + the empty surfaces seeded, the shell fidelity oracle is formalized (repo-relative, `SHELL_CAPTURE`-gated, per-surface `--surface` gallery regeneration), and each touched surface's mocked-e2e spec is re-anchored green.
