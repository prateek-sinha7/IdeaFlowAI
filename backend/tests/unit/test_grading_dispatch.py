"""Unit tests for evals.grading.dispatch — offline dispatch of one row.

`agents.factory.create_runner` is monkeypatched and `settings.RUNS_ROOT` points
at tmp_path, so nothing here touches a model or the network. Covers the copied
driver's invariants plus the six documented changes (T4).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import agents.factory
from app.agents.sandbox import RunSandbox
from app.core.config import settings
from evals.grading.model import dispatch
from evals.grading.model.stage_input import StageInput

AGENT_ID = "prototype-specify"
DISPATCH_PATH = Path(dispatch.__file__)


class FakeRunner:
    """Yields a scripted event list, mirroring DeepAgentRunner.astream_events."""

    def __init__(self, events, model_id="claude-haiku-4-5-20251001"):
        self._events = events
        if model_id is not None:
            self.model_id = model_id

    async def astream_events(self, _prompt):
        """Replay the scripted events."""
        for event in self._events:
            yield event


def patch_create_runner(monkeypatch, runner, captured=None):
    """Swap create_runner for a fake, recording the kwargs it was called with."""

    def fake_create_runner(agent_id, ctx, *, thread_id=None, run_sandbox=None, **kwargs):
        if captured is not None:
            captured.update(
                agent_id=agent_id, ctx=ctx, thread_id=thread_id, run_sandbox=run_sandbox
            )
        return runner

    monkeypatch.setattr(agents.factory, "create_runner", fake_create_runner)


@pytest.fixture(autouse=True)
def runs_root(tmp_path, monkeypatch):
    """Root every RunSandbox under tmp_path instead of the unwritable /app/runs."""
    monkeypatch.setattr(settings, "RUNS_ROOT", str(tmp_path / "runs"))
    return tmp_path


async def run(tmp_path, **overrides):
    """Call run_row with sensible defaults for a single-row dispatch."""
    stage_input = overrides.pop("stage_input", StageInput(row_id="row-1", prompt="Build a thing."))
    kwargs = {
        "agent_id": AGENT_ID,
        "sandbox_run_id": "260729-120000-ds-row-1",
        "log_path": tmp_path / "logs" / "row-1.log",
    }
    kwargs.update(overrides)
    return await dispatch.run_row(stage_input, **kwargs)


@pytest.mark.asyncio
async def test_streamed_chunks_are_joined_and_usage_is_summed(tmp_path, monkeypatch):
    events = [
        {"type": "chunk", "chunk": "<spec>\n"},
        {"type": "usage", "input_tokens": 5, "output_tokens": 7},
        {"type": "tool_call", "tool": "read_file", "args": {"path": "spec.md"}},
        {"type": "tool_result", "tool": "read_file", "result": "content"},
        {"type": "chunk", "chunk": "### Page\n</spec>"},
        {"type": "usage", "input_tokens": 11, "output_tokens": 13},
        {"type": "done"},
    ]
    patch_create_runner(monkeypatch, FakeRunner(events))

    result = await run(tmp_path)

    assert result.response == "<spec>\n### Page\n</spec>"
    assert result.errored is False
    assert (result.tokens_in, result.tokens_out) == (16, 20)
    log = Path(result.log_path).read_text()
    assert "read_file" in log and "tokens: in=16 out=20" in log


@pytest.mark.asyncio
async def test_seed_files_land_in_the_sandbox_before_dispatch(tmp_path, monkeypatch):
    seen = {}

    class ReadingRunner:
        model_id = "claude-haiku-4-5-20251001"

        async def astream_events(self, _prompt):
            sandbox = RunSandbox(dispatch.USER_ID, "260729-120000-ds-row-1")
            seen["spec.md"] = sandbox.read("spec.md")
            yield {"type": "chunk", "chunk": "ok"}

    patch_create_runner(monkeypatch, ReadingRunner())
    stage_input = StageInput(
        row_id="row-1", prompt="task", seed_files={"spec.md": "# The Spec\nreal content"}
    )

    result = await run(tmp_path, stage_input=stage_input)

    assert seen["spec.md"] == "# The Spec\nreal content"
    assert result.seed_files == {"spec.md": "# The Spec\nreal content"}


@pytest.mark.asyncio
async def test_deliverable_file_replaces_the_response(tmp_path, monkeypatch):
    class WritingRunner:
        model_id = "claude-haiku-4-5-20251001"

        async def astream_events(self, _prompt):
            sandbox = RunSandbox(dispatch.USER_ID, "260729-120000-ds-row-1")
            sandbox.write("prototype.html", "<!doctype html><html>built</html>")
            yield {"type": "chunk", "chunk": "Done."}

    patch_create_runner(monkeypatch, WritingRunner())
    stage_input = StageInput(row_id="row-1", prompt="task", deliverable_file="prototype.html")

    result = await run(tmp_path, stage_input=stage_input)

    assert result.response == "<!doctype html><html>built</html>"
    assert result.errored is False


@pytest.mark.asyncio
async def test_unwritten_deliverable_falls_back_to_streamed_text(tmp_path, monkeypatch):
    patch_create_runner(monkeypatch, FakeRunner([{"type": "chunk", "chunk": "no file written"}]))
    stage_input = StageInput(row_id="row-1", prompt="task", deliverable_file="prototype.html")

    result = await run(tmp_path, stage_input=stage_input)

    assert result.response == "no file written"
    assert result.errored is False


@pytest.mark.asyncio
async def test_error_event_errors_the_row_and_skips_deliverable_readback(tmp_path, monkeypatch):
    class ErroringRunner:
        model_id = "claude-haiku-4-5-20251001"

        async def astream_events(self, _prompt):
            sandbox = RunSandbox(dispatch.USER_ID, "260729-120000-ds-row-1")
            sandbox.write("prototype.html", "<html>partial</html>")
            yield {"type": "chunk", "chunk": "partial..."}
            yield {"type": "error", "error": "AWS auth failed"}

    patch_create_runner(monkeypatch, ErroringRunner())
    stage_input = StageInput(row_id="row-1", prompt="task", deliverable_file="prototype.html")

    result = await run(tmp_path, stage_input=stage_input)

    assert result.errored is True
    assert result.error_reason == "AWS auth failed"
    assert result.response == "partial..."


@pytest.mark.asyncio
async def test_empty_response_is_classified_errored(tmp_path, monkeypatch):
    patch_create_runner(monkeypatch, FakeRunner([{"type": "chunk", "chunk": "   \n"}]))

    result = await run(tmp_path)

    assert result.errored is True
    assert "empty response" in result.error_reason
    assert "EMPTY RESPONSE" in Path(result.log_path).read_text()


@pytest.mark.asyncio
async def test_sandbox_run_id_over_128_chars_raises(tmp_path, monkeypatch):
    patch_create_runner(monkeypatch, FakeRunner([{"type": "chunk", "chunk": "ok"}]))

    with pytest.raises(ValueError, match="128"):
        await run(tmp_path, sandbox_run_id="x" * 129)


@pytest.mark.asyncio
async def test_thread_id_and_run_sandbox_are_passed_explicitly(tmp_path, monkeypatch):
    captured = {}
    patch_create_runner(monkeypatch, FakeRunner([{"type": "chunk", "chunk": "ok"}]), captured)
    stage_input = StageInput(row_id="row-1", prompt="task", seed_files={"spec.md": "seeded"})

    result = await run(tmp_path, stage_input=stage_input)

    assert captured["thread_id"] == f"260729-120000-ds-row-1:{AGENT_ID}"
    assert captured["run_sandbox"] is not None
    assert captured["run_sandbox"].read("spec.md") == "seeded"
    assert captured["ctx"].run_id == result.sandbox_run_id
    assert captured["ctx"].user_id == dispatch.USER_ID


@pytest.mark.asyncio
async def test_resolved_model_id_falls_back_to_unknown(tmp_path, monkeypatch):
    patch_create_runner(monkeypatch, FakeRunner([{"type": "chunk", "chunk": "ok"}], model_id=None))

    result = await run(tmp_path)

    assert result.resolved_model_id == "unknown"


@pytest.mark.asyncio
async def test_returns_the_composed_system_prompt_actually_used(tmp_path, monkeypatch):
    patch_create_runner(monkeypatch, FakeRunner([{"type": "chunk", "chunk": "ok"}]))

    result = await run(tmp_path)

    assert result.system_prompt.strip()
    assert result.system_prompt == dispatch._compose_prompt_for(
        AGENT_ID, agents.factory.AgentContext(user_request="Build a thing.", user_id=dispatch.USER_ID)
    )


def test_dispatch_module_has_no_inline_imports():
    """Composition guard: every import must sit at module level, never in a body."""
    tree = ast.parse(DISPATCH_PATH.read_text())
    inline = [
        node
        for func in ast.walk(tree)
        if isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef))
        for node in ast.walk(func)
        if isinstance(node, (ast.Import, ast.ImportFrom))
    ]
    assert not inline


def test_dispatch_never_builds_a_raw_model_call():
    """It must dispatch through create_runner, never assemble its own chat call."""
    tree = ast.parse(DISPATCH_PATH.read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)

    assert "langchain_core.messages" not in imported
    assert "langchain_anthropic" not in imported
    assert "agents.factory" in imported
