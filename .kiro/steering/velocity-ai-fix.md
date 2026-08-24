---
inclusion: manual
---

# /velocity-ai-fix — VelocityAI Deep Analysis + Fix Protocol

You have been invoked to investigate, diagnose, and fix an issue in the VelocityAI / Flowin codebase.

**STOP. The architecture must remain as designed. No shortcuts or hacks are allowed.**

> You MUST complete every step in order. Do not skip any step.
>
> **Mandatory post-fix gate:** After applying any fix you MUST write tests (unit + integration
> where applicable), run them to confirm every new test passes, and only then register the fix.
> A fix is not done until the tests are green. See Steps 8a–8d.

---

## Step 0 — Local environment facts (CI and this machine are NOT the same)

Every command in this document was written for **CI**, which provisions a synced
environment (`astral-sh/setup-uv` + `requirements.txt`, `ci.yml:95-121`). A local
developer machine has no such environment, so the CI-canonical `uv run --no-sync`
form does **not** work here. Use the local column.

| Task | CI (`ci.yml`) | This machine (local) |
|---|---|---|
| Run pytest | `uv run --no-sync pytest tests/ -v` | `cd backend && python3.11 -m pytest ...` |
| Import-boundary check | `uv run --no-sync lint-imports` | `cd backend && /opt/homebrew/bin/lint-imports` |

Two traps that cost real time:

- **`uv run --no-sync` does not fail loudly here — it fails silently.** There is no
  `backend/.venv`, so `uv` *creates* one (an empty CPython 3.12 environment), skips the
  dependency install because of `--no-sync`, and only then dies on the first import. You
  are left with a stray `backend/.venv` that shadows the working interpreter. The local
  runtime is **python3.11** — the running backend is python3.11 and `python3.11 -m pytest`
  resolves pytest 8.3.4. (`backend/pyproject.toml` declares `requires-python = ">=3.12"`;
  that declaration does not match the local runtime. Do not "fix" it as part of an
  unrelated change.)
- **`lint-imports` must be run from `backend/`.** Its configuration lives in
  `backend/pyproject.toml`. Run from the repo root it prints *"Could not read any
  configuration"* and exits — which reads like a pass if you are not looking closely.

**The `dev.db` decoy.** `backend/app/core/config.py:322` defaults `DATABASE_URL` to
`sqlite:///./dev.db` — a path **relative to the process working directory**. The real
database is `backend/dev.db`. A query run from the repo root therefore opens a
*different, empty* database and returns zero rows **with no error**. Always query
`backend/dev.db` by explicit path.

**Do not trust any measured number written into this document.** Counts of passing
tests, kept contracts, and migration heads drift, and a stale number asserted as a
requirement is worse than no number. Every such figure below has been replaced with the
command that produces the current value. Baseline by re-measuring at the pre-change
commit, and record the SHA you compared against.

---

## Step 1 — Load Context: Always-On Steering

These are always loaded — confirm you have them:

- **`invariants.md`** — INV-1..INV-13, locked decisions, transport contract, "do not resurrect" table.
- **`project-index.md`** — key source files, migration chain, glossary.

Then load the **domain-specific steering file** for the area you are fixing:

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

## Step 2 — Prime the Knowledge Store

Read these four files in order (~12.5K tokens total):

```
.knowledge/surface/ARCHITECTURE.md   ← milestone, phase, enforced boundaries, ADRs in force
.knowledge/INVARIANTS.md              ← project-wide constraints
.knowledge/surface/RULES.md           ← decisions in force
.knowledge/surface/INDEX.md           ← one line per fix / issue / phase
```

They are inlined below for immediate access — no separate file read needed:

### ARCHITECTURE.md (current milestone, enforced import boundaries, component map, active ADRs)

#[[file:.knowledge/surface/ARCHITECTURE.md]]

---

### RULES.md (decisions in force — every item is a constraint, not a preference)

#[[file:.knowledge/surface/RULES.md]]

---

Check freshness:
```bash
# From repo root
python3 scripts/knowledge/check.py
```

**Do NOT load `.planning/FIX-REGISTER.md`, `ISSUES-REGISTER.md`, or `IMPLEMENTATION-REGISTER.md` in full.**

---

## Step 3 — Query the Knowledge Store

```bash
# Search by symptom — the primary lookup before diagnosing anything
# (run from repo root — scripts/knowledge/ lives at repo root, not under backend/)
python3 scripts/knowledge/ctx.py "<symptom words>"

# Find every rule and prior fix touching the file you are about to change
python3 scripts/knowledge/ctx.py --for <file path>

# Active decisions for an area
python3 scripts/knowledge/ctx.py --rules <area>

# Open a specific card in full
python3 scripts/knowledge/ctx.py --show FIX-NNN
```

- If a row in `INDEX.md` matches your symptom, use `--show FIX-NNN` for the full card.
- The **next sequential Fix ID** is in `INDEX.md` header (e.g. `532 cards · fixes 168 ...`). Add 1 to the highest FIX-NNN.
- **FIX-039** (`agent_start` accumulator reset) — verify every fix does not regress it.

If `ctx.py` cannot answer, use targeted grep:
```bash
grep_search query="<symptom>" includePattern="**/.planning/FIX-REGISTER.md"
```

Check existing test coverage to avoid duplication:
```bash
grep_search query="FIX-NNN" includePattern="**/.planning/FIX-TEST-REGISTER.md"
```

---

## Step 4 — Deep Codebase Investigation

**Investigation phase only — do NOT touch any code yet.**

### Key architectural entry points

| Area | Key files | Notes |
|---|---|---|
| Pipeline execution | `backend/agents/execution_engine/engine.py` | |
| SSE down-channel | `backend/app/api/run_stream.py` | Replaces deleted `websocket.py` |
| REST up-channel | `backend/app/api/run_commands.py` | Gate/cancel/answers/messages/revisions/resume |
| Shared run infra | `backend/app/api/run_engine.py` | Relocated from `websocket.py` |
| Handoff WebSocket | `backend/app/api/websocket_handoff.py` | Only remaining WS endpoint |
| Capability registry | `backend/agents/capabilities/registry.py` | |
| Model / Bedrock config | `backend/app/core/config.py`, `backend/app/agents/model_factory.py` | |
| Frontend SSE hook | `frontend/src/hooks/useRunStream.ts` | Replaces deleted `useWebSocket.ts` |
| Frontend connection provider | `frontend/src/providers/RunConnectionProvider.tsx` | |
| Frontend pipeline state | `frontend/src/hooks/useWorkflow.ts` | |
| Frontend run screen | `frontend/src/app/dashboard/page.tsx`, `frontend/src/components/layout/DashboardLayout.tsx` | |
| Auth / entitlements | `backend/app/api/auth.py`, `backend/app/core/entitlements.py` | |
| DB / migrations | `backend/alembic/versions/`, `backend/app/models/` | Head: 0037 — verify with `alembic heads` (must be ONE) |
| Scoped store / IDOR | `backend/agents/authz.py` | |
| Concierge | `backend/app/agents/chat/concierge.py` | |
| Gate pendency | `backend/agents/capabilities/gate_pendency.py` | Resume gate re-entry |

> ⚠️ **Deleted files — do NOT read, reference, or recreate:**
> `websocket.py` · `useWebSocket.ts` · `PrototypePipelineView.tsx` · `ReviewGatePanel.tsx` · `QuestionnairePanel.tsx` · `AgentProgressPanel.tsx` · `WaveTreePanel.tsx`

---

## Step 5 — Root Cause Analysis

Write this before touching any code:

```
ISSUE TYPE: [backend error / SSE/transport / frontend visual / resume / other]

ROOT CAUSE:
- What is broken and exactly why
- File and line where failure originates
- Exact sequence of events

EVIDENCE:
- File: <path> Line: <N> — <code / log>
- Trace: entry → A → B → [FAILURE] → outcome

PRIOR FIXES CHECKED:
- ctx.py "<symptom>" returned: [FIX-NNN, FIX-NNN, ...]
- FIX-039 status: confirmed not regressed

CONSTRAINTS:
- INV-1: [not affected / explain]
- INV-3: [not affected / goldens will stay clean]
- INV-12: [what existing code to reuse]
- SC-001: [not affected / explain if engine edit needed]
- Transport: [SSE + REST only — no WS run frames]
```

---

## Step 6 — Fix Plan

State what will change **before writing any code**:

```
FILES TO CHANGE:
- <path> — <what and why>

NOT CHANGING:
- <deliberately untouched files>

DELETED CODE CHECK:
- <confirmed nothing from invariants.md "What NOT to Resurrect" is being revived>

LOCKED DECISIONS RESPECTED:
- <cite from loaded steering file> — <how the fix honours it>
```

---

## Step 7 — Apply the Fix

1. One change at a time — surgical, only what the root cause requires
2. Match existing patterns — follow the surrounding code style
3. No new abstractions unless the root cause specifically requires them
4. No collateral cleanup — do not refactor unrelated code
5. Transport rule — any new run-event code uses `run_stream.py` + `run_commands.py`, never `/ws/chat`

---

## Step 8 — Verify the Fix

### 8a — Code review

- Read the changed files — confirm the edit looks right in context
- Trace the fix — mentally walk the execution path
- INV-3 check: `git status --porcelain backend/tests/agents/characterization/golden/` → empty
- Lint / import-boundary check: `cd backend && /opt/homebrew/bin/lint-imports` (if `agents/` or `app/` changed) → the kept/broken counts must be **IDENTICAL to the pre-change commit**, not any fixed number. There is a known pre-existing broken contract (`agents.capabilities.strategies.task_loop` → `agents.execution_engine.od_context` → `app.services.od_loader`); inheriting it is not your regression, adding to it is.
- **FIX-039 check**: if `useWorkflow.ts` was touched, confirm `agent_start` still resets all accumulators
- Backend restart needed? Restart if backend files changed.

---

### 8b — Write tests (mandatory)

**Do not skip this step. A fix without tests is not done.**

Write tests that:

1. **Fail before the fix** (or confirm no pre-existing test covers the defect)
2. **Pass after the fix** (the primary regression guard)
3. **Assert the safety boundary** — verify adjacent behaviour still works, not just the happy path

#### Where to put tests

| Fix area | Test location | Test runner |
|---|---|---|
| Python backend (`app/api/`, `agents/`, etc.) | `backend/tests/unit/` or `backend/tests/agents/` | `python3.11 -m pytest` (CI: `uv run --no-sync pytest`) |
| Python cross-layer (API + engine + DB) | `backend/tests/integration/` | `python3.11 -m pytest` (CI: `uv run --no-sync pytest`) |
| Frontend React/TS component | `frontend/src/components/<Comp>/<Comp>.test.tsx` | `vitest` |
| Frontend hook | `frontend/src/hooks/<hook>.test.ts` | `vitest` |
| Frontend page-level | `frontend/src/app/**/*.test.tsx` | `vitest` |
| End-to-end (mocked) | `frontend/e2e/tests/<suite>.spec.ts` | Playwright `--project=mocked` |
| End-to-end (live) | `frontend/e2e/tests/<suite>.live.spec.ts` | Playwright `--project=live` |

#### What to write per fix type

**Backend Python fix → write pytest unit tests:**

```python
# backend/tests/unit/test_<module>_<fix_id>.py

import pytest

class TestFix<NNN><ShortDescription>:
    """Unit tests for FIX-<NNN>: <one-line description>."""

    def test_fail_before_fix_description(self):
        """Assert the defect reproduces (or existed) — documents the regression baseline."""
        ...

    def test_pass_after_fix_happy_path(self):
        """Assert the fix works for the primary reported case."""
        ...

    def test_safety_boundary_adjacent_behaviour(self):
        """Assert the adjacent / prior behaviour is NOT regressed."""
        ...
```

**Integration test** (when the fix spans multiple layers, e.g. API + engine or API + DB):

```python
# backend/tests/integration/test_<area>_<fix_id>.py

@pytest.mark.integration
class TestFix<NNN>Integration:
    """Integration tests covering the full call chain for FIX-<NNN>."""

    async def test_end_to_end_<scenario>(self, ...):
        """Walk the full path: HTTP request → engine → DB → response."""
        ...
```

**Frontend TypeScript/React fix → write Jest/Vitest tests:**

```typescript
// frontend/src/components/<Component>/<Component>.test.tsx
// OR frontend/src/hooks/<hook>.test.ts

describe('FIX-<NNN>: <short description>', () => {
  it('should fail before fix — <describes the defect baseline>', () => {
    // Set up the pre-fix condition and assert the broken behaviour
  });

  it('should pass after fix — <describes the corrected behaviour>', () => {
    // Assert the fixed behaviour
  });

  it('should not regress — <adjacent behaviour still works>', () => {
    // Assert the safety boundary
  });
});
```

#### Naming conventions

- Unit test file: `test_<module>_fix<NNN>.py` (backend) or `<Component>.fix<NNN>.test.tsx` (frontend)
- Integration test file: `test_<area>_integration_fix<NNN>.py`
- Each `it()`/`test()` block must contain the FIX-NNN id in its description
- Mock external dependencies (Bedrock, DB, SSE stream) — tests must run offline

#### Coverage requirements

Every test suite for a fix must include at minimum:

| # | Category | Description |
|---|---|---|
| 1 | **Regression baseline** | The defect existed — fail-before or describe what was untested |
| 2 | **Happy path** | The primary reported case now works |
| 3 | **Edge case** | At least one boundary or error input |
| 4 | **Safety boundary** | The adjacent/prior behaviour is not broken |

---

### 8c — Run the tests

**Backend** (local form — see Step 0; CI uses `uv run --no-sync` from `backend/`, matching `ci.yml`):

```bash
# Run only the new fix tests first
cd backend && python3.11 -m pytest tests/unit/test_<module>_fix<NNN>.py -v

# Then run the full affected module's test suite to confirm no regression
cd backend && python3.11 -m pytest tests/unit/test_<module>.py -v

# If integration tests were written
cd backend && python3.11 -m pytest tests/integration/test_<area>_fix<NNN>.py -v

# INV-3: characterization goldens (all 5 named explicitly). Compare failing ids against
# the pre-change commit — some are red pre-existing; a red golden is not automatically
# your regression, and a green run is not the bar.
cd backend && python3.11 -m pytest \
  tests/agents/test_characterization_prototype.py \
  tests/agents/test_characterization_od_prototype.py \
  tests/agents/test_characterization_prototype_revision.py \
  tests/agents/test_characterization_od_ppt.py \
  tests/agents/test_characterization_app_builder.py -v
```

> **Do not run the whole suite locally.** `pytest tests/ -v` HANGS on this machine — parts
> of it are gated on Chromium, Bedrock credentials and Postgres, and they block rather
> than skip. CI runs the full suite; locally, always use targeted selections.
>
> **Do not use `uv run --no-sync` locally.** There is no `backend/.venv`, so it silently
> creates an empty CPython 3.12 environment, skips the dependency install, and fails on
> the first import — leaving a stray venv behind. See Step 0.

**Frontend** (the project uses **vitest** exclusively — there is no Jest; `package.json`
`"test": "vitest --run"`):

```bash
# Run all frontend unit tests (vitest picks up src/**/*.{test,spec}.{ts,tsx})
cd frontend && npm test
# equivalent: cd frontend && npx vitest --run

# Run only the tests for a specific file
cd frontend && npx vitest --run src/components/<Component>/<Component>.test.tsx

# Run tests matching a keyword (e.g. a fix id or component name)
cd frontend && npx vitest --run --reporter=verbose <keyword>

# Run tests for a whole directory
cd frontend && npx vitest --run src/hooks/
```

**End-to-end / Playwright** (only when unit tests are insufficient; testDir is `e2e/tests/`):

```bash
# Mocked suite — no backend needed, fast, CI-safe
cd frontend && npm run e2e
# equivalent: npx playwright test --project=mocked

# Live suite — requires a running backend. Locally that is :8010, NOT :8002.
# Confirm before running: lsof -nP -iTCP:8010 -sTCP:LISTEN
cd frontend && npm run e2e:live
# equivalent: npx playwright test --project=live
```

**Import-linter** (run after any change to `agents/` or `app/`):

```bash
# Must report the SAME kept/broken counts as the pre-change commit — there is no fixed
# expected number, and at least one contract is known-broken pre-existing. Must be run
# from backend/ (the config lives in backend/pyproject.toml); from the repo root it
# prints "Could not read any configuration" and exits, which looks like a pass.
cd backend && /opt/homebrew/bin/lint-imports
```

**All tests must be GREEN before proceeding to Step 9. If any test fails:**

1. Diagnose — do not increment the patch ad hoc
2. Fix the root cause, not the test assertion
3. Re-run until clean
4. If a test exposes a DIFFERENT defect, open a new issue for it rather than bundling it into this fix

---

### 8d — Test coverage summary

After all tests pass, write this block (used verbatim in the fix card):

```
TEST COVERAGE — FIX-<NNN>
Unit tests:        <N> tests in backend/tests/unit/test_<module>_fix<NNN>.py  → ALL GREEN
Integration tests: <N> tests in backend/tests/integration/...                 → ALL GREEN  (or N/A)
Frontend tests:    <N> tests in frontend/src/.../<Component>.test.tsx          → ALL GREEN (or N/A)
Goldens:           cd backend && python3.11 -m pytest tests/agents/test_characterization_*.py
                   → <N> failed / <N> passed — IDENTICAL failing ids to pre-change commit <sha> (INV-3 ✅)
lint-imports:      cd backend && /opt/homebrew/bin/lint-imports
                   → <N> kept / <N> broken — IDENTICAL to <sha>
Regression guards:
  - <test name>: <what it proves>
  - <test name>: <what it proves>
```

---

## Step 9 — Register the Fix

### 9a — Write the card (replaces manual archive-file append)

The fix entry must already be in `FIX-REGISTER.md`'s summary table. Include the test
coverage summary block from Step 8d verbatim in the card body. Then:

```bash
# All three scripts live at repo root scripts/knowledge/ — run from repo root
python3 scripts/knowledge/extract.py fixes --only FIX-NNN
python3 scripts/knowledge/build_index.py
python3 scripts/knowledge/check.py
```

The card is now in `.knowledge/cards/FIX-NNN.md` and searchable via `ctx.py`.

### 9b — Add a summary row to FIX-REGISTER.md

Append to the `## Fix Log` table only (no detailed entry needed — the card IS the detailed entry):

```
| FIX-<NNN> | YYYY-MM-DD | <description> | <root cause> | `<files>` | <Phase N> | INV-1/3/12/SC-001 ✅ | Done |
```

The row must also include the test count, e.g. `tests: 4 unit + 2 integration ✅`.

### 9c — Update the next Fix ID

Check the current highest ID in `.knowledge/surface/INDEX.md` (the `## Fixes` section lists them newest-first). The next ID = highest shown + 1.

> **Note:** The detailed `### FIX-NNN` prose entry used to go into `FIX-REGISTER.md` or a fix-archive file. It now lives in the card (`.knowledge/cards/FIX-NNN.md`) and is loaded on demand via `ctx.py --show FIX-NNN`. The monolith grows by one summary row only.

### 9d — Final gate checklist

Before closing the fix, confirm every item is ticked:

- [ ] Root cause correctly identified and fixed
- [ ] Fix is surgical — no collateral refactoring
- [ ] Invariants respected (INV-1 / INV-3 / INV-12 / SC-001)
- [ ] **All new unit tests GREEN**
- [ ] **All new integration tests GREEN** (or N/A with justification)
- [ ] **All new frontend tests GREEN** (or N/A with justification)
- [ ] **Characterization goldens unchanged** (`git status` clean on `golden/`)
- [ ] Test coverage block written in fix card (Step 8d)
- [ ] FIX-REGISTER.md row appended with test count
- [ ] `ctx.py --show FIX-NNN` resolves and returns the card
- [ ] `python3 scripts/knowledge/check.py` exits 0 or 1 (not 2)

---

## Hard Constraints

**Architecture invariants (full list in `invariants.md` and `.knowledge/INVARIANTS.md`):**
- **INV-1** — kernel has NO `if pipeline_type ==` / `if spec.id ==` branches
- **INV-3** — 5 characterization golden snapshots remain byte-identical
- **INV-12** — move-don't-copy, no dual implementations
- **INV-13** — every agent on LangChain `deepagents`, never hand-rolled
- **SC-001** — new workflow = manifest + AGENT.md only, zero engine edits

**Transport:** SSE + REST is the sole run transport. `/ws/chat` is DELETED. `/ws/handoff` STAYS.

**Migrations:** Additive only. Read the current head — do not trust a number written here:
`ls backend/alembic/versions/ | sort | tail -1`. Every new table: `owner_id` + `workspace_id` NOT NULL.

**Security:** Owner-scoping key = `WorkflowRun.user_id` (NOT nullable `owner_id`). Cross-owner → 404, never 403.

---

## Reference Shortcuts

| Need | Command |
|---|---|
| Prior fixes by symptom | `python3 scripts/knowledge/ctx.py "<symptom>"` |
| Rules for a file | `python3 scripts/knowledge/ctx.py --for <path>` |
| Full card detail | `python3 scripts/knowledge/ctx.py --show FIX-NNN` |
| Current milestone/phase | `.knowledge/surface/ARCHITECTURE.md` |
| All decisions in force | `.knowledge/surface/RULES.md` |
| Full fix index | `.knowledge/surface/INDEX.md` |
| Next FIX-ID / ISS-ID / TEST-ID | **Never** "highest in one source + 1" — that rule re-issued a live id and forced a renumber. Take the max across **four** sources (register, `.knowledge` cards, `git log --all` commit messages, open branches) and add 1. Full procedure: `.claude/skills/velocity-ai-bookkeeping/SKILL.md` Step 1 |
| Run backend tests | `cd backend && python3.11 -m pytest tests/ -v` (CI: `uv run --no-sync`) |
| Run frontend tests | `cd frontend && npm test` (= `vitest --run`) |
| Run a specific frontend file | `cd frontend && npx vitest --run src/path/to/file.test.tsx` |
| Run Playwright mocked suite | `cd frontend && npm run e2e` |
| Import-boundary check | `cd backend && /opt/homebrew/bin/lint-imports` (counts must match the pre-change commit; must be run from `backend/`) |
| Golden freshness | `git status --porcelain backend/tests/agents/characterization/golden/` |
| Rebuild knowledge index | `python3 scripts/knowledge/build_index.py` |
| Check knowledge store | `python3 scripts/knowledge/check.py` |
| Concurrent run / run-binding bugs | `python3 scripts/knowledge/ctx.py "concurrent run"` |
| Chat / revision / narrator bugs | `python3 scripts/knowledge/ctx.py "narrator"` |
| FIX-039 (CRITICAL — agent accumulator) | `python3 scripts/knowledge/ctx.py --show FIX-039` |
| Resume engine rules | `#backend-engine.md` + `python3 scripts/knowledge/ctx.py --type phase "resume"` |
| Deleted kernel leaks (L1–L13) | `python3 scripts/knowledge/ctx.py --show PHASE-07` |
| Prompt contracts | `python3 scripts/knowledge/ctx.py --show PHASE-15` |
