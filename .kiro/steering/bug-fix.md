---
inclusion: always
---

# Bug-Fix Conventions — Flowin / VelocityAI

Flowin is a brownfield workflow-engine refactor (backend: Python · FastAPI · PostgreSQL · LangGraph on the `deepagents` runtime; frontend: Next.js / React / TypeScript), built incrementally through the phased plan under `.planning/`. When fixing a bug, patch the defect on top of the existing architecture — extend, don't redesign it.

## Before fixing — read the registers

Read these first, every time, so you do not re-fix something already fixed, duplicate a registered capability, or contradict a locked decision:

- `.planning/IMPLEMENTATION-REGISTER.md` — index over all planned phases: what already exists, what was deliberately deleted (do not resurrect), and which decisions are locked (do not contradict).
- `.planning/FIX-REGISTER.md` — cumulative patch history on top of the phases. Check whether the area was already touched and reuse the established root-cause pattern.
- `.planning/ISSUES-REGISTER.md` (supporting) — known issues with status (OPEN / FIXED / DEFERRED / WONTFIX). Confirm the bug is not already tracked or intentionally deferred.

## While fixing — preserve the core architecture

These invariants define the architecture and must still hold after every fix. If a fix seems to require breaking one, stop and flag it instead of proceeding:

- **INV-1** — the engine kernel knows no workflow by name: no `if pipeline_type == …` / `spec.id == …` branches. Behaviour lives in registered, declared capabilities.
- **SC-001** — a custom workflow can replicate `prototype` from a manifest + `AGENT.md` alone, with zero engine edits. Prefer manifest/prompt fixes over kernel edits.
- **INV-3** — semantic event parity; deterministic deliverables stay byte-identical. Do not regenerate the characterization goldens unless the fix is intentionally output-changing, and call that out explicitly.
- **INV-12** — no dual implementations: move code and rewire call-sites, then delete the superseded version. Never leave a copy behind.
- **INV-13** — every agent runs on LangChain `deepagents`; `create_deep_agent` is called only inside `deep_agent_runner.py`.
- **Ports & Adapters** — the kernel depends only on capability ports; add behaviour by adding a module + `@register`, never by editing the kernel. `lint-imports` stays 4/0.
- **Persistence** — additive Alembic migrations only; every new table carries `owner_id` + `workspace_id`.
- **Security defaults OFF** — `exec` / `network` / `secrets` / `spawn_subagents` stay off unless a gate explicitly enables them.

Scope each change to the smallest layer that resolves the root cause: prefer frontend-only or `AGENT.md`/manifest changes when they suffice, and touch the engine kernel only as a last resort.

## Fix discipline

- Find the true root cause before editing. Name it precisely (file + mechanism) and reject the tempting shortcut that only masks the symptom.
- Keep the fix minimal and targeted — do not refactor unrelated code or "clean up" surrounding logic while you are there.
- Verify the invariants still hold: run the characterization goldens, `lint-imports`, and the tests relevant to the change.

## After fixing — log it

Append an entry to `.planning/FIX-REGISTER.md`, matching the format of existing entries in both the summary table and the detailed section: Fix ID, date, description, root cause, files changed, phase(s) involved, invariants verified, and status.
