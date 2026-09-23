# Design Document: Prototype Revision Analyzer

## Overview

The Prototype Revision Analyzer introduces a new agent (`prototype-revision-analyzer`) that executes **before** the tier-classification step in every prototype revision request. It reads the full Previous_HTML and the Revision_Instruction, reasons about the scope of change, and produces two outputs:

1. A **tier rating** (`small` | `large` | `feature`) — replacing the existing single-call `_classify_revision_tier` LLM heuristic with a more deliberate, structured determination.
2. A **Solution Plan** — a detailed, component-level implementation blueprint forwarded to every downstream revision agent (`prototype-revision-agent`, `prototype-revision-planner`, `prototype-revision-feature-specify`) so each begins with a pre-analyzed description of the changes needed, rather than only the raw user instruction.

### Architectural Boundaries

This feature is implemented entirely in the **app layer** (`app/api/run_commands.py`, new `app/agents/revision_analyzer.py`) and the **agent definition layer** (`agents/prompts/`, `agents/execution_engine/context.py`). The Execution_Engine kernel (`engine.py`) is extended by one additive, generic seam — a new `ectx.analyzer_solution` field and its corresponding injection block at position 5 of `_compose_context_message`. No pipeline-type guard or agent-id literal enters the kernel (SC-001 / INV-1).

All existing subsystems — SSE event stream, revision versioning, HTML preview, step tracking, file artifacts, Concierge run chat, audit log, and agent progress — are preserved unchanged.

---

## Architecture

### Data Flow (Happy Path)

```
POST /api/runs/{id}/revisions
    │
    ├─ Owner gate + parent lookup (existing)
    │
    ├─ [NEW] run_analyzer(instruction, html, event_queue, model_id)
    │       ├─ emit agent_start{prototype-revision-analyzer}   → event_queue
    │       ├─ LLM call (build_model, max_tokens=4096)
    │       ├─ parse_analyzer_output(raw) → (tier, solution)
    │       ├─ emit agent_complete{prototype-revision-analyzer} → event_queue
    │       └─ emit revision_analyzer_complete{tier, solution[:200]} → event_queue
    │         returns (tier, solution)
    │
    ├─ effective_target = _REVISION_TIER_TARGET_MAP[tier]
    │
    ├─ _mint_revision_row(db, ..., agent_count=pipeline_agents+1)
    │
    ├─ Set ectx.analyzer_solution = solution   (BEFORE first agent step)
    │
    └─ _drive_revision_to_queue(...)
            └─ Engine → _compose_context_message
                    └─ [NEW pos-5] if ectx.analyzer_solution:
                           append "=== REVISION ANALYSIS ===\n{solution}"
```

### Fallback Chain

```
run_analyzer raises exception
    └─ log error
    └─ _classify_revision_tier(instruction, parent_run_id)
            └─ raises exception
                    └─ default tier = "large"
```

> Note: The existing code defaults to `"small"` on `_classify_revision_tier` failure. The fallback chain for the Analyzer path uses `"large"` as the double-failure default (safer than `"small"` for an unknown request — matches the semantics already in `_classify_revision_tier`'s concierge-path default).

### Concierge Path

The Concierge disposal path (`CHANNEL_REVISION` in `post_message`) also calls `_classify_revision_tier` today. After this feature, it calls `run_analyzer` with the same interface, sourcing `existing_html` from the parent run's `output` column (identical to the existing Concierge path HTML extraction).

---

## Components and Interfaces

### 1. `prototype-revision-analyzer` AGENT.md

**Path:** `backend/agents/prompts/prototype-revision-analyzer/AGENT.md`

Frontmatter:

```yaml
---
consumes: []
context_from: []
guardrails:
- html-prototype
- accessibility
icon: 🔍
id: prototype-revision-analyzer
max_tokens: 4096
name: Prototype Revision Analyzer
order: 1
pipeline_type: prototype_revision
produces:
- prototype-revision-analyzer
role: analyzer
tools: []
---
```

The agent has `order: 1`, placing it before `prototype-revision-agent` which must be shifted to `order: 2`.

**System prompt responsibilities:**

- Read Revision_Instruction + Previous_HTML from context (injected via the `previous_run` context provider's standard seam)
- Reason step by step: scope of change, affected components, whether new pages/routes are introduced
- Emit a structured Markdown document with exactly two H2 sections: `## Tier` and `## Solution Plan`
- Apply the highest-tier-wins rule for mixed-scope instructions
- For each tier, include concrete positive and negative examples in the decision criteria

**Tier Decision Criteria (embedded in system prompt):**

| Tier | When to use | Positive example | Negative example |
|------|-------------|------------------|------------------|
| `small` | Targeted change to 1–3 elements, no new routes, no new JS functions | "Fix the broken Login button label (typo 'Lgoin')" | "Fix all broken navigation across 5 pages" |
| `large` | Structural change affecting 3+ components, coordinated HTML/CSS/JS edits across pages, multi-page layout work | "Redesign the dashboard layout, add a sidebar nav, update all page headers to use it" | "Add a brand-new checkout page that doesn't exist" |
| `feature` | New page, new route, new workflow capability absent from prototype | "Add an onboarding flow with 3 steps and progress indicator" | "Fix the broken 'View Details' modal" |

**Output contract:**

```markdown
## Tier
small

## Solution Plan
[detailed multi-sentence description of what changes are needed, naming exact element ids, function names, route paths, and CSS classes]
```

### 2. `parse_analyzer_output` — Pure Parser Function

**Path:** `backend/app/agents/revision_analyzer.py` (new file)

```python
def parse_analyzer_output(raw: str) -> tuple[str, str]:
    """Pure parser — no I/O, no LLM calls.

    Extracts:
      - tier: first non-blank line under '## Tier', lowercased, validated.
              Defaults to "large" + warning if absent or unrecognized.
      - solution: full text of '## Solution Plan' section.
                  Defaults to "" + warning if absent.

    Returns (tier, solution).
    """
```

**Parsing algorithm:**

1. Split `raw` into H2-delimited sections by scanning for lines matching `^## `.
2. Find the section whose header is `Tier` (case-insensitive trim).
3. In the tier section body, find the first non-blank line; `.strip().lower()` it.
4. Validate: if result not in `{"small", "large", "feature"}`, log warning including `raw[:500]`, set tier = `"large"`.
5. Find the section whose header is `Solution Plan` (case-insensitive trim); capture the full body string (preserving interior whitespace).
6. If the `## Solution Plan` section is absent, log warning, set solution = `""`.
7. Return `(tier, solution)`.

**Error table:**

| Condition | tier result | solution result | Log level |
|-----------|-------------|-----------------|-----------|
| Both sections present, tier valid | extracted | extracted | DEBUG |
| `## Tier` absent | `"large"` | extracted or `""` | WARNING (first 500 chars) |
| `## Tier` present but value unrecognized | `"large"` | extracted or `""` | WARNING (first 500 chars) |
| `## Solution Plan` absent | extracted | `""` | WARNING |
| Both sections absent | `"large"` | `""` | WARNING |

### 3. `run_analyzer` — Async Orchestrator

**Path:** `backend/app/agents/revision_analyzer.py`

```python
async def run_analyzer(
    instruction: str,
    existing_html: str,
    event_queue: asyncio.Queue,
    parent_run_id: str,
    model_id: str | None = None,
) -> tuple[str, str]:
    """Invoke the prototype-revision-analyzer agent and return (tier, solution).

    Emits three SSE events onto event_queue:
      1. agent_start    for prototype-revision-analyzer
      2. agent_complete for prototype-revision-analyzer
      3. revision_analyzer_complete with {tier, solution_preview: solution[:200]}

    On any exception: logs error, falls back to _classify_revision_tier.
    If that also fails: defaults to ("large", "").
    """
```

**Implementation steps:**

1. Build the prompt (see prompt structure below).
2. `await event_queue.put({"type": "agent_start", "data": {...}})` — with `agent_id`, `name`, `role`, `icon`, `index`, `total` keys matching `_REQUIRED_DATA_KEYS["agent_start"]`.
3. `llm = build_model(model_id, max_tokens=4096)` — same `build_model` import used by `_classify_revision_tier`.
4. `response = await llm.ainvoke([HumanMessage(content=prompt)])`.
5. `tier, solution = parse_analyzer_output(response.content)`.
6. `await event_queue.put({"type": "agent_complete", "data": {...}})` — with `agent_id`, `name`, `duration`, `output_length`, `input_tokens`, `output_tokens`, `total_tokens` keys.
7. `await event_queue.put({"type": "revision_analyzer_complete", "data": {"tier": tier, "solution_preview": solution[:200]}})`.
8. Return `(tier, solution)`.

**Analyzer prompt structure:**

```
You are the Prototype Revision Analyzer. Your job is to read a revision instruction
and the current prototype HTML, then output a structured analysis.

=== REVISION INSTRUCTION ===
{instruction}

=== CURRENT PROTOTYPE HTML ===
{existing_html}

Output ONLY this Markdown structure — no preamble, no closing remarks:

## Tier
[one word: small, large, or feature]

## Solution Plan
[detailed description of what needs to change, naming exact element ids, routes, functions, and CSS classes]
```

> Note: Unlike `_classify_revision_tier`, **no HTML truncation** — the full `existing_html` is passed. This satisfies Requirement 8.7 (full content for Solution_Plan quality). The 4096 token budget on the analyzer output is the output cap, not the input cap.

**Exception handling:**

```python
except Exception as exc:
    logger.error("run_analyzer failed (%s) — falling back to _classify_revision_tier", exc, exc_info=True)
    try:
        tier = await _classify_revision_tier(instruction, parent_run_id, model_id)
        return (tier, "")
    except Exception as exc2:
        logger.error("_classify_revision_tier fallback also failed (%s) — defaulting to large", exc2)
        return ("large", "")
```

### 4. `ExecutionContext.analyzer_solution` Field

**Path:** `backend/agents/execution_engine/context.py`

Add to the prototype-revision group (after `revision_baseline_console`):

```python
# analyzer_solution: the Revision_Analyzer's pre-analyzed implementation
# blueprint. Published before the first agent step by create_revision /
# _dispose_concierge_revision so _compose_context_message can inject the
# === REVISION ANALYSIS === block at position 5 (after === USER GUIDANCE ===).
# Default "" → DORMANT on every non-analyzer run → INV-3 byte-parity holds.
# Additive field (the same D-03 idiom as redo_directive / steering_notes).
analyzer_solution: str = ""
```

INV-3 safety: default is `""`, so all 5 existing golden runs that do not set this field produce identical context messages. Not in `_VOLATILE_STRIP_KEYS` — it is stable, run-specific content (Requirement 7.5).

### 5. `_compose_context_message` Extension

**Path:** `backend/agents/execution_engine/engine.py`

Add a new seam at position 5, after the `=== USER GUIDANCE ===` block (the `steering_notes` consume-once queue):

```python
# Position 5 — Revision Analysis (additive seam, INV-1 / SC-001 compliant)
if ectx.analyzer_solution:
    blocks.append(
        f"=== REVISION ANALYSIS ===\n{ectx.analyzer_solution}"
    )
```

No pipeline-type guard, no agent-id check — generic field truthiness only (INV-1 compliant). Empty default → dormant on all existing runs → INV-3 byte-identical.

### 6. `create_revision` Endpoint Changes

**Path:** `backend/app/api/run_commands.py`

Replace the `_classify_revision_tier` call block with `run_analyzer`:

```python
if body.target_artifact_type == "prototype_output":
    from app.agents.revision_analyzer import run_analyzer
    # run_analyzer emits agent_start / agent_complete / revision_analyzer_complete
    # events directly onto event_queue before the child run is minted.
    tier, analyzer_solution = await run_analyzer(
        instruction=body.instruction,
        existing_html=existing_html,   # extracted inline before this block
        event_queue=event_queue,
        parent_run_id=run_id,
        model_id=getattr(current_user, "preferred_model", None),
    )
    effective_target = _REVISION_TIER_TARGET_MAP.get(tier, "prototype_output")
```

After `_mint_revision_row`:

```python
# Store analyzer_solution BEFORE the first agent step (atomicity requirement).
# Also persist the revision_analyzer_complete event durably.
# If either fails, abort with error status (Requirement 7.6).
try:
    ectx = _get_or_create_ectx(child_run_id)   # fetch the run's ExecutionContext
    ectx.analyzer_solution = analyzer_solution
    # revision_analyzer_complete was already emitted onto event_queue above;
    # the ScopedStore.append_event call in the engine will persist it durably
    # as part of the normal event tail when the engine starts.
except Exception as exc:
    logger.error("Failed to store analyzer_solution for run=%s: %s", child_run_id, exc)
    _abort_revision_run(child_run_id, exc)
    raise HTTPException(status_code=500, detail="Revision analyzer context storage failed")
```

> Implementation note: The `revision_analyzer_complete` event is emitted by `run_analyzer` onto the `event_queue` before the child run is minted. It rides the same `ScopedStore.append_event` stamping boundary (seq/event_id) as all other engine events, fulfilling Requirement 7.2. The `ectx.analyzer_solution` storage and event emission are treated as an atomic pair: if the context field cannot be stored, the revision run is aborted (Requirement 7.6).

**`agent_count` update in `_mint_revision_row`:**

The existing code uses `len(_rev_agents) or 1`. After this feature, the analyzer is not itself a step in `_rev_agents` (it runs pre-mint in the app layer). Therefore `agent_count` is set to `len(_rev_agents) + 1` explicitly when the analyzer path is active:

```python
agent_count=len(_rev_agents) + 1,   # +1 for the pre-mint Analyzer step
```

This change applies unconditionally for `prototype_output` revisions. The `+1` accounts for the pre-run Analyzer agent displayed in the frontend progress bar (Requirement 9.6).

### 7. AGENT.md Updates for Downstream Agents

#### `prototype-revision-agent` AGENT.md

**Path:** `backend/agents/prompts/prototype-revision-agent/AGENT.md`

Two changes:
1. Frontmatter: `order: 1` → `order: 2`
2. System prompt: Add at the top of the prompt body (before "You are a senior frontend engineer…"):

```
> **When an `=== REVISION ANALYSIS ===` block is present in your context, follow its
> guidance precisely. It contains a pre-analyzed implementation blueprint that takes
> precedence over your own interpretation of the raw user instruction. Read the
> Solution Plan, then implement it exactly as described.**
```

#### `prototype-revision-planner` AGENT.md

**Path:** `backend/agents/prompts/prototype-revision-planner/AGENT.md`

Add to the system prompt (before "## ABSOLUTE OUTPUT CONTRACT"):

```
> **When an `=== REVISION ANALYSIS ===` block is present in your context, use the
> Solution Plan as the primary input for your task decomposition. The Solution Plan
> names the specific components, element IDs, functions, and routes that need to
> change — your task list should map directly onto those named components.**
```

#### `prototype-revision-feature-specify` AGENT.md

**Path:** `backend/agents/prompts/prototype-revision-feature-specify/AGENT.md`

Add to the system prompt (before "You are a product designer…"):

```
> **When an `=== REVISION ANALYSIS ===` block is present in your context, ground
> your feature specification in the Solution Plan. The plan identifies the new
> pages, routes, and capabilities the Analyzer determined are needed — reference
> them explicitly in your spec sections.**
```

### 8. `_DOCUMENTED_EVENT_TYPES` Update

**Path:** `backend/tests/agents/test_phase3_cutover_verify.py`

Add to `_DOCUMENTED_EVENT_TYPES`:

```python
# ── Revision Analyzer events (prototype-revision-analyzer feature) ───────
# revision_analyzer_complete — emitted by run_analyzer after the analyzer
# agent returns, with payload {tier, solution_preview}. Added to the
# vocabulary so the INV-3 golden suite recognises it without re-baselining
# the 5 existing characterization goldens (which never trigger the analyzer).
"revision_analyzer_complete",
```

---

## Data Models

### `ExecutionContext` — New Field

```python
@dataclass
class ExecutionContext:
    # ... existing fields ...

    # ── Prototype-revision group ──────────────────────────────────────────
    revision_original_html: str = ""
    revision_instruction: str | None = None
    revision_baseline_static: set[str] = field(default_factory=set)
    revision_baseline_console: set[str] = field(default_factory=set)
    # analyzer_solution: the Revision_Analyzer's pre-analyzed implementation
    # blueprint. Published before the first agent step. Default "" → DORMANT
    # on every non-analyzer run → INV-3 byte-parity holds.
    analyzer_solution: str = ""
```

### SSE Event Payloads

**`agent_start`** (existing shape, new agent):
```json
{
  "type": "agent_start",
  "data": {
    "agent_id": "prototype-revision-analyzer",
    "name": "Prototype Revision Analyzer",
    "role": "analyzer",
    "icon": "🔍",
    "index": 1,
    "total": "<agent_count>"
  }
}
```

**`agent_complete`** (existing shape, new agent):
```json
{
  "type": "agent_complete",
  "data": {
    "agent_id": "prototype-revision-analyzer",
    "name": "Prototype Revision Analyzer",
    "duration": 2.4,
    "output_length": 450,
    "input_tokens": 3200,
    "output_tokens": 380,
    "total_tokens": 3580
  }
}
```

**`revision_analyzer_complete`** (new):
```json
{
  "type": "revision_analyzer_complete",
  "data": {
    "tier": "large",
    "solution_preview": "<first 200 chars of solution plan>"
  }
}
```

### `parse_analyzer_output` Return Type

```python
tuple[str, str]
# (tier, solution)
# tier:     one of {"small", "large", "feature"} — always
# solution: raw string (may be empty if absent from LLM output)
```

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Parser output completeness — tier always in valid set

*For any* raw string passed to `parse_analyzer_output`, the returned `tier` is always one of `{"small", "large", "feature"}` — it is never `None`, never an empty string, and never any other value.

**Validates: Requirements 2.3, 2.5**

### Property 2: Parser round-trip — well-formed output is lossless

*For any* tier in `{"small", "large", "feature"}` and any non-empty solution string `s`, if a well-formed analyzer output is constructed (containing `## Tier\n{tier}\n\n## Solution Plan\n{s}`), then `parse_analyzer_output` of that string returns `(tier, s)` exactly (modulo leading/trailing whitespace normalization on the tier line, which is intentional).

**Validates: Requirements 2.1, 2.2, 2.4**

### Property 3: Tier case-normalization — any valid tier casing round-trips to lowercase

*For any* case-variant of a valid tier string under the `## Tier` heading (e.g., `"SMALL"`, `"Large"`, `"FEATURE"`), `parse_analyzer_output` returns the lowercase canonical form (`"small"`, `"large"`, `"feature"` respectively).

**Validates: Requirement 2.2**

### Property 4: Invalid tier defaults to "large"

*For any* string `t` that is NOT a case-variant of `"small"`, `"large"`, or `"feature"`, a raw output with `## Tier\n{t}\n` causes `parse_analyzer_output` to return `("large", ...)` regardless of `t`'s content.

**Validates: Requirement 2.3**

### Property 5: Solution extraction is faithful

*For any* non-empty solution plan body string `s` (containing at least one non-whitespace character), `parse_analyzer_output` of a well-formed output containing `## Solution Plan\n{s}` returns `s` as the solution component (subject to section-end trimming, i.e., content before the next `## ` heading is captured).

**Validates: Requirement 2.4**

### Property 6: Analyzer tier drives pipeline selection

*For any* tier value `t` in `{"small", "large", "feature"}`, when `run_analyzer` returns `(t, solution)`, the `effective_target` computed by `create_revision` equals `_REVISION_TIER_TARGET_MAP[t]`.

**Validates: Requirement 3.2**

### Property 7: SSE event seq is strictly monotonically increasing

*For any* sequence of N events emitted by `run_analyzer` (agent_start, agent_complete, revision_analyzer_complete), the `seq` values assigned by `ScopedStore.append_event` are strictly increasing: `seq[i+1] > seq[i]` for all `i` in `0..N-2`.

**Validates: Requirements 9.3, 9.5**

### Property 8: revision_analyzer_complete payload matches analyzer output

*For any* tier `t` and solution `s` returned by `parse_analyzer_output`, the `revision_analyzer_complete` event emitted by `run_analyzer` has `data.tier == t` and `data.solution_preview == s[:200]`.

**Validates: Requirement 7.2**

### Property 9: Non-empty analyzer_solution causes === REVISION ANALYSIS === injection

*For any* non-empty string `s` assigned to `ectx.analyzer_solution`, the output of `_compose_context_message(ectx)` contains the substring `"=== REVISION ANALYSIS ===\n"` followed by `s`.

**Validates: Requirements 4.1, 10.3**

### Property 10: Empty analyzer_solution suppresses the block

*For any* `ExecutionContext` where `analyzer_solution == ""`, the output of `_compose_context_message(ectx)` does NOT contain the substring `"=== REVISION ANALYSIS ==="`.

**Validates: Requirements 4.3, 10.4**

---

## Error Handling

### Analyzer Failure Hierarchy

| Failure | Behavior | Log level |
|---------|----------|-----------|
| `parse_analyzer_output`: tier section absent | Default tier = `"large"`, log raw[:500] | WARNING |
| `parse_analyzer_output`: tier value unrecognized | Default tier = `"large"`, log raw[:500] | WARNING |
| `parse_analyzer_output`: solution section absent | solution = `""` | WARNING |
| `run_analyzer`: LLM call raises exception | Fall back to `_classify_revision_tier` | ERROR + exc_info |
| `run_analyzer`: both LLM and fallback raise | Default tier = `"large"`, solution = `""` | ERROR |
| `ectx.analyzer_solution` storage fails post-mint | Abort revision run with 500 | ERROR |
| AGENT.md file absent at server startup | Loader logs warning; `run_analyzer` falls back | WARNING (loader) |
| AgentSpecError on AGENT.md parse | Same fallback path as absent file | WARNING (loader) |

### INV-3 Safety

The `analyzer_solution` field defaults to `""`. On all 5 existing characterization golden runs:
- `run_analyzer` is never called (those runs are not prototype revisions with `target_artifact_type == "prototype_output"` going through the new path).
- `ectx.analyzer_solution` remains `""` throughout.
- `_compose_context_message` produces byte-identical output (the new `if ectx.analyzer_solution:` guard is False — no block appended).
- The `revision_analyzer_complete` event type is in `_DOCUMENTED_EVENT_TYPES` but never fired by the scripted harness, so the golden event sets are unaffected.

### SC-001 Compliance

- Zero literals matching `prototype_revision`, `prototype_large_revision`, or `prototype_feature_revision` inside `agents/execution_engine/`.
- The `ectx.analyzer_solution` field check in `_compose_context_message` is a generic truthiness check on a field name — no pipeline-type or agent-id guard.
- `run_analyzer` and `parse_analyzer_output` live entirely under `app/agents/` (app layer).

---

## Testing Strategy

### Dual Testing Approach

**Unit tests** (`backend/tests/unit/test_revision_analyzer.py`):
- `parse_analyzer_output` pure function (all properties below, plus concrete examples)
- `run_analyzer` with mocked LLM and mocked event queue
- Fallback chain coverage (analyzer fails, then fallback also fails)
- Edge cases: empty raw string, only whitespace tier, no solution section

**Integration tests** (`backend/tests/integration/test_revision_analyzer_integration.py`):
- `create_revision` endpoint with mocked `run_analyzer` — asserts events emitted in order
- `ectx.analyzer_solution` is set before first agent_start for the pipeline
- `agent_count = pipeline_agents + 1`
- Concierge path also invokes `run_analyzer`

**Characterization tests (existing, unmodified):**
- 5 golden snapshots remain byte-identical (INV-3)
- `revision_analyzer_complete` added to `_DOCUMENTED_EVENT_TYPES` — vocabulary guard passes

### Property-Based Testing

The feature's pure parser function (`parse_analyzer_output`) is an ideal target for property-based testing. It is a pure function with no I/O, a well-defined input space (raw strings), and universal invariants that hold across all inputs.

**Library:** [`hypothesis`](https://hypothesis.readthedocs.io/) (Python PBT library)

**Configuration:** minimum 100 iterations per property test (randomized input generation).

**Tag format:** `# Feature: prototype-revision-analyzer, Property {N}: {property_text}`

#### Test: Tier always in valid set (implements Property 1)

```python
# Feature: prototype-revision-analyzer, Property 1: tier always in valid set
@given(st.text())
@settings(max_examples=200)
def test_tier_always_valid(raw: str):
    tier, _ = parse_analyzer_output(raw)
    assert tier in {"small", "large", "feature"}
```

#### Test: Round-trip and case normalization (implements Properties 2 & 3)

```python
# Feature: prototype-revision-analyzer, Properties 2+3: round-trip and case normalization
@given(
    tier=st.sampled_from(["small", "large", "feature", "SMALL", "Large", "FEATURE"]),
    solution=st.text(min_size=1),
)
@settings(max_examples=200)
def test_roundtrip_wellformed_output(tier: str, solution: str):
    raw = f"## Tier\n{tier}\n\n## Solution Plan\n{solution}"
    parsed_tier, parsed_solution = parse_analyzer_output(raw)
    assert parsed_tier == tier.lower()
    assert parsed_solution.strip() == solution.strip()
```

#### Test: Invalid tier defaults to "large" (implements Property 4)

```python
# Feature: prototype-revision-analyzer, Property 4: invalid tier defaults to large
VALID_TIER_VARIANTS = {"small", "large", "feature", "SMALL", "LARGE", "FEATURE",
                        "Small", "Large", "Feature"}

@given(st.text().filter(lambda t: t.strip().lower() not in {"small", "large", "feature"}))
@settings(max_examples=200)
def test_invalid_tier_defaults_to_large(invalid_tier: str):
    raw = f"## Tier\n{invalid_tier}\n\n## Solution Plan\nsome plan"
    tier, _ = parse_analyzer_output(raw)
    assert tier == "large"
```

#### Test: Context message injection (implements Properties 9 & 10)

```python
# Feature: prototype-revision-analyzer, Properties 9+10: REVISION ANALYSIS block injection
@given(st.text(min_size=1))
@settings(max_examples=200)
def test_nonempty_solution_injects_block(solution: str):
    ectx = ExecutionContext(run_id="test", owner_id="u1")
    ectx.analyzer_solution = solution
    msg = _compose_context_message(ectx)
    assert "=== REVISION ANALYSIS ===" in msg

@given(st.nothing())  # always empty string
@settings(max_examples=1)
def test_empty_solution_suppresses_block():
    ectx = ExecutionContext(run_id="test", owner_id="u1")
    ectx.analyzer_solution = ""
    msg = _compose_context_message(ectx)
    assert "=== REVISION ANALYSIS ===" not in msg
```

### File Change Test Matrix

| Changed file | Test file | Test type |
|---|---|---|
| `backend/app/agents/revision_analyzer.py` | `tests/unit/test_revision_analyzer.py` | Unit + PBT |
| `backend/agents/execution_engine/context.py` | `tests/agents/test_characterization_*.py` | Characterization (INV-3 guard) |
| `backend/agents/execution_engine/engine.py` | `tests/unit/test_revision_analyzer.py` (via `_compose_context_message`) | PBT |
| `backend/app/api/run_commands.py` | `tests/integration/test_revision_analyzer_integration.py` | Integration |
| `backend/tests/agents/test_phase3_cutover_verify.py` | All characterization tests (import `_DOCUMENTED_EVENT_TYPES`) | Passive — widened vocabulary |
| AGENT.md files | `tests/unit/test_revision_analyzer.py` | Smoke (parse frontmatter) |

---

## File Changes Summary

| File | Change type | Description |
|------|-------------|-------------|
| `backend/agents/prompts/prototype-revision-analyzer/AGENT.md` | **CREATE** | New analyzer agent definition |
| `backend/app/agents/revision_analyzer.py` | **CREATE** | `parse_analyzer_output` + `run_analyzer` |
| `backend/agents/execution_engine/context.py` | **EDIT** | Add `analyzer_solution: str = ""` field |
| `backend/agents/execution_engine/engine.py` | **EDIT** | Add position-5 seam in `_compose_context_message` |
| `backend/app/api/run_commands.py` | **EDIT** | Replace `_classify_revision_tier` with `run_analyzer`; update `_mint_revision_row` agent_count; add Concierge path update |
| `backend/agents/prompts/prototype-revision-agent/AGENT.md` | **EDIT** | `order: 1` → `order: 2`; add REVISION ANALYSIS instruction |
| `backend/agents/prompts/prototype-revision-planner/AGENT.md` | **EDIT** | Add REVISION ANALYSIS instruction |
| `backend/agents/prompts/prototype-revision-feature-specify/AGENT.md` | **EDIT** | Add REVISION ANALYSIS instruction |
| `backend/tests/agents/test_phase3_cutover_verify.py` | **EDIT** | Add `"revision_analyzer_complete"` to `_DOCUMENTED_EVENT_TYPES` |
| `backend/tests/unit/test_revision_analyzer.py` | **CREATE** | Unit + PBT tests for parser and async orchestrator |
| `backend/tests/integration/test_revision_analyzer_integration.py` | **CREATE** | Integration tests for create_revision endpoint flow |
