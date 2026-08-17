# 260812-12t — BASELINE (measured, not recalled)

Measured at **HEAD `d62bfe4d942b702afb71ed4234b4ff976746f6cb`**, branch
`bugfix/spec-revision-context-loss`, before any edit.

## Working tree at start

NOT clean. `git status --porcelain` showed **18 `.knowledge/` paths only** — 9 modified
(`cards/ISS-066.md` + the 8 regenerated `surface/*` files) and 9 untracked
(`cards/ISS-054..061.md`, `cards/ISS-069.md`). Zero `backend/` or `frontend/` changes.

These are **another session's in-flight issue-filing**, not this task's. They are recorded
here so nothing in this task can later be mistaken for them, and so no `git stash` is ever
issued (a stash here would sweep that work — the known executor hazard).

## Characterization goldens — 5 failed / 5 passed

```
cd backend && python3.11 -m pytest \
  tests/agents/test_characterization_prototype.py \
  tests/agents/test_characterization_od_prototype.py \
  tests/agents/test_characterization_od_ppt.py \
  tests/agents/test_characterization_app_builder.py \
  tests/agents/test_characterization_prototype_revision.py -q
```

```
FAILED tests/agents/test_characterization_prototype.py::test_prototype_event_snapshot
FAILED tests/agents/test_characterization_od_prototype.py::test_od_prototype_event_snapshot
FAILED tests/agents/test_characterization_od_ppt.py::test_od_ppt_event_snapshot
FAILED tests/agents/test_characterization_app_builder.py::test_app_builder_event_snapshot
FAILED tests/agents/test_characterization_prototype_revision.py::test_prototype_revision_event_snapshot
=================== 5 failed, 5 passed, 1 warning in 38.61s ====================
```

The exact five failing ids must be identical at the end — same count AND same ids.
**No golden is to be regenerated.**

## lint-imports — 3 kept / 1 broken

Run **from `backend/`** (`/opt/homebrew/bin/lint-imports`). From the repo root it prints
"Could not read any configuration" and exits, which reads as a false pass.

```
kernel imports only capability ports (scaffold) KEPT
agents.workflows must not import the execution kernel or the web layer KEPT
agents.capabilities must not import the execution kernel or the web layer BROKEN
agents.runtime must not import the execution kernel or the web layer KEPT

Contracts: 3 kept, 1 broken.
```

Broken contract is pre-existing: `agents.capabilities.strategies.task_loop ->
agents.execution_engine.od_context (l.562)`.

## Regression target — `tests/agents/test_spec_revision_cycles.py`

**5 passed** at HEAD (the FIX-218 suite). Must stay 5 passed.

## INV-3 is NOT a constraint on this gate work

Verified: all 10 golden files contain **zero** `review_gate_ready` events — the
characterization harness runs with `gate_agent_ids=[]`
(`backend/tests/agents/_scripted_model.py:649`). The goldens therefore cannot observe any
change to `_run_review_gate`. INV-3 must not be used to argue for a weaker fence.

## Environment facts (verified, do not re-derive)

- `python3.11 -m pytest` from `backend/`. There is no `backend/.venv`; do not use `uv run`.
- Full `pytest tests/` hangs offline (Chromium/Bedrock/Postgres-gated) — targeted selections only.
- Live DB is `backend/dev.db`; the repo-root `dev.db` is a 0-byte decoy.
- Backend runs on `:8010`, frontend on `:3000` — leave both running.
