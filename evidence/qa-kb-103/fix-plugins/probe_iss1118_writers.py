"""Probe the override WRITERS and READ over HTTP (ISS-1118 test notes, API section).

Both routers on one in-memory SQLite session (harness of test_workflow_override_e2e_api.py).
Nothing is launched. Not a test file.
"""
import copy
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from agents.workflows.manifest import load_manifest
from app.api.user_workflows import router as uw_router
from app.api.workflows import router as wf_router
from app.core.dependencies import get_current_principal, get_current_user
from app.models.database import Base, get_db
from tests.fakes.principal import principal_for


class U:
    def __init__(self, id, tier):
        self.id, self.tier = id, tier


engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Base.metadata.create_all(bind=engine)
session = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
app = FastAPI()
app.include_router(wf_router)
app.include_router(uw_router)
state = {"user": U("owner", "enterprise")}
app.dependency_overrides[get_current_user] = lambda: state["user"]
app.dependency_overrides[get_current_principal] = lambda: (state["user"], principal_for(state["user"]))


def _db():
    yield session


app.dependency_overrides[get_db] = _db
c = TestClient(app)
steps = lambda wid: copy.deepcopy(list(load_manifest(wid, Path("agents/workflows")).steps))


def save(wid, st, name):
    return c.post("/api/user-workflows", json={
        "name": name, "base_pipeline_type": wid, "agent_ids": [s["agent"] for s in st],
        "manifest": {"steps": st}, "overrides_pipeline_type": wid,
    })


for wid in ["prototype", "app_builder", "prototype_revision", "prototype_feature_revision", "prototype_large_revision"]:
    r = save(wid, steps(wid), f"My {wid}")
    line = f"POST  {wid} override (file's own steps): {r.status_code}"
    if r.status_code == 201:
        rid = r.json()["id"]
        d = c.get(f"/api/workflows/{wid}").json()
        refs = {s.get("agent"): {k: s.get(k) for k in ("compaction", "post_step") if s.get(k)} for s in (d.get("manifest_steps") or d.get("steps") or []) if isinstance(s, dict)}
        refs = {a: v for a, v in refs.items() if v}
        line += f" | GET is_overridden={d.get('is_overridden')} refs={refs}"
        p = c.patch(f"/api/user-workflows/{rid}", json={"manifest": {"steps": steps(wid)}})
        line += f" | PATCH {p.status_code}"
        sf = c.post(f"/api/user-workflows/{rid}/sync-from-file", json={"pipeline_type": wid})
        line += f" | sync-from-file own file {sf.status_code}"
    else:
        line += f" {r.text[:160]}"
    print(line)

# Controls on the writers
st = steps("prototype")
for s in st:
    s.pop("compaction", None)
st[0]["compaction"] = "html_skeleton"
state["user"] = U("owner2", "enterprise")
r = save("prototype", st, "Added ref")
print(f"POST  prototype override with compaction ADDED on step 0: {r.status_code} {r.text[:150]}")

state["user"] = U("owner3", "enterprise")
r = c.post("/api/user-workflows", json={"name": "My Deck", "base_pipeline_type": "ppt", "agent_ids": ["ppt-brief-analyst"],
                                        "manifest": {"steps": steps("ppt")}, "overrides_pipeline_type": "ppt"})
rid = r.json().get("id") if r.status_code == 201 else None
print(f"POST  ppt override (own steps): {r.status_code}")
if rid:
    sf = c.post(f"/api/user-workflows/{rid}/sync-from-file", json={"pipeline_type": "sample_subagents_parallel"})
    print(f"SYNC  sample_subagents_parallel into the ppt override: {sf.status_code} {sf.text[:150]}")
    sf = c.post(f"/api/user-workflows/{rid}/sync-from-file", json={"pipeline_type": "prototype"})
    print(f"SYNC  prototype into the ppt override (baseline is ppt): {sf.status_code} {sf.text[:150]}")
