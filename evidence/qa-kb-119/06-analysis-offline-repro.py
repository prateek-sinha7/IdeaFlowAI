"""Offline repro for QA-KB-119 (scratch, outside the repo): same harness as
backend/tests/integration/api/test_runs_api_events_api.py, but with 1,200 events.
Run from backend/: .venv/bin/python <this file>. No network, in-memory SQLite."""
import sys
import time

sys.path.insert(0, ".")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.runs import router
from app.core.dependencies import get_current_user
from app.models.database import Base, get_db
from tests.integration.api.test_runs_api_events_api import _FakeUser, _seed_events, _seed_run

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Base.metadata.create_all(bind=engine)
db = sessionmaker(bind=engine, autocommit=False, autoflush=False)()

app = FastAPI()
app.include_router(router)
app.dependency_overrides[get_current_user] = lambda: _FakeUser(id="owner")


def _db():
    yield db


app.dependency_overrides[get_db] = _db
client = TestClient(app)

N = 1200
_seed_run(db)
_seed_events(db, n=N)

t0 = time.monotonic()
r = client.get("/api/runs/run-1/events")  # NO params
dt = time.monotonic() - t0
body = r.json()
print(f"status={r.status_code} seeded={N} returned={len(body['events'])} elapsed={dt:.3f}s")
print(f"envelope keys: {sorted(body)}")
print(f"has_more/next_after present: {'has_more' in body}/{'next_after' in body}")
print(f"limit param accepted? GET ?limit=10 -> returned {len(client.get('/api/runs/run-1/events?limit=10').json()['events'])} rows (10 expected once paging exists)")
print(f"after=-1 -> status {client.get('/api/runs/run-1/events?after=-1').status_code} (422 expected once ge=0 lands)")
