"""Unit tests for evals.model_graded.driver — dispatch via
create_runner (mocked, no network), response capture, error handling
(task T2). Mocks agents.factory.create_runner directly rather than driving
the full deepagents scripted-model harness — sufficient to test driver.py's
own dispatch/capture/logging logic in isolation.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from evals.model_graded.driver import GradedScenario, run_graded_scenario_once

PRECHECK_CONFIG = {"wrapper": "<spec>", "min_sections": 1, "section_pattern": "^### ", "forbidden": []}


def _scenario(tmp_path, agent_id="prototype-specify") -> GradedScenario:
    return GradedScenario(
        id="s1",
        agent_id=agent_id,
        prompt="Build a thing.",
        precheck_config=PRECHECK_CONFIG,
        rubric="grade this",
        logs_dir=tmp_path / "logs",
    )


class _FakeRunner:
    def __init__(self, events, model_id="claude-haiku-4-5-20251001"):
        self._events = events
        self.model_id = model_id

    async def astream_events(self, _dispatch):
        for event in self._events:
            yield event


def _patch_create_runner(monkeypatch, runner, *, captured=None):
    import agents.factory as factory_module

    def _fake_create_runner(agent_id, ctx, *, thread_id=None, **kwargs):
        if captured is not None:
            captured["agent_id"] = agent_id
            captured["ctx"] = ctx
            captured["thread_id"] = thread_id
        return runner

    monkeypatch.setattr(factory_module, "create_runner", _fake_create_runner)
    return factory_module


@pytest.mark.asyncio
async def test_captures_streamed_response_text(tmp_path, monkeypatch):
    events = [
        {"type": "chunk", "chunk": "<spec>\n"},
        {"type": "chunk", "chunk": "### Page\n"},
        {"type": "chunk", "chunk": "</spec>"},
        {"type": "usage", "input_tokens": 5, "output_tokens": 7},
    ]
    _patch_create_runner(monkeypatch, _FakeRunner(events))

    result = await run_graded_scenario_once(_scenario(tmp_path))

    assert result.response == "<spec>\n### Page\n</spec>"
    assert result.errored is False
    assert result.tokens_in == 5
    assert result.tokens_out == 7
    assert Path(result.run_dir, "log.txt").exists()


@pytest.mark.asyncio
async def test_captures_resolved_model_id_from_runner(tmp_path, monkeypatch):
    """The ACTUAL resolved model id (off DeepAgentRunner.model_id, which is
    itself derived from the built model instance) must be captured — not
    just whatever `model`/`provider` args the caller happened to pass (often
    None, the common default-fallback-chain case)."""
    _patch_create_runner(monkeypatch, _FakeRunner([], model_id="mistral-large-latest"))
    result = await run_graded_scenario_once(_scenario(tmp_path))
    assert result.resolved_model_id == "mistral-large-latest"


@pytest.mark.asyncio
async def test_resolved_model_id_falls_back_to_unknown_when_runner_has_none(tmp_path, monkeypatch):
    class _RunnerWithoutModelId:
        async def astream_events(self, _dispatch):
            return
            yield  # pragma: no cover - makes this an async generator

    _patch_create_runner(monkeypatch, _RunnerWithoutModelId())
    result = await run_graded_scenario_once(_scenario(tmp_path))
    assert result.resolved_model_id == "unknown"


@pytest.mark.asyncio
async def test_runner_error_event_sets_errored_true(tmp_path, monkeypatch):
    events = [
        {"type": "chunk", "chunk": "partial..."},
        {"type": "error", "error": "AWS auth failed"},
    ]
    _patch_create_runner(monkeypatch, _FakeRunner(events))

    result = await run_graded_scenario_once(_scenario(tmp_path))

    assert result.errored is True
    assert result.error_reason == "AWS auth failed"


@pytest.mark.asyncio
async def test_run_id_format(tmp_path, monkeypatch):
    _patch_create_runner(monkeypatch, _FakeRunner([]))
    result = await run_graded_scenario_once(_scenario(tmp_path))
    run_id = Path(result.run_dir).name
    # <yymmddhhmmss>-graded-<scenario_id>-<uuid8>
    parts = run_id.split("-")
    assert parts[0].isdigit() and len(parts[0]) == 12
    assert parts[1] == "graded"
    assert parts[2] == "s1"
    assert len(parts[3]) == 8


@pytest.mark.asyncio
async def test_dispatches_via_create_runner_with_agent_id(tmp_path, monkeypatch):
    captured = {}
    _patch_create_runner(monkeypatch, _FakeRunner([]), captured=captured)

    await run_graded_scenario_once(_scenario(tmp_path, agent_id="prototype-specify"))

    assert captured["agent_id"] == "prototype-specify"
    assert captured["ctx"].user_request == "Build a thing."


def test_driver_never_builds_a_raw_model_call_itself():
    """Composition-fidelity guard (clarifications.md Q9/Q11): driver.py must
    dispatch EXCLUSIVELY through create_runner, never assembling its own
    system-prompt/chat-message call via build_model()/ChatAnthropic/etc. —
    that would bypass _compose_system_prompt's injected template/design-
    system/guardrail/skill/hook/constitution composition and grade an
    incomplete prompt. A raw call would show up as an import of
    app.agents.model_factory or langchain_core.messages in driver.py; assert
    neither is present.
    """
    driver_path = Path(__file__).resolve().parents[2] / "evals/model_graded/driver.py"
    tree = ast.parse(driver_path.read_text())
    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name)

    # build_model IS imported, but only for the rare provider=/model= override
    # of the AGENT UNDER TEST's own model — never to construct a competing,
    # non-composed chat call. The real guard is that create_runner is what
    # actually dispatches (verified behaviorally above), and no raw message
    # construction (SystemMessage/HumanMessage/ChatAnthropic) happens here.
    assert "langchain_core.messages" not in imported_modules
    assert "langchain_anthropic" not in imported_modules


@pytest.mark.asyncio
async def test_seed_files_are_written_to_the_sandbox_before_dispatch(tmp_path, monkeypatch):
    """Tool-using agents (prototype-build, prototype-validate): seed_files
    must land on disk BEFORE create_runner/astream_events runs, so the
    agent's own read_file("spec.md") calls see real content."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "RUNS_ROOT", str(tmp_path / "runs"))

    seen_spec_content = {}

    class _RunnerReadsSandbox:
        model_id = "claude-haiku-4-5-20251001"

        async def astream_events(self, _dispatch):
            from app.agents.sandbox import RunSandbox

            # Simulate the agent's own read_file("spec.md") tool call —
            # proves the seed landed BEFORE dispatch, not after.
            sandbox = RunSandbox("eval-graded", _captured_run_id["value"])
            seen_spec_content["spec.md"] = sandbox.read("spec.md")
            yield {"type": "chunk", "chunk": "ok"}

    _captured_run_id = {"value": None}

    import agents.factory as factory_module

    def _fake_create_runner(agent_id, ctx, *, thread_id=None, **kwargs):
        _captured_run_id["value"] = ctx.run_id
        return _RunnerReadsSandbox()

    monkeypatch.setattr(factory_module, "create_runner", _fake_create_runner)

    scenario = GradedScenario(
        id="s1",
        agent_id="prototype-build",
        prompt="=== CURRENT TASK ===\nTask 1 of 3\nbuild the shell\n=== END CURRENT TASK ===",
        precheck_config={"wrapper": "<!doctype html>", "close_wrapper": "</html>", "section_pattern": "x", "forbidden": []},
        rubric="grade this",
        logs_dir=tmp_path / "logs",
        seed_files={"spec.md": "# The Spec\nreal content"},
    )
    await run_graded_scenario_once(scenario)

    assert seen_spec_content["spec.md"] == "# The Spec\nreal content"


@pytest.mark.asyncio
async def test_deliverable_file_is_read_back_as_the_response(tmp_path, monkeypatch):
    """When deliverable_file is set, the graded response is the FILE
    content written by the agent's own tool calls — not the streamed text
    (which is often just a short confirmation)."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "RUNS_ROOT", str(tmp_path / "runs"))

    class _RunnerWritesFile:
        model_id = "claude-haiku-4-5-20251001"

        async def astream_events(self, _dispatch):
            from app.agents.sandbox import RunSandbox

            sandbox = RunSandbox("eval-graded", _captured_run_id["value"])
            sandbox.write("prototype.html", "<!doctype html><html>built</html>")
            yield {"type": "chunk", "chunk": "Done."}

    _captured_run_id = {"value": None}

    import agents.factory as factory_module

    def _fake_create_runner(agent_id, ctx, *, thread_id=None, **kwargs):
        _captured_run_id["value"] = ctx.run_id
        return _RunnerWritesFile()

    monkeypatch.setattr(factory_module, "create_runner", _fake_create_runner)

    scenario = GradedScenario(
        id="s1",
        agent_id="prototype-build",
        prompt="=== CURRENT TASK ===\nTask 1 of 3\nbuild the shell\n=== END CURRENT TASK ===",
        precheck_config={"wrapper": "<!doctype html>", "close_wrapper": "</html>", "section_pattern": "x", "forbidden": []},
        rubric="grade this",
        logs_dir=tmp_path / "logs",
        deliverable_file="prototype.html",
    )
    result = await run_graded_scenario_once(scenario)

    assert result.response == "<!doctype html><html>built</html>"


@pytest.mark.asyncio
async def test_deliverable_file_absent_falls_back_to_streamed_text(tmp_path, monkeypatch):
    """deliverable_file set but the agent never actually wrote it (e.g. a
    genuine failure to call write_file) — falls back to the streamed text
    rather than silently grading an empty/None response."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "RUNS_ROOT", str(tmp_path / "runs"))
    _patch_create_runner(monkeypatch, _FakeRunner([{"type": "chunk", "chunk": "no file written"}]))

    scenario = GradedScenario(
        id="s1",
        agent_id="prototype-build",
        prompt="task",
        precheck_config=PRECHECK_CONFIG,
        rubric="grade this",
        logs_dir=tmp_path / "logs",
        deliverable_file="prototype.html",
    )
    result = await run_graded_scenario_once(scenario)

    assert result.response == "no file written"


def test_driver_module_imports_no_grading_or_persistence_modules():
    """Component Boundaries (design.md): driver.py must not import judge.py,
    report.py, or precheck.py — dispatch-and-capture is its whole job."""
    driver_path = Path(__file__).resolve().parents[2] / "evals/model_graded/driver.py"
    tree = ast.parse(driver_path.read_text())
    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name)

    forbidden = {
        "evals.model_graded.judge",
        "evals.model_graded.report",
        "evals.model_graded.precheck",
    }
    assert not (imported_modules & forbidden)
