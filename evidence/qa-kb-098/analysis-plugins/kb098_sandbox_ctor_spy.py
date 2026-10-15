"""EXPERIMENT ONLY (QA-KB-098 analysis): record every RunSandbox construction the REAL engine
makes while test_two_revisions_write_distinct_log_paths drives a root run + two revisions, with
the file:line of the constructing call site.  Question it answers: which sandbox does the
factory (the object handed to playwright.bind_sandbox / pptx_tools.bind_sandbox) build for a
revision -- does its current_run_id carry the REVISION id, or the chain-root id?
The app import is lazy (inside the fixture) so it cannot run before tests/conftest.py pins env."""
import json
import sys

import pytest

OUT = "/private/tmp/claude-502/-Users-bilala-Developer-Projects-VELOCITY-AI-worktrees-feat-user-stories-v2/2d1a1575-310a-48fd-8155-2763a084604d/scratchpad/qa-kb-098/ctor.jsonl"


@pytest.fixture(autouse=True)
def _spy_runsandbox(monkeypatch):
    from app.agents import sandbox as sb

    orig = sb.RunSandbox.__init__

    def spy(self, user_id, sandbox_root_id, *a, current_run_id=None, **kw):
        fr = sys._getframe(1)
        site = f"{fr.f_code.co_filename.split('/backend/')[-1]}:{fr.f_lineno}"
        orig(self, user_id, sandbox_root_id, *a, current_run_id=current_run_id, **kw)
        with open(OUT, "a") as fh:
            fh.write(json.dumps({
                "site": site,
                "sandbox_root_id": sandbox_root_id,
                "current_run_id_arg": current_run_id,
                "effective_current_run_id": self.current_run_id,
                "browser_dir_leaf": self.browser_dir.name,
            }) + "\n")

    monkeypatch.setattr(sb.RunSandbox, "__init__", spy)
    yield
