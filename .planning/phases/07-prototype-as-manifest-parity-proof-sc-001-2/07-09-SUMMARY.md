---
phase: 07-prototype-as-manifest-parity-proof-sc-001-2
plan: 09
subsystem: engine/capabilities (context_message parity restoration)
tags: [parity, cluster-C, gap-closure, oracle, context_message, CR-01, CR-02, CR-04, WR-01, WR-02, WR-03, WR-05]
requires:
  - 07-08 (the acd1636 oracle + the tracked xfail divergence target)
provides:
  - "the routed prototype-build context_message restored byte-equal to the pre-Phase-7 (acd1636) oracle (CR-01/02/04, WR-01, WR-03)"
  - "per-injects per-block gate restored on the opendesign provider (example.html still gated to builders — 07-06 CR-02 intact)"
  - "RAW (un-rewrapped) injection-part emission via a provider sentinel + bare END markers in the engine injector"
  - "task_loop re-persists the typed prototype-build artifact after a fix iteration (WR-05) so prototype-validate reads the FIXED HTML"
  - "the 5 characterization goldens regenerated to oracle ground truth (drift de-pinned)"
affects:
  - 07-10/07-11 (verification + phase close: the routed prompt now == oracle, the goldens pin ground truth)
tech-stack:
  added: []
  patterns:
    - "RAW_BLOCK_PREFIX sentinel on a provider block-name key signals the generic injector to append the content verbatim (pre-wrapped) — preserves the dict[str,str] ContextProvider port while restoring legacy raw parts.append(part)"
    - "parametrized oracle: build_oracle_message accepts the dynamic CONTENT (od_context/parts/example/skeleton/task_body/planning/consumed) so the routed message asserts byte-equal over identical content — the GATE LOGIC stays pinned from acd1636"
key-files:
  created: []
  modified:
    - backend/agents/execution_engine/engine.py
    - backend/agents/capabilities/context_providers/opendesign.py
    - backend/agents/execution_engine/kernel_services.py
    - backend/agents/capabilities/strategies/task_loop.py
    - backend/agents/capabilities/deliverables/ppt.py
    - backend/tests/agents/test_context_message_oracle.py
    - backend/tests/agents/test_context_providers.py
    - backend/tests/agents/test_strategies.py
    - backend/tests/agents/test_deliverable_resolvers.py
    - backend/tests/agents/characterization/oracle/legacy_context_message.py
    - backend/tests/agents/characterization/golden/prototype.events.json
    - backend/tests/agents/characterization/golden/od_prototype.events.json
    - backend/tests/agents/characterization/golden/od_ppt.events.json
decisions:
  - "CR-04 raw injection parts via a RAW_BLOCK_PREFIX key sentinel (kept the dict[str,str] port) rather than a second return channel — minimal seam, the injector strips the sentinel and appends verbatim"
  - "Skeleton (WR-01) + TEMPLATE COMPLIANCE (CR-01) emitted by the ENGINE in the CURRENT-TASK build region (after the CURRENT TASK block), NOT by the provider — the provider blocks are appended before consumed-outputs/CURRENT-TASK, so emitting these in the engine preserves the legacy byte ORDER"
  - "WR-01 skeleton threaded onto ectx.current_prototype_skeleton via a new run_agent(skeleton=...) param (scratch reset in finally), sourced from the TYPED graph latest_typed_content('prototype-build') with the [Error: guard — not the raw disk read"
  - "WR-02: confirmed the NEW unwrap(sanitize(x)) order is byte-EQUIVALENT to the legacy sanitize(unwrap(x)) on an <artifact>-wrapped carousel — kept NEW, pinned the equivalence (no behavior change needed)"
  - "Parametrized the oracle so byte-equality is over IDENTICAL dynamic content (the routed path reads real disk template bytes; the oracle fixture is tiny) — the comparison verifies the legacy gate-logic/ordering/wrapper CONTRACT, the true target"
metrics:
  duration: ~75m
  completed: 2026-06-09
  tasks: 3
  files: 13
---

# Phase 07 Plan 09: Cluster C Part 2 — Per-Finding Parity Restorations vs the Oracle Summary

Restored the routed prototype-build `context_message` byte-equal to the pre-Phase-7 (`acd1636`) oracle from 07-08, closing the seven cluster-C findings (CR-01/02/04, WR-01/02/03/05); flipped the 07-08 divergence xfail to a hard byte-equality PASS, then regenerated the 5 characterization goldens to oracle ground truth and added a loop-closing assertion proving the regenerated goldens pin the oracle (not the drift).

## What This Plan Did

**Task 1 — context_message byte contract (CR-01, CR-02, CR-04, WR-03).** Restored the legacy injector contract measured against the 07-08 oracle:
- **CR-02 (per-injects gate):** the engine now threads the consuming agent's DECLARED `injects` onto the ExecutionContext (`current_spec_injects`, the same D-03 per-run-state-on-ctx mechanism as `current_spec_tools`). The opendesign provider gates the DS block on `"design_system" in injects` and the template/example/injection-parts on `"template" in injects` — the legacy per-block gate. The `is_builder` example gate is kept EXACTLY (07-06 CR-02 not re-opened): a tools:[] planning agent gets the template body + (no) parts but NEVER the example.html — asserted by a new guard test (T-07-09-01).
- **CR-04 (raw injection parts):** the provider marks injection-part blocks with a `RAW_BLOCK_PREFIX` key sentinel; the engine injector strips the sentinel and appends the part VERBATIM (legacy `parts.append(part)`) — no `=== TEMPLATE INJECTION PART N: ... ===` outer wrapper.
- **WR-03 (bare END markers):** the injector now emits `=== END {base} ===` where `{base}` strips BOTH the `: {id}` suffix AND the `(SKILL.md)` / `(example.html)` parenthetical — restoring `=== END ACTIVE DESIGN SYSTEM ===` / `=== END ACTIVE TEMPLATE ===` / `=== END TEMPLATE EXAMPLE ===`.
- **CR-01 (TEMPLATE COMPLIANCE):** re-emitted UNCONDITIONALLY on every build task in the engine's CURRENT-TASK build region, gated on the build signal (`build_task_number` + builder tool set), NOT a workflow name (INV-1).
- Parametrized `build_oracle_message` (od_context/parts/example/skeleton/task_body/planning/consumed) and flipped the 07-08 xfail to a hard `routed == oracle` byte-equality PASS (task 1).

**Task 2 — build-skeleton wrapper (WR-01).** `task_loop` now sources the task-2+ skeleton from the TYPED graph (`latest_typed_content("prototype-build")`) with the legacy `[Error:` suppression and threads it via a new `run_agent(skeleton=...)` param onto `ectx.current_prototype_skeleton` (scratch reset in `finally`). The engine emits the legacy STANDALONE `=== CURRENT PROTOTYPE (skeleton — call read_file('prototype.html') for full content before editing) ===` block AFTER the CURRENT TASK block, byte-exact — replacing the drifted nested `=== CURRENT PROTOTYPE SKELETON ===` form. Task-2 byte-equality is now a hard PASS.

**Task 3 — ppt order (WR-02), typed re-persist (WR-05), goldens.**
- **WR-02:** built the documented `<artifact>`-wrapped carousel repro and confirmed `unwrap(sanitize(x))` (NEW) is byte-EQUIVALENT to `sanitize(unwrap(x))` (LEGACY) — sanitize only touches in-deck CSS that survives both orderings, and unwrap discards outer bytes. Kept NEW; pinned the equivalence with a test and documented the finding in `ppt.py`.
- **WR-05:** `task_loop` snapshots the on-disk HTML before the fix-loop and RE-PERSISTS the typed prototype-build artifact when the post-fix HTML changed (mirrors the legacy `fixed_html != task_html` re-write), so `prototype-validate` reads the FIXED HTML. Added a fix-iteration test + a negative (no-change → no redundant re-persist) test.
- Regenerated the drifted goldens (prototype/od_prototype/od_ppt) to the corrected oracle-equal bytes; `prototype_revision`/`app_builder` were unchanged (no drift). Added the loop-closing assertion: the regenerated golden build-agent `context_message` == the acd1636 oracle (T-07-09-02).

## How the Restoration Closes the Drift

| Finding | Drifted (07-06 pinned) | Restored (07-09, == oracle) |
|---------|------------------------|------------------------------|
| CR-01 | TEMPLATE COMPLIANCE absent | unconditional on every build task |
| CR-02 | DS leaked on any non-empty injects | per-block per-injects gate; example still builder-only |
| CR-04 | parts double-wrapped `=== TEMPLATE INJECTION PART N ===` | RAW (parts carry own envelope) |
| WR-03 | `=== END ACTIVE DESIGN SYSTEM: default ===` | bare `=== END ACTIVE DESIGN SYSTEM ===` |
| WR-01 | nested `=== CURRENT PROTOTYPE SKELETON ===` in task block | standalone block w/ read_file instruction + `[Error:` guard |
| WR-02 | NEW order (suspected divergent) | confirmed equivalent — kept NEW |
| WR-05 | typed artifact stale after fix | re-persisted when on-disk HTML changed |

## Verification

```
python3.11 -m pytest tests/agents/test_context_message_oracle.py -q     # 10 passed (incl byte-equality + golden==oracle)
python3.11 -m pytest tests/agents/test_context_providers.py -q          # 15 passed (per-injects gate + example-leak guard)
python3.11 -m pytest tests/agents/test_characterization_*.py -q         # 10 passed (5 pipelines, goldens oracle-equal)
python3.11 -m pytest tests/agents/test_strategies.py tests/agents/test_deliverable_resolvers.py -q  # passed (WR-01/WR-05/WR-02)
grep -nE "if pipeline_type|spec\.id ==" engine.py opendesign.py        # 0 matches (INV-1 preserved)
python3.11 -m pytest tests/agents/ -q                                   # 569 passed, 19 skipped, 0 failed (no regression)
```

- Routed build/specify/plan context_message == oracle byte-for-byte (task 1 + task 2 hard PASS).
- `is_builder` example gate intact — tools:[] planning agents get NO example (07-06 CR-02 not re-opened).
- 5 goldens regenerated; the regenerated build-agent context_message == the oracle (loop closed).
- INV-1 grep = 0 on engine + opendesign + task_loop + ppt.

## Success Criteria

- [x] All 7 findings restored: CR-01, CR-02, CR-04, WR-01, WR-02 (confirmed equivalent), WR-03, WR-05.
- [x] Routed build/specify/plan context_message == oracle byte-for-byte (07-08 divergence xfail flipped to hard PASS).
- [x] `is_builder` example gate intact — tools:[] planning agents get NO example.
- [x] 5 goldens regenerated to oracle ground truth; characterization suite passes; golden==oracle asserted.
- [x] No spec.id/pipeline_type branch introduced (INV-1 grep = 0).
- [x] Each task committed individually; SUMMARY.md created.

## Deviations from Plan

None — plan executed as written. The plan offered Claude's discretion on the WR-01 seam (option a vs b) and on the WR-02 confirm-then-fix outcome:
- **WR-01 seam:** chose option (a) — `task_loop` sets a dedicated `ectx.current_prototype_skeleton` scratch (threaded via a new `run_agent(skeleton=...)` param) and the engine emits the standalone block in the legacy position. Documented in Decisions; sanctioned in-plan choice.
- **WR-02:** the confirm step found the two orderings byte-EQUIVALENT on the wrapped-carousel repro, so per the plan's "if identical … keep NEW and add a test asserting equivalence" branch, the NEW order was kept and the equivalence pinned. Documented in `ppt.py` + a test. Sanctioned in-plan choice, not a deviation.

## Self-Check: PASSED

All modified files exist on disk; all three task commits (`54e0bef`, `f8ccdb2`, `0b7ada2`) exist in git history.
