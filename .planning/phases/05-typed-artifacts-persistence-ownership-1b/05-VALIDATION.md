---
phase: 5
slug: typed-artifacts-persistence-ownership-1b
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-07
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> This phase's cutover is **parity-gated** — validation IS the exit gate. The mirror + thin store may only be deleted (D-13 step 5) once the 0A characterization suite is byte-identical + semantic-event green.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (+ pytest-asyncio for `async` engine tests; Hypothesis available) |
| **Config file** | `backend/pyproject.toml` (`[tool.pytest.ini_options]`, testpaths=`tests`) |
| **Quick run command** | `cd backend && python3.11 -m pytest tests/agents/test_migration_ledger.py tests/agents/test_parent_run_ownership.py -x` |
| **Full suite command** | `cd backend && python3.11 -m pytest tests/agents/ tests/unit/ -v` |
| **Import-linter (kernel boundary)** | `cd backend && lint-imports` (must stay exit 0) |
| **Vulture (dead-code after deletions)** | `cd backend && vulture app/ agents/` |
| **Estimated runtime** | ~quick <30s · full suite ~minutes (characterization dominates) |

---

## Sampling Rate

- **After every task commit:** Run the targeted unit file for that task + `lint-imports`.
- **After every plan wave:** Run `cd backend && python3.11 -m pytest tests/agents/ tests/unit/ -v` + `lint-imports` + `vulture`.
- **Phase gate (before D-13 step 5 — deleting the mirror + thin store + applying `0015`):** full `tests/agents/test_characterization_*.py` byte + semantic-event green (the parity gate that BLOCKS deletion), AND `test_migration_ledger.py` green with L15 + thin-store gates armed, AND L16 still green.
- **Before `/gsd-verify-work`:** Full suite must be green.
- **Max feedback latency:** ~30 seconds (quick command).

---

## Per-Task Verification Map

> Task IDs / waves are assigned by the planner; rows are keyed by requirement → likely plan slice (CONTEXT suggested slices 05-01..05-05). Threat refs map to the Security Domain table below (the planner's `<threat_model>` blocks own the canonical T-IDs).

| Req ID | Plan (planner confirms) | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|--------|-------------------------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| ART-01/03 | 05-01 | build graph, two refs (one derived), typed lineage read; `consumes:[X]` gets type-X refs | — | N/A | unit | `pytest tests/agents/test_artifact_graph.py -x` | ❌ W0 | ⬜ pending |
| ART-02 | 05-01 | every write records producer step/agent/task, sha256, version, parents | — | N/A | unit | `pytest tests/agents/test_artifact_graph.py -x` | ❌ W0 | ⬜ pending |
| ART-04 | 05-01 | retention defaults `run_ttl`; `keep` persists | — | N/A | unit | `pytest tests/agents/test_artifact_graph.py -x` | ❌ W0 | ⬜ pending |
| PERSIST-01 | 05-02 | `alembic upgrade head` from 0013 + `downgrade` reverse; indexes present; `owner_id`+`workspace_id` on each new table | — | N/A | integration | `pytest tests/unit/test_migration_0014.py -x` | ❌ W0 | ⬜ pending |
| PERSIST-03 | 05-02 / 05-05 | `run_events` contiguous per-run `seq`; unique `event_id` | T-5-REPLAY | event_id idempotent; seq monotonic; read-only owner-scoped | unit/integration | `pytest tests/unit/test_run_events.py -x` | ❌ W0 | ⬜ pending |
| PERSIST-02 | 05-04 | `grep accumulated_outputs backend/agents backend/app` → 0; thin-store artifact methods gone; HITL still works | — | N/A | ratchet+unit | `pytest tests/agents/test_migration_ledger.py -x` *(must edit flip set)* | ✅ (edit) | ⬜ pending |
| AUTHZ-01/02 | 05-03 | default-deny store scoping; cross-owner **parent** seeding denial (L16) | T-5-SEED / T-5-IDOR | `assert_owns` real store lookup raises PermissionError above seed | unit | `pytest tests/agents/test_parent_run_ownership.py -x` | ✅ (extend) | ⬜ pending |
| AUTHZ-04 | 05-03 | cross-owner **artifact** + **workspace** denial | T-5-IDOR | scoped helper default-deny filter; 404 at API (no existence leak) | unit | `pytest tests/agents/test_parent_run_ownership.py -x` + new artifact/workspace cases | ✅ (extend) | ⬜ pending |
| AUTHZ-03 | 05-03 | anon run persists `anon:<session_id>`; second anon session cannot read first | T-5-ANON | `owner_id` never `None`; anon is a real scoped principal | unit | `pytest tests/agents/test_parent_run_ownership.py -x` *(update anon strings)* | ✅ (edit) | ⬜ pending |
| CAPRUN-01 | 05-05 | exactly one `run_capabilities` row, `runtime=langchain_deepagents` | — | N/A | unit | `pytest tests/unit/test_run_capabilities.py -x` | ❌ W0 | ⬜ pending |
| API-04 | 05-05 | walkable lineage tree ≥2 linked nodes; cross-owner → 404 | T-5-IDOR / T-5-SQLI | ORM `.filter()` parameterized `{id}`; owner-scoped; 404 | api | `pytest tests/unit/test_runs_api_artifacts.py -x` | ❌ W0 | ⬜ pending |
| API-05 | 05-05 | `?after=k` → rows `seq>k` ascending, carry `event_id`; cross-owner → 404 | T-5-SQLI / T-5-IDOR | `after` int-coerced; owner-scoped; 404 | api | `pytest tests/unit/test_runs_api_events.py -x` | ❌ W0 | ⬜ pending |
| BACK-COMPAT (gate) | 05-04 | prototype / od_prototype / prototype_revision / ppt / code-gen byte-identical + semantic-event parity | — | N/A | characterization | `pytest tests/agents/test_characterization_*.py -x` | ✅ (5 files) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/agents/test_artifact_graph.py` — ART-01/02/03/04 graph unit tests (NEW)
- [ ] `tests/unit/test_migration_0014.py` — upgrade/downgrade + schema/index + owner_id/workspace_id assertions, PERSIST-01 (NEW)
- [ ] `tests/unit/test_run_events.py` — durable log seq/event_id, PERSIST-03 (NEW)
- [ ] `tests/unit/test_run_capabilities.py` — CAPRUN-01 (NEW)
- [ ] `tests/unit/test_runs_api_artifacts.py` + `tests/unit/test_runs_api_events.py` — API-04/05 incl. cross-owner 404 (NEW)
- [ ] Extend `tests/agents/test_parent_run_ownership.py` — artifact + workspace denial cases; update anon strings to `anon:<session_id>` (EDIT)
- [ ] Edit `tests/agents/test_migration_ledger.py` — expected flip set (currently hard-codes `["L14","L16"]`, **will break when L15 flips**) + add thin-store deletion gate row (EDIT)
- [ ] Edit `tests/agents/characterization/_normalize.py` — add `seq` / `event_id` to `_VOLATILE_STRIP_KEYS` so the new event fields don't perturb semantic-event parity (EDIT)
- [ ] Framework: pytest-asyncio already in use (async engine tests present) — no install needed.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| — | — | — | — |

*All phase behaviors have automated verification (unit / integration / api / characterization). No manual-only gates.*

---

## Highest-Risk Behaviors (Dimension 8 focus)

1. **0A characterization parity** (5 pipelines) — the cutover blocker. Highest risk: `seq`/`event_id` stamping perturbing the event multiset (mitigated by `_VOLATILE_STRIP_KEYS`); any read-migration changing deliverable bytes.
2. **Cross-owner denial** (parent + artifact + workspace, AUTHZ-04) — security-critical; default-deny must hold at the store layer, 404 at API.
3. **Migration up/down + backfill** — `alembic downgrade` must cleanly reverse `0014`; backfill must give EVERY existing run a `workspace_id` (uniform scoping).
4. **L16 stays green** — the relocated helper (now a real store lookup) must not regress the existing parent-ownership denial.
5. **`seq` contiguity** (SAFE-03, deltas==1) under the NEW sink across the interleaving build loop (no `seq` exists today — this is net-new, not a reuse).

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (8 test files above)
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s (quick command)
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
