"""EXPERIMENT ONLY (QA-KB-098 analysis): what would happen to the physical sandbox directory if the
engine's sandbox (engine.py:4415) were built WITH current_run_id=<revision id>, given that
engine.py:9779 hands `sandbox.run_id` to AgentContext.run_id and factory.py:371 uses ctx.run_id
as the DIRECTORY key?  Uses the real RunSandbox only; no engine, no browser."""
import sys
import tempfile

sys.path.insert(0, "/Users/bilala/Developer/Projects/VELOCITY-AI-worktrees/feat-user-stories-v2/backend")
from app.agents.sandbox import RunSandbox  # noqa: E402

tmp = tempfile.mkdtemp()
root_id, rev_id = "chain-root-aaa", "revision-bbb"

# today (engine.py:4415): no current_run_id
engine_sb_today = RunSandbox("u1", root_id, runs_root=tmp)
fac_today = RunSandbox("u1", engine_sb_today.run_id, runs_root=tmp)   # factory.py:371 with ctx.run_id = sandbox.run_id (engine.py:9779)
print(f"today:     engine sandbox.run_id={engine_sb_today.run_id!r}; factory sandbox dir leaf={fac_today.root.name!r}; shared with engine dir: {fac_today.root == engine_sb_today.root}")

# naive fix: add current_run_id=<revision id> at engine.py:4415 and change nothing else
engine_sb_fixed = RunSandbox("u1", root_id, current_run_id=rev_id, runs_root=tmp)
fac_fixed = RunSandbox("u1", engine_sb_fixed.run_id, runs_root=tmp)   # same two call sites, unchanged
print(f"naive fix: engine sandbox.run_id={engine_sb_fixed.run_id!r}; factory sandbox dir leaf={fac_fixed.root.name!r}; shared with engine dir: {fac_fixed.root == engine_sb_fixed.root}")
