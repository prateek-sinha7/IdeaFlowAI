---
inclusion: manual
---

# /velocity-ai-analyze — VelocityAI Deep Codebase Analysis Protocol

You have been invoked to perform a deep analysis of an issue, discussion, or question about the VelocityAI / Flowin codebase.

> ⚠️ **READ-ONLY MODE — STRICT RULE**
> This command is ANALYSIS ONLY. You MUST NOT modify, create, or delete any file.
> Your output is a structured analysis report. Fixes are handled separately via `/velocity-ai-fix`.

---

## Step 1 — Understand the User's Question

Classify the question:

| Type | Examples |
|---|---|
| **Bug investigation** | "pipeline fails with X error", "SSE stream doesn't connect" |
| **Impact analysis** | "what breaks if we change sandbox.py" |
| **Architecture question** | "how does fan-out work", "explain the artifact graph" |
| **Capability question** | "can we add MCP support for Y" |
| **Performance question** | "why does app_builder cost so much" |
| **Dependency question** | "what uses sandbox.py" |
| **Code quality / debt** | "how solid is the SSE reconnect logic" |

---

## Step 2 — Prime the Knowledge Store

Read these four files in order. Together they are ~12.5K tokens and replace the ~383K the registers would cost.

```
.knowledge/surface/ARCHITECTURE.md   ← WHERE WE ARE: milestone, phase, enforced boundaries, ADRs
.knowledge/INVARIANTS.md              ← project-wide constraints — bind every change
.knowledge/surface/RULES.md           ← decisions in force — constrain what you may write
.knowledge/surface/INDEX.md           ← one line per fix / issue / phase (168 fixes, 49 issues, 23 phases)
```

Check freshness first (optional but fast):
```bash
python3 scripts/knowledge/check.py
```
Exit 2 = broken (stop, report). Exit 1 = usable with caveats. Exit 0 = clean.

**Do NOT read `.planning/FIX-REGISTER.md`, `ISSUES-REGISTER.md`, or `IMPLEMENTATION-REGISTER.md` in full.** The card store exists to prevent exactly this.

---

## Step 3 — Query for the Specific Task

```bash
# Search by symptom — finds matching fixes, issues, decisions
python3 scripts/knowledge/ctx.py "<symptom words>"

# Find every rule and fix that touches a specific file
python3 scripts/knowledge/ctx.py --for <file path>

# Active decisions for an area
python3 scripts/knowledge/ctx.py --rules <area>

# Open one card in full
python3 scripts/knowledge/ctx.py --show FIX-NNN

# Secondary types (bugs, tests, requirements) — not in INDEX.md by default
python3 scripts/knowledge/ctx.py --type bug "<symptom>"
python3 scripts/knowledge/ctx.py --type issue "<symptom>"
```

Open only the 2–4 cards returned. If a phase card matches, read its shard at `.planning/_register-parts/` — never the full implementation register.

If `ctx.py` cannot answer, targeted grep is acceptable:
```bash
grep_search query="<symptom>" includePattern="**/.planning/FIX-REGISTER.md"
```

---

## Step 4 — Load Domain Context

Load the `fileMatch` steering file that matches the area being analysed:

| Area | Steering file |
|---|---|
| `execution_engine/` | `#backend-engine.md` |
| `capabilities/` | `#backend-capabilities.md` |
| `app/api/` | `#backend-api.md` |
| `app/models/`, `alembic/` | `#backend-models-migrations.md` |
| Run screen / preview / results | `#frontend-run-screen.md` |
| Chat, SSE, transport hooks | `#frontend-chat.md` |
| Workflow, catalog, composer | `#frontend-workflow.md` |
| Shell, settings, design tokens | `#frontend-shell.md` |

---

## Step 5 — Deep Codebase Investigation

Use ALL available read tools: **Read files · Search for patterns · Trace call chains · Cross-reference frontend + backend.**

### Key architectural entry points

| Area | Key files | Notes |
|---|---|---|
| Pipeline execution | `backend/agents/execution_engine/engine.py` | |
| SSE down-channel | `backend/app/api/run_stream.py` | Replaces deleted `websocket.py` |
| REST up-channel | `backend/app/api/run_commands.py` | Gate/cancel/answers/messages/revisions |
| Shared run infra | `backend/app/api/run_engine.py` | Relocated from `websocket.py` |
| Handoff WebSocket | `backend/app/api/websocket_handoff.py` | Only remaining WS endpoint |
| Capability registry | `backend/agents/capabilities/registry.py` | |
| Model / Bedrock config | `backend/app/core/config.py`, `backend/app/agents/model_factory.py` | |
| Workflow manifests | `backend/agents/workflows/<name>/workflow.yaml` | |
| Frontend SSE hook | `frontend/src/hooks/useRunStream.ts` | Replaces deleted `useWebSocket.ts` |
| Frontend connection provider | `frontend/src/providers/RunConnectionProvider.tsx` | |
| Frontend run screen | `frontend/src/app/dashboard/page.tsx`, `frontend/src/components/layout/DashboardLayout.tsx` | |
| Auth / entitlements | `backend/app/api/auth.py`, `backend/app/core/entitlements.py` | |
| DB / migrations | `backend/alembic/versions/`, `backend/app/models/` | Head: 0026 |
| Scoped store / IDOR | `backend/agents/authz.py` | |
| Concierge | `backend/app/agents/chat/concierge.py` | |

> ⚠️ **Deleted files — do NOT read or reference:**
> `websocket.py` · `useWebSocket.ts` · `PrototypePipelineView.tsx` · `ReviewGatePanel.tsx` · `QuestionnairePanel.tsx` · `AgentProgressPanel.tsx`

---

## Step 6 — Produce the Analysis Report

```markdown
### 🔍 Analysis: [one-line title]

**Type:** [Bug investigation / Impact analysis / Architecture question / etc.]
**Question:** [restated clearly]
**Scope:** [which files/areas were investigated]

#### 1. Summary (TL;DR)
[2–4 sentences]

#### 2. Root Cause / Key Finding
File: <path>
Line: <N>
Code: <snippet>
Why:  <explanation>

#### 3. Trace / Evidence
Entry point → function A → function B → [PROBLEM HERE] → outcome

#### 4. Related Decisions & Phase Context
| Phase | Decision | Relevance |
|---|---|---|

#### 5. What Is Working Correctly
- ✅ [thing] — [why fine]

#### 6. What Is Not Working / At Risk
- ❌ [problem] — [file:line] — [why it breaks]
- ⚠️ [risk] — [conditions]

#### 7. Impact Assessment
| Dimension | Assessment |
|---|---|
| Severity | Critical / High / Medium / Low |
| Reproducibility | Always / Conditional / Rare |
| Users affected | [scope] |

#### 8. Recommended Fix Approach
> Analysis only — use `/velocity-ai-fix` to apply.

**Option A (preferred):** [description]
**Option B:** [tradeoffs]

Files that would need to change:
- `<path>` — [what and why]

Invariants to check:
- [ ] INV-1 / INV-3 / INV-12 / SC-001

#### 9. Open Questions
- ❓ [question] — [why it matters]

#### 10. References
| Type | Location |
|---|---|
| Card | `ctx.py --show FIX-NNN` |
| Domain steering | `#backend-engine.md` / `#frontend-chat.md` |
| Issues Register | ISS-NNN |
| Architecture | `.knowledge/surface/ARCHITECTURE.md` |
```

---

## Rules for This Command

1. **No file modifications** — read-only. Zero exceptions.
2. **Never load a register wholesale** — use `ctx.py` or targeted `grep_search`.
3. **Cite actual file paths, line numbers, function names** — never say "somewhere in the engine".
4. **Distinguish confirmed vs suspected** — mark unconfirmed findings with ⚠️.
5. **Check the card store first** — a finding already in FIX-NNN or ISS-NNN is not new.
6. **Report what works too** — an analysis that only lists problems is not useful.
7. **Do not reference deleted files** — `websocket.py` and `useWebSocket.ts` are gone.

---

## Step 7 — Log to Jira

After producing the analysis report, create a Jira issue to track the finding.

Use `jira_create_issue` with:

| Field | Value |
|---|---|
| **project** | `KAN` |
| **issuetype** | `Bug` (confirmed broken) / `Task` (architecture/capability/quality) |
| **summary** | "Analysis: [one-line title]" |
| **priority** | Critical→Highest · High→High · Medium→Medium · Low→Low |
| **labels** | `velocity-ai-analyze` |

**Description format** (plain text, ALL-CAPS section headings, no Markdown symbols):

```
Bug Summary
[2-3 sentences]

Current Concern
- [concern 1]
- [concern 2]

Expected Behaviour
- [expected 1]

Verification Required
- [step 1]

Acceptance Criteria
- [criterion 1]

Root Cause
[file(s) and line(s)]

Impact
[severity and scope]
```

**Only create a Jira issue if:**
- A confirmed bug was found (❌ in section 6), OR
- A significant risk (⚠️ Medium or higher) that is NOT already in the card store

After creating, append to the report:
```
> **Jira issue created:** [KAN-XXX](https://velocityai-hex.atlassian.net/browse/KAN-XXX)
```
