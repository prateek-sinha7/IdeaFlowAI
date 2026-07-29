---
name: velocityai-analysis
description: Perform read-only deep analysis of bugs, architecture, impact, capabilities, performance, dependencies, and technical debt in VelocityAI/Flowin. Use when the user asks to investigate, analyze, explain, trace, or assess risk without implementing a fix.
compatibility: Kiro workspace skill requiring read access to the Flowin repository. Jira logging is optional and requires a configured Jira MCP server.
metadata:
  origin: VelocityAI
  version: "1.0"
---

# VelocityAI Deep Codebase Analysis

Perform a deep, evidence-based analysis of the VelocityAI/Flowin codebase. This is an analysis-only skill.

## Read-only contract

Do not:

- Modify, create, move, or delete repository files.
- Write or edit implementation code.
- Apply a fix or workaround.
- Run destructive commands or commands that change repository state.
- Drift from investigation into implementation.

You may use Kiro's repository-reading, code-search, and read-only command tools. Jira issue creation is the only permitted external write, and only when the criteria in this skill require it.

If the user has not supplied a symptom, question, affected area, or ticket, ask for the missing context instead of guessing.

## Required workflow

Follow these steps in order. Never skip the three planning registers.

### 1. Classify the request

Classify the request as one of:

| Type | Purpose |
|---|---|
| Bug investigation | Find the root cause of broken behavior |
| Impact analysis | Determine what would change or break if something changes |
| Architecture question | Explain how an existing subsystem works |
| Capability question | Determine whether the codebase supports a requested capability |
| Performance question | Explain latency, resource use, or cost |
| Dependency question | Trace callers, imports, consumers, and downstream effects |
| Code quality or debt | Assess robustness, gaps, and deferred work |

State the classification and the precise question in the report.

### 2. Read the implementation register

Read `.planning/IMPLEMENTATION-REGISTER.md` in full using an available Kiro file-reading tool. Use it to distinguish intentional behavior, deleted functionality, completed phases, and locked decisions.

### 3. Read the issues register

Read `.planning/ISSUES-REGISTER.md` in full. If the question maps to an OPEN, DEFERRED, MONITORING, or WONTFIX entry, identify that issue near the start of the report. Do not present an already tracked issue as a new discovery.

### 4. Read the fix register

Read `.planning/FIX-REGISTER.md` in full. Cite a related `FIX-NNN` entry rather than rediscovering it, but verify that the current implementation still matches the register.

### 5. Investigate the codebase

Start with one broad repository search based on the user's question, then read the relevant files and trace the behavior from entry point to outcome. Make additional searches only when a required fact remains unresolved.

Use Kiro's available read-only tools to:

- Read the source files involved.
- Search imports, calls, definitions, registrations, and consumers.
- Trace call chains and data flow.
- Cross-reference backend and frontend behavior when the issue spans both.
- Read relevant tests as evidence; do not add or modify tests.
- Run a targeted read-only test or diagnostic only when needed to distinguish confirmed behavior from a hypothesis.

Investigation guidance:

| Analysis type | Start with | Then trace |
|---|---|---|
| Bug investigation | Files named by the symptom or error | Callers, imports, tests, and failure handling |
| Impact analysis | The proposed change point | Every importer, caller, consumer, schema, and test |
| Architecture question | The subsystem's core files | Ports, registered implementations, dispatch, persistence, and UI consumers |
| Capability question | Capability registry and relevant capability directory | Manifest schema, compiler, execution path, and frontend surface |
| Performance question | The expensive operation | Model calls, token accounting, workflow fan-out, I/O, retries, and caching |
| Dependency question | The referenced symbol or file | All imports, calls, registrations, and runtime lookups |
| Code quality or debt | The component and its tests | Known issues, fixes, boundaries, error paths, and observability |

Always consider these architectural entry points when relevant:

| Area | Key paths |
|---|---|
| Pipeline execution | `backend/agents/execution_engine/engine.py` |
| WebSocket and pipeline dispatch | `backend/app/api/websocket.py` |
| Capability registry | `backend/agents/capabilities/registry.py` |
| Model and Bedrock configuration | `backend/app/core/config.py`, `backend/app/agents/model_factory.py` |
| Sandbox and file isolation | `backend/app/agents/sandbox.py` |
| Workflow manifests | `backend/agents/workflows/<name>/workflow.yaml` |
| Frontend pipeline state | `frontend/src/hooks/useWorkflow.ts`, `frontend/src/hooks/useWebSocket.ts` |
| Frontend rendering | `frontend/src/components/preview/PreviewPanel.tsx` |
| Authentication and entitlements | `backend/app/api/auth.py`, `backend/app/core/entitlements.py` |
| Database and migrations | `backend/alembic/versions/`, `backend/app/models/` |
| Artifact graph | `backend/agents/artifacts/graph.py` |

## Evidence standards

- Cite exact repository paths and current line numbers.
- Name functions, classes, capabilities, events, and configuration keys precisely.
- Include only short code excerpts needed to support a finding.
- Separate confirmed findings from hypotheses.
- If runtime verification was not possible, state what remains unverified and why.
- Explain what is working correctly, not only what is broken.
- Treat planning registers as context, not unquestionable truth; verify claims against current code.
- Do not use internet sources unless the question requires current external documentation. If internet research is necessary, prefer official sources and cite links.

## Required report format

Use the following structure. Omit no numbered section; write `None` when a section has no applicable content.

### Analysis: [one-line title]

**Type:** [classification]
**Question:** [clear restatement]
**Scope:** [files and subsystems investigated]

#### 1. Summary

Provide a two-to-four sentence answer stating the key finding, impact, and what is not broken.

#### 2. Root Cause or Key Finding

State the definitive finding. For a bug, identify the exact mechanism that fails. For architecture or capability analysis, give the direct answer. For impact analysis, identify the affected surfaces.

```text
File: <path>
Line: <line or range>
Symbol: <function, class, or key>
Evidence: <short explanation or excerpt>
Why: <mechanism and consequence>
```

#### 3. Trace and Evidence

Show the execution path or dependency chain:

```text
Entry point -> component A -> component B -> finding -> outcome
```

Support each important step with paths and line numbers.

#### 4. Related Decisions and Phase Context

| Phase or register entry | Decision or history | Relevance |
|---|---|---|
| Phase N / ISS-NNN / FIX-NNN | Summary | Why it matters |

#### 5. What Is Working Correctly

- [Working behavior] - [supporting evidence]

#### 6. What Is Not Working or Is at Risk

Label each item as `Confirmed` or `Risk`.

- **Confirmed:** [problem] - `[path:line]` - [trigger and consequence]
- **Risk:** [risk] - [conditions under which it could fail]

#### 7. Impact Assessment

| Dimension | Assessment |
|---|---|
| Severity | Critical / High / Medium / Low |
| Reproducibility | Always / specific conditions / rare / not applicable |
| Users affected | User groups or environments |
| Workflows affected | Workflow types or none |
| Data at risk | Yes or No, with concise reasoning |

#### 8. Recommended Fix Approach

Analysis only: describe the smallest appropriate fix without editing files or supplying a drop-in patch.

**Preferred approach:** [approach and why]

**Alternative:** [trade-offs, or None]

Files likely to change:

- `<path>` - [intended responsibility of the change]

Invariants to verify during implementation:

- [ ] Relevant Flowin invariant or locked decision and its specific risk
- [ ] Characterization, architecture, and targeted behavior checks

#### 9. Open Questions

- [Unresolved question, why it matters, and how to verify it]

#### 10. References

| Type | Location |
|---|---|
| Implementation register | Phase and section |
| Issues register | `ISS-NNN` or None |
| Fix register | `FIX-NNN` or None |
| Source and tests | Repository paths |
| Live verification | `.planning/live-verification/<file>` or None |

## Jira logging

After drafting the report, decide whether a Jira issue is warranted. If it is, use an available Jira MCP create-issue tool; MCP tool names vary by configuration, so do not assume a literal tool name.

Create an issue only when:

- A new bug is confirmed.
- A new, significant Medium-or-higher risk is confirmed.
- The finding is not already adequately tracked in the Issues Register.

Do not create an issue when:

- No bug or meaningful risk was found.
- The issue is already tracked and has a known fix.
- The request is purely informational, including architecture explanations.
- A Jira MCP integration is unavailable. In this case, state that Jira logging was skipped.

Use these fields when supported by the configured Jira integration:

| Jira field | Value |
|---|---|
| Project | `KAN` |
| Issue type | `Bug` for confirmed broken behavior; otherwise `Task` |
| Summary | `Analysis: [report title]` |
| Priority | Critical to Highest, High to High, Medium to Medium, Low to Low |
| Labels | `velocity-analyze` |

Use this plain-text description structure, with concise content and no Markdown formatting symbols:

```text
Bug Summary
[Two-to-three sentence summary]

Current Concern
- [concern]

Expected Behaviour
- [expectation]

Verification Required
- [verification step]

Acceptance Criteria
- [criterion]

Root Cause
[Specific files, symbols, and lines]

Impact
[Severity and affected users or workflows]
```

Draft the analysis first, create the Jira issue if required, and then present the report with this final line:

```text
Jira issue created: [KAN-XXX](https://velocityai-hex.atlassian.net/browse/KAN-XXX)
```

If no issue was created, state the reason briefly after the report.

## Guardrails

1. Never skip the implementation, issues, or fix registers.
2. Remain read-only even when the likely fix is obvious.
3. Describe a fix approach, but do not provide a ready-to-apply patch.
4. Do not contradict locked decisions or resurrect deliberately removed behavior.
5. Do not report known or intentional behavior as a new defect.
6. Keep findings specific, evidenced, and scoped to the user's question.
7. Mark uncertainty explicitly.
8. If the user asks to implement the fix, stop using this skill and handle implementation as a separate task.