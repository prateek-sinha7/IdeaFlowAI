"""EXPERIMENT ONLY (QA-KB-098 analysis): which key does a playwright session live under, and does
the engine's exit-time release(pipeline_run_id) (engine.py:7641) reach it for a REVISION run?
Uses the real RunSandbox, run_id_from_sandbox, get_session and release.  No browser is launched."""
import asyncio
import sys
import tempfile

sys.path.insert(0, "/Users/bilala/Developer/Projects/VELOCITY-AI-worktrees/feat-user-stories-v2/backend")

from app.agents import playwright_session as ps  # noqa: E402
from app.agents.sandbox import RunSandbox  # noqa: E402

tmp = tempfile.mkdtemp()
root_id, rev_id = "root-aaa", "revision-bbb"

root_sb = RunSandbox("u1", root_id, runs_root=tmp)
rev_sb = RunSandbox("u1", root_id, current_run_id=rev_id, runs_root=tmp)

key_root = ps.run_id_from_sandbox(root_sb)
key_rev = ps.run_id_from_sandbox(rev_sb)
print(f"run_id_from_sandbox(root sandbox)     = {key_root!r}")
print(f"run_id_from_sandbox(revision sandbox) = {key_rev!r}   (revision's logical id is {rev_id!r})")

# What the playwright tools do on first use inside the REVISION run (playwright.py:85-86 / :111):
ps.get_session(key_rev)
print(f"_SESSIONS keys after the revision's tool call: {sorted(ps._SESSIONS)}")

# What the engine does when the REVISION run exits (engine.py:7641): release(pipeline_run_id)
asyncio.run(ps.release(rev_id))
print(f"_SESSIONS keys after engine-style release(revision id): {sorted(ps._SESSIONS)}   <- session {'SURVIVES' if key_rev in ps._SESSIONS else 'released'}")

# Control: the ROOT run's exit releases by root id, which equals the key:
asyncio.run(ps.release(root_id))
print(f"_SESSIONS keys after release(root id):                  {sorted(ps._SESSIONS)}")
