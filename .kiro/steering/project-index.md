---
inclusion: always
---

# IdeaFlowAI — Project Index & Navigation

> **Read this before implementing any feature or bug-fix.**
> The project's full history lives in the card store — 532 cards, queryable in milliseconds.
> The registers (`.planning/FIX-REGISTER.md`, `IMPLEMENTATION-REGISTER.md`) are **never** loaded wholesale.

---

## What This Project Is

**Workflow Engine Decoupling & Universal Workflow Runtime** — a manifest-driven runtime kernel for Flowin's agent workflows. The `ExecutionEngine` is a small, workflow-agnostic kernel driven by declarative `workflow.yaml` manifests compiled to typed `CompiledWorkflow` plans. Every capability is a declared, registered module — no workflow names live in the kernel.

- **Stack:** Python · FastAPI · PostgreSQL · LangGraph checkpointer · LangChain `deepagents==0.6.7`
- **Full spec:** `specs/003-workflow-engine-decoupling/plan.md`
- **Issues log:** `.planning/ISSUES-REGISTER.md`

---

## SC-001 — The Core Value Invariant

> **A brand-new custom workflow can replicate `prototype` by manifest + AGENT.md only — with ZERO engine edits.**

---

## Before Implementing Anything

1. **Prime the knowledge store** (once per session):
   ```
   python3 scripts/knowledge/ctx.py --help
   ```
   Or invoke the `knowledge-prime` skill.

2. **Before touching a file**, query what rules and fixes apply to it:
   ```
   python3 scripts/knowledge/ctx.py --for <path>
   ```

3. **Before diagnosing a bug**, search prior fixes:
   ```
   python3 scripts/knowledge/ctx.py "<symptom words>"
   ```

4. **For domain-specific constraints**, the `fileMatch` steering files load automatically when you open the relevant code.

5. **Check `.planning/ISSUES-REGISTER.md`** for known open issues before touching a surface.

---

## Knowledge Store — How to Query

```bash
# Search by symptom (finds fixes, issues, decisions)
python3 scripts/knowledge/ctx.py "reconnect banner"

# Find every rule and fix touching a specific file
python3 scripts/knowledge/ctx.py --for frontend/src/hooks/useRunStream.ts

# Get decisions in force for an area
python3 scripts/knowledge/ctx.py --rules sse

# Open one full card
python3 scripts/knowledge/ctx.py --show FIX-157

# Check store freshness
python3 scripts/knowledge/check.py
```

The store contains **532 cards** across fixes, issues, bugs, phases, tests, requirements, and decisions. The full card index is at `.knowledge/surface/INDEX.md`.

---

## Current Project State

Current state, milestone, and enforced import boundaries: `.knowledge/surface/ARCHITECTURE.md`

---

## Alembic Migration Chain (head: 0026)

`0014` → `0015` → `0016` → `0017` → `0018` → `0019` → `0020` → `0021` → `0022` → `0023` → `0024` → `0025` → `0026`

Every new table **must** carry `owner_id` + `workspace_id` (Q3, additive-only).

---

## Key Source Files

| What | File |
|------|------|
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
|-----|---------|
| `INV-#` | Global invariant (see `invariants.md`) |
| `SC-001` | Zero-engine-edit custom-workflow proof |
| `Q#` | Locked architecture decision |
| `ISS-###` | Issue in `.planning/ISSUES-REGISTER.md` |
| `FIX-###` | Fix card — query with `ctx.py --show FIX-###` |
| `ADR-###` | Decision card — query with `ctx.py --rules <area>` |
| `migration 00NN` | Alembic revision |
| `INV-3` | 5 characterization goldens must stay byte/event-identical |
| `LOCK-B` | WS deletion complete — do not reintroduce WS run frames |
