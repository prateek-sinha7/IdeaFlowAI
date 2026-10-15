"""QA-KB-094 analyze probe: drive ex_A4_human_gate offline (scripted model, hermetic sqlite),
answering the human gate with (a) the runner's bare word and (b) the UI's JSON decision.
Lives in the scratchpad, NOT in the repo. Aborts unless the DB is sqlite (never the live Postgres)."""
import asyncio, os, pathlib, sys, tempfile

BACKEND = "/Users/bilala/Developer/Projects/VELOCITY-AI-worktrees/feat-user-stories-v2/backend"
os.chdir(BACKEND); sys.path.insert(0, BACKEND)
db = pathlib.Path(tempfile.mkdtemp(prefix="qa-kb-094-")) / "probe.db"
os.environ["DATABASE_URL"] = f"sqlite:///{db}"          # same pin tests/conftest.py applies before app import
os.environ.setdefault("ENV", "development")

from app.core.config import settings
assert str(settings.DATABASE_URL).startswith("sqlite:///"), "refusing to run: not hermetic"
import app.models  # noqa: F401  registers models
from app.models.database import Base, engine
Base.metadata.create_all(bind=engine)

import tests.agents.test_conditional_human_gate_source_t26 as t26

def stop(events):
    return any(e.get("type") in ("pipeline_complete", "pipeline_failed", "pipeline_cancelled", "budget_aborted") for e in events)

async def one(label, edit):
    events = await t26._run_pipeline(edit, stop_when=stop)
    starts = [e["data"].get("agent_id") for e in events if e.get("type") == "agent_start"]
    blocked = [e["data"] for e in events if e.get("type") == "gate_blocked"]
    term = [e for e in events if e.get("type", "").startswith("pipeline_")]
    print(f"--- {label}: edited_content={edit!r}")
    print("  agent_start      :", starts)
    print("  gate_blocked     :", blocked)
    print("  terminal         :", [(e["type"], (e.get("data") or {}).get("error")) for e in term])

async def main():
    await one("A) the .http runner's answer (bare word)", "spanish")
    await one("B) the UI chip's answer (JSON decision)", '{"decision": "spanish"}')

asyncio.run(main())
