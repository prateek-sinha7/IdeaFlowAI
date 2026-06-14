# Live Verification Campaign — 2026-06-14 — Phase 21 (Saved Workflows)

**Scope:** Phase 21 milestone live repass on the real stack (`AWS_PROFILE=default` / Bedrock Haiku eu-central-1; sqlite `dev.db`). This phase added a schema migration, so the dev DB was migrated `0020 → 0021` and the backend restarted on the Phase-21 code (HEAD `af03c930`).

**Result: ALL GREEN — no product defects.** Saving/launching a custom composition needs no Bedrock agent run (the run path itself is already live-proven); this pass verifies the persistence + CRUD + the full FE journey against the real backend.

## Migration + restart
- `alembic upgrade head`: `0020 → 0021 — additive saved user-workflows (Phase 21)` → head `0021`. The `workflows` table gained the 3 additive nullable columns: `base_pipeline_type`, `model_overrides`, `description` — **no new table** (reuse of the dormant `workflows` table, INV-12). Reversibility was already proven offline in-phase.
- Backend restarted on Phase-21 code; boot log `Database schema: alembic=0021`; `/api/user-workflows` → 403 unauth (JWT-gated, the new router is live).

## Backend half — real `/api/user-workflows` CRUD smoke (12/12 PASS)
Real login (enterprise/pro/basic), real DB. Custom agent ids drawn from the live registry (`market-research-agent`, `swot-analyst`).
- **CREATE** → 201, owner-stamped `source="user"`, agent_ids echoed.
- **LIST** contains it; **GET /{id}** → 200; **PATCH rename** → 200 + new name.
- **Validation:** empty `agent_ids` → **422** (WR-02 fix live); bogus agent id → **422** (re-validated against the live registry).
- **Entitlement:** basic user POST (custom = enterprise) → **403**.
- **IDOR:** pro user GET/PATCH/DELETE the enterprise row → **404 / 404 / 404** (owner-scoping live).
- **DELETE** as owner → **204**; row gone.

## Frontend half — live Playwright (`ts-z2.saved-workflows.live.spec.ts`, real login + real CRUD) — `1 passed (11.1s)`, stable ×5
- **save-persists:** catalog "+ Create workflow" → custom composer → AgentsPopup assembles 2 real agents → "Save workflow" → NameWorkflowModal → real `POST` **201** (`base_pipeline_type=custom`, both agent_ids) + "Saved" pill.
- **appears:** the saved row renders under **"Your workflows"** with a kebab; the built-in "Prototype" row has no Rename/Duplicate/Delete (read-only).
- **rename:** kebab → Rename → real `PATCH` **200**; row label updates, old name gone.
- **launch-preloads (load-bearing):** clicking the saved row lands on IdeaInputPage **pre-loaded with the 2 saved agents** (resolved by name; Run reads "Run workflow", not "Add agents first"). No run submitted (no Bedrock needed).
- **cleanup:** kebab → Delete → real `DELETE` **204**; + `beforeAll`/`afterAll` API sweep on the `__e2e-z2-live__` prefix → list `[]` after each run (idempotent).
- **Visual proof:** `/tmp/phase21-saved-workflows-live.png` (the "Your workflows" section with the saved row).

## Invariants (re-confirmed)
INV-3 5 goldens byte-identical (offline, in-phase, 42 passed) · INV-12 (`_persist_workflow_definition` removed, `grep==0`) · additive migration (no `create_table`, reversible, 3 nullable cols) · SC-001 (saved workflow = pure data) · `lint-imports` 4/0.

## Commits
Live spec: `test(21): live Playwright saved-workflows verification (real backend, enterprise)`. (Phase-21 feature commits `014c0959..af03c930`.)

**Deferred:** none for Phase 21 — saving/CRUD/launch fully live-verified. (A full Bedrock *run* of a launched saved workflow exercises the already-proven existing run path; not re-run here.)
