"""ISS-1159 (QA-KB-120): an unmaterialized declared output must not be staged or allowlisted.

Real RunSandbox + real git, offline, no model call.
"""

from __future__ import annotations

import logging
import types
import uuid
from unittest.mock import patch

import pytest

from agents.execution_engine import engine as eng
from app.agents.sandbox import RunSandbox

LOGGER_NAME = "agents.execution_engine.engine"


def _setup(tmp_path, *, strategy="single_file"):
    run_id = str(uuid.uuid4())
    sb = RunSandbox("u", run_id, runs_root=str(tmp_path))
    sb.ensure()
    sb._ws().git_init_sandbox()
    sb.run_log_path.parent.mkdir(parents=True, exist_ok=True)
    sb.run_log_path.write_text('{"event":"run_terminal"}\n', encoding="utf-8")
    ectx = types.SimpleNamespace(
        run_id=run_id,
        user_id="u",
        owner_id="u",
        workspace_id="w",
        runner=types.SimpleNamespace(sandbox=sb, registry=None, engine=None),
        final_status="failed",
        deliverable=types.SimpleNamespace(
            name="greeting.md", strategy=strategy, text_name=None
        ),
        revision_ordinal=1,
        step_visit_counts={},
        last_commit_blocked=False,
        completed_tasks=[],
        run_trace=None,
        last_streamed="",
    )
    return sb, run_id, ectx


@pytest.mark.issue("ISS-1159")
@pytest.mark.parametrize("mode", ["absent", "copy_raises", "streamed_empty"])
def test_unmaterialized_output_is_not_staged_nor_allowlisted(tmp_path, caplog, mode):
    """ISS-1159 - no stage_exact failure warning; only logs+summary staged and allowlisted."""
    sb, run_id, ectx = _setup(
        tmp_path,
        strategy="streamed_text" if mode == "streamed_empty" else "single_file",
    )
    if mode == "copy_raises":
        (sb.root / "greeting.md").write_text("hi", encoding="utf-8")
        real = eng.shutil.copy2

        def boom(src, dst, *a, **k):
            if str(dst).endswith("greeting.md"):
                raise OSError("boom")
            return real(src, dst, *a, **k)

        ctx = patch.object(eng.shutil, "copy2", boom)
    else:
        ctx = patch.object(eng, "logger", eng.logger)
    with ctx, caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        payload = eng.build_flat_payload(run_id, ectx)

    assert not [r for r in caplog.records if "stage_exact failed" in r.getMessage()]
    assert ".chain/greeting.md" not in payload.allowlist
    assert set(sb.staged_entries()) == {".chain/logs.jsonl", ".chain/summary.md"}
