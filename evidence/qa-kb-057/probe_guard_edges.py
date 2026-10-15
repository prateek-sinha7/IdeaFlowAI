"""Probe 2 for QA-KB-057 (analyzer evidence; edits no repo file): behaviours of the duplicate-context guard
that the 8 dead tests never covered. Reuses the harness replica from probe_seeds.py.

Usage (from backend/):
  PYTHONDONTWRITEBYTECODE=1 PROBE_SCRATCH=$(mktemp -d) .venv/bin/python ../evidence/qa-kb-057/probe_guard_edges.py

  E1  refused launch (bare seed -> 422): is an orphan run_id='pending' audit row left?
  E2  admitted launch with brief+block: how many strip audit rows (endpoint-level vs core-level guard)?
  E3  admitted launch whose message IS only the legacy block: stripped or kept? audit outcome?
"""

from __future__ import annotations

import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import probe_seeds as P  # noqa: E402  (sets DATABASE_URL / RUNS_ROOT from PROBE_SCRATCH)

import pytest  # noqa: E402

T = P.T
from app.models.run_provenance_audit import RunProvenanceAudit  # noqa: E402
from app.models.workflow import WorkflowRun  # noqa: E402


def audits(env):
    db = env["ws"]._get_db()
    try:
        return [
            (r.operation, r.run_id[:8] if r.run_id else r.run_id, r.source_ref and r.source_ref[:8], r.outcome)
            for r in db.query(RunProvenanceAudit).order_by(RunProvenanceAudit.created_at).all()
        ]
    finally:
        db.close()


def runs(env):
    db = env["ws"]._get_db()
    try:
        return [(r.id[:8], r.input) for r in db.query(WorkflowRun).order_by(WorkflowRun.created_at).all()]
    finally:
        db.close()


def scenario(name, seed, message):
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(P.settings, "RUNS_ROOT", str(P.RUNS))
        mp.setattr(T, "_seed_source_run", P.SEEDS[seed])
        env, db_engine = P.make_env(mp, with_principal=True)
        try:
            user = T._seed_user(env)
            env["state"]["user"] = user
            src = T._seed_source_run(env, user.id)
            resp = T._post_launch(
                env, message=message, pipeline_type="user_stories", source_workflow_run_id=src.id
            )
            print(f"\n[{name}] seed={seed} -> HTTP {resp.status_code} {resp.text[:110]}")
            print("   source id        :", src.id[:8])
            print("   audit rows       :", audits(env))
            print("   minted runs (id, input) excluding source:")
            for rid, inp in runs(env):
                if rid != src.id[:8]:
                    print("     ", rid, repr(inp))
            print("   engine invoked   :", T._RecordingEngine.invoked)
        finally:
            from app.models.database import Base

            Base.metadata.drop_all(bind=db_engine)
            db_engine.dispose()


BRIEF_PLUS_BLOCK = "Build me a backlog" + T._LEGACY_BLOCK
ONLY_BLOCK = T._LEGACY_BLOCK.lstrip("\n")

scenario("E1 refused launch leaves what audit rows?", "bare", BRIEF_PLUS_BLOCK)
scenario("E2 admitted brief+block", "legacy", BRIEF_PLUS_BLOCK)
scenario("E3 admitted, message is ONLY the legacy block", "legacy", ONLY_BLOCK)
