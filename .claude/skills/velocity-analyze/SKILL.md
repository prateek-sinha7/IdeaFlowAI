---
name: velocity-analyze
description: Read-only deep analysis of a bug, architecture question, impact assessment, or capability question in VelocityAI/Flowin — reads registers, investigates the codebase, produces a structured report, and logs a Jira issue. Never modifies code. Use whenever asked to investigate, analyze, explain, or assess impact/risk in this repo without being asked to fix anything yet.
origin: VelocityAI
---

# VelocityAI Deep Codebase Analysis Protocol

You have been invoked to perform a deep analysis of an issue, discussion, or question about the
VelocityAI / Flowin codebase.

> ⚠️ **READ-ONLY MODE — STRICT RULE**
> This skill is ANALYSIS ONLY. You MUST NOT:
> - Modify, create, or delete any file
> - Write or edit any code
> - Apply any fix or workaround
> - Suggest changes inline to existing files
>
> **The architecture must remain as designed. No shortcuts or hacks are allowed.**
>
> Your output is a structured analysis report. Fixes are handled separately via the `velocity-fix`
> skill; new capability work via `velocity-feature`.

If the question hasn't been described yet (no symptom, area, or ticket given), ask for one before
proceeding — don't guess at what to analyze.

---

## Step 1 — Understand the User's Question

Parse the user's input carefully. Classify it into one of these analysis types:

| Type | Description | Examples |
|---|---|---|
| **Bug investigation** | Something is broken — find root cause | "pipeline fails with X error", "WebSocket doesn't connect" |
| **Impact analysis** | What would change if we do X | "what breaks if we change sandbox.py", "impact of updating config" |
| **Architecture question** | How does X work in this codebase | "how does fan-out work", "explain the artifact graph" |
| **Capability question** | Does the codebase support X | "can we add MCP support for Y", "is PDF upload possible" |
| **Performance question** | Why is X slow or expensive | "why does app_builder cost so much", "token usage analysis" |
| **Dependency question** | What depends on X | "what uses sandbox.py", "what calls the tier gate" |
| **Code quality / debt** | What's the state of X | "how solid is the WebSocket reconnect logic", "what's deferred" |

State the classification and the specific question at the top of your output.

---

## Step 2 — Read the Implementation Register

Read the full Implementation Register below in its entirety. It contains the complete history of
all phases, every file touched, every decision locked, and every piece of code deliberately
deleted. This is mandatory context for any analysis — it tells you what was intentional vs
accidental, what exists vs what was removed. Do not truncate or skim it.

#[[file:.planning/IMPLEMENTATION-REGISTER.md]]

---

## Step 3 — Read the Issues Register

Read the issues register to see known open bugs, deferred items, and previously diagnosed
problems. Do not re-diagnose issues that are already tracked here — if the question maps directly
onto an existing OPEN/DEFERRED/MONITORING/WONTFIX entry, say so at the top of your report and
point at the ID instead of treating it as new. If it's DEFERRED or WONTFIX, make that call-out
explicit rather than silently re-litigating it.

#[[file:.planning/ISSUES-REGISTER.md]]

---

## Step 4 — Read the Fix Register

Read recent fixes so you know what has already been patched and what root causes were found. If
this exact question was already resolved by a prior fix, cite the `FIX-NNN` entry directly rather
than re-deriving the same root cause from scratch — but still confirm the current code still
matches what the register claims (registers can go stale).

#[[file:.planning/FIX-REGISTER.md]]

---

## Step 5 — Deep Codebase Investigation

Based on the user's question and the context from Steps 2–4, investigate the codebase. Use ALL
available read tools:

- **Read files** — read the actual source code relevant to the question
- **Search for patterns** — search across multiple files for function calls, imports, class usages
- **Trace call chains** — follow the execution path from trigger to outcome
- **Cross-reference** — check both frontend and backend when the issue spans both

### Investigation depth guide

| Analysis type | Files to always read | Additional files to trace |
|---|---|---|
| Bug investigation | The file(s) mentioned in the error | Callers of the failing function; imports; test files for the component |
| Impact analysis | The file being changed | Every file that imports or calls it |
| Architecture question | The core file(s) for the feature | The capability port, the registered impl, the engine dispatch site, and the FE consumer |
| Capability question | `backend/agents/capabilities/registry.py` + relevant capability dir | The manifest schema, compiler, and FE surface |
| Performance question | The expensive operation's source | Token counting, model factory, agent count in the workflow YAML |
| Dependency question | The file in question | grep across all `*.py` / `*.ts` for imports/usages |

### Key architectural entry points (always consider these in any analysis)

| Area | Key files |
|---|---|
| Pipeline execution | `backend/agents/execution_engine/engine.py` |
| WebSocket / pipeline dispatch | `backend/app/api/websocket.py` |
| Capability registry | `backend/agents/capabilities/registry.py` |
| Model / Bedrock config | `backend/app/core/config.py`, `backend/app/agents/model_factory.py` |
| Sandbox / file isolation | `backend/app/agents/sandbox.py` |
| Workflow manifests | `backend/agents/workflows/<name>/workflow.yaml` |
| Frontend pipeline state | `frontend/src/hooks/useWorkflow.ts`, `frontend/src/hooks/useWebSocket.ts` |
| Frontend rendering | `frontend/src/components/preview/PreviewPanel.tsx` |
| Auth / entitlements | `backend/app/api/auth.py`, `backend/app/core/entitlements.py` |
| DB / migrations | `backend/alembic/versions/`, `backend/app/models/` |
| Artifact graph | `backend/agents/artifacts/graph.py` |

---

## Step 6 — Produce the Analysis Report

Write a structured analysis report. Use this exact format:

---

### 🔍 Analysis: [one-line title of what was analysed]

**Type:** [Bug investigation / Impact analysis / Architecture question / etc.]
**Question:** [The user's original question, restated clearly]
**Scope:** [Which files/areas were investigated]

---

#### 1. Summary (TL;DR)

> [2–4 sentences. What is the situation? What is the key finding? What is NOT broken?]

---

#### 2. Root Cause / Key Finding

[The most important finding. For a bug: the exact line(s) and why they fail. For an architecture
question: the definitive answer. For impact analysis: the exact set of things that would break.]

```
File: <path>
Line: <N>
Code: <the relevant snippet>
Why:  <explanation>
```

---

#### 3. Trace / Evidence

[The full call chain, data flow, or code path that supports the finding. Show the trace from
input to outcome.]

```
Entry point → function A → function B → [PROBLEM HERE] → outcome
```

Include relevant code snippets at each step. Cite file paths and line numbers.

---

#### 4. Related Decisions & Phase Context

[Which phases and locked decisions are relevant to this analysis? What was intentional?]

| Phase | Decision | Relevance |
|---|---|---|
| Phase N | [decision] | [why it matters to this analysis] |

---

#### 5. What Is Working Correctly

[Explicitly state what is NOT broken — important for scoping a fix correctly.]

- ✅ [thing that works] — [why it's fine]
- ✅ [thing that works]

---

#### 6. What Is Not Working / At Risk

[The confirmed problems, gaps, or risks found during investigation.]

- ❌ [problem] — [file:line] — [why it breaks / what triggers it]
- ⚠️ [risk] — [conditions under which it would fail]

---

#### 7. Impact Assessment

[Who / what is affected? How severe? How reproducible?]

| Dimension | Assessment |
|---|---|
| Severity | Critical / High / Medium / Low |
| Reproducibility | Always / Under specific conditions: [describe] / Rare |
| Users affected | All users / Pro+ / Enterprise / Admin only / Local dev only |
| Pipelines affected | [list workflow types] |
| Data at risk | Yes/No — [describe if yes] |

---

#### 8. Recommended Fix Approach

> ⚠️ This is analysis only — no code is changed here. Use the `velocity-fix` skill to apply.

[Describe the fix approach in plain English. Be specific enough that `velocity-fix` can act on it
immediately.]

**Option A (preferred):** [description — why it's preferred]
**Option B (alternative):** [description — tradeoffs]

Files that would need to change:
- `<path>` — [what needs to change and why]

Invariants to check before fixing:
- [ ] INV-1 / INV-2 / INV-3 / INV-12 / INV-13 / SC-001 — [specific risk for this fix]

---

#### 9. Open Questions

[Things that remain uncertain after this analysis and would need further investigation.]

- ❓ [question] — [why it matters / how to answer it]

---

#### 10. References

| Type | Location |
|---|---|
| Implementation Register | Phase N §[section] |
| Issues Register | ISS-NNN |
| Fix Register | FIX-NNN (if a prior fix is related) |
| Live verification | `.planning/live-verification/<file>` |
| Test files | `backend/tests/<path>` |

---

## Rules for This Skill

1. **No file modifications** — read-only. Zero exceptions.
2. **No code written** — do not output code blocks intended to be saved to a file.
3. **No "here's the fix"** — describe the approach but do not implement it.
4. **Be specific** — cite actual file paths, line numbers, function names. Never say "somewhere in the engine".
5. **Be honest about uncertainty** — if you cannot confirm something without running code, say so.
6. **Distinguish confirmed vs suspected** — mark unconfirmed findings with ⚠️.
7. **Cross-reference the register** — always check if a finding is a known issue (ISS-NNN) or already fixed (FIX-NNN) before reporting it as new.
8. **Report what works too** — an analysis that only lists problems without confirming what's healthy is not useful.

---

## Step 7 — Log to Jira

After producing the analysis report and presenting it to the user, create a Jira issue to track
the finding.

Use the Jira MCP tool (`jira_create_issue`) with the following field mapping:

| Jira field | Value |
|---|---|
| **project** | `KAN` |
| **issuetype** | `Bug` (if type is Bug investigation or confirmed broken) / `Task` (if architecture question, capability question, or code quality) |
| **summary** | The one-line title from the analysis report: "Analysis: [title]" |
| **description** | See description format below |
| **priority** | Map from Impact Assessment severity: Critical→Highest, High→High, Medium→Medium, Low→Low |
| **labels** | `velocity-analyze` |

### Jira Description Format

The description MUST follow this exact structure. Write it in plain readable text — do not use
Markdown symbols (##, **, backticks) but DO use the ALL-CAPS section headings exactly as shown
below, with a blank line between each section:

```
Bug Summary
[2-3 sentence summary of what was analysed and the key finding]

Current Concern
- [concern 1]
- [concern 2]
- [concern 3]

Expected Behaviour
- [expected 1]
- [expected 2]

Verification Required
- [verification step 1]
- [verification step 2]
- [verification step 3]

Acceptance Criteria
- [criterion 1]
- [criterion 2]
- [criterion 3]

Root Cause
[The specific file(s) and line(s) where the issue originates, in plain text]

Impact
[Severity level and who/what is affected]
```

Keep each section concise — aim for 3-6 bullets per section. Total description should be 300-600
words. Do NOT use Markdown syntax characters.

**Only create the Jira issue AFTER the full analysis report is written and presented to the
user.**

**Do NOT create a Jira issue if:**
- The analysis found no bug or risk (everything is working correctly)
- The finding is already tracked in the Issues Register (ISS-NNN) AND already has a known fix
- The user's question was purely informational (architecture explanation, how-does-X-work)

**Do create a Jira issue if:**
- A confirmed bug was found (❌ in section 6)
- A significant risk was identified (⚠️ in section 6 with Medium or higher severity)
- A new issue was found that is NOT already in the Issues Register

After creating the issue, append a line to the analysis report:

```
> **Jira issue created:** [KAN-XXX](https://velocityai-hex.atlassian.net/browse/KAN-XXX)
```

If the Jira MCP tool isn't available in the current session, say so explicitly and skip this step
rather than failing silently — don't let a missing integration block delivering the analysis.

---

## Guardrails for this skill

- Never skip Steps 2–4 — reporting a known, already-triaged issue as new wastes the user's time
  and contradicts the registers this repo relies on.
- Never write or suggest inline code changes — that's what `velocity-fix` and `velocity-feature`
  are for. If mid-analysis it becomes obvious the user actually wants the fix applied, say so and
  suggest switching skills rather than drifting into edits.
- If a "finding" turns out to be a locked, intentional decision (per Step 4/Step 2), say so in
  section 4/5 rather than listing it under section 6 as a problem.
