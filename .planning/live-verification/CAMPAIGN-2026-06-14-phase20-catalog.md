# Live Verification Campaign — 2026-06-14 — Phase 20 (Workflow Catalog / WF-DB-01)

**Scope:** Phase 20 milestone-end live repass on real Bedrock (`AWS_PROFILE=default`, acct 473293451041, Haiku 4.5 / eu-central-1). Backend `sqlite dev.db`, `alembic=0020` (no new migration — additive-only confirmed). Frontend Next dev :3000. Seeded users `qa-{basic,pro,enterprise,admin}@flowinqa.com` / `flowin-e2e-pass`.

**Result: ALL GREEN — no product defects.** The catalog needs no Bedrock agent run (it lists + routes; the run path itself is already live-proven in the 2026-06-13 campaign), so this pass verifies the data + UI + routing against the real backend.

## Backend half — real `GET /api/workflows` (JWT, enterprise)
- 200 OK; response carries the new additive fields `user_launchable` / `launch_surface` / `display_name`.
- **7 `user_launchable=true`:** `app_builder, custom, dotnet_to_azure, mulesoft_to_springboot, user_stories` (plain-run) + `prototype, ppt` (`launch_surface="wizard"`).
- **8 `user_launchable=false` (correctly hidden):** `user_stories_revision, ppt_revision, prototype_revision, app_builder_revision, od_ppt, od_ppt_revision, reverse_engineer, chat`.
- **`display_name` null for all 15** → the FE drives labels from `getWorkflowLabel` (WR-01 fix live).
- **Notable:** the first probe returned **500** because the backend process predated Phase 20 — its old `_ALLOWED_TOP_KEYS` rejected the now-present `user_launchable:` key in the 7 manifests. Restarting on HEAD `33527c41` resolved it (a stale-process artifact, not a code defect; it incidentally proves the strict-key gate is live).

## Frontend half — live Playwright (`ts-z.catalog.live.spec.ts`, real login, real backend) — `3 passed (7.1s)`
- **(a) Enterprise:** all 7 launchable rows render; friendly labels via `WORKFLOW_LABELS` ("Mulesoft Migration", ".NET Migration") — raw "Mulesoft To Springboot"/"Dotnet To Azure" **absent (count 0)**; zero revision/`od_*`/`chat`/`reverse_engineer` rows; no lock copy (all entitled).
- **(b) Basic tier-gating:** gate-1 renders all 7; gate-2 enables only `user_stories`+`ppt`; the other 5 shown-locked — **"Requires Pro plan" ×2** (prototype, app_builder) + **"Requires Enterprise plan" ×3** (mulesoft, dotnet, custom). Basic set ⊂ enterprise set.
- **(c) Launch routing (no Bedrock run):** `user_stories` → IdeaInputPage ("Provide the brief"); `prototype` → `/workflow/prototype/templates`; `ppt` → `/workflow/ppt/templates`.
- **Visual proof:** `/tmp/phase20-catalog-live.png` (enterprise catalog, friendly-labelled rows with arrow affordances, no locks).

## Invariants (re-confirmed)
INV-3 5 goldens byte-identical (offline, in-phase), SC-001 (no name list; `WORKFLOWS` const deleted), lint-imports 4/0, additive-only (no migration — `alembic=0020`).

## Commits
`bb9cc8f6` test(20): live Playwright catalog verification (real backend, tier-gated). (Phase-20 feature commits `6e3bc097..33527c41`.)

**Deferred:** none for Phase 20 — the catalog is fully live-verified. (A full Bedrock *run launched from the catalog* exercises the already-proven existing run path; not re-run here.)
