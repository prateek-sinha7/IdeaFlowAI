"""Read-only probe for QA-KB-057 / ISS-905 (analyzer evidence; edits no repo file).

Runs the REAL bodies of tests/integration/api/test_duplicate_context_guard_api.py
against several source-run seeds, with the get_current_principal override added in
the harness replica below. Nothing in the repo is edited; RUNS_ROOT and the DB are
pinned to the scratchpad before any app import.

Usage (from backend/):
  PYTHONDONTWRITEBYTECODE=1 PROBE_SCRATCH=$(mktemp -d) .venv/bin/python ../evidence/qa-kb-057/probe_seeds.py [noprincipal|bare|legacy|v2 ...]
"""

from __future__ import annotations

import importlib
import inspect
import os
import pathlib
import sys
import traceback
import uuid

SCRATCH = pathlib.Path(os.environ["PROBE_SCRATCH"])
RUNS = SCRATCH / "runs"
RUNS.mkdir(parents=True, exist_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{SCRATCH / 'probe.db'}"
os.environ["RUNS_ROOT"] = str(RUNS)
sys.path.insert(0, str(pathlib.Path.cwd()))

import pytest  # noqa: E402

T = importlib.import_module("tests.integration.api.test_duplicate_context_guard_api")
import app.api.run_commands as rc_module  # noqa: E402
import agents.execution_engine.engine as engine_mod  # noqa: E402
from app.core.config import settings  # noqa: E402

ORIG_SEED = T._seed_source_run
CALLS: list[str] = []


def make_env(mp, *, with_principal: bool):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.api import run_engine as ws_module
    from app.core.dependencies import get_current_principal, get_current_user
    from app.models.database import Base
    from tests.fakes.principal import principal_for

    db_engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Session = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    Base.metadata.create_all(bind=db_engine)
    mp.setattr(ws_module, "_get_db", lambda: Session())
    mp.setattr(rc_module, "_get_db", lambda: Session())
    T._RecordingEngine.invoked = False
    T._RecordingEngine.last_kwargs = None
    mp.setattr(engine_mod, "get_execution_engine", lambda: T._RecordingEngine())

    app = FastAPI()
    app.include_router(rc_module.router)
    state: dict = {"user": None}
    app.dependency_overrides[get_current_user] = lambda: state["user"]
    if with_principal:
        app.dependency_overrides[get_current_principal] = lambda: (
            state["user"],
            principal_for(state["user"]),
        )
    return {
        "ws": ws_module,
        "client": TestClient(app),
        "state": state,
        "Session": Session,
    }, db_engine


# ---------------------------------------------------------------- seeds
def seed_bare(env, user_id):
    return ORIG_SEED(env, user_id)


def seed_legacy(env, user_id):
    """Pre-v2 shape: no finalization row, nested .chain/<id>/summary.md, no git."""
    from app.agents.sandbox import RunSandbox

    run = ORIG_SEED(env, user_id)
    sb = RunSandbox(user_id, run.id)
    sb.ensure()
    sb.write(f".chain/{run.id}/summary.md", f"run_id: {run.id}\n")
    return run


def seed_v2(env, user_id):
    """v2 shape: finalization row + real git sandbox + flat .chain/ at tag v1 + internal ref."""
    from app.agents.sandbox import RunSandbox
    from app.models.run_finalization import RunFinalization

    run = ORIG_SEED(env, user_id)
    sb = RunSandbox(user_id, run.id)
    sb.ensure()
    sb.git_init_sandbox()
    paths = [".chain/summary.md", ".chain/logs.jsonl", ".chain/user_stories.md"]
    sb.write(".chain/summary.md", f"run_id: {run.id}\noutput_filename: user_stories.md\n")
    sb.write(".chain/logs.jsonl", '{"event":"terminal"}\n')
    sb.write(".chain/user_stories.md", "# stories\n")
    # paths=[] (not the list): the force_add pass already staged the three ignored
    # .chain/ files; a second non-forced `git add` of an ignored path exits 1.
    sha = sb.commit_all("snapshot", paths=[], force_add=frozenset(paths))
    sb.create_tag("v1")
    sb.create_run_ref(run.id)
    db = env["ws"]._get_db()
    try:
        db.add(
            RunFinalization(
                owner_id=user_id,
                workspace_id="ws-1",
                run_id=run.id,
                published_status="completed",
                candidate_status="completed",
                payload_chainable=True,
                commit_sha=sha,
                internal_ref=f"refs/ideaflow/runs/{run.id}",
                git_tag="v1",
                tag_state="created",
            )
        )
        db.commit()
    finally:
        db.close()
    return run


SEEDS = {"bare": seed_bare, "legacy": seed_legacy, "v2": seed_v2}


def instrument(mp):
    for name in ("_select_v2_payload", "_select_legacy_payload_or_refuse"):
        real = getattr(rc_module, name)

        def wrap(*a, __real=real, __name=name, **k):
            CALLS.append(f"{__name}:enter")
            try:
                out = __real(*a, **k)
                CALLS.append(f"{__name}:ok")
                return out
            except Exception as exc:  # noqa: BLE001
                CALLS.append(f"{__name}:raised:{getattr(exc, 'reason', type(exc).__name__)}")
                raise

        mp.setattr(rc_module, name, wrap)


def run_variant(variant: str, with_principal: bool = True) -> None:
    print(f"\n=== seed={variant} principal_override={with_principal} RUNS_ROOT={settings.RUNS_ROOT}")
    passed = failed = 0
    for cls_name, cls in inspect.getmembers(T, inspect.isclass):
        if not cls_name.startswith("Test"):
            continue
        for meth_name, _ in inspect.getmembers(cls, inspect.isfunction):
            if not meth_name.startswith("test_"):
                continue
            CALLS.clear()
            with pytest.MonkeyPatch.context() as mp:
                mp.setattr(settings, "RUNS_ROOT", str(RUNS))
                mp.setattr(T, "_seed_source_run", SEEDS[variant])
                instrument(mp)
                env, db_engine = make_env(mp, with_principal=with_principal)
                try:
                    getattr(cls(), meth_name)(env)
                    status = "PASS"
                    passed += 1
                except AssertionError as exc:
                    status = "FAIL " + str(exc).splitlines()[0][:140]
                    failed += 1
                except Exception:  # noqa: BLE001
                    status = "ERROR " + traceback.format_exc().splitlines()[-1][:140]
                    failed += 1
                finally:
                    from app.models.database import Base

                    Base.metadata.drop_all(bind=db_engine)
                    db_engine.dispose()
            print(f"  {status:<9} {cls_name}::{meth_name}   calls={CALLS}")
    print(f"  -> passed={passed} failed={failed}")


if __name__ == "__main__":
    wanted = sys.argv[1:] or ["bare", "legacy", "v2"]
    for v in wanted:
        if v == "noprincipal":
            run_variant("bare", with_principal=False)
        else:
            run_variant(v)
