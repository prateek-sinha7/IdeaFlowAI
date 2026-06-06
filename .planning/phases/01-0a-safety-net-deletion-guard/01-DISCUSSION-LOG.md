# Phase 1: [0A] Safety Net + Deletion Guard - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-06
**Phase:** 1-[0A] Safety Net + Deletion Guard
**Mode:** `--auto` (autonomous — recommended option auto-selected for each area; grounded in a codebase scout)
**Areas discussed:** Characterization harness, Snapshot format, Migration ledger SoT, Static gates config, Banned-pattern gate, CI wiring

---

## Characterization harness

| Option | Description | Selected |
|--------|-------------|----------|
| Reuse/extend `_scripted_model.py` | Build on the existing `_drive()`/`ScriptedFakeChatModel` offline driver | ✓ |
| Rebuild a fresh harness | Author a new scripted-model + driver from scratch | |

**Auto choice:** Reuse/extend (recommended). The harness already runs `execute()` offline and returns ordered event dicts — exactly what SAFE-01/02 need.
**Notes:** Existing `test_phaseN_*` files use 002-era numbering — flagged to avoid confusion with 003's `[0A]…[6]`.

## Snapshot format

| Option | Description | Selected |
|--------|-------------|----------|
| Hand-rolled golden files + `_normalize()` | Commit golden deliverables + normalized event JSON; custom volatile-field stripping | ✓ |
| `syrupy` plugin | Add the syrupy pytest snapshot dependency | |

**Auto choice:** Hand-rolled golden files (recommended). No new dep; full control over normalization; matches the deleted `_serialize` precedent.
**Notes:** Deliverable byte-snapshot + semantic event snapshot; `seq` asserted contiguous, not absolute.

## Migration ledger source of truth

| Option | Description | Selected |
|--------|-------------|----------|
| Standalone `specs/003-.../migration-ledger.md` | Mirror §31 table; `test_migration_ledger.py` greps `☑` rows → 0 | ✓ |
| Assert directly against plan.md §31 | Parse the table inside plan.md | |

**Auto choice:** Standalone ledger file (recommended; plan §31 explicitly sanctions this mirror).
**Notes:** All rows start `☐` in Phase 1 → guard green; rows flip to `☑` (enforced ratchet) in their owning phases.

## Static gates config (import-linter + dead-code)

| Option | Description | Selected |
|--------|-------------|----------|
| `backend/pyproject.toml` + vulture in requirements-dev | import-linter `[tool.importlinter]`; add vulture; reuse existing ruff/pyright | ✓ |
| Separate `.importlinter` + shell dead-code script | Standalone config files | |

**Auto choice:** pyproject + vulture (recommended). Centralizes config; ruff/pyright/pre-commit already present.
**Notes:** Kernel→ports contract scaffolded green now (kernel still `engine.py`); tightens in Phase 7/8 without rewrite.

## Banned-pattern gate (INV-13 / R15)

| Option | Description | Selected |
|--------|-------------|----------|
| pytest test `test_banned_patterns.py` | Grep-based assertions inside the test job; readable failures; ratchet | ✓ |
| CI-only shell grep | Inline `grep` step in `.gitlab-ci.yml` | |

**Auto choice:** pytest test (recommended). Runs in the test job, is a ratchet, fails readably.
**Notes:** Allow-lists the real `from deepagents import create_deep_agent` + the one adapter module. INV-1 (`pipeline_type`/`spec.id`) seeded warn-only in Phase 1 → hard-fail in Phase 7.

## CI wiring

| Option | Description | Selected |
|--------|-------------|----------|
| Lint stage gates + dedicated characterization test job | import-linter+vulture in `backend:lint`; new offline `backend:characterization` job for snapshots/ledger/banned | ✓ |
| Extend the existing `tests/unit` command | Add `tests/agents` to the current pytest invocation | |

**Auto choice:** Lint-stage gates + dedicated job (recommended).
**Notes:** Critical finding — CI today runs only `tests/unit`, so `tests/agents` characterization tests are currently unrun and must be explicitly added (SAFE-07).

## Claude's Discretion

- Golden-file directory layout + exact `_normalize()` field list.
- Vulture config mechanism (pyproject `[tool.vulture]` + whitelist vs CLI allow-list).
- import-linter contract type (layers vs forbidden) for the green scaffold.

## Deferred Ideas

- Tighten import-linter kernel contract to final form → Phase 7/8 (needs `kernel.py`/`capabilities.base`).
- Flip ledger rows to `☑` + enable grep enforcement → each row's owning phase (L14/L16/D1 → Phase 2; L1–L12 → Phase 7; F1–F5 → Phase 8).
- INV-1 hard-fail → Phase 7 (L7 deletion).
- pre-commit hook mirrors of CI gates → opportunistic, not required for Phase 1.
