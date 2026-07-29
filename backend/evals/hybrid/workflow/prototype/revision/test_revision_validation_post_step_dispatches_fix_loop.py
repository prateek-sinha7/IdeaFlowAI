"""RevisionValidationPostStep dispatch to the fix-loop (formerly "L4";
R-10 / D-06).

``RevisionValidationPostStep.run()`` is where the stashed instruction is
handed to the fix-loop. These tests spy the ``ctx.runner`` handle (the
capability's ONLY reach into the kernel — import purity) and assert the
threaded arguments: pre-edit baseline computed from
``revision_original_html``, and ``run_validation_fix_loop`` called with
``user_instruction=<the instruction>``, ``label="revision"``, both baselines,
and the COMPILED step's agent id (never a hardcoded literal).

Instruction propagation is confirmed INTACT through this layer — the gap
(L5) is in what the loop's selection can *fail on*, not in what it is given.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.eval

INSTRUCTION = "Make the Save button on Settings actually save"
ORIGINAL_HTML = "<!doctype html><html><body>original</body></html>"


class _SpyRunner:
    def __init__(self, tmp_path, artifact_exists: bool = True):
        self._tmp = tmp_path
        self.baseline_calls: list[str] = []
        self.fix_loop_calls: list[dict] = []
        if artifact_exists:
            (tmp_path / "prototype.html").write_text("<!doctype html>", encoding="utf-8")
        self.sandbox = self

    def path_for(self, name: str):
        return self._tmp / name

    async def compute_revision_baseline(self, original_html: str):
        self.baseline_calls.append(original_html)
        return {"static-issue-A"}, {"console-error-B"}

    async def run_validation_fix_loop(self, step, **kwargs):
        self.fix_loop_calls.append({"step": step, **kwargs})


class _Step:
    agent_id = "prototype-revision-agent"


class _Deliverable:
    name = "prototype.html"


class _Ctx:
    def __init__(self, runner):
        self.runner = runner
        self.deliverable = _Deliverable()
        self.revision_original_html = ORIGINAL_HTML
        self.revision_instruction = INSTRUCTION


@pytest.fixture
def post_step():
    from agents.capabilities.post_steps.revision_validation import (
        RevisionValidationPostStep,
    )

    return RevisionValidationPostStep()


@pytest.mark.asyncio
async def test_baseline_computed_on_seeded_original(post_step, tmp_path) -> None:
    runner = _SpyRunner(tmp_path)
    ctx = _Ctx(runner)
    await post_step.run(_Step(), ctx)

    assert runner.baseline_calls == [ORIGINAL_HTML]
    # Mirrored onto ctx for the phase-5 parity contract.
    assert ctx.revision_baseline_static == {"static-issue-A"}
    assert ctx.revision_baseline_console == {"console-error-B"}


@pytest.mark.asyncio
async def test_fix_loop_receives_instruction_and_baselines(post_step, tmp_path) -> None:
    runner = _SpyRunner(tmp_path)
    await post_step.run(_Step(), _Ctx(runner))

    assert len(runner.fix_loop_calls) == 1
    call = runner.fix_loop_calls[0]
    assert call["user_instruction"] == INSTRUCTION
    assert call["label"] == "revision"
    assert call["baseline_static"] == {"static-issue-A"}
    assert call["baseline_console"] == {"console-error-B"}
    assert call["filename"] == "prototype.html"
    # agent_id sourced from the compiled step, not a literal.
    assert call["agent_id"] == _Step.agent_id


@pytest.mark.asyncio
async def test_skips_when_agent_produced_no_artifact(post_step, tmp_path) -> None:
    runner = _SpyRunner(tmp_path, artifact_exists=False)
    await post_step.run(_Step(), _Ctx(runner))

    assert runner.baseline_calls == []
    assert runner.fix_loop_calls == []
