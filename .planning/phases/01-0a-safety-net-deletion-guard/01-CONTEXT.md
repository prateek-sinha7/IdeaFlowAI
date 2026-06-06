# Phase 1: [0A] Safety Net + Deletion Guard - Context

**Gathered:** 2026-06-06
**Status:** Ready for planning
**Mode:** Captured autonomously (`--auto`) — recommended option chosen for every gray area; review before planning if any decision needs changing.

<domain>
## Phase Boundary

Lock the current behavior of every existing pipeline with **characterization snapshots**, and stand up the **CI enforcement gates** that the rest of the migration relies on — *before any refactor touches the engine*. This phase adds **no runtime behavior change**: it is tests + CI scaffolding only.

Delivers (REQUIREMENTS.md → SAFE-01..07, DEL-01..04):
- Deliverable byte-snapshots + semantic event-stream snapshots for `prototype`, `od_prototype`, `prototype_revision`, `ppt`/`od_ppt`, and one code-gen pipeline (driven by the scripted model).
- Migration-ledger CI guard (`test_migration_ledger.py`) asserting each `☑` ledger item's banned grep-pattern returns 0.
- Import-linter contract (kernel imports only capability ports).
- Banned-pattern gate against hand-rolled deep agents (INV-13 / R15) — a ratchet.
- All gates wired into CI; start green/empty, tighten as items delete.

**Out of scope (belongs to later phases):** any extraction/refactor of `engine.py`/`factory.py` (Phases 2/7/8), `ExecutionContext` (Phase 2), the actual deletion of L-items (their owning phases). Phase 1 only *records* behavior and *arms* the gates.
</domain>

<decisions>
## Implementation Decisions

### Characterization harness (SAFE-01/02/03)
- **D-01:** **Reuse and extend the existing offline harness** `backend/tests/agents/_scripted_model.py` — it already provides `ScriptedFakeChatModel` (+ `_ScriptedTurn`), `_scripts_for(agent_id)`, and `_drive(pipeline_type)` which runs the public `ExecutionEngine.execute()` end-to-end offline and returns the ordered list of yielded engine event dicts (the real outbound WS vocabulary). Do **not** rebuild a harness. *(auto: recommended)*
- **D-02:** Add per-agent scripts so all five characterization pipelines drive deterministically: `prototype`, `od_prototype`, `prototype_revision`, `ppt`/`od_ppt`, and one code-gen pipeline. Where a pipeline needs inputs the current `_drive()` doesn't script, extend `_scripts_for()` rather than fork the driver.
- **D-03:** Keep 003 characterization tests in clearly-named modules `tests/agents/test_characterization_<pipeline>.py` (plan §28). **Note:** the existing `test_phaseN_*.py` files use **002-deepagents** phase numbering — unrelated to 003's `[0A]…[6]`. Do not collide names or assume those phase numbers map to this roadmap.

### Snapshot format & volatile-field normalization (SAFE-02/03)
- **D-04:** **Hand-rolled golden files + a `_normalize()` helper** — no new snapshot dependency (syrupy). Rationale: `_drive()` already yields plain dicts; the deleted `_serialize` JSON emitter precedent existed; we need full control over normalization. *(auto: recommended)*
- **D-05:** Two snapshot kinds per pipeline: (a) **deliverable byte-snapshot** — the raw produced file, asserted byte-for-byte where output is deterministic (INV-3); (b) **semantic event snapshot** — normalized JSON of event *types*, order, required fields, and final result.
- **D-06:** `_normalize()` strips/normalizes volatile fields: timestamps, streamed-text chunk boundaries, generated IDs, token/usage counts (`usage_metadata`), durations. The monotonic per-run event `seq` (§21) is asserted **contiguous** (no gaps), not by absolute value (SAFE-03).
- **D-07:** Golden files committed under `backend/tests/agents/characterization/golden/` (deliverables + `*.events.json`); a `--snapshot-update` style env/flag regenerates them deliberately. Offline only (no `requires_api_key`).

### Migration & deletion ledger (DEL-01..04 / §31)
- **D-08:** Create a standalone **`specs/003-workflow-engine-decoupling/migration-ledger.md`** that mirrors the plan §31 table (every `L#`/`F#`/`D#` → legacy `file:line` → new home → phase → deletion grep-pattern → status `☐`/`☑`). This is the operational single source of truth CI asserts against. *(auto: recommended)*
- **D-09:** `tests/agents/test_migration_ledger.py` parses the ledger rows and, **for each `☑` row only**, runs its grep-pattern over `backend/` and asserts **0 matches**. `☐` rows are not yet enforced (they reference code that still legitimately exists). Once a row flips to `☑`, the pattern is permanently enforced (ratchet) — reintroduction fails CI.
- **D-10:** In Phase 1 all rows start `☐` (nothing deleted yet) → the guard is green/empty and tightens as later phases flip rows.

### Static gates: import-linter + dead-code (SAFE-05 / §31)
- **D-11:** Configure **import-linter in `backend/pyproject.toml` `[tool.importlinter]`**; add `import-linter` to `backend/requirements-dev.txt` (pinned). *(auto: recommended)*
- **D-12:** The kernel→ports contract is **scaffolded green now**: today the kernel module is still `engine.py` (not yet split to `kernel.py`). Author a forbidden-import contract that holds with the current tree and is designed to tighten when `kernel.py` + `capabilities/base.py` land (Phase 2/8) — i.e. "the kernel module must not import legacy `factory`/`engine` internals once those exist." Document the intended final contract inline so Phase 8 only tightens, never rewrites.
- **D-13:** Dead-code scan: **add `vulture` to `requirements-dev.txt`** for orphaned-function detection (the plan names "ruff / vulture"). Ruff (already present, `[tool.ruff]`) continues to catch F401/F811; pyright (already present) catches deleted-module imports. Vulture runs allow-listed to avoid false positives on framework entrypoints.

### Banned-pattern gate (SAFE-06 / INV-13 / R15)
- **D-14:** Implement as a **pytest test** `tests/agents/test_banned_patterns.py` (not just a shell grep) so it runs in the test job, is a ratchet, and gives readable failures. *(auto: recommended)*
- **D-15:** Patterns banned (fail if matched outside the sanctioned `langchain_deepagents` adapter): `class DeepAgent`, `def deep_agent`, a new module/package named `deepagents` or `langchain_deepagents` under our source, and bespoke `for _ in range(max_iterations)`-style agent loops. Allow-list the real import `from deepagents import create_deep_agent` and the one adapter module (`app/agents/deep_agent_runner.py` today). Also seed the INV-1 reservation (`if pipeline_type ==` / `spec.id ==`) as a **warn-only / documented** pattern in Phase 1 (it still exists in `engine.py`); it becomes hard-fail in Phase 7 when L7 is deleted.

### CI wiring (SAFE-07 / `.gitlab-ci.yml`)
- **D-16:** **Critical gap:** CI currently runs only `cd backend && python -m pytest tests/unit -q` — the agent/characterization tests in `tests/agents` are **not run in CI today**. They must be explicitly wired in. *(grounded in `.gitlab-ci.yml` + `pyproject.toml testpaths`)*
- **D-17:** Wiring plan: **lint stage** (`backend:lint`) gains `lint-imports` (import-linter) + the vulture dead-code scan (ruff already runs); **test stage** gains a dedicated `backend:characterization` job running `pytest tests/agents/test_characterization_*.py tests/agents/test_migration_ledger.py tests/agents/test_banned_patterns.py -q` — fully offline (no DB/API-key). The banned-pattern + ledger tests being in the test stage keeps them as hard ratchets. *(auto: recommended)*

### Claude's Discretion
- Exact golden-file directory layout and the `_normalize()` field list (within D-06's contract).
- Whether vulture runs via pyproject `[tool.vulture]` + a whitelist file or a CLI allow-list (either is fine; keep config in-repo).
- Precise import-linter contract type (layers vs forbidden) for the scaffold, provided D-12's tighten-don't-rewrite property holds.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### The specification (authoritative)
- `specs/003-workflow-engine-decoupling/plan.md` — the full spec. Phase 1 anchors: **§24** (backward-compat & testing strategy — characterization tests FIRST), **§31** (code deletion, migration ledger & anti-duplication — the L#/F#/D# table this phase mirrors), **§3** (INV-1, INV-3, INV-12, INV-13), **§25 Phase 0A** (Accept criteria), **§28** (`tests/agents/test_characterization_*.py`), **R14/R15** (duplication + hand-rolled-deep-agent risks).
- `specs/002-deepagents-migration/plan.md` — the prior migration this builds on; explains the existing `test_phaseN_*` naming and the `deepagents==0.6.7` / `create_deep_agent` mandate (INV-13 precedent).

### Project planning
- `.planning/REQUIREMENTS.md` — SAFE-01..07, DEL-01..04 with their plan anchors.
- `.planning/ROADMAP.md` §"Phase 1" — goal, success criteria, candidate plan breakdown.
- `.planning/PROJECT.md` — invariants + constraints (esp. INV-13 runtime mandate, no-dual-implementations).

### Code to read (existing assets / targets)
- `backend/tests/agents/_scripted_model.py` — the reusable offline harness (`ScriptedFakeChatModel`, `_scripts_for`, `_drive`). **The keystone asset for SAFE-01/02.**
- `backend/agents/execution_engine/engine.py` — the engine whose behavior is being snapshotted (leaks L1–L16 live here; do NOT edit in Phase 1).
- `backend/app/agents/deep_agent_runner.py` — the sanctioned `create_deep_agent` call site (allow-list anchor for the banned-pattern gate; `deep_agent_runner.py:240` per plan).
- `backend/pyproject.toml` — `[tool.pytest.ini_options]` (`testpaths=["tests"]`), `[tool.ruff]`; where `[tool.importlinter]` + `[tool.vulture]` will be added.
- `backend/requirements-dev.txt` — ruff/pyright/pre-commit already pinned; add `import-linter` + `vulture`.
- `.gitlab-ci.yml` — `lint` + `test` stages; currently runs only `tests/unit`. The wiring target for SAFE-07.
- `.pre-commit-config.yaml` (repo root) — existing hooks; candidate home for fast local mirrors of the gates.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`_scripted_model.py` offline driver** — `_drive(pipeline_type)` already runs `execute()` end-to-end offline and returns ordered event dicts; this is exactly the SAFE-02 capture mechanism. `ScriptedFakeChatModel` is the proven way to script the deepagents loop (stock LangChain fakes don't drive it).
- **Existing offline monkeypatch suite** in `_scripted_model.py` (scripted `ctx.model`, planner→PROCEED, `ALWAYS_CLARIFY=False`, `ArtifactStore.store` no-op, `_run_review_gate` no-op, temp `RUNS_ROOT`) — reuse so disk deliverables + event capture work without DB/network.
- **Existing test corpus** `tests/agents/test_phase{3,4,5,6,8}_*.py` — patterns for driving pipelines offline; reference for assertions (but distinct 002 numbering).
- **Lint stack already present** — ruff 0.8.4 (`[tool.ruff]`), pyright 1.1.391 (import resolution), pre-commit 4.0.1. Add only import-linter + vulture.

### Established Patterns
- `testpaths = ["tests"]`, `python_files=["test_*.py"]`, `addopts="-v --tb=short"`, `requires_api_key` marker for live tests — characterization tests must be **offline** (unmarked) so they run in CI.
- CI is **GitLab** (`.gitlab-ci.yml`), stages `lint` → `test`; backend test command is `cd backend && python -m pytest tests/unit -q` (SQLite DATABASE_URL, ENV=test).
- Dev runtime: `python3.11`, no venv (per project memory `dev-runtime`).

### Integration Points
- New gates plug into `.gitlab-ci.yml` (lint stage: import-linter + vulture; new test job: characterization + ledger + banned-pattern) and optionally `.pre-commit-config.yaml` for local fast feedback.
- `test_migration_ledger.py` reads `specs/003-workflow-engine-decoupling/migration-ledger.md` and greps `backend/`.
- import-linter contract + vulture config live in `backend/pyproject.toml`.

</code_context>

<specifics>
## Specific Ideas

- User directive (init): *"everything from plan.md should be part of whatever you generate — nothing can be missed out."* → the migration-ledger.md must faithfully mirror **all** of §31's L1–L16 / F1–F5 / D1 rows, and characterization must cover all five named pipeline families.
- Snapshots are gated on **semantic event parity** (INV-3), not just byte-identity — Phase 3 ([0C]) is the one sanctioned place deliverable bytes may legitimately change, so the event-snapshot machinery must be robust to text drift while pinning structure.

</specifics>

<deferred>
## Deferred Ideas

- **Tightening the import-linter kernel contract to its final form** — only possible once `kernel.py` + `capabilities/base.py` exist → Phase 7/8. Phase 1 ships the green scaffold (D-12).
- **Flipping ledger rows to `☑` + enabling their grep enforcement** — happens in each row's owning phase (L14/L16/D1 in Phase 2; L1–L12 in Phase 7; F1–F5 in Phase 8), not here.
- **INV-1 hard-fail** (`if pipeline_type ==` / `spec.id ==` → 0) — deferred to Phase 7 (L7 deletion); Phase 1 only documents/warns it (D-15).
- **pre-commit hook mirrors of the CI gates** — nice-to-have for local speed; can be added opportunistically, not required for Phase 1 acceptance.

None of these are scope creep — all are explicitly later-phase per ROADMAP.md.

</deferred>

---

*Phase: 1-[0A] Safety Net + Deletion Guard*
*Context gathered: 2026-06-06*
