---
inclusion: always
---

# IdeaFlowAI — Project Index & Navigation

> **Read this before implementing any feature or bug-fix.**
> The project history is maintained as individual cards under `.knowledge/cards/`.
> The `.planning/` registers are a frozen fallback and are never loaded wholesale.

---

## What This Project Is

**Workflow Engine Decoupling & Universal Workflow Runtime** — a manifest-driven runtime kernel for Flowin's agent workflows. The `ExecutionEngine` is a small, workflow-agnostic kernel driven by declarative `workflow.yaml` manifests compiled to typed `CompiledWorkflow` plans. Every capability is a declared, registered module — no workflow names live in the kernel.

- **Stack:** Python · FastAPI · PostgreSQL · LangGraph checkpointer · LangChain `deepagents==0.6.7`
- **Full spec:** `specs/003-workflow-engine-decoupling/plan.md`
- **Issues log:** `.planning/ISSUES-REGISTER.md` (fallback only)

---

## SC-001 — The Core Value Invariant

> **A brand-new custom workflow can replicate `prototype` by manifest + AGENT.md only — with ZERO engine edits.**

---

## Before Implementing Anything

1. **Prime the knowledge store** once per session with `/velocity prime`.
2. **Before touching a file**, use the primed `.knowledge/CONTEXT.md` to choose its `MOD-*.md` architecture card. Then use `.knowledge/INDEX.md` to select and open only the relevant cards; inspect their `applies_to` and `locked_constraints` fields.
3. **Before diagnosing a bug**, use `/velocity analyze <symptom>`. Use `/velocity fix <symptom>` when the user has asked for a repair.
4. **For domain-specific constraints**, the `fileMatch` steering files load automatically when you open relevant code.
5. **Use `.planning/` only when cards and the index do not contain the historical detail needed.** State that it is a frozen-archive fallback when reporting anything derived from it.

---

## Knowledge Store — Current Workflow

| Need | Current workflow |
|---|---|
| Inspect freshness | `/velocity status` |
| Build or refresh session context | `/velocity prime` |
| Investigate a symptom | `/velocity analyze <symptom>` |
| Diagnose and apply a fix | `/velocity fix <symptom>` |
| Find a card by known ID | Follow its link from `.knowledge/INDEX.md` |
| Find file or area context | Prime → `.knowledge/CONTEXT.md` → relevant `MOD-*.md` → `.knowledge/INDEX.md` → selected cards |

The legacy cache-query command is gone. The active read models are `.knowledge/CONTEXT.md`, `.knowledge/ARCHITECTURE.md`, `.knowledge/INDEX.md`, and the linked cards under `.knowledge/cards/`.

---

## Current Project State

Current state, milestone, and enforced import boundaries: `.knowledge/ARCHITECTURE.md`.

---

## Alembic Migration Chain

The migration head drifts. Verify it from `backend/` with `uv run alembic heads`; it must print exactly one head. Two heads make `alembic upgrade head` fail, which crash-loops the container (`docker-entrypoint.sh` runs it under `set -eu`).

Every new table **must** carry `owner_id` + `workspace_id` (Q3, additive-only).

---

## Key Source Files

| What | File |
|---|---|
| Runtime kernel | `backend/agents/execution_engine/engine.py` |
| ExecutionContext | `backend/agents/execution_engine/context.py` |
| Capability registry | `backend/agents/capabilities/registry.py` |
| Workflow manifests | `backend/agents/workflows/*/workflow.yaml` |
| Model catalog (single source) | `backend/agents/capabilities/model_catalog.py` |
| Scoped store / IDOR gate | `backend/agents/authz.py` |
| SSE down-channel | `backend/app/api/run_stream.py` |
| REST up-channel | `backend/app/api/run_commands.py` |
| Shared run infra | `backend/app/api/run_engine.py` |
| Run SSE hook (FE) | `frontend/src/hooks/useRunStream.ts` |
| Connection provider (FE) | `frontend/src/providers/RunConnectionProvider.tsx` |
| Design tokens | `frontend/src/styles/globals.css` |
| Migration ledger | `specs/003-workflow-engine-decoupling/migration-ledger.md` |

---

## Glossary Quick Reference

| Tag | Meaning |
|---|---|
| `INV-#` | Global invariant (see `invariants.md`) |
| `SC-001` | Zero-engine-edit custom-workflow proof |
| `Q#` | Locked architecture decision |
| `ISS-###` | Issue card — follow the link from `.knowledge/INDEX.md` |
| `FIX-###` | Fix card — follow the link from `.knowledge/INDEX.md` |
| `ADR-###` | Decision card — follow the link from `.knowledge/INDEX.md` |
| `INV-3` | Characterization goldens must stay byte/event-identical |
| `LOCK-B` | WS deletion complete — do not reintroduce WS run frames |
