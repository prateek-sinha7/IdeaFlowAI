# Status / Resume Log — Hardcoded Agents & Workflow Discovery

**Purpose:** chronological, resumable log of everything done on this investigation+fix. If
picking this back up in a new session, read this file first (bottom section = what's still open),
then pull in the referenced docs only as needed — don't re-derive anything already answered here.

**Companion docs in this folder:**
- `FINDINGS.md` — initial deep-dive analysis (root cause, register cross-refs)
- `INVENTORY.md` — flat table of every hardcoded location found
- `PLAN.md` — the fix plan written before implementation
- `REPORT.md` — consolidated final report (investigation → decision → fix → verification)

**Companion docs elsewhere:**
- `.planning/ISSUES-REGISTER.md` — ISS-035 (status: **FIXED**)
- `.planning/FIX-REGISTER.md` — FIX-051 (detailed entry)
- `.planning/quick/260720-9pt-agent-workflow-discovery-single-source-of-truth/` — quick-task PLAN/VERIFICATION/SUMMARY

---

## Timeline

### 2026-07-20, session start — Investigation kicked off
User asked to verify the backend isn't using hardcoded agents in multiple places, and to use
`/velocity-analyze` first, reading all registers to the end, to determine whether hardcoding was
intentional or organic. Chose the `velocity-analyze` → `velocity-fix` workflow (not the full GSD
roadmap-phase machinery) after a clarifying question.

Ran `/velocity-analyze` as a background research agent (register files are 600KB+, needed to be
read in full per user instruction — corrected the agent mid-run when it tried to grep instead of
full-read the registers). Delivered initial findings; written to `FINDINGS.md` + `INVENTORY.md`
by the orchestrator (the subagent's Write tool was blocked from producing report files, so its
text output was transcribed to disk directly).

**Initial (later-corrected) conclusion:** `PIPELINE_AGENTS` in `agents/registry.py` was assumed to
be a *locked, intentional* decision, mostly bypassed at runtime by a dynamic scan.

### Same session — User pushback + corrected investigation
User observed in practice that newly-added agents/workflows were **not** being discovered, and
asked for a corrected root-cause + fix plan (backend only, minimal footprint, tests to prevent
drift), plus the decision recorded in the register.

Direct code investigation (not the "locked decision" framing) revealed the real bug: while
`get_pipeline_agents()` was already 100% dynamic, three *other* consumers
(`get_all_agents_flat()`, `allowed_custom_agent_ids()`, `app/api/workflows.py`'s
`_KNOWN_WORKFLOW_IDS`/`list_workflows()`) read the hand-maintained `PIPELINE_AGENTS` dict
directly. **Live proof found:** 8 fully-formed `spec_kit` agents on disk (`analyze-agent`,
`deep-planner`, `clarify-agent`, `constitution-agent`, `plan-agent`, `research-agent`,
`specify-agent`, `tasks-agent`) — correct frontmatter, zero `PIPELINE_AGENTS` entries, invisible
to the agent library/allow-list/`/api/workflows`.

- Added **ISS-035** to `.planning/ISSUES-REGISTER.md` (Status: OPEN at the time).
- Wrote `PLAN.md` (this folder) — the 2-file root fix (`registry.py` + `workflows.py`), tests to
  add, explicit out-of-scope list.
- User asked one clarifying question about a suspected missing table column in the ISS-035 row —
  investigated, confirmed the row was actually correctly formed (6/6 columns matching the
  register's own convention); no register fix needed.

### Same session — Implementation
User said "yes implement." Followed the `velocity-fix` skill's Steps 4–8 (quick-task folder,
apply fix, verify, register, commit convention):

- Created quick-task folder `.planning/quick/260720-9pt-agent-workflow-discovery-single-source-of-truth/`.
- **`backend/agents/registry.py`** — replaced the ~150-line literal `PIPELINE_AGENTS` dict with
  `_discover_pipeline_agents()`, computed once at import time via `list_agent_ids()` per
  `SUPPORTED_PIPELINE_TYPES` value. Kept `"ppt"` as an explicit one-line alias to `"od_ppt"`'s
  agents (closes WR-01's symptom). Initially also had a "reference-only" dead copy of the old
  dict left in as a comment block — caught during self-review and deleted (no dead code).
- **`backend/app/api/workflows.py`** — replaced `_KNOWN_WORKFLOW_IDS = frozenset(PIPELINE_AGENTS.keys())`
  with `_discover_manifest_ids()`: the intersection of `SUPPORTED_PIPELINE_TYPES` and directories
  under `agents/workflows/` that actually have a `workflow.yaml`. Prevents `spec_kit` (agents, no
  manifest) and the `sample_*` test-fixture manifest dirs (ISS-015) from leaking into the public
  catalog.
- **Test-suite ripple** discovered during verification (several existing tests were implicitly
  coupled to the old dict's exact 15-key shape):
  - `test_id_alias_resolver.py`'s alias-identity test caught that `"od_prototype"` (a pure
    `_OD_ALIAS_BASE` id-alias, never a real `pipeline_type`) had leaked into the new
    `PIPELINE_AGENTS` — fixed by moving `_OD_ALIAS_BASE` earlier in `registry.py` and excluding
    its keys from the scan.
  - `test_manifest_coverage.py`, `test_manifest_parity.py`, `test_compiled_plan_runs.py`,
    `test_id_alias_resolver.py` — re-scoped parametrize lists from `sorted(PIPELINE_AGENTS)` to a
    locally-computed manifest-backed id set (their real invariant all along).
  - `test_pipeline_workflows.py`, `test_execution_engine.py` — added an explicit, documented
    `spec_kit` carve-out: now that `spec_kit`'s real agents are visible, DAG validation correctly
    surfaces that its `produces`/`consumes` contracts are unfinished (`clarify-agent` consumes
    `'brief'`, nothing produces it) — a genuine pre-existing gap, not a regression.
  - New `backend/tests/agents/test_registry_discovery.py` — the actual drift-prevention pins
    (no orphaned agent, flat-list completeness, pre-fix-list parity, ppt/od_ppt alias
    correctness).
  - `test_workflows_api.py` — re-scoped 3 assertions + added `TestKnownWorkflowIdsDiscovery`
    (matches-disk, spec_kit-not-exposed, sample-fixtures-not-exposed, every-known-id-compiles).
- **`backend/CLAUDE.md`** — removed the now-obsolete "add to `PIPELINE_AGENTS`" manual steps from
  "Adding an Agent" / "Adding a Pipeline".
- **Registers updated:** `ISS-035` → **FIXED** (FIX-051); `FIX-REGISTER.md` gained the FIX-051
  summary row + detailed entry.
- Wrote quick-task `PLAN.md` / `VERIFICATION.md` / `SUMMARY.md`.

**Verification (targeted):** 236 passed across every file touched or exercised by the fix. 28
failures, all individually traced to 4 pre-existing, unrelated causes (confirmed identical on the
unmodified base branch via `git stash`) — none introduced by this fix.

### Same session — Follow-up Q&A
User asked why the `ppt`→`od_ppt` alias patch is needed and why not fix it at the schema root.
Explained: the 3 shared `od-ppt-*` agents can only declare one `pipeline_type` value
(`od_ppt`) even though two manifests/products (`ppt`, `od_ppt`) run them — a genuine, separately
tracked limitation (WR-01, since Phase 4). A real fix means extending `AgentSpec.pipeline_type` to
support multi-membership — real schema/loader/resolver blast radius, out of scope for this
SRP-focused fix, and not requested. The one-line alias replaces a fragile hand-duplicated list
with an explicit, undrifting one — closes the symptom, not the schema limitation.

### Same session — Full-suite test pass + REPORT.md
User asked to "test everything" and produce a `REPORT.md` + summary.

- Ran the full backend suite (`pytest tests/`, 2293 tests). First attempt hit a real environment
  wall: no local Postgres running in this sandbox — `app/agents/checkpointer.py`'s
  `AsyncConnectionPool` retries for 30s per DB-touching test before failing, making a full run
  impractically slow (killed after ~6 min, <6% complete).
  - **Recovered via git-stash mishap:** an early `git stash` (to compare against the base branch)
    got interrupted by a command timeout mid-chain, leaving the fix stashed and the working tree
    reverted. Caught via the harness's file-change reminders, restored with
    `git stash pop stash@{0}` — verified restored correctly before continuing. (Lesson: avoid
    `git stash` for baseline diffs when chained with commands that might time out; read `git
    show HEAD:path` or reason from source instead.)
  - **Fix for the DB-stall problem:** `checkpointer.py` only opens a Postgres pool when
    `DATABASE_URL` starts with `postgresql://` — overriding it to `sqlite:///:memory:` for the
    test run makes `get_checkpointer()` fall back to its own existing `InMemorySaver` path
    immediately (documented behavior, not a hack). Full suite then completed in ~6.5 min.
- **Result:** 2156 passed, 99 failed, 38 skipped. Every failing *file* (not just the aggregate)
  was individually inspected — all 99 failures traced to 6 pre-existing/environmental categories,
  zero attributable to `registry.py`/`workflows.py`:
  1. Pre-existing `allowed_custom_agent_ids` cross-pipeline union (design vs. narrow test
     expectation) — 18 failures across 3 files.
  2. Stale `clarify.defaults` snapshots (4-item hardcoded vs. real 8-item manifests) — 15
     failures across 2 files.
  3. Stale FE-mirroring / hardcoded prototype agent expectations (missing `prototype-analyze`,
     pre-dates this fix) — 7 failures across 3 files.
  4. Manifest/prompt content drift (`display_name`, `user_launchable`, `max_tokens`, guardrail
     text) — 10 failures across 5 files.
  5. Test-fixture/engine mismatch (`'_Ctx' object has no attribute 'gate_agent_ids'`) — 2
     failures, 1 file.
  6. DB/checkpointer-dependent (persistence, migrations, HITL resume/redo, live harness) — 43
     failures across 14 files; needs a real Postgres, none available in this sandbox; some may
     specifically be an `InMemorySaver`-vs-`AsyncPostgresSaver` resume-timing artifact of the
     diagnostic `DATABASE_URL` override, not a code defect.
- Wrote `REPORT.md` (this folder) consolidating the full arc: investigation → decision → fix →
  both rounds of verification → known gaps → follow-ups.

### 2026-07-20 15:57 — Commit 1
`50290ead` — `fix(registry): derive PIPELINE_AGENTS from a folder scan, not a hand-maintained dict`
(17 files: the 2-file root fix, 9 test files, `backend/CLAUDE.md`, both registers, the
investigation docs, the quick-task folder). **Not pushed** (explicit instruction).

### Same session — Housekeeping
User asked about `.vscode/PythonImportHelper-v2-Completion.json` (an untracked file that showed
up during `git status`). Explained: a VS Code "Python Import Helper" extension's local autocomplete
index/cache, 3.2 MB, regenerated automatically — not part of this work, not previously
`.gitignore`d. User asked to ignore + commit it.

### 2026-07-20 16:04 — Commit 2
`c9609b8d` — `chore: ignore VS Code Python Import Helper cache file` (adds
`.vscode/PythonImportHelper-v2-Completion.json` to `.gitignore`). **Not pushed.**

### Same session — This file
User asked for this status/history log so a future session can resume without re-deriving
context.

---

## Where things stand right now

- **ISS-035 / FIX-051: DONE.** Root fix implemented, tested (236 targeted + full-suite sanity
  pass), registers updated, committed locally (2 commits, not pushed).
- Working tree is clean (`git status` shows nothing pending) as of this file's writing.
- Current branch: `feature/onboarding-and-diagrams`. Commits `50290ead` and `c9609b8d` sit ahead
  of the remote (not pushed) — confirm this is still true with `git status` / `git log
  origin/feature/onboarding-and-diagrams..HEAD` before assuming it's unchanged.

## Open items (not started, your call whether/when)

1. **Frontend `compatible_agents` stale IDs** (`frontend/src/data/hooks.ts` /
   `skills.ts`) — real bug found during the original investigation (`FINDINGS.md` §6), explicitly
   deferred to keep this fix backend-only. Needs: a validation test (or a source-from-backend
   change) so stale IDs like the ones found can't silently ship again.
2. **`spec_kit` pipeline is unfinished** — 8 real agents, no `workflow.yaml` manifest, and
   `clarify-agent`'s `consumes: [brief]` has no upstream producer. Decide: finish it (author a
   manifest + wire the contract), or leave/remove it. Currently correctly *invisible* as a
   launchable workflow (by design, per this fix), but the underlying incompleteness is
   unresolved.
3. **WR-01 schema-level fix** (optional, larger) — properly supporting one agent belonging to
   multiple pipelines would mean extending `AgentSpec.pipeline_type` (loader.py dataclass +
   validation + every consumer that treats it as a single string, e.g. `opendesign.py`'s
   injection gating). Only the *symptom* was closed in this fix; the schema limitation is
   unchanged, on purpose, per explicit scope constraint.
4. **28 (targeted) / 99 (full-suite) pre-existing test failures** — none caused by this fix, but
   also none fixed by it. Still failing on this branch. No one has picked these up as a cleanup
   task. See `REPORT.md` §5 / §6 for the categorized breakdown if this is ever prioritized.
5. **Push / PR** — not done; two local commits are waiting whenever you're ready.
