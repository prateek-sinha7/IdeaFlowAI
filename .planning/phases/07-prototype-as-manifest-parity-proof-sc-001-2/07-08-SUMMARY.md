---
phase: 07-prototype-as-manifest-parity-proof-sc-001-2
plan: 08
subsystem: characterization/oracle (test-only)
tags: [parity, oracle, context_message, cluster-C, gap-closure, acd1636]
requires:
  - 07-07 (cluster-B/golden-safe restorations landed before the cluster-C measuring stick)
provides:
  - "engine-independent pre-Phase-7 (acd1636) context_message oracle for the 4 prototype agent classes"
  - "the 07-09 acceptance target: a tracked xfail proving the current routed build prompt diverges from the oracle"
affects:
  - 07-09 (will correct the engine/provider so the routed build prompt == oracle, then flip the xfail to PASS and re-pin the 5 goldens)
tech-stack:
  added: []
  patterns:
    - "PINNED-BYTES oracle: verbatim legacy block strings + provenance comments, assembled engine-independently against a small deterministic od_context fixture"
key-files:
  created:
    - backend/tests/agents/characterization/oracle/__init__.py
    - backend/tests/agents/characterization/oracle/legacy_context_message.py
    - backend/tests/agents/test_context_message_oracle.py
  modified: []
decisions:
  - "Used PINNED-BYTES (not PINNED-OLD-ENGINE): running legacy _build_context_message at test time would re-couple the oracle to the engine + live od_loader disk reads — the exact coupling the oracle must avoid; verbatim pinned strings with acd1636 provenance keep it independent and reviewable"
  - "Pinned baseline to acd1636 (deep-review ref); recorded that 07-06 used 1d9234b^ and that the _is_builder example gate is present at BOTH refs, so the baseline choice does not affect the encoded example gate"
  - "Left the 5 characterization goldens UNTOUCHED — regenerating before the engine is corrected would re-pin the same drifted bytes; re-pinning to oracle ground truth is 07-09 work"
metrics:
  duration: ~25m
  completed: 2026-06-09
  tasks: 2
  files: 3
---

# Phase 07 Plan 08: Pre-Phase-7 context_message Oracle (Cluster C step 1) Summary

Built an engine-independent ORACLE that reconstructs the TRUE pre-Phase-7 (`acd1636`) assembled `context_message` bytes for the four prototype agent classes, and a test that pins the oracle while proving the current routed build prompt has drifted from it — the measuring stick and acceptance target the cluster-C restorations in 07-09 will close.

## What This Plan Did

This plan REVERSES the 07-06 adjudication. The 07-06 gap-closure de-blinded the characterization goldens by capturing POST-refactor `context_message` bytes via `SNAPSHOT_UPDATE=1` — but those bytes had ALREADY drifted from the true pre-Phase-7 prompt (CR-01/CR-02/CR-04). So "pinned == correct" was false (07-REVIEW-DEEP.md systemic[0]). Without an independent ground truth, every cluster-C "byte-exact restoration" would be asserted against a drifted golden and re-pin the wrong contract.

**Task 1** — Captured the legacy bytes as `oracle/legacy_context_message.py`. `build_oracle_message(agent_class, *, task="")` reconstructs the assembled message for `prototype-specify`, `prototype-plan`, `prototype-build` task 1, and `prototype-build` task 2. Capture mechanism is PINNED-BYTES: each legacy block string is pinned verbatim with a `# provenance: acd1636:...` comment and assembled with the legacy `"\n".join(parts)` order against a small deterministic `od_context` fixture. The oracle honors every acd1636 gate verbatim:
- per-`injects` gate (DS requires `design_system in injects`; template/example/parts require `template in injects`),
- `is_build_task_2_plus` suppression of DS body / template body / example / non-seed parts,
- the `_is_builder` example gate (`set(tools) & {prototype_emit_only, prototype}` — planning agents get NO example),
- RAW `parts.append(part)` for injection parts (un-rewrapped),
- BARE `=== END ACTIVE DESIGN SYSTEM ===` markers (no `: {id}` suffix),
- the task-2+ skeleton wrapper with the `read_file('prototype.html')` instruction + `[Error:` suppression,
- the UNCONDITIONAL `=== TEMPLATE COMPLIANCE ===` block on every build task.

**Task 2** — Wrote `test_context_message_oracle.py`: (1) oracle stability + legacy structural-marker assertions (all PASS), (2) a DIVERGENCE test that drives `_drive("prototype")`, extracts the build-agent `context_message` from the `agent_input` events, and asserts it does NOT yet equal the oracle — marked `xfail(strict=False)` with a docstring naming it the 07-09 acceptance target. A companion hard-PASS test pins the specific CR-01 drift (routed build prompt lacks TEMPLATE COMPLIANCE) so the divergence is non-vacuous.

## How the Divergence Manifests (the drift the de-blind masked)

| Finding | Legacy (oracle) | Current routed | 
|---------|-----------------|----------------|
| CR-01 | unconditional `=== TEMPLATE COMPLIANCE ===` on every build task | absent |
| CR-02 | `=== END ACTIVE DESIGN SYSTEM ===` (bare); DS only with `design_system in injects` | `=== END ACTIVE DESIGN SYSTEM: default ===`; DS leaks on any non-empty injects |
| CR-04 | injection parts RAW (`=== TEMPLATE SEED ... ===` only) | double-wrapped in `=== TEMPLATE INJECTION PART N: ... ===` |
| skeleton/HTML | task-2+ `=== CURRENT PROTOTYPE (skeleton — call read_file ...) ===`; task-1 CURRENT HTML | composed by task_loop strategy, not the engine branch |

## Verification

```
cd backend && python3.11 -m pytest tests/agents/test_context_message_oracle.py -q -rx
# 6 passed, 1 xfailed
```
- Oracle stability test PASSES; structural-marker tests PASS.
- Divergence test XFAILS (expected — the engine is still drifted). This is the 07-09 acceptance target.
- The five `golden/*.events.json` characterization goldens are NOT modified by this plan (`git diff --stat HEAD -- backend/tests/agents/characterization/golden/` is empty).

## Success Criteria

- [x] Oracle module created, reconstructing TRUE acd1636 context_message bytes engine-independently with per-block provenance.
- [x] Stability test PASSES; oracle contains the legacy structural markers (TEMPLATE COMPLIANCE on build tasks, bare END markers, skeleton wrapper with read_file, un-rewrapped injection parts).
- [x] Divergence test XFAILS — proves today's routed context_message != oracle; documented as the 07-09 acceptance target.
- [x] The 5 characterization goldens are NOT modified by this plan (git diff shows golden/*.events.json unchanged).
- [x] Each task committed individually; SUMMARY.md created.

## Deviations from Plan

None - plan executed exactly as written. Task 1 offered Claude's discretion between PINNED-BYTES and PINNED-OLD-ENGINE; chose PINNED-BYTES (documented in Decisions) — this is a sanctioned in-plan choice, not a deviation.

## Notes for 07-09

- The xfail `test_current_routed_build_prompt_diverges_from_oracle` is the acceptance target. After 07-09 corrects the engine/provider, this xpasses → remove the `@pytest.mark.xfail`.
- `test_routed_build_prompt_is_missing_template_compliance_today` asserts CR-01 is present TODAY; after 07-09 restores TEMPLATE COMPLIANCE this assertion must be inverted (the test docstring flags this).
- ONLY after the routed build prompt equals the oracle should 07-09 regenerate the 5 goldens with `SNAPSHOT_UPDATE=1` and additionally assert the regenerated build-agent `context_message` equals the oracle (closing the loop). Regenerating before then re-pins the drifted bytes.
- Baseline note: oracle pins to `acd1636`; 07-06 reasoned against `1d9234b^`; the `_is_builder` example gate exists at both, so the example gate is baseline-invariant.

## Self-Check: PASSED

All created files exist on disk; both task commits (`2bc175d`, `ac382af`) exist in git history.
